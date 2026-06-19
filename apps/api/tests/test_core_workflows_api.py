from __future__ import annotations

import uuid
from asyncio import run
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from fastapi import HTTPException
from starlette.datastructures import UploadFile

from app.auth.service import get_current_user
from app.database import get_db
from app.main import app
from app.models import Case, EvidenceFileHash, EvidenceSource, FilesystemNode, IngestJob
from app.routers import admin as admin_router
from app.routers import evidence as evidence_router
from app.routers import filesystem as filesystem_router
from app.routers import search as search_router
from app.routers import stats as stats_router
from app.routers import validation as validation_router


@dataclass
class FakeUser:
    id: str = "test-user"
    username: str = "analyst"
    role: str = "analyst"
    is_active: bool = True


class FakeQuery:
    def __init__(self, rows: list[Any]):
        self.rows = rows

    def filter(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def offset(self, *_args, **_kwargs):
        return self

    def all(self):
        return list(self.rows)

    def first(self):
        return self.rows[0] if self.rows else None

    def count(self):
        return len(self.rows)

    def yield_per(self, *_args, **_kwargs):
        return iter(self.rows)


class FakeDb:
    def __init__(self, case_id: uuid.UUID):
        self.case = Case(id=case_id, name="Case A", description=None)
        self.cases: list[Case] = [self.case]
        self.sources: list[EvidenceSource] = []
        self.jobs: list[IngestJob] = []
        self.file_hash_rows: list[Any] = []

    def get(self, model, key):
        if model is Case:
            for row in self.cases:
                if str(key) == str(row.id):
                    return row
        if model is IngestJob:
            for row in self.jobs:
                if str(row.id) == str(key):
                    return row
        if model is EvidenceSource:
            for row in self.sources:
                if str(row.id) == str(key):
                    return row
        return None

    def add(self, obj):
        if isinstance(obj, EvidenceSource):
            if not obj.id:
                obj.id = uuid.uuid4()
            obj.created_at = datetime.now(UTC)
            self.sources.append(obj)
        elif isinstance(obj, Case):
            if not obj.id:
                obj.id = uuid.uuid4()
            obj.created_at = datetime.now(UTC)
            self.cases.append(obj)
        elif isinstance(obj, IngestJob):
            if not obj.id:
                obj.id = uuid.uuid4()
            obj.created_at = datetime.now(UTC)
            self.jobs.append(obj)

    def flush(self):
        for source in self.sources:
            if not source.id:
                source.id = uuid.uuid4()

    def query(self, *models):
        if len(models) == 3 and models[0] is IngestJob and models[1] is EvidenceSource and models[2] is Case:
            return FakeAdminJobsQuery(
                [
                    (job, next((s for s in self.sources if s.id == job.evidence_source_id), None), self.case)
                    for job in self.jobs
                ]
            )
        model = models[0]
        if model is EvidenceSource:
            return FakeQuery(self.sources)
        if model is IngestJob:
            return FakeQuery(self.jobs)
        if model is EvidenceFileHash:
            return FakeQuery(self.file_hash_rows)
        return FakeQuery([])

    def commit(self):
        now = datetime.now(UTC)
        for case in self.cases:
            case.created_at = now
        for source in self.sources:
            source.created_at = now
        for job in self.jobs:
            job.created_at = now
        return None

    def refresh(self, _obj):
        _obj.created_at = datetime.now(UTC)
        return None

    def rollback(self):
        return None


class FakeAdminJobsQuery:
    def __init__(self, rows: list[tuple[IngestJob, EvidenceSource | None, Case]]):
        self.rows = [row for row in rows if row[1] is not None]
        self.limit_n: int | None = None

    def join(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def filter(self, *expressions):
        for expr in expressions:
            left = str(getattr(expr, "left", ""))
            right = getattr(getattr(expr, "right", None), "value", None)
            if right is None:
                continue
            if "ingest_jobs.status" in left:
                self.rows = [row for row in self.rows if row[0].status == right]
            elif "ingest_jobs.error_code" in left:
                self.rows = [row for row in self.rows if row[0].error_code == right]
            elif "ingest_jobs.error_stage" in left:
                self.rows = [row for row in self.rows if row[0].error_stage == right]
            elif "cases.id" in left:
                self.rows = [row for row in self.rows if str(row[2].id) == str(right)]
        return self

    def limit(self, n: int):
        self.limit_n = n
        return self

    def all(self):
        if self.limit_n is None:
            return self.rows
        return self.rows[: self.limit_n]


def _override_auth():
    return FakeUser()


def _override_admin_auth():
    return FakeUser(role="administrator")


def test_upload_then_list_jobs_workflow(monkeypatch, tmp_path: Path):
    case_id = uuid.uuid4()
    db = FakeDb(case_id)
    queued: list[tuple[str, list[str]]] = []

    monkeypatch.setattr(evidence_router.settings, "evidence_root", str(tmp_path))

    def fake_send_task(name: str, args: list[str], **_kwargs):
        queued.append((name, args))
        return SimpleNamespace(id=args[0])

    monkeypatch.setattr(evidence_router.celery_app, "send_task", fake_send_task)

    upload = UploadFile(filename="host-security.evtx", file=BytesIO(b"demo evtx bytes"))
    job = run(evidence_router.upload_evidence(case_id=case_id, file=upload, hostname=None, platform=None, db=db))
    assert job.status == "pending"
    assert queued and queued[0][0] == "worker.tasks.ingest.process_evidence_package"

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = _override_admin_auth
    try:
        client = TestClient(app)
        list_res = client.get(f"/api/v1/cases/{case_id}/evidence/{db.sources[0].id}/jobs")
        assert list_res.status_code == 200, list_res.text
        jobs = list_res.json()
        assert len(jobs) == 1
        assert jobs[0]["id"] == str(job.id)
        assert jobs[0]["error_code"] is None
        assert jobs[0]["error_stage"] is None
    finally:
        app.dependency_overrides.clear()


def test_upload_filename_path_traversal_is_contained(monkeypatch, tmp_path: Path):
    # H1 regression: a traversal filename must not write outside evidence_root.
    case_id = uuid.uuid4()
    db = FakeDb(case_id)
    evidence_root = tmp_path / "evidence"
    queued: list[tuple[str, list[str]]] = []

    monkeypatch.setattr(evidence_router.settings, "evidence_root", str(evidence_root))

    def fake_send_task(name: str, args: list[str], **_kwargs):
        queued.append((name, args))
        return SimpleNamespace(id=args[0])

    monkeypatch.setattr(evidence_router.celery_app, "send_task", fake_send_task)

    upload = UploadFile(filename="../../../pwned.txt", file=BytesIO(b"demo"))
    job = run(evidence_router.upload_evidence(case_id=case_id, file=upload, hostname=None, platform=None, db=db))

    assert job.status == "pending"
    assert not (tmp_path / "pwned.txt").exists()
    assert not (tmp_path.parent / "pwned.txt").exists()
    source_id = db.sources[0].id
    assert (evidence_root / str(case_id) / str(source_id) / "pwned.txt").is_file()


def test_upload_filename_that_basenames_empty_is_rejected(monkeypatch, tmp_path: Path):
    # H1 regression: a pure-traversal filename (no real basename) is a 400, not a 500.
    case_id = uuid.uuid4()
    db = FakeDb(case_id)
    monkeypatch.setattr(evidence_router.settings, "evidence_root", str(tmp_path / "evidence"))

    upload = UploadFile(filename="../../..", file=BytesIO(b"x"))
    with pytest.raises(HTTPException) as exc:
        run(evidence_router.upload_evidence(case_id=case_id, file=upload, hostname=None, platform=None, db=db))
    assert exc.value.status_code == 400


def test_validation_ingest_sample_queues_fast_mode_manifest(monkeypatch, tmp_path: Path):
    case_id = uuid.uuid4()
    db = FakeDb(case_id)
    sample_zip = tmp_path / "c.zip"
    sample_zip.write_bytes(b"zip")
    captured: dict[str, Any] = {}

    monkeypatch.setattr(validation_router.settings, "enable_validation_api", True)
    monkeypatch.setattr(validation_router.settings, "samples_root", str(tmp_path))
    
    async def fake_create_ingest_source(**kwargs):
        captured.update(kwargs)
        return IngestJob(
            id=uuid.uuid4(),
            evidence_source_id=uuid.uuid4(),
            status="pending",
            progress=0,
            message="Queued for ingest",
            created_at=datetime.now(UTC),
        )

    monkeypatch.setattr(validation_router, "_create_ingest_source", fake_create_ingest_source)

    result = run(
        validation_router.ingest_sample_package(
            sample="c",
            case_name="Validation fast",
            ingest_mode="fast",
            min_filesystem_nodes=1,
            db=db,
        )
    )

    assert result.sample == "c"
    assert captured["case_id"] in {case.id for case in db.cases}
    assert captured["manifest_overrides"] == {"ff_validation_mode": "fast"}


def test_cancel_job_sets_structured_error_fields():
    case_id = uuid.uuid4()
    source_id = uuid.uuid4()
    job_id = uuid.uuid4()
    db = FakeDb(case_id)
    db.sources.append(
        EvidenceSource(
            id=source_id,
            case_id=case_id,
            hostname="host-cancel",
            collector="import",
            source_type="endpoint",
            platform="windows",
            package_path="/tmp/evidence.zip",
            status="running",
        )
    )
    db.jobs.append(
        IngestJob(
            id=job_id,
            evidence_source_id=source_id,
            status="running",
            progress=42,
            message="In progress",
        )
    )

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = _override_admin_auth
    try:
        client = TestClient(app)
        response = client.post(f"/api/v1/jobs/{job_id}/cancel")
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["status"] == "failed"
        assert payload["error_code"] == "cancelled"
        assert payload["error_stage"] == "cancel"
    finally:
        app.dependency_overrides.clear()


def test_admin_jobs_filters_by_error_taxonomy(monkeypatch):
    case_id = uuid.uuid4()
    source_a = uuid.uuid4()
    source_b = uuid.uuid4()
    db = FakeDb(case_id)
    db.sources.extend(
        [
            EvidenceSource(
                id=source_a,
                case_id=case_id,
                hostname="host-a",
                collector="import",
                source_type="endpoint",
                platform="windows",
                package_path="/tmp/a.zip",
                status="failed",
            ),
            EvidenceSource(
                id=source_b,
                case_id=case_id,
                hostname="host-b",
                collector="import",
                source_type="endpoint",
                platform="windows",
                package_path="/tmp/b.zip",
                status="failed",
            ),
        ]
    )
    db.jobs.extend(
        [
            IngestJob(
                id=uuid.uuid4(),
                evidence_source_id=source_a,
                status="failed",
                progress=65,
                message="manifest invalid",
                error_code="manifest_invalid",
                error_stage="parse",
                created_at=datetime.now(UTC),
            ),
            IngestJob(
                id=uuid.uuid4(),
                evidence_source_id=source_b,
                status="failed",
                progress=72,
                message="timeline parse failed",
                error_code="timeline_parse_failed",
                error_stage="timeline",
                created_at=datetime.now(UTC),
            ),
        ]
    )

    monkeypatch.setattr(admin_router.settings, "enable_admin_api", True)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = _override_admin_auth
    try:
        client = TestClient(app)
        response = client.get("/api/v1/admin/jobs?status=failed&error_code=manifest_invalid&error_stage=parse")
        assert response.status_code == 200, response.text
        rows = response.json()
        assert len(rows) == 1
        assert rows[0]["error_code"] == "manifest_invalid"
        assert rows[0]["error_stage"] == "parse"
    finally:
        app.dependency_overrides.clear()


def test_filesystem_preview_and_download_workflow(monkeypatch, tmp_path: Path):
    case_id = uuid.uuid4()
    source_id = uuid.uuid4()
    node_id = uuid.uuid4()
    db = FakeDb(case_id)

    src = EvidenceSource(
        id=source_id,
        case_id=case_id,
        hostname="host-a",
        collector="import",
        source_type="endpoint",
        platform="windows",
        package_path=str(tmp_path),
        status="completed",
    )
    node = FilesystemNode(
        id=node_id,
        evidence_source_id=source_id,
        full_path="C/Users/Alice/note.txt",
        name="note.txt",
        is_directory=False,
        size=11,
        is_deleted=False,
        parent_path="C/Users/Alice",
    )
    file_path = tmp_path / "note.txt"
    file_path.write_bytes(b"hello world")

    monkeypatch.setattr(filesystem_router, "_get_source_and_node", lambda *_args, **_kwargs: (src, node))
    monkeypatch.setattr(filesystem_router, "_resolve_node_file", lambda *_args, **_kwargs: file_path)

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = _override_auth
    try:
        client = TestClient(app)

        preview = client.get(
            f"/api/v1/cases/{case_id}/sources/{source_id}/filesystem/{node_id}/preview?offset=0&length=5"
        )
        assert preview.status_code == 200, preview.text
        body = preview.json()
        assert body["ascii"] == "hello"
        assert body["length"] == 5

        download = client.get(f"/api/v1/cases/{case_id}/sources/{source_id}/filesystem/{node_id}/download")
        assert download.status_code == 200, download.text
        assert download.content == b"hello world"
    finally:
        app.dependency_overrides.clear()


def test_timeline_accepts_large_forensic_page_limit():
    case_id = uuid.uuid4()
    source_id = uuid.uuid4()
    db = FakeDb(case_id)
    db.sources.append(
        EvidenceSource(
            id=source_id,
            case_id=case_id,
            hostname="host-a",
            collector="import",
            source_type="endpoint",
            platform="windows",
            package_path="/tmp/evidence.zip",
            status="completed",
        )
    )

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = _override_auth
    try:
        client = TestClient(app)
        response = client.get(f"/api/v1/cases/{case_id}/sources/{source_id}/timeline?limit=10000")
        assert response.status_code == 200, response.text
        assert response.json() == []
    finally:
        app.dependency_overrides.clear()


def test_filesystem_hash_lookup_workflow(monkeypatch, tmp_path: Path):
    case_id = uuid.uuid4()
    source_id = uuid.uuid4()
    node_id = uuid.uuid4()
    db = FakeDb(case_id)

    src = EvidenceSource(
        id=source_id,
        case_id=case_id,
        hostname="host-b",
        collector="import",
        source_type="endpoint",
        platform="windows",
        package_path=str(tmp_path),
        status="completed",
    )
    node = FilesystemNode(
        id=node_id,
        evidence_source_id=source_id,
        full_path="C/Users/Bob/file.bin",
        name="file.bin",
        is_directory=False,
        size=3,
        is_deleted=False,
        parent_path="C/Users/Bob",
    )
    bin_path = tmp_path / "file.bin"
    bin_path.write_bytes(b"\x01\x02\x03")

    db.file_hash_rows = [
        SimpleNamespace(
            sha256="a" * 64,
            sha1="b" * 40,
            md5="c" * 32,
        )
    ]
    monkeypatch.setattr(filesystem_router, "_get_source_and_node", lambda *_args, **_kwargs: (src, node))
    monkeypatch.setattr(filesystem_router, "_resolve_node_file", lambda *_args, **_kwargs: bin_path)

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = _override_auth
    try:
        client = TestClient(app)
        res = client.get(f"/api/v1/cases/{case_id}/sources/{source_id}/filesystem/{node_id}/hashes")
        assert res.status_code == 200, res.text
        payload = res.json()
        assert payload["available"] is True
        assert payload["sha256"] == "a" * 64
    finally:
        app.dependency_overrides.clear()


class _ScalarQuery:
    def __init__(self, scalar_value: int):
        self.scalar_value = scalar_value

    def filter(self, *_args, **_kwargs):
        return self

    def scalar(self):
        return self.scalar_value


class _EventTypesQuery:
    def __init__(self, rows: list[tuple[str]]):
        self.rows = rows

    def filter(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def all(self):
        return self.rows


class StatsDbStub:
    def __init__(self, case_id: uuid.UUID, source_id: uuid.UUID):
        self.case_id = case_id
        self.source_id = source_id
        self.source = EvidenceSource(
            id=source_id,
            case_id=case_id,
            hostname="stat-host",
            collector="import",
            source_type="endpoint",
            platform="windows",
            package_path="/tmp",
            status="completed",
        )
        self._scalar_idx = 0
        self.scalar_values = [12, 4, 7, 3, 2, 1]
        self.event_types = [("4624",), ("4688",)]

    def query(self, *models):
        first = models[0]
        if first is EvidenceSource:
            return FakeQuery([self.source])
        if len(models) == 1 and str(first).startswith("count("):
            val = self.scalar_values[self._scalar_idx]
            self._scalar_idx += 1
            return _ScalarQuery(val)
        return _EventTypesQuery(self.event_types)

    def execute(self, *_args, **_kwargs):
        return SimpleNamespace(
            fetchone=lambda: ("2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z", 86_400),
            fetchall=lambda: [("2026-01-01T00:00:00Z", 5), ("2026-01-02T00:00:00Z", 3)],
        )


def test_stats_and_histogram_routes():
    case_id = uuid.uuid4()
    source_id = uuid.uuid4()
    db = StatsDbStub(case_id, source_id)

    stats = stats_router.get_source_stats(case_id=case_id, source_id=source_id, db=db)
    assert stats.timeline_count == 12
    assert stats.filesystem_count == 4
    assert stats.entity_count == 7
    assert stats.sigma_detection_count == 3
    assert stats.event_types == ["4624", "4688"]

    hist = stats_router.get_timeline_histogram(case_id=case_id, source_id=source_id, db=db)
    assert hist["granularity"] == "day"
    assert hist["total"] == 8
    assert len(hist["buckets"]) == 2


class SearchDbStub:
    def __init__(self, source: EvidenceSource | None):
        self.source = source

    def query(self, model):
        if model is EvidenceSource and self.source:
            return FakeQuery([self.source])
        return FakeQuery([])


class SearchFallbackDbStub:
    def __init__(
        self,
        source: EvidenceSource,
        timeline_rows: list[Any],
        filesystem_rows: list[Any],
        entity_rows: list[Any],
    ):
        self.source = source
        self.timeline_rows = timeline_rows
        self.filesystem_rows = filesystem_rows
        self.entity_rows = entity_rows

    def query(self, model):
        if model is EvidenceSource:
            return FakeQuery([self.source])
        if model is search_router.TimelineEvent:
            return FakeQuery(self.timeline_rows)
        if model is search_router.FilesystemNode:
            return FakeQuery(self.filesystem_rows)
        if model is search_router.Entity:
            return FakeQuery(self.entity_rows)
        return FakeQuery([])


def test_search_rejects_running_source():
    case_id = uuid.uuid4()
    source_id = uuid.uuid4()
    source = EvidenceSource(
        id=source_id,
        case_id=case_id,
        hostname="run-host",
        collector="import",
        source_type="endpoint",
        platform="windows",
        package_path="/tmp",
        status="running",
    )
    db = SearchDbStub(source)
    with pytest.raises(HTTPException) as exc:
        search_router.global_search(case_id=case_id, source_id=source_id, q="cmd", db=db)
    assert exc.value.status_code == 409


def test_search_fallback_short_query_limits_to_filesystem(monkeypatch):
    case_id = uuid.uuid4()
    source_id = uuid.uuid4()
    source = EvidenceSource(
        id=source_id,
        case_id=case_id,
        hostname="host-short",
        collector="import",
        source_type="endpoint",
        platform="linux",
        package_path="/tmp",
        status="completed",
    )
    db = SearchFallbackDbStub(
        source=source,
        timeline_rows=[SimpleNamespace(id=uuid.uuid4(), evidence_source_id=source_id)],
        filesystem_rows=[
            FilesystemNode(
                id=uuid.uuid4(),
                evidence_source_id=source_id,
                full_path="/var/log/auth.log",
                name="auth.log",
                is_directory=False,
                size=100,
                is_deleted=False,
                parent_path="/var/log",
            )
        ],
        entity_rows=[SimpleNamespace(id=uuid.uuid4(), evidence_source_id=source_id)],
    )
    monkeypatch.setattr(search_router, "opensearch_global_search", lambda *_args, **_kwargs: None)

    result = search_router.global_search(case_id=case_id, source_id=source_id, q="a", db=db)
    assert result.timeline == []
    assert len(result.filesystem) == 1
    assert result.entities == []


def test_search_fallback_regular_query_includes_all_sections(monkeypatch):
    case_id = uuid.uuid4()
    source_id = uuid.uuid4()
    source = EvidenceSource(
        id=source_id,
        case_id=case_id,
        hostname="host-regular",
        collector="import",
        source_type="endpoint",
        platform="linux",
        package_path="/tmp",
        status="completed",
    )
    timeline_event = search_router.TimelineEvent(
        id=uuid.uuid4(),
        evidence_source_id=source_id,
        timestamp_utc=datetime.now(UTC),
        event_type="4688",
        artifact_type="evtx",
        summary="Process start",
        original_source="Security.evtx",
        data={},
        entity_refs=[],
        sigma_hits=[],
    )
    entity = search_router.Entity(
        id=uuid.uuid4(),
        evidence_source_id=source_id,
        entity_type="user",
        display_name="alice",
        attributes={},
    )
    db = SearchFallbackDbStub(
        source=source,
        timeline_rows=[timeline_event],
        filesystem_rows=[
            FilesystemNode(
                id=uuid.uuid4(),
                evidence_source_id=source_id,
                full_path="/var/log/auth.log",
                name="auth.log",
                is_directory=False,
                size=100,
                is_deleted=False,
                parent_path="/var/log",
            )
        ],
        entity_rows=[entity],
    )
    monkeypatch.setattr(search_router, "opensearch_global_search", lambda *_args, **_kwargs: None)

    result = search_router.global_search(case_id=case_id, source_id=source_id, q="auth", db=db)
    assert len(result.timeline) == 1
    assert len(result.filesystem) == 1
    assert len(result.entities) == 1


def test_search_metrics_snapshot_tracks_fallback_queries(monkeypatch):
    case_id = uuid.uuid4()
    source_id = uuid.uuid4()
    source = EvidenceSource(
        id=source_id,
        case_id=case_id,
        hostname="host-metrics",
        collector="import",
        source_type="endpoint",
        platform="linux",
        package_path="/tmp",
        status="completed",
    )
    search_router._SEARCH_METRICS.clear()
    db = SearchFallbackDbStub(
        source=source,
        timeline_rows=[],
        filesystem_rows=[
            FilesystemNode(
                id=uuid.uuid4(),
                evidence_source_id=source_id,
                full_path="/var/log/syslog",
                name="syslog",
                is_directory=False,
                size=100,
                is_deleted=False,
                parent_path="/var/log",
            )
        ],
        entity_rows=[],
    )
    monkeypatch.setattr(search_router, "opensearch_global_search", lambda *_args, **_kwargs: None)

    search_router.global_search(case_id=case_id, source_id=source_id, q="a", db=db)
    search_router.global_search(case_id=case_id, source_id=source_id, q="auth", db=db)
    metrics = search_router.search_metrics_snapshot()

    assert metrics["total_queries"] == 2
    assert metrics["fallback_hits"] == 2
    assert metrics["fallback_short_queries"] == 1


class HashesDbStub:
    def __init__(self, source: EvidenceSource, rows: list[Any]):
        self.source = source
        self.rows = rows

    def query(self, *models):
        first = models[0]
        if first is EvidenceSource:
            return FakeQuery([self.source])
        if first is EvidenceFileHash:
            return FakeQuery(self.rows)
        return FakeQuery(self.rows)


def test_evidence_hash_status_and_export():
    case_id = uuid.uuid4()
    source_id = uuid.uuid4()
    source = EvidenceSource(
        id=source_id,
        case_id=case_id,
        hostname="host-c",
        collector="import",
        source_type="endpoint",
        platform="windows",
        package_path="/tmp",
        status="completed",
        sha256="1" * 64,
        sha1="2" * 40,
        md5="3" * 32,
        hash_status="completed",
        hash_file_count=2,
        yara_status="completed",
        yara_match_count=0,
        yara_file_count=2,
    )
    rows = [
        SimpleNamespace(
            relative_path="C/a.txt",
            sha256="a" * 64,
            sha1="b" * 40,
            md5="c" * 32,
            file_size=10,
            computed_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    ]
    db = HashesDbStub(source, rows)

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = _override_auth
    try:
        client = TestClient(app)
        status_res = client.get(f"/api/v1/cases/{case_id}/evidence/{source_id}/hashes")
        assert status_res.status_code == 200, status_res.text
        status = status_res.json()
        assert status["hash_status"] == "completed"
        assert status["hashed_files_in_db"] == 1

        export_res = client.get(f"/api/v1/cases/{case_id}/evidence/{source_id}/hashes/export")
        assert export_res.status_code == 200, export_res.text
        assert "text/csv" in export_res.headers.get("content-type", "")
        assert "path,sha256,sha1,md5,size_bytes,computed_at" in export_res.text
        assert "C/a.txt" in export_res.text
    finally:
        app.dependency_overrides.clear()
