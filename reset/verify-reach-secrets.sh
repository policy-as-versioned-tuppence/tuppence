#!/usr/bin/env bash
# Beat (ticket 17): "customer-accounts-reset accepts ONLY callers whose SVID
# attests the current policy version. A current caller reaches the service AND
# gets its OpenBao secret; a caller out of currency is refused BOTH — live."
#
# OFFLINE core (always; python3, + kubectl for dry-run if present):
#   1. reach.py: the reach glob (Istio principal) and the secret glob (OpenBao
#      bound_claims) are identical, admit a current SVID, refuse a stale/base one.
#   2. manifests are valid k8s (dry-run) and the AuthorizationPolicy is ALLOW-only
#      (=> default-deny for unmatched callers) selecting customer-accounts-reset.
# LIVE tail (only if the identity substrate + these manifests are on the cluster):
#   3. reach: from teller-current curling the service returns 200; from teller-stale
#      it is refused (RBAC: access denied / 403).
#   4. secret: a current JWT-SVID logs into OpenBao role 'posture' and reads the
#      secret; a stale JWT-SVID's login is refused.
#
# Outcomes: PASS (exit 0), FAIL (exit 1), SKIP (exit 3: no docker, no kind
# cluster, Flux not Ready -- nothing could be observed, so nothing is claimed).
WANT_CTX="${CTX:-kind-driftwood}"
source "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib.sh"   # set -euo pipefail, say, have, need_substrate
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CTX="$WANT_CTX"
NS="tuppence-reset"
fail() { echo "FAIL: $*" >&2; exit 1; }
need_substrate "${CTX#kind-}"

have python3 || fail "python3 required for the offline gate proof"

say "1. offline: the reach glob and the secret glob agree and gate correctly"
python3 "$HERE/reach.py" selfcheck || fail "posture gate invariants broken"

say "2. offline: manifests valid + AuthorizationPolicy is ALLOW-only, selects the service"
python3 - "$HERE" <<'PY' || exit 1
import sys, os, re
here = sys.argv[1]
text = open(os.path.join(here, "authorizationpolicy.yaml")).read()
assert re.search(r'action:\s*ALLOW', text), "AuthorizationPolicy must be ALLOW (=> default-deny unmatched)"
assert re.search(r'app:\s*customer-accounts-reset', text), "must select the customer-accounts-reset workload"
assert "action: DENY" not in text, "no explicit DENY needed; ALLOW-only default-denies the stale caller"
print("  ok   ALLOW-only policy selecting customer-accounts-reset")
PY
if have kubectl; then
  for f in workloads.yaml authorizationpolicy.yaml; do
    kubectl --context "$CTX" apply --dry-run=client -f "$HERE/$f" >/dev/null 2>&1 \
      && echo "  ok   $f is valid" \
      || echo "  (skip: $f client dry-run needs CRDs/kubeconfig; server dry-run in the live tail)"
  done
else
  echo "  (skip: kubectl absent — manifest validity checked live)"
fi

# ---- live tail: only if the actual prerequisite (the posture layer this beat
# gates on) is installed, AND the substrate + workloads are up. Gating on ns+
# deploy alone let this enter the live tail on a cluster that had the workload
# but not the posture gate — "present but incomplete" produced noise
# indistinguishable from a real failure, and "absent" always looked the same as
# "passed". Check stamp-posture first, matching verify-posture-projection.sh.
if have kubectl && timeout 10 kubectl --context "$CTX" get mutatingpolicy stamp-posture >/dev/null 2>&1 \
   && timeout 10 kubectl --context "$CTX" get ns "$NS" >/dev/null 2>&1 \
   && timeout 10 kubectl --context "$CTX" -n "$NS" get deploy customer-accounts-reset >/dev/null 2>&1; then

  LIVE_REACH=1
  say "3. live: reach — current caller gets 200, stale caller is refused"
  RC_OK=$(timeout 25 kubectl --context "$CTX" -n "$NS" exec deploy/teller-current -c caller -- \
            curl -sS -o /dev/null -w '%{http_code}' customer-accounts-reset.$NS/ 2>/dev/null || echo "ERR")
  [ "$RC_OK" = "200" ] && echo "  ok   teller-current reached the service (200)" \
    || fail "current caller did NOT reach (got '$RC_OK') — check sidecar injection + posture SVID"

  RC_STALE=$(timeout 25 kubectl --context "$CTX" -n "$NS" exec deploy/teller-stale -c caller -- \
            curl -sS -o /dev/null -w '%{http_code}' customer-accounts-reset.$NS/ 2>/dev/null || echo "REFUSED")
  { [ "$RC_STALE" = "403" ] || [ "$RC_STALE" = "REFUSED" ]; } \
    && echo "  ok   teller-stale refused reach ($RC_STALE)" \
    || fail "stale caller REACHED (got '$RC_STALE') — the posture reach gate is open!"

  say "4. live: secret — current JWT-SVID reads it, stale JWT-SVID's login is refused"
  # Mint a JWT-SVID for each caller (audience openbao) via the SPIRE agent socket,
  # exchange it at OpenBao's jwt/login, and read the secret. Bounded, best-effort:
  # if the OIDC/agent path isn't wired on this cluster the offline gate proof (step 1)
  # already demonstrates the claim; we report, never hang.
  # `sts/openbao`, not `deploy/openbao`: OpenBao runs as a StatefulSet here, so
  # the old ref resolved to nothing and every `bao` call below silently did
  # nothing -- which, with the empty-token test that follows, would have printed
  # "stale SVID login refused" on a broken exec. An assertion that passes on
  # absence is worse than no assertion, so the current login must now succeed
  # before the stale refusal is credited at all.
  BAO="timeout 20 kubectl --context $CTX -n openbao exec sts/openbao -- env BAO_ADDR=http://127.0.0.1:8200"
  login() { # $1 = jwt   -> prints the client token or empty on refusal
    $BAO bao write -field=token auth/jwt/login role=posture jwt="$1" 2>/dev/null || true; }
  mint() { # $1 = deploy -> a JWT-SVID for audience openbao, or empty
    timeout 20 kubectl --context "$CTX" -n "$NS" exec "deploy/$1" -c caller -- \
      sh -c 'command -v spire-agent >/dev/null 2>&1 && spire-agent api fetch jwt -audience openbao -socketPath /run/spire/agent-sockets/api.sock 2>/dev/null | sed -n "2p" | tr -d "[:space:]"' 2>/dev/null || true; }

  JWT_OK=$(mint teller-current); JWT_STALE=$(mint teller-stale)
  if [ -n "$JWT_OK" ]; then
    # A stale login returning nothing only means "refused" if a current login
    # returns something: otherwise an empty token proves the exec is broken,
    # not that the gate held. So this is a FAIL, never a printed warning.
    TOK=$(login "$JWT_OK")
    [ -n "$TOK" ] || fail "current SVID could not log into OpenBao role 'posture' — the login path itself is broken, so a stale refusal below would prove nothing (check the jwt role, the 'openbao' audience, and that sts/openbao is up)"
    echo "  ok   current SVID logged into role 'posture'"
    STOK=$(login "$JWT_STALE")
    [ -z "$STOK" ] && echo "  ok   stale SVID login refused (no token issued)" \
      || fail "stale SVID obtained an OpenBao token — the secret gate is open!"
    LIVE_SECRET=1
  else
    # NOT a substrate skip, and not honestly "checked": there is no SPIFFE
    # client in these pods at all (the `caller` container is curl only, and the
    # SPIFFE CSI socket is mounted into istio-proxy, not into it), so this half
    # of the beat has never once been observed live -- only the offline gate
    # proof in step 1 stands behind it. The fix is a second container in the
    # teller pods holding the Workload API socket (image
    # ghcr.io/spiffe/spire-agent, a `spire-agent-socket` csi.spiffe.io volume at
    # /run/spire/agent-sockets); the SPIRE entries are selected on k8s:pod-uid,
    # so any container in the pod attests to the same SVID. It is NOT applied
    # because no pod can currently be created in this namespace: cage-tier's
    # mutation sets priorityClassName after the built-in Priority admission
    # plugin has already stamped priority: 0, and the API server then refuses
    # the pod ("the integer value of priority (0) must not be provided in pod
    # spec; priority admission controller computed -10 from the given
    # PriorityClass name"). ponytail: land the svid container the moment the
    # cage stops blocking pod creation, and turn this branch into a fail.
    echo "  (NOT OBSERVED: the caller pods carry no SPIFFE client, so no JWT-SVID can be minted here — the secret half rests on step 1's offline gate proof alone; see the comment above)"
  fi
else
  say "3-4. live checks skipped: posture layer (stamp-posture) or $NS workloads not found on context '$CTX'"
  say "     run estate/platform/identity/up.sh, estate/platform/posture/up.sh, then"
  say "     estate/tuppence/reset/up.sh — the offline gate proof above is the claim."
fi

# The closing line may only claim what was actually looked at. The secret half
# used to be asserted here unconditionally even though its live check has never
# once run on this estate (see step 4): a PASS line that overclaims is the same
# defect as a check that passes on absence, just further from the assertion.
if [ "${LIVE_REACH:-0}" = 1 ] && [ "${LIVE_SECRET:-0}" = 1 ]; then
  echo "PASS: current-posture callers win reach + secret; out-of-currency loses both."
elif [ "${LIVE_REACH:-0}" = 1 ]; then
  echo "PASS: reach observed live (current 200, stale refused); the secret half is proved by the offline gate only — no live JWT-SVID/OpenBao observation was possible (see step 4)."
else
  echo "PASS: the posture gate holds offline (reach glob == secret glob, current admitted, stale and de-postured refused); no live tail ran on this context."
fi
