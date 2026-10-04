#!/usr/bin/env python3
"""tuppence's own selection policy, version 1.1. The curve never picks; this does.

ADR-0021: the twin emits a scenario, `fair.py` annualises it, and a **versioned package the
adopter publishes and pins** turns the priced residuals into one cage tier. It lives here, in the
adopter's own repository, because whose money is at risk decides how much of it to carry -- and
because a rule that lives in an unversioned place cannot be pinned, reviewed or rolled back.

The rule, version 1 (`select`, one line):

    pick the loosest tier whose caged residual is under this party's own appetite tolerance;
    then clamp up to the party's declared overlay floor.

The rule, version 1.1 (`select_party`, the party -- ticket 78, ADR-0022):

    the Namespace carries the STRICTEST tier any priced line selected, clamped up to the
    declared overlay floor, and is never written looser than it declares today.

A price line is one regime's view; one Namespace carries one tier for every pod in it, so the
declaration cannot be looser than its worst-priced regime. "Strictest line" is the stated interim
pending the summed-residual question (PE-05 / ticket 75 Q4): when that is decided, the fold in
`select_party` is the one place a summed rule slots in. A loosening is a different question this
version does not ask -- it needs the party's aggregate residual and a proposal body that argues it.

Two refusals, both missing instruments (ADR-0020): a residual in a currency the tolerance is not
stated in, and a tier name that is not on the ladder. Everything else is priced, never refused --
including "nothing is under tolerance", which fails closed to `isolated` rather than erroring.

Stdlib only, no imports from this repository or any other, so a consumer can vendor this one file
and re-derive a tier offline.

    python3 selection-policy/selection_policy.py        # the self-check
"""
from __future__ import annotations

import hashlib
import json

VERSION = "1.1.0"

# Loosest first (ADR-0022). `infra` is absent from LADDER because nothing SELECTS it: no price
# proposes it and no floor declares it.
LADDER = ("baseline", "restricted", "quarantine", "isolated")
FAIL_CLOSED = LADDER[-1]

# ADR-0022's fifth rung, which a Namespace may nonetheless DECLARE: only a platform-role party
# may, and a declaration from any other party renders `isolated`. Either reading answers the one
# question this fold asks -- would writing the selected tier TIGHTEN the declaration? -- the same
# way, because `infra` is tighter than every rung a price can select and `isolated` is LADDER's
# own tightest rung. So the fold is always held against an `infra` declaration, and no role
# lookup is needed. Grading it as a missing instrument (which is what 1.1.0 did before
# 2026-09-04) refused a legitimate declaration.
INFRA = "infra"
DECLARABLE = LADDER + (INFRA,)


def rank(tier):
    """How TIGHT `tier` is, as an index: higher is tighter, over every tier a Namespace may
    declare -- one rung longer than what a price may select."""
    if tier not in DECLARABLE:
        raise MissingInstrument(
            "%r is not a tier a Namespace may declare %s; tighter or looser cannot be told"
            % (tier, list(DECLARABLE)))
    return DECLARABLE.index(tier)


class MissingInstrument(ValueError):
    """No price in the tolerance's currency, or no such tier. The gate cannot read, so it must
    not emit a number (ADR-0020)."""


def curve_hash(curve):
    """The hash the proposal PR carries beside the policy version.

    Over the curve exactly as the feed published it, canonicalised (sorted keys, no whitespace) so
    the same curve hashes the same whatever wrote the JSON. A changed hash resets the rejection
    ledger, so it has to move when and only when the curve does.
    """
    canonical = json.dumps(curve, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def select(residuals, tolerance, floor=None):
    """One tier, and why.

    residuals: {tier: {"amount": float, "currency": "GBP"}} -- the caged residual under each tier,
               from the estate's own pricing. Tiers absent from the mapping are not candidates.
    tolerance: {"amount": float, "currency": "GBP"} -- party.yaml's signed `appetite.tolerance`.
    floor:     party.yaml's `overlay.floor`, or None. Tighten-only: the selection clamps up to it
               and never below it.

    Returns {tier, policy_version, basis, clamped}.
    """
    if not isinstance(tolerance, dict) or "amount" not in tolerance or "currency" not in tolerance:
        raise MissingInstrument(
            "no signed appetite.tolerance for this party: whose money is at risk is the party's "
            "own declaration, and there is no fixture to fall back to"
        )
    currency = str(tolerance["currency"])
    limit = float(tolerance["amount"])

    priced = {}
    for tier, price in residuals.items():
        if tier not in LADDER:
            raise MissingInstrument(
                "%r is not on the ladder %s; an unknown tier cannot be selected, and guessing "
                "which rung it meant would be a loosening nobody signed" % (tier, list(LADDER))
            )
        if str(price["currency"]) != currency:
            raise MissingInstrument(
                "residual for %r is in %s and the tolerance is in %s. Restating one in the other "
                "needs an FX rate from the signed fx feed for this price's date; without it there "
                "is no comparison to make (ADR-0020)" % (tier, price["currency"], currency)
            )
        priced[tier] = float(price["amount"])

    # `<=`, not `<`: a residual that lands exactly ON the band still fits inside it, and
    # this has to agree with the estate's own engine (platform/graded/cage.py:select_tier)
    # to the boundary -- verify/pound-seam runs both over the same residuals and refuses a
    # disagreement. A band is a limit you may reach, not one you must stay under.
    under = [t for t in LADDER if t in priced and priced[t] <= limit]
    if under:
        chosen = under[0]
        basis = "loosest tier whose caged residual (%.2f %s) is within the tolerance (%.2f %s)" % (
            priced[chosen], currency, limit, currency)
    else:
        chosen = FAIL_CLOSED
        basis = "no priced tier is under the tolerance (%.2f %s), so the selection fails closed" % (
            limit, currency)

    clamped = False
    if floor is not None:
        if floor not in LADDER:
            raise MissingInstrument(
                "declared floor %r is not on the ladder %s" % (floor, list(LADDER)))
        if LADDER.index(chosen) < LADDER.index(floor):
            chosen, clamped = floor, True
            basis += "; clamped up to the party's declared floor %r" % floor

    return {"tier": chosen, "policy_version": VERSION, "basis": basis, "clamped": clamped}


def select_party(line_tiers, current=None, floor=None):
    """One tier for the PARTY from every line's own selection, and whether writing it tightens.

    line_tiers: the `proposed_tier` of every priced line (an iterable of tier names; a line that
                prices no tier, such as a premium, is simply not in it).
    current:    the tier the governed Namespace declares today, or None where it declares none
                (which ADR-0022 renders as `isolated`).
    floor:      party.yaml's `overlay.floor`, or None. Tighten-only: clamps up, never down.

    Returns {tier, held, policy_version, basis, clamped}. `held` is True when writing `tier` would
    not tighten the declaration -- the proposer then writes nothing. The one write that neither
    tightens nor loosens an undeclared Namespace is the explicit `isolated` line, which is allowed.

    A Namespace declared `infra` (ADR-0022's platform-role rung) is tighter than anything a price
    can select, so the fold is always held against it -- but no price and no floor may name it.

    Mirrors platform/wargamer/wargamer.py:select_party_tier; the hub's verify/tier-binding/ check
    folds every shape on the ladder through both and refuses a disagreement (the
    two-implementations guard, ADR-0021, the same guard verify/pound-seam/ applies to select()).
    Honestly: this fold is a TRANSLITERATION of platform's, written from it rather than derived
    independently, so the agreement that guard observes is copy fidelity -- that this package has
    not drifted from the rule it pins -- not two minds reaching the same answer. `select()` above
    is the independent one.
    """
    tiers = list(line_tiers)
    for tier in tiers:
        if tier not in LADDER:
            raise MissingInstrument(
                "%r is not on the ladder %s; a line pricing an unknown tier cannot be folded "
                "into the party's declaration" % (tier, list(LADDER)))
    if floor is not None and floor not in LADDER:
        raise MissingInstrument("declared floor %r is not on the ladder %s" % (floor, list(LADDER)))
    if current is not None and current not in DECLARABLE:
        raise MissingInstrument(
            "the Namespace declares %r, which is not a tier a Namespace may declare %s; tighter "
            "or looser cannot be told" % (current, list(DECLARABLE)))

    strictest = max(tiers, key=LADDER.index) if tiers else None
    chosen, clamped = strictest, False
    if floor is not None and (chosen is None or LADDER.index(floor) > LADDER.index(chosen)):
        chosen, clamped = floor, True
    effective = current if current is not None else FAIL_CLOSED
    if chosen is None:
        held, basis = True, "no line prices a tier, so there is nothing to declare"
    else:
        tightens = rank(chosen) > rank(effective)
        explicit_default = current is None and chosen == FAIL_CLOSED
        held = not (tightens or explicit_default)
        basis = "strictest priced line is %r" % strictest
        if clamped:
            basis += "; clamped up to the party's declared floor %r" % floor
        basis += "; the Namespace declares %r" % current
        basis += "; held -- only a tighter tier is written" if held else "; %r tightens it" % chosen
    return {"tier": chosen, "held": held, "policy_version": VERSION, "basis": basis,
            "clamped": clamped}


def _selfcheck():
    gbp = lambda a: {"amount": a, "currency": "GBP"}  # noqa: E731
    tol = gbp(40000)
    residuals = {"baseline": gbp(90000), "restricted": gbp(38000), "quarantine": gbp(12000),
                 "isolated": gbp(4000)}

    # the loosest tier under tolerance, not the cheapest one
    assert select(residuals, tol)["tier"] == "restricted"

    # the floor is tighten-only: it clamps up and never down
    assert select(residuals, tol, floor="quarantine")["tier"] == "quarantine"
    assert select(residuals, tol, floor="quarantine")["clamped"] is True
    assert select(residuals, tol, floor="baseline")["tier"] == "restricted"

    # nothing under tolerance fails closed rather than erroring
    assert select({"baseline": gbp(90000)}, tol)["tier"] == "isolated"

    # a tighter tolerance selects a tighter tier -- the £ moves the cage
    assert select(residuals, gbp(10000))["tier"] == "isolated"

    # the boundary: a residual exactly ON the band is inside it, same as the estate's
    # engine. This is the case the two implementations used to disagree about.
    assert select(residuals, gbp(38000))["tier"] == "restricted"

    # two missing instruments
    for bad, why in (
        (lambda: select({"baseline": {"amount": 1, "currency": "USD"}}, tol), "mixed currency"),
        (lambda: select({"paranoid": gbp(1)}, tol), "tier off the ladder"),
    ):
        try:
            bad()
        except MissingInstrument:
            pass
        else:
            raise AssertionError("%s was not refused" % why)
    try:
        select(residuals, {"amount": 1})
    except MissingInstrument:
        pass
    else:
        raise AssertionError("a tolerance with no currency was not refused")

    # the hash is stable under key order and whitespace, and moves when the curve does
    curve = [{"account": "tuppence-base-case", "net_cost_of_risk": 384000.0},
             {"account": "loss-lands-as-chargebacks", "net_cost_of_risk": 160000.0}]
    assert curve_hash(curve) == curve_hash(json.loads(json.dumps(curve, indent=4)))
    assert curve_hash(curve) != curve_hash(curve[:1])

    # version 1.1: the party's one tier is the strictest line, clamped to the floor, and never
    # written looser than the Namespace declares (ticket 78, ADR-0022)
    # tuppence's only reachable crossing today: threat-register baseline -> restricted beside
    # two lines that already select isolated, on a Namespace declared isolated -- HELD
    today = select_party(["restricted", "isolated", "isolated"], current="isolated")
    assert today["tier"] == "isolated" and today["held"] is True, today
    # strictest line wins over the crossing line's own tier
    assert select_party(["restricted", "quarantine"], current="baseline")["tier"] == "quarantine"
    assert select_party(["restricted", "quarantine"], current="baseline")["held"] is False
    # the floor clamps up, never down
    assert select_party(["restricted"], current="baseline", floor="quarantine")["tier"] == "quarantine"
    assert select_party(["isolated"], current="baseline", floor="restricted")["tier"] == "isolated"
    # equal is held: a write that does not tighten is not a write
    assert select_party(["restricted"], current="restricted")["held"] is True
    # an undeclared Namespace is isolated by default; only the explicit isolated line lands
    assert select_party(["restricted"], current=None)["held"] is True
    assert select_party(["isolated"], current=None)["held"] is False
    # nothing priced: nothing to declare
    assert select_party([], current="baseline")["held"] is True
    # ADR-0022's `infra` rung is a DECLARATION, not a selection: tighter than anything a price
    # can pick, so the fold is held against it -- never refused as an unreadable tier
    infra = select_party(["isolated"], current="infra")
    assert infra["held"] is True and infra["tier"] == "isolated", infra
    assert rank("infra") > rank("isolated") > rank("baseline")
    # off the ladder, in any position, is a missing instrument -- and `infra` is off the ladder
    # everywhere except the declaration: no price proposes it and no floor declares it
    for bad in (lambda: select_party(["paranoid"], current="baseline"),
                lambda: select_party(["infra"], current="baseline"),
                lambda: select_party(["isolated"], floor="infra"),
                lambda: select_party(["isolated"], current="deny"),
                lambda: select_party(["isolated"], floor="deny")):
        try:
            bad()
        except MissingInstrument:
            pass
        else:
            raise AssertionError("an off-ladder tier was not refused by select_party")
    assert select_party(["isolated"], current="baseline")["policy_version"] == VERSION

    print("ok  selection-policy v%s: %d asserts" % (VERSION, 27))


if __name__ == "__main__":
    _selfcheck()
