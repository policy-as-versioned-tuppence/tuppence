#!/usr/bin/env bash
# cs-14: proves EXPECTED_IDENTITY_REGEXP in release.yml matches main and the
# release/<major>.<minor>.x maintenance-branch shape, and rejects everything
# else -- a foreign org, a foreign repo, and identity strings crafted to
# exploit an unanchored or unescaped regexp (prefix/suffix smuggling, `.`
# matching any char).
#
# cs-28 extends this with the SAME proof for shift-left.yml's
# EVIDENCE_EXPECTED_IDENTITY_REGEXP -- the institution's own constant for
# verifying PLATFORM's evidence signature (a different org/repo than the
# EXPECTED_IDENTITY_REGEXP above, which verifies tuppence's own release
# tags). "The institution holds its own expected-identity constant... a
# platform workflow rename breaks verification" (28's acceptance criteria)
# is exactly this: proved deterministically, no cosign process, no network.
#
# ponytail: uses bash's [[ =~ ]] (POSIX ERE), not RE2 (what gitsign actually
# evaluates). The pattern here uses no backreferences/lookaround, where ERE
# and RE2 agree on every case below -- close enough to prove anchoring and
# escaping without shelling out. Swap for a real `cosign`/`gitsign` binary if
# this pattern ever grows a construct where the two engines could diverge.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REGEXP=$(awk -F': ' '/^  EXPECTED_IDENTITY_REGEXP:/ {print $2; exit}' "${HERE}/.github/workflows/release.yml")

if [ -z "$REGEXP" ]; then
  echo "FAIL: could not extract EXPECTED_IDENTITY_REGEXP from release.yml" >&2
  exit 1
fi

fail=0

should_match() {
  local id="$1"
  if [[ "$id" =~ $REGEXP ]]; then
    echo "ok    matches:     $id"
  else
    echo "FAIL  should match but did not: $id" >&2
    fail=1
  fi
}

should_not_match() {
  local id="$1"
  if [[ "$id" =~ $REGEXP ]]; then
    echo "FAIL  matched but should not: $id" >&2
    fail=1
  else
    echo "ok    rejected:    $id"
  fi
}

# (a) real identities that must keep verifying
should_match "https://github.com/policy-as-versioned-tuppence/tuppence/.github/workflows/cut-release.yml@refs/heads/main"
should_match "https://github.com/policy-as-versioned-tuppence/tuppence/.github/workflows/cut-release.yml@refs/heads/release/1.0.x"

# (b) foreign org/repo must NOT match
should_not_match "https://github.com/evil-org/tuppence/.github/workflows/cut-release.yml@refs/heads/main"
should_not_match "https://github.com/policy-as-versioned-tuppence/evil-repo/.github/workflows/cut-release.yml@refs/heads/main"

# (c) anchoring: prefix/suffix smuggling must NOT match
should_not_match "https://evil.com/https://github.com/policy-as-versioned-tuppence/tuppence/.github/workflows/cut-release.yml@refs/heads/main"
should_not_match "https://github.com/policy-as-versioned-tuppence/tuppence/.github/workflows/cut-release.yml@refs/heads/main/../evil"

# (d) escaping: an unescaped `.` would match any char here
should_not_match "https://githubXcom/policy-as-versioned-tuppence/tuppence/.github/workflows/cut-release.yml@refs/heads/main"

# (e) branch shape: only main or release/<digits>.<digits>.x
should_not_match "https://github.com/policy-as-versioned-tuppence/tuppence/.github/workflows/cut-release.yml@refs/heads/maint/1.0.x"
should_not_match "https://github.com/policy-as-versioned-tuppence/tuppence/.github/workflows/cut-release.yml@refs/heads/release/1.0.x-rc1"

# (f) the PROPOSER's identity is not a publisher's identity (ticket 78).
#     propose-tier.yml signs cage-tier proposal COMMITS with this repo's own
#     Actions identity; a release TAG must never verify under it, or a workflow
#     that may only propose could publish.
should_not_match "https://github.com/policy-as-versioned-tuppence/tuppence/.github/workflows/propose-tier.yml@refs/heads/main"

if [ "$fail" -ne 0 ]; then
  echo "FAIL: EXPECTED_IDENTITY_REGEXP did not behave as expected" >&2
  exit 1
fi
echo "OK: EXPECTED_IDENTITY_REGEXP anchors org, repo and workflow path; allows only main or release/<major>.<minor>.x"

echo
echo "== EVIDENCE_EXPECTED_IDENTITY_REGEXP (shift-left.yml -- verifies PLATFORM's evidence, cs-28) =="
EVIDENCE_REGEXP=$(awk -F': ' '/^  EVIDENCE_EXPECTED_IDENTITY_REGEXP:/ {print $2; exit}' "${HERE}/.github/workflows/shift-left.yml")

if [ -z "$EVIDENCE_REGEXP" ]; then
  echo "FAIL: could not extract EVIDENCE_EXPECTED_IDENTITY_REGEXP from shift-left.yml" >&2
  exit 1
fi

should_match_evidence() {
  local id="$1"
  if [[ "$id" =~ $EVIDENCE_REGEXP ]]; then
    echo "ok    matches:     $id"
  else
    echo "FAIL  should match but did not: $id" >&2
    fail=1
  fi
}

should_not_match_evidence() {
  local id="$1"
  if [[ "$id" =~ $EVIDENCE_REGEXP ]]; then
    echo "FAIL  matched but should not: $id" >&2
    fail=1
  else
    echo "ok    rejected:    $id"
  fi
}

# (a) the real identity cosign signs evidence from (platform's cut-release.yml, the SAME run gitsign signs the tag from) -- must keep verifying
should_match_evidence "https://github.com/policy-as-versioned-platform/platform/.github/workflows/cut-release.yml@refs/heads/main"
should_match_evidence "https://github.com/policy-as-versioned-platform/platform/.github/workflows/cut-release.yml@refs/heads/release/1.0.x"

# (b) a platform workflow RENAME must break verification -- the acceptance criterion, proved directly
should_not_match_evidence "https://github.com/policy-as-versioned-platform/platform/.github/workflows/publish-release.yml@refs/heads/main"
should_not_match_evidence "https://github.com/policy-as-versioned-platform/platform/.github/workflows/cut_release.yml@refs/heads/main"

# (c) a foreign org/repo must NOT match -- including tuppence's OWN cut-release.yml identity, which
#     this constant must NOT accept (it is a different party's identity than release.yml's own EXPECTED_IDENTITY_REGEXP above)
should_not_match_evidence "https://github.com/evil-org/platform/.github/workflows/cut-release.yml@refs/heads/main"
should_not_match_evidence "https://github.com/policy-as-versioned-platform/evil-repo/.github/workflows/cut-release.yml@refs/heads/main"
should_not_match_evidence "https://github.com/policy-as-versioned-tuppence/tuppence/.github/workflows/cut-release.yml@refs/heads/main"

# (d) anchoring and escaping, same exploits as above
should_not_match_evidence "https://evil.com/https://github.com/policy-as-versioned-platform/platform/.github/workflows/cut-release.yml@refs/heads/main"
should_not_match_evidence "https://githubXcom/policy-as-versioned-platform/platform/.github/workflows/cut-release.yml@refs/heads/main"

# (e) branch shape
should_not_match_evidence "https://github.com/policy-as-versioned-platform/platform/.github/workflows/cut-release.yml@refs/heads/maint/1.0.x"

if [ "$fail" -ne 0 ]; then
  echo "FAIL: EVIDENCE_EXPECTED_IDENTITY_REGEXP did not behave as expected" >&2
  exit 1
fi
echo "OK: EVIDENCE_EXPECTED_IDENTITY_REGEXP anchors platform's org/repo/workflow path, distinct from"
echo "    tuppence's own identity above, and a workflow rename genuinely breaks the match"

echo
echo "== EXPECTED_PROPOSAL_IDENTITY_REGEXP (propose-tier.yml -- the cage-tier proposal commit, ticket 78) =="
# A THIRD constant, on the same footing as the second: the proposal commit and
# the release tag are different powers, so the identity that may propose a
# tighter cage is deliberately not widened into the one that may publish.
PROPOSAL_REGEXP=$(awk -F': ' '/^  EXPECTED_PROPOSAL_IDENTITY_REGEXP:/ {print $2; exit}' "${HERE}/.github/workflows/propose-tier.yml")

if [ -z "$PROPOSAL_REGEXP" ]; then
  echo "FAIL: could not extract EXPECTED_PROPOSAL_IDENTITY_REGEXP from propose-tier.yml -- the proposal commit's signature would be verified against nothing" >&2
  exit 1
fi

should_match_proposal() {
  local id="$1"
  if [[ "$id" =~ $PROPOSAL_REGEXP ]]; then
    echo "ok    matches:     $id"
  else
    echo "FAIL  should match but did not: $id" >&2
    fail=1
  fi
}

should_not_match_proposal() {
  local id="$1"
  if [[ "$id" =~ $PROPOSAL_REGEXP ]]; then
    echo "FAIL  matched but should not: $id" >&2
    fail=1
  else
    echo "ok    rejected:    $id"
  fi
}

# (a) what propose-tier.yml's own run presents. `refs/heads/main` is the ref the
#     WORKFLOW runs on (schedule, dispatch, merged pin bump), never the
#     `wargamer/retune-*` branch it writes.
should_match_proposal "https://github.com/policy-as-versioned-tuppence/tuppence/.github/workflows/propose-tier.yml@refs/heads/main"

# (b) the publisher's identity must NOT verify a proposal, and neither may a
#     maintenance branch, the branch the proposal is written to, a foreign
#     org/repo/path, or a smuggled prefix/suffix
should_not_match_proposal "https://github.com/policy-as-versioned-tuppence/tuppence/.github/workflows/cut-release.yml@refs/heads/main"
should_not_match_proposal "https://github.com/policy-as-versioned-tuppence/tuppence/.github/workflows/propose-tier.yml@refs/heads/release/1.0.x"
should_not_match_proposal "https://github.com/policy-as-versioned-tuppence/tuppence/.github/workflows/propose-tier.yml@refs/heads/wargamer/retune-tier-tuppence-cage-tier-feeds-feed"
should_not_match_proposal "https://github.com/policy-as-versioned-driftwood/driftwood/.github/workflows/propose-tier.yml@refs/heads/main"
should_not_match_proposal "https://github.com/policy-as-versioned-tuppence/evil-repo/.github/workflows/propose-tier.yml@refs/heads/main"
should_not_match_proposal "https://evil.com/https://github.com/policy-as-versioned-tuppence/tuppence/.github/workflows/propose-tier.yml@refs/heads/main"
should_not_match_proposal "https://github.com/policy-as-versioned-tuppence/tuppence/.github/workflows/propose-tier.yml@refs/heads/main.evil.com"
should_not_match_proposal "https://githubXcom/policy-as-versioned-tuppence/tuppence/.github/workflows/propose-tier.yml@refs/heads/main"

if [ "$fail" -ne 0 ]; then
  echo "FAIL: EXPECTED_PROPOSAL_IDENTITY_REGEXP did not behave as expected" >&2
  exit 1
fi
echo "OK: EXPECTED_PROPOSAL_IDENTITY_REGEXP matches only this repo's propose-tier.yml on main;"
echo "    the release and proposal identities do not overlap in either direction"
