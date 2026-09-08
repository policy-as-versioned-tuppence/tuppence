# tuppence: what you are running under

This page is a **compose-time render**. Every sentence below is derived from a field of tuppence's own composed artefact — the files under `composed/` in this repository — and from nothing else. It is rendered by `platform/compose/handbook.py` from those files and nothing else. `platform/compose/verify-fresh.sh` and the hub's `verify/handbook/` re-render it from the artefact as served at a ref and compare bytes; a page that said something the artefact does not would not survive that comparison.

It is **not** a summary of anybody's reasoning, and nothing here was written by hand.

## 1. Whose rules these are

Source: `composed/HEADER.yaml` → `parents[]`. Each row is a publisher this artefact records as a parent, at the commit the file records for it. Whether that commit is the tree the composition actually read is what `composition.py verify` proves (`cut-release.yml` runs it before a tag is cut; `shift-left.yml` recomposes and diffs); this page only restates the record.

| publisher | kind | feed name | version | commit |
| --- | --- | --- | --- | --- |
| platform | implementations | — | 2.0.1 | `533dccb0a823001b396fd60ab08014bf75065a37` |
| nist | controls | — | 1.1.0 | `33a05df1f5241bca6ffbc1c69a70075cdb7a5819` |
| ico | feed | penalty-schema | v3 | `e1fb8eb5663e50088b13d872a4e44112476f516e` |
| feeds | feed | threat-register | v1 | `50a0b330a730f4f9ee9520561b0c05c8be4c9268` |

## 2. What is actually installed

Source: the object files under `composed/`, and `composed/evidence.json` → `members[]`. The verbs are counted off each object's own `spec`.

| object | kind | policy version | does | inherited from | source path |
| --- | --- | --- | --- | --- | --- |
| `governed-namespace-requires-claim` | ValidatingPolicy | — (not versioned) | refuses (1) | platform@2.0.1 | `distribution/versions.yaml (static, ADR-0014)` |
| `policy-version-orphan-guard` | ValidatingPolicy | — (not versioned) | refuses (1) | platform@2.0.1 | `distribution/versions.yaml (rendered from the array)` |
| `cage-netpol-4-0-0` | GeneratingPolicy | 4.0.0 | generates (1), evaluates | platform@2.0.1 | `distribution/policies/v4.0.0/cage-netpol.yaml` |
| `cage-tier-4-0-0` | MutatingPolicy | 4.0.0 | mutates (2) | platform@2.0.1 | `distribution/policies/v4.0.0/cage-tier.yaml` |
| `posture-trust-boundary-4-0-0` | ValidatingPolicy | 4.0.0 | refuses (1) | platform@2.0.1 | `distribution/policies/v4.0.0/posture-trust-boundary.yaml` |
| `require-nonroot-4-0-0` | ValidatingPolicy | 4.0.0 | refuses (2) | platform@2.0.1 | `distribution/policies/v4.0.0/require-nonroot.yaml` |
| `stamp-posture-4-0-0` | MutatingPolicy | 4.0.0 | mutates (1) | platform@2.0.1 | `distribution/policies/v4.0.0/stamp-posture.yaml` |

7 object(s) in the artefact; `members[]` records 7: `cage-netpol`, `cage-tier`, `posture-trust-boundary`, `stamp-posture`, `require-nonroot`, `policy-version-orphan-guard`, `governed-namespace-requires-claim`.

## 3. The cage you land in

Source: `composed/HEADER.yaml` → `governed-namespaces`, `ungoverned-namespaces`, `selection-policy`; `composed/evidence.json` → `cages[]` and each `prices[].proposed_tier`.

- Governed namespaces (1): `tuppence`
- Ungoverned namespaces (1): `tuppence-reset`
- Tier(s) the pricing proposes (1): `isolated`
- `cages[]` entries: 0

## 4. What this costs, and to whom

Source: `composed/evidence.json` → `prices[]`, and `composed/HEADER.yaml` → `exposure`. Amounts are rounded to two decimals from the field named in each row; every one carries the perspective it is booked under and the currency it is booked in. An entry the composition could not price carries its reason instead of a number, and is named in section 6. In the *proposed tier* column, `—` means the entry's kind (`premium`, `switching`) proposes no tier by construction; a feed entry with no `proposed_tier` is named absent.

| priced by | kind | name | perspective | currency | amount | moved | proposed tier |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ico | feed | penalty-schema | tuppence | GBP | GBP 9,039,791.02 | no | isolated |
| feeds | feed | threat-register | tuppence | GBP | GBP 222,574.31 | no | isolated |

- **ico/penalty-schema** — basis: lm sourced from ICO (Information Commissioner's Office) real public fines (UK GDPR / Data Protection Act 2018 s157). warn/deny lef are editorial (schema doesn't carry frequency). Not sized to any subscriber: priced at the statutory cap.
- **feeds/threat-register** — basis: payment-fraud / account-takeover via API abuse (fintech, FCA/PCI, availability+fraud flavour). lef sourced from DBIR financial-sector base rate + card-scheme fraud-loss reporting, editorial midpoint.

- **ico/penalty-schema** carries 4 priced hole(s) inside that amount: `nist/pl-2` GBP 2,711,937.31, `nist/ra-3` GBP 2,711,937.31, `nist/ca-2` GBP 1,807,958.20, `nist/ir-8` GBP 1,807,958.20

**Exposure** — booked under perspective `tuppence` in `GBP`.

- Total: GBP 9,262,365.33
- Attachment: GBP 15,000.00
- Regimes (2):
  - `uk-gdpr` from ico feed `penalty-schema` v3: GBP 9,039,791.02, 4 control(s) named
  - `threat-register` from feeds feed `threat-register` v1: GBP 222,574.31, 0 control(s) named

## 5. What is not covered

Source: `composed/HEADER.yaml` → `baseline`, `selected-controls`, `holes`; `composed/evidence.json` → `holes[]`, `ungoverned[]`, `refusals[]`, `restatements[]`, `deltas[]`.

- Baseline: **MODERATE**
- Controls selected: 287
- Controls with no implementation behind them (`holes[]`): 285 — recorded: 285
- So 2 of 287 selected controls have an implementation in this artefact. A hole is priced, never refused (ADR-0020).
- `refusals[]`: 0
- `restatements[]`: 0
- `ungoverned[]`: 1

## 6. What this handbook cannot say

Source: `composed/evidence.json` → `limits[]`, plus every field this render looked for in the artefact and did not find. A limit here is a number this page prints, not a sentence somebody wrote once and stopped checking.

**2 recorded limit(s) on the composition itself** (not counting `publisher-clone-absent`, see below):

| limit | status | count | detail |
| --- | --- | --- | --- |
| `two-publisher-conflict` | open | 1 | the cross-party rule-conflict path above is only exercised in the real estate once a second implementations publisher is pinned |
| `pinned-parent-lacks-rendered-versions` | closed | 0 | the composed set renders policy versions the pinned parent commit does not contain; the header names a parent release that holds none of these trees. every rendered version is present at the pinned commit |

One recorded limit is deliberately not stated above: `publisher-clone-absent` records which publisher clones the run that re-derived this artefact could read, which is a fact about that run and not about the artefact; a page that stated it could not re-render byte-identically with a publisher absent, and re-rendering with a publisher absent is what `composition.py verify` holds this page to (ticket 45). `composed/evidence.json` records it in full.

**2 field(s) this render looked for in the artefact and did not find.** Where a field is absent this page states nothing in its place — no default prose, no zero (ADR-0020: a missing instrument refuses; it is never invented).

- `selection-policy` (in `composed/HEADER.yaml`) — no versioned rule is recorded as having chosen the tier, so this page names none
- `deltas` (in `composed/evidence.json`) — this artefact records no `deltas` list, so this page counts none

Two things this page can never tell you, by construction, and neither is a field of the artefact: whether the rules above are the **right** rules, and whether a human read and accepted the change that produced them. The first is the editorial review ([ADR-0007](https://github.com/policy-as-versioned-flux/policy-as-versioned-flux/blob/main/docs/adr/0007-agent-assisted-editorial-governance.md)); the second is the pull request this artefact arrived in.

---

Counted from the artefact: 4 publisher(s), 7 installed object(s), 7 recorded member(s), 2 price(s), 287 selected control(s), 285 hole(s), 2 recorded limit(s), 2 named absence(s).
