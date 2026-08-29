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
# `cosign verify-blob` itself runs here for real, in BOTH directions, and no
# longer only refuses. Scenarios D2 and E2 prove real refusals with the real
# binary (a present-but-malformed bundle; and a real bundle whose real Fulcio
# certificate identity does not match the institution's own constant).
# Scenario E proves a real ACCEPT: platform's own cut-release.yml has since
# committed real evidence bundles (computed-semver/evidence/*.json.bundle,
# Fulcio certs from that real Actions run, logged to Rekor), and VERIFYING
# them needs no ambient credential and no network at all -- only signing ever
# did -- so the whole gate runs unskipped, with the real identity constants,
# against the real committed pin, in about a second.
#
# What remains out of reach here is only signing NEW evidence, so Scenarios A
# and B -- which invent a fresh release line in a throwaway clone -- verify
# the REST of the pipeline: checkout-at-tag, the commit pin, reading real
# committed evidence content, the composition arithmetic (retirement forces
# major, strictest wins, weaker-than-declared prints and never downgrades),
# with adopter-gate.py's `--skip-cosign-verify`
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
command -v cosign >/dev/null 2>&1 || {
  # Genuine could-not-look: without the real binary the refusals AND the
  # accept below cannot be observed at all, and asserting them from reading
  # the code is exactly what this script exists not to do.
  echo "SKIP: cosign is not installed -- Scenarios D2/E/E2 run the real binary against real bundles" >&2
  exit 3
}

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

say "Scenario E: the REAL, unmodified, currently-committed platform-pin.yaml -- a genuine two-document YAML stream (GitRepository + Kustomization) -- verified end to end with REAL cosign against platform's REAL committed evidence bundles"
# Two things at once, both against real objects, with no fixture rewriting
# at all:
#
#  * parse_pin(). Every other scenario's pin fixture is single-document
#    (`spec: {ref: {...}}`) -- convenient, but never the shape
#    gitops/platform/platform-pin.yaml (and shift-left.yml's real
#    --new-pin-yaml / --old-pin-yaml args) actually has: a GitRepository
#    document, a `---` separator, then a Kustomization document with no
#    `ref` at all. yaml.safe_load() (single-document) raises ComposerError
#    on that shape. This scenario feeds the real file in, byte for byte,
#    and reads the tag it names out of the file rather than assuming one --
#    an earlier version of this scenario string-replaced a then-current
#    tag literal, which silently became a no-op the moment the pin was
#    bumped, and quietly stopped testing what it claimed to test.
#  * a REAL cosign ACCEPT. The older disclosure above -- that this sandbox
#    cannot produce a bundle cosign would genuinely accept -- no longer
#    holds: platform's own cut-release.yml has since committed real
#    evidence bundles (computed-semver/evidence/*.json.bundle, Fulcio certs
#    from that real Actions run, logged to Rekor), and `cosign verify-blob`
#    verifies them here offline, in under a second, with no ambient
#    credential of any kind -- verification never needed one, only signing
#    did. So this scenario runs with cosign NOT skipped, against the REAL
#    identity constants read straight out of shift-left.yml (never
#    hand-copied here), and demands a real PASS with every composed
#    element's evidence really verified.
e_platform="$scratch/platform-e"
git clone --local --quiet "$platform_repo" "$e_platform"
e_pin="${here}/gitops/platform/platform-pin.yaml"
e_dist="${here}/gitops/platform/platform-distribution.yaml"
# Until 2026-08-29 this file WAS the two-document stream (GitRepository +
# Kustomization) and E asserted that shape directly. Ticket 42 split the
# Kustomization out into platform-distribution.yaml, because applying the pin
# alone must not also install the cluster-scoped policy fan-out (two
# ResourceSets rendering one orphan guard fight over it -- observed live). The
# regression E exists for -- parse_pin() must walk PAST a non-GitRepository
# document instead of raising ComposerError -- is still proved for real below,
# on the two REAL committed files concatenated into the same stream
# `kubectl apply -k gitops/platform/` feeds the API server. Nothing here is a
# fixture: both halves are the repo's own content.
grep -q '^kind: GitRepository$' "$e_pin" || fail "E: expected the real pin file's own GitRepository document"
grep -q '^kind: Kustomization$' "$e_dist" || fail "E: expected the real platform-distribution.yaml Kustomization document"
e_multi="$scratch/platform-pin-multidoc.yaml"
{ cat "$e_pin"; echo '---'; cat "$e_dist"; } > "$e_multi"
grep -q '^---$' "$e_multi" || fail "E: the reassembled real stream carries no '---' separator"
e_tag=$(awk '/^    tag: / {print $2; exit}' "$e_pin")
e_regexp=$(awk -F': ' '/^  EVIDENCE_EXPECTED_IDENTITY_REGEXP:/ {print $2; exit}' "${here}/.github/workflows/shift-left.yml")
e_issuer=$(awk -F': ' '/^  EXPECTED_ISSUER:/ {print $2; exit}' "${here}/.github/workflows/shift-left.yml")
[ -n "$e_tag" ] || fail "E: could not read the pinned tag out of ${e_pin}"
[ -n "$e_regexp" ] || fail "E: could not read EVIDENCE_EXPECTED_IDENTITY_REGEXP out of shift-left.yml"
[ -n "$e_issuer" ] || fail "E: could not read EXPECTED_ISSUER out of shift-left.yml"
set +e
gate --platform-dir "$e_platform" --new-pin-yaml "$e_pin" \
     --identity-regexp "$e_regexp" --issuer "$e_issuer" \
     --out "$scratch/e-summary.json" > "$scratch/e.out" 2>&1
e_code=$?
set -e
cat "$scratch/e.out"
grep -q "^Traceback" "$scratch/e.out" && fail "E: parse_pin() crashed on the real multi-document pin shape (ComposerError) -- see output above"
grep -q "^ok  platform checked out at ${e_tag}, resolved commit matches the pinned commit field" "$scratch/e.out" \
  || fail "E: expected parse_pin() to read tag/commit past the real file's Kustomization document and reach a real checkout+commit-match, got: $(cat "$scratch/e.out")"
[ "$e_code" -eq 0 ] || fail "E: expected a real PASS against the real pin and platform's real signed evidence, got exit $e_code"
python3 -c "
import json
d = json.load(open('$scratch/e-summary.json'))
assert d['elements'], 'the real versions array composed to nothing -- no evidence was verified at all'
unverified = [e['version'] for e in d['elements'] if e['verified'] is not True]
assert not unverified, f'cosign did not verify: {unverified}'
print('ok  E: real cosign verify-blob ACCEPTED platform\\'s real committed evidence for ' + ', '.join(e['version'] for e in d['elements']))
"
echo "ok  E: the gate PASSES against the real, currently-committed platform-pin.yaml -- real checkout at ${e_tag}, commit verification, real identity constants, real cosign signature verification"

# E-multi: the same gate, over the REAL two-document stream the two committed
# files form together. This is the parse_pin() ComposerError regression, kept
# alive after the ticket-42 split: a second, non-GitRepository document in the
# stream must be walked past, not choked on.
set +e
gate --platform-dir "$e_platform" --new-pin-yaml "$e_multi" \
     --identity-regexp "$e_regexp" --issuer "$e_issuer" \
     --out "$scratch/e-multi-summary.json" > "$scratch/e-multi.out" 2>&1
e_multi_code=$?
set -e
grep -q "^Traceback" "$scratch/e-multi.out" && fail "E-multi: parse_pin() crashed on the real multi-document pin shape (ComposerError) -- $(cat "$scratch/e-multi.out")"
[ "$e_multi_code" -eq 0 ] || fail "E-multi: expected a real PASS over the reassembled two-document stream, got exit $e_multi_code: $(cat "$scratch/e-multi.out")"
cmp -s "$scratch/e-summary.json" "$scratch/e-multi-summary.json" \
  || fail "E-multi: the gate reached a different verdict on the two-document stream than on the pin file alone"
echo "ok  E-multi: parse_pin() reads tag/commit past a second (Kustomization) document with no ComposerError, and the gate reaches the identical verdict"

say "Scenario E2: the SAME real bundles, refused by REAL cosign when the identity constant names a foreign publisher -- the identity pin is load-bearing against a real Fulcio certificate, not only against a string"
# verify-identity-regexp.sh proves the CONSTANT's anchoring and escaping
# with no cosign process. This proves the other half: that the constant is
# actually handed to, and enforced by, the real binary against the real
# certificate in the real committed bundle.
set +e
gate --platform-dir "$e_platform" --new-pin-yaml "$e_pin" \
     --identity-regexp '^https://github\.com/evil-org/platform/\.github/workflows/cut-release\.yml@refs/heads/main$' \
     --issuer "$e_issuer" > "$scratch/e2.out" 2>&1
e2_code=$?
set -e
cat "$scratch/e2.out"
[ "$e2_code" -ne 0 ] || fail "E2: a foreign-org identity regexp must refuse platform's real evidence, got a PASS"
grep -q "cosign verify-blob failed for policy version" "$scratch/e2.out" \
  || fail "E2: expected a real cosign identity refusal, got: $(cat "$scratch/e2.out")"
grep -q "none of the expected identities matched" "$scratch/e2.out" \
  || fail "E2: expected cosign's own identity-mismatch reason, got: $(cat "$scratch/e2.out")"
echo "ok  E2: the same real bundle that just verified is refused by the real binary when the identity constant names a different publisher"

say "Scenario F: old_tag == new_tag -- the ordinary PR that never touches gitops/platform/platform-pin.yaml at all"
# shift-left.yml carries no \`paths:\` filter specifically so this required
# check reports on every PR (its own header comment). The large majority of
# PRs never touch the platform pin, so the PR-base and PR-head copies of
# platform-pin.yaml are byte-identical -- old_tag and new_tag parse to the
# SAME value. That MUST classify as a real no-op ("none"), never the
# "does not move forward" refusal a same-tag comparison used to raise.
set +e
gate --platform-dir "$d_platform" --new-pin-yaml "$scratch/new-pin-d.yaml" --old-pin-yaml "$scratch/new-pin-d.yaml" \
     --identity-regexp '.*' --issuer '.*' > "$scratch/f.out" 2>&1
f_code=$?
set -e
cat "$scratch/f.out"
grep -q "does not move forward" "$scratch/f.out" \
  && fail "F: an ordinary PR that doesn't touch the pin (old_tag == new_tag) must never refuse as 'does not move forward'"
python3 -c "
import importlib.util
spec = importlib.util.spec_from_file_location('ag', '${here}/.github/scripts/adopter-gate.py')
ag = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ag)
got = ag.classify_tag_bump('v1.0.0', 'v1.0.0')
assert got == 'none', f'expected classify_tag_bump on an unchanged tag to return none, got {got!r}'
"
# This platform tag (v1.0.0) genuinely predates cs-27 (same honest history
# Scenario D already establishes) so composition still refuses -- for the
# REAL reason (no evidence committed yet), never for the same-tag bug.
[ "$f_code" -ne 0 ] || fail "F: expected this real v1.0.0 tag to still refuse on missing evidence, same as Scenario D"
grep -q "no signed evidence committed for policy version 2.0.0" "$scratch/f.out" \
  || fail "F: expected the same real missing-evidence refusal Scenario D shows, got: $(cat "$scratch/f.out")"
echo "ok  F: an unchanged pin (old_tag == new_tag) classifies as a real no-op ('none'), never refuses as 'does not move forward'; the real refusal that does fire is the genuine missing-evidence one, unrelated to the same-tag bug"

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
# The `#` alternative in the element run is load-bearing, not decoration.
# Ticket 26 added platform's 4.0.0 element behind an eight-line comment
# block; an elements-only run stopped at that comment and left 4.0.0 in the
# array after every set_array call, so Scenarios A and B were composing
# against a version whose evidence this throwaway line never produced. The
# claim is unchanged and now actually held: the assertion below re-reads the
# file and demands the array really is what was asked for.
text = re.sub(
    r"    - versions:(?: \[\]| *\n(?:        (?:- \{|#)[^\n]*\n)*)", new_block, text, count=1)
path.write_text(text)
import yaml
got = [e["version"] for e in (yaml.safe_load(text)["spec"]["inputs"][0]["versions"] or [])]
want = [e["version"] for e in entries]
assert got == want, f"set_array wrote {got}, asked for {want}"
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
echo "binary, real subprocess, real exit code -- when signed evidence is entirely missing (the real,"
echo "currently-tagged v1.0.0, which honestly predates cs-27), when a present bundle is malformed,"
echo "and when a real bundle's real certificate identity is not the publisher this institution pins."
echo "Against the REAL committed platform-pin.yaml, and against the two-document stream it forms with"
echo "cosign really ACCEPTS platform's real committed evidence: the gate passes unskipped. On real"
echo "committed evidence it composes across real multi-version content with no"
echo "retirement to a real PASS (printing, never downgrading, when composed is weaker than the"
echo "publisher's own tag), and forces a real non-zero-exit FAIL, naming the version, when a composed"
echo "bump goes major on a real retirement."
