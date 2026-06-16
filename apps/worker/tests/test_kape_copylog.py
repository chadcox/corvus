from pathlib import Path

from worker.kape.detector import detect_kape_layout


def test_detects_kape_copylog_csv(tmp_path: Path):
    (tmp_path / "2026-04-02T22_56_35_1986681_CopyLog.csv").write_text(
        "CopiedTimestamp,SourceFile\n2026-04-02 22:56:56,c:\\test.txt\n"
    )
    (tmp_path / "c").mkdir()

    layout = detect_kape_layout(tmp_path)
    assert len(layout.csv_files) == 1
    assert "CopyLog" in layout.csv_files[0].name
