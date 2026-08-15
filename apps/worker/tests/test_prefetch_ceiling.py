"""The raw Prefetch ceiling must be deterministic and announce what it omits."""

from pathlib import Path
from uuid import uuid4

import pytest

from worker.kape import ingest as kape_ingest
from worker.kape.ingest import resolve_prefetch_max_files, select_prefetch_inputs
from worker.parsers.csv_events import is_partial_parse_note
from worker.tasks.ingest import should_delete_package

HEADER = "RunTime,ExecutableName\n"
POPULATED_ROW = "2024-01-01 10:00:00,A.EXE\n"

# Small enough to write in a unit test, large enough to have a real boundary.
CEILING = 4


def _make_package(tmp_path: Path, pf_count: int, pecmd_csv_body: str | None = None) -> Path:
    """Package with pf_count raw .pf files and an optional PECmd module CSV."""
    prefetch_dir = tmp_path / "C" / "Windows" / "prefetch"
    prefetch_dir.mkdir(parents=True)
    for n in range(pf_count):
        (prefetch_dir / f"APP-{n:03d}.pf").write_bytes(b"MAM\x04")
    if pecmd_csv_body is not None:
        modules = tmp_path / "Modules" / "Prefetch"
        modules.mkdir(parents=True)
        (modules / "20240101_PECmd_Output.csv").write_text(pecmd_csv_body)
    return tmp_path


@pytest.fixture
def pecmd(monkeypatch):
    """Stub PECmd that records its inputs and emits one parseable event each."""
    calls: list[Path] = []

    def fake_run_pecmd(input_path: Path, output_dir: Path) -> Path:
        calls.append(input_path)
        output_dir.mkdir(parents=True, exist_ok=True)
        out = output_dir / f"{input_path.stem}_out.csv"
        out.write_text(HEADER + POPULATED_ROW)
        return out

    monkeypatch.setattr(kape_ingest, "run_pecmd", fake_run_pecmd)
    return calls


@pytest.fixture
def small_ceiling(monkeypatch):
    """Exercise the real ceiling logic at a size a unit test can write."""
    monkeypatch.setattr(kape_ingest.settings, "prefetch_max_files", CEILING)


def _partial_notes(result: dict) -> list[str]:
    return [n for n in result["ingest_notes"] if is_partial_parse_note(n)]


def test_shipped_ceiling_is_unchanged():
    # Pin the production default: the tests below run against a patched one.
    assert resolve_prefetch_max_files() == 100


@pytest.mark.parametrize("pf_count", [0, CEILING - 1, CEILING])
def test_package_within_ceiling_parses_everything_without_note(
    tmp_path, pecmd, small_ceiling, pf_count
):
    pkg = _make_package(tmp_path, pf_count)

    result = kape_ingest.ingest_package(pkg, uuid4())

    assert len(pecmd) == pf_count
    assert _partial_notes(result) == []


def test_package_one_file_over_ceiling_parses_the_cap_and_warns(
    tmp_path, pecmd, small_ceiling
):
    pkg = _make_package(tmp_path, CEILING + 1)

    result = kape_ingest.ingest_package(pkg, uuid4())

    assert len(pecmd) == CEILING
    notes = _partial_notes(result)
    assert len(notes) == 1
    assert (
        notes[0] == f"Partial parse: {CEILING + 1} raw prefetch file(s) found, "
        f"{CEILING} parsed, 1 omitted by the PREFETCH_MAX_FILES ceiling "
        f"({CEILING}). Raise PREFETCH_MAX_FILES and re-ingest to parse the rest."
    )


def test_partial_note_carries_counts_only_and_no_collected_paths(
    tmp_path, pecmd, small_ceiling
):
    pkg = _make_package(tmp_path, CEILING + 3)

    note = _partial_notes(kape_ingest.ingest_package(pkg, uuid4()))[0]

    assert str(pkg) not in note and "APP-" not in note
    # A note is one bullet in the job message, which splits notes on ";".
    assert ";" not in note


def test_selection_is_stable_regardless_of_traversal_order(tmp_path):
    pkg = tmp_path
    files = [pkg / "C" / "Windows" / "prefetch" / f"APP-{n:03d}.pf" for n in range(10)]

    forward, note = select_prefetch_inputs(files, pkg, 4)
    backward, _ = select_prefetch_inputs(list(reversed(files)), pkg, 4)

    assert forward == backward == files[:4]
    assert is_partial_parse_note(note)


def test_paths_outside_the_package_still_order_deterministically(tmp_path):
    outside = [Path("/elsewhere/b.pf"), Path("/elsewhere/a.pf")]

    selected, note = select_prefetch_inputs(outside, tmp_path, 1)

    assert selected == [Path("/elsewhere/a.pf")]
    assert is_partial_parse_note(note)


def test_populated_module_csv_suppresses_raw_parsing_without_a_partial_note(
    tmp_path, pecmd, small_ceiling
):
    pkg = _make_package(tmp_path, CEILING + 1, pecmd_csv_body=HEADER + POPULATED_ROW)

    result = kape_ingest.ingest_package(pkg, uuid4())

    assert pecmd == []
    assert _partial_notes(result) == []


def test_empty_module_csv_falls_back_to_capped_raw_parsing(
    tmp_path, pecmd, small_ceiling
):
    pkg = _make_package(tmp_path, CEILING + 1, pecmd_csv_body=HEADER)

    result = kape_ingest.ingest_package(pkg, uuid4())

    assert len(pecmd) == CEILING
    assert len(_partial_notes(result)) == 1


@pytest.mark.parametrize("configured", [0, -5])
def test_non_positive_ceiling_still_parses_one_file(monkeypatch, configured):
    monkeypatch.setattr(kape_ingest.settings, "prefetch_max_files", configured)

    assert resolve_prefetch_max_files() == 1


def test_prefetch_partial_note_keeps_the_package_on_disk(tmp_path, pecmd, small_ceiling):
    pkg = _make_package(tmp_path, CEILING + 1)

    notes = kape_ingest.ingest_package(pkg, uuid4())["ingest_notes"]

    assert should_delete_package(True, notes) is False
