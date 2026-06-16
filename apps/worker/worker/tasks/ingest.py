import csv
import io
import json
import logging
import shutil
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy import text

from worker.celery_app import celery_app
from worker.config import settings
from worker.db import get_session
from worker.chainsaw.evaluate import evaluate_chainsaw_hunt
from worker.chainsaw.hunt import collect_evtx_for_hunt
from worker.config import settings as worker_settings
from worker.sigma.evaluate import evaluate_sigma_rules
from worker.sigma.ingest_note import sigma_ingest_note
from worker.search_index import delete_source_docs, index_source
from worker.sources import ingest_source_package
from worker.util.pg_sanitize import sanitize_for_postgres, sanitize_text

logger = logging.getLogger(__name__)

VALIDATION_MODE_FAST = "fast"

_TIMELINE_INSERT = text(
    """
    INSERT INTO timeline_events
    (id, evidence_source_id, timestamp_utc, event_type, summary,
     artifact_type, original_source, data, entity_refs, sigma_hits)
    VALUES
    (:id, :evidence_source_id, :timestamp_utc, :event_type, :summary,
     :artifact_type, :original_source,
     CAST(:data AS jsonb), CAST(:entity_refs AS jsonb), CAST(:sigma_hits AS jsonb))
    """
)

_SIGMA_INSERT = text(
    """
    INSERT INTO sigma_detections
    (id, evidence_source_id, engine, rule_id, title, level, description, tags, match_count, sample_event_ids)
    VALUES
    (gen_random_uuid(), :evidence_source_id, :engine, :rule_id, :title, :level, :description,
     CAST(:tags AS jsonb), :match_count, CAST(:sample_event_ids AS jsonb))
    ON CONFLICT (evidence_source_id, engine, rule_id) DO UPDATE SET
        title = EXCLUDED.title,
        level = EXCLUDED.level,
        description = EXCLUDED.description,
        tags = EXCLUDED.tags,
        match_count = EXCLUDED.match_count,
        sample_event_ids = EXCLUDED.sample_event_ids
    """
)

_ENTITY_INSERT = text(
    """
    INSERT INTO entities
    (id, evidence_source_id, entity_type, display_name, attributes)
    VALUES
    (:id, :evidence_source_id, :entity_type, :display_name,
     CAST(:attributes AS jsonb))
    """
)

_FILESYSTEM_INSERT = text(
    """
    INSERT INTO filesystem_nodes
    (id, evidence_source_id, full_path, name, is_directory, size, is_deleted, parent_path)
    VALUES
    (:id, :evidence_source_id, :full_path, :name, :is_directory,
     :size, :is_deleted, :parent_path)
    """
)


def _hostname_from_events(events: list[dict]) -> str | None:
    """Pick the most common host/computer value from parsed timeline events."""
    candidates: Counter[str] = Counter()
    for ev in events:
        data = ev.get("data") or {}
        if not isinstance(data, dict):
            continue
        raw = data.get("Computer") or data.get("computer") or data.get("host") or data.get("Host")
        if not raw:
            continue
        host = sanitize_text(str(raw)).strip()
        if not host:
            continue
        if host.lower() in {"unknown", "unknown-host", "localhost", "n/a", "-"}:
            continue
        candidates[host] += 1
    if not candidates:
        return None
    return candidates.most_common(1)[0][0][:255]


def _update_job(
    session,
    job_id: UUID,
    *,
    status: str | None = None,
    progress: int | None = None,
    message: str | None = None,
    error_code: str | None = None,
    error_stage: str | None = None,
    finished: bool = False,
) -> None:
    sets = []
    params: dict = {"job_id": str(job_id)}
    if status:
        sets.append("status = :status")
        params["status"] = status
    if progress is not None:
        sets.append("progress = :progress")
        params["progress"] = progress
    if message is not None:
        sets.append("message = :message")
        params["message"] = message
    if error_code is not None:
        sets.append("error_code = :error_code")
        params["error_code"] = error_code
    if error_stage is not None:
        sets.append("error_stage = :error_stage")
        params["error_stage"] = error_stage
    if finished:
        sets.append("finished_at = :finished_at")
        params["finished_at"] = datetime.now(timezone.utc)
    if status == "running":
        sets.append("started_at = COALESCE(started_at, :started_at)")
        params["started_at"] = datetime.now(timezone.utc)

    if sets:
        session.execute(text(f"UPDATE ingest_jobs SET {', '.join(sets)} WHERE id = :job_id"), params)
        session.commit()


def classify_ingest_failure(exc: Exception, stage: str) -> tuple[str, str]:
    if isinstance(exc, FileNotFoundError):
        return "source_not_found", stage
    if isinstance(exc, RuntimeError) and str(exc).lower().startswith("cancelled"):
        return "cancelled", "cancel"
    msg = str(exc).lower()
    if "manifest" in msg:
        return "manifest_invalid", stage
    if "opensearch" in msg:
        return "search_index_error", stage
    return "ingest_failed", stage


def _assign_event_ids(events: list[dict]) -> None:
    for ev in events:
        if not ev.get("id"):
            ev["id"] = str(uuid.uuid4())


def _assign_filesystem_ids(nodes: list[dict]) -> None:
    for node in nodes:
        if not node.get("id"):
            node["id"] = str(uuid.uuid4())


def _job_cancel_requested(session, job_id: UUID) -> bool:
    row = session.execute(
        text("SELECT status, message FROM ingest_jobs WHERE id = :id"),
        {"id": str(job_id)},
    ).fetchone()
    if not row:
        return False
    status = (row[0] or "").lower()
    message = (row[1] or "").lower()
    return status == "failed" and message.startswith("cancelled")


def _raise_if_cancel_requested(session, job_id: UUID) -> None:
    if _job_cancel_requested(session, job_id):
        raise RuntimeError("Cancelled by user")


def validation_mode(manifest: dict | None) -> str | None:
    if not isinstance(manifest, dict):
        return None
    raw = manifest.get("ff_validation_mode")
    if not raw:
        return None
    return sanitize_text(str(raw)).strip().lower() or None


def is_fast_validation_mode(manifest: dict | None) -> bool:
    return validation_mode(manifest) == VALIDATION_MODE_FAST


def _timeline_row(ev: dict) -> dict:
    data = sanitize_for_postgres(ev.get("data") or {})
    return {
        "id": ev["id"],
        "evidence_source_id": ev["evidence_source_id"],
        "timestamp_utc": ev["timestamp_utc"],
        "event_type": sanitize_text(str(ev["event_type"]))[:128],
        "summary": sanitize_text(str(ev["summary"]))[:2000],
        "artifact_type": sanitize_text(str(ev["artifact_type"]))[:64] if ev.get("artifact_type") else None,
        "original_source": sanitize_text(str(ev["original_source"])) if ev.get("original_source") else None,
        "data": json.dumps(data),
        "entity_refs": json.dumps(sanitize_for_postgres(ev.get("entity_refs") or [])),
        "sigma_hits": json.dumps(sanitize_for_postgres(ev.get("sigma_hits") or [])),
    }


def _copy_timeline_rows(session, rows: list[dict]) -> None:
    if not rows:
        return
    sa_conn = session.connection()
    proxy_conn = sa_conn.connection
    raw_conn = getattr(proxy_conn, "driver_connection", proxy_conn)
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    for row in rows:
        writer.writerow(
            [
                row["id"],
                row["evidence_source_id"],
                row["timestamp_utc"].isoformat(),
                row["event_type"],
                row["summary"],
                row["artifact_type"],
                row["original_source"],
                row["data"],
                row["entity_refs"],
                row["sigma_hits"],
            ]
        )
    copy_sql = """
        COPY timeline_events
        (id, evidence_source_id, timestamp_utc, event_type, summary,
         artifact_type, original_source, data, entity_refs, sigma_hits)
        FROM STDIN WITH (FORMAT CSV)
    """
    with raw_conn.cursor() as cur:
        with cur.copy(copy_sql) as cp:
            cp.write(buf.getvalue())


def _bulk_insert_timeline(session, events: list[dict]) -> None:
    if not events:
        return
    # Apply lower durability only to this transaction to speed bulk ingest.
    session.execute(text("SET LOCAL synchronous_commit TO OFF"))
    batch: list[dict] = []
    try:
        for ev in events:
            batch.append(_timeline_row(ev))
            if len(batch) >= 10_000:
                _copy_timeline_rows(session, batch)
                batch.clear()
        _copy_timeline_rows(session, batch)
        return
    except Exception:
        logger.exception("timeline_copy_failed_fallback_to_insert")

    # Fallback path: batched INSERT without per-batch commit.
    rows = [_timeline_row(ev) for ev in events]
    for batch_start in range(0, len(rows), 5_000):
        batch = rows[batch_start : batch_start + 5_000]
        session.execute(_TIMELINE_INSERT, batch)


def _bulk_insert_sigma(session, detections: list[dict]) -> None:
    if not detections:
        return
    rows = [
        {
            "evidence_source_id": d["evidence_source_id"],
            "engine": sanitize_text(str(d.get("engine") or "sigma"))[:32],
            "rule_id": sanitize_text(d["rule_id"])[:128],
            "title": sanitize_text(d["title"])[:512],
            "level": sanitize_text(d["level"])[:32],
            "description": sanitize_text(d["description"])[:4000] if d.get("description") else None,
            "tags": json.dumps(sanitize_for_postgres(d.get("tags") or [])),
            "match_count": d.get("match_count", 0),
            "sample_event_ids": json.dumps(sanitize_for_postgres(d.get("sample_event_ids") or [])),
        }
        for d in detections
    ]
    for batch_start in range(0, len(rows), 200):
        batch = rows[batch_start : batch_start + 200]
        session.execute(_SIGMA_INSERT, batch)
        session.commit()


def _bulk_insert_entities(session, entities: list[dict]) -> None:
    if not entities:
        return
    rows = [
        {
            "id": ent["id"],
            "evidence_source_id": ent["evidence_source_id"],
            "entity_type": sanitize_text(str(ent["entity_type"]))[:64],
            "display_name": sanitize_text(str(ent["display_name"]))[:512],
            "attributes": json.dumps(sanitize_for_postgres(ent.get("attributes") or {})),
        }
        for ent in entities
    ]
    for batch_start in range(0, len(rows), 500):
        batch = rows[batch_start : batch_start + 500]
        session.execute(_ENTITY_INSERT, batch)
        session.commit()


def _filesystem_row(node: dict) -> dict:
    raw_size = node.get("size")
    size_value: int | None
    if raw_size is None or raw_size == "":
        size_value = None
    else:
        try:
            size_value = int(raw_size)
        except (TypeError, ValueError):
            size_value = None
    parent = node.get("parent_path")
    return {
        "id": node["id"],
        "evidence_source_id": node["evidence_source_id"],
        "full_path": sanitize_text(str(node["full_path"]))[:4096],
        "name": sanitize_text(str(node["name"]))[:512],
        "is_directory": node["is_directory"],
        "size": size_value,
        "is_deleted": node.get("is_deleted", False),
        "parent_path": sanitize_text(str(parent))[:4096] if parent else None,
    }


def _bulk_insert_filesystem(session, nodes: list[dict]) -> None:
    if not nodes:
        return
    rows = [_filesystem_row(n) for n in nodes]
    for batch_start in range(0, len(rows), 500):
        batch = rows[batch_start : batch_start + 500]
        session.execute(_FILESYSTEM_INSERT, batch)
        session.commit()


# Tables written by the ingest task, in FK-safe deletion order.
_SOURCE_DATA_TABLES = (
    "timeline_events",
    "sigma_detections",
    "entities",
    "filesystem_nodes",
)


def _clear_source_data(session, source_id: UUID) -> None:
    """Remove any rows written for a source so a failed/partial ingest leaves
    no half-populated timeline behind (bulk inserts commit per batch)."""
    try:
        delete_source_docs(source_id)
    except Exception:
        logger.exception("opensearch_clear_failed source_id=%s", source_id)
    for table in _SOURCE_DATA_TABLES:
        session.execute(
            text(f"DELETE FROM {table} WHERE evidence_source_id = :sid"),
            {"sid": str(source_id)},
        )
    session.commit()


@celery_app.task(name="worker.tasks.ingest.process_evidence_package", bind=True)
def process_evidence_package(self, job_id: str, source_id: str) -> dict:
    session = get_session()
    jid = UUID(job_id)
    sid = UUID(source_id)
    task_start = time.perf_counter()
    stage_times: dict[str, float] = {}
    current_stage = "startup"

    def record_stage(name: str, started: float) -> None:
        stage_times[name] = time.perf_counter() - started

    try:
        _update_job(session, jid, status="running", progress=5, message="Starting ingest")
        _raise_if_cancel_requested(session, jid)

        row = session.execute(
            text(
                """
                SELECT package_path, platform, collector, manifest, case_id
                FROM evidence_sources
                WHERE id = :id
                """
            ),
            {"id": str(sid)},
        ).fetchone()
        if not row:
            raise ValueError(f"Evidence source {source_id} not found")
        case_id = UUID(str(row[4]))

        try:
            delete_source_docs(sid)
        except Exception:
            logger.exception("opensearch_delete_failed source_id=%s", sid)

        package_dir = Path(row[0])
        if not package_dir.is_dir():
            package_dir = Path(settings.evidence_root) / package_dir
        if not package_dir.is_dir():
            raise FileNotFoundError(f"Package not found: {package_dir}")

        def on_progress(pct: int, msg: str) -> None:
            _update_job(session, jid, progress=pct, message=msg)
            self.update_state(state="PROGRESS", meta={"progress": pct, "message": msg})

        manifest = row[3] if isinstance(row[3], dict) else None
        fast_validation_mode = is_fast_validation_mode(manifest)

        current_stage = "parse"
        stage_start = time.perf_counter()
        result = ingest_source_package(
            package_dir,
            sid,
            platform=row[1] or "unknown",
            collector=row[2] or "import",
            manifest=manifest,
            on_progress=on_progress,
        )
        _raise_if_cancel_requested(session, jid)
        record_stage("parse", stage_start)

        events = result["timeline_events"]
        _assign_event_ids(events)
        _assign_filesystem_ids(result["filesystem_nodes"])

        sigma_detections: list[dict] = []
        use_chainsaw_sigma = (
            not fast_validation_mode
            and worker_settings.chainsaw_enabled
            and worker_settings.chainsaw_include_sigma
        )

        if fast_validation_mode:
            _update_job(
                session,
                jid,
                progress=86,
                message="Fast validation ingest: skipping Sigma and Chainsaw detection stages",
            )
            result.setdefault("ingest_notes", []).append(
                "Fast validation mode: skipped Sigma, Chainsaw, and OpenSearch indexing"
            )
        elif use_chainsaw_sigma:
            _update_job(
                session,
                jid,
                progress=86,
                message="Skipping in-process Sigma (EVTX rules run via Chainsaw hunt)",
            )
        else:
            current_stage = "sigma"
            _update_job(session, jid, progress=86, message="Running Sigma detection rules")
            stage_start = time.perf_counter()
            sigma_detections, events = evaluate_sigma_rules(events, sid)
            _raise_if_cancel_requested(session, jid)
            record_stage("sigma", stage_start)
            for row in sigma_detections:
                row["engine"] = "sigma"
            result["timeline_events"] = events

        chainsaw_detections: list[dict] = []
        if not fast_validation_mode and worker_settings.chainsaw_enabled:
            current_stage = "chainsaw"
            stage_start = time.perf_counter()
            evtx_files = collect_evtx_for_hunt(package_dir)
            evtx_count = len(evtx_files)
            hunt_msg = f"Running Chainsaw hunt ({evtx_count} EVTX, parallel"
            if use_chainsaw_sigma:
                hunt_msg += ", Sigma dfir tier)"
            else:
                hunt_msg += ")"
            _update_job(session, jid, progress=88, message=hunt_msg)
            chainsaw_detections, events = evaluate_chainsaw_hunt(
                package_dir,
                events,
                sid,
                evtx_files=evtx_files,
            )
            _raise_if_cancel_requested(session, jid)
            record_stage("chainsaw", stage_start)
            result["timeline_events"] = events

        all_detections = sigma_detections + chainsaw_detections

        current_stage = "db_timeline"
        _update_job(session, jid, progress=92, message="Writing timeline to database")
        stage_start = time.perf_counter()
        _bulk_insert_timeline(session, events)
        _raise_if_cancel_requested(session, jid)
        record_stage("db_timeline", stage_start)
        current_stage = "db_detections"
        _update_job(session, jid, progress=94, message="Writing detection results")
        stage_start = time.perf_counter()
        _bulk_insert_sigma(session, all_detections)
        _raise_if_cancel_requested(session, jid)
        record_stage("db_detections", stage_start)
        current_stage = "db_entities_filesystem"
        _update_job(session, jid, progress=96, message="Writing entities and filesystem")
        current_stage = "search_index"
        stage_start = time.perf_counter()
        _bulk_insert_entities(session, result["entities"])
        _bulk_insert_filesystem(session, result["filesystem_nodes"])
        _raise_if_cancel_requested(session, jid)
        record_stage("db_entities_filesystem", stage_start)
        inferred_hostname = _hostname_from_events(events)

        if fast_validation_mode:
            stage_times["opensearch_index"] = 0.0
        else:
            stage_start = time.perf_counter()
            try:
                _update_job(session, jid, progress=98, message="Indexing searchable artifacts")
                index_source(
                    case_id=case_id,
                    source_id=sid,
                    events=events,
                    filesystem_nodes=result["filesystem_nodes"],
                    entities=result["entities"],
                )
                _raise_if_cancel_requested(session, jid)
            except Exception:
                logger.exception("opensearch_index_failed source_id=%s job_id=%s", sid, jid)
            record_stage("opensearch_index", stage_start)

        if inferred_hostname:
            session.execute(
                text(
                    """
                    UPDATE evidence_sources
                    SET status = 'completed',
                        hostname = :hostname
                    WHERE id = :id
                    """
                ),
                {"id": str(sid), "hostname": inferred_hostname},
            )
        else:
            session.execute(
                text("UPDATE evidence_sources SET status = 'completed' WHERE id = :id"),
                {"id": str(sid)},
            )
        session.commit()

        if worker_settings.delete_evidence_after_ingest:
            try:
                shutil.rmtree(package_dir, ignore_errors=True)
                logger.info("evidence_deleted_after_ingest source_id=%s path=%s", sid, package_dir)
            except Exception:
                logger.exception(
                    "evidence_delete_failed_after_ingest source_id=%s path=%s",
                    sid,
                    package_dir,
                )

        notes = list(result.get("ingest_notes") or [])
        sigma_msg = sigma_ingest_note(events, len(all_detections))
        if sigma_msg:
            notes.append(sigma_msg)
        note_suffix = f" — {'; '.join(notes)}" if notes else ""
        sigma_note = ""
        _update_job(
            session,
            jid,
            status="completed",
            progress=100,
            error_code=None,
            error_stage=None,
            message=(
                f"Ingested {len(events)} events, "
                f"{len(result['entities'])} entities, "
                f"{len(result['filesystem_nodes'])} filesystem nodes"
                f"{sigma_note}{note_suffix}"
            ),
            finished=True,
        )
        elapsed = time.perf_counter() - task_start
        logger.info(
            "ingest_performance source_id=%s job_id=%s elapsed_seconds=%.3f "
            "events=%d detections=%d entities=%d filesystem_nodes=%d stages=%s",
            sid,
            jid,
            elapsed,
            len(events),
            len(all_detections),
            len(result["entities"]),
            len(result["filesystem_nodes"]),
            {name: round(seconds, 3) for name, seconds in stage_times.items()},
        )

        return {
            "timeline_count": len(events),
            "entity_count": len(result["entities"]),
            "filesystem_count": len(result["filesystem_nodes"]),
            "sigma_detection_count": len(all_detections),
            "chainsaw_detection_count": len(chainsaw_detections),
        }
    except Exception as exc:
        session.rollback()
        # Bulk inserts commit per batch, so a mid-write failure can leave
        # partial rows. Remove them so a failed source is never half-populated.
        try:
            _clear_source_data(session, sid)
        except Exception:
            session.rollback()
        session.execute(
            text("UPDATE evidence_sources SET status = 'failed' WHERE id = :id"),
            {"id": str(sid)},
        )
        session.commit()
        error_code, error_stage = classify_ingest_failure(exc, current_stage)
        _update_job(
            session,
            jid,
            status="failed",
            message=str(exc)[:2000],
            error_code=error_code,
            error_stage=error_stage,
            finished=True,
        )
        raise
    finally:
        session.close()
