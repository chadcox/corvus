#!/usr/bin/env bash
# Install Chainsaw hunt binary (Linux x86_64) from GitHub releases.
set -euo pipefail

VERSION="${CHAINSAW_VERSION:-2.16.0}"
DEST="${1:-/usr/local/bin/chainsaw}"
ARCH="x86_64-unknown-linux-gnu"
TARBALL="/tmp/chainsaw-${VERSION}-${ARCH}.tar.gz"
URL="https://github.com/WithSecureLabs/chainsaw/releases/download/v${VERSION}/chainsaw_${ARCH}.tar.gz"

echo "Installing chainsaw ${VERSION} → ${DEST}"
wget -q "${URL}" -O "${TARBALL}"
rm -rf /tmp/chainsaw-install
mkdir -p /tmp/chainsaw-install
tar xzf "${TARBALL}" -C /tmp/chainsaw-install
BIN="$(find /tmp/chainsaw-install -type f -name chainsaw -executable 2>/dev/null | head -1)"
if [[ -z "${BIN}" ]]; then
  echo "FAIL: chainsaw binary not found in archive"
  exit 1
fi
install -m 0755 "${BIN}" "${DEST}"
rm -rf /tmp/chainsaw-install "${TARBALL}"
"${DEST}" --version
