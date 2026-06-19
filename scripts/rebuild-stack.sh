#!/usr/bin/env bash
# Start or rebuild the Corvus Docker stack.
#
# Usage:
#   ./scripts/rebuild-stack.sh
#   ./scripts/rebuild-stack.sh --tools
#   ./scripts/rebuild-stack.sh --full
#   ./scripts/rebuild-stack.sh --no-cache
#   ./scripts/rebuild-stack.sh --pull          # pull base images first
#   ./scripts/rebuild-stack.sh --no-wait       # skip readiness poll
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

API="${API_URL:-http://localhost:8000}"
WEB="${WEB_URL:-http://localhost:5173}"
MAX_WAIT="${MAX_WAIT:-120}"
POLL="${POLL:-2}"

NO_CACHE=0
PULL=0
WAIT=1
MODE="fast"

while [ $# -gt 0 ]; do
  case "$1" in
    --no-cache)
      NO_CACHE=1
      shift
      ;;
    --pull)
      PULL=1
      shift
      ;;
    --full)
      MODE="full"
      shift
      ;;
    --tools)
      MODE="tools"
      shift
      ;;
    --no-wait)
      WAIT=0
      shift
      ;;
    -h|--help)
      sed -n '2,10p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown option: $1 (try --help)" >&2
      exit 1
      ;;
  esac
done

if [ ! -f docker-compose.yml ]; then
  echo "FAIL: docker-compose.yml not found in $ROOT" >&2
  exit 1
fi
if [ ! -f docker-compose.dev.yml ]; then
  echo "FAIL: docker-compose.dev.yml not found in $ROOT" >&2
  exit 1
fi

echo "=== Corvus stack start ==="
echo "Project: $ROOT"
echo "Mode: $MODE"
echo ""

COMPOSE=(docker compose)
PROFILE_ARGS=()
if [ "$MODE" = "fast" ] || [ "$MODE" = "tools" ]; then
  COMPOSE=(-f docker-compose.yml -f docker-compose.dev.yml)
  COMPOSE=(docker compose "${COMPOSE[@]}")
  if [ "$MODE" = "fast" ]; then
    PROFILE_ARGS=(--profile dev-fast)
  else
    PROFILE_ARGS=(--profile dev-tools)
  fi
fi

if [ "$PULL" -eq 1 ]; then
  echo "Pulling base images…"
  "${COMPOSE[@]}" "${PROFILE_ARGS[@]}" pull
  echo ""
fi

if [ "$MODE" = "full" ]; then
  if [ "$NO_CACHE" -eq 1 ]; then
    echo "Full rebuild with --no-cache…"
    docker compose build --no-cache
    docker compose up -d
  else
    echo "Full rebuild of all services…"
    docker compose up -d --build
  fi
elif [ "$MODE" = "tools" ]; then
  if [ "$NO_CACHE" -eq 1 ]; then
    echo "Fast tools mode with worker-tools rebuild --no-cache…"
    "${COMPOSE[@]}" "${PROFILE_ARGS[@]}" build --no-cache api web
    "${COMPOSE[@]}" "${PROFILE_ARGS[@]}" up -d api web postgres redis opensearch worker_tools beat_tools
  else
    echo "Fast tools mode (live-mounted app code + prebuilt worker tools image)…"
    "${COMPOSE[@]}" "${PROFILE_ARGS[@]}" up -d api web postgres redis opensearch worker_tools beat_tools
  fi
else
  if [ "$NO_CACHE" -eq 1 ]; then
    echo "Fast mode with --no-cache for API/web images…"
    "${COMPOSE[@]}" "${PROFILE_ARGS[@]}" build --no-cache api web worker beat
    "${COMPOSE[@]}" "${PROFILE_ARGS[@]}" up -d api web postgres redis opensearch worker beat
  else
    echo "Fast mode (live-mounted app code; no full stack rebuild)…"
    "${COMPOSE[@]}" "${PROFILE_ARGS[@]}" up -d api web postgres redis opensearch worker beat
  fi
fi

echo ""
"${COMPOSE[@]}" "${PROFILE_ARGS[@]}" ps

if [ "$WAIT" -eq 1 ]; then
  echo ""
  echo "Waiting for API readiness (max ${MAX_WAIT}s)…"
  deadline=$((SECONDS + MAX_WAIT))
  while [ "$SECONDS" -lt "$deadline" ]; do
    if curl -sf "$API/health/ready" >/dev/null 2>&1; then
      echo "API ready."
      break
    fi
    sleep "$POLL"
  done
  if ! curl -sf "$API/health/ready" >/dev/null 2>&1; then
    echo "WARN: API not ready after ${MAX_WAIT}s — check: docker compose logs api worker worker_tools" >&2
  fi
fi

echo ""
echo "=== Stack up ==="
echo "  Web:  $WEB"
echo "  API:  $API"
echo "  Docs: $API/docs"
echo ""
echo "Logs:  docker compose logs -f worker worker_tools"
echo "Health: curl -s $API/health/ready | jq ."
