#!/usr/bin/env bash
# Shared config + helpers for the tuppence bring-up. Sourced, not run.
set -euo pipefail

CLUSTER=tuppence
CTX="kind-${CLUSTER}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # estate/tuppence
GITOPS_DIR="${HERE}/gitops"
GITSERVER_DIR="${HERE}/git-server"
WORK="${HERE}/.work"
IMAGE=tuppence-git:local
GIT_URL_IN_CLUSTER="http://git-server.flux-system.svc.cluster.local/cgi-bin/git/tuppence.git"

say() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }

require() {
  local missing=0
  for c in "$@"; do have "$c" || { echo "MISSING cli: $c" >&2; missing=1; }; done
  [ "$missing" = 0 ] || { echo "install the missing CLIs and re-run" >&2; exit 1; }
}

# Substrate gate for live-claiming scripts. PASS and FAIL are observations of a
# cluster; when there is nothing to observe the only honest answer is SKIP.
# Exit 3 = SKIP, distinct from 0 (PASS) and 1 (FAIL). Call it before any assertion.
skip() { echo "SKIP: $*"; exit 3; }
need_substrate() { # $1 = kind cluster name (default: $CLUSTER)
  local c="${1:-$CLUSTER}" ctx="kind-${1:-$CLUSTER}" ks k
  have docker && have kind && have kubectl || skip "docker, kind and kubectl are all needed to look at a cluster"
  docker info >/dev/null 2>&1 || skip "docker is not running"
  kind get clusters 2>/dev/null | grep -qx "$c" || skip "kind cluster '$c' does not exist"
  ks=$(kubectl --context "$ctx" --request-timeout=20s -n flux-system get kustomizations.kustomize.toolkit.fluxcd.io \
       -o jsonpath='{range .items[*]}{.metadata.name}={.status.conditions[?(@.type=="Ready")].status}{" "}{end}' 2>/dev/null) \
    || skip "context '$ctx' did not answer, or Flux is not installed"
  [ -n "$ks" ] || skip "no Flux Kustomization in flux-system on '$ctx'"
  for k in $ks; do case "$k" in *=True) ;; *) skip "Flux Kustomization not Ready on '$ctx': $k";; esac; done
}
