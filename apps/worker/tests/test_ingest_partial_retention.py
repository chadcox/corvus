"""A partial ingest must keep the source package so the tail can be re-ingested."""

from worker.parsers.csv_events import MAX_KAPE_COLLECTION_EVENTS, is_partial_parse_note
from worker.tasks.ingest import (
    MAX_PARTIAL_NOTES_IN_MESSAGE,
    is_partial_ingest,
    should_delete_package,
    summarize_partial_notes,
)

PARTIAL_NOTE = (
    "Partial parse: big.csv exceeded the generic CSV parser row ceiling "
    "(stops after row index 500000); inspected 500002 rows and emitted 500002 "
    "timeline events. The rest of the file was not read, so the number of "
    "omitted rows is unknown. Re-ingest after splitting the file to parse the remainder."
)
COMPLETE_NOTES = [
    "Source adapter: generic_directory",
    "Browser: 12 events from 1 profile(s)",
    f"CopyLog capped at {MAX_KAPE_COLLECTION_EVENTS} collection events "
    f"(use Disk view for full file tree)",
]


def test_complete_ingest_still_deletes_package_when_enabled():
    assert should_delete_package(True, COMPLETE_NOTES) is True
    assert should_delete_package(True, []) is True


def test_partial_ingest_keeps_package_even_when_deletion_enabled():
    assert should_delete_package(True, COMPLETE_NOTES + [PARTIAL_NOTE]) is False


def test_deletion_disabled_never_deletes():
    assert should_delete_package(False, []) is False
    assert should_delete_package(False, [PARTIAL_NOTE]) is False


def test_is_partial_ingest_only_flags_partial_parse_notes():
    assert is_partial_ingest([PARTIAL_NOTE]) is True
    assert is_partial_ingest(COMPLETE_NOTES) is False
    assert is_partial_ingest([]) is False


def test_notes_within_the_limit_are_passed_through_unchanged():
    notes = COMPLETE_NOTES + [PARTIAL_NOTE] * MAX_PARTIAL_NOTES_IN_MESSAGE

    assert summarize_partial_notes(notes) == notes


def test_many_partial_notes_collapse_into_one_bounded_count():
    notes = [COMPLETE_NOTES[0]] + [PARTIAL_NOTE] * (MAX_PARTIAL_NOTES_IN_MESSAGE + 40)

    summarized = summarize_partial_notes(notes)

    # Original order kept, the first `limit` details kept, the rest counted.
    assert summarized[0] == COMPLETE_NOTES[0]
    assert summarized[1 : 1 + MAX_PARTIAL_NOTES_IN_MESSAGE] == [
        PARTIAL_NOTE
    ] * MAX_PARTIAL_NOTES_IN_MESSAGE
    assert len(summarized) == MAX_PARTIAL_NOTES_IN_MESSAGE + 2
    assert "40 more file(s) were parsed only in part" in summarized[-1]
    # The collapsed note must still read as an incomplete ingest.
    assert is_partial_parse_note(summarized[-1])
    assert is_partial_ingest(summarized) is True
