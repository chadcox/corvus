from pathlib import Path
from typing import Any
from uuid import UUID

from worker.config import settings
from worker.parsers.external_events import parse_tool_outputs
from worker.sources.base import ProgressCallback
from worker.sources.external_tools import (
    run_volatility3,
    run_volatility3_banners,
    volatility3_available,
)
from worker.sources.generic import GenericDirectoryAdapter
from worker.sources.result_merge import empty_result, merge_results

_MEMORY_EXTS = {
    ".raw",
    ".mem",
    ".vmem",
    ".bin",
    ".dmp",
    ".img",
}


def _find_memory_images(package_dir: Path) -> list[Path]:
    images: list[Path] = []
    for path in package_dir.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() in _MEMORY_EXTS:
            images.append(path)
            continue
        name = path.name.lower()
        if name.endswith((".memdump", ".memory", ".hiberfil.sys")):
            images.append(path)
    return sorted(images)


class Volatility3Adapter:
    """Windows memory capture adapter using Volatility3."""

    name = "volatility3"

    def supports(self, package_dir: Path, *, platform: str, collector: str) -> bool:
        if collector.lower() in {"volatility3", "volatility"}:
            return True
        if platform not in {"windows", "memory"}:
            return False
        return bool(_find_memory_images(package_dir))

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
        images = _find_memory_images(package_dir)
        parsed_root = package_dir / "_ff_parsed" / "volatility3"

        if not images:
            result["ingest_notes"].append("Volatility3 skipped: no Windows memory image found")
        elif not settings.volatility3_enabled:
            result["ingest_notes"].append("Volatility3 disabled; using generic parser fallback")
        elif not volatility3_available():
            result["ingest_notes"].append("Volatility3 not installed; using generic parser fallback")
        else:
            plugins = [p.strip() for p in settings.volatility3_plugins.split(",") if p.strip()]
            max_images = min(len(images), 2)
            for index, image in enumerate(images[:max_images], start=1):
                if on_progress:
                    on_progress(12, f"Running Volatility3 banners ({index}/{max_images}): {image.name}")
                banners_out, banners_err = run_volatility3_banners(image)
                if banners_err:
                    result["ingest_notes"].append(
                        f"Volatility3 notice ({image.name}): banners plugin failed: {banners_err}"
                    )
                    result["ingest_notes"].append(
                        f"Volatility3: only Windows memory is supported currently ({image.name})"
                    )
                    continue
                if not _is_windows_memory_from_banners(banners_out or ""):
                    result["ingest_notes"].append(
                        f"Volatility3: only Windows memory is supported currently ({image.name})"
                    )
                    continue

                if on_progress:
                    on_progress(14, f"Running Volatility3 Windows plugins ({index}/{max_images}): {image.name}")
                image_out = parsed_root / image.stem
                output_dir, err = run_volatility3(image, image_out, plugins=plugins)
                if output_dir:
                    events = parse_tool_outputs(output_dir, eid, tool="volatility3")
                    result["timeline_events"].extend(events)
                    result["ingest_notes"].append(
                        f"Volatility3: {len(events)} timeline events from {image.name}"
                    )
                if err:
                    result["ingest_notes"].append(f"Volatility3 notice ({image.name}): {err}")
            if len(images) > max_images:
                result["ingest_notes"].append(
                    f"Volatility3 limited to first {max_images} memory images per package"
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


def _is_windows_memory_from_banners(output: str) -> bool:
    lower = output.lower()
    return "ntkrnlmp.pdb|" in lower or "ntoskrnl.pdb|" in lower
