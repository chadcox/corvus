"""Admin / development helpers — counts, disk usage, route catalog."""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import redis
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    Case,
    Entity,
    EvidenceSource,
    FilesystemNode,
    IngestJob,
    Relation,
    SigmaDetection,
    TimelineEvent,
)
from app.auth.service import recent_revocation_failures
from app.routers.search import search_metrics_snapshot
from app.services.readiness import readiness_payload
from app.sigma_rules_status import get_sigma_rules_status
from corvus_core.schemas import (
    AdminDiskUsage,
    AdminFeatureFlags,
    AdminOverviewRead,
    AdminAuthSecurityRead,
    AdminSearchObservabilityRead,
    AdminTableCounts,
    SigmaRulesStatusRead,
)

_DISK_USAGE_CACHE: dict[str, tuple[float, AdminDiskUsage]] = {}


def auth_security_snapshot() -> AdminAuthSecurityRead:
    revocation_failures = recent_revocation_failures()
    try:
        client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        failed = 0
        lockouts = 0

        for key in client.scan_iter(match="auth:attempts:*", count=200):
            try:
                failed += int(client.get(key) or 0)
            except (TypeError, ValueError):
                continue

        for _ in client.scan_iter(match="auth:lock:*", count=200):
            lockouts += 1

        return AdminAuthSecurityRead(
            failed_logins_5m=failed,
            active_lockouts=lockouts,
            redis_available=True,
            revocation_redis_available=True,
            revocation_failures_5m=revocation_failures,
            error=None,
        )
    except redis.RedisError as exc:
        return AdminAuthSecurityRead(
            redis_available=False,
            revocation_redis_available=False,
            revocation_failures_5m=revocation_failures,
            error=f"redis_error:{exc.__class__.__name__}",
        )


def _database_host() -> str:
    try:
        parsed = urlparse(settings.database_url)
        host = parsed.hostname or "unknown"
        if parsed.port:
            host = f"{host}:{parsed.port}"
        return host
    except Exception:
        return "unknown"


def disk_usage_for_path(path: str) -> AdminDiskUsage:
    ttl = max(settings.admin_disk_usage_cache_seconds, 0)
    now = time.monotonic()
    cached = _DISK_USAGE_CACHE.get(path)
    if ttl > 0 and cached and (now - cached[0]) < ttl:
        return cached[1]

    try:
        usage = shutil.disk_usage(path)
        root = Path(path)
        used_in_path = 0
        if root.exists():
            for p in root.rglob("*"):
                if p.is_file():
                    try:
                        used_in_path += p.stat().st_size
                    except OSError:
                        continue
        result = AdminDiskUsage(
            path=path,
            total_bytes=usage.total,
            used_bytes=used_in_path,
            free_bytes=usage.free,
        )
        if ttl > 0:
            _DISK_USAGE_CACHE[path] = (now, result)
        return result
    except OSError as exc:
        return AdminDiskUsage(path=path, error=str(exc))


def table_counts(db: Session) -> AdminTableCounts:
    return AdminTableCounts(
        cases=db.query(func.count(Case.id)).scalar() or 0,
        evidence_sources=db.query(func.count(EvidenceSource.id)).scalar() or 0,
        ingest_jobs=db.query(func.count(IngestJob.id)).scalar() or 0,
        timeline_events=db.query(func.count(TimelineEvent.id)).scalar() or 0,
        filesystem_nodes=db.query(func.count(FilesystemNode.id)).scalar() or 0,
        entities=db.query(func.count(Entity.id)).scalar() or 0,
        relations=db.query(func.count(Relation.id)).scalar() or 0,
        sigma_detections=db.query(func.count(SigmaDetection.id)).scalar() or 0,
    )


def jobs_by_status(db: Session) -> dict[str, int]:
    rows = db.query(IngestJob.status, func.count(IngestJob.id)).group_by(IngestJob.status).all()
    return {status: count for status, count in rows}


def evidence_by_status(db: Session) -> dict[str, int]:
    rows = (
        db.query(EvidenceSource.status, func.count(EvidenceSource.id))
        .group_by(EvidenceSource.status)
        .all()
    )
    return {status: count for status, count in rows}


def build_admin_overview(db: Session) -> AdminOverviewRead:
    sigma = SigmaRulesStatusRead.model_validate(get_sigma_rules_status())
    return AdminOverviewRead(
        readiness=readiness_payload(),
        table_counts=table_counts(db),
        jobs_by_status=jobs_by_status(db),
        evidence_by_status=evidence_by_status(db),
        disk=disk_usage_for_path(settings.evidence_root),
        sigma_rules=sigma,
        feature_flags=AdminFeatureFlags(
            enable_validation_api=settings.enable_validation_api,
            enable_admin_api=settings.enable_admin_api,
        ),
        auth_security=auth_security_snapshot(),
        search_observability=AdminSearchObservabilityRead.model_validate(search_metrics_snapshot()),
    )


def collect_routes(app: Any) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for route in app.routes:
        path = getattr(route, "path", None)
        if not path or not path.startswith("/"):
            continue
        methods = sorted(getattr(route, "methods", None) or [])
        if not methods or methods == ["HEAD"]:
            continue
        methods = [m for m in methods if m != "HEAD"]
        if not methods:
            continue
        tags = list(getattr(route, "tags", None) or [])
        entries.append(
            {
                "methods": methods,
                "path": path,
                "name": getattr(route, "name", None),
                "tags": tags,
            }
        )
    entries.sort(key=lambda e: (e["path"], ",".join(e["methods"])))
    return entries
