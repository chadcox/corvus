"""Delete cases (projects) and on-disk evidence packages."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.models import Case, EvidenceSource
from app.services.opensearch_service import delete_source_docs
from pathlib import Path

from app.config import settings
from app.util.evidence_storage import delete_case_evidence_dir, wipe_all_evidence_dirs
from ff_core.schemas import CasePurgeResult


def _case_query(db: Session, *, case_ids: list[UUID] | None, name_prefix: str | None):
    query = db.query(Case)
    if case_ids is not None:
        query = query.filter(Case.id.in_(case_ids))
    if name_prefix is not None:
        query = query.filter(Case.name.startswith(name_prefix))
    return query.order_by(Case.created_at)


def purge_cases(
    db: Session,
    *,
    case_ids: list[UUID] | None = None,
    name_prefix: str | None = None,
    all_cases: bool = False,
    dry_run: bool = False,
    wipe_orphan_evidence_dirs: bool = True,
) -> CasePurgeResult:
    """
    Remove cases from the database (CASCADE clears sources, jobs, timeline, etc.)
    and delete matching directories under EVIDENCE_ROOT.
    """
    if all_cases:
        query = db.query(Case).order_by(Case.created_at)
    elif case_ids is not None:
        query = _case_query(db, case_ids=case_ids, name_prefix=None)
    elif name_prefix is not None:
        query = _case_query(db, case_ids=None, name_prefix=name_prefix)
    else:
        raise ValueError("Specify all_cases, case_ids, or name_prefix")

    cases = query.all()
    ids = [c.id for c in cases]

    if dry_run:
        return CasePurgeResult(
            deleted_cases=0,
            case_ids=ids,
            evidence_dirs_removed=0,
            dry_run=True,
        )

    source_ids = [
        row[0]
        for row in db.query(EvidenceSource.id).filter(EvidenceSource.case_id.in_(ids)).all()
    ]
    for source_id in source_ids:
        try:
            delete_source_docs(source_id)
        except Exception:
            pass

    for case in cases:
        db.delete(case)
    db.commit()

    dirs_removed = 0
    orphan_removed = 0

    if all_cases:
        dirs_removed = wipe_all_evidence_dirs()
    else:
        for case_id in ids:
            if _dir_exists(case_id):
                delete_case_evidence_dir(case_id)
                dirs_removed += 1
        if wipe_orphan_evidence_dirs:
            orphan_removed = _cleanup_orphan_evidence_dirs(db)

    return CasePurgeResult(
        deleted_cases=len(ids),
        case_ids=ids,
        evidence_dirs_removed=dirs_removed,
        orphan_evidence_dirs_removed=orphan_removed,
        dry_run=False,
    )


def _dir_exists(case_id: UUID) -> bool:
    from app.util.evidence_storage import case_evidence_dir

    return case_evidence_dir(case_id).is_dir()


def _cleanup_orphan_evidence_dirs(db: Session) -> int:
    """Remove evidence directories with no matching case row."""
    import shutil

    root = Path(settings.evidence_root)
    if not root.is_dir():
        return 0
    known = {str(row[0]) for row in db.query(Case.id).all()}
    removed = 0
    for child in root.iterdir():
        if child.is_dir() and child.name not in known:
            shutil.rmtree(child, ignore_errors=True)
            removed += 1
    return removed
