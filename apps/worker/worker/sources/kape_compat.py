from pathlib import Path
from typing import Any
from uuid import UUID

from worker.kape.detector import detect_kape_layout
from worker.kape.ingest import ingest_package
from worker.sources.base import ProgressCallback


class KapeCompatAdapter:
    """Compatibility adapter for KAPE-shaped Windows endpoint packages."""

    name = "kape_compat"

    def supports(self, package_dir: Path, *, platform: str, collector: str) -> bool:
        if collector.lower() == "kape":
            return True
        layout = detect_kape_layout(package_dir)
        return bool(
            layout.raw_collection
            or layout.category_dirs
            or layout.csv_files
            or layout.evtx_files
            or layout.mft_files
            or layout.registry_hives
            or layout.prefetch_files
            or layout.amcache_files
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
        return ingest_package(package_dir, evidence_source_id, on_progress=on_progress)
