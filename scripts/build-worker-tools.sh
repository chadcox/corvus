#!/usr/bin/env bash
# Build and tag the heavy worker image once, then reuse it in dev-tools mode.
#
# Usage:
#   ./scripts/build-worker-tools.sh
#   ./scripts/build-worker-tools.sh --tag forensicflow-worker:tools
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

TAG="${WORKER_TOOLS_IMAGE:-forensicflow-worker:tools}"
NO_CACHE=0

while [ $# -gt 0 ]; do
  case "$1" in
    --tag)
      TAG="$2"
      shift 2
      ;;
    --no-cache)
      NO_CACHE=1
      shift
      ;;
    -h|--help)
      sed -n '2,9p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown option: $1 (try --help)" >&2
      exit 1
      ;;
  esac
done

echo "=== Build worker tools image ==="
echo "Tag: $TAG"
if [ "$NO_CACHE" -eq 1 ]; then
  docker build --no-cache \
    -f apps/worker/Dockerfile \
    --build-arg INSTALL_OPEN_FORENSICS=true \
    --build-arg INSTALL_VOLATILITY3="${INSTALL_VOLATILITY3:-true}" \
    -t "$TAG" .
else
  docker build \
    -f apps/worker/Dockerfile \
    --build-arg INSTALL_OPEN_FORENSICS=true \
    --build-arg INSTALL_VOLATILITY3="${INSTALL_VOLATILITY3:-true}" \
    -t "$TAG" .
fi

echo "Built: $TAG"
echo "Run dev tools mode with:"
echo "  WORKER_TOOLS_IMAGE=$TAG ./scripts/rebuild-stack.sh --tools"
