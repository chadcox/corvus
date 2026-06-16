#!/usr/bin/env bash
# Phase 0 gate: verify EZ Tools run on this host (Linux).
set -euo pipefail

EZTOOLS_ROOT="${EZTOOLS_ROOT:-/opt/eztools}"
PASS=0
FAIL=0

run_tool() {
  local name="$1"
  local dll="$2"
  shift 2
  if [[ ! -f "${dll}" ]]; then
    echo "SKIP ${name}: not found at ${dll}"
    ((FAIL++)) || true
    return
  fi
  if dotnet "${dll}" --help &>/dev/null; then
    echo "PASS ${name}"
    ((PASS++)) || true
  else
    echo "FAIL ${name}"
    ((FAIL++)) || true
  fi
}

if ! command -v dotnet &>/dev/null; then
  echo "FAIL: dotnet runtime not installed (.NET 9 required)"
  exit 1
fi

echo "EZTOOLS_ROOT=${EZTOOLS_ROOT}"
echo "dotnet $(dotnet --version)"

TOOLS=(
  "EvtxECmd:EvtxECmd/EvtxECmd.dll"
  "MFTECmd:MFTECmd/MFTECmd.dll"
  "RECmd:RECmd/RECmd.dll"
  "AmcacheParser:AmcacheParser/AmcacheParser.dll"
  "PECmd:PECmd/PECmd.dll"
  "JLECmd:JLECmd/JLECmd.dll"
  "LECmd:LECmd/LECmd.dll"
)

for entry in "${TOOLS[@]}"; do
  name="${entry%%:*}"
  path="${entry#*:}"
  run_tool "${name}" "${EZTOOLS_ROOT}/${path}"
done

echo "---"
echo "Pass: ${PASS}  Fail/SKIP: ${FAIL}"
if [[ "${FAIL}" -gt 0 ]]; then
  echo "Recommendation: deploy workers on Windows Server or require KAPE !EZParser CSV output."
  exit 1
fi
echo "All tools available. Linux deployment OK."
