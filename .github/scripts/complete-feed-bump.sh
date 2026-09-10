#!/usr/bin/env bash
# complete-feed-bump.sh -- eco-system ticket 61. Renovate runs this as a
# postUpgradeTasks command on its own bump branch, after it has edited the
# pin. A pin bump alone can never go green: shift-left's compose-check job
# recomposes on every pull request and fails on any drift against the
# committed composed/ copy, so the pin, party.yaml's inherits entry and the
# composed/ re-render must move in the SAME commit. This script is that
# completion: it re-renders composed/ in the working tree, and Renovate's
# fileFilters (composed/**) fold the render into the bump commit.
#
# Parent checkouts use the same exact pins as CI. Compiler software has its
# own pin; updating it never changes the implementation policy window.
#
# A refusal from composition.py exits non-zero here, which surfaces on the
# Renovate PR as a failed post-upgrade task instead of a silently stale
# composed/ -- "a refusal is the most valuable output the gate produces".
set -euo pipefail

python3 -c 'import yaml' 2>/dev/null || pip install --quiet pyyaml

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

# Read the same five tag/SHA pairs as CI; no moving publisher branches.
eval "$(python3 .github/scripts/read-pins.py \
  .github/platform-tools-pin.yaml tools \
  gitops/platform/platform-pin.yaml platform \
  gitops/flux-system/gotk-sync-nist.yaml nist \
  gitops/flux-system/gotk-sync-ico.yaml ico \
  gitops/flux-system/gotk-sync-feeds.yaml feeds)"
clone() { git clone --quiet --branch "$2" "https://github.com/policy-as-versioned-$1/$1" "$work/${3:-$1}"; }
clone platform "$tools_tag" platform-tools
clone platform "$platform_tag"
clone nist "$nist_tag"
clone ico "$ico_tag"
clone feeds "$feeds_tag"
python3 .github/scripts/verify-pinned-checkouts.py \
  gitops/platform/platform-pin.yaml "$work/platform" \
  gitops/flux-system/gotk-sync-nist.yaml "$work/nist" \
  gitops/flux-system/gotk-sync-ico.yaml "$work/ico" \
  gitops/flux-system/gotk-sync-feeds.yaml "$work/feeds"
# gitsign must be installed on the Renovate runner; the tool runner refuses
# missing verifiers and rejects an incorrect release identity before execution.

# Compose TWICE, deliberately. Composition reads the previous composed
# HEADER from disk to fill each price entry's old_version, so a single run
# here would commit a transition record (old_version v1, new_version v2)
# that the NEXT recompose -- compose-check on this PR, and on every PR
# after the merge -- can never reproduce, failing the drift check forever.
# The committed artefact must be the settled fixpoint (old == new); the
# pull request diff itself is the record of the transition.
python3 .github/scripts/platform-tools.py --tools-dir "$work/platform-tools" compose "$PWD" \
  --estate-clone "$work" --out "$PWD" > /dev/null
python3 .github/scripts/platform-tools.py --tools-dir "$work/platform-tools" compose "$PWD" \
  --estate-clone "$work" --out "$PWD"

