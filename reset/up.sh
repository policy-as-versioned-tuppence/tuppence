#!/usr/bin/env bash
# Idempotent bring-up of the workload flagship (ticket 17) onto the EXISTING
# cluster that already runs the identity substrate (SPIRE + Istio + OpenBao) and
# the posture projection (ticket 15). Never creates/deletes/waits on a cluster —
# a slow reconcile just means "re-run up.sh".
#
# Prereqs (run these first, they install what this depends on):
#   estate/platform/identity/up.sh   — SPIRE + Istio + OpenBao + jwt seam
#   estate/platform/posture/up.sh    — stamp-posture + trust-boundary + posture ClusterSPIFFEID
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CTX="${CTX:-kind-driftwood}"
say() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }

command -v kubectl >/dev/null || { echo "MISSING cli: kubectl" >&2; exit 1; }
kubectl --context "$CTX" version >/dev/null 2>&1 || { echo "cluster not reachable ($CTX); run the identity substrate up first" >&2; exit 1; }

say "customer-accounts-reset + current/stale callers (meshed, posture-managed)"
kubectl --context "$CTX" apply -f "$HERE/workloads.yaml"

say "reach gate: Istio AuthorizationPolicy on the current-posture prefix"
kubectl --context "$CTX" apply -f "$HERE/authorizationpolicy.yaml" \
  || echo "  (Istio CRDs not ready — re-run up.sh once istiod is up)"

say "peer SAN override: expect the real posture-shaped SVID, not Istio's ns/sa default"
kubectl --context "$CTX" apply -f "$HERE/destinationrule.yaml" \
  || echo "  (Istio CRDs not ready — re-run up.sh once istiod is up)"

say "secret gate: OpenBao jwt role bound to the current-posture prefix"
# Delete first, then apply. A Job's pod template is immutable, so `apply` on an
# already-created Job is a silent no-op -- it does NOT re-run it. That matters
# because this OpenBao runs `bao server -dev`, i.e. in-memory: every restart of
# the openbao pod wipes the role, the policy and the secret this Job writes, and
# nothing put them back. Observed live on driftwood: this Job last ran (and
# failed) 27 days ago, openbao has restarted 6 times since, and neither the jwt
# auth method, the `posture` role nor secret/customer-accounts-reset existed.
# ponytail: the real upgrade is a persistent OpenBao (or a reconciled config
# controller) instead of dev mode -- then this delete can go.
kubectl --context "$CTX" -n openbao delete job openbao-reset-role --ignore-not-found >/dev/null 2>&1 || true
kubectl --context "$CTX" apply -f "$HERE/openbao-role.yaml" \
  || echo "  (openbao namespace not ready — re-run up.sh)"

say "done. verify with estate/tuppence/reset/verify-reach-secrets.sh"
