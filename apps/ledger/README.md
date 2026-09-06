# ledger — tuppence's own application

Lifted into tuppence by eco-system ticket 33 from `policy-as-versioned-flux/ledger` at commit
`036bb972dd733eb12c00791415b145648d453e18`. ticket 13's resolution put it here: tuppence is the
fintech institution, and a ledger is a bank's application, not a platform's.

**This is tuppence's artefact now.** It is versioned by tuppence's own tags, its served workload
manifest is `gitops/apps/ledger.yaml` (rendered by `gitops/apps/kustomization.yaml`, which is what
this repository's Flux Kustomization reconciles), it is graded by tuppence's own `shift-left`
job against tuppence's own composed policy set, and its dependency tree is bumped by tuppence's
own `renovate.json`. Nothing outside this repository reads it.

The tree below is the incumbent repository's tree, unchanged except for the three things a lift
removes: its `k8s/` manifest (superseded by the served manifest above, re-labelled and
re-namespaced), its own `renovate.json` stub (superseded by this repository's), and its release
workflow (see the residual below). It is left byte-identical otherwise so that a reader can `git
diff` it against `policy-as-versioned-flux/ledger` at that commit and see the whole of the move.
That is also why the Java package is still `com.mycompany.ledger` and the groupId still
`com.mycompany`: renaming them means rebuilding, and a rebuilt jar is not the image the served
manifest pins.

## The point of this app

The laggard, deliberately: a genuine, resolvable `log4j-core:2.14.1` (Log4Shell-era,
CVE-2021-44228 — see `pom.xml`). Real signal for a dependency bumper and for a vulnerability
scanner, not a fixture. Plain JDK `HttpServer`, no framework — the dependency is the point, not
the web stack.

## The residual: who builds the image

`gitops/apps/ledger.yaml` pins
`ghcr.io/policy-as-versioned-flux/ledger@sha256:9709e1075a503fe59ca85deae2b748fcbbfd80b464e56d2e1f82ec8182268111`
— the digest the incumbent repository's own manifest pinned, built and published by the incumbent
org. The source moved and the build did not. Moving the build needs a new workflow job in this
repository and a container registry under `policy-as-versioned-tuppence`; both are on ticket 33's
`## Waits on the owner`. The hub's `verify/lifted-apps/` check counts the lifted apps whose image
is still published by the incumbent org and prints that count on every run, so this paragraph
cannot quietly stop being true without the gate saying so.
