"""Redis-backed status for Sigma rule sync jobs."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import redis

from worker.config import settings

REDIS_KEY = "corvus:sigma:rules:status"


def _client() -> redis.Redis:
    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


def read_status() -> dict[str, Any]:
    raw = _client().get(REDIS_KEY)
    if not raw:
        return {
            "state": "idle",
            "rule_count": 0,
            "ref": settings.sigma_ref,
            "updated_at": None,
            "message": None,
            "task_id": None,
        }
    data = json.loads(raw)
    if isinstance(data, dict):
        return data
    return {"state": "idle", "rule_count": 0, "ref": settings.sigma_ref}


def write_status(**fields: Any) -> dict[str, Any]:
    current = read_status()
    current.update(fields)
    if "updated_at" not in fields and fields.get("state") in ("ok", "error"):
        current["updated_at"] = datetime.now(UTC).isoformat()
    _client().set(REDIS_KEY, json.dumps(current))
    return current
