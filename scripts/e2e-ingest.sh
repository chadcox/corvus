#!/usr/bin/env bash
# End-to-end ingest validation using samples/kape-minimal.zip
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API="${API_URL:-http://localhost:8000}"
ZIP="$ROOT/samples/kape-minimal.zip"

if [ ! -f "$ZIP" ]; then
  echo "Building sample ZIP..."
  (cd "$ROOT/samples" && zip -qr kape-minimal.zip kape-minimal/)
fi

echo "=== Health check ==="
curl -sf "$API/health" | grep -q ok
curl -sf "$API/health/ready" | grep -q ready

echo "=== Create case ==="
CASE=$(curl -sf -X POST "$API/api/v1/cases" \
  -H 'Content-Type: application/json' \
  -d '{"name":"E2E kape-minimal validation"}')
CASE_ID=$(echo "$CASE" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "Case: $CASE_ID"

echo "=== Upload ==="
JOB=$(curl -sf -X POST "$API/api/v1/cases/$CASE_ID/evidence/upload" -F "file=@$ZIP")
JOB_ID=$(echo "$JOB" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
SOURCE_ID=$(echo "$JOB" | python3 -c "import sys,json; print(json.load(sys.stdin)['evidence_source_id'])")

echo "=== Poll job ==="
for _ in $(seq 1 30); do
  J=$(curl -sf "$API/api/v1/jobs/$JOB_ID")
  STATUS=$(echo "$J" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")
  MSG=$(echo "$J" | python3 -c "import sys,json; print(json.load(sys.stdin).get('message') or '')")
  echo "  $STATUS — $MSG"
  [ "$STATUS" = "completed" ] || [ "$STATUS" = "failed" ] && break
  sleep 2
done
[ "$STATUS" = "completed" ] || { echo "FAILED"; exit 1; }

echo "=== Assertions ==="
python3 - <<PY
import json, subprocess, sys

def get(path):
    out = subprocess.check_output(["curl", "-sf", f"$API{path}"])
    return json.loads(out)

evidence = get(f"/api/v1/cases/$CASE_ID/evidence")
assert len(evidence) == 1, evidence
src = evidence[0]
assert src["hostname"] == "WKS-DEMO", f"hostname: {src['hostname']}"
assert src["manifest"] is not None, "manifest missing"
assert src["manifest"]["collector"] == "kape"

stats = get(f"/api/v1/cases/$CASE_ID/sources/$SOURCE_ID/stats")
assert stats["timeline_count"] == 3, stats
assert stats["entity_count"] == 2, stats
assert stats["filesystem_count"] >= 1, stats

timeline = get(f"/api/v1/cases/$CASE_ID/sources/$SOURCE_ID/timeline")
assert all(e.get("entity_refs") for e in timeline), "entity_refs missing"
assert "Event 4624" in timeline[0]["summary"]

search = get(f"/api/v1/cases/$CASE_ID/sources/$SOURCE_ID/search?q=jsmith")
assert search["total"] >= 1, search

print("All assertions passed.")
PY

echo "=== E2E OK ==="
