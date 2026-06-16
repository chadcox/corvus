from __future__ import annotations

import socket
import time
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import IngestJob
from ff_core.constants import JobStatus

router = APIRouter(prefix="/system", tags=["system"])


def _read_cpu_times() -> tuple[int, int] | None:
    try:
        line = Path("/proc/stat").read_text(encoding="utf-8").splitlines()[0]
    except Exception:
        return None
    parts = line.split()
    if len(parts) < 5 or parts[0] != "cpu":
        return None
    values = [int(v) for v in parts[1:]]
    idle = values[3] + (values[4] if len(values) > 4 else 0)
    total = sum(values)
    return total, idle


def _cpu_usage_percent() -> float | None:
    first = _read_cpu_times()
    if not first:
        return None
    time.sleep(0.1)
    second = _read_cpu_times()
    if not second:
        return None
    total_delta = second[0] - first[0]
    idle_delta = second[1] - first[1]
    if total_delta <= 0:
        return None
    return round(max(0.0, min(100.0, (1 - (idle_delta / total_delta)) * 100)), 1)


def _memory_usage() -> tuple[int, int] | tuple[None, None]:
    try:
        meminfo = {}
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            key, value = line.split(":", 1)
            meminfo[key] = value.strip()
        total_kb = int(meminfo["MemTotal"].split()[0])
        available_kb = int(meminfo["MemAvailable"].split()[0])
        used_kb = max(0, total_kb - available_kb)
        return used_kb * 1024, total_kb * 1024
    except Exception:
        return None, None


@router.get("/status")
def get_system_status(db: Session = Depends(get_db)) -> dict:
    running_jobs = (
        db.query(func.count(IngestJob.id))
        .filter(IngestJob.status.in_((JobStatus.PENDING, JobStatus.RUNNING)))
        .scalar()
        or 0
    )
    queued_jobs = (
        db.query(func.count(IngestJob.id))
        .filter(IngestJob.status == JobStatus.PENDING)
        .scalar()
        or 0
    )
    completed_jobs = (
        db.query(func.count(IngestJob.id))
        .filter(IngestJob.status == JobStatus.COMPLETED)
        .scalar()
        or 0
    )
    failed_jobs = (
        db.query(func.count(IngestJob.id))
        .filter(IngestJob.status == JobStatus.FAILED)
        .scalar()
        or 0
    )

    disk = Path("/data")
    try:
        import shutil

        usage = shutil.disk_usage(disk if disk.exists() else "/")
        disk_used_bytes = usage.used
        disk_total_bytes = usage.total
    except Exception:
        disk_used_bytes = None
        disk_total_bytes = None

    mem_used_bytes, mem_total_bytes = _memory_usage()
    return {
        "hostname": socket.gethostname(),
        "cpu_usage_percent": _cpu_usage_percent(),
        "memory_used_bytes": mem_used_bytes,
        "memory_total_bytes": mem_total_bytes,
        "disk_used_bytes": disk_used_bytes,
        "disk_total_bytes": disk_total_bytes,
        "jobs": {
            "running": running_jobs,
            "queued": queued_jobs,
            "completed": completed_jobs,
            "failed": failed_jobs,
        },
    }
