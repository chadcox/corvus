"""Celery task for YARA rule bundle refresh."""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import redis

from worker.celery_app import celery_app
from worker.config import settings

REDIS_KEY = "forensicflow:yara:rules:status"


def _count_rules(rules_root: Path) -> int:
    if not rules_root.is_dir():
        return 0
    return sum(1 for _ in rules_root.rglob("*.yar")) + sum(1 for _ in rules_root.rglob("*.yara"))


def _write_status(*, state: str, rule_count: int, message: str | None = None, task_id: str | None = None) -> None:
    payload = {
        "state": state,
        "rule_count": rule_count,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "message": message,
        "task_id": task_id,
    }
    try:
        redis.Redis.from_url(settings.redis_url, decode_responses=True).set(REDIS_KEY, json.dumps(payload))
    except redis.RedisError:
        pass


@celery_app.task(name="worker.tasks.yara_rules.refresh_yara_rules", bind=True)
def refresh_yara_rules(self) -> dict[str, object]:
    task_id = self.request.id
    rules_root = Path(settings.yara_rules_root)
    bundled_root = Path(settings.yara_rules_bundled)
    bundled_yara = bundled_root / "yara"

    _write_status(state="running", rule_count=_count_rules(rules_root), message="Refreshing YARA rules", task_id=task_id)

    try:
        subprocess.run(
            ["/usr/local/bin/fetch-yara-rules.sh", str(bundled_root)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        rules_root.mkdir(parents=True, exist_ok=True)
        if bundled_yara.is_dir():
            for item in bundled_yara.iterdir():
                dest = rules_root / item.name
                if item.is_dir():
                    if dest.exists():
                        shutil.rmtree(dest)
                    shutil.copytree(item, dest)
                else:
                    shutil.copy2(item, dest)

        count = _count_rules(rules_root)
        _write_status(state="ok", rule_count=count, message=f"Installed {count:,} YARA rules", task_id=task_id)
        return {"rule_count": count}
    except Exception as exc:
        count = _count_rules(rules_root)
        _write_status(state="error", rule_count=count, message=str(exc)[:2000], task_id=task_id)
        raise
