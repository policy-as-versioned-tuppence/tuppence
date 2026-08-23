#!/usr/bin/env bash
# verify-adopter-gate.sh -- ticket cs-28's offline twin.
#
# Runs the SAME code shift-left.yml runs (.github/scripts/adopter-gate.py)
# against real git objects: a real (throwaway, local-only) platform clone,
# real tags, real distribution/versions.yaml arrays, and real evidence
# produced by platform's own cut-release-gate.py (CUT_RELEASE_TEST_MODE=1,
# the same CI-only boundary platform's own verify-publisher-gate.sh already
# draws: real kyverno, real classification). Every scenario below is a case
# that SHOULD trigger a specific outcome, proved by actually running the
# check and reading its real exit code and real stderr -- never asserted
# from reading the code.
#
# What stays untestable here, and why (the same CI-only boundary cs-13's and
# cs-27's own offline twins already disclosed, confirmed one layer deeper):
# a real keyless cosign signature needs a live Fulcio-issued certificate
# from GitHub Actions' ambient OIDC -- confirmed directly, `cosign sign-blob
# --yes` here hangs on the interactive device-code flow until it times out.
# A LOCAL key pair does not route around this in the installed cosign
# version (3.1.3, the same version shift-left.yml itself pins): its
# mandatory new bundle format needs a signing config it fetches from
# Sigstore's TUF CDN even for `--key` signing, and that CDN host times out
# from this sandbox too (confirmed: a direct `dial tcp` timeout, while
# plain HTTPS to other hosts, including rekor.sigstore.dev itself, works
# fine -- a specific unreachable host, not a blanket network outage).
#
# `cosign verify-blob` itself DOES run here for real, and DOES correctly
# refuse -- Scenarios C and D below prove that with the real binary, against
# a real missing-evidence case and a real malformed/non-cosign bundle case
# (each completes in ~30s: cosign's own TUF-fetch timeout, then a real
# fallback verification that still correctly fails). What this sandbox
# cannot produce is a bundle cosign would genuinely ACCEPT, so Scenarios A
# and B verify the REST of the pipeline -- checkout-at-tag, the commit pin,
# reading real committed evidence content, the composition arithmetic
# (retirement forces major, strictest wins, weaker-than-declared prints and
# never downgrades) -- with adopter-gate.py's `--skip-cosign-verify`
# (TEST-ONLY, never set by shift-left.yml; mirrors platform's own
# CUT_RELEASE_TEST_MODE precedent exactly: it wraps only the cosign
# subprocess call, never the file-existence checks or the decision logic
# around it -- see verify_evidence()'s own docstring). The identity-regexp
# STRING itself (anchoring, escaping, and "a platform workflow rename
# breaks verification") is proved separately and deterministically in
# verify-identity-regexp.sh, with no cosign process involved at all.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
platform_repo="${PLATFORM_REPO:-${here}/../platform}"
[ -d "${platform_repo}/.git" ] || { echo "FAIL: no platform clone at ${platform_repo} (set PLATFORM_REPO=)" >&2; exit 1; }

scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }
say() { echo; echo "== $* =="; }

gate() {  # wraps adopter-gate.py's argv for readability below
  python3 "${here}/.github/scripts/adopter-gate.py" "$@"
}

say "Scenario D: against the REAL, currently-tagged v1.0.0 (predates cs-27) -- honest current-state refusal"
# The repair release (cs-15) shipped hand-classified, before the gate existed
# (spec.md: "the gate cannot ship before the repair"). Its real tags carry no
# computed-semver/evidence/ at all. An institution bumping onto v1.0.0 today
# for real, through this exact script, correctly and honestly refuses --
# this is the estate telling the truth about its own history, not a bug in
# the adopter gate. Real cosign verify-blob is NOT even reached here (the
# missing-evidence check runs first) -- Scenario C below reaches it for real.
d_platform="$scratch/platform-d"
git clone --local --quiet "$platform_repo" "$d_platform"
cat > "$scratch/new-pin-d.yaml" <<YAML
apiVersion: source.toolkit.fluxcd.io/v1
kind: GitRepository
spec:
  ref:
    tag: v1.0.0
    commit: $(git -C "$d_platform" rev-parse v1.0.0^{commit})
YAML
set +e
gate --platform-dir "$d_platform" --new-pin-yaml "$scratch/new-pin-d.yaml" \
     --identity-regexp '.*' --issuer '.*' > "$scratch/d.out" 2>&1
d_code=$?
set -e
cat "$scratch/d.out"
[ "$d_code" -ne 0 ] || fail "D: expected a refusal against the real, evidence-less v1.0.0"
grep -q "no signed evidence committed for policy version 2.0.0" "$scratch/d.out" \
  || fail "D: expected the missing-evidence reason naming 2.0.0, got: $(cat "$scratch/d.out")"
echo "ok  D: real refusal against the real repo's own current tags -- no evidence exists yet, correctly refused"

say "Scenario C: commit-pin mismatch -- ADR-0001's pin made load-bearing"
c_platform="$scratch/platform-c"
git clone --local --quiet "$platform_repo" "$c_platform"
git -C "$c_platform" checkout --quiet v1.0.0
real_commit=$(git -C "$c_platform" rev-parse HEAD)
cat > "$scratch/new-pin-c.yaml" <<YAML
apiVersion: source.toolkit.fluxcd.io/v1
kind: GitRepository
spec:
  ref:
    tag: v1.0.0
    commit: 0000000000000000000000000000000000000c
YAML
set +e
gate --platform-dir "$c_platform" --new-pin-yaml "$scratch/new-pin-c.yaml" \
     --identity-regexp '.*' --issuer '.*' > "$scratch/c.out" 2>&1
c_code=$?
set -e
cat "$scratch/c.out"
[ "$c_code" -ne 0 ] || fail "C: expected a refusal on commit mismatch"
grep -q "tag actually resolves to ${real_commit}" "$scratch/c.out" \
  || fail "C: expected the resolved-commit disagreement named, got: $(cat "$scratch/c.out")"
echo "ok  C: a pin naming the wrong commit for its own tag is refused, naming the real resolved commit"

say "Scenario D2: a REAL cosign verify-blob rejection of a present-but-malformed bundle (the real binary reaches the trust check itself, not just the file-existence check)"
d2_platform="$scratch/platform-d2"
git clone --local --quiet "$platform_repo" "$d2_platform"
git -C "$d2_platform" checkout --quiet v1.0.0
mkdir -p "$d2_platform/computed-semver/evidence"
echo '{"outcome":{"result":"passed"},"bump":{"computed":"none"}}' > "$d2_platform/computed-semver/evidence/2.0.0.json"
echo '{"not":"a real cosign bundle"}' > "$d2_platform/computed-semver/evidence/2.0.0.json.bundle"
cat > "$scratch/new-pin-d2.yaml" <<YAML
apiVersion: source.toolkit.fluxcd.io/v1
kind: GitRepository
spec:
  ref:
    tag: v1.0.0
    commit: $(git -C "$d2_platform" rev-parse HEAD)
YAML
set +e
gate --platform-dir "$d2_platform" --new-pin-yaml "$scratch/new-pin-d2.yaml" \
     --identity-regexp '.*' --issuer '.*' > "$scratch/d2.out" 2>&1
d2_code=$?
set -e
cat "$scratch/d2.out"
[ "$d2_code" -ne 0 ] || fail "D2: expected a real cosign refusal against a malformed bundle"
grep -q "cosign verify-blob failed for policy version 2.0.0" "$scratch/d2.out" \
  || fail "D2: expected the real cosign failure reason, got: $(cat "$scratch/d2.out")"
echo "ok  D2: real cosign verify-blob genuinely rejects a present-but-malformed bundle (not just a missing-file check)"

say "Scenario A/B setup: one real gated release, plus two real array-level releases (unchanged, then retired)"
clone="$scratch/clone"
git clone --local --quiet "$platform_repo" "$clone"
cd "$clone"
git config user.email test@example.invalid
git config user.name test
export CUT_RELEASE_TEST_MODE=1
export GITHUB_REPOSITORY_OWNER=scratch

render_from() {  # render_from <new-version> <copy-from-version>
  local nv="$1" cv="$2"
  python3 - "$nv" "$cv" <<'PY'
import sys, importlib.util
from pathlib import Path
nv, cv = sys.argv[1], sys.argv[2]
spec = importlib.util.spec_from_file_location("rvt", "distribution/render-version-tree.py")
rvt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rvt)
target = Path(f"distribution/policies/v{nv}")
rvt.write_tree(nv, target)
nv_slug, cv_slug = nv.replace(".", "-"), cv.replace(".", "-")
src = Path(f"distribution/policies/v{cv}/require-nonroot.yaml").read_text()
(target / "require-nonroot.yaml").write_text(
    src.replace(f"{cv_slug}", nv_slug).replace(f"'{cv}'", f"'{nv}'")
)
PY
}

set_array() {  # set_array '{"version":"1","tag":"policy/v1","commit":"..."}' ...  (zero args -> empty array)
  # Writes the array back in the exact flow-mapping-per-line shape
  # cut-release-update-array-commit.sh's own regex expects (and the real
  # committed file already uses) -- yaml.safe_dump's default block style
  # would silently make that regex match zero elements.
  python3 - "$@" <<'PY'
import json, re, sys
from pathlib import Path
entries = [json.loads(e) for e in sys.argv[1:]]
path = Path("distribution/versions.yaml")
text = path.read_text()
if entries:
    lines = "\n".join(
        f'        - {{ version: "{e["version"]}", tag: "{e["tag"]}", commit: "{e["commit"]}" }}'
        for e in entries
    )
    new_block = f"    - versions:\n{lines}\n"
else:
    new_block = "    - versions: []\n"
text = re.sub(r"    - versions:(?: \[\]| *\n(?:        - \{[^\n]*\}\n)*)", new_block, text, count=1)
path.write_text(text)
PY
}

cut() {  # cut <tags.json>
  python3 .github/scripts/cut-release-gate.py "$1"
  ./.github/scripts/cut-release-commit-evidence.sh "$1"
  ./.github/scripts/cut-release-update-array-commit.sh "$1"
  ./.github/scripts/cut-release-create-tags.sh "$1"
}

# Release 1: the ONE real gated release in this throwaway line -- the only
# one that needs to go through cut-release-gate.py at all. versions.yaml =
# [9.0.0], no predecessor, so gate.run_gate() runs end to end (legality,
# coverage, the lot -- real kyverno) and signs (test-mode stand-in) real
# evidence with a genuine `bump.computed = "no predecessor"`.
#
# ponytail: every OTHER pair of write_tree()-rendered versions this repo's
# generator produces shows real posture-trust-boundary movement classed
# major (the same movement the real, live v2.0.0->v3.0.0 release shows --
# not a fixture quirk, the generator's own witnesses are built to catch
# exactly this). A second gated release in this scratch chain would need
# its OWN major-classed number to pass the publisher gate for real, adding
# nothing this adopter-gate test needs to prove. Releases 2 and 3 below
# stay at the array level on purpose -- real git commits and real tags,
# just not run back through the (already cs-27-tested) publisher gate.
render_from "9.0.0" "3.0.0"
git add "distribution/policies/v9.0.0"
git commit -q -m "scratch: render v9.0.0 (copy of v3.0.0, self-scope renamed)"
tree_9_0_0=$(git rev-parse HEAD)
set_array '{"version":"9.0.0","tag":"policy/v9.0.0","commit":"'"$tree_9_0_0"'"}'
git add distribution/versions.yaml
git commit -q -m "scratch: array = [9.0.0]"
echo '[{"tag":"v2.0.0","message":"release 1 bare"},{"tag":"policy/v9.0.0","message":"release 1 policy"}]' > "$scratch/tags1.json"
cut "$scratch/tags1.json"
[ -f computed-semver/evidence/9.0.0.json ] || fail "release 1: no evidence for 9.0.0"
r1_commit=$(git rev-parse v2.0.0^{commit})

# Release 2: a bare platform tag on the SAME commit, array UNCHANGED --
# models a real, common shape (a platform release that touches nothing in
# distribution/versions.yaml at all: tooling, docs, an unrelated fix).
git tag -a v2.1.0 -m "release 2: bare tag only, array unchanged"
r2_commit=$(git rev-parse v2.1.0^{commit})
[ "$r2_commit" = "$r1_commit" ] || fail "release 2: expected v2.1.0 on the same commit as v2.0.0"

# Release 3: the array-only release -- 9.0.0 retires, nothing replaces it.
# No new policy tag in this dispatch, so cut() below is a real no-op on the
# gate/evidence/array-correction steps (same B2 path platform's own
# verify-publisher-gate.sh already proves for a bare tag) -- the retirement
# itself is a real, direct git commit to distribution/versions.yaml.
set_array
git add distribution/versions.yaml
git commit -q -m "scratch: array = [] -- 9.0.0 retired, nothing replaces it"
echo '[{"tag":"v3.0.0","message":"release 3: retirement only"}]' > "$scratch/tags3.json"
cut "$scratch/tags3.json"
r3_commit=$(git rev-parse v3.0.0^{commit})
echo "ok  one real gated release (9.0.0, real evidence), plus two real array-level releases (unchanged, then retired), real tags v2.0.0/v2.1.0/v3.0.0"

say "Scenario A: real PASS -- array unchanged (v2.0.0 -> v2.1.0), composed re-reads 9.0.0's real committed evidence, weaker-than-declared note fires"
cat > "$scratch/old-pin-a.yaml" <<YAML
spec: {ref: {tag: v2.0.0, commit: "$r1_commit"}}
YAML
cat > "$scratch/new-pin-a.yaml" <<YAML
spec: {ref: {tag: v2.1.0, commit: "$r2_commit"}}
YAML
set +e
gate --platform-dir "$clone" --new-pin-yaml "$scratch/new-pin-a.yaml" --old-pin-yaml "$scratch/old-pin-a.yaml" \
     --identity-regexp 'unused' --issuer 'unused' --skip-cosign-verify \
     --out "$scratch/a-summary.json" > "$scratch/a.out" 2>&1
a_code=$?
set -e
cat "$scratch/a.out"
[ "$a_code" -eq 0 ] || fail "A: expected a real PASS (array unchanged, no retirement), got exit $a_code"
grep -q "^declared (platform tag v2.0.0 -> v2.1.0): minor" "$scratch/a.out" || fail "A: expected declared=minor from the tag jump (v2.0.0->v2.1.0)"
grep -q "NOTE: composed bump ('no predecessor') is weaker than the publisher's tag ('minor')" "$scratch/a.out" \
  || fail "A: expected the weaker-than-declared note, informational only, nothing lowered"
python3 -c "
import json
d = json.load(open('$scratch/a-summary.json'))
assert d['retired'] == [], d['retired']
assert d['composed'] == 'no predecessor', d['composed']
assert {e['version'] for e in d['elements']} == {'9.0.0'}, d['elements']
assert d['elements'][0]['evidence']['bump']['computed'] == 'no predecessor', d['elements']
print('ok  A: composed by RE-READING 9.0.0\\'s real committed evidence (never recomputed), no retirement, real PASS')
"

echo "  A-render: render-evidence-comment.py against this REAL summary (not the fixture its own selfcheck uses)"
python3 "${here}/.github/scripts/render-evidence-comment.py" "$scratch/a-summary.json" > "$scratch/a-comment.md"
grep -q '`minor`' "$scratch/a-comment.md" || fail "A-render: declared bump not rendered"
grep -q '`no predecessor`' "$scratch/a-comment.md" || fail "A-render: composed bump not rendered"
grep -q 'sha256:' "$scratch/a-comment.md" || fail "A-render: corpus checksum not rendered"
if grep -q '%' "$scratch/a-comment.md"; then fail "A-render: a coverage percentage leaked into the rendered comment"; fi
echo "ok  A-render: rendered a real evidence summary to markdown, no percentage anywhere"

say "Scenario B: real FAIL -- 9.0.0 retires with nothing replacing it, composed forced major"
cat > "$scratch/old-pin-b.yaml" <<YAML
spec: {ref: {tag: v2.1.0, commit: "$r2_commit"}}
YAML
cat > "$scratch/new-pin-b.yaml" <<YAML
spec: {ref: {tag: v3.0.0, commit: "$r3_commit"}}
YAML
set +e
gate --platform-dir "$clone" --new-pin-yaml "$scratch/new-pin-b.yaml" --old-pin-yaml "$scratch/old-pin-b.yaml" \
     --identity-regexp '.*' --issuer '.*' --skip-cosign-verify \
     --out "$scratch/b-summary.json" > "$scratch/b.out" 2>&1
b_code=$?
set -e
cat "$scratch/b.out"
[ "$b_code" -ne 0 ] || fail "B: expected a real FAIL on retirement with no replacement"
grep -q "^FAIL: composed bump is major" "$scratch/b.out" || fail "B: expected the major-composed failure line"
grep -q "RETIRED, reaching this institution as major: 9.0.0" "$scratch/b.out" \
  || fail "B: expected the retirement named, not silent"
python3 -c "
import json
d = json.load(open('$scratch/b-summary.json'))
assert d['composed'] == 'major', d['composed']
assert d['retired'] == ['9.0.0'], d['retired']
assert d['elements'] == [{'version': '9.0.0', 'verified': None, 'bump_computed': 'major', 'evidence': None, 'retired': True}], d['elements']
print('ok  B: real refusal -- a composed major fails the required check for real (non-zero exit), retirement named, nothing silent')
"

echo
echo "PASS: adopter-gate.py checks out the tag under review (never the default branch), refuses a"
echo "resolved-commit disagreement with the pinned commit field, and refuses -- with the real cosign"
echo "binary, real subprocess, real exit code -- both when signed evidence is entirely missing"
echo "(the real, currently-tagged v1.0.0, which honestly predates cs-27) and when a present bundle is"
echo "malformed. On real committed evidence it composes across real multi-version content with no"
echo "retirement to a real PASS (printing, never downgrading, when composed is weaker than the"
echo "publisher's own tag), and forces a real non-zero-exit FAIL, naming the version, when a composed"
echo "bump goes major on a real retirement."
