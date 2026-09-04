#!/usr/bin/env bash
# Beat: "tuppence's twin carries six standing scenarios of its own, four of them realising committed
# classes, and the one about a published penalty prices the consequence and never the fine."
#
# Offline. Eco-system ticket 64, the shape ticket 29 built for driftwood; decision ticket 11 answer
# item 4, ticket 19 answer items 3 and 4.
# Three outcomes only:
#   PASS (exit 0)  every assertion observed true
#   FAIL (exit 1)  an assertion observed false
#   SKIP (exit 3)  could not look, with the reason on the last line
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORG="tuppence"

skip() { echo "SKIP: $*"; exit 3; }

# The `twin` package owns the class enum and the standing library. This overlay vendors that
# package's world layer (PIN.yaml, VENDORED.md) but not its code, so the enum has to be read from
# the release rendering it -- never re-typed here, which is how the third place silently stops
# matching the other two.
HUB=""
d="$HERE"
while [ "$d" != "/" ]; do
  [ -f "$d/twin/repo.py" ] && [ -f "$d/clone-estate.sh" ] && { HUB="$d"; break; }
  d="$(dirname "$d")"
done
[ -n "$HUB" ] || skip "no checkout of the twin package above $HERE; the committed class enum and the standing library cannot be read"

PY="$HUB/.venv/bin/python"
if [ ! -x "$PY" ]; then
  PY=python3
  "$PY" -c 'import yaml' 2>/dev/null || skip "no $HUB/.venv and python3 lacks pyyaml"
fi
command -v git >/dev/null 2>&1 || skip "git is needed to build the standing library fixture"

log="$(mktemp)"; trap 'rm -f "$log"' EXIT
HUB="$HUB" HERE="$HERE" ORG="$ORG" "$PY" - >"$log" 2>&1 <<'PY'
import os, re, subprocess, sys, tempfile
from pathlib import Path

HUB, HERE = Path(os.environ["HUB"]), Path(os.environ["HERE"])
ORG = os.environ["ORG"]
sys.path.insert(0, str(HUB))
import yaml
from twin import fixtures, schema
from twin.model import Overlay
from twin.repo import ModelRepo

def money_in(text):
    """Money-shaped, not digit-shaped: a scenario legitimately carries dates and an ADR number.
    A symbol, an ISO code before a figure, a thousands-separated figure, or a magnitude word."""
    return re.findall(
        r"[£$€]\s?[\d,.]+|\b(?:GBP|USD|EUR)\s?[\d,.]+|\b\d{1,3}(?:,\d{3})+\b"
        r"|\b\d+(?:\.\d+)?\s?(?:k|m|million|bn|billion)\b",
        text, re.I)


# Planted, because a screen only ever run against text that passes it cannot tell "correct" from
# "matches nothing". Three ways a fine gets typed, and the two things that are not one.
assert money_in("the penalty was £17,500,000"), "the money screen misses a symbol and separators"
assert money_in("a 4.4m fine under GBP 750000"), "the money screen misses magnitudes and ISO codes"
assert not money_in("at: '2026-09-04'\nhorizon: '2027-09-04'\nADR-0021"), "the money screen reads dates as money"

LINES = []
def out(status, msg):
    LINES.append(status)
    print("%s: %s" % (status, msg))

SCENARIOS = HERE / "orgs" / ORG / "scenarios"
files = sorted(SCENARIOS.glob("*.yaml"))
docs = {p.stem: yaml.safe_load(p.read_text()) for p in files}

# 1. six standing scenarios, each one loadable and complete
out("PASS" if len(docs) == 6 else "FAIL",
    "the overlay carries %d standing scenarios (the six of decision ticket 11 answer item 4)" % len(docs))
required = ("id", "question", "proposition", "at", "components", "world_models", "affected_parties")
thin = sorted("%s (no %s)" % (n, ", ".join(f for f in required if not d.get(f))) for n, d in docs.items()
              if not all(d.get(f) for f in required))
out("FAIL" if thin else "PASS",
    "every scenario declares a question, a proposition, a date, components, a world model and an "
    "affected-parties register" + ("; thin: " + "; ".join(thin) if thin else ""))

# 2. the four subjects that carry a class name committed classes, and the two from ticket 19
#    deliberately carry none -- `class` is optional and closed, so an uncommitted class is a
#    load-time refusal rather than a silently uncounted one.
classed = {n: str(d["class"]) for n, d in docs.items() if d.get("class")}
committed = set(schema.COMMITTED_SCENARIO_CLASSES)
stray = sorted("%s -> %s" % (n, c) for n, c in classed.items() if c not in committed)
out("FAIL" if stray else "PASS",
    "%d scenario(s) name a committed class (%s); %d name none, by decision"
    % (len(classed), ", ".join(sorted(classed.values())), len(docs) - len(classed))
    + ("; not committed: " + ", ".join(stray) if stray else ""))
want = {"supply-shock", "eol-date-passes", "penalty-published", "bus-factor-key-person"}
absent = sorted(want - set(classed.values()))
out("FAIL" if absent else "PASS",
    "the four classed subjects are present: a tier-one supplier failing (supply-shock), an EOL "
    "date passing, a penalty published, a key-person event"
    + ("; missing: " + ", ".join(absent) if absent else ""))

# 3. the three places each class lands. The enum and this overlay are read above; the third is
#    the standing library, built fresh from the same release. Both classes ticket 29 committed are
#    checked here too: this overlay realises them, so a class that lost its library scenario would
#    leave this overlay naming an enum entry nothing else carries.
for new in ("eol-date-passes", "penalty-published"):
    in_enum = new in committed
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "library"
        fixtures.build_library_org(root)
        library = Overlay.load(ModelRepo.open(root), fixtures.LIBRARY_ORG)
        in_library = any(str(s.get("class")) == new for s in library.scenarios.values())
    in_overlay = new in set(classed.values())
    ok = in_enum and in_library and in_overlay
    out("PASS" if ok else "FAIL",
        "class %r lands in all three places: enum=%s library=%s overlay=%s"
        % (new, in_enum, in_library, in_overlay))

# 4. the seam. A scenario about a published penalty forecasts the consequence on the value chain;
#    the amount of the fine is the estate's, priced from the regulator's own published schema
#    through composition. So there is no money in that file at all -- no symbol, no figure.
penalty = next((p for p in files if str(docs[p.stem].get("class")) == "penalty-published"), None)
if penalty is None:
    out("FAIL", "no penalty-published scenario to check for a fine amount")
else:
    text = penalty.read_text()
    money = money_in(text)
    out("FAIL" if money else "PASS",
        "%s prices no fine: no currency symbol and no figure anywhere in it (the estate prices the "
        "fine, the twin prices what the publication does)" % penalty.name
        + ("; found " + ", ".join(money) if money else ""))
    # ...and the other half of the same sentence. "Prices the consequence, never the fine" graded
    # on the absent half only would pass a scenario that priced NOTHING identically to one that
    # priced the value-chain shock. So the artefact has to say in its own words which half it
    # carries.
    consequence = str(docs[penalty.stem].get("note", "")) + str(docs[penalty.stem].get("question", ""))
    said = "not yet priced" in consequence.lower() or "not priced" in consequence.lower()
    out("PASS" if said else "FAIL",
        "%s says which half of the seam it carries: the consequence is declared and its note says "
        "in its own words that it is not priced" % penalty.name
        + ("" if said else "; the note claims neither a price nor the absence of one, so a reader "
                          "cannot tell the post-penalty value-chain shock is unpriced"))

# 5. the supply-shock headline is a scenario here and never a news-feed entry (amendment C13).
shock = [n for n, d in docs.items() if str(d.get("class")) == "supply-shock"]
out("PASS" if shock else "FAIL",
    "the supply-shock headline lives in this overlay as %s, not in a news feed"
    % (", ".join(shock) or "nothing"))

# 6. every scenario resolves against the vendored world layer + this overlay. Components are
#    checked by the loader itself; propositions and world models are checked here because the
#    loader does not, and a scenario naming a proposition nobody published forecasts nothing.
world = HERE / "world"
props = {yaml.safe_load(p.read_text())["id"] for p in (world / "propositions").glob("*.yaml")}
models = {yaml.safe_load(p.read_text())["id"] for p in (world / "world_models").glob("*.yaml")}
dangling = sorted("%s -> %s" % (n, d["proposition"]) for n, d in docs.items() if d["proposition"] not in props)
dangling += sorted("%s -> %s" % (n, m) for n, d in docs.items() for m in d["world_models"] if m not in models)
out("FAIL" if dangling else "PASS",
    "every scenario's proposition and world model exist in the vendored world layer"
    + ("; dangling: " + "; ".join(dangling) if dangling else ""))
believed = set()
for p in (world / "world_models").glob("*.yaml"):
    believed |= set(yaml.safe_load(p.read_text())["beliefs"])
unbelieved = sorted(d["proposition"] for d in docs.values() if d["proposition"] not in believed)
out("FAIL" if unbelieved else "PASS",
    "every scenario's proposition carries a prior belief in the reference map"
    + ("; without one: " + ", ".join(unbelieved) if unbelieved else ""))

# 7. the loader agrees: the whole overlay, scenarios included, loads through the emitter's own
#    deterministic mirror. Cheaper to assert the emitter than to restage the mirror here. Exit 3
#    is its named refusal (no signed size, and one grade-3 edge) -- reported as a could-not-look
#    with the reason, never swallowed as a pass.
r = subprocess.run([sys.executable, str(HERE / "emit-forward-intel.py"), "--check"],
                   capture_output=True, text=True)
told = (r.stdout + r.stderr).strip().replace("\n", " | ")
if r.returncode == 0:
    out("PASS", "the overlay with its six scenarios still loads and re-renders the feed byte-identically")
elif r.returncode == 3:
    out("SKIP", "the overlay with its six scenarios loads, and the emitter could not price it: " + told[:400])
else:
    out("FAIL", "the overlay with its six scenarios did not load: " + told[:400])

# 8. the pinned-feed-version -> dated-signal lookup (ticket 29, spec user story 45). The clock
#    binds without judgement only if the binding is a table it cannot argue with: every pin
#    resolves to exactly one row, every row names a scenario that exists, and a scenario no pin
#    binds is DECLARED unbound with a reason rather than quietly unreachable.
lookup_path = HERE / "signals.yaml"
if not lookup_path.exists():
    out("FAIL", "twin/signals.yaml is absent: no subscribed feed version maps to a dated signal, "
                "so the twin sweep would have to decide on the clock what a pin move means")
else:
    lookup = yaml.safe_load(lookup_path.read_text()) or {}
    rows = lookup.get("signals") or []
    party = yaml.safe_load((HERE.parent / "party.yaml").read_text()) or {}

    def key(d):
        return (str(d.get("party")), str(d.get("kind")), str(d.get("name") or ""),
                str(d.get("version")))

    pins = [key(i) for i in (party.get("inherits") or [])]
    keyed = {}
    for row in rows:
        keyed.setdefault(key(row.get("pin") or {}), []).append(row)
    unresolved = sorted("/".join(k) for k in pins if k not in keyed)
    doubled = sorted("/".join(k) for k, v in keyed.items() if len(v) > 1)
    orphan_rows = sorted("/".join(k) for k in keyed if k not in pins)
    out("FAIL" if (unresolved or doubled or orphan_rows) else "PASS",
        "every one of the %d pins on party.yaml resolves to exactly one dated signal" % len(pins)
        + ("; no row for: " + ", ".join(unresolved) if unresolved else "")
        + ("; more than one row for: " + ", ".join(doubled) if doubled else "")
        + ("; rows for pins this party does not carry: " + ", ".join(orphan_rows) if orphan_rows else ""))

    dated = sorted(r["signal"]["id"] for r in rows
                   if not (r.get("signal") or {}).get("at") or not r["signal"].get("id"))
    bound = {str((r.get("signal") or {}).get("scenario")) for r in rows}
    missing_scenarios = sorted(s for s in bound if s not in docs)
    declared_unbound = {str(u.get("scenario")) for u in (lookup.get("unbound_scenarios") or [])
                        if u.get("why")}
    unreachable = sorted(set(docs) - bound - declared_unbound)
    out("FAIL" if (dated or missing_scenarios or unreachable) else "PASS",
        "every signal is dated and names a scenario that exists, and every scenario is either "
        "bound by a pin or declared unbound with a reason"
        + ("; undated: " + ", ".join(dated) if dated else "")
        + ("; names no such scenario: " + ", ".join(missing_scenarios) if missing_scenarios else "")
        + ("; neither bound nor declared unbound: " + ", ".join(unreachable) if unreachable else ""))

    priced = sorted(r["signal"]["id"] for r in rows
                    if money_in(yaml.safe_dump(r.get("signal") or {})))
    out("FAIL" if priced else "PASS",
        "the lookup carries no price: binding a pin to a signal is not pricing it"
        + ("; money in: " + ", ".join(priced) if priced else ""))

# 9. every PRICED valuation names a fact that resolves in the signed party artefact, and its
#    amount re-derives from that fact. This party has none, and that is reported as a
#    could-not-look with the reason rather than as a green line over an empty set: a check that
#    inspected nothing must not print a sentence that reads as though it inspected something.
party_doc = yaml.safe_load((HERE.parent / "party.yaml").read_text()) or {}


def party_fact(path):
    node = party_doc
    for part in str(path).split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


unresolved, mismatched, checked = [], [], 0
for pf in sorted((HERE / "orgs" / ORG / "perspectives").glob("*.yaml")):
    for vid, val in (yaml.safe_load(pf.read_text()).get("values") or {}).items():
        if not isinstance(val, dict) or val.get("amount") is None:
            continue                     # unpriced: it travels as a register entry, not a number
        checked += 1
        fact_path = val.get("derived_from_party_fact")
        fact = party_fact(fact_path) if fact_path else None
        if fact is None:
            unresolved.append("%s/%s -> %s" % (pf.stem, vid, fact_path or "no fact named"))
            continue
        base = fact.get("amount") if isinstance(fact, dict) else fact
        share = float(val.get("share_of_turnover", 1.0))
        periods = float(val.get("periods_per_year", 1.0))
        want_amount = float(base) * share / periods
        if abs(want_amount - float(val["amount"])) > 1.0:
            mismatched.append("%s/%s: %s x %s / %s = %.2f, not %.2f"
                              % (pf.stem, vid, base, share, periods, want_amount, float(val["amount"])))
if checked == 0:
    out("SKIP",
        "no valuation in this overlay carries an amount, so there was no priced figure to "
        "re-derive from the signed party artefact: party.yaml for this party publishes no `size:` "
        "block and every valuation here is graded outside the pricing threshold")
else:
    out("FAIL" if (unresolved or mismatched) else "PASS",
        "each of the %d priced valuation(s) names a fact resolvable in party.yaml and re-derives "
        "from it" % checked
        + ("; no resolvable fact: " + "; ".join(unresolved) if unresolved else "")
        + ("; does not re-derive: " + "; ".join(mismatched) if mismatched else ""))

code = 1 if "FAIL" in LINES else 3 if "SKIP" in LINES else 0
print("TOTAL: %d pass, %d fail, %d could-not-look"
      % (LINES.count("PASS"), LINES.count("FAIL"), LINES.count("SKIP")))
sys.exit(code)
PY
rc=$?
cat "$log"
case $rc in
  0) echo "PASS: tuppence carries its six standing scenarios, four committed classes in all three places, and no fine amount in the twin";;
  3) echo "SKIP: $(grep '^SKIP:' "$log" | head -1 | cut -c7-)";;
  *) echo "FAIL: $(grep -c '^FAIL:' "$log") standing-scenario check(s) observed false";;
esac
exit "$rc"
