from __future__ import annotations

import uuid
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app.auth.service import get_current_user
from app.database import get_db
from app.main import app
from app.models import Entity, EvidenceSource, FilesystemNode, TimelineEvent
from app.routers import stats as stats_router
from app.routers.timeline import _filtered_timeline_query
from app.search_filters import escape_like, like_contains


@dataclass
class FakeUser:
    id: str = "test-user"
    username: str = "analyst"
    role: str = "analyst"
    is_active: bool = True


class RecordingQuery:
    """Collects filter criteria so tests can compile the emitted SQL."""

    def __init__(self, rows: list[Any], recorded: list[Any]):
        self.rows = rows
        self.recorded = recorded

    def filter(self, *args, **_kwargs):
        self.recorded.extend(args)
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def offset(self, *_args, **_kwargs):
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return list(self.rows)


class RecordingDb:
    def __init__(self, source: EvidenceSource):
        self.source = source
        self.criteria: list[Any] = []

    def query(self, *models):
        rows = [self.source] if models[0] is EvidenceSource else []
        return RecordingQuery(rows, self.criteria)


def _compile(criterion) -> tuple[str, dict[str, Any]]:
    compiled = criterion.compile(dialect=postgresql.dialect())
    return str(compiled), dict(compiled.params)


def _make_source() -> EvidenceSource:
    return EvidenceSource(
        id=uuid.uuid4(),
        case_id=uuid.uuid4(),
        hostname="WKS-042",
        collector="import",
        source_type="endpoint",
        platform="windows",
        package_path="/tmp/evidence.zip",
        status="completed",
    )


def _call(path_suffix: str, params: dict[str, Any]) -> tuple[RecordingDb, Any]:
    source = _make_source()
    db = RecordingDb(source)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: FakeUser()
    try:
        client = TestClient(app)
        response = client.get(
            f"/api/v1/cases/{source.case_id}/sources/{source.id}/{path_suffix}",
            params=params,
        )
    finally:
        app.dependency_overrides.clear()
    return db, response


def _patterns(db: RecordingDb) -> list[str]:
    patterns: list[str] = []
    for criterion in db.criteria:
        _sql, params = _compile(criterion)
        patterns.extend(v for v in params.values() if isinstance(v, str) and "%" in v)
    return patterns


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("plain", "plain"),
        ("100%", r"100\%"),
        ("ntuser_dat", r"ntuser\_dat"),
        ("back\\slash", r"back\\slash"),
        (r"%_\%", r"\%\_\\\%"),
        ("", ""),
    ],
)
def test_escape_like_escapes_wildcards_and_escape_char(raw: str, expected: str):
    assert escape_like(raw) == expected


def test_like_contains_wraps_escaped_value():
    assert like_contains(r"C:\Temp\a_b%") == r"%C:\\Temp\\a\_b\%%"


def test_timeline_filter_escapes_query_wildcards():
    session = Session()
    query = _filtered_timeline_query(
        session,
        uuid.uuid4(),
        start=None,
        end=None,
        event_type=None,
        artifact_type=None,
        q="ntuser_dat 100%",
    )
    sql, params = _compile(query.statement)
    assert "ESCAPE" in sql
    assert r"%ntuser\_dat 100\%%" in params.values()


def test_timeline_browser_filter_escapes_all_json_fields():
    session = Session()
    query = _filtered_timeline_query(
        session,
        uuid.uuid4(),
        start=None,
        end=None,
        event_type=None,
        artifact_type=None,
        q="a_b",
        browser_only=True,
    )
    sql, params = _compile(query.statement)
    escaped = [v for v in params.values() if v == r"%a\_b%"]
    # summary plus url/title/message/host JSON fields.
    assert len(escaped) == 5
    assert sql.count("ESCAPE") >= 5
    # Static browser-scope filters keep their intentional wildcards.
    assert "browser.%" in params.values()


def _mft_query(q: str | None):
    return _filtered_timeline_query(
        Session(),
        uuid.uuid4(),
        start=None,
        end=None,
        event_type=None,
        artifact_type=None,
        q=q,
        mft_only=True,
    )


def test_timeline_mft_filter_searches_full_path_and_summary():
    sql, params = _compile(_mft_query("System32/cmd.exe").statement)
    # Summary keeps its own predicate; the path predicate spans ParentPath + FileName.
    assert r"%System32/cmd.exe%" in params.values()
    assert "ParentPath" in params.values()
    assert "FileName" in params.values()
    assert sql.count("ILIKE") >= 2
    assert "concat" in sql.lower() and "coalesce" in sql.lower()


def test_timeline_mft_filter_normalizes_separators():
    """A backslash-typed path matches rows stored with either separator."""
    _sql, params = _compile(_mft_query(r"System32\cmd.exe").statement)
    patterns = [v for v in params.values() if isinstance(v, str) and v.startswith("%")]
    # Path pattern is normalized to "/"; both sides of the comparison are.
    assert r"%System32/cmd.exe%" in patterns
    assert "\\" in params.values() and "/" in params.values()


def test_timeline_mft_filter_escapes_path_wildcards():
    sql, params = _compile(_mft_query("a_b%").statement)
    assert [v for v in params.values() if v == r"%a\_b\%%"], params
    assert "ESCAPE" in sql


def test_timeline_mft_filter_absent_without_query():
    """mft_only alone keeps the existing scope-only predicate."""
    sql, params = _compile(_mft_query(None).statement)
    assert "ParentPath" not in params.values()
    # Only the static MFT scope wildcards remain.
    assert {v for v in params.values() if isinstance(v, str) and "%" in v} == {
        "%mft%",
        "%/mft/%",
        "%.mft%",
    }
    assert "concat" not in sql.lower()


def test_global_search_escapes_wildcards():
    db, response = _call("search", {"q": "ntuser_dat"})
    assert response.status_code == 200, response.text
    patterns = _patterns(db)
    assert patterns, "expected at least one LIKE pattern"
    assert all(p == r"%ntuser\_dat%" for p in patterns)
    for criterion in db.criteria:
        sql, params = _compile(criterion)
        if any(isinstance(v, str) and v.startswith("%") for v in params.values()):
            assert "ESCAPE" in sql


def test_global_search_percent_only_query_is_literal():
    db, response = _call("search", {"q": "%"})
    assert response.status_code == 200, response.text
    # A bare "%" must not become a match-everything scan of the timeline.
    patterns = _patterns(db)
    assert patterns and set(patterns) == {r"%\%%"}


def test_filesystem_search_escapes_wildcards():
    db, response = _call("filesystem/search", {"q": "a_b%"})
    assert response.status_code == 200, response.text
    assert _patterns(db) == [r"%a\_b\%%"]


def test_entity_search_escapes_wildcards():
    db, response = _call("entities", {"q": "svc_host"})
    assert response.status_code == 200, response.text
    assert _patterns(db) == [r"%svc\_host%"]


class HistogramDbStub:
    """Captures the raw SQL and bind params the histogram route emits."""

    def __init__(self, source: EvidenceSource):
        self.source = source
        self.statements: list[tuple[str, dict[str, Any]]] = []

    def query(self, *models):
        return RecordingQuery([self.source] if models[0] is EvidenceSource else [], [])

    def execute(self, statement, params):
        self.statements.append((str(statement), dict(params)))
        return SimpleNamespace(
            fetchone=lambda: (None, None, None),
            fetchall=lambda: [],
        )


def _histogram(*, q: str, browser_only: bool = False) -> HistogramDbStub:
    source = _make_source()
    db = HistogramDbStub(source)
    stats_router.get_timeline_histogram(
        case_id=source.case_id,
        source_id=source.id,
        start=None,
        end=None,
        event_type=None,
        q=q,
        artifact_type=None,
        sigma_only=False,
        mft_only=False,
        browser_only=browser_only,
        browser_category=None,
        db=db,
    )
    return db


def test_histogram_q_escapes_wildcards_like_event_list():
    db = _histogram(q="ntuser_dat 100%")
    sql, params = db.statements[0]
    assert params["q"] == r"%ntuser\_dat 100\%%"
    assert "summary ILIKE :q ESCAPE" in sql


def test_histogram_browser_q_escapes_all_json_fields():
    db = _histogram(q="a_b", browser_only=True)
    sql, params = db.statements[0]
    assert params["q"] == r"%a\_b%"
    # summary plus url/title/message/host JSON fields.
    assert sql.count("ILIKE :q ESCAPE") == 5
    # Static browser/MFT scope filters keep their intentional wildcards.
    assert "browser.%" in sql


def test_histogram_percent_only_query_is_literal():
    db = _histogram(q="%")
    _sql, params = db.statements[0]
    # A bare "%" must not become a match-everything scan of the timeline.
    assert params["q"] == r"%\%%"
