from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.auth.service import get_current_user
from app.database import get_db
from app.main import app
from app.models import EvidenceSource, TimelineEvent
from app.routers import timeline as timeline_router
from app.routers.timeline import EXPORT_MAX


@dataclass
class FakeUser:
    id: str = "test-user"
    username: str = "analyst"
    role: str = "analyst"
    is_active: bool = True


@dataclass
class QueryLog:
    """Records how the route drove the ORM so query shape is assertable."""

    all_calls: int = 0
    scalar_calls: int = 0
    yield_per_calls: int = 0
    limits: list[int | None] = field(default_factory=list)
    count_entities: int = 0


class FakeQuery:
    """Query stub that honors ``limit`` so cap behavior can be exercised."""

    def __init__(self, rows: list[Any], log: QueryLog, row_limit: int | None = None):
        self.rows = rows
        self.log = log
        self.row_limit = row_limit

    def filter(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def with_entities(self, *args, **_kwargs):
        # func.count() renders as "count(*)"; anything of that shape means the
        # route asked the database to tally the filter separately.
        if any("count(" in str(arg) for arg in args):
            self.log.count_entities += 1
        return self

    def offset(self, *_args, **_kwargs):
        return self

    def limit(self, value=None, *_args, **_kwargs):
        self.log.limits.append(value)
        return FakeQuery(self.rows, self.log, row_limit=value)

    def _rows(self) -> list[Any]:
        return self.rows if self.row_limit is None else self.rows[: self.row_limit]

    def all(self):
        self.log.all_calls += 1
        return self._rows()

    def scalar(self):
        """Stand in for a ``func.count()`` query the export must not issue."""
        self.log.scalar_calls += 1
        return len(self.rows)

    def first(self):
        return self.rows[0] if self.rows else None

    def yield_per(self, *_args, **_kwargs):
        self.log.yield_per_calls += 1
        return iter(self._rows())


class FakeDb:
    def __init__(self, source: EvidenceSource, events: list[Any]):
        self.source = source
        self.events = events
        self.event_log = QueryLog()
        self.source_log = QueryLog()

    def query(self, *models):
        if models[0] is EvidenceSource:
            return FakeQuery([self.source], self.source_log)
        if models[0] is TimelineEvent:
            return FakeQuery(self.events, self.event_log)
        return FakeQuery([], self.event_log)


def _override_auth():
    return FakeUser()


def _event(index: int = 0) -> TimelineEvent:
    return TimelineEvent(
        id=uuid.uuid4(),
        timestamp_utc=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC) + timedelta(seconds=index),
        event_type="process.create",
        summary=f"powershell.exe launched {index}",
        artifact_type="evtx",
        original_source="Security.evtx",
    )


def _call(
    path_suffix: str,
    hostname: str | None,
    events: list[Any],
    *,
    authenticated: bool = True,
    headers: dict[str, str] | None = None,
):
    case_id = uuid.uuid4()
    source_id = uuid.uuid4()
    source = EvidenceSource(
        id=source_id,
        case_id=case_id,
        hostname=hostname,
        collector="import",
        source_type="endpoint",
        platform="windows",
        package_path="/tmp/evidence.zip",
        status="completed",
    )
    for event in events:
        event.evidence_source_id = source_id
    db = FakeDb(source, events)

    app.dependency_overrides[get_db] = lambda: db
    if authenticated:
        app.dependency_overrides[get_current_user] = _override_auth
    try:
        client = TestClient(app)
        response = client.get(
            f"/api/v1/cases/{case_id}/sources/{source_id}/timeline{path_suffix}",
            headers=headers,
        )
    finally:
        app.dependency_overrides.clear()
    return response, db


def _get(path_suffix: str, hostname: str | None, events: list[Any]):
    response, _ = _call(path_suffix, hostname, events)
    return response


def _export(hostname: str | None, event_count: int = 1, **kwargs):
    response, _ = _call(
        "/export", hostname, [_event(index) for index in range(event_count)], **kwargs
    )
    return response


def _export_with_db(hostname: str | None, event_count: int = 1):
    return _call("/export", hostname, [_event(index) for index in range(event_count)])


def test_export_uses_plain_hostname_filename():
    response = _export("WKS-042")
    assert response.status_code == 200, response.text
    assert response.headers["content-disposition"] == 'attachment; filename="timeline-WKS-042.csv"'
    assert "powershell.exe launched" in response.text


@pytest.mark.parametrize(
    ("hostname", "expected"),
    [
        ("host name", "timeline-host_name.csv"),
        ("../../etc/passwd", "timeline-.._.._etc_passwd.csv"),
        ('evil"; rm -rf /', "timeline-evil___rm_-rf__.csv"),
        ("host\r\nX-Injected: 1", "timeline-host__X-Injected__1.csv"),
        ("хост-ワークステーション", "timeline-____-_________.csv"),
        (None, "timeline-host.csv"),
    ],
)
def test_export_sanitizes_hostile_hostname_filename(hostname: str | None, expected: str):
    response = _export(hostname)
    assert response.status_code == 200, response.text
    disposition = response.headers["content-disposition"]
    assert disposition == f'attachment; filename="{expected}"'
    # Header must stay a single latin-1 encodable line with no path separators.
    disposition.encode("latin-1")
    assert "\r" not in disposition and "\n" not in disposition
    assert "/" not in expected and "\\" not in expected


@pytest.fixture
def export_cap(monkeypatch):
    """Shrink the export cap so truncation is testable without 50k rows.

    The cap is a fixed module constant, not a setting, so the constant itself is
    what the tests patch.
    """

    def _set(rows: int):
        monkeypatch.setattr(timeline_router, "EXPORT_MAX", rows)

    return _set


def _data_rows(response) -> list[str]:
    lines = response.text.splitlines()
    assert lines[0].startswith("timestamp_utc") or lines[0].startswith('"timestamp_utc"')
    return lines[1:]


def test_export_cap_is_a_fixed_fifty_thousand_row_constant():
    """The cap stays a module constant; there is no configuration knob for it."""
    from app.config import Settings

    assert EXPORT_MAX == 50_000
    assert "timeline_export_max_rows" not in Settings.model_fields
    assert not hasattr(timeline_router, "export_row_limit")


def test_export_below_cap_reports_not_truncated(export_cap):
    export_cap(5)
    response = _export("WKS-042", event_count=3)

    assert response.status_code == 200, response.text
    assert response.headers["x-corvus-export-truncated"] == "false"
    assert response.headers["x-corvus-export-row-limit"] == "5"
    assert response.headers["x-corvus-export-row-count"] == "3"
    assert len(_data_rows(response)) == 3


def test_export_exactly_at_cap_is_not_truncated(export_cap):
    """The boundary case: cap rows exactly is complete, not partial."""
    export_cap(3)
    response = _export("WKS-042", event_count=3)

    assert response.status_code == 200, response.text
    assert response.headers["x-corvus-export-truncated"] == "false"
    assert response.headers["x-corvus-export-row-count"] == "3"
    assert len(_data_rows(response)) == 3


def test_export_one_row_over_cap_reports_truncation(export_cap):
    """One match past the cap must flip the flag, not round down to complete."""
    export_cap(3)
    response = _export("WKS-042", event_count=4)

    assert response.status_code == 200, response.text
    assert response.headers["x-corvus-export-truncated"] == "true"
    assert response.headers["x-corvus-export-row-count"] == "3"
    assert len(_data_rows(response)) == 3


def test_export_above_cap_reports_truncation(export_cap):
    export_cap(3)
    response = _export("WKS-042", event_count=7)

    assert response.status_code == 200, response.text
    assert response.headers["x-corvus-export-truncated"] == "true"
    assert response.headers["x-corvus-export-row-limit"] == "3"
    assert response.headers["x-corvus-export-row-count"] == "3"
    assert len(_data_rows(response)) == 3


@pytest.mark.parametrize("event_count", [0, 1, 2, 3, 4, 9])
def test_row_count_header_always_equals_body_row_count(export_cap, event_count: int):
    """Headers and bytes come from one list, so they cannot disagree."""
    export_cap(3)
    response = _export("WKS-042", event_count=event_count)

    body_rows = _data_rows(response)
    assert response.headers["x-corvus-export-row-count"] == str(len(body_rows))
    expected_truncated = "true" if event_count > 3 else "false"
    assert response.headers["x-corvus-export-truncated"] == expected_truncated
    assert len(body_rows) == min(event_count, 3)


def test_export_issues_exactly_one_row_query_and_no_count(export_cap):
    """No COUNT and no second probe: one materialized query drives everything."""
    export_cap(3)
    response, db = _export_with_db("WKS-042", event_count=7)

    assert response.status_code == 200, response.text
    assert db.event_log.all_calls == 1
    assert db.event_log.scalar_calls == 0
    assert db.event_log.count_entities == 0
    assert db.event_log.yield_per_calls == 0


def test_export_fetches_one_row_past_the_cap_to_detect_truncation(export_cap):
    """Truncation is detected with a bounded cap+1 fetch, not an unbounded one."""
    export_cap(3)
    _, db = _export_with_db("WKS-042", event_count=7)

    assert db.event_log.limits == [4]


def test_export_limit_is_bounded_by_the_module_constant():
    """Unpatched, the export never asks the database for more than cap+1 rows."""
    _, db = _export_with_db("WKS-042", event_count=2)

    assert db.event_log.limits == [EXPORT_MAX + 1]


def test_truncated_export_body_is_byte_identical_to_untruncated_prefix(export_cap):
    """Truncation must stay in the headers: no warning row in the CSV."""
    export_cap(3)
    truncated = _export("WKS-042", event_count=7)

    export_cap(10)
    complete = _export("WKS-042", event_count=3)

    assert truncated.headers["x-corvus-export-truncated"] == "true"
    assert complete.headers["x-corvus-export-truncated"] == "false"
    assert truncated.content == complete.content


@pytest.mark.parametrize("event_count", [3, 7])
def test_export_body_carries_only_evidence_rows(export_cap, event_count: int):
    """A capped export must not smuggle a note, banner, or sentinel row in."""
    export_cap(3)
    response = _export("WKS-042", event_count=event_count)

    body = response.content.lower()
    for contaminant in (b"truncat", b"partial", b"warning", b"omitted", b"corvus"):
        assert contaminant not in body

    # Every data row is a real event: five columns, ISO timestamp first.
    for row in _data_rows(response):
        assert row.count(",") == 4
        assert row.lstrip('"').startswith("2026-01-02T03:04:")
        assert "powershell.exe launched" in row


def test_export_headers_are_exactly_the_disclosure_set(export_cap):
    """Total-Matches was removed; only the three disclosure headers ship."""
    export_cap(3)
    response = _export("WKS-042", event_count=7)

    corvus_headers = {
        name.lower() for name in response.headers if name.lower().startswith("x-corvus-")
    }
    assert corvus_headers == {
        "x-corvus-export-truncated",
        "x-corvus-export-row-limit",
        "x-corvus-export-row-count",
    }
    assert "x-corvus-export-total-matches" not in response.headers


def test_truncation_headers_are_exposed_to_browser_clients():
    """The web app is cross-origin, so CORS must expose the export headers."""
    exposed = {
        value.strip().lower()
        for value in _export("WKS-042").headers["access-control-expose-headers"].split(",")
    }
    assert exposed == {
        "content-disposition",
        "x-corvus-export-truncated",
        "x-corvus-export-row-limit",
        "x-corvus-export-row-count",
    }


def test_expose_headers_survive_the_cors_middleware():
    """The header is set per-route, so assert the middleware does not drop it."""
    response = _export("WKS-042", headers={"Origin": "http://localhost:5173"})

    assert response.status_code == 200, response.text
    # Guard against a vacuous assertion: the middleware must have engaged.
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    exposed = {
        value.strip().lower()
        for value in response.headers["access-control-expose-headers"].split(",")
    }
    assert "x-corvus-export-truncated" in exposed
    assert "content-disposition" in exposed


def test_count_endpoint_response_shape_is_unchanged():
    """The count endpoint carries no export metadata; the export headers do."""
    response = _get("/count", "WKS-042", [_event()])

    assert response.status_code == 200, response.text
    assert response.json() == {"count": 1}


def test_export_requires_authentication():
    """The download must not be reachable without a bearer token."""
    response = _export("WKS-042", authenticated=False)

    assert response.status_code == 401, response.text
    assert "x-corvus-export-truncated" not in response.headers
