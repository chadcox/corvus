from uuid import UUID
from collections import deque
from threading import Lock
import time

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import cast, or_, String
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Entity, EvidenceSource, FilesystemNode, TimelineEvent
from app.services.opensearch_service import opensearch_global_search
from ff_core.schemas import EntityRead, FilesystemNodeRead, GlobalSearchResult, TimelineEventRead

router = APIRouter(
    prefix="/cases/{case_id}/sources/{source_id}/search",
    tags=["search"],
)

DEFAULT_LIMIT = 25
MAX_LIMIT = 100
FALLBACK_MIN_COMPLEX_QUERY_LENGTH = 3
_SEARCH_METRICS_WINDOW_SECONDS = 300
_SEARCH_METRICS_MAX_SAMPLES = 2000
_SEARCH_METRICS_LOCK = Lock()
_SEARCH_METRICS: deque[tuple[float, str, bool, float]] = deque()


def _like(q: str) -> str:
    return f"%{q}%"


def _prune_search_metrics(now: float) -> None:
    cutoff = now - _SEARCH_METRICS_WINDOW_SECONDS
    while _SEARCH_METRICS and _SEARCH_METRICS[0][0] < cutoff:
        _SEARCH_METRICS.popleft()


def _record_search_metric(path: str, short_query: bool, latency_ms: float) -> None:
    now = time.monotonic()
    with _SEARCH_METRICS_LOCK:
        _prune_search_metrics(now)
        _SEARCH_METRICS.append((now, path, short_query, latency_ms))
        while len(_SEARCH_METRICS) > _SEARCH_METRICS_MAX_SAMPLES:
            _SEARCH_METRICS.popleft()


def search_metrics_snapshot() -> dict[str, float | int]:
    now = time.monotonic()
    with _SEARCH_METRICS_LOCK:
        _prune_search_metrics(now)
        total = len(_SEARCH_METRICS)
        opensearch_hits = 0
        fallback_hits = 0
        fallback_short = 0
        fallback_latency_total = 0.0
        for _ts, path, short_query, latency_ms in _SEARCH_METRICS:
            if path == "opensearch":
                opensearch_hits += 1
            else:
                fallback_hits += 1
                fallback_latency_total += latency_ms
                if short_query:
                    fallback_short += 1
        fallback_avg_ms = (fallback_latency_total / fallback_hits) if fallback_hits else 0.0
    return {
        "window_seconds": _SEARCH_METRICS_WINDOW_SECONDS,
        "total_queries": total,
        "opensearch_hits": opensearch_hits,
        "fallback_hits": fallback_hits,
        "fallback_short_queries": fallback_short,
        "fallback_avg_ms": round(fallback_avg_ms, 2),
    }


@router.get("", response_model=GlobalSearchResult)
def global_search(
    case_id: UUID,
    source_id: UUID,
    q: str = Query(..., min_length=1, max_length=500),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    db: Session = Depends(get_db),
) -> GlobalSearchResult:
    """Search timeline events, filesystem paths, and entities in one query."""
    source = (
        db.query(EvidenceSource)
        .filter(EvidenceSource.id == source_id, EvidenceSource.case_id == case_id)
        .first()
    )
    if not source:
        raise HTTPException(status_code=404, detail="Evidence source not found")

    if source.status in ("pending", "running"):
        raise HTTPException(
            status_code=409,
            detail="Evidence is still processing. Search is available after ingest completes.",
        )

    query = q.strip()
    short_fallback_query = len(query) < FALLBACK_MIN_COMPLEX_QUERY_LENGTH
    started = time.monotonic()
    pattern = _like(query)
    opensearch_result = opensearch_global_search(
        db,
        case_id=case_id,
        source_id=source_id,
        q=query,
        limit=limit,
    )
    if opensearch_result is not None:
        _record_search_metric(
            path="opensearch",
            short_query=short_fallback_query,
            latency_ms=(time.monotonic() - started) * 1000.0,
        )
        return opensearch_result

    base = TimelineEvent.evidence_source_id == source_id

    timeline = []
    if not short_fallback_query:
        timeline = (
            db.query(TimelineEvent)
            .filter(
                base,
                or_(
                    TimelineEvent.summary.ilike(pattern),
                    TimelineEvent.event_type.ilike(pattern),
                    TimelineEvent.artifact_type.ilike(pattern),
                    TimelineEvent.original_source.ilike(pattern),
                    cast(TimelineEvent.data, String).ilike(pattern),
                ),
            )
            .order_by(TimelineEvent.timestamp_utc.asc())
            .limit(limit)
            .all()
        )

    filesystem = (
        db.query(FilesystemNode)
        .filter(
            FilesystemNode.evidence_source_id == source_id,
            or_(
                FilesystemNode.full_path.ilike(pattern),
                FilesystemNode.name.ilike(pattern),
            ),
        )
        .order_by(FilesystemNode.full_path.asc())
        .limit(limit)
        .all()
    )

    entities = []
    if not short_fallback_query:
        entities = (
            db.query(Entity)
            .filter(
                Entity.evidence_source_id == source_id,
                or_(
                    Entity.display_name.ilike(pattern),
                    Entity.entity_type.ilike(pattern),
                    cast(Entity.attributes, String).ilike(pattern),
                ),
            )
            .order_by(Entity.entity_type, Entity.display_name)
            .limit(limit)
            .all()
        )

    total = len(timeline) + len(filesystem) + len(entities)
    _record_search_metric(
        path="fallback",
        short_query=short_fallback_query,
        latency_ms=(time.monotonic() - started) * 1000.0,
    )
    return GlobalSearchResult(
        query=query,
        timeline=[TimelineEventRead.model_validate(e) for e in timeline],
        filesystem=[FilesystemNodeRead.model_validate(n) for n in filesystem],
        entities=[EntityRead.model_validate(e) for e in entities],
        total=total,
    )
