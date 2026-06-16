"""Celery tasks for Sigma rule bundle maintenance."""

from __future__ import annotations

from pathlib import Path

from worker.celery_app import celery_app
from worker.config import settings
from worker.sigma.sync import count_rule_files, sync_sigma_rules_from_github
from worker.sigma.sync_meta import write_status


@celery_app.task(name="worker.tasks.sigma_rules.refresh_sigma_rules", bind=True)
def refresh_sigma_rules(self, ref: str | None = None) -> dict[str, object]:
    task_id = self.request.id
    try:
        result = sync_sigma_rules_from_github(ref=ref, task_id=task_id)
        count = int(result["rule_count"])
        write_status(
            state="ok",
            rule_count=count,
            ref=str(result["ref"]),
            message=f"Installed {count:,} Sigma rule files from GitHub.",
            task_id=task_id,
        )
        return result
    except Exception as exc:
        count = count_rule_files(Path(settings.sigma_rules_root))
        write_status(
            state="error",
            rule_count=count,
            message=str(exc)[:2000],
            task_id=task_id,
        )
        raise
