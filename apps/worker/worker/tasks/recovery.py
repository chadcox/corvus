from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Iterator

from sqlalchemy import text

from worker.config import settings
from worker.db import get_session

logger = logging.getLogger(__name__)

INGEST_TASK_NAME = "worker.tasks.ingest.process_evidence_package"
RECONCILE_ERROR_CODE = "interrupted"
RECONCILE_ERROR_STAGE = "worker_restart"
RECONCILE_MESSAGE = "Ingest interrupted by worker restart"

# Buckets that mean "a worker still owns this task": executing, prefetched, or
# scheduled with an ETA. All three must be treated as live so a restart never
# fails a job another worker is about to finish.
_INSPECT_BUCKETS = ("active", "reserved", "scheduled")

# Hard ceiling so a mis-set grace window cannot delay recovery indefinitely.
MAX_STARTUP_DELAY_SECONDS = 300.0

INSPECT_FAILURE_ACTIONS = ("skip", "fail")


class InspectUnavailable(RuntimeError):
    """No worker answered the liveness probe, so ownership is unknown."""


def _task_ids(entries: Any) -> Iterator[str]:
    """Yield ingest task ids from one inspector bucket for one worker."""
    if not isinstance(entries, (list, tuple)):
        return
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        # `scheduled` wraps the task in a `request` envelope; the other buckets
        # expose the task fields directly.
        request = entry.get("request")
        payload = request if isinstance(request, dict) else entry
        if payload.get("name") != INGEST_TASK_NAME:
            continue
        task_id = payload.get("id")
        if task_id:
            yield str(task_id)


def live_ingest_task_ids(inspector: Any) -> set[str]:
    """Return ingest task ids currently claimed by any responding worker.

    Job ids are dispatched as Celery task ids, so a claimed task id is a job
    that is still owned. Raises :class:`InspectUnavailable` when no bucket
    produced a reply, because an empty result and a silent control plane are
    indistinguishable from the caller's point of view.
    """
    live: set[str] = set()
    replied = False
    for bucket in _INSPECT_BUCKETS:
        probe = getattr(inspector, bucket, None)
        if probe is None:
            continue
        reply = probe()
        if reply is None:
            continue
        replied = True
        if not isinstance(reply, dict):
            continue
        for entries in reply.values():
            live.update(_task_ids(entries))
    if not replied:
        raise InspectUnavailable("no worker replied to the ingest liveness probe")
    return live


def _default_inspector() -> Any:
    # Imported lazily: worker.celery_app imports this module at startup.
    from worker.celery_app import celery_app

    timeout = max(0.1, float(settings.worker_reconcile_inspect_timeout_seconds))
    return celery_app.control.inspect(timeout=timeout)


def _resolve_live_ids(inspector: Any) -> set[str] | None:
    """Resolve claimed task ids, or ``None`` when reconciliation must stand down."""
    try:
        return live_ingest_task_ids(inspector)
    except Exception as exc:
        action = str(settings.worker_reconcile_on_inspect_failure or "").strip().lower()
        if action not in INSPECT_FAILURE_ACTIONS:
            action = "skip"
        if action == "fail":
            logger.warning(
                "reconcile_inspect_unavailable action=fail error=%s", exc.__class__.__name__
            )
            return set()
        logger.warning(
            "reconcile_inspect_unavailable action=skip error=%s running jobs left untouched",
            exc.__class__.__name__,
        )
        return None


def reconcile_orphaned_ingest_jobs(
    inspector: Any | None = None,
    now: datetime | None = None,
) -> int:
    """Fail running ingest jobs that no live worker owns.

    Jobs whose task id is still claimed by a responding worker are preserved so
    a rolling restart never reports a running ingest as failed.
    """
    session = get_session()
    stamp = now or datetime.now(timezone.utc)
    try:
        rows = session.execute(
            text(
                """
                SELECT id, evidence_source_id
                FROM ingest_jobs
                WHERE status = 'running'
                """
            )
        ).fetchall()
        if not rows:
            # Nothing to reconcile: never probe the control plane for no reason.
            return 0
        # Release the read snapshot before the bounded control-plane probe so no
        # transaction sits idle while workers are polled.
        session.rollback()

        live_ids = _resolve_live_ids(inspector if inspector is not None else _default_inspector())
        if live_ids is None:
            return 0

        orphan_ids = [str(row[0]) for row in rows if str(row[0]) not in live_ids]
        if not orphan_ids:
            logger.info("reconcile_no_orphans running=%d live=%d", len(rows), len(live_ids))
            return 0

        orphan_set = set(orphan_ids)
        # A source can carry several jobs; only fail the source when none of its
        # remaining running jobs are still owned by a live worker.
        live_source_ids = {str(row[1]) for row in rows if str(row[0]) not in orphan_set}

        updated = session.execute(
            text(
                """
                UPDATE ingest_jobs
                SET status = 'failed',
                    message = :message,
                    error_code = :error_code,
                    error_stage = :error_stage,
                    finished_at = COALESCE(finished_at, :now)
                WHERE status = 'running'
                  AND id = ANY(CAST(:job_ids AS uuid[]))
                RETURNING id, evidence_source_id
                """
            ),
            {
                "message": RECONCILE_MESSAGE,
                "error_code": RECONCILE_ERROR_CODE,
                "error_stage": RECONCILE_ERROR_STAGE,
                "now": stamp,
                "job_ids": orphan_ids,
            },
        ).fetchall()
        # Derived from rows this statement actually changed: a job that finished
        # between the read and the probe keeps its source untouched.
        source_ids = sorted({str(row[1]) for row in updated} - live_source_ids)
        if source_ids:
            session.execute(
                text(
                    """
                    UPDATE evidence_sources
                    SET status = 'failed'
                    WHERE id = ANY(CAST(:source_ids AS uuid[]))
                      AND status IN ('pending', 'running')
                    """
                ),
                {"source_ids": source_ids},
            )
        session.commit()
        logger.warning(
            "reconciled_orphaned_ingest_jobs jobs=%d preserved=%d sources=%s",
            len(updated),
            len(rows) - len(orphan_ids),
            ",".join(source_ids) or "-",
        )
        return len(updated)
    except Exception:
        session.rollback()
        logger.exception("reconcile_orphaned_ingest_jobs_failed")
        return 0
    finally:
        session.close()


def start_startup_reconciliation(
    delay_seconds: float | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    runner: Callable[[], int] = reconcile_orphaned_ingest_jobs,
) -> threading.Thread:
    """Run reconciliation off the boot path after a bounded grace window.

    The delay runs in a background thread so the worker's own control-plane
    replies (and those of workers still starting) are available by the time
    ownership is probed, and so startup is never blocked by the probe.
    """
    configured = (
        settings.worker_reconcile_startup_delay_seconds
        if delay_seconds is None
        else delay_seconds
    )
    try:
        delay = float(configured)
    except (TypeError, ValueError):
        delay = 0.0
    delay = max(0.0, min(delay, MAX_STARTUP_DELAY_SECONDS))

    def _run() -> None:
        try:
            if delay > 0:
                sleeper(delay)
            runner()
        except Exception:
            logger.exception("reconcile_startup_thread_failed")

    thread = threading.Thread(target=_run, name="corvus-reconcile", daemon=True)
    thread.start()
    return thread
