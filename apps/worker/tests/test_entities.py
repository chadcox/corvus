from worker.parsers.entities import extract_entities_from_events


def _event(data: dict) -> dict:
    return {"data": data, "evidence_source_id": "test-source"}


def test_extracts_users_and_deduplicates():
    events = [
        _event({"UserName": "DOMAIN\\jsmith", "EventId": "4624"}),
        _event({"UserName": "DOMAIN\\jsmith", "EventId": "4688"}),
        _event({"UserName": "DOMAIN\\admin"}),
    ]
    entities = extract_entities_from_events(events, "src-1")

    users = [e for e in entities if e["entity_type"] == "User"]
    assert len(users) == 2
    names = {u["display_name"] for u in users}
    assert names == {"DOMAIN\\jsmith", "DOMAIN\\admin"}


def test_extracts_processes_and_files():
    events = [
        _event({"ProcessName": "cmd.exe", "TargetFilename": "C:\\Windows\\System32\\cmd.exe"}),
    ]
    entities = extract_entities_from_events(events, "src-1")

    types = {e["entity_type"] for e in entities}
    assert types == {"Process", "File"}


def test_skips_invalid_ips():
    events = [
        _event({"IpAddress": "not-an-ip", "SourceIp": "192.168.1.10"}),
    ]
    entities = extract_entities_from_events(events, "src-1")

    ips = [e for e in entities if e["entity_type"] == "IpAddress"]
    assert len(ips) == 1
    assert ips[0]["display_name"] == "192.168.1.10"


def test_skips_empty_values():
    events = [_event({"UserName": "", "ProcessName": "N/A"})]
    entities = extract_entities_from_events(events, "src-1")
    assert entities == []
    assert events[0]["entity_refs"] == []


def test_links_entity_refs_on_events():
    events = [
        _event({"UserName": "DOMAIN\\jsmith", "ProcessName": "cmd.exe"}),
    ]
    entities = extract_entities_from_events(events, "src-1")
    assert len(entities) == 2
    assert len(events[0]["entity_refs"]) == 2
    entity_ids = {e["id"] for e in entities}
    assert set(events[0]["entity_refs"]) == entity_ids


def test_extracts_entities_from_kape_copylog_paths():
    events = [
        _event(
            {
                "SourceFile": r"c:\Users\chad\AppData\Local\Google\Chrome\Application\chrome.exe",
                "DestinationFile": r"F:\collection\PC-RACHEL\c\Users\chad\AppData\Local\Google\Chrome\Application\chrome.exe",
                "FileSize": "1024",
            }
        ),
    ]
    entities = extract_entities_from_events(events, "src-1")
    types = {e["entity_type"] for e in entities}
    assert "User" in types
    assert "File" in types
    assert "Process" in types

    users = [e for e in entities if e["entity_type"] == "User"]
    assert any(e["display_name"] == "chad" for e in users)

    processes = [e for e in entities if e["entity_type"] == "Process"]
    assert any(e["display_name"] == "chrome.exe" for e in processes)

    assert len(events[0]["entity_refs"]) >= 3
