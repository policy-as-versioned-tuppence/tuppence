#!/usr/bin/env bash
# Version and digest come from the one shared action. Download and install only
# under runner temp: scheduled jobs must leave their checkout untouched.
set -euo pipefail
version="${1:?version required}"
digest="${2:?sha256 required}"
: "${RUNNER_TEMP:?RUNNER_TEMP required}"
: "${GITHUB_PATH:?GITHUB_PATH required}"
mkdir -p "$RUNNER_TEMP"
work="$(mktemp -d "$RUNNER_TEMP/gitsign-download.XXXXXX")"
trap 'rm -rf "$work"' EXIT
curl -fsSL -o "$work/gitsign" "https://github.com/sigstore/gitsign/releases/download/v${version}/gitsign_${version}_linux_amd64"
printf '%s  %s\n' "$digest" "$work/gitsign" | sha256sum -c -
install_dir="$RUNNER_TEMP/pavf-gitsign/bin"
mkdir -p "$install_dir"
install -m 755 "$work/gitsign" "$install_dir/gitsign"
printf '%s\n' "$install_dir" >> "$GITHUB_PATH"
