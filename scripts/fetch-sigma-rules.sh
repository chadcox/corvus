#!/usr/bin/env bash
# Bundle Sigma rules from SigmaHQ for offline ingest-time matching.
# https://github.com/SigmaHQ/sigma
set -euo pipefail

DEST="${1:-/opt/sigma/rules}"
# Pinned to a SigmaHQ release tag; the beat scheduler refreshes rules at runtime.
REF="${SIGMA_REF:-r2026-04-01}"

# Replace destination atomically when updating an existing bundle.
rm -rf "${DEST}"
mkdir -p "${DEST}"
ARCHIVE="/tmp/sigma-${REF}.zip"
BASE_URL="https://github.com/SigmaHQ/sigma/archive/${REF}.zip"

echo "Downloading Sigma rules (${REF}) → ${DEST}…"
wget -q "${BASE_URL}" -O "${ARCHIVE}"
rm -rf /tmp/sigma-extract
unzip -qo "${ARCHIVE}" -d /tmp/sigma-extract

ROOT="$(find /tmp/sigma-extract -mindepth 1 -maxdepth 1 -type d -name 'sigma-*' | head -1)"
if [[ -z "${ROOT}" || ! -d "${ROOT}/rules" ]]; then
  echo "FAIL: could not find extracted sigma folder (expected sigma-*/rules)"
  exit 1
fi

copy_tree() {
  local src="$1"
  if [[ -d "${ROOT}/${src}" ]]; then
    mkdir -p "${DEST}/$(dirname "${src}")"
    cp -a "${ROOT}/${src}" "${DEST}/$(dirname "${src}")/"
    echo "  + ${src}"
  fi
}

# Windows EVTX / IR-focused Sigma rules (subset of SigmaHQ repo)
# Set SIGMA_PROFILE=full in env to load every bundled rule without DFIR filtering.
for path in \
  rules/windows/builtin/security \
  rules/windows/sysmon \
  rules/windows/powershell \
  rules/windows/process_creation \
  rules/windows/registry \
  rules/windows/network_connection \
  rules/windows/file \
  rules-dfir \
  rules-threat-hunting/windows
do
  copy_tree "${path}"
done

COUNT="$(find "${DEST}" -name '*.yml' -o -name '*.yaml' | wc -l)"
echo "Sigma rules installed: ${COUNT} files under ${DEST}"
rm -f "${ARCHIVE}"
rm -rf /tmp/sigma-extract
