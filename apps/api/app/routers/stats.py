from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import distinct, func, text
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Entity, EvidenceSource, FilesystemNode, SigmaDetection, TimelineEvent
from corvus_core.schemas import SourceStats

router = APIRouter(prefix="/cases/{case_id}/sources/{source_id}/stats", tags=["stats"])


@router.get("", response_model=SourceStats)
def get_source_stats(
    case_id: UUID,
    source_id: UUID,
    db: Session = Depends(get_db),
) -> SourceStats:
    source = (
        db.query(EvidenceSource)
        .filter(EvidenceSource.id == source_id, EvidenceSource.case_id == case_id)
        .first()
    )
    if not source:
        raise HTTPException(status_code=404, detail="Evidence source not found")

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
    mft_count = (
        db.query(func.count(TimelineEvent.id))
        .filter(
            TimelineEvent.evidence_source_id == source_id,
            TimelineEvent.artifact_type == "mft",
        )
        .scalar()
        or 0
    )
    browser_count = (
        db.query(func.count(TimelineEvent.id))
        .filter(
            TimelineEvent.evidence_source_id == source_id,
            TimelineEvent.artifact_type == "browser",
        )
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
        mft_count=mft_count,
        browser_count=browser_count,
        event_types=event_types,
    )


@router.get("/histogram")
def get_timeline_histogram(
    case_id: UUID,
    source_id: UUID,
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
    event_type: str | None = Query(None),
    q: str | None = Query(None),
    artifact_type: str | None = Query(None),
    sigma_only: bool = Query(False),
    mft_only: bool = Query(False),
    browser_only: bool = Query(False),
    browser_category: str | None = Query(None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return event counts bucketed over time for the density chart.

    Granularity is selected automatically from the total time span.
    """
    source = (
        db.query(EvidenceSource)
        .filter(EvidenceSource.id == source_id, EvidenceSource.case_id == case_id)
        .first()
    )
    if not source:
        raise HTTPException(status_code=404, detail="Evidence source not found")

    clauses: list[str] = []
    params: dict[str, Any] = {"sid": str(source_id)}
    if start:
        clauses.append("AND timestamp_utc >= :start")
        params["start"] = start
    if end:
        clauses.append("AND timestamp_utc <= :end")
        params["end"] = end
    if event_type:
        clauses.append("AND event_type = :event_type")
        params["event_type"] = event_type
    if q:
        if browser_only:
            clauses.append(
                "AND (summary ILIKE :q OR data->>'url' ILIKE :q OR data->>'title' ILIKE :q OR data->>'message' ILIKE :q OR data->>'host' ILIKE :q)"
            )
        else:
            clauses.append("AND summary ILIKE :q")
        params["q"] = f"%{q}%"
    if artifact_type:
        clauses.append("AND artifact_type = :artifact_type")
        params["artifact_type"] = artifact_type
    if sigma_only:
        clauses.append("AND coalesce(jsonb_array_length(sigma_hits), 0) > 0")
    if mft_only:
        clauses.append(
            "AND (artifact_type = 'mft' OR artifact_type ILIKE '%mft%' OR original_source ILIKE '%/mft/%' OR original_source ILIKE '%.mft%')"
        )
    if browser_only:
        clauses.append(
            "AND (artifact_type = 'browser' OR event_type LIKE 'browser.%' OR original_source ILIKE '%/browser/%')"
        )
        if browser_category:
            category_map: dict[str, list[str]] = {
                "visits": ["browser.visit"],
                "downloads": ["browser.download"],
                "cookies": ["browser.cookie"],
                "bookmarks": ["browser.bookmark"],
                "sessions": ["browser.session"],
                "credentials": ["browser.credential"],
                "storage": ["browser.storage"],
                "autofill": ["browser.autofill"],
                "extensions": ["browser.extension"],
                "cache": ["browser.cache"],
                "preferences": ["browser.preference"],
            }
            event_types = category_map.get(browser_category)
            if event_types:
                clauses.append("AND event_type = ANY(:browser_types)")
                params["browser_types"] = event_types
    filter_clause = " ".join(clauses)

    range_row = db.execute(
        text(
            f"""
            SELECT
                min(timestamp_utc),
                max(timestamp_utc),
                extract(epoch from max(timestamp_utc) - min(timestamp_utc)) as span_secs
            FROM timeline_events
            WHERE evidence_source_id = :sid {filter_clause}
            """
        ),
        params,
    ).fetchone()

    if not range_row or range_row[0] is None:
        return {"buckets": [], "total": 0, "granularity": "day"}

    span_secs = float(range_row[2] or 0)
    if span_secs < 3_600:
        granularity = "minute"
    elif span_secs < 86_400:
        granularity = "hour"
    elif span_secs < 2_592_000:
        granularity = "day"
    elif span_secs < 94_608_000:
        granularity = "week"
    else:
        granularity = "month"

    rows = db.execute(
        text(
            f"""
            SELECT
                to_char(
                    date_trunc('{granularity}', timestamp_utc AT TIME ZONE 'UTC'),
                    'YYYY-MM-DD"T"HH24:MI:SS"Z"'
                ) AS ts,
                count(*)::int AS count
            FROM timeline_events
            WHERE evidence_source_id = :sid {filter_clause}
            GROUP BY date_trunc('{granularity}', timestamp_utc AT TIME ZONE 'UTC')
            ORDER BY 1
            """
        ),
        params,
    ).fetchall()

    buckets = [{"ts": row[0], "count": row[1]} for row in rows]
    return {"buckets": buckets, "total": sum(b["count"] for b in buckets), "granularity": granularity}
