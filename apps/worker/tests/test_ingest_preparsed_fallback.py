"""Raw parsing must fall back when a matching module CSV contributes nothing."""

from pathlib import Path
from uuid import uuid4

import pytest

from worker.kape import ingest as kape_ingest

HEADER = "RecordNumber,EventId,TimeCreated,Channel,Description\n"
POPULATED_ROW = "1,4624,2024-01-01 10:00:00,Security,Logon\n"
UNPARSEABLE_ROW = "1,4624,not-a-timestamp,Security,Logon\n"


def _make_package(tmp_path: Path, evtx_csv_body: str | None) -> Path:
    """Package with one raw EVTX file and optionally one EvtxECmd module CSV."""
    logs = tmp_path / "C" / "Windows" / "System32" / "winevt" / "Logs"
    logs.mkdir(parents=True)
    (logs / "System.evtx").write_bytes(b"ElfFile\x00")
    if evtx_csv_body is not None:
        modules = tmp_path / "Modules" / "EventLogs"
        modules.mkdir(parents=True)
        (modules / "20240101_EvtxECmd_Output.csv").write_text(evtx_csv_body)
    return tmp_path


@pytest.fixture
def evtx_tool(monkeypatch):
    """Stub EvtxECmd that records its inputs and emits one parseable event."""
    calls: list[Path] = []

    def fake_run_evtxecmd(input_path: Path, output_dir: Path) -> Path:
        calls.append(input_path)
        output_dir.mkdir(parents=True, exist_ok=True)
        out = output_dir / f"{input_path.stem}_out.csv"
        out.write_text(HEADER + "9,4688,2024-02-02 11:00:00,Security,Process start\n")
        return out

    monkeypatch.setattr(kape_ingest, "run_evtxecmd", fake_run_evtxecmd)
    return calls


def _evtx_events(result: dict) -> list[dict]:
    return [e for e in result["timeline_events"] if e["artifact_type"] == "evtx"]


def _fallback_notes(result: dict) -> list[str]:
    return [n for n in result["ingest_notes"] if "contributed no" in n]


@pytest.mark.parametrize(
    "csv_body,label",
    [(HEADER, "header-only"), (HEADER + UNPARSEABLE_ROW, "unparseable timestamps")],
)
def test_empty_module_csv_still_parses_raw_evtx(tmp_path, evtx_tool, csv_body, label):
    pkg = _make_package(tmp_path, csv_body)

    result = kape_ingest.ingest_package(pkg, uuid4())

    assert [p.name for p in evtx_tool] == ["System.evtx"], label
    assert len(_evtx_events(result)) == 1, label
    notes = _fallback_notes(result)
    assert len(notes) == 1 and "evtx" in notes[0], notes


def test_empty_module_csv_note_names_the_fallback(tmp_path, evtx_tool):
    pkg = _make_package(tmp_path, HEADER)

    result = kape_ingest.ingest_package(pkg, uuid4())

    note = _fallback_notes(result)[0]
    assert "1 pre-parsed module CSV(s)" in note
    assert "raw evtx parsing not suppressed" in note


def test_populated_module_csv_suppresses_raw_evtx(tmp_path, evtx_tool):
    pkg = _make_package(tmp_path, HEADER + POPULATED_ROW)

    result = kape_ingest.ingest_package(pkg, uuid4())

    assert evtx_tool == []
    # Only the module CSV's own event — the raw EVTX was not re-parsed.
    assert len(_evtx_events(result)) == 1
    assert _fallback_notes(result) == []


def test_mixed_empty_and_populated_module_csvs_suppress_raw_evtx(tmp_path, evtx_tool):
    pkg = _make_package(tmp_path, HEADER)
    (pkg / "Modules" / "EventLogs" / "other_EvtxECmd_Output.csv").write_text(
        HEADER + POPULATED_ROW
    )

    result = kape_ingest.ingest_package(pkg, uuid4())

    assert evtx_tool == []
    assert len(_evtx_events(result)) == 1
    assert _fallback_notes(result) == []


def test_no_module_csv_parses_raw_evtx_without_note(tmp_path, evtx_tool):
    pkg = _make_package(tmp_path, None)

    result = kape_ingest.ingest_package(pkg, uuid4())

    assert [p.name for p in evtx_tool] == ["System.evtx"]
    assert len(_evtx_events(result)) == 1
    assert _fallback_notes(result) == []
