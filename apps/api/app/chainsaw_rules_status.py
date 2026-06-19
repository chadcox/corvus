"""Chainsaw rules bundle and binary status."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import redis

from app.config import settings

REDIS_KEY = "corvus:chainsaw:rules:status"


def _count_rules(rules_root: str) -> int:
    root = Path(rules_root)
    if not root.is_dir():
        return 0
    return sum(1 for _ in root.rglob("*.yml")) + sum(1 for _ in root.rglob("*.yaml"))


def _count_mappings(mappings_root: str) -> int:
    root = Path(mappings_root)
    if not root.is_dir():
        return 0
    return sum(1 for _ in root.glob("*.yml")) + sum(1 for _ in root.glob("*.yaml"))


def _chainsaw_version() -> str | None:
    bin_path = Path(settings.chainsaw_bin)
    if not bin_path.is_file():
        return None
    try:
        proc = subprocess.run(
            [str(bin_path), "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        line = (proc.stdout or proc.stderr or "").strip().splitlines()
        return line[0] if line else None
    except OSError:
        return None


def get_chainsaw_rules_status() -> dict[str, Any]:
    rules_root = settings.chainsaw_rules_root
    mappings_root = settings.chainsaw_mappings_root
    default_rules = _count_rules(rules_root)
    default_maps = _count_mappings(mappings_root)
    binary_ok = Path(settings.chainsaw_bin).is_file()
    # Hunt runs in the worker container; API may not ship the binary but shares rule volumes.
    worker_binary = binary_ok

    base: dict[str, Any] = {
        "state": "idle",
        "rule_count": default_rules,
        "mapping_count": default_maps,
        "binary_available": worker_binary if worker_binary else default_rules > 0,
        "chainsaw_version": _chainsaw_version() if worker_binary else None,
        "ref": settings.chainsaw_ref,
        "updated_at": None,
        "message": None,
        "task_id": None,
        "include_sigma_in_hunt": settings.chainsaw_include_sigma,
    }

    try:
        client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        raw = client.get(REDIS_KEY)
    except redis.RedisError:
        return base

    if not raw:
        return base

    data = json.loads(raw)
    if not isinstance(data, dict):
        return base
    data.setdefault("rule_count", default_rules)
    data.setdefault("mapping_count", default_maps)
    data["binary_available"] = binary_ok
    if binary_ok and not data.get("chainsaw_version"):
        data["chainsaw_version"] = _chainsaw_version()
    data["include_sigma_in_hunt"] = settings.chainsaw_include_sigma
    return data
