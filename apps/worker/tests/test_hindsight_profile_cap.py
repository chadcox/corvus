"""The Hindsight per-package profile ceiling must be reported, not silent.

Profiles past HINDSIGHT_MAX_PROFILES are skipped by design; the omission has to
reach the job message as a partial parse so the operator sees it and the
evidence package is retained for a re-ingest with a higher limit.
"""

import json
from pathlib import Path
from uuid import uuid4

import pytest

from worker.config import settings
from worker.hindsight.profiles import find_browser_profiles, select_browser_profiles
from worker.hindsight.runner import HindsightRun
from worker.kape import ingest as kape_ingest
from worker.parsers.csv_events import is_partial_parse_note
from worker.tasks.ingest import is_partial_ingest, should_delete_package

PROFILE_NAMES = ["Default"] + [f"Profile {n}" for n in range(1, 9)]


def _profile_paths(root: Path) -> list[Path]:
    return [root / "Chrome" / "User Data" / name for name in PROFILE_NAMES]


def _make_profiles(package_dir: Path) -> list[Path]:
    """Create nine Chromium profiles inside a raw collection layout."""
    base = package_dir / "C" / "Users" / "alice" / "AppData" / "Local" / "Google"
    profiles = _profile_paths(base)
    for profile in profiles:
        profile.mkdir(parents=True)
        (profile / "History").write_bytes(b"SQLite format 3\x00")
    return profiles


def _fake_hindsight(monkeypatch, events_per_profile: int = 2) -> list[Path]:
    """Stand in for the Hindsight CLI, recording which profiles were run."""
    seen: list[Path] = []

    def run(profile_dir: Path, output_dir: Path, out_stem: str | None = None) -> HindsightRun:
        seen.append(profile_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        jsonl = output_dir / f"{out_stem or profile_dir.name}.jsonl"
        jsonl.write_text(
            "".join(
                json.dumps(
                    {
                        "datetime": "2024-06-01T12:00:00+00:00",
                        "data_type": "chrome:history:page_visited",
                        "message": f"https://example.com/{n} (Example)",
                        "url": f"https://example.com/{n}",
                        "title": "Example",
                    }
                )
                + "\n"
                for n in range(events_per_profile)
            ),
            encoding="utf-8",
        )
        return HindsightRun(jsonl, None)

    monkeypatch.setattr(kape_ingest, "hindsight_available", lambda: True)
    monkeypatch.setattr(kape_ingest, "run_hindsight", run)
    return seen


@pytest.fixture
def hindsight_on(monkeypatch):
    monkeypatch.setattr(settings, "hindsight_enabled", True)
    monkeypatch.setattr(settings, "hindsight_max_profiles", 8)


# --- selection helper -------------------------------------------------------


def test_profiles_within_the_limit_are_all_selected_without_a_note(tmp_path):
    profiles = _profile_paths(tmp_path)[:8]

    selected, note = select_browser_profiles(profiles, 8)

    assert selected == profiles
    assert note is None


def test_one_profile_over_the_limit_caps_and_reports(tmp_path):
    profiles = _profile_paths(tmp_path)

    selected, note = select_browser_profiles(profiles, 8)

    assert len(selected) == 8
    assert is_partial_parse_note(note)
    assert "9 Chromium browser profile(s) found" in note
    assert "8 processed" in note
    assert "1 not parsed" in note
    assert "HINDSIGHT_MAX_PROFILES" in note


def test_selection_is_deterministic_and_takes_the_lowest_sorted_profiles(tmp_path):
    profiles = _profile_paths(tmp_path)
    shuffled = list(reversed(profiles))

    selected, _ = select_browser_profiles(shuffled, 8)

    assert selected == profiles[:8]
    assert select_browser_profiles(shuffled, 8)[0] == selected
    # "Profile 8" sorts last, so it is the one left out.
    assert profiles[-1] not in selected


def test_case_colliding_profiles_select_the_same_subset_in_any_order(tmp_path):
    """Case-only differences must not hand the choice to traversal order.

    A case-sensitive collection can hold both ``Profile`` and ``profile``. Under
    a case-folding-only sort they compare equal, so the stable sort would keep
    whichever order discovery happened to produce and the capped subset would
    change between extractions of the same package.
    """
    base = tmp_path / "Chrome" / "User Data"
    collided = [base / "Default", base / "Profile", base / "profile"]

    selected, note = select_browser_profiles(list(reversed(collided)), 2)

    # Exact subset: "Default" sorts first, then the tie between "Profile" and
    # "profile" is broken by the exact path, so "profile" is the one omitted.
    assert selected == [base / "Default", base / "Profile"]
    assert selected == select_browser_profiles(collided, 2)[0]
    assert is_partial_parse_note(note)


def test_nonpositive_limit_is_clamped_to_one_profile(tmp_path):
    profiles = _profile_paths(tmp_path)

    for limit in (0, -5):
        selected, note = select_browser_profiles(profiles, limit)

        assert selected == profiles[:1]
        assert is_partial_parse_note(note)
        assert "1 processed" in note and "8 not parsed" in note


def test_note_leaks_no_collected_paths_and_no_message_separator(tmp_path):
    profiles = _profile_paths(tmp_path)

    _, note = select_browser_profiles(profiles, 2)

    # The UI splits job messages on ";" and " — ", so neither may appear.
    assert ";" not in note
    assert " — " not in note
    # Counts only: nothing derived from attacker-controlled collected paths.
    assert "Profile" not in note.replace("profile", "")
    assert str(tmp_path) not in note
    assert "Default" not in note


def test_empty_profile_list_selects_nothing_without_a_note():
    assert select_browser_profiles([], 8) == ([], None)


def _is_case_sensitive(root: Path) -> bool:
    """Whether ``root``'s filesystem can hold ``Profile`` and ``profile``."""
    probe = root / "_case_probe"
    probe.mkdir()
    sensitive = not (root / "_CASE_PROBE").exists()
    probe.rmdir()
    return sensitive


def test_discovery_order_does_not_depend_on_creation_order(tmp_path):
    """Two identical packages built in opposite order discover identically."""
    if not _is_case_sensitive(tmp_path):
        pytest.skip("filesystem is case-insensitive: Profile/profile cannot coexist")

    names = ["Default", "Profile", "profile"]
    discovered = []
    for package, order in (("forward", names), ("reverse", list(reversed(names)))):
        user_data = tmp_path / package / "Chrome" / "User Data"
        for name in order:
            (user_data / name).mkdir(parents=True)
            (user_data / name / "History").write_bytes(b"SQLite format 3\x00")
        discovered.append([p.name for p in find_browser_profiles(tmp_path / package)])

    assert discovered[0] == ["Default", "Profile", "profile"]
    assert discovered[0] == discovered[1]


# --- ingest integration -----------------------------------------------------


def test_ingest_caps_profiles_and_keeps_their_events(tmp_path, monkeypatch, hindsight_on):
    profiles = _make_profiles(tmp_path)
    seen = _fake_hindsight(monkeypatch)

    result = kape_ingest.ingest_package(tmp_path, uuid4())

    assert seen == profiles[:8]
    browser_events = [e for e in result["timeline_events"] if e["artifact_type"] == "browser"]
    assert len(browser_events) == 16
    assert any("Browser: 16 events from 8 profile(s)" in n for n in result["ingest_notes"])


def test_capped_ingest_is_partial_and_retains_the_package(tmp_path, monkeypatch, hindsight_on):
    _make_profiles(tmp_path)
    _fake_hindsight(monkeypatch)

    notes = kape_ingest.ingest_package(tmp_path, uuid4())["ingest_notes"]

    partial = [n for n in notes if is_partial_parse_note(n)]
    assert len(partial) == 1
    assert "9 Chromium browser profile(s) found" in partial[0]
    assert is_partial_ingest(notes) is True
    assert should_delete_package(True, notes) is False


def test_ingest_at_the_limit_is_complete_and_still_deletes(tmp_path, monkeypatch, hindsight_on):
    monkeypatch.setattr(settings, "hindsight_max_profiles", 9)
    profiles = _make_profiles(tmp_path)
    seen = _fake_hindsight(monkeypatch)

    result = kape_ingest.ingest_package(tmp_path, uuid4())

    assert seen == profiles
    notes = result["ingest_notes"]
    assert [n for n in notes if is_partial_parse_note(n)] == []
    assert should_delete_package(True, notes) is True


def test_no_cap_warning_when_hindsight_is_disabled(tmp_path, monkeypatch, hindsight_on):
    _make_profiles(tmp_path)
    _fake_hindsight(monkeypatch)
    monkeypatch.setattr(settings, "hindsight_enabled", False)

    notes = kape_ingest.ingest_package(tmp_path, uuid4())["ingest_notes"]

    assert [n for n in notes if is_partial_parse_note(n)] == []
    assert not any("HINDSIGHT_MAX_PROFILES" in n for n in notes)


def test_no_cap_warning_when_hindsight_is_unavailable(tmp_path, monkeypatch, hindsight_on):
    _make_profiles(tmp_path)
    _fake_hindsight(monkeypatch)
    monkeypatch.setattr(kape_ingest, "hindsight_available", lambda: False)

    notes = kape_ingest.ingest_package(tmp_path, uuid4())["ingest_notes"]

    assert [n for n in notes if is_partial_parse_note(n)] == []
    assert not any("HINDSIGHT_MAX_PROFILES" in n for n in notes)
