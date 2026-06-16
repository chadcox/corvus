"""Celery task: hash all files in an evidence package directory."""

from __future__ import annotations

import concurrent.futures
import hashlib
import os
from pathlib import Path
from uuid import UUID

from sqlalchemy import text

from worker.celery_app import celery_app
from worker.config import settings
from worker.db import get_session

_HASH_CHUNK_SIZE = 1024 * 1024
_HASH_BATCH_SIZE = 1000
_MAX_HASH_WORKERS = max(1, min(8, (os.cpu_count() or 4)))

_HASH_INSERT = text("""
    INSERT INTO evidence_file_hashes
    (id, evidence_source_id, relative_path, sha256, sha1, md5, file_size)
    VALUES (gen_random_uuid(), :evidence_source_id, :relative_path, :sha256, :sha1, :md5, :file_size)
""")


def _file_hashes(path: Path) -> tuple[str, str, str, int]:
    h_sha256 = hashlib.sha256()
    h_sha1 = hashlib.sha1()
    h_md5 = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(_HASH_CHUNK_SIZE), b""):
            h_sha256.update(chunk)
            h_sha1.update(chunk)
            h_md5.update(chunk)
    return h_sha256.hexdigest(), h_sha1.hexdigest(), h_md5.hexdigest(), path.stat().st_size


def _iter_files(root: Path):
    for dirpath, _dirnames, filenames in os.walk(root):
        base = Path(dirpath)
        for filename in filenames:
            yield base / filename


def _flush_hash_batch(session, batch: list[dict]) -> None:
    if batch:
        session.execute(_HASH_INSERT, batch)
        session.commit()
        batch.clear()


@celery_app.task(name="worker.tasks.hash_evidence.hash_evidence_files", bind=True)
def hash_evidence_files(self, source_id: str) -> dict:
    """Hash every file in the evidence package directory and store results."""
    session = get_session()
    sid = UUID(source_id)

    try:
        row = session.execute(
            text("SELECT package_path FROM evidence_sources WHERE id = :id"),
            {"id": str(sid)},
        ).fetchone()
        if not row:
            return {"error": "source not found"}

        package_dir = Path(row[0])
        if not package_dir.is_dir():
            package_dir = Path(settings.evidence_root) / package_dir
        if not package_dir.is_dir():
            return {"error": "package directory not found"}

        # Clear existing hashes for a clean re-run
        session.execute(
            text("DELETE FROM evidence_file_hashes WHERE evidence_source_id = :sid"),
            {"sid": str(sid)},
        )
        session.commit()

        hashed = 0
        batch: list[dict] = []
        pending: set[concurrent.futures.Future] = set()
        max_pending = _MAX_HASH_WORKERS * 4

        def submit_until_full(pool) -> bool:
            try:
                while len(pending) < max_pending:
                    path = next(paths)
                    if path.is_file():
                        fut = pool.submit(_file_hashes, path)
                        pending.add(fut)
                        future_paths[fut] = path
            except StopIteration:
                return False
            return True

        def collect_done(done) -> None:
            nonlocal hashed
            for fut in done:
                path = future_paths.pop(fut)
                try:
                    sha256, sha1, md5, file_size = fut.result()
                    rel = str(path.relative_to(package_dir)).replace("\\", "/")
                    batch.append({
                        "evidence_source_id": str(sid),
                        "relative_path": rel,
                        "sha256": sha256,
                        "sha1": sha1,
                        "md5": md5,
                        "file_size": file_size,
                    })
                    hashed += 1
                    if len(batch) >= _HASH_BATCH_SIZE:
                        _flush_hash_batch(session, batch)
                        self.update_state(state="PROGRESS", meta={"hashed": hashed})
                except OSError:
                    continue

        paths = iter(_iter_files(package_dir))
        future_paths: dict[concurrent.futures.Future, Path] = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=_MAX_HASH_WORKERS) as pool:
            more_paths = submit_until_full(pool)
            while pending:
                done, pending = concurrent.futures.wait(
                    pending,
                    return_when=concurrent.futures.FIRST_COMPLETED,
                )
                collect_done(done)
                if more_paths:
                    more_paths = submit_until_full(pool)

        _flush_hash_batch(session, batch)

        session.execute(
            text("""
                UPDATE evidence_sources
                SET hash_status = 'complete', hash_file_count = :count
                WHERE id = :id
            """),
            {"count": hashed, "id": str(sid)},
        )
        session.commit()

        return {"hashed": hashed}

    except Exception:
        session.rollback()
        session.execute(
            text("UPDATE evidence_sources SET hash_status = 'failed' WHERE id = :id"),
            {"id": str(sid)},
        )
        session.commit()
        raise
    finally:
        session.close()
