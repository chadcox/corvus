"""Single source of truth for per-evidence-source counts.

Both the stats router and the ingest-outcome router report the same
`SourceStats` payload. They used to compute it independently, and the
ingest-outcome copy silently omitted `mft_count` / `browser_count`, so the
same source reported `mft_count=0` on `/outcome` and the real count on
`/stats`. Everything now goes through `load_source_stats`.
"""

from uuid import UUID

from sqlalchemy import distinct, func
from sqlalchemy.orm import Session

from app.models import Entity, FilesystemNode, SigmaDetection, TimelineEvent
from corvus_core.schemas import SourceStats

# Cap on distinct event types returned; a noisy source can have thousands.
EVENT_TYPE_LIMIT = 50


def _count(db: Session, column, *filters) -> int:
    return db.query(func.count(column)).filter(*filters).scalar() or 0


def load_source_stats(db: Session, source_id: UUID) -> SourceStats:
    """Count timeline, filesystem, entity, and detection rows for one source."""
    timeline_count = _count(
        db, TimelineEvent.id, TimelineEvent.evidence_source_id == source_id
    )
    filesystem_count = _count(
        db, FilesystemNode.id, FilesystemNode.evidence_source_id == source_id
    )
    entity_count = _count(db, Entity.id, Entity.evidence_source_id == source_id)
    sigma_detection_count = _count(
        db, SigmaDetection.id, SigmaDetection.evidence_source_id == source_id
    )
    mft_count = _count(
        db,
        TimelineEvent.id,
        TimelineEvent.evidence_source_id == source_id,
        TimelineEvent.artifact_type == "mft",
    )
    browser_count = _count(
        db,
        TimelineEvent.id,
        TimelineEvent.evidence_source_id == source_id,
        TimelineEvent.artifact_type == "browser",
    )
    event_types = [
        row[0]
        for row in (
            db.query(distinct(TimelineEvent.event_type))
            .filter(TimelineEvent.evidence_source_id == source_id)
            .order_by(TimelineEvent.event_type)
            .limit(EVENT_TYPE_LIMIT)
            .all()
        )
        if row[0]
    ]

    return SourceStats(
        timeline_count=timeline_count,
        filesystem_count=filesystem_count,
        entity_count=entity_count,
        sigma_detection_count=sigma_detection_count,
        mft_count=mft_count,
        browser_count=browser_count,
        event_types=event_types,
    )
