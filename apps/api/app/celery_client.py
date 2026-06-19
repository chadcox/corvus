from celery import Celery

from app.config import settings

celery_app = Celery("corvus", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_routes={"worker.tasks.ingest.*": {"queue": "ingest"}},
)
