"""Which backend serves /search, and what the caller sees for each.

Companion to test_search_like_escaping.py. That module pins SEARCH_BACKEND=postgres so it
can inspect SQL LIKE patterns; this module owns the branch itself. Without these tests a
change that makes `opensearch_global_search` always return a result would leave the SQL
escaping suite green while silently retiring the code it covers.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.auth.service import get_current_user
from app.database import get_db
from app.main import app
from app.models import EvidenceSource
from app.routers import search as search_router


@dataclass
class FakeUser:
    id: str = "test-user"
    username: str = "analyst"
    role: str = "analyst"
    is_active: bool = True


class StubQuery:
    def __init__(self, rows: list[Any]):
        self.rows = rows

    def filter(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return list(self.rows)


class StubDb:
    """Serves the EvidenceSource lookup; every other model resolves to no rows."""

    def __init__(self, source: EvidenceSource):
        self.source = source
        self.sql_models: list[str] = []

    def query(self, *models):
        if models[0] is EvidenceSource:
            return StubQuery([self.source])
        self.sql_models.append(getattr(models[0], "__name__", str(models[0])))
        return StubQuery([])


def _make_source(status: str = "completed") -> EvidenceSource:
    return EvidenceSource(
        id=uuid.uuid4(),
        case_id=uuid.uuid4(),
        hostname="WKS-042",
        collector="import",
        source_type="endpoint",
        platform="windows",
        package_path="/tmp/evidence.zip",
        status=status,
    )


def _call(db: StubDb, q: str = "ntuser_dat"):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: FakeUser()
    try:
        client = TestClient(app)
        return client.get(
            f"/api/v1/cases/{db.source.case_id}/sources/{db.source.id}/search",
            params={"q": q},
        )
    finally:
        app.dependency_overrides.clear()


def test_opensearch_result_short_circuits_sql(monkeypatch: pytest.MonkeyPatch):
    db = StubDb(_make_source())
    served = {
        "query": "ntuser_dat",
        "timeline": [],
        "filesystem": [],
        "entities": [],
        "total": 7,
    }
    monkeypatch.setattr(search_router, "opensearch_global_search", lambda *a, **k: served)

    response = _call(db)

    assert response.status_code == 200, response.text
    assert response.json()["total"] == 7
    assert db.sql_models == [], "SQL fallback must not run when OpenSearch answers"


def test_none_from_opensearch_falls_back_to_sql(monkeypatch: pytest.MonkeyPatch):
    db = StubDb(_make_source())
    monkeypatch.setattr(search_router, "opensearch_global_search", lambda *a, **k: None)

    response = _call(db)

    assert response.status_code == 200, response.text
    assert response.json()["total"] == 0
    assert db.sql_models, "SQL fallback must run when OpenSearch is unavailable"


def test_search_rejected_while_source_still_ingesting(monkeypatch: pytest.MonkeyPatch):
    db = StubDb(_make_source(status="running"))
    monkeypatch.setattr(search_router, "opensearch_global_search", lambda *a, **k: None)

    response = _call(db)

    assert response.status_code == 409
    assert db.sql_models == []
