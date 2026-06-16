from worker.parsers.csv_events import _summary_from_row


def test_evtx_summary_combines_event_id_description_user():
    row = {
        "EventId": "4624",
        "Description": "Successful logon",
        "UserName": "DOMAIN\\jsmith",
        "Channel": "Security",
    }
    summary = _summary_from_row(row, "demo-security.csv")
    assert summary == "Event 4624: Successful logon — DOMAIN\\jsmith — [Security]"


def test_fallback_summary_uses_first_available_field():
    row = {"FullPath": "C:\\Windows\\System32\\cmd.exe"}
    summary = _summary_from_row(row, "mft.csv")
    assert summary == "FullPath: C:\\Windows\\System32\\cmd.exe"
