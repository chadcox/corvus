from pathlib import Path

from worker.chainsaw.evtx_select import (
    evtx_priority_rank,
    find_evtx_files,
    is_priority_evtx,
)


def test_evtx_priority_rank_security_first(tmp_path: Path):
    sec = tmp_path / "Logs" / "Security.evtx"
    other = tmp_path / "Logs" / "Application.evtx"
    sec.parent.mkdir(parents=True)
    sec.write_bytes(b"x")
    other.write_bytes(b"x")
    assert evtx_priority_rank(sec) < evtx_priority_rank(other)
    assert is_priority_evtx(sec)
    assert not is_priority_evtx(other)


def test_find_evtx_priority_mode_caps_and_orders(tmp_path: Path):
    logs = tmp_path / "Logs"
    logs.mkdir()
    (logs / "Application.evtx").write_bytes(b"a")
    (logs / "Security.evtx").write_bytes(b"b")
    (logs / "Microsoft-Windows-Sysmon-Operational.evtx").write_bytes(b"c")

    selected = find_evtx_files(tmp_path, max_files=2, mode="priority")
    assert len(selected) == 2
    names = [p.name for p in selected]
    assert "Security.evtx" in names
    assert "Microsoft-Windows-Sysmon-Operational.evtx" in names


def test_find_evtx_all_mode_lexicographic(tmp_path: Path):
    logs = tmp_path / "Logs"
    logs.mkdir()
    (logs / "Z.evtx").write_bytes(b"z")
    (logs / "A.evtx").write_bytes(b"a")

    selected = find_evtx_files(tmp_path, max_files=10, mode="all")
    assert [p.name for p in selected] == ["A.evtx", "Z.evtx"]
