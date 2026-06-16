"""Build structured pass/fail checks for ingest jobs (API validation without UI)."""

from __future__ import annotations

from typing import Any

from ff_core.constants import JobStatus
from ff_core.schemas import IngestCheck, IngestOutcomeRead, SourceStats


def _check(name: str, passed: bool, detail: str | None = None) -> IngestCheck:
    return IngestCheck(name=name, passed=passed, detail=detail)


def build_ingest_outcome(
    *,
    job_id: Any,
    evidence_source_id: Any,
    case_id: Any,
    job_status: str,
    job_progress: int,
    job_message: str | None,
    source_status: str | None,
    stats: SourceStats | None,
    min_timeline_events: int = 1,
    min_filesystem_nodes: int = 0,
) -> IngestOutcomeRead:
    """Assemble machine-readable ingest success/failure from DB state."""
    checks: list[IngestCheck] = []
    terminal = job_status in (JobStatus.COMPLETED, JobStatus.FAILED)

    checks.append(
        _check(
            "job_terminal",
            terminal,
            f"status={job_status}" if terminal else "still running",
        )
    )
    checks.append(
        _check(
            "job_completed",
            job_status == JobStatus.COMPLETED,
            job_message,
        )
    )

    if source_status is not None:
        checks.append(
            _check(
                "source_completed",
                source_status == JobStatus.COMPLETED,
                f"source status={source_status}",
            )
        )
    else:
        checks.append(_check("source_completed", False, "evidence source not found"))

    if stats is not None:
        checks.append(
            _check(
                "timeline_persisted",
                stats.timeline_count >= min_timeline_events,
                f"{stats.timeline_count} timeline event(s)",
            )
        )
        if min_filesystem_nodes > 0:
            checks.append(
                _check(
                    "filesystem_persisted",
                    stats.filesystem_count >= min_filesystem_nodes,
                    f"{stats.filesystem_count} path(s)",
                )
            )
        checks.append(
            _check(
                "stats_available",
                True,
                (
                    f"events={stats.timeline_count}, paths={stats.filesystem_count}, "
                    f"entities={stats.entity_count}, sigma_rules={stats.sigma_detection_count}"
                ),
            )
        )
    elif job_status == JobStatus.COMPLETED:
        checks.append(_check("timeline_persisted", False, "stats unavailable"))
    elif not terminal:
        checks.append(_check("timeline_persisted", False, "waiting for ingest"))

    success = all(c.passed for c in checks) and job_status == JobStatus.COMPLETED

    return IngestOutcomeRead(
        success=success,
        case_id=case_id,
        job_id=job_id,
        evidence_source_id=evidence_source_id,
        job_status=job_status,
        source_status=source_status,
        progress=job_progress,
        message=job_message,
        stats=stats,
        checks=checks,
    )
