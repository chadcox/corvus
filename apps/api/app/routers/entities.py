from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Entity, EvidenceSource, TimelineEvent
from app.search_filters import LIKE_ESCAPE_CHAR, like_contains
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


def _get_entity(db: Session, source_id: UUID, entity_id: UUID) -> Entity:
    entity = (
        db.query(Entity)
        .filter(Entity.id == entity_id, Entity.evidence_source_id == source_id)
        .first()
    )
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    return entity


def _filtered_entity_query(
    db: Session,
    source_id: UUID,
    *,
    entity_type: str | None,
    q: str | None,
    ids: list[UUID] | None,
):
    query = db.query(Entity).filter(Entity.evidence_source_id == source_id)
    if entity_type:
        query = query.filter(Entity.entity_type == entity_type)
    if q:
        query = query.filter(
            Entity.display_name.ilike(like_contains(q), escape=LIKE_ESCAPE_CHAR)
        )
    if ids:
        query = query.filter(Entity.id.in_(ids))
    # Stable order is required for offset pagination; extraction routinely emits
    # several entities sharing a (type, display_name) pair, so id is the
    # deterministic tiebreaker that keeps page boundaries from repeating or
    # dropping rows.
    return query.order_by(Entity.entity_type, Entity.display_name, Entity.id)


def _entity_timeline_query(db: Session, source_id: UUID, entity_id: UUID):
    eid = str(entity_id)
    return (
        db.query(TimelineEvent)
        .filter(
            TimelineEvent.evidence_source_id == source_id,
            TimelineEvent.entity_refs.contains([eid]),
        )
        # Same reasoning as the entity list: many artifacts share a timestamp.
        .order_by(TimelineEvent.timestamp_utc.asc(), TimelineEvent.id.asc())
    )


def _count(query) -> int:
    return query.order_by(None).with_entities(func.count()).scalar() or 0


@router.get("/count")
def count_entities(
    case_id: UUID,
    source_id: UUID,
    entity_type: str | None = Query(None),
    q: str | None = Query(None),
    ids: list[UUID] | None = Query(None),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    """Return the exact filtered entity total (no rows materialized)."""
    _get_source(db, case_id, source_id)
    query = _filtered_entity_query(db, source_id, entity_type=entity_type, q=q, ids=ids)
    return {"count": _count(query)}


@router.get("", response_model=list[EntityRead])
def list_entities(
    case_id: UUID,
    source_id: UUID,
    entity_type: str | None = Query(None),
    q: str | None = Query(None),
    ids: list[UUID] | None = Query(None),
    limit: int = Query(200, ge=0, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[Entity]:
    _get_source(db, case_id, source_id)
    return (
        _filtered_entity_query(db, source_id, entity_type=entity_type, q=q, ids=ids)
        .offset(offset)
        .limit(limit)
        .all()
    )


@router.get("/{entity_id}/timeline/count")
def count_entity_timeline(
    case_id: UUID,
    source_id: UUID,
    entity_id: UUID,
    db: Session = Depends(get_db),
) -> dict[str, int]:
    """Return the exact number of timeline events linked to one entity."""
    _get_source(db, case_id, source_id)
    _get_entity(db, source_id, entity_id)
    return {"count": _count(_entity_timeline_query(db, source_id, entity_id))}


@router.get("/{entity_id}/timeline", response_model=list[TimelineEventRead])
def list_entity_timeline(
    case_id: UUID,
    source_id: UUID,
    entity_id: UUID,
    limit: int = Query(100, ge=0, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[TimelineEvent]:
    _get_source(db, case_id, source_id)
    _get_entity(db, source_id, entity_id)
    return _entity_timeline_query(db, source_id, entity_id).offset(offset).limit(limit).all()
