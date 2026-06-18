#!/usr/bin/env bash
# Bundle YARA rules from Neo23x0/signature-base for offline scanning.
set -euo pipefail

DEST="${1:-/opt/yara-bundled/signature-base}"
# signature-base has no stable releases; pin to a commit for reproducible builds.
REF="${YARA_REF:-43b2b2faafdaeb7f00102673f62555a2feb04c1b}"

rm -rf "${DEST}"
mkdir -p "${DEST}"
ARCHIVE="/tmp/signature-base-${REF}.zip"
BASE_URL="https://github.com/Neo23x0/signature-base/archive/${REF}.zip"

echo "Downloading signature-base (${REF}) -> ${DEST}..."
wget -q "${BASE_URL}" -O "${ARCHIVE}"
rm -rf /tmp/signature-base-extract
unzip -qo "${ARCHIVE}" -d /tmp/signature-base-extract

ROOT="$(find /tmp/signature-base-extract -mindepth 1 -maxdepth 1 -type d -name 'signature-base-*' | head -1)"
if [[ -z "${ROOT}" || ! -d "${ROOT}/yara" ]]; then
  echo "FAIL: could not find extracted signature-base folder (expected signature-base-*/yara)"
  exit 1
fi

cp -a "${ROOT}/yara" "${DEST}/"
if [[ -d "${ROOT}/vendor" ]]; then
  cp -a "${ROOT}/vendor" "${DEST}/"
fi

COUNT="$(find "${DEST}" -type f \( -name '*.yar' -o -name '*.yara' \) | wc -l)"
echo "YARA rules installed: ${COUNT} files under ${DEST}"

rm -f "${ARCHIVE}"
rm -rf /tmp/signature-base-extract
