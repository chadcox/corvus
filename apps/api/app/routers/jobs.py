from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.celery_client import celery_app
from app.database import get_db
from app.models import EvidenceSource, IngestJob
from ff_core.constants import JobStatus
from ff_core.schemas import IngestJobRead

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=IngestJobRead)
def get_job(job_id: UUID, db: Session = Depends(get_db)) -> IngestJob:
    job = db.get(IngestJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/{job_id}/cancel", response_model=IngestJobRead)
def cancel_job(job_id: UUID, db: Session = Depends(get_db)) -> IngestJob:
    job = db.get(IngestJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status in (JobStatus.COMPLETED, JobStatus.FAILED):
        return job

    source = db.get(EvidenceSource, job.evidence_source_id)
    job.status = JobStatus.FAILED
    job.finished_at = job.finished_at or datetime.now(timezone.utc)
    job.message = "Cancelled by user"
    job.error_code = "cancelled"
    job.error_stage = "cancel"
    if source and source.status in (JobStatus.PENDING, JobStatus.RUNNING):
        source.status = JobStatus.FAILED
    db.commit()
    db.refresh(job)

    try:
        celery_app.control.revoke(str(job.id), terminate=True, signal="SIGTERM")
    except Exception:
        # Keep cancellation state even if revoke call fails.
        pass

    return job
