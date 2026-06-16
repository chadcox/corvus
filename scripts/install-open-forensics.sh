#!/usr/bin/env bash
set -euo pipefail

INSTALL_ROOT="${INSTALL_ROOT:-/opt/open-forensics}"
INSTALL_PLASO="${INSTALL_PLASO:-true}"
INSTALL_MAC_APT="${INSTALL_MAC_APT:-true}"
INSTALL_VOLATILITY3="${INSTALL_VOLATILITY3:-false}"

mkdir -p "$INSTALL_ROOT/bin"

if [[ "$INSTALL_PLASO" == "true" ]]; then
  python -m pip install --no-cache-dir plaso
fi

if [[ "$INSTALL_MAC_APT" == "true" ]]; then
  if [[ ! -d "$INSTALL_ROOT/mac_apt/.git" ]]; then
    git clone --depth 1 https://github.com/ydkhatri/mac_apt.git "$INSTALL_ROOT/mac_apt"
  fi
  python -m pip install --no-cache-dir -r "$INSTALL_ROOT/mac_apt/requirements.txt" || true
  ln -sf "$INSTALL_ROOT/mac_apt/mac_apt.py" "$INSTALL_ROOT/bin/mac_apt.py"
  chmod +x "$INSTALL_ROOT/mac_apt/mac_apt.py"
fi

if [[ "$INSTALL_VOLATILITY3" == "true" ]]; then
  python -m pip install --no-cache-dir volatility3
fi
