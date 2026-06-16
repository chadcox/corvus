from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID


ProgressCallback = Callable[[int, str], None]


class SourceAdapter(Protocol):
    name: str

    def supports(self, package_dir: Path, *, platform: str, collector: str) -> bool:
        """Return true when this adapter should parse the evidence package."""
        ...

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
        """Parse an evidence package into timeline, filesystem, entity, and note records."""
        ...
