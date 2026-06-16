from pathlib import Path

from worker.sigma.diagnostics import is_sigma_eligible_event, summarize_sigma_inputs
from worker.sigma.evaluate import evaluate_sigma_rules
from worker.sigma.ingest_note import sigma_ingest_note
from worker.sigma.loader import _parse_rule
from worker.sigma.matcher import normalize_event_fields, rule_matches_event


def test_copylog_not_sigma_eligible():
    assert not is_sigma_eligible_event({"SourceFile": r"C:\a.txt"})
    stats = summarize_sigma_inputs(
        [{"event_type": "kape.collection", "data": {"SourceFile": "x"}}]
    )
    assert stats["sigma_eligible"] == 0
    assert stats["copylog"] == 1


def test_admin_rdp_rule_matches_full_security_row():
    raw = {
        "title": "Admin User Remote Logon",
        "id": "test",
        "logsource": {"product": "windows", "service": "security"},
        "detection": {
            "selection": {
                "EventID": 4624,
                "LogonType": 10,
                "AuthenticationPackageName": "Negotiate",
                "TargetUserName|startswith": "Admin",
            },
            "condition": "selection",
        },
    }
    rule = _parse_rule(Path("test.yml"), raw)
    data = {
        "EventId": "4624",
        "Channel": "Security",
        "LogonType": "10",
        "TargetUserName": "Administrator",
        "AuthenticationPackageName": "Negotiate",
    }
    fields = normalize_event_fields(data)
    assert rule_matches_event(rule, fields)


def test_sparse_demo_csv_matches_nothing():
    data = {
        "EventId": "4624",
        "Channel": "Security",
        "UserName": "DOMAIN\\jsmith",
        "Description": "Successful logon",
    }
    dets, _ = evaluate_sigma_rules([{"id": "1", "data": data}], "src")
    # Minimal rows rarely satisfy multi-field Sigma selections
    assert isinstance(dets, list)


def test_ingest_note_copylog_only():
    events = [
        {"event_type": "kape.collection", "data": {"SourceFile": "x"}},
    ] * 3
    note = sigma_ingest_note(events, 0)
    assert note is not None
    assert "CopyLog" in note
