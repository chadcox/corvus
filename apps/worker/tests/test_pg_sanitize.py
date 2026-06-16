from worker.util.pg_sanitize import sanitize_for_postgres, sanitize_text


def test_strips_nul_from_string():
    assert sanitize_text("ka\u0000pe") == "kape"


def test_strips_bom_from_dict_keys_and_values():
    raw = {"\ufeffEntryNumber": "5\u0000", "Path": "C:\\x"}
    clean = sanitize_for_postgres(raw)
    assert "\ufeff" not in next(iter(clean))
    assert "\x00" not in clean["EntryNumber"]


def test_nested_structures():
    assert sanitize_for_postgres(["a\u0000", {"k\u0000": 1}]) == ["a", {"k": 1}]
