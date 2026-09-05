#!/usr/bin/env bash
# Beat: "tuppence's twin loads its own overlay, says whose money and in which currency, prices no
# rung it has not authored a response for -- and refuses to emit a forward-intel feed, naming the
# instruments it does not have, rather than inventing a number."
#
# Offline. Eco-system ticket 64, the shape ticket 29 built for driftwood; ADR-0019/0020/0021;
# overlay floor from ticket 11 answer item 2.
# Three outcomes only:
#   PASS (exit 0)  every assertion observed true
#   FAIL (exit 1)  an assertion observed false
#   SKIP (exit 3)  could not look, with the reason on the last line
#
# THIS SCRIPT ENDS AT COULD-NOT-LOOK TODAY, ON PURPOSE. The emitter refuses (exit 3) because this
# party publishes no signed `size:` and its one causal edge to the declared cash flow is graded 3,
# outside the ladder's path admission threshold. Every offline assertion around that refusal is
# still made and still graded; the refusal itself is reported as a could-not-look with its own
# reason on the last line, because a run that observed no feed must not print a line saying one
# was emitted. See twin/VENDORED.md.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORG="tuppence"

# The same contract as scripts/lib.sh: absence is never a pass.
skip() { echo "SKIP: $*"; exit 3; }

# The `twin` package renders the overlay and is not vendored: the tag is not cut yet, so there is
# nothing for this repo to pin (twin/PIN.yaml, twin/VENDORED.md). Find the checkout that has it.
HUB=""
d="$HERE"
while [ "$d" != "/" ]; do
  [ -f "$d/twin/repo.py" ] && [ -f "$d/clone-estate.sh" ] && { HUB="$d"; break; }
  d="$(dirname "$d")"
done
[ -n "$HUB" ] || skip "no checkout of the twin package above $HERE; the overlay cannot be rendered"

PY="$HUB/.venv/bin/python"
if [ ! -x "$PY" ]; then
  PY=python3
  "$PY" -c 'import jsonschema, yaml' 2>/dev/null \
    || skip "no $HUB/.venv and python3 lacks jsonschema/pyyaml"
fi

command -v git >/dev/null 2>&1 || skip "git is needed to stage the overlay's deterministic mirror"

log="$(mktemp)"
HUB="$HUB" HERE="$HERE" ORG="$ORG" "$PY" - >"$log" 2>&1 <<'PY'
import json, os, re, subprocess, sys

HUB, HERE, ORG = os.environ["HUB"], os.environ["HERE"], os.environ["ORG"]
sys.path.insert(0, HUB)
import yaml

LINES = []
def out(status, msg):
    LINES.append(status)
    print("%s: %s" % (status, msg))

TWIN = os.path.join(HERE, "twin")
EMIT = os.path.join(TWIN, "emit-forward-intel.py")
VENDORED = os.path.join(TWIN, "forward-intel", "payload.schema.json")
CANONICAL = os.path.join(HERE, "..", "platform", "feeds", "forward-intel.payload.schema.json")
OVERLAY = os.path.join(TWIN, "orgs", ORG)

# 1. the emitter's own verdict, consumed rather than re-derived. Exit 3 is could-not-look with the
#    reason on its own line; exit 0 means a feed exists and re-renders byte-identically; anything
#    else is observed false. Re-implementing the refusal here would let this script pass while the
#    emitter failed, which is the shape ticket 64 exists to end one level up.
r = subprocess.run([sys.executable, EMIT, "--check"], capture_output=True, text=True)
said = (r.stdout + r.stderr).strip().replace("\n", " | ")
if r.returncode == 0:
    out("PASS", "the overlay loads and re-renders twin/forward-intel/v1/feed.json byte-identically")
elif r.returncode == 3:
    out("SKIP", "the emitter could not look: " + said)
else:
    out("FAIL", "emit-forward-intel.py --check: " + said)

# 2. the vendored payload schema is the platform's canonical one, byte for byte. Checked even
#    though nothing is emitted: the schema a feed WILL be validated against is a pin like any
#    other, and finding it drifted on the day the first feed is emitted is finding it late.
if os.path.isfile(CANONICAL):
    same = open(CANONICAL, "rb").read() == open(VENDORED, "rb").read()
    out("PASS" if same else "FAIL",
        "vendored payload schema %s platform/feeds/forward-intel.payload.schema.json"
        % ("is byte-identical to" if same else "DIFFERS from"))
else:
    out("SKIP", "platform/feeds/forward-intel.payload.schema.json is not in this estate yet, so "
                "the vendored copy could not be compared to its canonical home")

# 3. whose money, in which currency -- checked against the signed party artefact.
party = yaml.safe_load(open(os.path.join(HERE, "party.yaml")))
reporting = str(party.get("reporting_currency", "USD"))
declared = yaml.safe_load(open(os.path.join(TWIN, "currency.yaml")))["perspectives"]
persp = yaml.safe_load(open(os.path.join(OVERLAY, "perspectives", ORG + ".yaml")))

out("PASS" if persp.get("party") == "employer" else "FAIL",
    "perspective %r is party=%r (the overlay floor needs one employer seat)" % (ORG, persp.get("party")))
out("PASS" if declared.get(ORG) == reporting else "FAIL",
    "perspective currency %r and party.yaml reporting_currency %r agree"
    % (declared.get(ORG), reporting))
out("PASS" if ORG == party["party"] else "FAIL",
    "this overlay names the party whose balance sheet it is (%r)" % party["party"])

# 4. the overlay floor: a caged workload, a pinned policy line, regulated data, roles, and the
#    causal edge that reaches the declared cash flow -- with its grade REPORTED, not assumed.
comp_dir = os.path.join(OVERLAY, "components")
comps = {}
for f in sorted(os.listdir(comp_dir)):
    doc = yaml.safe_load(open(os.path.join(comp_dir, f)))
    comps[doc["id"]] = doc
FLOOR = {"payments-api": "the caged workload", "cage-policy-line": "the pinned policy line",
         "customer-account-records": "the regulated data",
         "payment-fee-income": "the declared cash flow"}
missing = [f"{c} ({w})" for c, w in sorted(FLOOR.items())
           if c not in comps or "evolution" not in comps[c] or "visibility" not in comps[c]]
out("FAIL" if missing else "PASS",
    "overlay floor: 4 positioned components" + ("; missing or unpositioned: " + ", ".join(missing) if missing else ""))

people = sorted(os.listdir(os.path.join(OVERLAY, "people")))
out("PASS" if people else "FAIL", "overlay floor: %d role(s) declared as people" % len(people))

edge_dir = os.path.join(OVERLAY, "edges")
edges = [yaml.safe_load(open(os.path.join(edge_dir, f))) for f in sorted(os.listdir(edge_dir))]
from twin import evidence  # the published ladder, not a number copied into this script
admits = evidence.admission_threshold()
cash_flow = persp["cash_flow"][0]
reaching = [e for e in edges if e.get("type") == "influences" and e["to"] == cash_flow]
graded = [e for e in reaching if int(e["evidence_grade"]) <= admits]
out("PASS" if len(reaching) == 1 else "FAIL",
    "overlay floor: %d causal edge(s) reach the declared cash flow %r (this payload prices one "
    "shock, so exactly one is what the emitter needs)" % (len(reaching), cash_flow))
if len(reaching) == 1 and not graded:
    out("SKIP",
        "the one causal edge to %r (%s) is graded %d, outside the ladder's path admission "
        "threshold of %d, so no impact may enter this perspective's pound through it: this "
        "institution has no dated incident of its own and the elasticity is arithmetic on a "
        "comparable firm's published regulatory record"
        % (cash_flow, reaching[0]["id"], int(reaching[0]["evidence_grade"]), admits))
else:
    out("PASS" if len(graded) == 1 else "FAIL",
        "overlay floor: %d graded causal edge(s) reaching %r at or inside the admission threshold "
        "(%d)" % (len(graded), cash_flow, admits))

# 5. the perspective's valuation on the declared cash flow. An amount is admitted only inside the
#    pricing threshold, and the absence of one here is REPORTED as a could-not-look with the
#    reason, never as a pass. `derived_from_party_fact` is checked when an amount exists.
valuation = (persp.get("values") or {}).get(cash_flow) or {}
grade = valuation.get("evidence_grade")
if "amount" in valuation:
    fact = valuation.get("derived_from_party_fact")
    node, ok = party, bool(fact)
    for part in str(fact or "").split("."):
        node = node.get(part) if isinstance(node, dict) else None
    out("PASS" if (ok and node is not None) else "FAIL",
        "the priced valuation on %r names a fact that resolves in the signed party artefact (%r)"
        % (cash_flow, fact))
else:
    out("SKIP",
        "the perspective's valuation on %r carries no amount (grade %s, outside the pricing "
        "threshold of %d): party.yaml for this party publishes no signed `size:` block, so there "
        "is no signed fact for an amount to derive from and the twin's own valuation schema "
        "refuses a figure at this grade" % (cash_flow, grade, evidence.threshold()))

# 6. the ladder. Declared in twin/ladder.yaml because this repository ships no selection-policy
#    package; checked against platform's own graded/cage.py when a checkout is present, and never
#    treated as agreed when one is not.
ladder = yaml.safe_load(open(os.path.join(TWIN, "ladder.yaml")))
rungs = [str(x) for x in ladder["rungs"]]
resp_dir = os.path.join(OVERLAY, "responses")
priced = {yaml.safe_load(open(os.path.join(resp_dir, f)))["id"] for f in sorted(os.listdir(resp_dir))}
unpriced = [t for t in rungs if ("run-the-payments-api-at-%s" % t) not in priced]
out("FAIL" if unpriced else "PASS",
    "every declared rung %s is priced by a response in this overlay" % rungs
    + ("; no response for: " + ", ".join(unpriced) if unpriced else ""))

cage = os.path.join(HERE, "..", "platform", "graded", "cage.py")
if os.path.isfile(cage):
    src = open(cage).read()
    m = re.search(r"^ORDER\s*=\s*[\(\[]([^)\]]*)[\)\]]", src, re.M)
    published = [s.strip().strip("\"'") for s in m.group(1).split(",") if s.strip()] if m else None
    if published is None:
        out("SKIP", "platform/graded/cage.py declares no ORDER tuple this script can read, so the "
                    "declared ladder could not be compared to the published one")
    else:
        out("PASS" if published == rungs else "FAIL",
            "twin/ladder.yaml's rungs %s are platform's own published ladder %s" % (rungs, published))
else:
    out("SKIP", "platform/graded/cage.py is not in this estate, so twin/ladder.yaml's rungs could "
                "not be compared to the release that published them")

# 7. the twin never picks. Grepped over the whole overlay rather than an emitted payload, because
#    there is no payload: an action-shaped key authored into a response or a scenario would reach
#    the feed the day one is emitted, and finding it then is finding it late.
ACTION = re.compile(r"recommend|advice|advis|verdict|remediat|next.?step", re.I)
offenders = []
for base, _, names in os.walk(OVERLAY):
    for name in sorted(names):
        if not name.endswith((".yaml", ".yml")):
            continue
        doc = yaml.safe_load(open(os.path.join(base, name)))
        stack = [(doc, name)]
        while stack:
            node, path = stack.pop()
            if isinstance(node, dict):
                for k, v in node.items():
                    if ACTION.search(str(k)):
                        offenders.append("%s.%s" % (path, k))
                    stack.append((v, "%s.%s" % (path, k)))
            elif isinstance(node, list):
                stack.extend((v, path) for v in node)
out("FAIL" if offenders else "PASS",
    "no action-shaped key anywhere in the overlay" + ("; found " + ", ".join(sorted(offenders)) if offenders else ""))

# 8. NO discovery record for a feed nobody emitted. The inverse of driftwood's check 8, and it is
#    an assertion rather than an omission: ADR-0019 point 5 makes publishes[] the only discovery
#    record there is, so a record pointing at a path with no feed in it would resolve to nothing.
entry = next((e for e in party.get("publishes") or []
              if e.get("kind") == "feed" and e.get("name") == "forward-intel"), None)
emitted = os.path.isfile(os.path.join(TWIN, "forward-intel", "v1", "feed.json"))
if emitted:
    problems = []
    if entry is None:
        problems.append("a feed is emitted and party.yaml declares no publishes[] record for it")
    out("FAIL" if problems else "PASS", "; ".join(problems) or "publishes[] declares the emitted feed")
else:
    out("PASS" if entry is None else "FAIL",
        "no forward-intel feed is emitted and party.yaml declares no publishes[] record for one"
        + ("" if entry is None else "; publishes[] points at %r and nothing is there" % entry.get("path")))

# 9. the refusals actually bite. Planted in a throwaway copy, never against the real files. Under
#    the hub rather than in /tmp because the emitter finds the twin package by walking up, and a
#    plant that refused for the wrong reason would prove nothing. Directly under the hub, not
#    under .estate-clone/, so no estate-wide glob ever sees it.
import shutil, tempfile
plant_root = tempfile.mkdtemp(prefix=".plant-", dir=HUB)
try:
    def planted(label, mutate, expect, prefix="REFUSED"):
        """One violation, in isolation, in a fresh copy -- and it must be refused for the reason
        planted, not for a leftover from the previous plant."""
        plant = os.path.join(plant_root, ORG)
        shutil.rmtree(plant, ignore_errors=True)
        os.makedirs(plant)
        for item in ("twin", "party.yaml"):
            src, dst = os.path.join(HERE, item), os.path.join(plant, item)
            (shutil.copytree if os.path.isdir(src) else shutil.copy2)(src, dst)
        mutate(plant)
        p = subprocess.run([sys.executable, os.path.join(plant, "twin", "emit-forward-intel.py")],
                           capture_output=True, text=True)
        told = (p.stdout + p.stderr).strip().splitlines()
        why = told[-1] if told else ""
        ok = p.returncode != 0 and why.startswith(prefix) and expect in why
        out("PASS" if ok else "FAIL",
            "planted %s -> %s" % (label, why[:140] or "was NOT refused"))

    planted("a perspective valuing in a currency the party does not report in",
            lambda p: open(os.path.join(p, "twin", "currency.yaml"), "a").write(
                "\n# planted\nperspectives: {%s: USD}\n" % ORG),
            "values in USD and party.yaml reports in %s" % reporting)

    planted("a world_ref that no longer describes the vendored bytes",
            lambda p: open(os.path.join(p, "twin", "world", "meta.yaml"), "a").write(
                "description: planted, so the vendored bytes no longer stage to this pin\n"),
            "does not describe the bytes beside it")

    planted("a ladder rung the overlay prices no response for",
            lambda p: os.remove(os.path.join(p, "twin", "orgs", ORG, "responses",
                                             ("run-the-payments-api-at-%s" % "quarantine") + ".yaml")),
            "declares rung(s) 'quarantine'")

    planted("a twin release PIN.yaml does not pin",
            lambda p: open(os.path.join(p, "twin", "PIN.yaml"), "a").write(
                "\ntwin_version: 9.9.9\n"),
            "pins twin 9.9.9")
finally:
    shutil.rmtree(plant_root, ignore_errors=True)

code = 1 if "FAIL" in LINES else 3 if "SKIP" in LINES else 0
print("TOTAL: %d pass, %d fail, %d could-not-look"
      % (LINES.count("PASS"), LINES.count("FAIL"), LINES.count("SKIP")))
sys.exit(code)
PY
rc=$?
cat "$log"
case $rc in
  0) echo "PASS: tuppence's twin overlay loads, is labelled, prices every rung it declares and emits its feed";;
  3) echo "SKIP: $(grep '^SKIP:' "$log" | head -1 | cut -c7-)";;
  *) echo "FAIL: $(grep -c '^FAIL:' "$log") twin-overlay check(s) observed false";;
esac
rm -f "$log"
exit "$rc"
