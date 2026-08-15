from pathlib import Path
from unittest.mock import patch

import pytest

from worker.chainsaw.evaluate import evaluate_chainsaw_hunt_with_coverage
from worker.chainsaw.hunt import (
    ChainsawHuntRun,
    collect_evtx_for_hunt_with_count,
    detection_coverage_note,
    run_chainsaw_hunt_parallel_with_coverage,
)
from worker.config import settings
from worker.tasks.ingest import (
    is_partial_ingest,
    should_delete_package,
    should_run_chainsaw_detection,
)


def _note(
    *,
    found: int,
    selected: int,
    hunted: int,
    failed: int = 0,
    failed_batches: int = 0,
    effective_max: int = 64,
) -> str | None:
    return detection_coverage_note(
        found_files=found,
        selected_files=selected,
        effective_max=effective_max,
        run=ChainsawHuntRun([], hunted, failed, failed_batches),
    )


def test_ceiling_note_reports_found_hunted_omitted_and_reingest_remedy():
    note = _note(found=312, selected=64, hunted=64)

    assert note is not None
    assert "312 EVTX file(s) found, 64 hunted, 248 not hunted" in note
    assert "248 omitted by the effective CHAINSAW_EVTX_MAX ceiling of 64" in note
    assert "Re-ingest with a higher CHAINSAW_EVTX_MAX" in note


@pytest.mark.parametrize("found", [0, 1, 63, 64])
def test_at_or_under_ceiling_has_no_coverage_note(found):
    assert _note(found=found, selected=found, hunted=found) is None


def test_ceiling_note_is_emitted_even_when_hunt_has_zero_hits():
    evtx_files = [Path(f"/{number}.evtx") for number in range(64)]
    empty_run = ChainsawHuntRun([], hunted_files=64, failed_files=0, failed_batches=0)

    with patch(
        "worker.chainsaw.evaluate.run_chainsaw_hunt_parallel_with_coverage",
        return_value=empty_run,
    ):
        detections, events, note = evaluate_chainsaw_hunt_with_coverage(
            [],
            "source-id",
            evtx_files=evtx_files,
            found_files=312,
            effective_max=64,
        )

    assert detections == []
    assert events == []
    assert note is not None and "248 not hunted" in note


def test_failed_batch_reports_unhunted_files_and_preserves_successful_hits(monkeypatch):
    paths = [Path(f"/{number}.evtx") for number in range(4)]
    successful_hit = {"name": "successful detection"}
    partial_failed_hit = {"name": "detection emitted before failure"}
    monkeypatch.setattr(settings, "chainsaw_evtx_batch_size", 2)
    monkeypatch.setattr(settings, "chainsaw_evtx_parallel", 2)

    def fake_batch(batch, *, sigma_root):
        if batch[0] == paths[0]:
            return [successful_hit], True
        return [partial_failed_hit], False

    with patch("worker.chainsaw.hunt.resolve_sigma_rules_root", return_value=None):
        with patch("worker.chainsaw.hunt._run_chainsaw_hunt_batch", side_effect=fake_batch):
            run = run_chainsaw_hunt_parallel_with_coverage(paths)

    assert sorted(hit["name"] for hit in run.hits) == [
        "detection emitted before failure",
        "successful detection",
    ]
    assert run.hunted_files == 2
    assert run.failed_files == 2
    assert run.failed_batches == 1
    note = detection_coverage_note(
        found_files=4,
        selected_files=4,
        effective_max=64,
        run=run,
    )
    assert note is not None
    assert "4 EVTX file(s) found, 2 hunted, 2 not hunted" in note
    assert "2 in 1 failed or timed-out Chainsaw batch(es)" in note


def test_count_only_note_cannot_leak_an_adversarial_filename(tmp_path, monkeypatch):
    secret = "HOST-SECRET — x;Partial parse"
    for name in (f"{secret}.evtx", "ordinary.evtx"):
        (tmp_path / name).write_bytes(b"ElfFile")
    monkeypatch.setattr(settings, "chainsaw_evtx_max", 1)
    monkeypatch.setattr(settings, "chainsaw_evtx_mode", "all")

    selected, found, effective_max = collect_evtx_for_hunt_with_count(tmp_path)
    note = detection_coverage_note(
        found_files=found,
        selected_files=len(selected),
        effective_max=effective_max,
        run=ChainsawHuntRun([], 1, 0, 0),
    )

    assert note is not None
    assert secret not in note
    assert str(tmp_path) not in note
    assert ";" not in note
    assert " — " not in note


@pytest.mark.parametrize("configured", [0, -7])
def test_nonpositive_ceiling_is_effectively_one(tmp_path, monkeypatch, configured):
    for number in range(3):
        (tmp_path / f"{number}.evtx").write_bytes(b"ElfFile")
    monkeypatch.setattr(settings, "chainsaw_evtx_max", configured)
    monkeypatch.setattr(settings, "chainsaw_evtx_mode", "all")

    selected, found, effective_max = collect_evtx_for_hunt_with_count(tmp_path)

    assert len(selected) == 1
    assert found == 3
    assert effective_max == 1
    assert "effective CHAINSAW_EVTX_MAX ceiling of 1" in (
        _note(found=3, selected=1, hunted=1, effective_max=effective_max) or ""
    )


def test_selection_and_note_are_deterministic(tmp_path, monkeypatch):
    for name in ("z.evtx", "A.evtx", "m.evtx"):
        (tmp_path / name).write_bytes(b"ElfFile")
    monkeypatch.setattr(settings, "chainsaw_evtx_max", 2)
    monkeypatch.setattr(settings, "chainsaw_evtx_mode", "all")

    first = collect_evtx_for_hunt_with_count(tmp_path)
    second = collect_evtx_for_hunt_with_count(tmp_path)

    assert first == second
    assert [path.name for path in first[0]] == ["A.evtx", "m.evtx"]
    run = ChainsawHuntRun([], 2, 0, 0)
    assert detection_coverage_note(
        found_files=first[1], selected_files=2, effective_max=first[2], run=run
    ) == detection_coverage_note(
        found_files=second[1], selected_files=2, effective_max=second[2], run=run
    )


def test_disabled_or_fast_validation_does_not_run_chainsaw_coverage():
    assert should_run_chainsaw_detection(
        fast_validation_mode=False, chainsaw_enabled=True
    )
    assert not should_run_chainsaw_detection(
        fast_validation_mode=False, chainsaw_enabled=False
    )
    assert not should_run_chainsaw_detection(
        fast_validation_mode=True, chainsaw_enabled=True
    )


def test_detection_coverage_note_does_not_change_partial_parse_cleanup():
    note = _note(found=312, selected=64, hunted=64)

    assert note is not None
    assert is_partial_ingest([note]) is False
    assert should_delete_package(True, [note]) is True
