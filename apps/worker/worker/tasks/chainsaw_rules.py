"""Celery task to refresh Chainsaw rules from GitHub."""

from pathlib import Path

from worker.celery_app import celery_app
from worker.chainsaw.sync import sync_chainsaw_rules_from_github
from worker.chainsaw.sync_meta import write_status


@celery_app.task(name="worker.tasks.chainsaw_rules.refresh_chainsaw_rules", bind=True)
def refresh_chainsaw_rules(self, ref: str | None = None) -> dict[str, object]:
    task_id = self.request.id
    write_status(state="running", task_id=task_id, message="Downloading Chainsaw rules from GitHub")
    try:
        result = sync_chainsaw_rules_from_github(ref=ref)
        write_status(
            state="idle",
            task_id=task_id,
            message=f"Chainsaw rules updated ({result.get('rule_count', 0)} files)",
            rule_count=int(result.get("rule_count", 0)),
            mapping_count=int(result.get("mapping_count", 0)),
            ref=str(result.get("ref", "")),
        )
        return result
    except Exception as exc:
        write_status(state="error", task_id=task_id, message=str(exc)[:500])
        raise
