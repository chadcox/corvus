#!/usr/bin/env bash
# Download net9 EZ Tool zips and print sha256 lines for scripts/eztools-checksums.sha256
set -euo pipefail

BASE_URL="${BASE_URL:-https://download.ericzimmermanstools.com/net9}"
TOOLS=(EvtxECmd MFTECmd RECmd AmcacheParser PECmd JLECmd LECmd)

for tool in "${TOOLS[@]}"; do
  tmp="/tmp/${tool}.zip"
  wget -q "${BASE_URL}/${tool}.zip" -O "${tmp}"
  sha256sum "${tmp}" | awk -v name="${tool}.zip" '{print $1, name}'
  rm -f "${tmp}"
done
