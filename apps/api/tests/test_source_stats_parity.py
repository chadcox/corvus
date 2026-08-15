"""Regression tests for the shared per-source stats loader.

Bug this locks down: `/api/v1/jobs/{job_id}/outcome` and
`/api/v1/cases/{case_id}/sources/{source_id}/stats` each computed their own
`SourceStats`. The outcome copy never set `mft_count` or `browser_count`, so
the same evidence source reported `mft_count=0` on one route and the real
count on the other, and the UI stat strip disagreed with the ingest report
depending on which route it happened to read.

Both routes now call `app.services.source_stats.load_source_stats`. These
tests assert the counts are right and that the two routes stay identical.

The stub below evaluates real SQLAlchemy filter clauses (column + bound
value) against in-memory rows rather than replaying a fixed sequence of
scalars, so reordering or adding a count in the loader cannot silently pass.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import pytest

from app.models import EvidenceSource
from app.routers import ingest_outcome as ingest_outcome_router
from app.routers import stats as stats_router
from app.services.source_stats import EVENT_TYPE_LIMIT, load_source_stats

TABLES = {
    "timeline_events": "timeline",
    "filesystem_nodes": "filesystem",
    "entities": "entities",
    "sigma_detections": "sigma",
}


def _clause_to_predicate(clause: Any):
    """Turn `Model.col == value` into a callable over a dict row."""
    column = clause.left.name
    value = clause.right.value
    return lambda row: row.get(column) == value


class _CountQuery:
    def __init__(self, rows: list[dict[str, Any]]):
        self.rows = rows

    def filter(self, *clauses):
        preds = [_clause_to_predicate(c) for c in clauses]
        return _CountQuery([r for r in self.rows if all(p(r) for p in preds)])

    def scalar(self) -> int:
        return len(self.rows)


class _DistinctQuery:
    def __init__(self, rows: list[dict[str, Any]], column: str):
        self.rows = rows
        self.column = column
        self._limit: int | None = None

    def filter(self, *clauses):
        preds = [_clause_to_predicate(c) for c in clauses]
        return _DistinctQuery(
            [r for r in self.rows if all(p(r) for p in preds)], self.column
        )

    def order_by(self, *_args):
        return self

    def limit(self, n: int):
        self._limit = n
        return self

    def all(self) -> list[tuple[Any]]:
        seen = sorted({r.get(self.column) for r in self.rows}, key=lambda v: (v is None, v))
        rows = [(v,) for v in seen]
        return rows[: self._limit] if self._limit else rows


class _SourceQuery:
    def __init__(self, source: EvidenceSource | None):
        self.source = source

    def filter(self, *_clauses):
        return self

    def first(self):
        return self.source


class StatsDb:
    """Minimal Session stand-in that counts real rows for real clauses."""

    def __init__(self, source: EvidenceSource, tables: dict[str, list[dict[str, Any]]]):
        self.source = source
        self.tables = tables

    def query(self, arg):
        if arg is EvidenceSource:
            return _SourceQuery(self.source)
        # `func.count(Model.id)` renders as "count(<table>.id)";
        # `distinct(Model.event_type)` renders as "DISTINCT <table>.event_type".
        rendered = str(arg)
        for table in self.tables:
            if f"{table}." in rendered:
                rows = self.tables[table]
                if rendered.upper().startswith("DISTINCT"):
                    return _DistinctQuery(rows, rendered.split(".")[-1])
                return _CountQuery(rows)
        raise AssertionError(f"unexpected query target: {rendered}")


SOURCE_ID = uuid.uuid4()
CASE_ID = uuid.uuid4()
OTHER_SOURCE_ID = uuid.uuid4()


def _timeline_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    # 6 evtx events for our source.
    rows += [
        {"evidence_source_id": SOURCE_ID, "artifact_type": "evtx", "event_type": "4624"}
        for _ in range(6)
    ]
    # 3 mft events for our source.
    rows += [
        {"evidence_source_id": SOURCE_ID, "artifact_type": "mft", "event_type": "file"}
        for _ in range(3)
    ]
    # 2 browser events for our source.
    rows += [
        {
            "evidence_source_id": SOURCE_ID,
            "artifact_type": "browser",
            "event_type": "visit",
        }
        for _ in range(2)
    ]
    # Noise from a different source must never be counted.
    rows += [
        {
            "evidence_source_id": OTHER_SOURCE_ID,
            "artifact_type": "mft",
            "event_type": "other",
        }
        for _ in range(50)
    ]
    return rows


def _make_db() -> StatsDb:
    source = EvidenceSource(
        id=SOURCE_ID,
        case_id=CASE_ID,
        hostname="stat-host",
        collector="import",
        source_type="endpoint",
        platform="windows",
        package_path="/tmp",
        status="completed",
    )
    return StatsDb(
        source,
        {
            "timeline_events": _timeline_rows(),
            "filesystem_nodes": [{"evidence_source_id": SOURCE_ID} for _ in range(4)]
            + [{"evidence_source_id": OTHER_SOURCE_ID}],
            "entities": [{"evidence_source_id": SOURCE_ID} for _ in range(7)],
            "sigma_detections": [{"evidence_source_id": SOURCE_ID} for _ in range(3)],
        },
    )


def test_loader_counts_scoped_to_source():
    stats = load_source_stats(_make_db(), SOURCE_ID)

    assert stats.timeline_count == 11  # 6 evtx + 3 mft + 2 browser, no cross-source
    assert stats.filesystem_count == 4
    assert stats.entity_count == 7
    assert stats.sigma_detection_count == 3
    assert stats.mft_count == 3
    assert stats.browser_count == 2
    assert stats.event_types == ["4624", "file", "visit"]


def test_outcome_and_stats_routes_agree():
    """The actual regression: outcome used to report mft_count/browser_count as 0."""
    from_stats = stats_router.get_source_stats(
        case_id=CASE_ID, source_id=SOURCE_ID, db=_make_db()
    )
    from_outcome = ingest_outcome_router._load_stats(_make_db(), SOURCE_ID)

    assert from_outcome is not None
    assert from_outcome.model_dump() == from_stats.model_dump()
    assert from_outcome.mft_count == 3
    assert from_outcome.browser_count == 2


def test_stats_route_404s_for_unknown_source():
    db = StatsDb(None, {"timeline_events": []})  # type: ignore[arg-type]
    with pytest.raises(Exception) as exc:
        stats_router.get_source_stats(case_id=CASE_ID, source_id=SOURCE_ID, db=db)
    assert getattr(exc.value, "status_code", None) == 404


def test_event_types_capped():
    db = _make_db()
    db.tables["timeline_events"] = [
        {
            "evidence_source_id": SOURCE_ID,
            "artifact_type": "evtx",
            "event_type": f"evt-{i:04d}",
        }
        for i in range(EVENT_TYPE_LIMIT + 25)
    ]
    stats = load_source_stats(db, SOURCE_ID)
    assert len(stats.event_types) == EVENT_TYPE_LIMIT
    assert stats.timeline_count == EVENT_TYPE_LIMIT + 25


def test_empty_source_reports_zeros():
    db = StatsDb(
        SimpleNamespace(id=SOURCE_ID),  # type: ignore[arg-type]
        {
            "timeline_events": [],
            "filesystem_nodes": [],
            "entities": [],
            "sigma_detections": [],
        },
    )
    stats = load_source_stats(db, SOURCE_ID)
    assert stats.timeline_count == 0
    assert stats.mft_count == 0
    assert stats.browser_count == 0
    assert stats.event_types == []
