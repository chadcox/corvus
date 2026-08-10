from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.auth.service import get_current_user
from app.database import get_db
from app.main import app
from app.models import EvidenceSource, TimelineEvent


@dataclass
class FakeUser:
    id: str = "test-user"
    username: str = "analyst"
    role: str = "analyst"
    is_active: bool = True


class FakeQuery:
    def __init__(self, rows: list[Any]):
        self.rows = rows

    def filter(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def with_entities(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def yield_per(self, *_args, **_kwargs):
        return iter(self.rows)


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


def _export(hostname: str | None):
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
    event = TimelineEvent(
        id=uuid.uuid4(),
        evidence_source_id=source_id,
        timestamp_utc=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
        event_type="process.create",
        summary="powershell.exe launched",
        artifact_type="evtx",
        original_source="Security.evtx",
    )
    db = FakeDb(source, [event])

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = _override_auth
    try:
        client = TestClient(app)
        response = client.get(f"/api/v1/cases/{case_id}/sources/{source_id}/timeline/export")
    finally:
        app.dependency_overrides.clear()
    return response


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
