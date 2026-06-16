from pathlib import Path
from typing import Any
from uuid import UUID

from worker.parsers.external_events import parse_tool_outputs
from worker.sources.base import ProgressCallback
from worker.sources.generic import GenericDirectoryAdapter
from worker.sources.result_merge import empty_result, merge_results


def looks_like_velociraptor_package(package_dir: Path) -> bool:
    if not package_dir.is_dir():
        return False
    names = {p.name.lower() for p in package_dir.iterdir()}
    if {"uploads", "results", "logs"} & names:
        return any("velociraptor" in p.as_posix().lower() for p in package_dir.rglob("*"))
    return any(
        p.is_file() and p.suffix.lower() in (".json", ".jsonl", ".csv")
        and ("velociraptor" in p.as_posix().lower() or "artifact" in p.name.lower())
        for p in package_dir.rglob("*")
    )


class VelociraptorImportAdapter:
    """Import Velociraptor collection exports without bundling Velociraptor."""

    name = "velociraptor_import"

    def supports(self, package_dir: Path, *, platform: str, collector: str) -> bool:
        return package_dir.is_dir() and (
            collector.lower() in ("velociraptor", "velociraptor_import")
            or looks_like_velociraptor_package(package_dir)
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
        result = empty_result()
        if on_progress:
            on_progress(12, "Importing Velociraptor collection outputs")
        events = parse_tool_outputs(package_dir, eid, tool="velociraptor")
        if events:
            result["timeline_events"].extend(events)
            result["ingest_notes"].append(f"Velociraptor structured output: {len(events)} events")
        else:
            result["ingest_notes"].append("No Velociraptor structured timeline rows found")

        return merge_results(
            result,
            GenericDirectoryAdapter().ingest(
                package_dir,
                evidence_source_id,
                platform=platform,
                collector=collector,
                manifest=manifest,
                on_progress=on_progress,
            ),
        )
