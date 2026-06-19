"""Read Sigma rule sync status from Redis (written by worker tasks)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import redis

from app.config import settings

REDIS_KEY = "corvus:sigma:rules:status"


def _count_rules(rules_root: str) -> int:
    root = Path(rules_root)
    if not root.is_dir():
        return 0
    return sum(1 for _ in root.rglob("*.yml")) + sum(1 for _ in root.rglob("*.yaml"))


def get_sigma_rules_status() -> dict[str, Any]:
    ref = settings.sigma_ref
    rules_root = settings.sigma_rules_root
    default_count = _count_rules(rules_root)

    try:
        client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        raw = client.get(REDIS_KEY)
    except redis.RedisError:
        return {
            "state": "idle",
            "rule_count": default_count,
            "ref": ref,
            "updated_at": None,
            "message": None,
            "task_id": None,
            "refresh_interval_hours": settings.sigma_refresh_interval_hours,
        }

    if not raw:
        return {
            "state": "idle",
            "rule_count": default_count,
            "ref": ref,
            "updated_at": None,
            "message": None,
            "task_id": None,
            "refresh_interval_hours": settings.sigma_refresh_interval_hours,
        }

    data = json.loads(raw)
    if not isinstance(data, dict):
        data = {}
    if not data.get("rule_count") and default_count:
        data["rule_count"] = default_count
    data.setdefault("ref", ref)
    data.setdefault("state", "idle")
    data["refresh_interval_hours"] = settings.sigma_refresh_interval_hours
    return data
