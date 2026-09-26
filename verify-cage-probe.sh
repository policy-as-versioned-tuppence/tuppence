#!/usr/bin/env bash
# The cage probe, proven against the SERVED DOCUMENTS (eco-system ticket 161 item 4, from ticket
# 152 Q9). Three outcomes only:
#   PASS (exit 0)  the documents this repository serves put the fall-closed pod on the ladder's
#                  bottom and select nothing on the reference workload, at the pinned tag and at
#                  HEAD, for every version the ResourceSet array installs; and the sampler's own
#                  selfcheck passed on the way
#   FAIL (exit 1)  the documents say otherwise, or the selfcheck failed
#   SKIP (exit 3)  could not look: no kyverno CLI, a CLI that is not the engine this adopter
#                  declares, a CLI that does not read Namespace labels, a pinned tag this checkout
#                  does not carry, no pyyaml
#
# WHAT THIS IS, AND IS NOT. This is a proof about DOCUMENTS: `composed/` at the tag that
# gitops/composed/composed-set.yaml pins, and at HEAD, run through the pinned kyverno CLI offline.
# The lane's facts 6 and 7 (drift/five-facts.py, drift/window.yaml) are the proof about a CLUSTER:
# a real pod admitted, a real connection refused. A could-not-look there on the same state is the
# behaviour claim waiting for a cluster; a PASS here is the documents agreeing with what the lane
# expects to see. The two do not conflict, and neither stands in for the other. In the hub's gate
# this row is self-proof with no declared skip, so an exit 3 there is a fall, not a wait.
#
# The steps, in the order ticket 161 lists them:
#   1. drift/five-facts.py selfcheck -- nothing else runs it (ticket 152 found that out);
#   2. the CLI's version against the engine this repository declares: gitops/engine/kyverno.yaml
#      (ticket 147) when it exists, else KYVERNO_VERSION in .github/workflows/drift-sample.yml.
#      The CLI is $KYVERNO_CLI, or `kyverno` on the PATH when that variable is unset, so the hub
#      can hand each adopter its own CLI (ticket 150 item 4);
#   3. the CLI reads Namespace labels through a Values file `namespaces:` list (a Namespace given
#      as --resource lands on `isolated`: ticket 152's harness, SANE-quirk);
#   4. the sampler's own probe objects (imported from drift/five-facts.py) against the served
#      bodies at the pinned tag and at HEAD, for every version the array installs;
#   5. FAIL when the fall-closed pod is not on the bottom (lowest `cage-` PriorityClass, a selecting
#      NetworkPolicy with no rules and both types), when any mutation or generated NetworkPolicy
#      touches or selects the reference pod, or when a PriorityClass a mutation names is not served.
#      Generation is judged by the objects written, never by the CLI's result table.
# The pinned tag must be present: shift-left.yml checks this repository out without tags and
# fetches it first; a checkout without it exits 3 here and names the tag.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE" || exit 2
say()  { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
skip() { echo "SKIP: $*"; exit 3; }
fail() { echo "FAIL: $*"; exit 1; }

PY="${PYTHON:-python3}"
command -v "$PY" >/dev/null 2>&1 || skip "no python3 here, so neither the sampler's selfcheck nor the offline proof can run"
"$PY" -c 'import yaml' 2>/dev/null || skip "python3 here has no pyyaml, so drift/five-facts.py cannot read the pre-registration or the pins"

# --- 1. the sampler's own selfcheck ----------------------------------------------------------
say "1. drift/five-facts.py selfcheck (the instrument's own branches, no cluster)"
set +e
out="$("$PY" drift/five-facts.py selfcheck 2>&1)"; rc=$?
set -e
printf '%s\n' "$out" | tail -3 | sed 's/^/   /'
[ "$rc" = 0 ] || fail "drift/five-facts.py selfcheck exited $rc: $(printf '%s\n' "$out" | tail -1)"
set +e

# --- 2. the CLI is the engine this repository declares ---------------------------------------
say "2. the kyverno CLI against the engine this repository declares"
CLI="${KYVERNO_CLI:-kyverno}"
command -v "$CLI" >/dev/null 2>&1 || skip "no kyverno CLI: KYVERNO_CLI is unset and \`kyverno\` is not on the PATH, so the served documents cannot be run"
declared="$("$PY" drift/cage_probe.py declared-engine 2>&1)"; rc=$?
[ "$rc" = 0 ] || skip "the declared engine could not be read: ${declared#COULD NOT LOOK: }"
declared_version="${declared%% *}"; declared_where="${declared#* }"
have="$("$PY" drift/cage_probe.py cli-version --cli "$CLI" 2>&1)"; rc=$?
[ "$rc" = 0 ] || skip "the kyverno CLI's version could not be read: ${have#COULD NOT LOOK: }"
if [ "$have" != "$declared_version" ]; then
  skip "the kyverno CLI at $(command -v "$CLI") is $have and this repository declares engine $declared_version in $declared_where; the two differ, so the served documents would be graded on an engine this adopter does not run"
fi
echo "   ok  kyverno CLI $have is the engine $declared_where declares ($declared_version)"

# --- 3. the CLI reads Namespace labels -------------------------------------------------------
TAG="$("$PY" -c 'import sys; sys.path.insert(0, "scripts"); import render_composed as rc; print(rc.pinned_tag())' 2>&1)" \
  || skip "gitops/composed/composed-set.yaml pins no tag this script can read: $TAG"
git rev-parse -q --verify "refs/tags/${TAG}^{commit}" >/dev/null 2>&1 \
  || skip "the pinned composed tag ${TAG} is not present in this checkout, so the served documents cannot be read here (git fetch origin tag ${TAG})"
say "3. the CLI reads Namespace labels through a Values file (served cage-tier at ${TAG})"
out="$("$PY" drift/cage_probe.py namespace-labels --cli "$CLI" --ref "$TAG" 2>&1)"; rc=$?
printf '%s\n' "$out" | sed 's/^/   /'
[ "$rc" = 0 ] || skip "${out#COULD NOT LOOK: }"

# --- 4 and 5. the sampler's own objects against the served documents, at the tag and at HEAD --
overall=0
for ref in "$TAG" HEAD; do
  say "4. the sampler's probe objects against composed/ at ${ref}"
  out="$("$PY" drift/cage_probe.py prove --cli "$CLI" --ref "$ref" 2>&1)"; rc=$?
  printf '%s\n' "$out" | sed 's/^/   /'
  case "$rc" in
    0) ;;
    3) skip "the served documents at ${ref} could not be looked at: $(printf '%s\n' "$out" | tail -1 | sed 's/^COULD NOT LOOK: //')" ;;
    *) overall=1 ;;
  esac
done
[ "$overall" = 0 ] || fail "the served documents put the fall-closed pod off the ladder's bottom, or select the reference workload, at the pinned tag ${TAG} or at HEAD (see the FAULT lines above); this is a proof about the documents, and the lane's could-not-look on the same state is the behaviour claim"

versions="$("$PY" -c 'import sys; sys.path.insert(0, "scripts"); import render_composed as rc; print(", ".join(rc.versions()))' 2>/dev/null)"
echo "PASS: the served documents at ${TAG} (the tag gitops/composed/composed-set.yaml pins) and at HEAD $(git rev-parse --short HEAD), run offline through kyverno ${have} (the engine ${declared_where} declares), put the fall-closed pod on the ladder's bottom for every version the ResourceSet array installs (${versions}): its priority is the lowest served \`cage-\` PriorityClass, the class the mutation names is served, and a generated NetworkPolicy with no rules and both policy types selects it; no served mutation touches the reference pod and no generated NetworkPolicy selects it; and drift/five-facts.py selfcheck passed. This is a proof about the documents, not about a cluster: the lane's facts 6 and 7 are that"
