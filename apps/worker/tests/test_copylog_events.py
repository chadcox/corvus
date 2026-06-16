from pathlib import Path

from worker.parsers.csv_events import parse_csv_to_events


def test_parse_copylog_csv(tmp_path: Path):
    csv_path = tmp_path / "CopyLog.csv"
    csv_path.write_text(
        "CopiedTimestamp,SourceFile,DestinationFile,FileSize\n"
        "2026-04-02 22:56:56.3520923,c:\\Users\\chad\\test.txt,F:\\collection\\PC-RACHEL\\c\\Users\\chad\\test.txt,1024\n"
    )
    events, note = parse_csv_to_events(csv_path, "src-1")
    assert len(events) == 1
    assert note is None
    assert events[0]["event_type"] == "kape.collection"
    assert "Collected:" in events[0]["summary"]
    assert "test.txt" in events[0]["summary"]


def test_parse_dotnet_seven_digit_fractional_seconds(tmp_path: Path):
    csv_path = tmp_path / "CopyLog.csv"
    csv_path.write_text(
        "CopiedTimestamp,SourceFile\n"
        "2026-04-02 22:56:56.3520923,c:\\a.txt\n"
    )
    events, _ = parse_csv_to_events(csv_path, "src-1")
    assert len(events) == 1
