from uuid import uuid4

from app.services.ingest_outcome import build_ingest_outcome
from corvus_core.constants import JobStatus
from corvus_core.schemas import SourceStats


def test_outcome_success_when_job_and_stats_ok():
    cid = uuid4()
    jid = uuid4()
    sid = uuid4()
    outcome = build_ingest_outcome(
        job_id=jid,
        evidence_source_id=sid,
        case_id=cid,
        job_status=JobStatus.COMPLETED,
        job_progress=100,
        job_message="Ingested 3 events",
        source_status=JobStatus.COMPLETED,
        stats=SourceStats(
            timeline_count=3,
            filesystem_count=1,
            entity_count=2,
            sigma_detection_count=0,
            event_types=["4624"],
        ),
    )
    assert outcome.success is True
    assert all(c.passed for c in outcome.checks)


def test_outcome_failed_job():
    outcome = build_ingest_outcome(
        job_id=uuid4(),
        evidence_source_id=uuid4(),
        case_id=uuid4(),
        job_status=JobStatus.FAILED,
        job_progress=92,
        job_message="NUL byte error",
        source_status=JobStatus.FAILED,
        stats=None,
    )
    assert outcome.success is False
    assert not any(c.name == "job_completed" and c.passed for c in outcome.checks)


def test_outcome_running_not_success():
    outcome = build_ingest_outcome(
        job_id=uuid4(),
        evidence_source_id=uuid4(),
        case_id=uuid4(),
        job_status=JobStatus.RUNNING,
        job_progress=50,
        job_message="Parsing",
        source_status=JobStatus.RUNNING,
        stats=None,
    )
    assert outcome.success is False
    assert not outcome.checks[0].passed  # job_terminal
