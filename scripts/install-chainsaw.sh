#!/usr/bin/env bash
# Install Chainsaw hunt binary (Linux x86_64) from GitHub releases.
set -euo pipefail

VERSION="${CHAINSAW_VERSION:-2.16.0}"
# SHA256 of chainsaw_x86_64-unknown-linux-gnu.tar.gz for the pinned VERSION.
# Override CHAINSAW_SHA256 too if you change CHAINSAW_VERSION.
SHA256="${CHAINSAW_SHA256:-5d46cd140838413aeb5711451a282b3922443d9ec6afaea3e6b6b220454fd807}"
DEST="${1:-/usr/local/bin/chainsaw}"
ARCH="x86_64-unknown-linux-gnu"
TARBALL="/tmp/chainsaw-${VERSION}-${ARCH}.tar.gz"
URL="https://github.com/WithSecureLabs/chainsaw/releases/download/v${VERSION}/chainsaw_${ARCH}.tar.gz"

echo "Installing chainsaw ${VERSION} → ${DEST}"
wget -q "${URL}" -O "${TARBALL}"
echo "${SHA256}  ${TARBALL}" | sha256sum -c -
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
