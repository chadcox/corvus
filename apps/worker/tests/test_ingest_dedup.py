from pathlib import Path

import pytest

from worker.kape.ingest import _module_categories, _preparsed_categories


def _p(name: str) -> Path:
    return Path("/pkg/Modules/EventLogs") / name


# One representative module CSV per raw-artifact category.
MODULE_CSVS = (
    ("evtx", "20240101_EvtxECmd_Output.csv"),
    ("mft", "MFTECmd_$MFT_Output.csv"),
    ("prefetch", "PECmd_Output.csv"),
    ("registry", "RECmd_Batch_Output.csv"),
    ("amcache", "AmcacheParser_AssociatedFileEntries.csv"),
)


def test_module_categories_maps_filenames():
    for category, name in MODULE_CSVS:
        assert _module_categories(_p(name)) == {category}


def test_module_categories_ignores_collection_logs():
    assert _module_categories(_p("2024_CopyLog.csv")) == set()


@pytest.mark.parametrize("category,name", MODULE_CSVS)
def test_populated_module_csv_suppresses_raw_parsing(category, name):
    suppressed, empty = _preparsed_categories([(_p(name), 12)])
    assert category in suppressed
    assert empty == {}


@pytest.mark.parametrize("category,name", MODULE_CSVS)
def test_empty_module_csv_does_not_suppress_raw_parsing(category, name):
    # A header-only CSV — or one whose rows carry no parseable timestamp —
    # contributes no events, so the raw artifacts remain the only source.
    suppressed, empty = _preparsed_categories([(_p(name), 0)])
    assert category not in suppressed
    assert empty == {category: 1}


@pytest.mark.parametrize("category,name", MODULE_CSVS)
def test_mixed_empty_and_populated_module_csvs_suppress(category, name):
    suppressed, empty = _preparsed_categories([(_p(name), 0), (_p(f"other_{name}"), 3)])
    assert category in suppressed
    # A populated match wins, so no fallback note is warranted.
    assert empty == {}


def test_all_modules_populated_suppresses_every_category():
    counts = [(_p(name), 5) for _, name in MODULE_CSVS]
    suppressed, empty = _preparsed_categories(counts)
    assert suppressed == {"evtx", "mft", "prefetch", "registry", "amcache"}
    assert empty == {}


def test_collection_logs_never_suppress():
    suppressed, empty = _preparsed_categories(
        [(_p("2024_CopyLog.csv"), 500), (_p("2024_SkipLog.csv"), 0)]
    )
    assert suppressed == set()
    assert empty == {}


def test_empty_counts_multiple_module_csvs_per_category():
    suppressed, empty = _preparsed_categories(
        [(_p("a_EvtxECmd_Output.csv"), 0), (_p("b_EvtxECmd_Output.csv"), 0)]
    )
    assert suppressed == set()
    assert empty == {"evtx": 2}


def test_preparsed_empty():
    assert _preparsed_categories([]) == (set(), {})
