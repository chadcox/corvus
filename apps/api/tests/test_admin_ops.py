from __future__ import annotations

from pathlib import Path

from app.services import admin_ops


class FakeRedis:
    def __init__(self):
        self.values = {
            "auth:attempts:ip-user:1:abc": "2",
            "auth:attempts:user:abc": "3",
            "auth:lock:1:abc": "1",
        }

    def scan_iter(self, match: str, count: int = 200):
        _ = count
        if match == "auth:attempts:*":
            for key in self.values:
                if key.startswith("auth:attempts:"):
                    yield key
        elif match == "auth:lock:*":
            for key in self.values:
                if key.startswith("auth:lock:"):
                    yield key

    def get(self, key: str):
        return self.values.get(key)


class FailRedisFactory:
    @staticmethod
    def from_url(*_args, **_kwargs):
        raise admin_ops.redis.RedisError("boom")


def test_auth_security_snapshot_counts(monkeypatch):
    monkeypatch.setattr(admin_ops.redis.Redis, "from_url", lambda *_args, **_kwargs: FakeRedis())
    monkeypatch.setattr(admin_ops, "recent_revocation_failures", lambda: 2)
    snapshot = admin_ops.auth_security_snapshot()
    assert snapshot.redis_available is True
    assert snapshot.failed_logins_5m == 5
    assert snapshot.active_lockouts == 1
    assert snapshot.revocation_redis_available is True
    assert snapshot.revocation_failures_5m == 2


def test_auth_security_snapshot_redis_unavailable(monkeypatch):
    monkeypatch.setattr(admin_ops.redis, "Redis", FailRedisFactory)
    monkeypatch.setattr(admin_ops, "recent_revocation_failures", lambda: 4)
    snapshot = admin_ops.auth_security_snapshot()
    assert snapshot.redis_available is False
    assert snapshot.revocation_redis_available is False
    assert snapshot.revocation_failures_5m == 4
    assert snapshot.error == "redis_error:RedisError"


def test_disk_usage_for_path_uses_cache(monkeypatch, tmp_path: Path):
    target = tmp_path / "evidence"
    target.mkdir()
    sample = target / "a.bin"
    sample.write_bytes(b"abc")

    monkeypatch.setattr(admin_ops.settings, "admin_disk_usage_cache_seconds", 30)
    admin_ops._DISK_USAGE_CACHE.clear()
    first = admin_ops.disk_usage_for_path(str(target))

    sample.write_bytes(b"abc123456")
    second = admin_ops.disk_usage_for_path(str(target))
    assert first.used_bytes == second.used_bytes

    monkeypatch.setattr(admin_ops.settings, "admin_disk_usage_cache_seconds", 0)
    third = admin_ops.disk_usage_for_path(str(target))
    assert third.used_bytes > second.used_bytes


def test_build_admin_overview_includes_search_observability(monkeypatch):
    monkeypatch.setattr(
        admin_ops,
        "search_metrics_snapshot",
        lambda: {
            "window_seconds": 300,
            "total_queries": 4,
            "opensearch_hits": 1,
            "fallback_hits": 3,
            "fallback_short_queries": 2,
            "fallback_avg_ms": 12.5,
        },
    )
    monkeypatch.setattr(
        admin_ops,
        "get_sigma_rules_status",
        lambda: {
            "state": "idle",
            "rule_count": 0,
            "ref": "master",
            "updated_at": None,
            "message": None,
            "task_id": None,
            "refresh_interval_hours": 0.0,
        },
    )
    monkeypatch.setattr(admin_ops, "readiness_payload", lambda: {"ok": True})
    monkeypatch.setattr(admin_ops, "table_counts", lambda _db: admin_ops.AdminTableCounts(**{k: 0 for k in (
        "cases",
        "evidence_sources",
        "ingest_jobs",
        "timeline_events",
        "filesystem_nodes",
        "entities",
        "relations",
        "sigma_detections",
    )}))
    monkeypatch.setattr(admin_ops, "jobs_by_status", lambda _db: {})
    monkeypatch.setattr(admin_ops, "evidence_by_status", lambda _db: {})
    monkeypatch.setattr(admin_ops, "disk_usage_for_path", lambda _path: admin_ops.AdminDiskUsage(path="/tmp"))
    monkeypatch.setattr(admin_ops, "auth_security_snapshot", lambda: admin_ops.AdminAuthSecurityRead())

    overview = admin_ops.build_admin_overview(db=None)  # type: ignore[arg-type]
    assert overview.search_observability.total_queries == 4
    assert overview.search_observability.fallback_hits == 3
