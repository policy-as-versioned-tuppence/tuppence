# tuppence: what you are running under

This page is a **compose-time render**. Every sentence below is derived from a field of tuppence's own composed artefact — the files under `composed/` in this repository — and from nothing else. It is rendered by `platform/compose/handbook.py` from those files and nothing else. `platform/compose/verify-fresh.sh` and the hub's `verify/handbook/` re-render it from the artefact as served at a ref and compare bytes; a page that said something the artefact does not would not survive that comparison.

It is **not** a summary of anybody's reasoning, and nothing here was written by hand.

## 1. Whose rules these are

Source: `composed/HEADER.yaml` → `parents[]`. Each row is a publisher this artefact records as a parent, at the commit the file records for it. Whether that commit is the tree the composition actually read is what `composition.py verify` proves (`cut-release.yml` runs it before a tag is cut; `shift-left.yml` recomposes and diffs); this page only restates the record.

| publisher | kind | feed name | version | commit |
| --- | --- | --- | --- | --- |
| platform | implementations | — | 5.0.0 | `703eff6aee959843c4160aa54fd03413f62858cc` |
| nist | controls | — | 1.1.0 | `33a05df1f5241bca6ffbc1c69a70075cdb7a5819` |
| ico | feed | penalty-schema | v3 | `e1fb8eb5663e50088b13d872a4e44112476f516e` |
| feeds | feed | threat-register | v4 | `37dfe4a2de50f1a1fd7aeb6348d819373188e0e6` |
| feeds | feed | cve | v3 | `37dfe4a2de50f1a1fd7aeb6348d819373188e0e6` |

## 2. What is actually installed

Source: the object files under `composed/`, and `composed/evidence.json` → `members[]`. The verbs are counted off each object's own `spec`.

| object | kind | policy version | does | inherited from | source path |
| --- | --- | --- | --- | --- | --- |
| `cage-netpol-bottom-rung` | GeneratingPolicy | — (not versioned) | generates (1), evaluates | platform@5.0.0 | `distribution/versions.yaml (rendered from the array, ticket 89)` |
| `cage-isolated` | PriorityClass | — (not versioned) | nothing this page can read | platform@5.0.0 | `distribution/versions.yaml (static, ticket 89)` |
| `governed-namespace-requires-claim` | MutatingPolicy | — (not versioned) | mutates (4) | platform@5.0.0 | `distribution/versions.yaml (static, ADR-0014)` |
| `governed-namespace-cage-holds` | MutatingPolicy | — (not versioned) | mutates (1) | platform@5.0.0 | `distribution/versions.yaml (static, ticket 89)` |
| `governed-namespace-unclaimed-report` | ValidatingPolicy | — (not versioned) | refuses (1) | platform@5.0.0 | `distribution/versions.yaml (static, ticket 89)` |
| `policy-version-orphan-cage-holds` | MutatingPolicy | — (not versioned) | mutates (1) | platform@5.0.0 | `distribution/versions.yaml (rendered from the array, ticket 89)` |
| `policy-version-orphan-cage` | MutatingPolicy | — (not versioned) | mutates (4) | platform@5.0.0 | `distribution/versions.yaml (rendered from the array, ticket 89)` |
| `policy-version-orphan-guard` | ValidatingPolicy | — (not versioned) | refuses (1) | platform@5.0.0 | `distribution/versions.yaml (rendered from the array)` |
| `cage-baseline-5-0-0` | PriorityClass | 5.0.0 | nothing this page can read | platform@5.0.0 | `distribution/policies/v5.0.0/priorityclasses.yaml` |
| `cage-isolated-5-0-0` | PriorityClass | 5.0.0 | nothing this page can read | platform@5.0.0 | `distribution/policies/v5.0.0/priorityclasses.yaml` |
| `cage-netpol-5-0-0` | GeneratingPolicy | 5.0.0 | generates (1), evaluates | platform@5.0.0 | `distribution/policies/v5.0.0/cage-netpol.yaml` |
| `cage-quarantine-5-0-0` | PriorityClass | 5.0.0 | nothing this page can read | platform@5.0.0 | `distribution/policies/v5.0.0/priorityclasses.yaml` |
| `cage-restricted-5-0-0` | PriorityClass | 5.0.0 | nothing this page can read | platform@5.0.0 | `distribution/policies/v5.0.0/priorityclasses.yaml` |
| `cage-tier-5-0-0` | MutatingPolicy | 5.0.0 | mutates (2) | platform@5.0.0 | `distribution/policies/v5.0.0/cage-tier.yaml` |
| `posture-trust-boundary-5-0-0` | ValidatingPolicy | 5.0.0 | refuses (1) | platform@5.0.0 | `distribution/policies/v5.0.0/posture-trust-boundary.yaml` |
| `require-nonroot-5-0-0` | ValidatingPolicy | 5.0.0 | refuses (1) | platform@5.0.0 | `distribution/policies/v5.0.0/require-nonroot.yaml` |
| `stamp-posture-5-0-0` | MutatingPolicy | 5.0.0 | mutates (1) | platform@5.0.0 | `distribution/policies/v5.0.0/stamp-posture.yaml` |
| `cage-baseline-6-0-0` | PriorityClass | 6.0.0 | nothing this page can read | platform@5.0.0 | `distribution/policies/v6.0.0/priorityclasses.yaml` |
| `cage-isolated-6-0-0` | PriorityClass | 6.0.0 | nothing this page can read | platform@5.0.0 | `distribution/policies/v6.0.0/priorityclasses.yaml` |
| `cage-netpol-6-0-0` | GeneratingPolicy | 6.0.0 | generates (1), evaluates | platform@5.0.0 | `distribution/policies/v6.0.0/cage-netpol.yaml` |
| `cage-quarantine-6-0-0` | PriorityClass | 6.0.0 | nothing this page can read | platform@5.0.0 | `distribution/policies/v6.0.0/priorityclasses.yaml` |
| `cage-restricted-6-0-0` | PriorityClass | 6.0.0 | nothing this page can read | platform@5.0.0 | `distribution/policies/v6.0.0/priorityclasses.yaml` |
| `cage-tier-6-0-0` | MutatingPolicy | 6.0.0 | mutates (2) | platform@5.0.0 | `distribution/policies/v6.0.0/cage-tier.yaml` |
| `posture-trust-boundary-6-0-0` | ValidatingPolicy | 6.0.0 | refuses (1) | platform@5.0.0 | `distribution/policies/v6.0.0/posture-trust-boundary.yaml` |
| `require-nonroot-6-0-0` | ValidatingPolicy | 6.0.0 | refuses (1) | platform@5.0.0 | `distribution/policies/v6.0.0/require-nonroot.yaml` |
| `stamp-posture-6-0-0` | MutatingPolicy | 6.0.0 | mutates (1) | platform@5.0.0 | `distribution/policies/v6.0.0/stamp-posture.yaml` |
| `cage-baseline-7-0-0` | PriorityClass | 7.0.0 | nothing this page can read | platform@5.0.0 | `distribution/policies/v7.0.0/priorityclasses.yaml` |
| `cage-isolated-7-0-0` | PriorityClass | 7.0.0 | nothing this page can read | platform@5.0.0 | `distribution/policies/v7.0.0/priorityclasses.yaml` |
| `cage-netpol-7-0-0` | GeneratingPolicy | 7.0.0 | generates (1), evaluates | platform@5.0.0 | `distribution/policies/v7.0.0/cage-netpol.yaml` |
| `cage-quarantine-7-0-0` | PriorityClass | 7.0.0 | nothing this page can read | platform@5.0.0 | `distribution/policies/v7.0.0/priorityclasses.yaml` |
| `cage-restricted-7-0-0` | PriorityClass | 7.0.0 | nothing this page can read | platform@5.0.0 | `distribution/policies/v7.0.0/priorityclasses.yaml` |
| `cage-tier-7-0-0` | MutatingPolicy | 7.0.0 | mutates (2) | platform@5.0.0 | `distribution/policies/v7.0.0/cage-tier.yaml` |
| `require-nonroot-7-0-0` | ValidatingPolicy | 7.0.0 | refuses (1) | platform@5.0.0 | `distribution/policies/v7.0.0/require-nonroot.yaml` |
| `stamp-posture-7-0-0` | MutatingPolicy | 7.0.0 | mutates (1) | platform@5.0.0 | `distribution/policies/v7.0.0/stamp-posture.yaml` |

34 object(s) in the artefact; `members[]` records 34: `cage-baseline`, `cage-isolated`, `cage-netpol`, `cage-quarantine`, `cage-restricted`, `cage-tier`, `posture-trust-boundary`, `stamp-posture`, `require-nonroot`, `cage-baseline`, `cage-isolated`, `cage-netpol`, `cage-quarantine`, `cage-restricted`, `cage-tier`, `posture-trust-boundary`, `stamp-posture`, `require-nonroot`, `cage-baseline`, `cage-isolated`, `cage-netpol`, `cage-quarantine`, `cage-restricted`, `cage-tier`, `stamp-posture`, `require-nonroot`, `policy-version-orphan-guard`, `governed-namespace-requires-claim`, `policy-version-orphan-cage`, `policy-version-orphan-cage-holds`, `governed-namespace-cage-holds`, `governed-namespace-unclaimed-report`, `cage-netpol-bottom-rung`, `cage-isolated`.

## 3. The cage you land in

Source: `composed/HEADER.yaml` → `governed-namespaces`, `ungoverned-namespaces`, `selection-policy`; `composed/evidence.json` → `cages[]` and each `prices[].proposed_tier`.

- Governed namespaces (1): `tuppence`
- Ungoverned namespaces (2): `openbao`, `tuppence-reset`
- The tier was chosen by selection-policy version **1.1.0**.
- Tier(s) the pricing proposes (2): `baseline`, `isolated`
- `cages[]` entries: 0

## 4. What this costs, and to whom

Source: `composed/evidence.json` → `prices[]`, and `composed/HEADER.yaml` → `exposure`. Amounts are rounded to two decimals from the field named in each row; every one carries the perspective it is booked under and the currency it is booked in. An entry the composition could not price carries its reason instead of a number, and is named in section 6. In the *proposed tier* column, `—` means the entry's kind (`premium`, `switching`, `supersede`) proposes no tier by construction; a feed entry with no `proposed_tier` is named absent. An `agent-cage` entry prices the twin agent's cage (ADR-0031): the tier in its row is the twin agent's own rung, for the subject the row names, never the Namespace's, and the Namespace fold does not read it.

| priced by | kind | name | perspective | currency | amount | moved | proposed tier |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ico | feed | penalty-schema | tuppence | GBP | GBP 17,907,950.70 | no | isolated |
| ico | supersede | penalty-schema | tuppence | GBP | GBP 1,128,446.21 | no | — |
| feeds | feed | threat-register | tuppence | GBP | GBP 326,139.13 | no | isolated |
| feeds | feed | cve | tuppence | GBP | GBP 437,107.34 | no | isolated |
| twin | twin | forward-intel | tuppence | GBP | GBP 84,198,283.09 | no | isolated |
| platform | agent-cage | twin-agent | tuppence | GBP | GBP 18.70 | no | baseline |
| ico | switching | penalty-schema | tuppence | GBP | GBP 17,907,950.70 | no | — |
| feeds | switching | threat-register | tuppence | GBP | could not look (section 6) | no | — |
| feeds | switching | cve | tuppence | GBP | could not look (section 6) | no | — |

- **ico/penalty-schema** — Publisher tags were observed when this artefact was composed; the recorded observation is replayed offline and during verification. It does not establish the publisher's current newest major. A fresh composition with the publisher present refreshes it.
- **ico/penalty-schema** — basis: lm sourced from ICO (Information Commissioner's Office) real public fines (UK GDPR / Data Protection Act 2018 s157). warn/deny lef are editorial (schema doesn't carry frequency). Scaled to a subscriber turnover of 861,741,000.00 GBP.
- **ico/penalty-schema supersede** — clock starts 2026-09-10; priced as of 2026-10-03. the pinned checkout carries no directory for v4.0.0, so the newer major's content is unread here: this line is priced from the signed tags alone, and no retirement to v4 is proposed until the ico pin reaches a commit that carries it
- **ico/penalty-schema** (supersede) — basis: the pinned line's own amount x (eol_ramp(since, as_of) - 1): the surcharge the feeds module's EOL ramp puts on a version its publisher has superseded, +1x per year behind and capped at +4x, where `since` is the day the newer major's signing tag was cut; zero on that day, printed with both dates, and never summed into the exposure the line itself is already in
- **feeds/threat-register** — Publisher tags were observed when this artefact was composed; the recorded observation is replayed offline and during verification. It does not establish the publisher's current newest major. A fresh composition with the publisher present refreshes it.
- **feeds/threat-register** — basis: payment-fraud / account-takeover via API abuse (fintech, FCA/PCI, availability+fraud flavour). Frequency basis (editorial, read 2026-09-09): Annual loss-event frequency for this institution's headline threat. DBIR financial-sector base rate + 2026 UK fintech ATO-uptick roundup, editorial midpoint COULD NOT LOOK: the DBIR publishes sector breach-frequency ranges, not a rate for one named institution, and no run of this estate has counted events for these three. Editorial midpoints, labelled as such. Magnitude basis (editorial, read 2026-09-09): Impact per payment-fraud / account-takeover event for a UK fintech: direct fraud loss plus reimbursement, higher per event than retail PII and far below a health record. COULD NOT LOOK: no run of this estate has counted per-event losses for any institution in this register, and none of the three publishes one. These are the publisher's editorial bands, moved here from platform/feeds/to_fair_scenario.py's THREAT_LM_GBP unchanged so that the move itself moves no price. What would close it: a per-sector per-event loss figure with a published source and a date, or an institution's own signed incident cost.
- **feeds/cve** — Publisher tags were observed when this artefact was composed; the recorded observation is replayed offline and during verification. It does not establish the publisher's current newest major. A fresh composition with the publisher present refreshes it.
- **feeds/cve** — basis: Apache/Log4j2 CVSS 10.0 (critical), epss=0.99999. Source: CISA KEV; NVD CVE-2021-44228; FIRST EPSS 2026-10-03. headline entry CVE-2021-44228 of 2 (largest mode-product entry, mode lef x mode lm -- an ordinal proxy, not fair.py's PERT expectation; ticket 75 Q4); not priced by this line: CVE-2021-45046. Scanned intersection 2; 8 scanned CVE(s) outside the pinned feed carry no amount.
- **twin/forward-intel** — basis: payment-fraud / account-takeover via API abuse (fintech, FCA/PCI, availability+fraud flavour). Frequency basis (editorial, read 2026-09-09): Annual loss-event frequency for this institution's headline threat. DBIR financial-sector base rate + 2026 UK fintech ATO-uptick roundup, editorial midpoint COULD NOT LOOK: the DBIR publishes sector breach-frequency ranges, not a rate for one named institution, and no run of this estate has counted events for these three. Editorial midpoints, labelled as such. Magnitude basis (editorial, read 2026-09-09): Impact per payment-fraud / account-takeover event for a UK fintech: direct fraud loss plus reimbursement, higher per event than retail PII and far below a health record. COULD NOT LOOK: no run of this estate has counted per-event losses for any institution in this register, and none of the three publishes one. These are the publisher's editorial bands, moved here from platform/feeds/to_fair_scenario.py's THREAT_LM_GBP unchanged so that the move itself moves no price. What would close it: a per-sector per-event loss figure with a published source and a date, or an institution's own signed incident cost.
- **twin/forward-intel** — rests on evidence grade 3, the weakest grade behind the twin's price (its propagation path, its valuation and the path that admits it to the cash flow; ADR-0032)
- **platform/twin-agent** — basis: Frequency basis (published, read 2026-09-26): Annual frequency with which a marketplace action this institution's scheduled twin sweep runs by floating tag is compromised at that tag, taken as the frequency the sweep's write credential is misused. N x C / M with N = 1 (actions/checkout@v4, the one distinct marketplace action the served twin-sweep.yml references, read at tuppence origin/main 5deffe6 on 2026-09-26); C = 2 for the min and the mode (the marketplace actions CISA's alert of 2025-03-18 names as compromised in 2025: tj-actions/changed-files, CVE-2025-30066, used in over 23,000 repositories per StepSecurity's 2025-03-14 report, and reviewdog/action-setup, CVE-2025-30154) and 7 for the max (those two plus the five downstream reviewdog actions Wiz named on 2025-03-17 as compromised through action-setup: action-shellcheck, action-composite-template, action-staticcheck, action-ast-grep, action-typos); M = 23,757 marketplace actions counted over four months by Chaiwut and Nikiforakis (IEEE SecDev 2025). 8.42e-05 to 0.000295 events a year. Grade 3 on the estate's evidence ladder: published work, not observed here. COULD NOT LOOK: No publisher counts credential MISUSE after a compromise, so this rate counts every published compromise of a floating-tag marketplace action as a misuse of the sweep's token: an upper bound for that door, and the only door with a published count. Not in the rate: the hub checkout at `main` and `pip install pyyaml`, dependencies the served sweep runs unpinned today (eco-system ticket 143 pins both by hash, and hash-pinning closes the floating-tag door this rate counts); a maintainer's own compromised account pushing a workflow (GhostAction, GitGuardian, 2025-09-05: 327 users, 817 repositories, 3,325 secrets), which is a human credential, not the scheduled agent's; and a pwn request on the repository's own workflow (the Nx s1ngularity entry point, 2025-08-26). The count is one year's (2025): no second year is counted, so the min and mode are the two actions with a CVE and the max the seven Wiz names. No run of this estate has observed a misuse. What would close it: an institution's own dated incident record (grade 2), or a published per-repository annual rate of CI credential misuse.
- **platform/twin-agent** (`agent-cage`, subject `twin-agent`) — a rung for the twin agent, not the Namespace: `baseline`, picked by selection-policy version 1.1.0 over residuals derived from `platform-twin-agent-table@1.0.0` (baseline GBP 18.70, restricted GBP 18.70, quarantine GBP 18.70, isolated GBP 0.00). Loss magnitude: the gap between this party's residual at `baseline` and at `isolated` on its own twin line (GBP 57,254,832.50 a year) over the gate's detection window of 1.0 day(s) (the hub's .github/workflows/truth.yml `schedule: cron: '47 5 * * *'` (once a day), read 2026-09-26 at policy-as-versioned-flux/policy-as-versioned-flux origin/main 9c3b1f22). Frequency: threat-register@v4. Run cost GBP 0.00 at every rung, outside the selection. The rung is what the twin-sweep writer job reads (eco-system ticket 143 item 4).
- **ico/penalty-schema** (switching) — basis: re-composed with this publisher's feed edges dropped
- **feeds/threat-register** (switching) — basis: re-composed with this publisher's feed edges dropped
- **feeds/cve** (switching) — basis: re-composed with this publisher's feed edges dropped

- **ico/penalty-schema** carries 4 priced hole(s) inside that amount: `nist/pl-2` GBP 5,372,385.21, `nist/ra-3` GBP 5,372,385.21, `nist/ca-2` GBP 3,581,590.14, `nist/ir-8` GBP 3,581,590.14

**Exposure** — booked under perspective `tuppence` in `GBP`.

- Total: GBP 102,869,480.25
  - What this number is: an ordinal, auditable comparison under one perspective; not an expected annual loss.
  - Every figure under this section is derived from published feeds through published converters, and is reproducible from the signed inputs named beside it -- that is what AUDITABLE means here. What it is NOT: the loss-event frequencies and several loss magnitudes it rests on are editorial bands carrying a named could-not-look rather than counted rates (ico penalty-schema major 4, feeds threat-register major 3), so the total is usable for COMPARING one version, one pin or one control set against another under this one perspective, and not as a number to reserve against. Totals under two different perspectives are two balance sheets and are never added (ADR-0021). Ticket 75 Q4 (a), eco-system ticket 79 item 10.
- Aggregate of the selected-tier residuals: GBP 2,057,389.61 against a tolerance of GBP 15,000.00 -- BREACHES the declared aggregate.
  - `penalty-schema` at tier `isolated`: GBP 358,159.01
  - `threat-register` at tier `isolated`: GBP 6,522.78
  - `cve` at tier `isolated`: GBP 8,742.15
  - `forward-intel` at tier `isolated`: GBP 1,683,965.66
- Attachment: GBP 15,000.00
- Regimes (4):
  - `uk-gdpr` from ico feed `penalty-schema` v3: GBP 17,907,950.70, 4 control(s) named
  - `threat-register` from feeds feed `threat-register` v4: GBP 326,139.13, 0 control(s) named
  - `cve` from feeds feed `cve` v3: GBP 437,107.34, 0 control(s) named
  - `forward-intel` from twin feed `forward-intel` 1.0.0: GBP 84,198,283.09, 0 control(s) named

### Floor comparison

Source: `composed/floor-change.json`; recorded floor inputs in `composed/HEADER.yaml` → `floor-comparison`.

Floor: **unknown → absent**. floor-only counterfactual at current publisher, scenario, appetite and selection inputs.

Could not look: previous floor was not recorded; absence of history is not an absent floor.

- ico/penalty-schema: unknown → isolated; retained residual unknown → GBP 358,159.01; delta unknown.
- feeds/threat-register: unknown → isolated; retained residual unknown → GBP 6,522.78; delta unknown.
- feeds/cve: unknown → isolated; retained residual unknown → GBP 8,742.15; delta unknown.
- twin/forward-intel: unknown → isolated; retained residual unknown → GBP 1,683,965.66; delta unknown.

Instrument: `platform-cage-tiers@1.0.0`. selection evidence, not an enacted Namespace tier; platform reductions are self-declared calibration, not measured effectiveness.

## 5. What is not covered

Source: `composed/HEADER.yaml` → `baseline`, `selected-controls`, `holes`; `composed/evidence.json` → `holes[]`, `ungoverned[]`, `refusals[]`, `restatements[]`, `deltas[]`.

- Baseline: **MODERATE**
- Controls selected: 287
- Controls with no implementation behind them (`holes[]`): 284 — recorded: 284
- So 3 of 287 selected controls have an implementation in this artefact. A hole is priced, never refused (ADR-0020).
- `refusals[]`: 0
- `restatements[]`: 0
- `deltas[]`: 0
- `ungoverned[]`: 2

## 6. What this handbook cannot say

Source: `composed/evidence.json` → `limits[]`, plus every field this render looked for in the artefact and did not find. A limit here is a number this page prints, not a sentence somebody wrote once and stopped checking.

**2 recorded limit(s) on the composition itself** (not counting `publisher-clone-absent`, see below):

| limit | status | count | detail |
| --- | --- | --- | --- |
| `two-publisher-conflict` | open | 1 | the cross-party rule-conflict path above is only exercised in the real estate once a second implementations publisher is pinned |
| `pinned-parent-lacks-rendered-versions` | closed | 0 | the composed set renders policy versions the pinned parent commit does not contain; the header names a parent release that holds none of these trees. every rendered version is present at the pinned commit |

One recorded limit is deliberately not stated above: `publisher-clone-absent` records which publisher clones the run that re-derived this artefact could read, which is a fact about that run and not about the artefact; a page that stated it could not re-render byte-identically with a publisher absent, and re-rendering with a publisher absent is what `composition.py verify` holds this page to (ticket 45). `composed/evidence.json` records it in full.

**15 field(s) this render looked for in the artefact and did not find.** Where a field is absent this page states nothing in its place — no default prose, no zero (ADR-0020: a missing instrument refuses; it is never invented).

- `spec of cage-isolated` (in `composed/bottom-rung-priorityclass.yaml`) — this object declares no mutation, validation or generation this page can read
- `spec of cage-baseline-5-0-0` (in `composed/policies/v5.0.0/cage-baseline.yaml`) — this object declares no mutation, validation or generation this page can read
- `spec of cage-isolated-5-0-0` (in `composed/policies/v5.0.0/cage-isolated.yaml`) — this object declares no mutation, validation or generation this page can read
- `spec of cage-quarantine-5-0-0` (in `composed/policies/v5.0.0/cage-quarantine.yaml`) — this object declares no mutation, validation or generation this page can read
- `spec of cage-restricted-5-0-0` (in `composed/policies/v5.0.0/cage-restricted.yaml`) — this object declares no mutation, validation or generation this page can read
- `spec of cage-baseline-6-0-0` (in `composed/policies/v6.0.0/cage-baseline.yaml`) — this object declares no mutation, validation or generation this page can read
- `spec of cage-isolated-6-0-0` (in `composed/policies/v6.0.0/cage-isolated.yaml`) — this object declares no mutation, validation or generation this page can read
- `spec of cage-quarantine-6-0-0` (in `composed/policies/v6.0.0/cage-quarantine.yaml`) — this object declares no mutation, validation or generation this page can read
- `spec of cage-restricted-6-0-0` (in `composed/policies/v6.0.0/cage-restricted.yaml`) — this object declares no mutation, validation or generation this page can read
- `spec of cage-baseline-7-0-0` (in `composed/policies/v7.0.0/cage-baseline.yaml`) — this object declares no mutation, validation or generation this page can read
- `spec of cage-isolated-7-0-0` (in `composed/policies/v7.0.0/cage-isolated.yaml`) — this object declares no mutation, validation or generation this page can read
- `spec of cage-quarantine-7-0-0` (in `composed/policies/v7.0.0/cage-quarantine.yaml`) — this object declares no mutation, validation or generation this page can read
- `spec of cage-restricted-7-0-0` (in `composed/policies/v7.0.0/cage-restricted.yaml`) — this object declares no mutation, validation or generation this page can read
- `prices[7].amount` (in `composed/evidence.json`) — feeds/threat-register could not be priced: missing instrument: tuppence/twin/forward-intel/v1/feed.json supplies no lef and its derived_from names 0 subscribed feeds that price one (none); a borrowed frequency has to be named, not guessed at
- `prices[8].amount` (in `composed/evidence.json`) — feeds/cve could not be priced: missing instrument: tuppence/twin/forward-intel/v1/feed.json supplies no lef and its derived_from names 0 subscribed feeds that price one (none); a borrowed frequency has to be named, not guessed at

Two things this page can never tell you, by construction, and neither is a field of the artefact: whether the rules above are the **right** rules, and whether a human read and accepted the change that produced them. The first is the editorial review ([ADR-0007](https://github.com/policy-as-versioned-flux/policy-as-versioned-flux/blob/main/docs/adr/0007-agent-assisted-editorial-governance.md)); the second is the pull request this artefact arrived in.

---

Counted from the artefact: 5 publisher(s), 34 installed object(s), 34 recorded member(s), 9 price(s), 287 selected control(s), 284 hole(s), 2 recorded limit(s), 15 named absence(s).
