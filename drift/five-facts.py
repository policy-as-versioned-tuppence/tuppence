#!/usr/bin/env python3
"""The five-fact sample: is tuppence's composed policy set in force, from signed sources?

Ecosystem ticket 40, from ticket 16 answer items Q1, Q2, Q3 and Q5, under ADR-0023 (D1, D3).
The pre-registration -- the five facts, the three falsifiers, the coverage floor -- is
`drift/window.yaml`, section `five_fact_sample`, and it was committed before this file took its
first sample. This module is the instrument, not the conclusion.

    five-facts.py sample [--context CTX] [--cluster NAME] [--ref REF] [--out PATH|-]
    five-facts.py grade  [--samples PATH] [--max-age-hours H]
    five-facts.py selfcheck

`sample` writes ONE JSON record PER SOURCE. `grade` reads the latest complete sample and returns
the verify-script contract: 0 every fact observed true, 3 could not look, 1 a fact observed false.

## The five facts

  1. the GitRepository is Ready at the pinned {tag, commit} AND its url is the publisher's real
     remote;
  2. the tag signature is verified at the source boundary;
  3. the Kustomization's lastAppliedRevision equals that commit (for platform and nist, which are
     verified sources only, the pinned commit equals composed/HEADER.yaml's parent sha -- the
     revision the composed set in force was actually built from);
  4. every rendered policy object is live and byte-equal to an offline render;
  5. every such object is in the Flux inventory.

Facts 1 to 3 are per source. Facts 4 and 5 are properties of THE COMPOSED SET, which is one thing
where the sources are three, so every record carries the same values for them with
`"scope": "the composed set"` on the fact. Recorded plainly rather than repeated as though three
independent observations had been made.

Each fact is `{"observed": true | false | null, ...}`. `null` is could-not-look and is NEVER a
pass -- neither here nor in `grade`.

## What this log holds

`drift/samples.jsonl` in this repository carries five-fact records and nothing else --
tuppence has no build-ticket-64 drift probe, so there is no second instrument sharing the
path. Every record still carries `kind`, `ts` and `reachable`, the shape ADR-0023's
observation lane names, so the hub's schedules verifier parses this log like any other.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "scripts"))
import render_composed as rc  # noqa: E402


def _org() -> str:
    """This party's own name, read from party.yaml -- never typed twice and never
    guessed from a directory name that a checkout can rename."""
    with open(os.path.join(REPO, "party.yaml")) as fh:
        return str((yaml.safe_load(fh) or {})["party"])


ORG = _org()
SAMPLES = os.path.join(HERE, "samples.jsonl")
WINDOW = os.path.join(HERE, "window.yaml")
KIND = "flux.five-facts/v1"
SCHEMA_VERSION = 1

FACT_IDS = (
    "fact_1_ready_at_the_pin_on_the_real_remote",
    "fact_2_tag_signature_verified_at_the_source_boundary",
    "fact_3_last_applied_revision_equals_the_pinned_commit",
    "fact_4_rendered_objects_byte_equal_to_an_offline_render",
    "fact_5_every_rendered_object_is_in_the_flux_inventory",
)
FALSIFIER_IDS = (
    "verified_source_ready_but_the_object_is_absent_or_unequal_and_unhealed",
    "cluster_side_verification_passes_a_tag_that_identity_pinned_ci_rejects",
    "coverage_below_the_floor_at_close_recorded_unmeasured",
)

REAL_REMOTE = re.compile(r"^https://github\.com/policy-as-versioned-([a-z0-9-]+)/([a-z0-9-]+)$")

# The gitsign-verifying controller's annotation contract (platform identity/gitsign-verifier).
ANN = "policy-as-versioned.dev/"
ACTIONS_ISSUER = "https://token.actions.githubusercontent.com"

# The observation lane's own identity, as .github/workflows/drift-sample.yml sets it. A line
# committed by anyone else is a rehearsal (ADR-0023, D4) and is never graded PASS.
SAMPLER_EMAIL = f"drift-sample@policy-as-versioned-{ORG}.invalid"


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fact(observed, why: str, **extra) -> dict:
    return {"observed": observed, "why": why, **extra}


# --- reading the pins out of the tree ----------------------------------------
def _yaml_docs(path: str) -> list[dict]:
    with open(path) as fh:
        return [d for d in yaml.safe_load_all(fh) if isinstance(d, dict)]


def _gitrepo(path: str, name: str) -> dict:
    for doc in _yaml_docs(path):
        if doc.get("kind") == "GitRepository" and doc["metadata"]["name"] == name:
            return doc
    raise KeyError(f"{path} declares no GitRepository/{name}")


def header_parents() -> dict[str, dict]:
    """composed/HEADER.yaml's pinned parents, keyed by party."""
    with open(os.path.join(REPO, "composed", "HEADER.yaml")) as fh:
        doc = yaml.safe_load(fh) or {}
    return {p["party"]: p for p in (doc.get("parents") or []) if p.get("kind") != "feed"}


def sources() -> list[dict]:
    """The sources this sample grades, read from the checked-in tree and never typed here.

    tuppence-composed is the adopter's own signed tag, which is what the ResourceSet installs.
    platform and nist stay VERIFIED SOURCES ONLY (ticket 16 Q5): nothing on the cluster reconciles
    their trees, so their fact 3 is the HEADER parent sha instead of an applied revision.
    """
    gitops = os.path.join(REPO, "gitops")
    parents = header_parents()
    out = []
    for name, path, party, consumer in (
        (f"{ORG}-composed", "composed/composed-set.yaml", ORG, "resourceset"),
        ("platform", "platform/platform-pin.yaml", "platform", "verified-source-only"),
        ("nist", "flux-system/gotk-sync-nist.yaml", "nist", "verified-source-only"),
    ):
        full = os.path.join(gitops, path)
        if not os.path.exists(full):
            continue
        doc = _gitrepo(full, name)
        ref = doc["spec"].get("ref") or {}
        out.append({
            "source": name,
            "party": party,
            "consumer": consumer,
            "pin_from": f"gitops/{path}",
            "url": doc["spec"].get("url", ""),
            "tag": str(ref.get("tag", "")),
            "commit": str(ref.get("commit", "")),
            "verify_declared": bool(doc["spec"].get("verify")),
            "header_parent_sha": (parents.get(party) or {}).get("sha", ""),
        })
    return out


def ci_identity() -> dict:
    """The identity CI pins for tuppence's own tags. Falsifier 2 compares what the cluster
    verified against to this; a cluster that verifies a tag this rejects is the falsifier firing."""
    path = os.path.join(REPO, ".github", "workflows", "release.yml")
    found = {"regexp": "", "issuer": ""}
    try:
        with open(path) as fh:
            for line in fh:
                for key, name in (("regexp", "EXPECTED_IDENTITY_REGEXP"), ("issuer", "EXPECTED_ISSUER")):
                    match = re.match(rf"^\s*{name}:\s*(\S+)\s*$", line)
                    if match:
                        found[key] = match.group(1)
    except OSError:
        pass
    return found


# --- looking at the cluster ---------------------------------------------------
class Cluster:
    """Every read of the API server, and the record of whether it answered at all."""

    def __init__(self, context: str):
        self.context = context
        self.reachable = None
        self.reason = ""

    def get(self, *args: str) -> dict | None:
        cmd = ["kubectl", "--context", self.context, "--request-timeout=20s", *args, "-o", "json"]
        try:
            done = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.SubprocessError) as e:
            self.reachable, self.reason = False, f"kubectl could not run: {e}"
            return None
        if done.returncode != 0:
            err = (done.stderr or "").strip().splitlines()[-1:] or [""]
            if "not found" not in err[0] and "NotFound" not in err[0]:
                if self.reachable is None:
                    self.reachable, self.reason = False, f"context {self.context}: {err[0]}"
                return None
            self.reachable = True if self.reachable is None else self.reachable
            return None
        self.reachable = True
        try:
            return json.loads(done.stdout)
        except json.JSONDecodeError:
            return None


def condition(obj: dict, kind: str) -> dict:
    for c in ((obj.get("status") or {}).get("conditions") or []):
        if c.get("type") == kind:
            return c
    return {}


def inventory_ids(cluster: Cluster) -> dict[str, str]:
    """{inventory id: the Flux object that claims it}. This is the fact-5 evidence and the reason
    fact 5 is a fact of its own: five hand-applied ValidatingPolicies with the right names already
    sit on kind-tuppence, and no inventory anywhere lists them."""
    found: dict[str, str] = {}
    for resource in ("kustomizations.kustomize.toolkit.fluxcd.io", "resourcesets.fluxcd.controlplane.io"):
        listing = cluster.get("-n", "flux-system", "get", resource)
        for item in (listing or {}).get("items", []):
            owner = f"{item['kind']}/{item['metadata']['name']}"
            for entry in ((item.get("status") or {}).get("inventory") or {}).get("entries", []) or []:
                found[str(entry.get("id"))] = owner
    return found


def inventory_id(obj: dict) -> str:
    """Flux's inventory id: `namespace_name_group_Kind`, namespace and group empty when absent."""
    meta = obj.get("metadata") or {}
    group = obj.get("apiVersion", "").rsplit("/", 1)[0] if "/" in obj.get("apiVersion", "") else ""
    return f"{meta.get('namespace', '')}_{meta.get('name', '')}_{group}_{obj.get('kind')}"


def gitsign_verifies(tag: str, identity: dict) -> tuple[bool | None, str]:
    """The CI half of falsifier 2, run for real where gitsign is on PATH."""
    if not identity["regexp"] or not identity["issuer"]:
        return None, "release.yml declares no EXPECTED_IDENTITY_REGEXP/EXPECTED_ISSUER to pin against"
    try:
        done = subprocess.run(
            ["gitsign", "verify-tag", tag,
             f"--certificate-identity-regexp={identity['regexp']}",
             f"--certificate-oidc-issuer={identity['issuer']}"],
            cwd=REPO, capture_output=True, text=True, timeout=120,
            env={**os.environ, "GITSIGN_REKOR_MODE": "offline"})
    except (OSError, subprocess.SubprocessError) as e:
        return None, f"gitsign could not run ({e}); the identity-pinned half of falsifier 2 was not looked at"
    if done.returncode == 0:
        return True, f"gitsign verify-tag {tag} accepted the tag against the identity release.yml pins"
    tail = (done.stderr or done.stdout or "").strip().splitlines()[-1:] or [""]
    return False, f"gitsign verify-tag {tag} REJECTED the tag: {tail[0]}"


# --- the composed set (facts 4 and 5) -----------------------------------------
def composed_set_facts(cluster: Cluster, ref: str | None) -> tuple[dict, dict, list[str]]:
    declared = rc.render(ref)
    if not declared:
        why = "the offline render of composed/ produced no objects"
        return fact(None, why), fact(None, why), []
    inventory = inventory_ids(cluster)
    unequal, absent, uninventoried, checked = [], [], [], []
    for k, obj in sorted(declared.items()):
        obj = {kk: vv for kk, vv in obj.items() if kk != "_source_path"}
        kind, name = obj["kind"], obj["metadata"]["name"]
        # SINGULAR kind, qualified by the DECLARED group AND version:
        # `mutatingpolicy.v1alpha1.policies.kyverno.io`. Two things this gets right that the
        # obvious spellings do not -- naive pluralisation (`mutatingpolicys`) resolves to nothing
        # and made every object read as absent from a cluster that was holding it, and asking
        # without a version returns the server's PREFERRED version, so a policy declared at
        # v1alpha1 came back as v1 and read as drift when the only difference was API version
        # negotiation.
        version = obj["apiVersion"].rsplit("/", 1)[-1]
        group = obj["apiVersion"].rsplit("/", 1)[0] if "/" in obj["apiVersion"] else ""
        resource = ".".join(x for x in (kind.lower(), version, group) if x)
        live = cluster.get("get", resource, name)
        if live is None:
            absent.append(k)
            continue
        verdict = rc.compare(obj, live)
        checked.append(k)
        if not verdict["declared_equal"]:
            unequal.append({"object": k, "differences": verdict["differences"],
                            "strict_equal": verdict["strict_equal"]})
        if inventory_id(obj) not in inventory:
            uninventoried.append(k)
    total = len(declared)
    f4 = fact(
        not absent and not unequal,
        (f"all {total} rendered objects are live and equal to the offline render"
         if not absent and not unequal else
         f"{len(absent)} of {total} rendered objects are absent from the cluster and "
         f"{len(unequal)} are live but unequal to the offline render"),
        scope="the composed set", objects_declared=total, objects_absent=absent,
        objects_unequal=unequal,
        rendered_from=ref or "the working tree",
        ceiling="declared_equal, not byte identity: the API server defaults fields the render "
                "never declared. strict_equal is recorded per unequal object.")
    f5 = fact(
        not absent and not uninventoried,
        (f"all {total} rendered objects appear in a Flux inventory"
         if not absent and not uninventoried else
         f"{len(uninventoried) + len(absent)} of {total} rendered objects are in no Flux "
         f"inventory (absent from the cluster, or live but put there by something other than "
         f"Flux)"),
        scope="the composed set", objects_not_in_inventory=sorted(set(uninventoried) | set(absent)),
        inventory_entries=len(inventory))
    return f4, f5, [u["object"] for u in unequal] + absent


# --- the sample ---------------------------------------------------------------
def take_sample(context: str, cluster_name: str, ref: str | None) -> list[dict]:
    cluster = Cluster(context)
    stamp = now()
    run = os.environ.get("GITHUB_RUN_ID", "")

    revision = ""
    top = cluster.get("-n", "flux-system", "get", "kustomization", ORG)
    if top:
        revision = str((top.get("status") or {}).get("lastAppliedRevision", ""))
    if cluster.reachable is None:
        # Nothing above may have touched the API server (a missing Kustomization reads as
        # NotFound, which is an answer, not a failure to reach). Ask something that always
        # exists, so `reachable` is an observation and not an assumption.
        cluster.get("get", "ns", "kube-system")

    f4, f5, unhealed = composed_set_facts(cluster, ref) if cluster.reachable else (
        fact(None, "the cluster did not answer"), fact(None, "the cluster did not answer"), [])

    identity = ci_identity()
    kustomizations = cluster.get("-n", "flux-system", "get",
                                 "kustomizations.kustomize.toolkit.fluxcd.io") or {}
    records = []
    for src in sources():
        live = cluster.get("-n", "flux-system", "get", "gitrepository", src["source"]) if cluster.reachable else None
        records.append({
            "ts": stamp,
            "reachable": bool(cluster.reachable),
            "reason": "" if cluster.reachable else cluster.reason,
            "kind": KIND,
            "schema_version": SCHEMA_VERSION,
            "cluster": cluster_name,
            "context": context,
            "run": run,
            "revision": revision,
            "source": src["source"],
            "party": src["party"],
            "pin": {k: src[k] for k in ("url", "tag", "commit", "pin_from", "consumer")},
            "facts": _source_facts(src, live, kustomizations, identity, f4, f5),
            "falsifiers": _falsifier_state(src, live, identity, unhealed, kustomizations),
        })
    for record in records:
        record["verdict"] = _verdict(record["facts"])
    return records


def _source_facts(src, live, kustomizations, identity, f4, f5) -> dict:
    if live is None:
        gone = fact(False, f"no GitRepository/{src['source']} in flux-system on this cluster")
        return dict(zip(FACT_IDS, [gone, gone, _fact_three(src, kustomizations), f4, f5]))

    spec, ref = live.get("spec") or {}, (live.get("spec") or {}).get("ref") or {}
    ready = condition(live, "Ready").get("status")
    url = str(spec.get("url", ""))
    wrong = []
    if ready != "True":
        wrong.append(f"Ready={ready}")
    if url != src["url"]:
        wrong.append(f"url {url!r} is not the pin {src['url']!r}")
    if not REAL_REMOTE.match(url):
        wrong.append(f"url {url!r} is not a real remote of the form "
                     f"https://github.com/policy-as-versioned-<party>/<party>")
    if str(ref.get("tag", "")) != src["tag"]:
        wrong.append(f"tag {ref.get('tag')!r} is not the pin {src['tag']!r}")
    if src["commit"] and str(ref.get("commit", "")) != src["commit"]:
        wrong.append(f"commit {ref.get('commit')!r} is not the pin {src['commit']!r}")
    f1 = fact(not wrong,
              "Ready at the pinned tag and commit, from the publisher's real remote"
              if not wrong else "; ".join(wrong),
              live_url=url, live_tag=str(ref.get("tag", "")), live_commit=str(ref.get("commit", "")))

    return dict(zip(FACT_IDS, [f1, _fact_two(src, live, spec, identity),
                               _fact_three(src, kustomizations, live), f4, f5]))


def _identity_pin_wrong(party: str, regexp: str, ci: dict) -> str:
    """Empty when the regexp the cluster verified WITH is the publisher's own pinned identity.

    tuppence's own is release.yml's constant, read here. A parent's release.yml is not in this
    checkout, so what is checkable from here is the property that makes it a pin at all: anchored
    at both ends, and naming that publisher's own repository. An unanchored regexp matches a
    substring of any identity, which is not a pin.
    """
    if party == ORG and ci.get("regexp") and regexp != ci["regexp"]:
        return (f"the cluster verified with {regexp!r}, which is not the identity release.yml "
                f"pins ({ci['regexp']!r})")
    if not (regexp.startswith("^") and regexp.endswith("$")):
        return (f"the pinned identity regexp {regexp!r} is not anchored at both ends, so it "
                f"matches a substring of any identity and pins nothing")
    if f"policy-as-versioned-{party}/{party}" not in regexp.replace("\\", ""):
        return (f"the pinned identity regexp {regexp!r} does not name {party}'s own repository, "
                f"so the tag was verified against somebody else's workflow identity")
    return ""


def _fact_two(src, live, spec, identity) -> dict:
    """Fact 2 asks WITH WHAT the source boundary verified, not merely whether a boolean is True.

    Three states, and only one of them is a pass:
      * `spec.verify` -- an OpenPGP/SSH key re-signing the ref. ADR-0023 D3 forbids a second
        signer, so a source verified this way is observed FALSE however green the condition is;
      * no verdict at all -- nothing looked, so neither did this sample: null, never a pass;
      * the gitsign-verifying controller's annotations -- observed true only when it says true AND
        the identity and issuer it verified with are the publisher's own pins.
    """
    ann = (live.get("metadata") or {}).get("annotations") or {}
    verdict = ann.get(ANN + "gitsign-verified")
    regexp = str(ann.get(ANN + "gitsign-identity-regexp", ""))
    issuer = str(ann.get(ANN + "gitsign-issuer", ""))
    if spec.get("verify"):
        return fact(False,
                    "SourceVerified here comes from spec.verify, an OpenPGP or SSH key re-signing "
                    "the ref. ADR-0023 D3 allows one signature, the gitsign tag, and no second "
                    "signer under another name -- so whatever this verified, it is not the "
                    "publisher's signature",
                    cluster_verified_identity=spec["verify"], cluster_verified_with=None)
    if verdict is None:
        return fact(None,
                    "nothing checked a signature at this source boundary: the GitRepository "
                    "declares no spec.verify (Flux speaks OpenPGP and SSH only) and carries no "
                    "verdict from the identity-pinned gitsign-verifying controller (ticket 41). "
                    "Not looked at, and a thing not looked at is never a pass",
                    cluster_verified_identity=None, cluster_verified_with=None)
    if verdict == "unknown":
        return fact(None,
                    f"the gitsign-verifying controller could not look at {src['tag']}: "
                    f"{ann.get(ANN + 'gitsign-verify-reason', 'no reason recorded')}",
                    cluster_verified_identity=None, cluster_verified_with=regexp)
    wrong = []
    if verdict != "true":
        wrong.append(f"the controller's verdict is {verdict!r}: "
                     f"{ann.get(ANN + 'gitsign-verify-reason', 'no reason recorded')}")
    if issuer != ACTIONS_ISSUER:
        wrong.append(f"it verified against issuer {issuer!r}, not the Actions OIDC issuer "
                     f"{ACTIONS_ISSUER!r}")
    pin_wrong = _identity_pin_wrong(src["party"], regexp, identity)
    if pin_wrong:
        wrong.append(pin_wrong)
    return fact(not wrong,
                (f"the gitsign tag {src['tag']} was verified at the source boundary against "
                 f"{src['party']}'s own pinned identity {regexp}"
                 if not wrong else "; ".join(wrong)),
                cluster_verified_identity=None, cluster_verified_with=regexp,
                cluster_verified_issuer=issuer, controller_verdict=verdict)


def _fact_three(src, kustomizations, live=None) -> dict:
    """The revision actually in force, traced back to the pinned commit."""
    if src["consumer"] == "verified-source-only":
        parent = src["header_parent_sha"]
        if not parent:
            return fact(None, f"composed/HEADER.yaml pins no parent for {src['party']}")
        return fact(parent == src["commit"],
                    (f"{src['party']} is a verified source only (ticket 16 Q5): no Kustomization "
                     f"reconciles it, so the revision in force is the parent sha the composed set "
                     f"was built from. HEADER {parent[:12]} vs pin {src['commit'][:12]}"),
                    header_parent_sha=parent, pinned_commit=src["commit"])
    consumers = [k for k in kustomizations.get("items", [])
                 if ((k.get("spec") or {}).get("sourceRef") or {}).get("name") == src["source"]]
    if not consumers:
        return fact(False,
                    f"no Kustomization on this cluster reconciles GitRepository/{src['source']}, "
                    f"so no revision of it is applied at all")
    applied = {k["metadata"]["name"]: str((k.get("status") or {}).get("lastAppliedRevision", ""))
               for k in consumers}
    behind = {n: r for n, r in applied.items() if src["commit"] not in r}
    return fact(not behind,
                (f"every Kustomization consuming {src['source']} applied {src['commit'][:12]}"
                 if not behind else
                 f"{len(behind)} of {len(applied)} consuming Kustomizations applied a revision "
                 f"that is not the pinned commit {src['commit'][:12]}"),
                last_applied_revisions=applied)


def _falsifier_state(src, live, identity, unhealed, kustomizations) -> dict:
    """Per-record falsifier evidence. `fired` is true, false or null; `grade` decides across
    consecutive samples what one sample cannot see."""
    intervals = sorted({str((k.get("spec") or {}).get("interval", ""))
                        for k in kustomizations.get("items", [])} - {""})
    ready_and_verified = bool(live) and condition(live, "Ready").get("status") == "True"
    f1 = {
        "id": FALSIFIER_IDS[0],
        # One sample cannot see "unhealed": that needs N consecutive samples. This records the
        # evidence; `grade` walks the log and fires it.
        "fired": None,
        "source_ready": ready_and_verified,
        "objects_absent_or_unequal": sorted(set(unhealed)),
        "kustomization_intervals": intervals,
        "why": "unhealed is a property of consecutive samples; `five-facts.py grade` fires this "
               "one by walking the log against the live intervals above",
    }
    ann = ((live or {}).get("metadata") or {}).get("annotations") or {}
    cluster_verified = bool(live) and (
        condition(live, "SourceVerified").get("status") == "True"
        or ann.get(ANN + "gitsign-verified") == "true")
    if not cluster_verified:
        f2 = {"id": FALSIFIER_IDS[1], "fired": None,
              "why": "the cluster verified nothing at this source boundary, so there is no "
                     "cluster verdict for CI to disagree with (ticket 41 has not landed)",
              "ci_pinned_identity": identity}
    else:
        ok, why = gitsign_verifies(src["tag"], identity) if src["party"] == ORG else (
            None, f"{src['party']}'s own release.yml is not in this checkout, so the identity it "
                  f"pins cannot be read here")
        f2 = {"id": FALSIFIER_IDS[1], "fired": (ok is False), "ci_accepts": ok, "why": why,
              "ci_pinned_identity": identity}
    return {FALSIFIER_IDS[0]: f1, FALSIFIER_IDS[1]: f2}


def _verdict(facts: dict) -> str:
    values = [facts[f]["observed"] for f in FACT_IDS]
    if False in values:
        return "FAIL"
    return "PASS" if all(v is True for v in values) else "COULD-NOT-LOOK"


# --- grading ------------------------------------------------------------------
def _load(path: str) -> list[dict]:
    if not os.path.isfile(path):
        return []
    out = []
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                doc = json.loads(line)
            except json.JSONDecodeError:
                continue
            if doc.get("kind") == KIND:
                out.append(doc)
    return out


def _minutes(interval: str) -> float:
    match = re.fullmatch(r"(\d+)(s|m|h)", interval or "")
    if not match:
        return 0.0
    return int(match.group(1)) * {"s": 1 / 60, "m": 1.0, "h": 60.0}[match.group(2)]


def falsifiers_declared() -> list[str]:
    """Ticket 40: a sample that passes with a falsifier undeclared is a FAIL. Read, never assumed."""
    try:
        with open(WINDOW) as fh:
            doc = yaml.safe_load(fh) or {}
    except (OSError, yaml.YAMLError):
        return []
    return [str(f.get("id")) for f in
            ((doc.get("five_fact_sample") or {}).get("falsifiers") or [])]


def sample_provenance(path: str, group: list[dict]) -> str:
    """Empty when the newest sample is attributable to the observation lane; otherwise the one
    reason it is a rehearsal.

    ADR-0023 D4: "a sample taken by hand is a rehearsal that is never appended or cited". The
    docstring said so and nothing enforced it -- three lines typed into samples.jsonl with every
    fact `true` graded PASS (found 2026-08-29). Attribution is read, never trusted from the record:
    the run must be a GitHub Actions run id, and the commit that put the line in the file must be
    the lane's own signed commit.

    ponytail: %G? on a gitsign x509 signature needs `gpg.x509.program=gitsign` configured in the
    checkout doing the grading; where it is not, this returns a could-not-look reason rather than a
    pass, which is the right way round. Configure gitsign on the truth runner to close it.
    """
    typed = sorted({str(r.get("run") or "") for r in group
                    if not str(r.get("run") or "").isdigit()})
    if typed:
        return (f"the newest five-fact sample carries run={typed[0]!r}, which is not a GitHub "
                f"Actions run id -- it was not taken by the scheduled observation lane, and a "
                f"sample taken by hand is a rehearsal that is never cited (ADR-0023, D4)")

    def git(*args) -> str | None:
        try:
            done = subprocess.run(["git", "-C", REPO, *args], capture_output=True, text=True,
                                  timeout=30)
        except (OSError, subprocess.SubprocessError):
            return None
        return done.stdout.strip() if done.returncode == 0 else None

    dirty = git("status", "--porcelain", "--", path)
    if dirty is None:
        return ("drift/samples.jsonl is not inside a readable git checkout here, so the newest "
                "sample cannot be attributed to the observation lane")
    if dirty:
        return ("drift/samples.jsonl carries uncommitted edits, so its newest line is a "
                "working-tree rehearsal and not a lane commit")
    meta = git("log", "-1", "--format=%ae%n%G?", "--", path) or ""
    author, _, signature = meta.partition("\n")
    if not author:
        return "no commit in this checkout touches drift/samples.jsonl, so nothing attributes it"
    if author != SAMPLER_EMAIL:
        return (f"the last commit to drift/samples.jsonl was authored by {author}, not the "
                f"observation lane's {SAMPLER_EMAIL} -- a human edit is a rehearsal, not an "
                f"observation")
    if signature.strip() not in ("G", "U"):
        return (f"git could not verify the signature on that lane commit (%G? = "
                f"{signature.strip() or 'empty'!r}); an unverified lane commit is not an "
                f"attributable observation here")
    return ""


def grade(path: str, max_age_hours: float) -> tuple[int, list[str]]:
    lines: list[str] = []
    declared = falsifiers_declared()
    missing = [f for f in FALSIFIER_IDS if f not in declared]
    if missing:
        return 1, [f"FAIL: drift/window.yaml declares {len(declared)} of the three falsifiers; "
                   f"missing {missing[0]} -- a sample that passes with a falsifier undeclared is "
                   f"a fail (ticket 40)"]

    samples = _load(path)
    if not samples:
        return 3, ["SKIP: drift/samples.jsonl carries no five-fact sample yet -- "
                   ".github/workflows/drift-sample.yml has not run on the remote, and a sample "
                   "taken by hand is a rehearsal that is never appended or cited (ADR-0023, D4)"]

    latest = max(s["ts"] for s in samples)
    age = (dt.datetime.now(dt.timezone.utc)
           - dt.datetime.strptime(latest, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc))
    group = [s for s in samples if s["ts"] == latest]
    if age > dt.timedelta(hours=max_age_hours):
        return 3, [f"SKIP: the newest five-fact sample is {int(age.total_seconds() // 3600)}h old "
                   f"({latest}), older than the {max_age_hours:g}h freshness bound -- the "
                   f"scheduled sampler has stopped, and a stale sample is not an observation of "
                   f"the cluster now"]

    rehearsal = sample_provenance(path, group)
    if rehearsal:
        return 3, [f"SKIP: {rehearsal}"]

    lines.append(f"five-fact sample {latest} on cluster {group[0].get('cluster')} "
                 f"(run {group[0].get('run') or 'local'}), {len(group)} sources")
    verdict = 0
    for record in sorted(group, key=lambda r: r["source"]):
        for name in FACT_IDS:
            got = record["facts"][name]
            mark = {True: "true ", False: "FALSE", None: "?    "}[got["observed"]]
            lines.append(f"  {record['source']:<20} {mark} {name}: {got['why']}")
            if got["observed"] is False:
                verdict = max(verdict, 1)
            elif got["observed"] is None and verdict == 0:
                verdict = 3

    # Falsifier 1: unhealed across N samples spanning more than N intervals.
    fired = _falsifier_one(samples, group)
    if fired:
        lines.append(f"  FALSIFIER FIRED: {FALSIFIER_IDS[0]} -- {fired}")
        verdict = 1
    # Falsifier 2, per record. `fired: null` is could-not-look, not "did not fire": where the
    # cluster DID verify this source, a falsifier nobody ran is exactly the state that must never
    # ride along inside a PASS.
    for record in group:
        state = (record.get("falsifiers") or {}).get(FALSIFIER_IDS[1]) or {}
        if state.get("fired"):
            lines.append(f"  FALSIFIER FIRED: {FALSIFIER_IDS[1]} on {record['source']} -- "
                         f"{state.get('why')}")
            verdict = 1
        elif state.get("fired") is None and record["facts"][FACT_IDS[1]]["observed"] is True:
            lines.append(f"  FALSIFIER NOT LOOKED AT: {FALSIFIER_IDS[1]} on {record['source']} -- "
                         f"{state.get('why') or 'no evidence recorded'}")
            if verdict == 0:
                verdict = 3

    if verdict == 0:
        lines.append("PASS: all five facts observed true for every source; no falsifier fired")
    elif verdict == 3:
        lines.append("SKIP: a fact could not be looked at, and a fact not looked at is never a pass")
    else:
        lines.append("FAIL: a fact of the five-fact sample was observed false")
    return verdict, lines


def _falsifier_one(samples: list[dict], group: list[dict]) -> str:
    """N=3 consecutive samples with the same object absent-or-unequal, spanning more than N times
    the consuming Kustomization's own live interval. N and the interval source are declared in
    window.yaml; the interval is read from the sample, never typed here."""
    n = 3
    by_ts: dict[str, dict] = {}
    for s in samples:
        by_ts.setdefault(s["ts"], s)
    stamps = sorted(by_ts)[-n:]
    if len(stamps) < n:
        return ""
    def bad(ts):
        state = (by_ts[ts].get("falsifiers") or {}).get(FALSIFIER_IDS[0]) or {}
        return set(state.get("objects_absent_or_unequal") or []) if state.get("source_ready") else set()
    persistent = set.intersection(*(bad(ts) for ts in stamps))
    if not persistent:
        return ""
    intervals = [_minutes(i) for i in
                 ((group[0].get("falsifiers") or {}).get(FALSIFIER_IDS[0]) or {}).get(
                     "kustomization_intervals") or []]
    limit = n * max(intervals or [0])
    if not limit:
        return ""
    span = (dt.datetime.strptime(stamps[-1], "%Y-%m-%dT%H:%M:%SZ")
            - dt.datetime.strptime(stamps[0], "%Y-%m-%dT%H:%M:%SZ")).total_seconds() / 60
    if span <= limit:
        return ""
    return (f"{len(persistent)} object(s) absent or unequal in {n} consecutive samples spanning "
            f"{span:.0f} minutes, more than {n} x the live Kustomization interval ({limit:.0f} "
            f"minutes), while the source was Ready: {sorted(persistent)[:3]}")


# --- entry points -------------------------------------------------------------
def selfcheck() -> int:
    assert set(FALSIFIER_IDS) <= set(falsifiers_declared()), \
        "window.yaml must declare all three falsifiers before a sample is taken"
    assert _verdict({f: {"observed": True} for f in FACT_IDS}) == "PASS"
    assert _verdict({**{f: {"observed": True} for f in FACT_IDS},
                     FACT_IDS[2]: {"observed": None}}) == "COULD-NOT-LOOK", \
        "a could-not-look fact must never grade PASS"
    assert _verdict({**{f: {"observed": True} for f in FACT_IDS},
                     FACT_IDS[0]: {"observed": False}}) == "FAIL"
    assert _minutes("5m") == 5 and _minutes("1h") == 60 and _minutes("") == 0
    assert inventory_id({"apiVersion": "policies.kyverno.io/v1alpha1", "kind": "MutatingPolicy",
                         "metadata": {"name": "cage-tier-3-0-0"}}) \
        == "_cage-tier-3-0-0_policies.kyverno.io_MutatingPolicy"
    assert inventory_id({"apiVersion": "v1", "kind": "ConfigMap",
                         "metadata": {"name": "c", "namespace": "tuppence"}}) \
        == "tuppence_c__ConfigMap"
    assert REAL_REMOTE.match("https://github.com/policy-as-versioned-nist/nist")
    assert not REAL_REMOTE.match("http://git-server.flux-system.svc.cluster.local/cgi-bin/git/nist.git")
    assert [s["source"] for s in sources()], "no sources readable from the checked-in tree"

    # fact 2 grades WHAT the boundary verified with, not a bare boolean.
    ci = {"regexp": r"^https://github\.com/policy-as-versioned-tuppence/tuppence/x$",
          "issuer": ACTIONS_ISSUER}
    src = {"party": "tuppence", "tag": "v1.1.0"}
    def live_with(**ann):
        return {"metadata": {"annotations": {ANN + "gitsign-issuer": ACTIONS_ISSUER, **ann}}}
    good = {ANN + "gitsign-verified": "true", ANN + "gitsign-identity-regexp": ci["regexp"]}
    assert _fact_two(src, live_with(**good), {}, ci)["observed"] is True
    assert _fact_two(src, live_with(), {}, ci)["observed"] is None, \
        "no controller verdict is could-not-look, never observed false and never a pass"
    assert _fact_two(src, live_with(), {"verify": {"mode": "HEAD"}}, ci)["observed"] is False, \
        "a spec.verify key re-signing the ref is a second signer (ADR-0023 D3), not a pass"
    attacker = {ANN + "gitsign-verified": "true",
                ANN + "gitsign-identity-regexp": r"^https://github\.com/someone-else/x$"}
    assert _fact_two(src, live_with(**attacker), {}, ci)["observed"] is False, \
        "a verdict reached with somebody else's identity is not this publisher's signature"
    loose = {ANN + "gitsign-verified": "true", ANN + "gitsign-identity-regexp": ".*"}
    assert _fact_two(src, live_with(**loose), {}, ci)["observed"] is False, \
        "an unanchored identity regexp pins nothing"
    assert _identity_pin_wrong("platform", r"^https://github\.com/policy-as-versioned-platform/"
                               r"platform/\.github/workflows/cut-release\.yml@refs/heads/main$",
                               ci) == "", "a parent's own anchored pin must be acceptable"

    # a hand-typed sample is a rehearsal (ADR-0023, D4) whatever it says about itself.
    assert sample_provenance(SAMPLES, [{"run": "typed-by-hand"}]), \
        "a sample whose run is not an Actions run id must never be graded"
    print(f"ok  three falsifiers declared; verdict is tri-state; {len(sources())} sources read "
          f"from gitops/; fact 2 grades the identity; a hand-typed sample is refused")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    take = sub.add_parser("sample")
    take.add_argument("--context", default=os.environ.get("DRIFT_CONTEXT", "kind-tuppence"))
    take.add_argument("--cluster", default="")
    take.add_argument("--ref", default=None,
                      help="render composed/ from this git ref instead of the worktree")
    take.add_argument("--out", default=SAMPLES, help="'-' for stdout (a rehearsal, never cited)")
    scored = sub.add_parser("grade")
    scored.add_argument("--samples", default=SAMPLES)
    scored.add_argument("--max-age-hours", type=float, default=48.0)
    sub.add_parser("selfcheck")
    args = parser.parse_args()

    if args.cmd == "selfcheck":
        return selfcheck()
    if args.cmd == "sample":
        cluster = args.cluster or args.context
        records = take_sample(args.context, cluster, args.ref)
        text = "".join(json.dumps(r, sort_keys=True) + "\n" for r in records)
        if args.out == "-":
            sys.stdout.write(text)
        else:
            with open(args.out, "a") as fh:
                fh.write(text)
        return 0
    code, lines = grade(args.samples, args.max_age_hours)
    print("\n".join(lines))
    return code


if __name__ == "__main__":
    sys.exit(main())
