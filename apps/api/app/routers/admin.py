"""Administrator and development endpoints — gated by ENABLE_ADMIN_API."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func
from sqlalchemy.orm import Session, aliased

from app.config import settings
from app.database import get_db
from app.models import Case, EvidenceSource, IngestJob
from app.services.opensearch_service import reindex_source
from app.services.admin_ops import (
    _database_host,
    build_admin_overview,
    collect_routes,
)
from app.services.case_purge import purge_cases
from app.util.evidence_storage import wipe_all_evidence_dirs
from corvus_core.schemas import (
    AdminConfigRead,
    AdminEvidenceSourceSummary,
    AdminJobSummary,
    AdminOverviewRead,
    AdminPurgeResult,
    AdminRouteEntry,
    CaseBulkDeleteRequest,
    CasePurgeResult,
)

router = APIRouter(prefix="/admin", tags=["admin"])


def _require_admin() -> None:
    if not settings.enable_admin_api:
        raise HTTPException(status_code=404, detail="Admin API disabled")


def _require_confirm(confirm: bool, *, action: str) -> None:
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail=f"Set confirm=true to {action}",
        )


@router.get("/overview", response_model=AdminOverviewRead)
def admin_overview(db: Session = Depends(get_db)) -> AdminOverviewRead:
    """
    Single-pane system snapshot: readiness, table counts, job/source status histograms,
    evidence disk usage, and Sigma rule sync state.
    """
    _require_admin()
    return build_admin_overview(db)


@router.get("/config", response_model=AdminConfigRead)
def admin_config() -> AdminConfigRead:
    """Non-secret configuration (paths, feature flags, DB host only)."""
    _require_admin()
    return AdminConfigRead(
        api_version=settings.api_version,
        evidence_root=settings.evidence_root,
        samples_root=settings.samples_root,
        sigma_rules_root=settings.sigma_rules_root,
        sigma_ref=settings.sigma_ref,
        sigma_refresh_interval_hours=settings.sigma_refresh_interval_hours,
        cors_origins=settings.cors_origins,
        database_url_host=_database_host(),
    )


@router.get("/routes", response_model=list[AdminRouteEntry])
def admin_routes(request: Request) -> list[AdminRouteEntry]:
    """Registered HTTP routes — useful when OpenAPI UI is unavailable."""
    _require_admin()
    return [AdminRouteEntry.model_validate(entry) for entry in collect_routes(request.app)]


@router.post("/search/reindex")
def reindex_search(
    case_id: UUID | None = Query(None),
    source_id: UUID | None = Query(None),
    db: Session = Depends(get_db),
) -> dict:
    """Rebuild OpenSearch documents from canonical PostgreSQL/Timescale rows."""
    _require_admin()
    query = db.query(EvidenceSource)
    if case_id:
        query = query.filter(EvidenceSource.case_id == case_id)
    if source_id:
        query = query.filter(EvidenceSource.id == source_id)
    sources = query.all()
    totals = {"sources": len(sources), "timeline": 0, "filesystem": 0, "entities": 0}
    for source in sources:
        counts = reindex_source(db, case_id=source.case_id, source_id=source.id)
        totals["timeline"] += counts["timeline"]
        totals["filesystem"] += counts["filesystem"]
        totals["entities"] += counts["entities"]
    return totals


@router.get("/jobs", response_model=list[AdminJobSummary])
def list_jobs(
    status: str | None = Query(None, description="Filter by job status (pending, running, completed, failed)"),
    error_code: str | None = Query(None, description="Filter failed jobs by structured error code"),
    error_stage: str | None = Query(None, description="Filter failed jobs by structured error stage"),
    case_id: UUID | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[AdminJobSummary]:
    """Recent ingest jobs across all cases (newest first)."""
    _require_admin()

    query = (
        db.query(IngestJob, EvidenceSource, Case)
        .join(EvidenceSource, IngestJob.evidence_source_id == EvidenceSource.id)
        .join(Case, EvidenceSource.case_id == Case.id)
        .order_by(IngestJob.created_at.desc())
    )
    if status:
        query = query.filter(IngestJob.status == status)
    if error_code:
        query = query.filter(IngestJob.error_code == error_code)
    if error_stage:
        query = query.filter(IngestJob.error_stage == error_stage)
    if case_id:
        query = query.filter(Case.id == case_id)

    rows = query.limit(limit).all()
    return [
        AdminJobSummary(
            id=job.id,
            evidence_source_id=source.id,
            case_id=case.id,
            case_name=case.name,
            hostname=source.hostname,
            status=job.status,
            progress=job.progress,
            message=job.message,
            error_code=job.error_code,
            error_stage=job.error_stage,
            created_at=job.created_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
        )
        for job, source, case in rows
    ]


@router.get("/evidence-sources", response_model=list[AdminEvidenceSourceSummary])
def list_evidence_sources(
    status: str | None = Query(None),
    case_id: UUID | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[AdminEvidenceSourceSummary]:
    """Evidence sources with latest ingest job status."""
    _require_admin()

    latest_job = aliased(IngestJob)
    subq = (
        db.query(
            IngestJob.evidence_source_id.label("source_id"),
            func.max(IngestJob.created_at).label("max_created"),
        )
        .group_by(IngestJob.evidence_source_id)
        .subquery()
    )

    query = (
        db.query(EvidenceSource, Case, latest_job)
        .join(Case, EvidenceSource.case_id == Case.id)
        .outerjoin(
            subq,
            subq.c.source_id == EvidenceSource.id,
        )
        .outerjoin(
            latest_job,
            (latest_job.evidence_source_id == EvidenceSource.id)
            & (latest_job.created_at == subq.c.max_created),
        )
        .order_by(EvidenceSource.created_at.desc())
    )
    if status:
        query = query.filter(EvidenceSource.status == status)
    if case_id:
        query = query.filter(Case.id == case_id)

    rows = query.limit(limit).all()
    return [
        AdminEvidenceSourceSummary(
            id=source.id,
            case_id=case.id,
            case_name=case.name,
            hostname=source.hostname,
            status=source.status,
            collector=source.collector,
            platform=source.platform,
            source_type=source.source_type,
            created_at=source.created_at,
            latest_job_id=job.id if job else None,
            latest_job_status=job.status if job else None,
        )
        for source, case, job in rows
    ]


# --- Case / project purge (database + evidence disk) ---


@router.get("/cases/purge-preview", response_model=CasePurgeResult)
def preview_purge_all_cases(db: Session = Depends(get_db)) -> CasePurgeResult:
    """Count cases that would be removed by DELETE /admin/cases?confirm=true."""
    _require_admin()
    return purge_cases(db, all_cases=True, dry_run=True)


@router.delete("/cases", response_model=CasePurgeResult)
def delete_all_cases(
    confirm: bool = Query(False, description="Must be true to delete every case"),
    dry_run: bool = Query(False, description="List case IDs only; no deletion"),
    db: Session = Depends(get_db),
) -> CasePurgeResult:
    """
    Delete **all** cases (projects) and investigation data.

    Cascades to evidence sources, jobs, timeline, entities, filesystem, and Sigma rows.
    Removes all directories under ``EVIDENCE_ROOT``.
    """
    _require_admin()
    if dry_run:
        return purge_cases(db, all_cases=True, dry_run=True)
    _require_confirm(confirm, action="delete all cases")
    return purge_cases(db, all_cases=True, dry_run=False)


@router.post("/cases/bulk-delete", response_model=CasePurgeResult)
def bulk_delete_cases(
    payload: CaseBulkDeleteRequest,
    db: Session = Depends(get_db),
) -> CasePurgeResult:
    """Delete specific cases by ID."""
    _require_admin()
    _require_confirm(payload.confirm, action="delete the requested cases")

    found = db.query(Case.id).filter(Case.id.in_(payload.case_ids)).all()
    found_ids = {row[0] for row in found}
    missing = [cid for cid in payload.case_ids if cid not in found_ids]
    if missing:
        raise HTTPException(
            status_code=404,
            detail=f"Case(s) not found: {missing[:5]}{'...' if len(missing) > 5 else ''}",
        )

    return purge_cases(db, case_ids=list(payload.case_ids), dry_run=False)


@router.delete("/cases/validation", response_model=AdminPurgeResult)
def purge_validation_cases(
    name_prefix: str = Query(
        "Validation",
        min_length=1,
        max_length=64,
        description="Delete cases whose name starts with this prefix",
    ),
    confirm: bool = Query(False, description="Must be true to delete"),
    dry_run: bool = Query(False, description="List matches without deleting"),
    db: Session = Depends(get_db),
) -> AdminPurgeResult:
    """Remove automated validation cases (default: name starts with 'Validation')."""
    _require_admin()

    if dry_run:
        result = purge_cases(db, name_prefix=name_prefix, dry_run=True)
        return AdminPurgeResult(deleted_cases=0, case_ids=result.case_ids)

    _require_confirm(confirm, action="delete validation cases")
    result = purge_cases(db, name_prefix=name_prefix, dry_run=False)
    return AdminPurgeResult(deleted_cases=result.deleted_cases, case_ids=result.case_ids)


@router.post("/evidence/wipe", response_model=dict)
def wipe_evidence_disk(
    confirm: bool = Query(False, description="Must be true to wipe disk"),
    db: Session = Depends(get_db),
) -> dict:
    """
    Remove all package directories under ``EVIDENCE_ROOT`` without deleting DB rows.

    Use after manual DB edits or to reclaim disk when cases were removed outside the API.
  Does not remove case rows — use ``DELETE /admin/cases`` for a full reset.
    """
    _require_admin()
    _require_confirm(confirm, action="wipe all evidence directories on disk")
    removed = wipe_all_evidence_dirs()
    remaining_cases = db.query(func.count(Case.id)).scalar() or 0
    return {
        "evidence_dirs_removed": removed,
        "cases_remaining_in_db": remaining_cases,
    }
