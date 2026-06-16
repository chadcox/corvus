from pathlib import Path

from worker.kape.ingest import _preparsed_categories


def _p(name: str) -> Path:
    return Path("/pkg/Modules/EventLogs") / name


def test_preparsed_detects_evtxecmd_output():
    cats = _preparsed_categories([_p("20240101_EvtxECmd_Output.csv")])
    assert "evtx" in cats


def test_preparsed_detects_multiple_modules():
    cats = _preparsed_categories(
        [
            _p("EvtxECmd_Output.csv"),
            _p("MFTECmd_$MFT_Output.csv"),
            _p("PECmd_Output.csv"),
            _p("RECmd_Batch_Output.csv"),
            _p("AmcacheParser_AssociatedFileEntries.csv"),
        ]
    )
    assert cats == {"evtx", "mft", "prefetch", "registry", "amcache"}


def test_preparsed_ignores_collection_logs():
    # CopyLog / SkipLog are not pre-parsed module output and must not suppress
    # raw artifact parsing.
    cats = _preparsed_categories([_p("2024_CopyLog.csv"), _p("2024_SkipLog.csv")])
    assert cats == set()


def test_preparsed_empty():
    assert _preparsed_categories([]) == set()
