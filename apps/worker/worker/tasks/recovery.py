from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import text

from worker.db import get_session

logger = logging.getLogger(__name__)


def reconcile_orphaned_ingest_jobs() -> int:
    """Mark stale running ingest jobs as failed after worker restarts."""
    session = get_session()
    now = datetime.now(timezone.utc)
    try:
        rows = session.execute(
            text(
                """
                UPDATE ingest_jobs
                SET status = 'failed',
                    message = 'Ingest interrupted by worker restart',
                    finished_at = COALESCE(finished_at, :now)
                WHERE status = 'running'
                RETURNING evidence_source_id
                """
            ),
            {"now": now},
        ).fetchall()
        source_ids = sorted({str(row[0]) for row in rows})
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
        if source_ids:
            logger.warning(
                "reconciled_orphaned_ingest_jobs count=%d source_ids=%s",
                len(source_ids),
                ",".join(source_ids),
            )
        return len(source_ids)
    except Exception:
        session.rollback()
        logger.exception("reconcile_orphaned_ingest_jobs_failed")
        return 0
    finally:
        session.close()
