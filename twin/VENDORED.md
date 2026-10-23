# What is vendored here, and at which ref

Authored by eco-system ticket 64, the same shape ticket 29 built for driftwood. Ticket 29's own
Answer claimed all three adopters and only driftwood had one; that Answer is corrected with a
dated note in the hub.

## `world/` -- the twin's shared world layer

An overlay may reference the world layer and the world layer may never reference an overlay, and
`twin/model.py Overlay.load` resolves `world_ref` on the **same** `ModelRepo`. So an overlay that
lives in an adopter's own repository must carry the world layer in the same git tree, or the
loader would have to learn a second repository (ticket 11 answer item 1). It is vendored, not
imported.

| | |
|---|---|
| Source repository | `policy-as-versioned-flux` (the hub) |
| Source release | `twin` **0.1.0** (`twin/VERSION`), pinned machine-readably in `PIN.yaml` |
| Signed source tag | `twin/v0.1.0`, published 2026-10-23; exact source and verification below |
| Source path | `twin/fixtures.py`, the `LIBRARY_WORLD_FILES` mapping |
| Files | 30: `world/meta.yaml`, 15 components, 13 propositions, 1 world model |
| Copied | byte-for-byte, verbatim, no edits |
| Stages to | `world_ref: c2d07330a778ed547b60cfbb87217bcf9813181f` in `orgs/tuppence/meta.yaml` |

The same sha driftwood's overlay pins, and that is a checkable fact rather than a coincidence: the
staging mirror commits `world/` alone in its first commit, so identical bytes stage to an identical
content-addressed commit in every adopter's repository.

Two pins, and they check each other. `PIN.yaml`'s `twin_version` must equal the hub's
`twin/VERSION` or `emit-forward-intel.py` refuses -- the release these bytes came from cannot
silently move underneath them. `world_ref` must equal the commit the vendored bytes stage to in
the emitter's deterministic mirror, or it refuses again.

**The tag.** `twin/v0.1.0` is prefixed because the hub repository also carries
other packages. The owner's hosted cut workflow signed annotated object
`b0d6140154d3619d6eff9ef499d837f8a8444300`, resolving to source commit
`0e353029f7f5b497a2fe19ef2874846119376d6e`.
The [published source release](https://github.com/policy-as-versioned-flux/policy-as-versioned-flux/releases/tag/twin/v0.1.0)
was published on 2026-10-23 at 15:56:21 UTC (release 422033887;
cut run 39982451070, publication run 39982502887). Production verification
accepted the canonical main `cut-release.yml` identity and GitHub OIDC issuer
and rejected a different identity. `PIN.yaml` therefore carries `tag_cut: true`.
Its full `hub_commit` remains an independent integrity anchor; `world_ref` pins
the unchanged vendored world bytes. Later code updates require a reviewed pin
and the same release checks. See `twin/RELEASE.md` in the hub.

Re-vendoring is a two-line job:

```sh
.venv/bin/python -c 'import pathlib; from twin.fixtures import LIBRARY_WORLD_FILES as W; [ (pathlib.Path(".estate-clone/tuppence/twin")/r).write_text(b, encoding="utf-8", newline="\n") for r,b in W.items() ]'
.venv/bin/python .estate-clone/tuppence/twin/emit-forward-intel.py   # refuses until world_ref is re-pinned
```

### The priors in `world/world_models/reference-map.yaml` are AUTHORED, not measured

Every causal edge in this estate carries an `evidence_grade` and a written basis. The prior
beliefs in the reference map carry neither, because the `world_models` schema has no grade field:
they are floats typed into `twin/fixtures.py` by whoever added the scenario class. Vendoring puts
them inside this repository's own signed tree, where they read like measured facts. The forward-intel producer does not read those authored priors: its money comes from the
declared native filing, causal edge and response mechanisms. Read every number in that file as
an authored prior, not an observed frequency.

## The declared financial and evidence instruments

Tuppence's declared turnover and payment-fee share derive its native GBP cash flow.
The perspective reports in GBP too, so no FX conversion is needed.

Both the valuation and the loss mechanism retain evidence grade 3: published comparable
work, **not observed here**. The party explicitly declares `pricing_threshold: 3`, which
admits that grade without a regrade event. Grade-5 mitigation remains unpriced. The producer
borrows the subscribed threat-register frequency explicitly; the comparable enforcement
record is no claim that this institution experienced that event.

The first forward-intel v1 envelope is authored on 2026-10-04. Its ordinary publisher rule,
bump and discovery declaration are reviewed with the source. Local emission is not an
authentic signed release, delivered application, or scheduled live observation.

## `forward-intel/payload.schema.json`

This is the adopter's owned schema for its forward-intel envelope. Its base is the
immutable `platform/feeds/forward-intel.payload.schema.json` at authenticated tools
v5.0.0 (`703eff6aee959843c4160aa54fd03413f62858cc`). It preserves every canonical
property, requirement and type. Ticket 144 adds exactly two optional declarations:
`rests_on_grade` (integer grades 1–3) and `valuation` (the native amount/currency,
party fact, reporting amount/currency and nullable dated FX record). No inherited
constraint is removed and the closed property set remains closed.

The active schema is an owned extension, not a byte-for-byte vendored copy. It lives
inside this publishing repository because the envelope resolves `payload_schema`
here, and the feed can be validated offline from these self-contained bytes.
`verify-twin-overlay.sh` checks the complete canonical base semantically and the
exact two optional additions against the materialized authentic platform schema.
It reports could-not-look if that parent is absent; absence never proves agreement.

## `ladder.yaml` -- the rungs, and why they are not read from a selection policy

This repository also ships a versioned `selection-policy` package. Its forward-intel
producer reads its curve rungs from the separate `ladder.yaml` declaration; it does not select
a delivered tier. The ladder records the platform release that published the rungs
(`graded/cage.py`, `ORDER`, TABLE_VERSION 1.0.0, at platform v2.0.1) and is checked against that
release's own module when a platform checkout is present.


## First tagged code adoption

The signed `twin/v0.1.0` source package is published and its canonical cut-workflow
identity and issuer have been authenticated. The workflow requires `tag_cut: true`,
the literal initial tag and version, an annotated tag object, the exact full
`hub_commit` and checkout HEAD, and matching `twin/VERSION`. It verifies the tag
offline with the consumer-owned canonical main identity before executing hub code.
The emitter still checks the independent vendored `world_ref`.

This release publishes versioned source only. It establishes no actor attestation,
measured forecast, calibration, financial credit or production outcome. Historical
hub coverage remains unmeasured and its CI invariant remains red. No world,
overlay, financial or forward-intel bytes are replaced by this code pin.
