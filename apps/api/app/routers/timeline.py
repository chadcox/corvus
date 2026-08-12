import io
import re
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import EvidenceSource, TimelineEvent
from app.search_filters import LIKE_ESCAPE_CHAR, like_contains
from app.util.csv_export import csv_writer, escape_csv_row
from corvus_core.schemas import TimelineEventRead

router = APIRouter(prefix="/cases/{case_id}/sources/{source_id}/timeline", tags=["timeline"])

EXPORT_MAX = 50_000

# Additive response headers that make CSV export truncation explicit. The CSV
# body itself is unchanged: a spreadsheet-safe export must not carry a warning
# row that downstream tooling would read as evidence.
EXPORT_TRUNCATED_HEADER = "X-Corvus-Export-Truncated"
EXPORT_ROW_LIMIT_HEADER = "X-Corvus-Export-Row-Limit"
EXPORT_ROW_COUNT_HEADER = "X-Corvus-Export-Row-Count"
EXPORT_TOTAL_MATCHES_HEADER = "X-Corvus-Export-Total-Matches"


def export_row_limit() -> int:
    """Resolve the configured export row cap.

    A non-positive setting would silently produce an empty or unbounded export,
    so fall back to the documented default instead.
    """
    configured = settings.timeline_export_max_rows
    return configured if configured > 0 else EXPORT_MAX


BROWSER_CATEGORY_TYPES: dict[str, list[str]] = {
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


def _get_source(db: Session, case_id: UUID, source_id: UUID) -> EvidenceSource:
    source = (
        db.query(EvidenceSource)
        .filter(EvidenceSource.id == source_id, EvidenceSource.case_id == case_id)
        .first()
    )
    if not source:
        raise HTTPException(status_code=404, detail="Evidence source not found")
    return source


def _filtered_timeline_query(
    db: Session,
    source_id: UUID,
    *,
    start: datetime | None,
    end: datetime | None,
    event_type: str | None,
    artifact_type: str | None,
    q: str | None,
    sigma_only: bool = False,
    mft_only: bool = False,
    browser_only: bool = False,
    browser_category: str | None = None,
):
    query = db.query(TimelineEvent).filter(TimelineEvent.evidence_source_id == source_id)
    if start:
        query = query.filter(TimelineEvent.timestamp_utc >= start)
    if end:
        query = query.filter(TimelineEvent.timestamp_utc <= end)
    if event_type:
        query = query.filter(TimelineEvent.event_type == event_type)
    if artifact_type:
        query = query.filter(TimelineEvent.artifact_type == artifact_type)
    if q:
        like = like_contains(q)
        if browser_only:
            query = query.filter(
                or_(
                    TimelineEvent.summary.ilike(like, escape=LIKE_ESCAPE_CHAR),
                    TimelineEvent.data["url"].astext.ilike(like, escape=LIKE_ESCAPE_CHAR),
                    TimelineEvent.data["title"].astext.ilike(like, escape=LIKE_ESCAPE_CHAR),
                    TimelineEvent.data["message"].astext.ilike(like, escape=LIKE_ESCAPE_CHAR),
                    TimelineEvent.data["host"].astext.ilike(like, escape=LIKE_ESCAPE_CHAR),
                )
            )
        else:
            query = query.filter(TimelineEvent.summary.ilike(like, escape=LIKE_ESCAPE_CHAR))
    if sigma_only:
        query = query.filter(func.coalesce(func.jsonb_array_length(TimelineEvent.sigma_hits), 0) > 0)
    if mft_only:
        query = query.filter(
            or_(
                TimelineEvent.artifact_type == "mft",
                TimelineEvent.artifact_type.ilike("%mft%"),
                TimelineEvent.original_source.ilike("%/mft/%"),
                TimelineEvent.original_source.ilike("%.mft%"),
            )
        )
    if browser_only:
        query = query.filter(
            or_(
                TimelineEvent.artifact_type == "browser",
                TimelineEvent.event_type.like("browser.%"),
                TimelineEvent.original_source.ilike("%/browser/%"),
            )
        )
        if browser_category and browser_category in BROWSER_CATEGORY_TYPES:
            query = query.filter(
                TimelineEvent.event_type.in_(BROWSER_CATEGORY_TYPES[browser_category])
            )
    # Stable order is required for offset pagination; many artifacts (notably MFT)
    # share identical timestamps, so include id as a deterministic tiebreaker.
    return query.order_by(TimelineEvent.timestamp_utc.asc(), TimelineEvent.id.asc())


@router.get("/events/{event_id}", response_model=TimelineEventRead)
def get_timeline_event(
    case_id: UUID,
    source_id: UUID,
    event_id: UUID,
    db: Session = Depends(get_db),
) -> TimelineEvent:
    _get_source(db, case_id, source_id)
    event = (
        db.query(TimelineEvent)
        .filter(
            TimelineEvent.id == event_id,
            TimelineEvent.evidence_source_id == source_id,
        )
        .first()
    )
    if not event:
        raise HTTPException(status_code=404, detail="Timeline event not found")
    return event


@router.get("", response_model=list[TimelineEventRead])
def list_timeline_events(
    case_id: UUID,
    source_id: UUID,
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
    event_type: str | None = Query(None),
    artifact_type: str | None = Query(None),
    q: str | None = Query(None, description="Search summary"),
    sigma_only: bool = Query(False, description="Only events with detection rule hits"),
    mft_only: bool = Query(False, description="Only MFT-derived file system records"),
    browser_only: bool = Query(False, description="Only Chromium browser forensics (Hindsight)"),
    browser_category: str | None = Query(
        None,
        description="Browser subset: visits, downloads, cookies, bookmarks, sessions, credentials, storage",
    ),
    limit: int = Query(10_000, le=10_000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[TimelineEvent]:
    _get_source(db, case_id, source_id)
    return _filtered_timeline_query(
        db,
        source_id,
        start=start,
        end=end,
        event_type=event_type,
        artifact_type=artifact_type,
        q=q,
        sigma_only=sigma_only,
        mft_only=mft_only,
        browser_only=browser_only,
        browser_category=browser_category,
    ).offset(offset).limit(limit).all()


@router.get("/count")
def count_timeline_events(
    case_id: UUID,
    source_id: UUID,
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
    event_type: str | None = Query(None),
    artifact_type: str | None = Query(None),
    q: str | None = Query(None, description="Search summary"),
    sigma_only: bool = Query(False, description="Only events with detection rule hits"),
    mft_only: bool = Query(False, description="Only MFT-derived file system records"),
    browser_only: bool = Query(False, description="Only Chromium browser forensics (Hindsight)"),
    browser_category: str | None = Query(None),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    """Return the filtered total count (no rows materialized).

    ``export_row_limit`` is reported alongside so callers can tell, before
    starting a download, whether the CSV export would be truncated.
    """
    _get_source(db, case_id, source_id)
    query = _filtered_timeline_query(
        db,
        source_id,
        start=start,
        end=end,
        event_type=event_type,
        artifact_type=artifact_type,
        q=q,
        sigma_only=sigma_only,
        mft_only=mft_only,
        browser_only=browser_only,
        browser_category=browser_category,
    )
    count = query.order_by(None).with_entities(func.count()).scalar() or 0
    return {"count": count, "export_row_limit": export_row_limit()}


@router.get("/export")
def export_timeline_csv(
    case_id: UUID,
    source_id: UUID,
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
    event_type: str | None = Query(None),
    artifact_type: str | None = Query(None),
    q: str | None = Query(None),
    sigma_only: bool = Query(False),
    mft_only: bool = Query(False),
    browser_only: bool = Query(False),
    browser_category: str | None = Query(None),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Download filtered timeline events as CSV for reporting.

    The export is capped at ``TIMELINE_EXPORT_MAX_ROWS`` rows. Truncation is
    reported in additive ``X-Corvus-Export-*`` response headers rather than in
    the CSV body, so a partial export is never mistaken for a complete one.
    """
    source = _get_source(db, case_id, source_id)
    filtered = _filtered_timeline_query(
        db,
        source_id,
        start=start,
        end=end,
        event_type=event_type,
        artifact_type=artifact_type,
        q=q,
        sigma_only=sigma_only,
        mft_only=mft_only,
        browser_only=browser_only,
        browser_category=browser_category,
    )

    # Headers must be settled before the body streams, so the match total comes
    # from a count query rather than from tallying yielded rows.
    row_limit = export_row_limit()
    total_matches = filtered.order_by(None).with_entities(func.count()).scalar() or 0
    row_count = min(total_matches, row_limit)
    truncated = total_matches > row_limit

    query = filtered.with_entities(
        TimelineEvent.timestamp_utc,
        TimelineEvent.event_type,
        TimelineEvent.summary,
        TimelineEvent.artifact_type,
        TimelineEvent.original_source,
    ).limit(row_limit)

    escape = settings.csv_export_formula_escape

    def generate():
        buffer = io.StringIO()
        writer = csv_writer(buffer, enabled=escape)
        writer.writerow(
            ["timestamp_utc", "event_type", "summary", "artifact_type", "original_source"]
        )
        yield buffer.getvalue()
        for ev in query.yield_per(2000):
            buffer.seek(0)
            buffer.truncate(0)
            writer.writerow(
                escape_csv_row(
                    [
                        ev.timestamp_utc.isoformat(),
                        ev.event_type,
                        ev.summary,
                        ev.artifact_type or "",
                        ev.original_source or "",
                    ],
                    enabled=escape,
                )
            )
            yield buffer.getvalue()

    safe_host = re.sub(r"[^A-Za-z0-9._-]", "_", source.hostname or "host")
    filename = f"timeline-{safe_host}.csv"
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        EXPORT_TRUNCATED_HEADER: "true" if truncated else "false",
        EXPORT_ROW_LIMIT_HEADER: str(row_limit),
        EXPORT_ROW_COUNT_HEADER: str(row_count),
        EXPORT_TOTAL_MATCHES_HEADER: str(total_matches),
        # The web app is served from a different origin, so these headers are
        # unreadable by browser callers unless CORS exposes them explicitly.
        "Access-Control-Expose-Headers": ", ".join(
            [
                "Content-Disposition",
                EXPORT_TRUNCATED_HEADER,
                EXPORT_ROW_LIMIT_HEADER,
                EXPORT_ROW_COUNT_HEADER,
                EXPORT_TOTAL_MATCHES_HEADER,
            ]
        ),
    }
    return StreamingResponse(generate(), media_type="text/csv", headers=headers)
