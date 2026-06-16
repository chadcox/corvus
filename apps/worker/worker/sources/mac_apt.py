from pathlib import Path
from typing import Any
from uuid import UUID

from worker.config import settings
from worker.parsers.external_events import parse_tool_outputs
from worker.sources.base import ProgressCallback
from worker.sources.external_tools import mac_apt_available, run_mac_apt
from worker.sources.generic import GenericDirectoryAdapter
from worker.sources.plaso import PlasoAdapter
from worker.sources.result_merge import empty_result, merge_results


class MacAptAdapter:
    """macOS-specialized adapter backed by mac_apt when available."""

    name = "mac_apt"

    def supports(self, package_dir: Path, *, platform: str, collector: str) -> bool:
        return package_dir.is_dir() and (platform == "macos" or collector.lower() == "mac_apt")

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
        parsed_dir = package_dir / "_ff_parsed" / "mac_apt"
        used_plaso = False

        if settings.mac_apt_enabled and mac_apt_available():
            if on_progress:
                on_progress(12, "Running mac_apt")
            output_dir, err = run_mac_apt(package_dir, parsed_dir)
            if output_dir:
                events = parse_tool_outputs(output_dir, eid, tool="mac_apt")
                result["timeline_events"].extend(events)
                result["ingest_notes"].append(f"mac_apt: {len(events)} timeline events")
            elif err:
                result["ingest_notes"].append(f"mac_apt skipped: {err}")
        else:
            existing = parse_tool_outputs(package_dir, eid, tool="mac_apt")
            if existing:
                result["timeline_events"].extend(existing)
                result["ingest_notes"].append(f"mac_apt output import: {len(existing)} events")
            else:
                result["ingest_notes"].append("mac_apt not installed; using generic parser fallback")

        plaso = PlasoAdapter()
        if not result["timeline_events"] and plaso.supports(
            package_dir,
            platform=platform,
            collector=collector,
        ):
            used_plaso = True
            result = merge_results(
                result,
                plaso.ingest(
                    package_dir,
                    evidence_source_id,
                    platform=platform,
                    collector=collector,
                    manifest=manifest,
                    on_progress=on_progress,
                ),
            )

        if used_plaso:
            return result

        generic = GenericDirectoryAdapter().ingest(
            package_dir,
            evidence_source_id,
            platform=platform,
            collector=collector,
            manifest=manifest,
            on_progress=on_progress,
        )
        return merge_results(result, generic)
