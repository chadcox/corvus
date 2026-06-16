from worker.tasks.ingest import classify_ingest_failure, is_fast_validation_mode, validation_mode


def test_classify_ingest_failure_manifest_error() -> None:
    code, stage = classify_ingest_failure(ValueError("manifest.json failed validation"), "parse")
    assert code == "manifest_invalid"
    assert stage == "parse"


def test_classify_ingest_failure_cancelled() -> None:
    code, stage = classify_ingest_failure(RuntimeError("Cancelled by user"), "db_timeline")
    assert code == "cancelled"
    assert stage == "cancel"


def test_classify_ingest_failure_source_missing() -> None:
    code, stage = classify_ingest_failure(FileNotFoundError("not found"), "startup")
    assert code == "source_not_found"
    assert stage == "startup"


def test_validation_mode_reads_manifest_flag() -> None:
    assert validation_mode({"ff_validation_mode": "FAST"}) == "fast"
    assert is_fast_validation_mode({"ff_validation_mode": "fast"}) is True


def test_validation_mode_ignores_missing_or_invalid_manifest() -> None:
    assert validation_mode(None) is None
    assert validation_mode({"hostname": "host-a"}) is None
    assert is_fast_validation_mode({"ff_validation_mode": "full"}) is False
