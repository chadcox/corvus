from pathlib import Path

from worker.kape.detector import detect_kape_layout


def test_detects_mft_files(tmp_path: Path):
    mft = tmp_path / "$MFT"
    mft.write_bytes(b"fake")
    (tmp_path / "EventLogs").mkdir()
    (tmp_path / "EventLogs" / "x.csv").write_text("Timestamp,EventId\n2025-01-01 00:00:00,1\n")

    layout = detect_kape_layout(tmp_path)
    assert len(layout.mft_files) == 1
    assert layout.mft_files[0].name == "$MFT"


def test_detects_registry_prefetch_amcache(tmp_path: Path):
    (tmp_path / "Registry").mkdir()
    (tmp_path / "Registry" / "SYSTEM").write_bytes(b"hive")
    (tmp_path / "EvidenceOfExecution").mkdir()
    (tmp_path / "EvidenceOfExecution" / "CALC.EXE-ABC.pf").write_bytes(b"pf")
    (tmp_path / "C" / "Windows" / "appcompat" / "Programs").mkdir(parents=True)
    amcache = tmp_path / "C" / "Windows" / "appcompat" / "Programs" / "Amcache.hve"
    amcache.write_bytes(b"hve")

    layout = detect_kape_layout(tmp_path)
    assert len(layout.registry_hives) == 1
    assert layout.registry_hives[0].name == "SYSTEM"
    assert len(layout.prefetch_files) == 1
    assert layout.prefetch_files[0].suffix.lower() == ".pf"
    assert len(layout.amcache_files) == 1
    assert layout.amcache_files[0].name == "Amcache.hve"
