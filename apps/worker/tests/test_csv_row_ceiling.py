"""The generic CSV row ceiling must announce itself instead of truncating silently."""

import csv
from pathlib import Path

import pytest

from worker.parsers import csv_events
from worker.parsers.csv_events import (
    MAX_CSV_ROW_INDEX,
    MAX_KAPE_COLLECTION_EVENTS,
    is_partial_parse_note,
    parse_csv_to_events,
)

HEADER = "TimeCreated,EventId,Description\n"

# With a ceiling at row index N, parsing stops only after an event has been
# emitted from index N + 1, so a complete parse covers N + 2 timestamped rows.
CEILING_INDEX = 3
RETAINED_ROWS = CEILING_INDEX + 2


def _row(n: int, timestamp: str = "2024-01-01 10:00:00") -> str:
    return f"{timestamp},4624,row-{n}\n"


def _write_rows(path: Path, count: int) -> Path:
    path.write_text(HEADER + "".join(_row(n) for n in range(count)))
    return path


@pytest.fixture
def small_ceiling(monkeypatch):
    """Exercise the real ceiling logic at a size a unit test can write."""
    monkeypatch.setattr(csv_events, "MAX_CSV_ROW_INDEX", CEILING_INDEX)


def test_shipped_ceiling_is_unchanged():
    # Pin the production ceiling: the fast tests below run against a patched one.
    assert MAX_CSV_ROW_INDEX == 500_000


def test_file_at_exact_ceiling_parses_completely_without_note(tmp_path, small_ceiling):
    csv_path = _write_rows(tmp_path / "events.csv", RETAINED_ROWS)

    events, note = parse_csv_to_events(csv_path, "src-1")

    assert len(events) == RETAINED_ROWS
    assert note is None


def test_file_one_row_past_ceiling_keeps_prefix_and_warns(tmp_path, small_ceiling):
    csv_path = _write_rows(tmp_path / "events.csv", RETAINED_ROWS + 1)

    events, note = parse_csv_to_events(csv_path, "src-1")

    # Exactly the same retained prefix as before the warning existed.
    assert len(events) == RETAINED_ROWS
    assert [e["summary"].split("row-")[-1] for e in events] == [
        str(n) for n in range(RETAINED_ROWS)
    ]
    assert is_partial_parse_note(note)


def test_partial_note_names_file_ceiling_counts_and_unknown_tail(tmp_path, small_ceiling):
    csv_path = _write_rows(tmp_path / "huge_EvtxECmd_Output.csv", RETAINED_ROWS + 50)

    _events, note = parse_csv_to_events(csv_path, "src-1")

    assert "huge_EvtxECmd_Output.csv" in note
    assert f"row index {CEILING_INDEX}" in note
    assert f"inspected {RETAINED_ROWS} rows" in note
    assert f"emitted {RETAINED_ROWS} timeline events" in note
    assert "number of omitted rows is unknown" in note
    # The tail is never counted, so no total may be claimed for it.
    assert "50" not in note


def test_rows_without_timestamps_do_not_shift_the_retained_prefix(tmp_path, small_ceiling):
    # Timestamp-less rows are skipped before the ceiling check, so they neither
    # end the parse early nor consume a retained slot.
    csv_path = tmp_path / "events.csv"
    csv_path.write_text(
        HEADER
        + "".join(_row(n) for n in range(CEILING_INDEX + 1))
        + _row(90, timestamp="")
        + _row(91, timestamp="not-a-timestamp")
        + _row(92)
        + _row(93)
    )

    events, note = parse_csv_to_events(csv_path, "src-1")

    assert [e["summary"].split("row-")[-1] for e in events] == ["0", "1", "2", "3", "92"]
    assert is_partial_parse_note(note)


def test_unreadable_tail_is_reported_as_partial_not_complete(tmp_path, small_ceiling):
    # A row past the ceiling that the csv module cannot read still means the
    # file did not end at the ceiling; the honest answer is "partial".
    csv_path = tmp_path / "events.csv"
    csv_path.write_text(
        HEADER
        + "".join(_row(n) for n in range(RETAINED_ROWS))
        + "2024-01-01 10:00:00,4624," + ("x" * 200_000) + "\n"
    )
    previous_limit = csv.field_size_limit()
    csv.field_size_limit(1_000)
    try:
        events, note = parse_csv_to_events(csv_path, "src-1")
    finally:
        csv.field_size_limit(previous_limit)

    assert len(events) == RETAINED_ROWS
    assert is_partial_parse_note(note)


def _write_production_scale_csv(path: Path, rows: int) -> Path:
    with path.open("w") as f:
        f.write(HEADER)
        for n in range(rows):
            f.write(_row(n))
    return path


# Production-ceiling coverage: ~13 MB written and ~1.5 s parsed per case, which
# is worth paying to prove the shipped constant behaves like the patched one.
PRODUCTION_RETAINED_ROWS = MAX_CSV_ROW_INDEX + 2


def test_production_ceiling_exact_cap_parses_completely_without_note(tmp_path):
    csv_path = _write_production_scale_csv(tmp_path / "events.csv", PRODUCTION_RETAINED_ROWS)

    events, note = parse_csv_to_events(csv_path, "src-1")

    assert len(events) == PRODUCTION_RETAINED_ROWS
    assert note is None


def test_production_ceiling_one_row_past_cap_keeps_prefix_and_warns(tmp_path):
    csv_path = _write_production_scale_csv(tmp_path / "events.csv", PRODUCTION_RETAINED_ROWS + 1)

    events, note = parse_csv_to_events(csv_path, "src-1")

    assert len(events) == PRODUCTION_RETAINED_ROWS
    assert is_partial_parse_note(note)
    assert f"inspected {PRODUCTION_RETAINED_ROWS} rows" in note


def test_copylog_cap_note_is_unchanged_and_is_not_a_partial_parse(tmp_path):
    csv_path = tmp_path / "CopyLog.csv"
    csv_path.write_text(
        "CopiedTimestamp,SourceFile,FileSize\n"
        + "".join(
            f"2026-04-02 22:56:56.3520923,c:\\file-{n}.txt,10\n"
            for n in range(MAX_KAPE_COLLECTION_EVENTS + 5)
        )
    )

    events, note = parse_csv_to_events(csv_path, "src-1")

    assert len(events) == MAX_KAPE_COLLECTION_EVENTS
    assert note == (
        f"CopyLog capped at {MAX_KAPE_COLLECTION_EVENTS} collection events "
        f"(use Disk view for full file tree)"
    )
    # The CopyLog cap is a deliberate display cap with the full tree in Disk
    # view, so it must not be treated as an incomplete parse.
    assert not is_partial_parse_note(note)


def test_is_partial_parse_note_rejects_other_notes():
    assert not is_partial_parse_note(None)
    assert not is_partial_parse_note("")
    assert not is_partial_parse_note("Browser: 12 events from 1 profile(s)")
