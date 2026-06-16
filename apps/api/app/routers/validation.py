"""Programmatic ingest validation — upload sample packages and inspect outcomes."""

from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Case
from app.routers.evidence import _create_ingest_source
from ff_core.schemas import IngestSampleStartRead

router = APIRouter(prefix="/validation", tags=["validation"])

ALLOWED_SAMPLES = frozenset({"c", "kape-minimal"})
ALLOWED_INGEST_MODES = frozenset({"fast", "full"})


@router.post("/ingest-sample", response_model=IngestSampleStartRead, status_code=202)
async def ingest_sample_package(
    sample: str = Query("c", description="Sample name under samples/ (c, kape-minimal)"),
    case_name: str | None = Query(None, description="Case name; auto-generated if omitted"),
    ingest_mode: str = Query("fast", description="Validation ingest mode: fast or full"),
    min_filesystem_nodes: int = Query(
        0,
        ge=0,
        description="Pass outcome.filesystem_persisted when count >= this (use 1 for c.zip)",
    ),
    db: Session = Depends(get_db),
) -> IngestSampleStartRead:
    """
    Upload a bundled sample ZIP and queue ingest — for CI/automation (no UI required).

  Poll ``GET /api/v1/jobs/{job_id}/outcome`` until ``success`` is true or ``job_status`` is failed.
    """
    if not settings.enable_validation_api:
        raise HTTPException(status_code=404, detail="Validation API disabled")

    name = sample.strip()
    if name not in ALLOWED_SAMPLES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown sample {name!r}; allowed: {sorted(ALLOWED_SAMPLES)}",
        )
    if ingest_mode not in ALLOWED_INGEST_MODES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown ingest_mode {ingest_mode!r}; allowed: {sorted(ALLOWED_INGEST_MODES)}",
        )

    zip_path = Path(settings.samples_root) / f"{name}.zip"
    if not zip_path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"Sample not found: {zip_path} (mount samples/ into the API container)",
        )

    case = Case(
        name=case_name or f"Validation {name} {uuid4().hex[:8]}",
        description=f"Automated ingest validation ({name}.zip)",
    )
    db.add(case)
    db.commit()
    db.refresh(case)

    with zip_path.open("rb") as handle:
        upload = UploadFile(filename=zip_path.name, file=handle)
        job = await _create_ingest_source(
            case_id=case.id,
            file=upload,
            hostname=None,
            platform=None,
            db=db,
            manifest_overrides={"ff_validation_mode": ingest_mode},
        )

    base = f"/api/v1/cases/{case.id}/sources/{job.evidence_source_id}"
    fs_q = f"&min_filesystem_nodes={min_filesystem_nodes}" if min_filesystem_nodes else ""
    outcome_path = f"/api/v1/jobs/{job.id}/outcome?min_timeline_events=1{fs_q}"

    return IngestSampleStartRead(
        case_id=case.id,
        job_id=job.id,
        evidence_source_id=job.evidence_source_id,
        sample=name,
        outcome_path=outcome_path,
        job_path=f"/api/v1/jobs/{job.id}",
        stats_path=f"{base}/stats",
    )


@router.post("/ingest-upload", response_model=IngestSampleStartRead, status_code=202)
async def ingest_validation_upload(
    file: UploadFile = File(...),
    case_name: str | None = Query(None),
    ingest_mode: str = Query("fast"),
    db: Session = Depends(get_db),
) -> IngestSampleStartRead:
    """Upload any ZIP and return poll URLs (same outcome flow as ingest-sample)."""
    if not settings.enable_validation_api:
        raise HTTPException(status_code=404, detail="Validation API disabled")
    if ingest_mode not in ALLOWED_INGEST_MODES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown ingest_mode {ingest_mode!r}; allowed: {sorted(ALLOWED_INGEST_MODES)}",
        )

    case = Case(
        name=case_name or f"Validation upload {uuid4().hex[:8]}",
        description="Automated ingest validation (custom ZIP)",
    )
    db.add(case)
    db.commit()
    db.refresh(case)

    job = await _create_ingest_source(
        case_id=case.id,
        file=file,
        hostname=None,
        platform=None,
        db=db,
        manifest_overrides={"ff_validation_mode": ingest_mode},
    )
    base = f"/api/v1/cases/{case.id}/sources/{job.evidence_source_id}"

    return IngestSampleStartRead(
        case_id=case.id,
        job_id=job.id,
        evidence_source_id=job.evidence_source_id,
        sample=file.filename or "upload",
        outcome_path=f"/api/v1/jobs/{job.id}/outcome",
        job_path=f"/api/v1/jobs/{job.id}",
        stats_path=f"{base}/stats",
    )
