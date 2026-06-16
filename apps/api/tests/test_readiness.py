from __future__ import annotations

import sys
import types

from app.services import readiness


class _Conn:
    def execute(self, *_args, **_kwargs):
        return None


class _ConnCtx:
    def __enter__(self):
        return _Conn()

    def __exit__(self, exc_type, exc, tb):
        _ = (exc_type, exc, tb)
        return False


class _Engine:
    def connect(self):
        return _ConnCtx()


class _RedisClient:
    def ping(self):
        return True


def test_readiness_includes_alembic_revision(monkeypatch):
    monkeypatch.setattr(readiness, "engine", _Engine())
    monkeypatch.setattr(readiness, "current_db_revision", lambda: "20260601_0004")
    monkeypatch.setattr(readiness.celery_app.control, "ping", lambda timeout=1.0: [{"worker": "ok"}])
    monkeypatch.setattr(readiness, "opensearch_ping", lambda: True)

    fake_redis = types.SimpleNamespace(from_url=lambda *args, **kwargs: _RedisClient())
    monkeypatch.setitem(sys.modules, "redis", fake_redis)

    payload = readiness.readiness_payload()

    assert payload["status"] in {"ready", "degraded"}
    assert payload["alembic_revision"] == "20260601_0004"
