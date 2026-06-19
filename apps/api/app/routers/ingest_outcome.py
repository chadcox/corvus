"""Ingest job outcome — structured success/failure for automation and CI."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from sqlalchemy import distinct, func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Entity, EvidenceSource, FilesystemNode, IngestJob, SigmaDetection, TimelineEvent
from app.services.ingest_outcome import build_ingest_outcome
from corvus_core.schemas import IngestOutcomeRead, SourceStats

router = APIRouter(tags=["ingest-outcome"])


def _load_stats(db: Session, source_id: UUID) -> SourceStats | None:
    timeline_count = (
        db.query(func.count(TimelineEvent.id))
        .filter(TimelineEvent.evidence_source_id == source_id)
        .scalar()
        or 0
    )
    filesystem_count = (
        db.query(func.count(FilesystemNode.id))
        .filter(FilesystemNode.evidence_source_id == source_id)
        .scalar()
        or 0
    )
    entity_count = (
        db.query(func.count(Entity.id))
        .filter(Entity.evidence_source_id == source_id)
        .scalar()
        or 0
    )
    sigma_detection_count = (
        db.query(func.count(SigmaDetection.id))
        .filter(SigmaDetection.evidence_source_id == source_id)
        .scalar()
        or 0
    )
    event_types = [
        row[0]
        for row in (
            db.query(distinct(TimelineEvent.event_type))
            .filter(TimelineEvent.evidence_source_id == source_id)
            .order_by(TimelineEvent.event_type)
            .limit(50)
            .all()
        )
        if row[0]
    ]
    return SourceStats(
        timeline_count=timeline_count,
        filesystem_count=filesystem_count,
        entity_count=entity_count,
        sigma_detection_count=sigma_detection_count,
        event_types=event_types,
    )


@router.get("/jobs/{job_id}/outcome", response_model=IngestOutcomeRead)
def get_job_outcome(
    job_id: UUID,
    min_timeline_events: int = Query(1, ge=0),
    min_filesystem_nodes: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> IngestOutcomeRead:
    job = db.get(IngestJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    source = db.get(EvidenceSource, job.evidence_source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Evidence source for job not found")

    stats: SourceStats | None = None
    if job.status in ("completed", "failed"):
        stats = _load_stats(db, source.id)

    return build_ingest_outcome(
        job_id=job.id,
        evidence_source_id=job.evidence_source_id,
        case_id=source.case_id,
        job_status=job.status,
        job_progress=job.progress,
        job_message=job.message,
        source_status=source.status if source else None,
        stats=stats,
        min_timeline_events=min_timeline_events,
        min_filesystem_nodes=min_filesystem_nodes,
    )


@router.get(
    "/cases/{case_id}/sources/{source_id}/outcome",
    response_model=IngestOutcomeRead,
)
def get_source_latest_outcome(
    case_id: UUID,
    source_id: UUID,
    min_timeline_events: int = Query(1, ge=0),
    min_filesystem_nodes: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> IngestOutcomeRead:
    source = (
        db.query(EvidenceSource)
        .filter(EvidenceSource.id == source_id, EvidenceSource.case_id == case_id)
        .first()
    )
    if not source:
        raise HTTPException(status_code=404, detail="Evidence source not found")

    job = (
        db.query(IngestJob)
        .filter(IngestJob.evidence_source_id == source_id)
        .order_by(IngestJob.created_at.desc())
        .first()
    )
    if not job:
        raise HTTPException(status_code=404, detail="No ingest job for this source")

    stats: SourceStats | None = None
    if job.status in ("completed", "failed"):
        stats = _load_stats(db, source_id)

    return build_ingest_outcome(
        job_id=job.id,
        evidence_source_id=source_id,
        case_id=case_id,
        job_status=job.status,
        job_progress=job.progress,
        job_message=job.message,
        source_status=source.status,
        stats=stats,
        min_timeline_events=min_timeline_events,
        min_filesystem_nodes=min_filesystem_nodes,
    )
