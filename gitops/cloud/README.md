# Prepared cloud delivery

The RDS and S3 configuration claims are a tuppence workload beside ledger. They carry
`policy-as-versioned.dev/policy-version: 5.0.0`, a version tuppence's own composed set serves.
All three original resources come from datastore commit
`988e414eb01c7f768bdd9fc75a0d7e068745a9b3`, recorded with its blob and SHA256 in
`INCUMBENT.json`; `sources/datastore-claims.yaml` preserves its original bytes. The lift changes
only namespace and the policy claim. Names, two RDS intents, the S3 selector and other labels
remain exact. No ProviderConfig, credentials, provider controller or Bucket is provisioned.

This root's kustomization selects only the delivery controls, not the claim file. All three
routes consume `tuppence-composed`: real vendor CRDs become Established first, policies next,
claims last. The claims route grades delivery without waiting for impossible AWS reconciliation.
The current composed self-pin v4.0.1 contains none of these paths. This remains opt-in and unactivated.

The qualifying signed e2e4 record now exists. The compiler pin selects the actually published
`v5.1.0`, and `platform-cloud-pin.yaml` selects the separately signed `cloud/v1.0.0`, both at
`d314b8df0b19c42ea816c0a6ada41913b7940fbe`. The cloud pin is source data, never applied to a
cluster. Renovate tracks its exact tag and commit together. Ordinary verified composition
reproduces every cloud path while preserving the Pod policy parent, 5/6/7 window and engine
1.18.2.

This is composition A: it prepares the generated files while leaving the active composed
self-pin and signature gates unchanged. After a genuine signed composition release contains
those paths, composition B moves the existing source's tag and commit and adds the three gates
below atomically. The offline observer and hosted lane select the cloud routes only when the
actually pinned signed tag carries `CLOUD-PARENT.json`. Prepared worktree files cannot activate
future routes or OSCAL control mappings.

`prepare.py` can independently render the same cloud-only paths into a temporary directory
for review. It accepts the actual cloud tag and full SHA; the exact upstream vendor CRDs are
included in the signed package. Optional supplied copies must match those pins, including
original file bytes. The helper also checks the incumbent lift before rendering. Cut the next
genuinely re-rendered signed composed tag, and move the existing composed source's
tag and commit together. Add `flux-system/crossplane-crds`, `flux-system/cloud-policies` and
`flux-system/cloud-claims` to that source's existing `gitsign-gates` annotation in the same
reviewed change. The hub admission check must pass before either incumbent row can archive.

The proof sends spec-only server dry-runs to KinD and checks their mutated service fields.
Dry-runs never reach a provider reconciler. Isolated carries the strongest available service
dials here; this is not an observation of AWS reach isolation, data durability or encryption
on a real cloud resource.
