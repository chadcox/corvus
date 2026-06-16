from pathlib import Path
from unittest.mock import patch

from worker.eztools import runner


def test_tool_dll_finds_nested_layout(tmp_path: Path):
    nested = tmp_path / "EvtxECmd" / "EvtxeCmd"
    nested.mkdir(parents=True)
    dll = nested / "EvtxECmd.dll"
    dll.write_bytes(b"fake")

    with patch.object(runner.settings, "eztools_root", str(tmp_path)):
        assert runner._tool_dll("EvtxECmd") == dll


def test_tool_dll_returns_none_when_missing(tmp_path: Path):
    with patch.object(runner.settings, "eztools_root", str(tmp_path)):
        assert runner._tool_dll("MissingTool") is None
