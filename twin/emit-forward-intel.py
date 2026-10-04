#!/usr/bin/env python3
"""Render tuppence's forward-intel feed from tuppence's own twin overlay -- or refuse, and say why.

ADR-0019 (the envelope), ADR-0020 (a missing instrument is a refusal, never a default),
ADR-0021 (the seam). The twin emits a **scenario**; the estate annualises it with `fair.py` and a
versioned selection policy picks the tier. So this script carries no frequency, no *selected* tier
and -- ever -- no recommended action.

Ticket 144 records the native GBP turnover and filing date on `party.yaml`; the perspective
re-derives its cash flow from that fact through its declared share and periods. The institution's
own `pricing_threshold` is read from the party artefact. Grade-3 comparable published work remains
grade 3 and is admitted only where that actual declaration permits it; no comparable regulatory
event becomes this institution's observed incident.

The native and reporting currencies are both GBP, so this valuation uses no FX rate. A foreign
currency amount would require the pinned, signature-verified FX envelope for the exact filing
month. Missing money, an inadmissible grade, or a missing dated instrument is named as CANNOT LOOK
with exit 3. A complete admitted overlay emits the closed scenario shape without choosing a tier.

Deterministic. The same overlay in gives byte-identical output, on any machine and at any time:

* `version` and `published_at` are the publisher's own declaration (the constants below), bumped
  by the release PR that also writes `bump.yaml`. Nothing here reads a wall clock.
* the overlay and world pins in `derived_from` come from a **staging mirror**: `world/` and
  `orgs/` are copied into a throwaway git repository committed with the twin fixtures' fixed
  identity and date, so the pins are content-addressed and identical everywhere.

  The mirror stages `world/` and `orgs/` and nothing else, deliberately: editing this script, or
  the payload schema, or anything else in the repository must not move the feed's bytes.

Exit codes, the same three the estate's checks use everywhere:

    0  emitted, or (with --check) the file on disk is what this overlay renders
    1  observed false -- a pin that does not describe the bytes beside it, a rung with no
       response, a currency the party does not report in, or a --check mismatch
    3  could not look -- a named missing instrument. The last line says which.

Run it (needs the hub's `twin` package and pyyaml):

    .venv/bin/python .estate-clone/tuppence/twin/emit-forward-intel.py           # write
    .venv/bin/python .estate-clone/tuppence/twin/emit-forward-intel.py --check   # compare only
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess  # noqa: F401  (fixtures.git shells out; kept so the dependency is visible)
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
ORG = "tuppence"

# The publisher's own declaration. A release bumps these two lines and `forward-intel/bump.yaml`
# in the same PR a human merges -- they are not derived from the overlay, which is exactly why a
# re-emit at any hour of any day produces the same bytes. The stored v1 source is derived by this
# producer; authentic signed consumption still requires the ordinary adopter release workflow.
VERSION = "1.0.0"
PUBLISHED_AT = "2026-10-04T00:00:00Z"
HORIZON = 1  # years; ticket 08: "horizon is one year and is stated in the payload"

CLAIM_INCLUDED = ["uk-gdpr", "fca-principle-3"]
CLAIM_EXCLUDED = ["pci-dss"]
CLAIM_NOTE = (
    "The shock is an exfiltration of the account and transaction record store, scoped to the two "
    "regimes this party is supervised under that a subscribed publisher prices or publishes a "
    "schema for. Card-scheme penalties are carved out: no publisher in this party's inherits[] "
    "prices pci-dss, so a number here would have no instrument behind it."
)

# This scenario has no frequency of its own: `lef` below is null, and the estate annualises it
# with a triple published by a subscribed feed. WHICH feed is a declaration, reviewed in the same
# release PR as CLAIM_INCLUDED above, and never a fallthrough -- the version is read off
# `party.yaml` so the pin and the borrow can never name different versions.
FREQUENCY_FROM = "threat-register"

FEED_DIR = HERE / "forward-intel"
FEED_FILE = FEED_DIR / f"v{VERSION.split('.')[0]}" / "feed.json"
PAYLOAD_SCHEMA = "twin/forward-intel/payload.schema.json"

RESPONSE_ID = "run-the-payments-api-at-%s"


class CannotLook(Exception):
    """A named missing instrument. Exit 3, never a default and never a zero."""


def hub() -> Path:
    """The checkout that carries the `twin` package.

    ponytail: located by walking up. `twin` self-versions (twin/VERSION, twin/RELEASE.md) and
    PIN.yaml beside this file records which release these bytes are vendored from, but the tag is
    not cut yet, so there is still nothing on a remote for Flux or Renovate to resolve. When the
    owner dispatches the release workflow that cuts `twin/v0.1.0` this becomes an ordinary pinned
    dependency and this walk goes.
    """
    for parent in [HERE, *HERE.parents]:
        if (parent / "twin" / "repo.py").is_file() and (parent / "clone-estate.sh").is_file():
            return parent
    raise CannotLook(
        "no checkout of the `twin` package above %s. This overlay is rendered by the hub's twin "
        "loader; without it there is nothing to load the overlay with." % HERE
    )


HUB = hub()
sys.path.insert(0, str(HUB))
import yaml  # noqa: E402
from twin import evidence, fixtures  # noqa: E402
from twin.model import Overlay  # noqa: E402
from twin.repo import ModelRepo  # noqa: E402
from twin.schema import CAUSAL_EDGE  # noqa: E402


def check_twin_pin() -> str:
    """PIN.yaml names the `twin` release this directory is vendored from; refuse if it is not the
    release actually rendering it. The world layer under `world/` is a verbatim copy of that
    release's standing-library layer, so a version that has moved underneath the copy is the same
    fault as a `world_ref` that no longer describes the bytes -- caught here, once."""
    pin = yaml.safe_load((HERE / "PIN.yaml").read_text())
    declared, actual = str(pin["twin_version"]), (HUB / "twin" / "VERSION").read_text().strip()
    if declared != actual:
        sys.exit(
            "REFUSED: twin/PIN.yaml pins twin %s and the twin package rendering this overlay is "
            "%s. Re-vendor the world layer at the pinned release, or bump the pin (see "
            "VENDORED.md)." % (declared, actual)
        )
    return declared


def ladder() -> list[str]:
    """The cage rungs this overlay prices a response for.

    This producer reads the rungs declared in `twin/ladder.yaml`, independently of the estate's
    versioned `selection-policy` package. The ladder also records which
    platform release published them. Declared in one place and read here, rather than spelled a
    second time in this file: a second spelling is a list that silently stops matching.
    """
    path = HERE / "ladder.yaml"
    if not path.is_file():
        raise CannotLook(
            "twin/ladder.yaml is absent, so the rungs this overlay prices a response for are not "
            "declared anywhere and the curve has no accounts. See VENDORED.md."
        )
    doc = yaml.safe_load(path.read_text()) or {}
    rungs = [str(r) for r in (doc.get("rungs") or [])]
    if not rungs:
        raise CannotLook("twin/ladder.yaml declares no rungs")
    return rungs


def stage(dest: Path) -> Path:
    """Copy `world/` and `orgs/` into a deterministic two-commit git mirror and return it.

    Two commits, in this order, for the reason `twin.fixtures.build` does it: the world layer
    lands first so the overlay can pin the world commit it resolves against.
    """
    for unit in ("world", "orgs"):
        shutil.copytree(HERE / unit, dest / unit)
    fixtures.git(dest, "init", "-q", "-b", "main", "--object-format=sha1")
    fixtures.git(dest, "add", "-A", "world")
    fixtures.git(dest, "commit", "-q", "-m", "vendored world layer")
    world_commit = fixtures.git(dest, "rev-parse", "HEAD").strip()
    declared = str(yaml.safe_load((HERE / "orgs" / ORG / "meta.yaml").read_text())["world_ref"])
    if declared != world_commit:
        sys.exit(
            "REFUSED: orgs/%s/meta.yaml pins world_ref %s, and the vendored world layer stages to "
            "%s. A pin that does not describe the bytes beside it is not a pin." % (ORG, declared, world_commit)
        )
    fixtures.git(dest, "add", "-A")
    fixtures.git(dest, "commit", "-q", "-m", "%s overlay" % ORG)
    return dest


def priceable(overlay: Overlay) -> tuple[float, object]:
    """The two things an impact needs before it may become a number, or a named refusal.

    Both are checked here, together, and both reasons are reported when both are true -- a caller
    that learned only the first would fix a size block and then discover the grade, and the point
    of naming an instrument is that the whole instrument is named at once.
    """
    perspective = overlay.perspectives[ORG]
    cash_flow = str(perspective["cash_flow"][0])
    values = perspective["values"]
    admits = overlay.pricing_threshold

    reasons: list[str] = []
    valuation = values.get(cash_flow) or {}
    if "amount" not in valuation:
        reasons.append(
            "perspective %r declares %r as its cash flow and puts no priced valuation on it "
            "(grade %s, outside the pricing threshold of %d), because party.yaml publishes no "
            "signed size: for the amount to derive from"
            % (ORG, cash_flow, valuation.get("evidence_grade"), evidence.threshold())
        )

    hits = [e for e in overlay.graph().edges if e.type == CAUSAL_EDGE and e.target == cash_flow]
    if len(hits) != 1:
        reasons.append(
            "%d causal edges reach the declared cash flow %r; this payload prices one shock, so "
            "the overlay must carry exactly one" % (len(hits), cash_flow)
        )
    else:
        edge = hits[0]
        if not evidence.may_price(edge.grade, threshold=overlay.pricing_threshold):
            reasons.append(
                "the one causal edge to %r (%s) is graded %d, outside the ladder's path admission "
                "threshold of %d, so no impact may enter this perspective's pound through it"
                % (cash_flow, edge.id, edge.grade, admits)
            )

    if reasons:
        raise CannotLook(
            "%s's twin cannot price a forward-intel payload today, and the instruments it is "
            "missing are named rather than defaulted (ADR-0020): %s. The overlay, the vendored "
            "world layer and the six standing scenarios are all present and load; what is absent "
            "is a figure and an evidenced path, and inventing either is the one thing this "
            "estate refuses." % (ORG, "; ".join(reasons))
        )
    return float(values[cash_flow]["amount"]), hits[0]


def money(value: float) -> float:
    """Two decimal places. Rounded here rather than at the reader, so every consumer of this feed
    reads the same bytes; the underlying multiplication is IEEE-754 and portable either way."""
    return round(float(value), 2)


def curve(overlay: Overlay, rungs: list[str], impact: float) -> list[dict]:
    """What one shock costs under each rung of the cage ladder: what is left of the impact after
    that rung's graded mitigation claim, plus what the rung itself costs to run.

    The figures are per shock, in `currency`, and are NOT annualised: `lef` is null, and the
    estate multiplies the frequency in from the subscribed pricing feed.
    """
    out = []
    for tier in rungs:
        response = overlay.responses.get(RESPONSE_ID % tier)
        if response is None:
            sys.exit(
                "REFUSED: the ladder has a %r rung and this overlay prices no response for it. A "
                "curve missing a rung reads as a rung nobody would choose, which is a different "
                "claim from one nobody priced." % tier
            )
        reduction = (float(response["mitigates"]["reduction"]["mode"])
                     if evidence.may_price(int(response["mitigates"]["evidence_grade"]),
                                           threshold=overlay.pricing_threshold) else 0.0)
        cost = float(response["cost"]["mode"])
        out.append({"account": tier, "net_cost_of_risk": money(impact * (1.0 - reduction) + cost)})
    return out


def check_ladder_has_a_response(overlay: Overlay, rungs: list[str]) -> None:
    """Every declared rung is priced, checked even when nothing is emitted.

    This is the half a refusal would otherwise hide: an overlay that cannot price is still an
    overlay whose ladder must be complete, and finding a missing rung only on the day the first
    price becomes possible is finding it a year late.
    """
    absent = [t for t in rungs if overlay.responses.get(RESPONSE_ID % t) is None]
    if absent:
        sys.exit(
            "REFUSED: twin/ladder.yaml declares rung(s) %s and this overlay prices no response "
            "for them. A curve missing a rung reads as a rung nobody would choose, which is a "
            "different claim from one nobody priced." % ", ".join(repr(t) for t in absent)
        )


def valuation_amount(party, value, currency):
    """A native filing amount reaches GBP only through its pinned, verified dated FX feed."""
    from twin.valuation import MissingInstrument, rederive
    native = party.get("size", {}).get("turnover", {}).get("currency")
    fx = None
    if native != currency:
        pin_path = REPO / "gitops/flux-system/gotk-sync-fx.yaml"
        if not pin_path.exists():
            raise CannotLook("no pinned signature-verified FX source for the filing date; "
                             "USD turnover and service fees remain native USD, never labelled GBP")
        spec = yaml.safe_load(pin_path.read_text())["spec"]
        pin = spec["ref"]
        feeds = HUB / ".estate-clone/feeds"
        try:
            commit = subprocess.check_output(["git", "-C", str(feeds), "rev-parse", pin["tag"] + "^{commit}"], text=True).strip()
            if commit != pin["commit"] or not str(pin["tag"]).startswith("fx/v"):
                raise CannotLook("FX pin tag and commit do not describe the same FX release")
            subprocess.run(["gitsign", "verify-tag", pin["tag"],
                "--certificate-identity-regexp=^https://github\\.com/policy-as-versioned-feeds/feeds/\\.github/workflows/cut-release\\.yml@refs/heads/(main|release/[0-9]+\\.[0-9]+\\.x)$",
                "--certificate-oidc-issuer=https://token.actions.githubusercontent.com"],
                cwd=feeds, check=True, capture_output=True)
            version = str(pin["tag"]).split("/v", 1)[1].split(".", 1)[0]
            raw = subprocess.check_output(["git", "-C", str(feeds), "show", pin["commit"] + ":fx/v" + version + "/feed.json"], text=True)
            fx = json.loads(raw)
            if "illustrative" in str(fx["payload"].get("note", "")).lower():
                raise CannotLook("the pinned FX release declares illustrative rates; no observed currency instrument")
        except (OSError, subprocess.CalledProcessError, KeyError, ValueError) as exc:
            raise CannotLook("FX signature/rate instrument could not be read: " + str(exc)) from exc
    try:
        return rederive(party, value, currency, fx=fx)
    except MissingInstrument as exc:
        raise CannotLook(str(exc)) from exc


def payload(overlay: Overlay, currency: str, party: dict, rungs: list[str]) -> dict:
    base, edge = priceable(overlay)
    cash_flow = str(overlay.perspectives[ORG]["cash_flow"][0])
    valuation_reading = valuation_amount(party, overlay.perspectives[ORG]["values"][cash_flow], currency)
    base = float(valuation_reading["amount"])
    elasticity = edge.causal["elasticity"]
    lm = [money(base * float(elasticity[k])) for k in ("min", "mode", "max")]

    frequency_pin = next(
        (i for i in party.get("inherits") or []
         if i.get("kind") == "feed" and i.get("name") == FREQUENCY_FROM), None)
    if frequency_pin is None:
        raise CannotLook(
            "party.yaml pins no feed called %r, and this scenario has no frequency of its own: "
            "either publish an lef or subscribe to the feed that does" % FREQUENCY_FROM)
    derived_from = [{
        "party": str(frequency_pin["party"]), "kind": "feed", "name": str(frequency_pin["name"]),
        "version": str(frequency_pin["version"]).lstrip("v"),
    }, {
        "party": ORG, "kind": "feed", "name": "forward-intel", "version": VERSION,
        "ref": overlay.ref.commit,
    }]

    return {
        "perspective": ORG,
        "valuation": valuation_reading,
        "rests_on_grade": max(edge.grade, int(overlay.perspectives[ORG]["values"][str(overlay.perspectives[ORG]["cash_flow"][0])]["evidence_grade"])),
        "shock": str(overlay.edges[edge.id]["note"]).strip(),
        "horizon": HORIZON,
        "lef": None,
        "lm": lm,
        "currency": currency,
        "curve": curve(overlay, rungs, base * float(elasticity["mode"])),
        "register": [],
        "claim_scope": {"included": CLAIM_INCLUDED, "excluded": CLAIM_EXCLUDED, "note": CLAIM_NOTE},
        "derived_from": derived_from,
    }


def envelope(body: dict) -> dict:
    return {
        "kind": "feed",
        "name": "forward-intel",
        "version": VERSION,
        "published_by": ORG,
        "published_at": PUBLISHED_AT,
        "payload_schema": PAYLOAD_SCHEMA,
        "payload": body,
    }


def render() -> str:
    check_twin_pin()
    rungs = ladder()
    party = yaml.safe_load((REPO / "party.yaml").read_text())
    reporting = str(party.get("reporting_currency", "USD"))  # ADR-0020: the default is USD
    declared = yaml.safe_load((HERE / "currency.yaml").read_text())["perspectives"]
    currency = str(declared[ORG])
    if currency != reporting:
        sys.exit(
            "REFUSED: perspective %r values in %s and party.yaml reports in %s. Restating one in "
            "the other needs an FX rate from the signed fx feed for this price's date, and a "
            "missing rate is a missing instrument (ADR-0020)." % (ORG, currency, reporting)
        )
    with tempfile.TemporaryDirectory() as tmp:
        repo = ModelRepo.open(stage(Path(tmp) / "mirror"))
        overlay = Overlay.load(repo, ORG, pricing_threshold=evidence.declared_threshold(party))
        check_ladder_has_a_response(overlay, rungs)
        return json.dumps(envelope(payload(overlay, currency, party, rungs)), indent=2,
                          ensure_ascii=False) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true",
                    help="do not write; exit 1 if the file on disk is not what this run renders")
    args = ap.parse_args(argv)
    try:
        rendered = render()
    except CannotLook as why:
        # Not a failure and not a pass. The overlay is whole; the instruments a price needs are
        # not here, and they are named. A caller that treats this as green is claiming more than
        # the run observed.
        print("CANNOT LOOK: %s" % why)
        return 3
    if args.check:
        on_disk = FEED_FILE.read_text() if FEED_FILE.is_file() else None
        if on_disk != rendered:
            print("FAIL: %s is not what the overlay renders" % FEED_FILE.relative_to(REPO))
            return 1
        print("ok  %s is byte-identical to a fresh render of the overlay" % FEED_FILE.relative_to(REPO))
        return 0
    FEED_FILE.parent.mkdir(parents=True, exist_ok=True)
    FEED_FILE.write_text(rendered)
    print("wrote %s (%d bytes)" % (FEED_FILE.relative_to(REPO), len(rendered)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
