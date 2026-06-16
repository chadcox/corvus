#!/usr/bin/env bash
# Programmatic ingest validation via API only (no UI).
# Usage:
#   ./scripts/validate-ingest.sh                    # samples/c.zip
#   ./scripts/validate-ingest.sh samples/c.zip
#   SAMPLE=kape-minimal ./scripts/validate-ingest.sh
#   ./scripts/validate-ingest.sh --sample kape-minimal
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API="${API_URL:-http://localhost:8000}"
MAX_WAIT="${MAX_WAIT:-900}"
POLL="${POLL:-3}"
USE_SAMPLE_API="${USE_SAMPLE_API:-1}"
MIN_FS="${MIN_FILESYSTEM_NODES:-0}"

ZIP=""
SAMPLE=""

while [ $# -gt 0 ]; do
  case "$1" in
    --sample)
      SAMPLE="$2"
      shift 2
      ;;
    --max-wait)
      MAX_WAIT="$2"
      shift 2
      ;;
    --min-filesystem)
      MIN_FS="$2"
      shift 2
      ;;
    --api-url)
      API="$2"
      shift 2
      ;;
    *)
      ZIP="$1"
      shift
      ;;
  esac
done

if [ -z "$SAMPLE" ] && [ -z "$ZIP" ]; then
  if [ -f "$ROOT/samples/c.zip" ]; then
    SAMPLE="c"
  else
    SAMPLE="kape-minimal"
  fi
fi

echo "=== ForensicFlow ingest validation ==="
echo "API: $API"

echo "=== Health ==="
curl -sf "$API/health/ready" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d.get('status')=='ready', d"

if [ "$USE_SAMPLE_API" = "1" ] && [ -n "$SAMPLE" ]; then
  echo "=== Start ingest (sample=$SAMPLE) ==="
  START=$(curl -sf -X POST "$API/api/v1/validation/ingest-sample?sample=${SAMPLE}&min_filesystem_nodes=${MIN_FS}")
  JOB_ID=$(echo "$START" | python3 -c "import sys,json; print(json.load(sys.stdin)['job_id'])")
  OUTCOME_PATH=$(echo "$START" | python3 -c "import sys,json; print(json.load(sys.stdin)['outcome_path'])")
  CASE_ID=$(echo "$START" | python3 -c "import sys,json; print(json.load(sys.stdin)['case_id'])")
  SOURCE_ID=$(echo "$START" | python3 -c "import sys,json; print(json.load(sys.stdin)['evidence_source_id'])")
  echo "Case: $CASE_ID"
  echo "Source: $SOURCE_ID"
  echo "Job: $JOB_ID"
else
  if [ -z "$ZIP" ]; then
    ZIP="$ROOT/samples/${SAMPLE:-kape-minimal}.zip"
  fi
  if [ ! -f "$ZIP" ] && [ -d "$ROOT/samples/kape-minimal" ]; then
    echo "Building kape-minimal.zip..."
    (cd "$ROOT/samples" && zip -qr kape-minimal.zip kape-minimal/)
  fi
  [ -f "$ZIP" ] || { echo "ZIP not found: $ZIP"; exit 1; }

  echo "=== Upload $ZIP ==="
  CASE=$(curl -sf -X POST "$API/api/v1/cases" \
    -H 'Content-Type: application/json' \
    -d "{\"name\":\"validate-ingest $(basename "$ZIP")\"}")
  CASE_ID=$(echo "$CASE" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
  JOB=$(curl -sf -X POST "$API/api/v1/cases/$CASE_ID/evidence/upload" -F "file=@$ZIP")
  JOB_ID=$(echo "$JOB" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
  SOURCE_ID=$(echo "$JOB" | python3 -c "import sys,json; print(json.load(sys.stdin)['evidence_source_id'])")
  OUTCOME_PATH="/api/v1/jobs/${JOB_ID}/outcome?min_timeline_events=1&min_filesystem_nodes=${MIN_FS}"
fi

echo "=== Poll outcome (max ${MAX_WAIT}s) ==="
ELAPSED=0
while [ "$ELAPSED" -lt "$MAX_WAIT" ]; do
  OUTCOME=$(curl -sf "$API${OUTCOME_PATH}")
  echo "$OUTCOME" | python3 -c "
import sys, json
o = json.load(sys.stdin)
print(f\"  {o['job_status']} ({o['progress']}%) — {o.get('message') or ''}\")
for c in o.get('checks', []):
    mark = 'ok' if c['passed'] else 'FAIL'
    print(f\"    [{mark}] {c['name']}: {c.get('detail') or ''}\")
"
  DONE=$(echo "$OUTCOME" | python3 -c "import sys,json; o=json.load(sys.stdin); print('yes' if o['job_status'] in ('completed','failed') else 'no')")
  SUCCESS=$(echo "$OUTCOME" | python3 -c "import sys,json; print('yes' if json.load(sys.stdin).get('success') else 'no')")
  if [ "$DONE" = "yes" ]; then
    if [ "$SUCCESS" = "yes" ]; then
      echo "=== VALIDATION PASSED ==="
      echo "$OUTCOME" | python3 -m json.tool
      exit 0
    fi
    echo "=== VALIDATION FAILED ==="
    echo "$OUTCOME" | python3 -m json.tool
    exit 1
  fi
  sleep "$POLL"
  ELAPSED=$((ELAPSED + POLL))
done

echo "TIMEOUT after ${MAX_WAIT}s"
exit 1
