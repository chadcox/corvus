"""Parser notes from tool-generated CSVs must reach ingest, not be discarded."""

from pathlib import Path
from uuid import uuid4

import pytest

from worker.kape import ingest as kape_ingest
from worker.parsers import csv_events
from worker.parsers.csv_events import is_partial_parse_note

HEADER = "TimeCreated,EventId,Description\n"
CEILING_INDEX = 3
OVERSIZED_ROWS = CEILING_INDEX + 10


@pytest.fixture
def small_ceiling(monkeypatch):
    monkeypatch.setattr(csv_events, "MAX_CSV_ROW_INDEX", CEILING_INDEX)


def _oversized_csv(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        HEADER
        + "".join(f"2024-01-01 10:00:00,4624,row-{n}\n" for n in range(OVERSIZED_ROWS))
    )
    return path


def _tool_writing_oversized_csv(output_dir: Path):
    def run_fn(input_path: Path, out_dir: Path) -> Path:
        return _oversized_csv(out_dir / f"{input_path.stem}_out.csv")

    return run_fn


def test_run_tool_and_parse_returns_parser_note(tmp_path, small_ceiling):
    events, notes = kape_ingest._run_tool_and_parse(
        _tool_writing_oversized_csv(tmp_path), tmp_path / "System.evtx", tmp_path / "out", "src-1"
    )

    assert len(events) == CEILING_INDEX + 2
    assert len(notes) == 1 and is_partial_parse_note(notes[0])


def test_run_tool_and_parse_without_output_returns_nothing(tmp_path):
    events, notes = kape_ingest._run_tool_and_parse(
        lambda _in, _out: None, tmp_path / "System.evtx", tmp_path / "out", "src-1"
    )

    assert events == [] and notes == []


def test_parallel_tool_parse_notes_follow_input_order_deterministically(tmp_path, small_ceiling):
    inputs = [tmp_path / f"Log{n}.evtx" for n in range(5)]

    runs = [
        kape_ingest._parallel_tool_parse(
            _tool_writing_oversized_csv(tmp_path), inputs, tmp_path / "out", "src-1"
        )
        for _ in range(2)
    ]

    for events, notes in runs:
        assert len(notes) == len(inputs)
        assert [n.split()[2] for n in notes] == [f"Log{n}_out.csv" for n in range(len(inputs))]
        assert len(events) == len(inputs) * (CEILING_INDEX + 2)
    assert runs[0][1] == runs[1][1]
    assert [e["summary"] for e in runs[0][0]] == [e["summary"] for e in runs[1][0]]


def test_parallel_tool_parse_with_no_inputs(tmp_path):
    assert kape_ingest._parallel_tool_parse(
        _tool_writing_oversized_csv(tmp_path), [], tmp_path / "out", "src-1"
    ) == ([], [])


def test_ingest_package_surfaces_raw_evtx_partial_note(tmp_path, monkeypatch, small_ceiling):
    logs = tmp_path / "C" / "Windows" / "System32" / "winevt" / "Logs"
    logs.mkdir(parents=True)
    (logs / "System.evtx").write_bytes(b"ElfFile\x00")
    monkeypatch.setattr(kape_ingest, "run_evtxecmd", _tool_writing_oversized_csv(tmp_path))

    result = kape_ingest.ingest_package(tmp_path, uuid4())

    partial = [n for n in result["ingest_notes"] if is_partial_parse_note(n)]
    assert len(partial) == 1
    assert "System_out.csv" in partial[0]
    assert len(result["timeline_events"]) == CEILING_INDEX + 2
