# `selection-policy` -- tuppence's own tier rule, versioned

The curve never picks. The twin emits a scenario (`twin/forward-intel/`), `fair.py` annualises it
into a caged residual per tier, and **this package** turns those residuals into one tier
(ADR-0021). It lives in tuppence's own repository because whose money is at risk decides how much
of it to carry, and it is versioned because a rule in an unversioned place cannot be pinned,
reviewed or rolled back.

## Version 1

    pick the loosest tier whose caged residual is WITHIN this party's own appetite tolerance
    (`<=`, a band is a limit you may reach), then clamp up to the party's declared overlay floor

The tolerance is `party.yaml`'s signed `appetite.tolerance`; there is no fixture behind it, and a
party with no appetite is a missing instrument that refuses (ADR-0020). The floor is
`party.yaml`'s `overlay.floor`, tighten-only: the selection clamps **up** to it and never below
(ADR-0022). Nothing under tolerance fails closed to `isolated`.

The residuals it reads are the **estate's annualised** ones -- `fair.py` output, frequency from
the subscribed pricing feed times the magnitude the twin emitted, plus the rung's own cost. They
are not the `net_cost_of_risk` figures in `twin/forward-intel/v1/feed.json`: that curve is per
shock, because the twin has no frequency (`lef: null`). The curve's `account` names are the rungs
of this ladder, and `twin/emit-forward-intel.py` reads them from this file so the two lists cannot
drift apart.

`infra` is not on this ladder. Only a platform-role party declares infra, and it declares it on a
Namespace manifest, never through a price.

Two refusals, both missing instruments: a residual stated in a currency the tolerance is not
stated in (convert through the signed fx feed first), and a tier name that is not on the ladder.
Every other missing thing is priced.

## What the proposal PR must carry

`propose-tier.yml` opens a PR against `composed/`. That PR must name both:

* **the policy version** -- `1.0.0`, from `VERSION` and `PIN.yaml`; and
* **the curve hash** -- `selection_policy.curve_hash(payload["curve"])` over the curve exactly as
  `twin/forward-intel/v1/feed.json` published it.

Without the version, a reader cannot tell which rule produced the tier. Without the hash, a
re-proposal on an unchanged curve is indistinguishable from a new one -- and the rejection ledger
keys on it: a changed curve hash resets the ledger, so a tier a human closed stays closed only
while the curve behind it stands.

## How it is pinned

`PIN.yaml` carries `policy_version`, and the composed artefact reads it.

It is **not** in `party.yaml`: the party schema is closed and forbids unknown keys. It is **not**
a Renovate customManager either. The two managers in `../renovate.json` use the `git-refs`
datasource against another org's repository and maintain a `{tag, commit}` pair; this package
lives in this repository, so there is no external ref to track and a manager pointed at
tuppence's own remote would only ever propose the commit it already is. A dead manager reads as
a working one, so there is none. When the rule is extracted into its own published package, it
gets a third manager of exactly that shape and `PIN.yaml` gains the `{tag, commit}` pair.

## Check

    python3 selection_policy.py

Thirteen asserts, no framework: the loosest-within-tolerance rule, the tighten-only clamp in
both directions, the fail-closed default, a tighter tolerance moving the tier, the band
boundary itself, all three missing instruments, and the curve hash's stability under key order
and whitespace.

This package is a second implementation of a rule the estate also implements, in
`platform/graded/cage.py`. Two implementations drift, so the hub's `verify/pound-seam` runs both
over the same residuals at every band boundary and with every rung tried as a floor, and refuses
any disagreement -- and does the same for the curve hash. That check is what caught this
package's original `<` against cage.py's `<=`.
