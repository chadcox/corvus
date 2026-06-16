from pathlib import Path
from typing import Any
from uuid import UUID

from worker.kape.ingest import ingest_package
from worker.parsers.filesystem import build_filesystem_nodes
from worker.sources.base import ProgressCallback


class GenericDirectoryAdapter:
    """Default endpoint package adapter.

    The current parser stack already handles generic CSVs, raw Windows artifacts,
    filesystem trees, and Chromium profiles. This adapter gives that behavior a
    collector-neutral home while macOS/Linux-specific adapters are added.
    """

    name = "generic_directory"

    def supports(self, package_dir: Path, *, platform: str, collector: str) -> bool:
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
        result = ingest_package(package_dir, evidence_source_id, on_progress=on_progress)
        if not result.get("filesystem_nodes") and platform in ("linux", "macos", "unknown"):
            filesystem = build_filesystem_nodes(package_dir, str(evidence_source_id))
            if filesystem:
                result["filesystem_nodes"] = filesystem
                result.setdefault("ingest_notes", []).append(
                    f"Filesystem: {len(filesystem)} nodes from package tree"
                )
        return result
