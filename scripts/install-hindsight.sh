#!/usr/bin/env bash
# Install Hindsight (pyhindsight) and ccl_chromium_reader for Chromium browser forensics.
set -euo pipefail

HINDSIGHT_REF="${HINDSIGHT_REF:-main}"

echo "Installing ccl_chromium_reader…"
pip install --no-cache-dir "git+https://github.com/cclgroupltd/ccl_chromium_reader.git"

echo "Installing Hindsight (pyhindsight) from RyanDFIR/hindsight@${HINDSIGHT_REF}…"
pip install --no-cache-dir "git+https://github.com/RyanDFIR/hindsight.git@${HINDSIGHT_REF}"

if command -v hindsight.py >/dev/null 2>&1; then
  echo "Hindsight CLI: $(command -v hindsight.py)"
else
  # pip scripts may land on PATH as hindsight.py in /usr/local/bin
  for candidate in /usr/local/bin/hindsight.py /usr/local/bin/hindsight; do
    if [[ -x "$candidate" ]]; then
      ln -sf "$candidate" /usr/local/bin/hindsight
      echo "Hindsight CLI: /usr/local/bin/hindsight"
      break
    fi
  done
fi

python3 -c "import pyhindsight; print('pyhindsight', pyhindsight.__version__)"
