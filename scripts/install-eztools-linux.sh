#!/usr/bin/env bash
# Install Eric Zimmerman .NET 9 tools to EZTOOLS_ROOT (used in worker Docker build).
set -euo pipefail

EZTOOLS_ROOT="${1:-/opt/eztools}"
BASE_URL="${BASE_URL:-https://download.ericzimmermanstools.com/net9}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHECKSUM_FILE="${CHECKSUM_FILE:-${SCRIPT_DIR}/eztools-checksums.sha256}"
VERIFY_CHECKSUMS="${VERIFY_EZTOOLS_CHECKSUMS:-1}"

TOOLS=(EvtxECmd MFTECmd RECmd AmcacheParser PECmd JLECmd LECmd)

mkdir -p "${EZTOOLS_ROOT}"
apt-get update -qq && apt-get install -y -qq wget unzip ca-certificates >/dev/null

verify_checksum() {
  local zip_path="$1"
  local tool="$2"
  if [[ "${VERIFY_CHECKSUMS}" != "1" ]] || [[ ! -f "${CHECKSUM_FILE}" ]]; then
    return 0
  fi
  local expected
  expected="$(grep -E "[[:space:]]${tool}\\.zip$" "${CHECKSUM_FILE}" | awk '{print $1}' || true)"
  if [[ -z "${expected}" ]]; then
    echo "WARN: no checksum pinned for ${tool}.zip — skipping verify"
    return 0
  fi
  local actual
  actual="$(sha256sum "${zip_path}" | awk '{print $1}')"
  if [[ "${actual}" != "${expected}" ]]; then
    echo "FAIL: ${tool}.zip checksum mismatch (expected ${expected}, got ${actual})"
    exit 1
  fi
}

for tool in "${TOOLS[@]}"; do
  echo "Installing ${tool}..."
  wget -q "${BASE_URL}/${tool}.zip" -O "/tmp/${tool}.zip"
  verify_checksum "/tmp/${tool}.zip" "${tool}"
  unzip -qo "/tmp/${tool}.zip" -d "${EZTOOLS_ROOT}/${tool}"
  rm -f "/tmp/${tool}.zip"
done

echo "EZ Tools installed to ${EZTOOLS_ROOT}"
