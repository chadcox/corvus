from pathlib import Path

from worker.parsers.csv_events import _artifact_label


def test_mft_csv_label(tmp_path: Path):
    csv = tmp_path / "_ff_parsed" / "mft" / "$MFT.csv"
    csv.parent.mkdir(parents=True)
    csv.write_text("x", encoding="utf-8")
    assert _artifact_label(csv) == "mft"


def test_evtx_parsed_csv_label(tmp_path: Path):
    csv = tmp_path / "_ff_parsed" / "evtx" / "Security.csv"
    csv.parent.mkdir(parents=True)
    csv.write_text("x", encoding="utf-8")
    assert _artifact_label(csv) == "evtx"
