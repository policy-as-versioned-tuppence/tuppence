#!/usr/bin/env bash
# cs-14: proves EXPECTED_IDENTITY_REGEXP in release.yml matches main and the
# release/<major>.<minor>.x maintenance-branch shape, and rejects everything
# else -- a foreign org, a foreign repo, and identity strings crafted to
# exploit an unanchored or unescaped regexp (prefix/suffix smuggling, `.`
# matching any char).
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

if [ "$fail" -ne 0 ]; then
  echo "FAIL: EXPECTED_IDENTITY_REGEXP did not behave as expected" >&2
  exit 1
fi
echo "OK: EXPECTED_IDENTITY_REGEXP anchors org, repo and workflow path; allows only main or release/<major>.<minor>.x"
