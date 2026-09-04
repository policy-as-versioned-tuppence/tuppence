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
| Tag the owner must cut | `twin/v0.1.0` -- **not cut yet**, see below |
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

**The tag.** `twin/v0.1.0` is prefixed because the hub repository is not only the twin. It does
not exist yet: a signed tag is cut by a release workflow with gitsign, never on a laptop, so until
the owner dispatches that workflow, `world_ref` is the only pin with bytes behind it and
`PIN.yaml` carries `tag_cut: false`.

Re-vendoring is a two-line job:

```sh
.venv/bin/python -c 'import pathlib; from twin.fixtures import LIBRARY_WORLD_FILES as W; [ (pathlib.Path(".estate-clone/tuppence/twin")/r).write_text(b, encoding="utf-8", newline="\n") for r,b in W.items() ]'
.venv/bin/python .estate-clone/tuppence/twin/emit-forward-intel.py   # refuses until world_ref is re-pinned
```

### The priors in `world/world_models/reference-map.yaml` are AUTHORED, not measured

Every causal edge in this estate carries an `evidence_grade` and a written basis. The prior
beliefs in the reference map carry neither, because the `world_models` schema has no grade field:
they are floats typed into `twin/fixtures.py` by whoever added the scenario class. Vendoring puts
them inside this repository's own signed tree, where they read like measured facts. They reach no
price here, because nothing in this overlay reaches a price at all (below). Read every number in
that file as an authored prior.

## This overlay is COMPLETE and UNPRICED, and that is the finding, not a gap

`emit-forward-intel.py` exits **3, could-not-look**, and names two missing instruments (ADR-0020):

1. `party.yaml` for this party publishes **no `size:` block at all**. driftwood's perspective
   derives its amount from its signed `size.turnover`; there is no signed fact here to derive
   from, so the valuation on the declared cash flow carries no amount. The twin's `valuation`
   schema enforces this from the other side: a grade outside the pricing threshold may not carry
   an amount at all.
2. The one causal edge reaching the declared cash flow is graded **3**, because its elasticity
   triple is arithmetic on a comparable firm's own published regulatory record rather than this
   institution's own dated incident. The ladder's `path_admission_threshold` is 2, so no impact
   may enter this perspective's pound through it.

Both are named in the refusal, both at once, so that fixing one does not turn up the other a month
later. Signing a `size:` block is the owner's act (money, ADR-0025 point 6); a grade-1 or grade-2
edge is this institution's own dated record plus a regrade event saying who moved it and why.
Until both exist there is **no `forward-intel/v1/feed.json` in this repository, no `rule.yaml`,
no `bump.yaml` and no `publishes[]` record for the feed** -- a discovery record for a feed nobody
emitted is a claim with nothing behind it.

## `forward-intel/payload.schema.json`

The canonical home is `platform/feeds/forward-intel.payload.schema.json`, and the copy here is a
byte-for-byte vendoring of it. It is vendored beside the (not yet emitted) feed for two reasons:

1. a feed envelope's `payload_schema` is resolved **inside the publishing repository**
   (`verify/feed-contract/feed_contract.py`), so a path into another repo cannot validate; and
2. a departing adopter must be able to re-derive its prices offline from this checkout alone
   (spec.md, "A departing adopter").

`verify-twin-overlay.sh` byte-compares the two copies whenever the platform one is present, and
says it could not look when it is not. It never treats absence as agreement.

## `ladder.yaml` -- the rungs, and why they are not read from a selection policy

driftwood ships a versioned `selection-policy` package and reads its rungs from it. This
repository ships none; authoring one is ticket 25's shape and not ticket 64's. So the rungs are
declared in `ladder.yaml`, which records the platform release that published them
(`graded/cage.py`, `ORDER`, TABLE_VERSION 1.0.0, at platform v2.0.1) and is checked against that
release's own module when a platform checkout is present.

