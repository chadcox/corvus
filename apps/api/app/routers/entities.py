from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Entity, EvidenceSource, TimelineEvent
from corvus_core.schemas import EntityRead, TimelineEventRead

router = APIRouter(prefix="/cases/{case_id}/sources/{source_id}/entities", tags=["entities"])


def _get_source(db: Session, case_id: UUID, source_id: UUID) -> EvidenceSource:
    source = (
        db.query(EvidenceSource)
        .filter(EvidenceSource.id == source_id, EvidenceSource.case_id == case_id)
        .first()
    )
    if not source:
        raise HTTPException(status_code=404, detail="Evidence source not found")
    return source


@router.get("", response_model=list[EntityRead])
def list_entities(
    case_id: UUID,
    source_id: UUID,
    entity_type: str | None = Query(None),
    q: str | None = Query(None),
    ids: list[UUID] | None = Query(None),
    limit: int = Query(200, le=1000),
    db: Session = Depends(get_db),
) -> list[Entity]:
    _get_source(db, case_id, source_id)

    query = db.query(Entity).filter(Entity.evidence_source_id == source_id)
    if entity_type:
        query = query.filter(Entity.entity_type == entity_type)
    if q:
        query = query.filter(Entity.display_name.ilike(f"%{q}%"))
    if ids:
        query = query.filter(Entity.id.in_(ids))

    return query.order_by(Entity.entity_type, Entity.display_name).limit(limit).all()


@router.get("/{entity_id}/timeline", response_model=list[TimelineEventRead])
def list_entity_timeline(
    case_id: UUID,
    source_id: UUID,
    entity_id: UUID,
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
) -> list[TimelineEvent]:
    _get_source(db, case_id, source_id)

    entity = (
        db.query(Entity)
        .filter(Entity.id == entity_id, Entity.evidence_source_id == source_id)
        .first()
    )
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    eid = str(entity_id)
    return (
        db.query(TimelineEvent)
        .filter(
            TimelineEvent.evidence_source_id == source_id,
            TimelineEvent.entity_refs.contains([eid]),
        )
        .order_by(TimelineEvent.timestamp_utc.asc())
        .limit(limit)
        .all()
    )
