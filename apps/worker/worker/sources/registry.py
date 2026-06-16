from pathlib import Path
from typing import Any
from uuid import UUID

from worker.sources.base import ProgressCallback, SourceAdapter
from worker.sources.generic import GenericDirectoryAdapter
from worker.sources.kape_compat import KapeCompatAdapter
from worker.sources.mac_apt import MacAptAdapter
from worker.sources.plaso import PlasoAdapter
from worker.sources.uac import UacImportAdapter
from worker.sources.velociraptor import VelociraptorImportAdapter
from worker.sources.volatility3 import Volatility3Adapter


_ADAPTERS: tuple[SourceAdapter, ...] = (
    UacImportAdapter(),
    KapeCompatAdapter(),
    Volatility3Adapter(),
    VelociraptorImportAdapter(),
    MacAptAdapter(),
    PlasoAdapter(),
    GenericDirectoryAdapter(),
)


def select_source_adapter(package_dir: Path, *, platform: str, collector: str) -> SourceAdapter:
    for adapter in _ADAPTERS:
        if adapter.supports(package_dir, platform=platform, collector=collector):
            return adapter
    raise ValueError(f"No source adapter found for platform={platform!r}, collector={collector!r}")


def ingest_source_package(
    package_dir: Path,
    evidence_source_id: UUID,
    *,
    platform: str,
    collector: str,
    manifest: dict[str, Any] | None = None,
    on_progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    adapter = select_source_adapter(package_dir, platform=platform, collector=collector)
    if on_progress:
        on_progress(8, f"Selected {adapter.name} source adapter")
    result = adapter.ingest(
        package_dir,
        evidence_source_id,
        platform=platform,
        collector=collector,
        manifest=manifest,
        on_progress=on_progress,
    )
    result.setdefault("ingest_notes", []).append(f"Source adapter: {adapter.name}")
    return result
