"""Read YARA rule sync status from Redis (written by worker task)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import redis

from app.config import settings

REDIS_KEY = "corvus:yara:rules:status"


def _count_rules(rules_root: str) -> int:
    root = Path(rules_root)
    if not root.is_dir():
        return 0
    return sum(1 for _ in root.rglob("*.yar")) + sum(1 for _ in root.rglob("*.yara"))


def get_yara_rules_status() -> dict[str, Any]:
    default_count = _count_rules("/opt/yara/rules")
    try:
        client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        raw = client.get(REDIS_KEY)
    except redis.RedisError:
        return {
            "state": "idle",
            "rule_count": default_count,
            "updated_at": None,
            "message": None,
            "task_id": None,
        }

    if not raw:
        return {
            "state": "idle",
            "rule_count": default_count,
            "updated_at": None,
            "message": None,
            "task_id": None,
        }

    data = json.loads(raw)
    if not isinstance(data, dict):
        data = {}
    if not data.get("rule_count") and default_count:
        data["rule_count"] = default_count
    data.setdefault("state", "idle")
    return data
