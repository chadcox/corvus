"""Redis status for Chainsaw rule sync (read by API)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import redis

from worker.config import settings

REDIS_KEY = "corvus:chainsaw:rules:status"


def write_status(**fields: Any) -> None:
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        **fields,
    }
    try:
        client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        client.set(REDIS_KEY, json.dumps(payload))
    except redis.RedisError:
        pass
