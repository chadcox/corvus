from pathlib import Path
from typing import Any
from uuid import UUID

from worker.config import settings
from worker.parsers.external_events import parse_tool_outputs
from worker.sources.base import ProgressCallback
from worker.sources.external_tools import plaso_available, run_plaso
from worker.sources.generic import GenericDirectoryAdapter
from worker.sources.result_merge import empty_result, merge_results


class PlasoAdapter:
    """Explicit Plaso adapter used when collector is set to plaso."""

    name = "plaso"

    def supports(self, package_dir: Path, *, platform: str, collector: str) -> bool:
        if collector.lower() != "plaso":
            return False
        if not settings.plaso_enabled or not plaso_available():
            return False
        return package_dir.is_dir()

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
        parsed_dir = package_dir / "_ff_parsed" / "plaso"

        if settings.plaso_enabled and plaso_available():
            if on_progress:
                on_progress(12, "Running Plaso/log2timeline")
            output, err = run_plaso(package_dir, parsed_dir, platform=platform)
            if output:
                events = parse_tool_outputs(parsed_dir, eid, tool="plaso")
                result["timeline_events"].extend(events)
                result["ingest_notes"].append(f"Plaso: {len(events)} timeline events")
            elif err:
                result["ingest_notes"].append(f"Plaso skipped: {err}")
        else:
            result["ingest_notes"].append("Plaso not installed; using generic parser fallback")

        generic = GenericDirectoryAdapter().ingest(
            package_dir,
            evidence_source_id,
            platform=platform,
            collector=collector,
            manifest=manifest,
            on_progress=on_progress,
        )
        return merge_results(result, generic)
