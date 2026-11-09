#!/usr/bin/env bash
# Install the pinned tools that `make check` and CI use. Used by validate, agent-dev and agent-fix.
# ruff and zizmor are pinned in requirements-lint.txt (Dependabot's pip ecosystem reads it). actionlint is pinned here
# together with its SHA-256; bump both (the checksum is in the release's actionlint_<version>_checksums.txt).
#   install_tools.sh        everything: ruff, zizmor, pytest-timeout, requirements_test.txt, actionlint
#   install_tools.sh lint   only the lint tools (ruff, zizmor, actionlint; no test dependencies)
set -euo pipefail
ACTIONLINT=1.7.7
# The override exists only to test that a wrong checksum fails the install.
ACTIONLINT_SHA256="${ACTIONLINT_SHA256_OVERRIDE:-023070a287cd8cccd71515fedc843f1985bf96c436b7effaecce67290e7e0757}"
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
if [ "${1:-}" = lint ]; then
  pip install -r "$root/requirements-lint.txt"
else
  pip install -r "$root/requirements-lint.txt" pytest-timeout
  for f in requirements.txt requirements_test.txt; do
    if [ -f "$f" ]; then pip install -r "$f"; fi
  done
fi
# Project-specific extra command: only from the environment (repo variable vars.EXTRA_INSTALL), never from a file in the
# checkout, because a PR branch must not be able to change what runs here.
if [ -n "${EXTRA_INSTALL:-}" ]; then bash -c "$EXTRA_INSTALL"; fi
dir="${RUNNER_TEMP:-/tmp}/actionlint"
mkdir -p "$dir"
tarball="$dir/actionlint.tar.gz"
curl -fsSL -o "$tarball" "https://github.com/rhysd/actionlint/releases/download/v${ACTIONLINT}/actionlint_${ACTIONLINT}_linux_amd64.tar.gz"
echo "${ACTIONLINT_SHA256}  $tarball" | sha256sum -c -
tar -xz -C "$dir" -f "$tarball" actionlint
if [ -n "${GITHUB_PATH:-}" ]; then echo "$dir" >> "$GITHUB_PATH"; fi
