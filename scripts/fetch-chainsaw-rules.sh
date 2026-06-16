#!/usr/bin/env bash
# Bundle Chainsaw detection rules and Sigma mappings from WithSecureLabs/chainsaw.
# https://github.com/WithSecureLabs/chainsaw
set -euo pipefail

DEST="${1:-/opt/chainsaw-bundled}"
REF="${CHAINSAW_REF:-master}"
ARCHIVE="/tmp/chainsaw-${REF}.zip"
BASE_URL="https://github.com/WithSecureLabs/chainsaw/archive/refs/heads/${REF}.zip"

echo "Downloading Chainsaw rules (${REF}) → ${DEST}…"
rm -rf "${DEST}"
mkdir -p "${DEST}"
wget -q "${BASE_URL}" -O "${ARCHIVE}"
rm -rf /tmp/chainsaw-extract
unzip -qo "${ARCHIVE}" -d /tmp/chainsaw-extract

ROOT="$(find /tmp/chainsaw-extract -mindepth 1 -maxdepth 1 -type d -name 'chainsaw-*' | head -1)"
if [[ -z "${ROOT}" ]]; then
  echo "FAIL: could not find extracted chainsaw folder"
  exit 1
fi

mkdir -p "${DEST}/rules" "${DEST}/mappings"
if [[ -d "${ROOT}/rules/evtx" ]]; then
  cp -a "${ROOT}/rules/evtx" "${DEST}/rules/"
  echo "  + rules/evtx"
fi
if [[ -d "${ROOT}/rules/mft" ]]; then
  cp -a "${ROOT}/rules/mft" "${DEST}/rules/"
  echo "  + rules/mft"
fi
if [[ -d "${ROOT}/mappings" ]]; then
  cp -a "${ROOT}/mappings/." "${DEST}/mappings/"
  echo "  + mappings/"
fi

RULE_COUNT="$(find "${DEST}/rules" -name '*.yml' -o -name '*.yaml' 2>/dev/null | wc -l)"
MAP_COUNT="$(find "${DEST}/mappings" -name '*.yml' -o -name '*.yaml' 2>/dev/null | wc -l)"
echo "Chainsaw bundle: ${RULE_COUNT} rule files, ${MAP_COUNT} mapping files under ${DEST}"
rm -f "${ARCHIVE}"
rm -rf /tmp/chainsaw-extract
