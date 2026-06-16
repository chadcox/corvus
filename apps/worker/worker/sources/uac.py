from pathlib import Path
from typing import Any
from uuid import UUID

from worker.parsers.external_events import parse_tool_outputs
from worker.sources.base import ProgressCallback
from worker.sources.generic import GenericDirectoryAdapter
from worker.sources.plaso import PlasoAdapter
from worker.sources.result_merge import empty_result, merge_results


def looks_like_uac_package(package_dir: Path) -> bool:
    names = {p.name.lower() for p in package_dir.iterdir()} if package_dir.is_dir() else set()
    if {"uac.log", "uac.log.gz", "uac.conf", "uac.yml", "uac.yaml"} & names:
        return True
    return any(p.name.lower().startswith("uac-") for p in package_dir.glob("*"))


def _find_uac_root(package_dir: Path, max_depth: int = 4) -> Path | None:
    if not package_dir.is_dir():
        return None
    if looks_like_uac_package(package_dir):
        return package_dir
    base_depth = len(package_dir.parts)
    for path in package_dir.rglob("*"):
        if not path.is_dir():
            continue
        if path.name in (".git", "__MACOSX"):
            continue
        if len(path.parts) - base_depth > max_depth:
            continue
        if looks_like_uac_package(path):
            return path
    return None


def _uac_root(package_dir: Path) -> Path:
    return _find_uac_root(package_dir) or package_dir


class UacImportAdapter:
    """Import Unix-like Artifacts Collector packages and parse their contents."""

    name = "uac_import"

    def supports(self, package_dir: Path, *, platform: str, collector: str) -> bool:
        return package_dir.is_dir() and (
            collector.lower() == "uac"
            or _uac_root(package_dir) != package_dir
            or looks_like_uac_package(package_dir)
        )

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
        package_dir = _uac_root(package_dir)
        effective_platform = platform
        if effective_platform == "windows" and looks_like_uac_package(package_dir):
            effective_platform = "linux"
        result = empty_result()
        if on_progress:
            on_progress(12, "Importing UAC package outputs")
        events = parse_tool_outputs(package_dir, eid, tool="uac")
        if events:
            result["timeline_events"].extend(events)
            result["ingest_notes"].append(f"UAC structured output: {len(events)} events")

        plaso = PlasoAdapter()
        if plaso.supports(package_dir, platform=effective_platform, collector=collector):
            return merge_results(
                result,
                plaso.ingest(
                    package_dir,
                    evidence_source_id,
                    platform=effective_platform,
                    collector=collector,
                    manifest=manifest,
                    on_progress=on_progress,
                ),
            )

        return merge_results(
            result,
            GenericDirectoryAdapter().ingest(
                package_dir,
                evidence_source_id,
                platform=effective_platform,
                collector=collector,
                manifest=manifest,
                on_progress=on_progress,
            ),
        )
