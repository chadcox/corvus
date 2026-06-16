from datetime import timedelta

from celery import Celery
from celery.signals import worker_ready

from worker.config import settings
from worker.tasks.recovery import reconcile_orphaned_ingest_jobs

celery_app = Celery("forensicflow", broker=settings.redis_url, backend=settings.redis_url)

_beat: dict = {}
if settings.sigma_refresh_interval_hours > 0:
    _beat["sigma-refresh-rules"] = {
        "task": "worker.tasks.sigma_rules.refresh_sigma_rules",
        "schedule": timedelta(hours=settings.sigma_refresh_interval_hours),
        "options": {"queue": "ingest"},
    }

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    include=[
        "worker.tasks.ingest",
        "worker.tasks.sigma_rules",
        "worker.tasks.chainsaw_rules",
        "worker.tasks.yara_rules",
        "worker.tasks.hash_evidence",
        "worker.tasks.yara_scan",
    ],
    beat_schedule=_beat,
)


@worker_ready.connect
def _reconcile_orphaned_jobs_on_start(**kwargs) -> None:
    reconcile_orphaned_ingest_jobs()
