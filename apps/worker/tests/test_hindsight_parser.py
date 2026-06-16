import json
from pathlib import Path

from worker.hindsight.parser import parse_hindsight_jsonl, _event_type_from_data_type
from worker.hindsight.profiles import (
    find_browser_dirs_without_history,
    find_browser_profiles,
)
from worker.hindsight.runner import output_stem


def test_event_type_mapping():
    assert _event_type_from_data_type("chrome:history:page_visited") == "browser.visit"
    assert _event_type_from_data_type("chrome:history:file_downloaded") == "browser.download"
    assert _event_type_from_data_type("chrome:cookie:entry") == "browser.cookie"


def test_session_storage_is_storage_not_session():
    # "session_storage" contains "session" — must not fall into the session bucket.
    assert _event_type_from_data_type("chrome:session_storage:entry") == "browser.storage"
    assert _event_type_from_data_type("chrome:session:navigation") == "browser.session"
    assert _event_type_from_data_type("chrome:local_storage:entry") == "browser.storage"
    assert _event_type_from_data_type("chrome:extension_storage:entry") == "browser.storage"
    assert _event_type_from_data_type("chrome:file_system:entry") == "browser.storage"


def test_parse_hindsight_jsonl_visit(tmp_path: Path):
    jsonl = tmp_path / "out.jsonl"
    record = {
        "datetime": "2024-06-01T12:00:00+00:00",
        "data_type": "chrome:history:page_visited",
        "message": "https://example.com (Example)",
        "url": "https://example.com",
        "title": "Example",
        "visit_count": 3,
    }
    jsonl.write_text(json.dumps(record) + "\n", encoding="utf-8")

    events = parse_hindsight_jsonl(jsonl, "src-1", profile_hint="/Chrome/User Data/Default")
    assert len(events) == 1
    assert events[0]["event_type"] == "browser.visit"
    assert events[0]["artifact_type"] == "browser"
    assert "example.com" in events[0]["summary"]
    assert events[0]["data"]["url"] == "https://example.com"


def _chrome_profile(root: Path, profile_name: str) -> Path:
    profile = (
        root
        / "Users"
        / "alice"
        / "AppData"
        / "Local"
        / "Google"
        / "Chrome"
        / "User Data"
        / profile_name
    )
    profile.mkdir(parents=True)
    return profile


def test_find_browser_profiles_returns_profile_dir(tmp_path: Path):
    profile = _chrome_profile(tmp_path, "Default")
    (profile / "History").write_bytes(b"sqlite")

    found = find_browser_profiles(tmp_path)
    assert len(found) == 1
    assert found[0].name == "Default"


def test_find_browser_profiles_without_history(tmp_path: Path):
    # Cleared history but cookies remain — profile must still be discovered.
    profile = _chrome_profile(tmp_path, "Profile 1")
    network = profile / "Network"
    network.mkdir()
    (network / "Cookies").write_bytes(b"sqlite")

    found = find_browser_profiles(tmp_path)
    assert [p.name for p in found] == ["Profile 1"]


def test_browser_dir_without_history_detected(tmp_path: Path):
    # Chrome User Data/Default collected with only Cache — no history DBs.
    default = _chrome_profile(tmp_path, "Default")
    (default / "Cache").mkdir()
    (default / "Cache" / "data_0").write_bytes(b"x")

    assert find_browser_profiles(tmp_path) == []
    empty = find_browser_dirs_without_history(tmp_path)
    assert [p.name for p in empty] == ["User Data"]


def test_browser_dir_with_history_not_flagged(tmp_path: Path):
    default = _chrome_profile(tmp_path, "Default")
    (default / "History").write_bytes(b"sqlite")

    assert find_browser_dirs_without_history(tmp_path) == []


def test_output_stem_unique_for_same_profile_name(tmp_path: Path):
    a = tmp_path / "chrome" / "User Data" / "Default"
    b = tmp_path / "edge" / "User Data" / "Default"
    a.mkdir(parents=True)
    b.mkdir(parents=True)
    assert output_stem(a, "chrome/Default") != output_stem(b, "edge/Default")
