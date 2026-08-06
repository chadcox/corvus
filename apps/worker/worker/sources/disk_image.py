"""Disk image evidence adapter (EWF/E01 and raw/dd).

Corvus does not mount disk images. Detected images are handed to
Plaso/log2timeline, which reads EWF and raw images directly through its
bundled dfVFS/libewf support, so no FUSE mount, privileged container, or
loop device is required.

Plaso is optional (see ``scripts/install-open-forensics.sh``). When it is
unavailable the adapter degrades to the generic directory adapter so the
package is still indexed and the limitation is recorded in ingest notes.
"""

import json
from pathlib import Path
from typing import Any
from uuid import UUID

from worker.config import settings
from worker.parsers.external_events import parse_tool_outputs
from worker.sources.base import ProgressCallback
from worker.sources.external_tools import plaso_available, run_plaso
from worker.sources.generic import GenericDirectoryAdapter
from worker.sources.result_merge import empty_result, merge_results

# EWF segment headers: EWF-E01, logical (L01) and EWF2-Ex01.
_EWF_MAGICS: tuple[bytes, ...] = (
    b"EVF\x09\x0d\x0a\xff\x00",
    b"LVF\x09\x0d\x0a\xff\x00",
    b"EVF2\x0d\x0a\x81\x00",
)

# Only first segments are listed; Plaso follows the remaining segments itself.
_EWF_SUFFIXES = {".e01", ".ex01", ".l01", ".lx01"}
_RAW_SUFFIXES = {".raw", ".dd", ".img", ".001"}
_IMAGE_SUFFIXES = _EWF_SUFFIXES | _RAW_SUFFIXES

_GPT_SIGNATURE = b"EFI PART"
_MBR_BOOT_SIGNATURE = b"\x55\xaa"

# Bound the package walk so a large triage collection cannot turn adapter
# selection into a full recursive stat of every file.
_MAX_SCAN_ENTRIES = 20_000

# Upper bound on filesystem nodes derived from one disk image, so a full-volume
# image cannot exhaust worker memory or the insert batch.
MAX_DISK_IMAGE_FS_NODES = 250_000

_EXPLICIT_COLLECTORS = {"disk_image", "disk-image", "diskimage", "e01", "ewf"}


def _read_header(path: Path, size: int = 520) -> bytes:
    try:
        with path.open("rb") as handle:
            return handle.read(size)
    except OSError:
        return b""


def looks_like_disk_image(path: Path) -> bool:
    """Verify a file is an EWF or raw disk image by content, not by name.

    Raw images are only accepted when they carry an MBR or GPT signature,
    which keeps memory captures (``memdump.raw``) and unrelated ``.bin``
    blobs from being claimed as disks.
    """
    suffix = path.suffix.lower()
    if suffix not in _IMAGE_SUFFIXES:
        return False

    header = _read_header(path)
    if len(header) < 16:
        return False

    if any(header.startswith(magic) for magic in _EWF_MAGICS):
        return True
    if suffix in _EWF_SUFFIXES:
        # Claims to be EWF but has no EWF header.
        return False

    if len(header) >= 512 and header[510:512] == _MBR_BOOT_SIGNATURE:
        return True
    return len(header) >= 520 and header[512:520] == _GPT_SIGNATURE


def _read_package_manifest(package_dir: Path) -> dict[str, Any]:
    """Best-effort read of manifest.json for adapter selection."""
    manifest_path = package_dir / "manifest.json"
    if not manifest_path.is_file():
        return {}
    try:
        loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _manifest_image(package_dir: Path, manifest: dict[str, Any] | None) -> Path | None:
    if not manifest:
        return None
    declared = manifest.get("disk_image_path")
    if not declared or not isinstance(declared, str):
        return None
    root = package_dir.resolve()
    candidate = (root / declared).resolve()
    # Manifests are attacker-controlled input; keep the path inside the package.
    if not candidate.is_relative_to(root) or not candidate.is_file():
        return None
    return candidate


def find_disk_image_in_package(
    package_dir: Path,
    manifest: dict[str, Any] | None = None,
) -> Path | None:
    """Return the primary disk image in a package, or None.

    An explicit ``disk_image_path`` manifest entry wins and is trusted without
    content sniffing, so operators can declare formats this module does not
    recognize. Otherwise the package is scanned for a content-verified image.
    Results are deterministic.
    """
    if manifest is None:
        manifest = _read_package_manifest(package_dir)
    declared = _manifest_image(package_dir, manifest)
    if declared is not None:
        return declared

    candidates: list[Path] = []
    for index, path in enumerate(sorted(package_dir.rglob("*"))):
        if index >= _MAX_SCAN_ENTRIES:
            break
        if path.suffix.lower() not in _IMAGE_SUFFIXES:
            continue
        if not path.is_file():
            continue
        if looks_like_disk_image(path):
            candidates.append(path)

    if not candidates:
        return None
    # Prefer EWF containers over bare raw images when both are present.
    candidates.sort(key=lambda p: (p.suffix.lower() not in _EWF_SUFFIXES, str(p)))
    return candidates[0]


def filesystem_nodes_from_events(
    events: list[dict[str, Any]],
    evidence_source_id: str,
    *,
    limit: int = MAX_DISK_IMAGE_FS_NODES,
) -> list[dict[str, Any]]:
    """Derive filesystem nodes from Plaso ``fs:stat`` events.

    The image is never mounted, so the file tree shown in the Disk view has to
    come from the timeline. Plaso emits one ``fs:stat`` event per timestamp per
    file entry, so entries are de-duplicated by path and parent directories are
    synthesised for paths whose directory entry was not itself emitted.
    """
    nodes: dict[str, dict[str, Any]] = {}

    def parent_of(full_path: str) -> str | None:
        parent = full_path.rsplit("/", 1)[0]
        if not parent or parent == full_path:
            return None
        return parent

    def add_parents(full_path: str) -> None:
        parent = parent_of(full_path)
        while parent:
            if parent in nodes:
                return
            nodes[parent] = {
                "evidence_source_id": evidence_source_id,
                "full_path": parent,
                "name": (parent.rsplit("/", 1)[-1] or "/")[:512],
                "is_directory": True,
                "size": None,
                "is_deleted": False,
                "parent_path": parent_of(parent),
            }
            parent = parent_of(parent)

    for event in events:
        data = event.get("data")
        if not isinstance(data, dict) or data.get("data_type") != "fs:stat":
            continue
        # ``filename`` is the bare path (``\Windows\System32`` on NTFS,
        # ``/etc/passwd`` on TSK). Only ``display_name`` carries a back-end
        # prefix (``NTFS:\...``); splitting ``filename`` on ":" would corrupt
        # NTFS alternate data stream paths such as ``\$Extend\$UsnJrnl:$J``.
        raw_path = data.get("filename")
        if not raw_path:
            display = str(data.get("display_name") or "")
            raw_path = display.split(":", 1)[1] if ":" in display else display
        if not raw_path:
            continue
        full_path = "/" + str(raw_path).replace("\\", "/").strip("/")
        if full_path == "/":
            continue
        is_directory = str(data.get("file_entry_type", "")).lower() == "directory"
        size = data.get("file_size")
        node = {
            "evidence_source_id": evidence_source_id,
            "full_path": full_path,
            "name": full_path.rsplit("/", 1)[-1][:512],
            "is_directory": is_directory,
            "size": None if is_directory or not isinstance(size, int) else size,
            "is_deleted": data.get("is_allocated") is False,
            "parent_path": parent_of(full_path),
        }
        existing = nodes.get(full_path)
        if existing is not None and not existing["is_directory"]:
            # Real entries win over synthesised parents; otherwise keep the first.
            continue
        if full_path not in nodes and len(nodes) >= limit:
            break
        nodes[full_path] = node
        add_parents(full_path)

    return [nodes[key] for key in sorted(nodes)]


class DiskImageAdapter:
    """Parses E01/raw disk images with Plaso instead of mounting them."""

    name = "disk_image"

    def supports(self, package_dir: Path, *, platform: str, collector: str) -> bool:
        if not package_dir.is_dir():
            return False
        if collector.lower() in _EXPLICIT_COLLECTORS or platform.lower() == "disk":
            return True
        manifest = _read_package_manifest(package_dir)
        if str(manifest.get("source_type", "")).lower() in _EXPLICIT_COLLECTORS:
            return True
        return find_disk_image_in_package(package_dir, manifest) is not None

    def ingest(
        self,
        package_dir: Path,
        evidence_source_id: UUID,
        *,
        platform: str,
        collector: str,
        manifest: dict[str, Any] | None,
        on_progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        eid = str(evidence_source_id)
        result = empty_result()
        image = find_disk_image_in_package(package_dir, manifest)

        if image is None:
            result["ingest_notes"].append(
                "Disk image adapter selected but no EWF/E01 or raw disk image was found in the package"
            )
        else:
            size = image.stat().st_size
            result["ingest_notes"].append(f"Disk image: {image.name} ({size} bytes)")
            if settings.plaso_enabled and plaso_available():
                if on_progress:
                    on_progress(12, "Running Plaso/log2timeline on disk image")
                parsed_dir = package_dir / "_ff_parsed" / "disk_image"
                output, err = run_plaso(
                    image,
                    parsed_dir,
                    # A disk image can hold any OS and must be read in a single
                    # pass, so it uses the union "disk" parser profile rather
                    # than the collection platform.
                    platform="disk",
                    source_args=["--partitions", "all"],
                )
                if output:
                    events = parse_tool_outputs(parsed_dir, eid, tool="plaso")
                    result["timeline_events"].extend(events)
                    result["ingest_notes"].append(
                        f"Disk image: {len(events)} timeline events from Plaso"
                    )
                    image_nodes = filesystem_nodes_from_events(events, eid)
                    if image_nodes:
                        result["filesystem_nodes"].extend(image_nodes)
                        note = f"Disk image: {len(image_nodes)} filesystem nodes from image"
                        if len(image_nodes) >= MAX_DISK_IMAGE_FS_NODES:
                            note += f" (truncated at {MAX_DISK_IMAGE_FS_NODES})"
                        result["ingest_notes"].append(note)
                elif err:
                    result["ingest_notes"].append(f"Disk image parsing skipped: {err}")
            else:
                result["ingest_notes"].append(
                    "Plaso is not installed; disk image contents were not parsed. "
                    "Rebuild the worker with INSTALL_OPEN_FORENSICS=true to enable E01/raw parsing."
                )

        generic = GenericDirectoryAdapter().ingest(
            package_dir,
            evidence_source_id,
            platform=platform,
            collector=collector,
            manifest=manifest,
            on_progress=on_progress,
        )
        return merge_results(result, generic)
