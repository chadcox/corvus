from __future__ import annotations

import threading

import pytest

from worker.tasks import recovery

JOB_A = "11111111-1111-1111-1111-111111111111"
JOB_B = "22222222-2222-2222-2222-222222222222"
SOURCE_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
SOURCE_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class FakeSession:
    """Records the statements reconciliation issues against the database."""

    def __init__(self, rows=(), fail_on: str | None = None, updated_rows=None):
        self.rows = list(rows)
        self.fail_on = fail_on
        # None = the UPDATE changes exactly the rows it targeted.
        self.updated_rows = updated_rows
        self.statements: list[tuple[str, dict | None]] = []
        self.events: list[str] = []
        self.closed = False

    def execute(self, statement, params=None):
        sql = str(statement)
        self.statements.append((sql, params))
        self.events.append(sql.split()[0] + " " + sql.split()[1])
        if self.fail_on and self.fail_on in sql:
            raise RuntimeError("database unavailable")
        if "UPDATE ingest_jobs" in sql:
            if self.updated_rows is not None:
                return FakeResult(list(self.updated_rows))
            targeted = set((params or {}).get("job_ids", []))
            return FakeResult([row for row in self.rows if str(row[0]) in targeted])
        if sql.strip().startswith("SELECT"):
            return FakeResult(self.rows)
        return FakeResult([])

    def commit(self):
        self.events.append("commit")

    def rollback(self):
        self.events.append("rollback")

    def close(self):
        self.closed = True

    @property
    def committed(self) -> bool:
        return "commit" in self.events

    def sql_for(self, fragment: str):
        return [(sql, params) for sql, params in self.statements if fragment in sql]


class FakeInspector:
    """Minimal stand-in for ``celery_app.control.inspect()``."""

    def __init__(self, active=None, reserved=None, scheduled=None):
        self._buckets = {"active": active, "reserved": reserved, "scheduled": scheduled}
        self.calls: list[str] = []

    def _reply(self, bucket):
        self.calls.append(bucket)
        return self._buckets[bucket]

    def active(self):
        return self._reply("active")

    def reserved(self):
        return self._reply("reserved")

    def scheduled(self):
        return self._reply("scheduled")


class ExplodingInspector:
    def active(self):
        raise AssertionError("inspector must not be probed")

    reserved = active
    scheduled = active


def _ingest_entry(task_id: str) -> dict:
    return {"id": task_id, "name": recovery.INGEST_TASK_NAME}


def _install_session(monkeypatch, session: FakeSession) -> FakeSession:
    monkeypatch.setattr(recovery, "get_session", lambda: session)
    return session


# --- liveness probe parsing -------------------------------------------------


def test_live_ids_collects_active_reserved_and_scheduled():
    inspector = FakeInspector(
        active={"worker-a": [_ingest_entry(JOB_A)]},
        reserved={"worker-b": [_ingest_entry(JOB_B)]},
        scheduled={"worker-b": [{"eta": "later", "request": _ingest_entry("job-c")}]},
    )
    assert recovery.live_ingest_task_ids(inspector) == {JOB_A, JOB_B, "job-c"}


def test_live_ids_ignores_non_ingest_tasks():
    inspector = FakeInspector(
        active={"worker-a": [{"id": JOB_A, "name": "worker.tasks.hash_evidence.hash_evidence_files"}]},
        reserved={"worker-a": []},
        scheduled={"worker-a": []},
    )
    assert recovery.live_ingest_task_ids(inspector) == set()


def test_live_ids_raises_when_no_worker_replies():
    inspector = FakeInspector(active=None, reserved=None, scheduled=None)
    with pytest.raises(recovery.InspectUnavailable):
        recovery.live_ingest_task_ids(inspector)


def test_live_ids_empty_reply_is_available():
    inspector = FakeInspector(active={"worker-a": []}, reserved=None, scheduled=None)
    assert recovery.live_ingest_task_ids(inspector) == set()


# --- reconciliation decisions ----------------------------------------------


def test_active_job_is_preserved(monkeypatch):
    session = _install_session(monkeypatch, FakeSession(rows=[(JOB_A, SOURCE_A)]))
    inspector = FakeInspector(active={"worker-b": [_ingest_entry(JOB_A)]})

    assert recovery.reconcile_orphaned_ingest_jobs(inspector=inspector) == 0
    assert session.sql_for("UPDATE ingest_jobs") == []
    assert session.sql_for("UPDATE evidence_sources") == []
    assert session.closed is True


def test_orphan_job_failed_with_taxonomy(monkeypatch):
    session = _install_session(monkeypatch, FakeSession(rows=[(JOB_A, SOURCE_A)]))
    inspector = FakeInspector(active={"worker-a": []})

    assert recovery.reconcile_orphaned_ingest_jobs(inspector=inspector) == 1

    _, params = session.sql_for("UPDATE ingest_jobs")[0]
    assert params["job_ids"] == [JOB_A]
    assert params["error_code"] == "interrupted"
    assert params["error_stage"] == "worker_restart"
    assert params["message"] == recovery.RECONCILE_MESSAGE
    assert session.sql_for("UPDATE evidence_sources")[0][1]["source_ids"] == [SOURCE_A]
    assert session.committed is True


def test_mixed_batch_fails_only_unclaimed_jobs(monkeypatch):
    session = _install_session(
        monkeypatch, FakeSession(rows=[(JOB_A, SOURCE_A), (JOB_B, SOURCE_B)])
    )
    inspector = FakeInspector(active={"worker-b": [_ingest_entry(JOB_B)]})

    assert recovery.reconcile_orphaned_ingest_jobs(inspector=inspector) == 1

    _, params = session.sql_for("UPDATE ingest_jobs")[0]
    assert params["job_ids"] == [JOB_A]
    assert session.sql_for("UPDATE evidence_sources")[0][1]["source_ids"] == [SOURCE_A]


def test_source_kept_when_another_job_on_it_is_live(monkeypatch):
    session = _install_session(
        monkeypatch, FakeSession(rows=[(JOB_A, SOURCE_A), (JOB_B, SOURCE_A)])
    )
    inspector = FakeInspector(active={"worker-b": [_ingest_entry(JOB_B)]})

    assert recovery.reconcile_orphaned_ingest_jobs(inspector=inspector) == 1
    assert session.sql_for("UPDATE ingest_jobs")[0][1]["job_ids"] == [JOB_A]
    # SOURCE_A still has a live job, so its status must not be failed.
    assert session.sql_for("UPDATE evidence_sources") == []


def test_non_ingest_active_task_does_not_shield_a_job(monkeypatch):
    session = _install_session(monkeypatch, FakeSession(rows=[(JOB_A, SOURCE_A)]))
    inspector = FakeInspector(
        active={"worker-a": [{"id": JOB_A, "name": "worker.tasks.yara_scan.scan_evidence"}]}
    )

    assert recovery.reconcile_orphaned_ingest_jobs(inspector=inspector) == 1
    assert session.sql_for("UPDATE ingest_jobs")[0][1]["job_ids"] == [JOB_A]


def test_no_running_jobs_skips_the_probe(monkeypatch):
    session = _install_session(monkeypatch, FakeSession(rows=[]))

    assert recovery.reconcile_orphaned_ingest_jobs(inspector=ExplodingInspector()) == 0
    assert session.sql_for("UPDATE ingest_jobs") == []
    assert session.closed is True


# --- probe failure fallbacks ------------------------------------------------


def test_inspect_failure_skips_by_default(monkeypatch):
    monkeypatch.setattr(recovery.settings, "worker_reconcile_on_inspect_failure", "skip")
    session = _install_session(monkeypatch, FakeSession(rows=[(JOB_A, SOURCE_A)]))
    inspector = FakeInspector(active=None, reserved=None, scheduled=None)

    assert recovery.reconcile_orphaned_ingest_jobs(inspector=inspector) == 0
    assert session.sql_for("UPDATE ingest_jobs") == []


def test_inspect_failure_can_fall_back_to_failing_jobs(monkeypatch):
    monkeypatch.setattr(recovery.settings, "worker_reconcile_on_inspect_failure", "fail")
    session = _install_session(monkeypatch, FakeSession(rows=[(JOB_A, SOURCE_A)]))
    inspector = FakeInspector(active=None, reserved=None, scheduled=None)

    assert recovery.reconcile_orphaned_ingest_jobs(inspector=inspector) == 1
    assert session.sql_for("UPDATE ingest_jobs")[0][1]["job_ids"] == [JOB_A]


def test_unknown_inspect_failure_action_is_treated_as_skip(monkeypatch):
    monkeypatch.setattr(recovery.settings, "worker_reconcile_on_inspect_failure", "bogus")
    session = _install_session(monkeypatch, FakeSession(rows=[(JOB_A, SOURCE_A)]))

    class RaisingInspector:
        def active(self):
            raise RuntimeError("broker down")

        reserved = active
        scheduled = active

    assert recovery.reconcile_orphaned_ingest_jobs(inspector=RaisingInspector()) == 0
    assert session.sql_for("UPDATE ingest_jobs") == []


def test_database_error_rolls_back_and_reports_zero(monkeypatch):
    session = _install_session(
        monkeypatch, FakeSession(rows=[(JOB_A, SOURCE_A)], fail_on="UPDATE ingest_jobs")
    )
    inspector = FakeInspector(active={"worker-a": []})

    assert recovery.reconcile_orphaned_ingest_jobs(inspector=inspector) == 0
    # The failing UPDATE is rolled back and nothing is committed.
    assert session.events[-1] == "rollback"
    assert session.committed is False
    assert session.closed is True


def test_read_snapshot_is_released_before_the_probe(monkeypatch):
    session = _install_session(monkeypatch, FakeSession(rows=[(JOB_A, SOURCE_A)]))
    inspector = FakeInspector(active={"worker-a": []})

    recovery.reconcile_orphaned_ingest_jobs(inspector=inspector)
    # SELECT, release, UPDATE jobs, UPDATE sources, commit.
    assert session.events[0].startswith("SELECT")
    assert session.events[1] == "rollback"
    assert session.events[-1] == "commit"


def test_job_that_finished_before_the_update_leaves_its_source_alone(monkeypatch):
    # The job completed between the read and the probe, so the guarded UPDATE
    # changes no rows and the source must not be failed.
    session = _install_session(
        monkeypatch, FakeSession(rows=[(JOB_A, SOURCE_A)], updated_rows=[])
    )
    inspector = FakeInspector(active={"worker-a": []})

    assert recovery.reconcile_orphaned_ingest_jobs(inspector=inspector) == 0
    assert session.sql_for("UPDATE evidence_sources") == []
    assert session.committed is True


# --- startup grace window ---------------------------------------------------


def test_startup_reconciliation_waits_for_the_grace_window():
    slept: list[float] = []
    ran: list[str] = []

    def runner() -> int:
        ran.append("ran")
        assert slept == [7.5]
        return 0

    thread = recovery.start_startup_reconciliation(
        delay_seconds=7.5, sleeper=slept.append, runner=runner
    )
    thread.join(timeout=5)
    assert isinstance(thread, threading.Thread)
    assert thread.is_alive() is False
    assert ran == ["ran"]


def test_startup_delay_is_clamped_and_never_negative():
    slept: list[float] = []

    thread = recovery.start_startup_reconciliation(
        delay_seconds=10_000, sleeper=slept.append, runner=lambda: 0
    )
    thread.join(timeout=5)
    assert slept == [recovery.MAX_STARTUP_DELAY_SECONDS]

    slept.clear()
    thread = recovery.start_startup_reconciliation(
        delay_seconds=-5, sleeper=slept.append, runner=lambda: 0
    )
    thread.join(timeout=5)
    assert slept == []


def test_startup_reconciliation_swallows_runner_errors():
    def runner() -> int:
        raise RuntimeError("boom")

    thread = recovery.start_startup_reconciliation(
        delay_seconds=0, sleeper=lambda _: None, runner=runner
    )
    thread.join(timeout=5)
    assert thread.is_alive() is False


def test_startup_reconciliation_uses_configured_delay(monkeypatch):
    monkeypatch.setattr(recovery.settings, "worker_reconcile_startup_delay_seconds", 3)
    slept: list[float] = []

    thread = recovery.start_startup_reconciliation(sleeper=slept.append, runner=lambda: 0)
    thread.join(timeout=5)
    assert slept == [3.0]
