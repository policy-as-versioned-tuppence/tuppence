# Prepared cloud delivery

The RDS and S3 configuration claims are a tuppence workload beside ledger. They carry
`policy-as-versioned.dev/policy-version: 5.0.0`, a version tuppence's own composed set serves.
They are prepared from locally available fleet/policy seeds. The incumbent datastore clone
was unavailable offline, so exact resource-name/data fidelity to its original claims is still
unmeasured. No ProviderConfig, credentials, provider controller or Bucket is provisioned.

This root's kustomization selects only the delivery controls, not the claim file. All three
routes consume `tuppence-composed`: real vendor CRDs become Established first, policies next,
claims last. The claims route grades delivery without waiting for impossible AWS reconciliation.
The current self-pin v3.0.0 contains none of these paths. This remains opt-in and unactivated.

After the qualifying signed e2e4 clock record and a platform `cloud/v1.0.0` publication exist,
run `prepare.py` with that tag's exact full SHA, real vendor CRDs and an output directory.
The helper verifies the platform tag offline under cloud-release.yml's identity and writes
only cloud/crds/workload paths plus CLOUD-PARENT provenance. Incorporate those paths in the
next tuppence composed artefact, cut its signed tag, and move the existing composed source's
tag and commit together. Add `flux-system/crossplane-crds`, `flux-system/cloud-policies` and
`flux-system/cloud-claims` to that source's existing `gitsign-gates` annotation in the same
reviewed change. The hub admission check must pass before either incumbent row can archive.

The proof sends spec-only server dry-runs to KinD and checks their mutated service fields.
Dry-runs never reach a provider reconciler. Isolated carries the strongest available service
dials here; this is not an observation of AWS reach isolation, data durability or encryption
on a real cloud resource.
