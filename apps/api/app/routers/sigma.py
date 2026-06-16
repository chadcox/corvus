from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import EvidenceSource, SigmaDetection
from ff_core.schemas import SigmaDetectionRead

router = APIRouter(prefix="/cases/{case_id}/sources/{source_id}/sigma", tags=["sigma"])


@router.get("", response_model=list[SigmaDetectionRead])
def list_sigma_detections(
    case_id: UUID,
    source_id: UUID,
    engine: str | None = Query(
        None,
        description="Filter by detection engine (sigma, chainsaw)",
    ),
    db: Session = Depends(get_db),
) -> list[SigmaDetection]:
    source = (
        db.query(EvidenceSource)
        .filter(EvidenceSource.id == source_id, EvidenceSource.case_id == case_id)
        .first()
    )
    if not source:
        raise HTTPException(status_code=404, detail="Evidence source not found")

    level_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "informational": 4}
    query = db.query(SigmaDetection).filter(SigmaDetection.evidence_source_id == source_id)
    if engine:
        query = query.filter(SigmaDetection.engine == engine)
    rows = query.all()
    rows.sort(
        key=lambda r: (
            level_order.get(r.level.lower(), 9),
            -r.match_count,
            r.title,
        )
    )
    return rows
