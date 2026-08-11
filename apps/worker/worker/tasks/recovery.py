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
# scheduled with an ETA. Ownership evidence from any of them keeps a job alive,
# including one a peer worker has only just picked up.
_INSPECT_BUCKETS = ("active", "reserved", "scheduled")

# Hard ceiling so a mis-set grace window cannot delay recovery indefinitely.
MAX_STARTUP_DELAY_SECONDS = 300.0

# What to do with a running job that no responding worker claims. Celery's
# inspect API cannot prove such a job is gone (see `live_ingest_task_ids`), so
# `skip` — the default — leaves it alone and only reports it.
UNCLAIMED_ACTIONS = ("skip", "fail")
DEFAULT_UNCLAIMED_ACTION = "skip"


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
    """Return ingest task ids positively observed as claimed by some worker.

    Job ids are dispatched as Celery task ids, so a task id in a reply is proof
    that the job is still owned. The converse does not hold: this result is
    **presence-only evidence**. Celery's inspect API broadcasts to the cluster
    and returns whatever arrives before the timeout, so a worker that is busy,
    paused, slow, partitioned, or simply late is silently absent from the reply
    and is indistinguishable from a worker that answered "I hold nothing". A
    task id missing from this set therefore proves nothing about that task.
    Callers must not read absence here as evidence that a job is orphaned.
    """
    live: set[str] = set()
    for bucket in _INSPECT_BUCKETS:
        probe = getattr(inspector, bucket, None)
        if probe is None:
            continue
        reply = probe()
        # `None` (nobody answered) and a partial dict carry the same weight:
        # both add no positive evidence and neither refutes ownership.
        if not isinstance(reply, dict):
            continue
        for entries in reply.values():
            live.update(_task_ids(entries))
    return live


def _unclaimed_action() -> str:
    """Normalize the configured action for jobs no responding worker claims."""
    action = str(settings.worker_reconcile_unclaimed_action or "").strip().lower()
    if action not in UNCLAIMED_ACTIONS:
        return DEFAULT_UNCLAIMED_ACTION
    return action


def _default_inspector() -> Any:
    # Imported lazily: worker.celery_app imports this module at startup.
    from worker.celery_app import celery_app

    timeout = max(0.1, float(settings.worker_reconcile_inspect_timeout_seconds))
    return celery_app.control.inspect(timeout=timeout)


def _probe_live_ids(inspector: Any) -> set[str]:
    """Collect presence evidence, treating a broken probe as "no evidence"."""
    try:
        return live_ingest_task_ids(inspector)
    except Exception as exc:
        # An unreachable control plane yields no positive evidence, which is
        # already how a silent worker is handled: nothing is proven either way.
        logger.warning("reconcile_probe_failed error=%s", exc.__class__.__name__)
        return set()


def reconcile_orphaned_ingest_jobs(
    inspector: Any | None = None,
    now: datetime | None = None,
) -> int:
    """Report running ingest jobs that no responding worker claims.

    Celery's inspect API is presence-only (see :func:`live_ingest_task_ids`): it
    can prove a job is still owned, never that it is orphaned. So by default
    (``WORKER_RECONCILE_UNCLAIMED_ACTION=skip``) unclaimed jobs are logged and
    left running rather than marked failed, because a job held by a worker that
    did not answer in time is indistinguishable from an abandoned one. Setting
    the action to ``fail`` opts into the lossy legacy cleanup, which can still
    mark another worker's live ingest as failed.
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

        live_ids = _probe_live_ids(inspector if inspector is not None else _default_inspector())

        unclaimed_ids = [str(row[0]) for row in rows if str(row[0]) not in live_ids]
        if not unclaimed_ids:
            logger.info(
                "reconcile_all_jobs_claimed running=%d claimed=%d",
                len(rows),
                len(live_ids),
            )
            return 0

        action = _unclaimed_action()
        if action != "fail":
            # Nothing observed here proves these jobs are gone, so they keep
            # running and an operator decides. Logged so they stay visible.
            logger.warning(
                "reconcile_unclaimed_jobs_left_running action=skip unclaimed=%d "
                "claimed=%d jobs=%s",
                len(unclaimed_ids),
                len(rows) - len(unclaimed_ids),
                ",".join(sorted(unclaimed_ids)),
            )
            return 0

        logger.warning(
            "reconcile_failing_unclaimed_jobs action=fail unclaimed=%d ownership_unproven "
            "(a worker that did not answer the probe may still hold these jobs)",
            len(unclaimed_ids),
        )
        unclaimed_set = set(unclaimed_ids)
        # A source can carry several jobs; only fail the source when none of its
        # remaining running jobs are still claimed by a responding worker.
        live_source_ids = {str(row[1]) for row in rows if str(row[0]) not in unclaimed_set}

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
                "job_ids": unclaimed_ids,
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
            "reconciled_unclaimed_ingest_jobs jobs=%d preserved=%d sources=%s",
            len(updated),
            len(rows) - len(unclaimed_ids),
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
