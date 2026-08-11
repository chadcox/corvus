from __future__ import annotations

import threading

import pytest

from worker.config import WorkerSettings
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
    """Minimal stand-in for ``celery_app.control.inspect()``.

    A bucket value of ``None`` is what Celery returns when nobody answered; a
    dict contains only the workers that answered in time.
    """

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


@pytest.fixture
def fail_unclaimed(monkeypatch):
    """Opt into the lossy legacy cleanup of jobs no worker claims."""
    monkeypatch.setattr(recovery.settings, "worker_reconcile_unclaimed_action", "fail")


# --- presence-only probe parsing --------------------------------------------


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


def test_live_ids_is_empty_when_no_worker_replies():
    # Silence yields no positive evidence; it is not an error and it is not
    # proof that any task is gone.
    inspector = FakeInspector(active=None, reserved=None, scheduled=None)
    assert recovery.live_ingest_task_ids(inspector) == set()


def test_live_ids_empty_reply_is_not_authoritative():
    # One idle worker answered. Absence of JOB_A from this set says nothing
    # about the workers that stayed silent.
    inspector = FakeInspector(active={"worker-a": []}, reserved=None, scheduled=None)
    assert recovery.live_ingest_task_ids(inspector) == set()


def test_live_ids_only_report_the_workers_that_answered():
    # worker-b holds JOB_B but did not answer, so it is simply missing from the
    # reply -- exactly how a partial Celery inspect result looks.
    inspector = FakeInspector(
        active={"worker-a": [_ingest_entry(JOB_A)]},
        reserved={"worker-a": []},
        scheduled={"worker-a": []},
    )
    assert recovery.live_ingest_task_ids(inspector) == {JOB_A}


# --- reconciliation decisions ----------------------------------------------


def test_claimed_job_is_preserved(monkeypatch):
    session = _install_session(monkeypatch, FakeSession(rows=[(JOB_A, SOURCE_A)]))
    inspector = FakeInspector(active={"worker-b": [_ingest_entry(JOB_A)]})

    assert recovery.reconcile_orphaned_ingest_jobs(inspector=inspector) == 0
    assert session.sql_for("UPDATE ingest_jobs") == []
    assert session.sql_for("UPDATE evidence_sources") == []
    assert session.closed is True


def test_claimed_job_is_preserved_even_when_failing_unclaimed(
    monkeypatch, fail_unclaimed
):
    session = _install_session(monkeypatch, FakeSession(rows=[(JOB_A, SOURCE_A)]))
    inspector = FakeInspector(reserved={"worker-b": [_ingest_entry(JOB_A)]})

    assert recovery.reconcile_orphaned_ingest_jobs(inspector=inspector) == 0
    assert session.sql_for("UPDATE ingest_jobs") == []


# --- default: absence is never treated as proof -----------------------------


def test_idle_responder_does_not_orphan_a_silent_worker_job(monkeypatch):
    """An answering idle worker plus a silent worker that holds the ingest.

    This is the multi-worker restart case: the probe comes back complete-looking
    but the worker actually running JOB_A never replied. Nothing may be failed.
    """
    session = _install_session(monkeypatch, FakeSession(rows=[(JOB_A, SOURCE_A)]))
    inspector = FakeInspector(
        active={"worker-idle": []},
        reserved={"worker-idle": []},
        scheduled={"worker-idle": []},
    )

    assert recovery.reconcile_orphaned_ingest_jobs(inspector=inspector) == 0
    assert session.sql_for("UPDATE ingest_jobs") == []
    assert session.sql_for("UPDATE evidence_sources") == []
    assert session.committed is False
    assert session.closed is True


def test_default_leaves_unclaimed_jobs_running_when_nobody_answers(monkeypatch):
    session = _install_session(
        monkeypatch, FakeSession(rows=[(JOB_A, SOURCE_A), (JOB_B, SOURCE_B)])
    )
    inspector = FakeInspector(active=None, reserved=None, scheduled=None)

    assert recovery.reconcile_orphaned_ingest_jobs(inspector=inspector) == 0
    assert session.sql_for("UPDATE ingest_jobs") == []
    assert session.sql_for("UPDATE evidence_sources") == []


def test_default_leaves_unclaimed_jobs_running_when_the_probe_raises(monkeypatch):
    class RaisingInspector:
        def active(self):
            raise RuntimeError("broker down")

        reserved = active
        scheduled = active

    session = _install_session(monkeypatch, FakeSession(rows=[(JOB_A, SOURCE_A)]))

    assert recovery.reconcile_orphaned_ingest_jobs(inspector=RaisingInspector()) == 0
    assert session.sql_for("UPDATE ingest_jobs") == []


def test_default_leaves_a_partially_claimed_batch_alone(monkeypatch):
    # JOB_B is claimed, JOB_A is not; the unproven one still keeps running.
    session = _install_session(
        monkeypatch, FakeSession(rows=[(JOB_A, SOURCE_A), (JOB_B, SOURCE_B)])
    )
    inspector = FakeInspector(active={"worker-b": [_ingest_entry(JOB_B)]})

    assert recovery.reconcile_orphaned_ingest_jobs(inspector=inspector) == 0
    assert session.sql_for("UPDATE ingest_jobs") == []


def test_unknown_unclaimed_action_falls_back_to_skip(monkeypatch):
    monkeypatch.setattr(recovery.settings, "worker_reconcile_unclaimed_action", "bogus")
    session = _install_session(monkeypatch, FakeSession(rows=[(JOB_A, SOURCE_A)]))
    inspector = FakeInspector(active={"worker-a": []})

    assert recovery.reconcile_orphaned_ingest_jobs(inspector=inspector) == 0
    assert session.sql_for("UPDATE ingest_jobs") == []


@pytest.mark.parametrize(
    "configured, expected",
    [
        ("fail", "fail"),
        ("FAIL", "fail"),
        (" skip ", "skip"),
        ("", "skip"),
        (None, "skip"),
        ("purge", "skip"),
    ],
)
def test_unclaimed_action_is_normalized(monkeypatch, configured, expected):
    monkeypatch.setattr(
        recovery.settings, "worker_reconcile_unclaimed_action", configured
    )
    assert recovery._unclaimed_action() == expected


def test_shipped_default_is_skip():
    assert recovery.DEFAULT_UNCLAIMED_ACTION == "skip"
    field = WorkerSettings.model_fields["worker_reconcile_unclaimed_action"]
    assert field.default == "skip"


# --- opt-in legacy cleanup of unclaimed jobs --------------------------------


def test_unclaimed_job_failed_with_taxonomy(monkeypatch, fail_unclaimed):
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


def test_mixed_batch_fails_only_unclaimed_jobs(monkeypatch, fail_unclaimed):
    session = _install_session(
        monkeypatch, FakeSession(rows=[(JOB_A, SOURCE_A), (JOB_B, SOURCE_B)])
    )
    inspector = FakeInspector(active={"worker-b": [_ingest_entry(JOB_B)]})

    assert recovery.reconcile_orphaned_ingest_jobs(inspector=inspector) == 1

    _, params = session.sql_for("UPDATE ingest_jobs")[0]
    assert params["job_ids"] == [JOB_A]
    assert session.sql_for("UPDATE evidence_sources")[0][1]["source_ids"] == [SOURCE_A]


def test_source_kept_when_another_job_on_it_is_live(monkeypatch, fail_unclaimed):
    session = _install_session(
        monkeypatch, FakeSession(rows=[(JOB_A, SOURCE_A), (JOB_B, SOURCE_A)])
    )
    inspector = FakeInspector(active={"worker-b": [_ingest_entry(JOB_B)]})

    assert recovery.reconcile_orphaned_ingest_jobs(inspector=inspector) == 1
    assert session.sql_for("UPDATE ingest_jobs")[0][1]["job_ids"] == [JOB_A]
    # SOURCE_A still has a live job, so its status must not be failed.
    assert session.sql_for("UPDATE evidence_sources") == []


def test_non_ingest_active_task_does_not_shield_a_job(monkeypatch, fail_unclaimed):
    session = _install_session(monkeypatch, FakeSession(rows=[(JOB_A, SOURCE_A)]))
    inspector = FakeInspector(
        active={"worker-a": [{"id": JOB_A, "name": "worker.tasks.yara_scan.scan_evidence"}]}
    )

    assert recovery.reconcile_orphaned_ingest_jobs(inspector=inspector) == 1
    assert session.sql_for("UPDATE ingest_jobs")[0][1]["job_ids"] == [JOB_A]


def test_silent_control_plane_fails_everything_when_opted_in(
    monkeypatch, fail_unclaimed
):
    # The documented cost of `fail`: with no reply at all, a live ingest on a
    # silent worker is failed anyway. This is why `skip` is the default.
    session = _install_session(monkeypatch, FakeSession(rows=[(JOB_A, SOURCE_A)]))
    inspector = FakeInspector(active=None, reserved=None, scheduled=None)

    assert recovery.reconcile_orphaned_ingest_jobs(inspector=inspector) == 1
    assert session.sql_for("UPDATE ingest_jobs")[0][1]["job_ids"] == [JOB_A]


def test_probe_error_fails_unclaimed_jobs_when_opted_in(monkeypatch, fail_unclaimed):
    class RaisingInspector:
        def active(self):
            raise RuntimeError("broker down")

        reserved = active
        scheduled = active

    session = _install_session(monkeypatch, FakeSession(rows=[(JOB_A, SOURCE_A)]))

    assert recovery.reconcile_orphaned_ingest_jobs(inspector=RaisingInspector()) == 1
    assert session.sql_for("UPDATE ingest_jobs")[0][1]["job_ids"] == [JOB_A]


# --- database interaction ---------------------------------------------------


def test_no_running_jobs_skips_the_probe(monkeypatch):
    session = _install_session(monkeypatch, FakeSession(rows=[]))

    assert recovery.reconcile_orphaned_ingest_jobs(inspector=ExplodingInspector()) == 0
    assert session.sql_for("UPDATE ingest_jobs") == []
    assert session.closed is True


def test_database_error_rolls_back_and_reports_zero(monkeypatch, fail_unclaimed):
    session = _install_session(
        monkeypatch, FakeSession(rows=[(JOB_A, SOURCE_A)], fail_on="UPDATE ingest_jobs")
    )
    inspector = FakeInspector(active={"worker-a": []})

    assert recovery.reconcile_orphaned_ingest_jobs(inspector=inspector) == 0
    # The failing UPDATE is rolled back and nothing is committed.
    assert session.events[-1] == "rollback"
    assert session.committed is False
    assert session.closed is True


def test_read_snapshot_is_released_before_the_probe(monkeypatch, fail_unclaimed):
    session = _install_session(monkeypatch, FakeSession(rows=[(JOB_A, SOURCE_A)]))
    inspector = FakeInspector(active={"worker-a": []})

    recovery.reconcile_orphaned_ingest_jobs(inspector=inspector)
    # SELECT, release, UPDATE jobs, UPDATE sources, commit.
    assert session.events[0].startswith("SELECT")
    assert session.events[1] == "rollback"
    assert session.events[-1] == "commit"


def test_job_that_finished_before_the_update_leaves_its_source_alone(
    monkeypatch, fail_unclaimed
):
    # The job completed between the read and the probe, so the guarded UPDATE
    # changes no rows and the source must not be failed.
    session = _install_session(
        monkeypatch, FakeSession(rows=[(JOB_A, SOURCE_A)], updated_rows=[])
    )
    inspector = FakeInspector(active={"worker-a": []})

    assert recovery.reconcile_orphaned_ingest_jobs(inspector=inspector) == 0
    assert session.sql_for("UPDATE evidence_sources") == []
    assert session.committed is True


# --- multi-worker cluster against the real Celery inspect plumbing ----------
#
# These use a real `celery.Celery().control.inspect()` object so the replies go
# through Celery's own `_prepare`/`flatten_reply` handling. Only the transport
# is stubbed: `control.broadcast` returns the per-node reply list a broker would
# have produced. That is a faithful reproduction of the reply *shape*, including
# the fact that a worker which does not answer in time is simply missing from
# it, but it is not a live two-worker broker test -- no broker runs here, so
# real timeout and network behaviour is not exercised.


def _celery_inspector(monkeypatch, replies):
    """Real Celery inspector whose broadcast returns `replies` per command."""
    celery = pytest.importorskip("celery")
    app = celery.Celery("corvus-reconcile-test", broker="memory://")
    inspector = app.control.inspect(timeout=0.01)

    def fake_broadcast(command, **kwargs):
        # Celery returns None when nothing arrived before the timeout, and a
        # list of {hostname: payload} for the nodes that did answer.
        return replies.get(command)

    monkeypatch.setattr(app.control, "broadcast", fake_broadcast)
    return inspector


def test_real_inspect_reply_reports_the_worker_that_answered(monkeypatch):
    inspector = _celery_inspector(
        monkeypatch,
        {
            "active": [{"worker-a": []}, {"worker-b": [_ingest_entry(JOB_B)]}],
            "reserved": [{"worker-a": []}, {"worker-b": []}],
            "scheduled": [{"worker-a": []}, {"worker-b": []}],
        },
    )
    assert recovery.live_ingest_task_ids(inspector) == {JOB_B}


def test_real_inspect_reply_hides_a_worker_that_did_not_answer(monkeypatch):
    # worker-b is running JOB_B but did not reply in time, so Celery hands back
    # a reply that looks complete and mentions only idle worker-a.
    inspector = _celery_inspector(
        monkeypatch,
        {
            "active": [{"worker-a": []}],
            "reserved": [{"worker-a": []}],
            "scheduled": [{"worker-a": []}],
        },
    )
    assert recovery.live_ingest_task_ids(inspector) == set()


def test_cluster_with_a_silent_holder_changes_nothing_by_default(monkeypatch):
    session = _install_session(
        monkeypatch, FakeSession(rows=[(JOB_A, SOURCE_A), (JOB_B, SOURCE_B)])
    )
    inspector = _celery_inspector(
        monkeypatch,
        {
            # Only the rebooted, idle worker answers. JOB_A and JOB_B are both
            # held by peers that are busy ingesting and did not reply.
            "active": [{"worker-rebooted": []}],
            "reserved": [{"worker-rebooted": []}],
            "scheduled": [{"worker-rebooted": []}],
        },
    )

    assert recovery.reconcile_orphaned_ingest_jobs(inspector=inspector) == 0
    assert session.sql_for("UPDATE ingest_jobs") == []
    assert session.sql_for("UPDATE evidence_sources") == []
    assert session.committed is False


def test_cluster_with_a_silent_holder_loses_jobs_when_opted_in(
    monkeypatch, fail_unclaimed
):
    # The honest cost of `fail`: JOB_B is still being ingested by the silent
    # worker, and this setting marks it failed anyway.
    session = _install_session(monkeypatch, FakeSession(rows=[(JOB_B, SOURCE_B)]))
    inspector = _celery_inspector(
        monkeypatch,
        {
            "active": [{"worker-rebooted": []}],
            "reserved": [{"worker-rebooted": []}],
            "scheduled": [{"worker-rebooted": []}],
        },
    )

    assert recovery.reconcile_orphaned_ingest_jobs(inspector=inspector) == 1
    assert session.sql_for("UPDATE ingest_jobs")[0][1]["job_ids"] == [JOB_B]


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
