from worker.sigma.loader import SigmaRule
from worker.sigma.matcher import normalize_event_fields, rule_matches_event


def _rule(detection: dict, **logsource) -> SigmaRule:
    return SigmaRule(
        path=None,  # type: ignore[arg-type]
        title="Test rule",
        rule_id="test-rule-id",
        level="high",
        description="",
        tags=[],
        logsource={"product": "windows", **logsource},
        detection=detection,
    )


def test_failed_logon_event_id_match():
    rule = _rule(
        {"selection": {"EventID": 4625}, "condition": "selection"},
        service="security",
    )
    fields = normalize_event_fields(
        {
            "EventId": "4625",
            "Channel": "Security",
            "TargetUserName": "DOMAIN\\user",
        }
    )
    assert rule_matches_event(rule, fields)


def test_copylog_event_does_not_match_security_rule():
    rule = _rule(
        {"selection": {"EventID": 4625}, "condition": "selection"},
        service="security",
    )
    fields = normalize_event_fields(
        {"SourceFile": r"c:\Users\chad\file.txt", "CopiedTimestamp": "2026-01-01 00:00:00"}
    )
    assert not rule_matches_event(rule, fields)
