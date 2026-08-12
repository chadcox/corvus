from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.auth.service import get_current_user
from app.config import Settings, settings
from app.database import get_db
from app.main import app
from app.models import EvidenceSource, TimelineEvent
from app.routers.timeline import EXPORT_MAX


@dataclass
class FakeUser:
    id: str = "test-user"
    username: str = "analyst"
    role: str = "analyst"
    is_active: bool = True


class FakeQuery:
    """Query stub that honors ``limit`` so cap behavior can be exercised."""

    def __init__(self, rows: list[Any], row_limit: int | None = None):
        self.rows = rows
        self.row_limit = row_limit

    def filter(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def with_entities(self, *_args, **_kwargs):
        return self

    def limit(self, value=None, *_args, **_kwargs):
        return FakeQuery(self.rows, row_limit=value)

    def scalar(self):
        """Stand in for the unlimited ``func.count()`` query."""
        return len(self.rows)

    def first(self):
        return self.rows[0] if self.rows else None

    def yield_per(self, *_args, **_kwargs):
        rows = self.rows if self.row_limit is None else self.rows[: self.row_limit]
        return iter(rows)


class FakeDb:
    def __init__(self, source: EvidenceSource, events: list[Any]):
        self.source = source
        self.events = events

    def query(self, *models):
        if models[0] is EvidenceSource:
            return FakeQuery([self.source])
        if models[0] is TimelineEvent:
            return FakeQuery(self.events)
        return FakeQuery([])


def _override_auth():
    return FakeUser()


def _event(index: int = 0) -> TimelineEvent:
    return TimelineEvent(
        id=uuid.uuid4(),
        timestamp_utc=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC) + timedelta(seconds=index),
        event_type="process.create",
        summary="powershell.exe launched",
        artifact_type="evtx",
        original_source="Security.evtx",
    )


def _get(path_suffix: str, hostname: str | None, events: list[Any]):
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
    app.dependency_overrides[get_current_user] = _override_auth
    try:
        client = TestClient(app)
        response = client.get(
            f"/api/v1/cases/{case_id}/sources/{source_id}/timeline{path_suffix}"
        )
    finally:
        app.dependency_overrides.clear()
    return response


def _export(hostname: str | None, event_count: int = 1):
    return _get("/export", hostname, [_event(index) for index in range(event_count)])


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
    """Shrink the export cap so truncation is testable without 50k rows."""

    def _set(rows: int):
        monkeypatch.setattr(settings, "timeline_export_max_rows", rows)

    return _set


def _data_rows(response) -> list[str]:
    lines = response.text.splitlines()
    assert lines[0].startswith("timestamp_utc") or lines[0].startswith('"timestamp_utc"')
    return lines[1:]


def test_export_default_cap_is_fifty_thousand():
    """The shipped default must not change; only its visibility does."""
    assert Settings.model_fields["timeline_export_max_rows"].default == 50_000
    assert EXPORT_MAX == 50_000


def test_export_below_cap_reports_not_truncated(export_cap):
    export_cap(5)
    response = _export("WKS-042", event_count=3)

    assert response.status_code == 200, response.text
    assert response.headers["x-corvus-export-truncated"] == "false"
    assert response.headers["x-corvus-export-row-limit"] == "5"
    assert response.headers["x-corvus-export-row-count"] == "3"
    assert response.headers["x-corvus-export-total-matches"] == "3"
    assert len(_data_rows(response)) == 3


def test_export_exactly_at_cap_is_not_truncated(export_cap):
    export_cap(3)
    response = _export("WKS-042", event_count=3)

    assert response.status_code == 200, response.text
    assert response.headers["x-corvus-export-truncated"] == "false"
    assert response.headers["x-corvus-export-row-count"] == "3"
    assert response.headers["x-corvus-export-total-matches"] == "3"
    assert len(_data_rows(response)) == 3


def test_export_above_cap_reports_truncation(export_cap):
    export_cap(3)
    response = _export("WKS-042", event_count=7)

    assert response.status_code == 200, response.text
    assert response.headers["x-corvus-export-truncated"] == "true"
    assert response.headers["x-corvus-export-row-limit"] == "3"
    assert response.headers["x-corvus-export-row-count"] == "3"
    assert response.headers["x-corvus-export-total-matches"] == "7"
    assert len(_data_rows(response)) == 3


def test_truncated_export_body_is_byte_identical_to_untruncated_prefix(export_cap):
    """Truncation must stay in the headers: no warning row in the CSV."""
    export_cap(3)
    truncated = _export("WKS-042", event_count=7)

    export_cap(10)
    complete = _export("WKS-042", event_count=3)

    assert truncated.headers["x-corvus-export-truncated"] == "true"
    assert complete.headers["x-corvus-export-truncated"] == "false"
    assert truncated.content == complete.content
    assert b"truncat" not in truncated.content.lower()


def test_truncation_headers_are_exposed_to_browser_clients():
    """The web app is cross-origin, so CORS must expose the export headers."""
    exposed = {
        value.strip().lower()
        for value in _export("WKS-042").headers["access-control-expose-headers"].split(",")
    }
    assert {
        "content-disposition",
        "x-corvus-export-truncated",
        "x-corvus-export-row-limit",
        "x-corvus-export-row-count",
        "x-corvus-export-total-matches",
    } <= exposed


@pytest.mark.parametrize("configured", [0, -1])
def test_non_positive_cap_falls_back_to_default(export_cap, configured: int):
    export_cap(configured)
    response = _export("WKS-042")
    assert response.headers["x-corvus-export-row-limit"] == str(EXPORT_MAX)


def test_count_endpoint_reports_export_row_limit(export_cap):
    export_cap(7)
    response = _get("/count", "WKS-042", [_event()])

    assert response.status_code == 200, response.text
    assert response.json() == {"count": 1, "export_row_limit": 7}
