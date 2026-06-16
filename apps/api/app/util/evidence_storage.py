"""On-disk evidence package paths under EVIDENCE_ROOT."""

import shutil
from pathlib import Path
from uuid import UUID

from app.config import settings


def case_evidence_dir(case_id: UUID) -> Path:
    return Path(settings.evidence_root) / str(case_id)


def delete_case_evidence_dir(case_id: UUID) -> None:
    """Remove extracted packages for a case (best-effort)."""
    path = case_evidence_dir(case_id)
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)


def wipe_all_evidence_dirs() -> int:
    """Remove every case directory under EVIDENCE_ROOT (orphan cleanup). Returns count removed."""
    root = Path(settings.evidence_root)
    if not root.is_dir():
        return 0
    removed = 0
    for child in root.iterdir():
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
            removed += 1
    return removed
