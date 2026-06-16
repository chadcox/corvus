"""Dependency readiness checks shared by /health/ready and admin overview."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from app.celery_client import celery_app
from app.config import settings
from app.database import current_db_revision, engine
from app.services.opensearch_service import ping as opensearch_ping


def readiness_payload() -> dict[str, Any]:
    checks: dict[str, str] = {}

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as exc:
        checks["postgres"] = f"error: {exc.__class__.__name__}"

    try:
        import redis

        client = redis.from_url(settings.redis_url, socket_connect_timeout=2)
        client.ping()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {exc.__class__.__name__}"

    try:
        replies = celery_app.control.ping(timeout=1.0)
        if replies:
            checks["celery"] = "ok"
        else:
            checks["celery"] = "no workers"
    except Exception as exc:
        checks["celery"] = f"error: {exc.__class__.__name__}"

    if settings.search_backend.lower() == "opensearch":
        try:
            checks["opensearch"] = "ok" if opensearch_ping() else "unavailable"
        except Exception as exc:
            checks["opensearch"] = f"error: {exc.__class__.__name__}"

    failed = [k for k, v in checks.items() if k in ("postgres", "redis") and v.startswith("error")]
    celery_bad = checks.get("celery") in ("no workers",) or str(checks.get("celery", "")).startswith(
        "error"
    )
    status = "ready" if not failed and not celery_bad else "degraded"

    return {
        "status": status,
        "version": settings.api_version,
        "alembic_revision": current_db_revision(),
        "checks": checks,
        "feature_flags": {
            "admin_api": settings.enable_admin_api,
            "validation_api": settings.enable_validation_api,
            "search_backend": settings.search_backend,
        },
    }
