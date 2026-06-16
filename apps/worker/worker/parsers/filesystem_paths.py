"""Build filesystem nodes from file paths referenced in artifact CSV data."""

from pathlib import PureWindowsPath
from typing import Any


def _normalize_path(raw: str) -> str | None:
    raw = raw.strip()
    if not raw or raw in ("-", "N/A"):
        return None
    # Skip non-path values
    if not (":" in raw or raw.startswith("\\\\") or raw.startswith("/")):
        return None
    path = str(PureWindowsPath(raw.replace("/", "\\")))
    if path.endswith("\\"):
        path = path.rstrip("\\")
    return "/" + path.replace("\\", "/").lstrip("/")


def build_filesystem_from_paths(
    events: list[dict[str, Any]],
    evidence_source_id: str,
) -> list[dict[str, Any]]:
    """Create filesystem nodes for file paths seen in timeline event data."""
    seen: set[str] = set()
    nodes: list[dict[str, Any]] = []

    path_fields = ("FullPath", "TargetFilename", "FileName", "Path", "Image")

    for event in events:
        data = event.get("data") or {}
        if not isinstance(data, dict):
            continue
        for field in path_fields:
            raw = data.get(field)
            if not raw:
                continue
            full = _normalize_path(str(raw))
            if not full or full in seen:
                continue
            seen.add(full)

            parts = full.strip("/").split("/")
            name = parts[-1] if parts else full
            parent = "/" + "/".join(parts[:-1]) if len(parts) > 1 else None

            nodes.append(
                {
                    "evidence_source_id": evidence_source_id,
                    "full_path": full,
                    "name": name[:512],
                    "is_directory": False,
                    "size": None,
                    "is_deleted": False,
                    "parent_path": parent,
                }
            )

    return nodes
