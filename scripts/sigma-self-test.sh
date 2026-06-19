#!/usr/bin/env bash
# Verify Sigma rule bundle + matcher inside the worker container.
set -euo pipefail

SERVICE="${SIGMA_TEST_SERVICE:-corvus-worker-1}"

echo "== Sigma self-test (service: ${SERVICE}) =="

docker exec "${SERVICE}" bash -c 'cd /app/apps/worker && PYTHONPATH=. python - << "PY"
from pathlib import Path
from worker.config import settings
from worker.sigma.loader import load_sigma_rules
from worker.sigma.matcher import normalize_event_fields, rule_matches_event
from worker.sigma.evaluate import evaluate_sigma_rules
from worker.sigma.diagnostics import summarize_sigma_inputs
import yaml
from worker.sigma.loader import _parse_rule

root = Path(settings.sigma_rules_root)
rules = load_sigma_rules(root)
assert len(rules) > 500, f"expected 500+ rules, got {len(rules)}"
print(f"OK rules_loaded={len(rules)}")

# CopyLog must not match Security rules
copylog = {"SourceFile": r"C:\x.txt", "CopiedTimestamp": "2026-01-01 00:00:00"}
assert not normalize_event_fields(copylog).get("eventid")
stats = summarize_sigma_inputs([{"event_type": "kape.collection", "data": copylog}])
assert stats["sigma_eligible"] == 0
print("OK copylog_not_sigma_eligible")

# Full-field Security event should match at least one rule
admin_rdp = Path("/opt/sigma/rules/rules/windows/builtin/security/account_management/win_security_admin_rdp_login.yml")
rule = _parse_rule(admin_rdp, yaml.safe_load(admin_rdp.read_text()))
data = {
    "EventId": "4624",
    "Channel": "Security",
    "LogonType": "10",
    "TargetUserName": "Administrator",
    "AuthenticationPackageName": "Negotiate",
}
assert rule_matches_event(rule, normalize_event_fields(data))
dets, _ = evaluate_sigma_rules([{"id": "t", "data": data}], "test")
assert len(dets) >= 1, "evaluate_sigma_rules should aggregate >=1 detection"
print("OK evaluate_detections=%d example=%r" % (len(dets), dets[0]["title"]))

print("Sigma self-test passed.")
PY'

echo "Done."
