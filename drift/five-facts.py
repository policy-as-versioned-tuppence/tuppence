#!/usr/bin/env python3
"""The five-fact sample: is tuppence's composed policy set in force, from signed sources?

Ecosystem ticket 40, from ticket 16 answer items Q1, Q2, Q3 and Q5, under ADR-0023 (D1, D3).
The pre-registration -- the five facts, the three falsifiers, the coverage floor -- is
`drift/window.yaml`, section `five_fact_sample`, and it was committed before this file took its
first sample. This module is the instrument, not the conclusion.

    five-facts.py sample [--context CTX] [--cluster NAME] [--ref REF]
                         [--cage-probe-image IMAGE] [--out PATH|-]
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
  5. every such object is in the Flux inventory;
  6. a workload the cage puts on its OWN BOTTOM RUNG is admitted and Running;
  7. that workload reaches neither the API server nor the internet, while a control workload
     the cage left loose reaches both.

Facts 6 and 7 are ecosystem ticket 86. They are pre-registered in `window.yaml` under
`cage_behaviour_sample` and graded in the same sample and the same run as the five. `grade`
refuses to score them against any sample taken before the commit that registered them, and
reads that commit out of git at the served ref rather than from a date typed anywhere.

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
import time

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
SCHEMA_VERSION = 2  # 2 (ticket 86): every record carries facts 6 and 7 as well

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

# --- the cage (facts 6 and 7, ecosystem ticket 86) ----------------------------
# Pre-registered in `drift/window.yaml` under `cage_behaviour_sample`, committed before any sample
# that scores them, and `grade` REFUSES to score them against a sample taken before that commit
# (ticket 93's rule, measured from git at the served ref rather than from a date typed here).
#
# The estate's most distinctive claim is that nothing is denied: a workload that does not fit its
# cage runs on a tighter rung, and the bottom rung runs and reaches nothing. Until these two facts
# existed that claim had never been graded on a citable run. The only instrument that observes it,
# platform's `graded/verify-graded.sh` live tail, needs a persistent KinD cluster the scheduled
# truth runner has never had; the presenter runs that DO observe it are rehearsals and NORTH-STAR
# §5 forbids citing them. This lane already brings up a cluster per run, so the claim is graded
# where a cluster exists.
#
# TWO facts, not one. They fail for different reasons and one must never hide inside the other:
# a pod that was refused, or that never ran, also reaches nothing, so a single fact would grade a
# cage that is a gate exactly as it grades a cage that holds. Fact 6 is admission and life; fact 7
# is reach, and fact 7 is a could-not-look whenever fact 6 did not deliver a running workload.
CAGE_FACT_IDS = (
    "fact_6_the_bottom_rung_is_admitted_and_runs",
    "fact_7_the_bottom_rung_reaches_nothing_while_the_control_reaches",
)
# Declared in window.yaml before the first sample. Each is a way this measurement comes out
# AGAINST the claim, or comes out unmeasured -- never a quiet pass.
CAGE_FALSIFIER_IDS = (
    "the_cage_refuses_or_never_runs_the_workload_it_caged",
    "the_bottom_rung_completes_a_connection",
    "the_control_reaches_nothing_either_recorded_unmeasured",
    "the_cage_puts_the_control_and_the_fall_closed_workload_on_the_same_rung",
)
ALL_FACT_IDS = FACT_IDS + CAGE_FACT_IDS
CAGE_SCOPE = "the cage in force"

# The cage's own fan-out names its MutatingPolicy `cage-tier-<major>-<minor>-<patch>`. The version
# in force is READ off the cluster, never typed here: an adopter whose composed array declares a
# different set gets its own answer with no edit to this file.
CAGE_TIER_NAME = re.compile(r"^cage-tier-(\d+)-(\d+)-(\d+)$")

# Two namespaces, and NEITHER declares a rung.
#
#   * the FALL-CLOSED namespace declares only `policy-as-versioned.dev/governed: "true"`. The
#     cage's own rule is that a governed namespace with no tier falls closed to its bottom rung,
#     so the rung is the CAGE's answer and not this instrument's assertion. Nothing here types
#     the word `isolated`; whatever the cage stamps on the pod is recorded as what it stamped.
#   * the CONTROL namespace declares nothing at all, so the cage stamps its loosest rung.
#
# The tier is a property of the NAMESPACE in this cage (ticket 26, ADR-0022: never a pod label, or
# a workload could select its own rung), so the control cannot be the same pod twice. That is the
# comparison's ceiling and it is recorded on the fact.
CAGE_FALLCLOSED_NS = "cage-probe-fallclosed"
CAGE_CONTROL_NS = "cage-probe-control"
CAGE_POD = "cage-probe"
# A public address that is not the cluster's. Port 80 rather than 443: the question is whether a
# TCP connection completes at all, and an open port anybody can dial makes a REACHED verdict mean
# reached rather than "the far end happened to be listening".
CAGE_INTERNET_HOST = "1.1.1.1"
CAGE_INTERNET_PORT = "80"
# Printed by the probe's own shell so a `kubectl exec` that never ran the command is told apart
# from a command that ran and failed. Round 4 of the sampler wait order (ticket 107) is the same
# lesson one level up: a question asked before its answer can exist, whose silence reads as a yes,
# is not a question. An exec whose output carries no marker is a could-not-look, never a block.
CAGE_RC_MARKER = "cage-probe-rc="

# Waiting reasons that mean a pod is still coming up rather than a pod that will not come up. A
# wait that reads `ContainerCreating` as an answer is round 3 of the sampler wait order (ticket
# 107) one level down: a question asked before its answer could exist, whose silence reads as a
# verdict. Measured 2026-09-10 on a rehearsal cluster, where exactly that graded a healthy caged
# pod FALSE 1.9 seconds after it was created.
CAGE_TRANSIENT_WAITS = ("ContainerCreating", "PodInitializing")

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

    def run(self, *args: str, stdin: str | None = None) -> tuple[int, str]:
        """(exit code, stdout+stderr) of one kubectl call, where BOTH are the observation.

        Separate from `get`, which parses JSON and reads a NotFound as an absence. Here a
        non-zero exit and the message beside it are the fact: an admission refusal is what the
        API server said, quoted, and summarising it would lose the only evidence there is.
        """
        cmd = ["kubectl", "--context", self.context, "--request-timeout=30s", *args]
        try:
            done = subprocess.run(cmd, input=stdin, capture_output=True, text=True, timeout=180)
        except (OSError, subprocess.SubprocessError) as e:
            return 127, f"kubectl could not run: {e}"
        return done.returncode, ((done.stdout or "") + (done.stderr or "")).strip()


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


# --- the cage: does the bottom rung run, and does it reach? (facts 6 and 7) ----
def cage_in_force(cluster: Cluster) -> tuple[str, str]:
    """(the policy version whose cage is in force, why not) -- read off the cluster.

    The NEWEST installed `cage-tier-x-y-z`, because that is the cage a pod claiming the newest
    served version meets. Derived rather than declared: nothing here knows which versions this
    adopter's composed array holds, so an array that gains or retires a version moves this with
    no edit.
    """
    listing = cluster.get("get", "mutatingpolicies.policies.kyverno.io")
    if listing is None:
        return "", ("no MutatingPolicy could be listed on this cluster, so which cage is in force "
                    "could not be read")
    found = []
    for item in listing.get("items", []) or []:
        match = CAGE_TIER_NAME.match(str((item.get("metadata") or {}).get("name", "")))
        if match:
            found.append((tuple(int(p) for p in match.groups()), ".".join(match.groups())))
    if not found:
        return "", ("no cage-tier MutatingPolicy is installed on this cluster, so no cage is in "
                    "force and there is no rung to put a workload on")
    return max(found)[1], ""


def _cage_objects(version: str, image: str) -> str:
    """The experiment, as JSON kubectl can apply. Two namespaces and two pods.

    The pods declare `runAsNonRoot` and a NUMERIC `runAsUser`, and `readOnlyRootFilesystem` on
    their own container: the hardened rungs write both, the kubelet refuses an image whose USER it
    cannot resolve to a uid, and a pod that declared them itself proves the cage's tighten-only
    rule left them alone rather than that the cage supplied them. Neither pod declares a tier.
    """
    def namespace(name: str, governed: bool) -> dict:
        labels = {"app.kubernetes.io/managed-by": "drift-five-facts"}
        if governed:
            labels["policy-as-versioned.dev/governed"] = "true"
        return {"apiVersion": "v1", "kind": "Namespace",
                "metadata": {"name": name, "labels": labels}}

    def pod(namespace_name: str) -> dict:
        return {"apiVersion": "v1", "kind": "Pod",
                "metadata": {"name": CAGE_POD, "namespace": namespace_name,
                             "labels": {"policy-as-versioned.dev/policy-version": version}},
                "spec": {"securityContext": {"runAsNonRoot": True, "runAsUser": 65532},
                         "containers": [{"name": "app", "image": image,
                                         "imagePullPolicy": "IfNotPresent",
                                         "securityContext": {"readOnlyRootFilesystem": True}}]}}

    return json.dumps({"apiVersion": "v1", "kind": "List", "items": [
        namespace(CAGE_FALLCLOSED_NS, True), namespace(CAGE_CONTROL_NS, False),
        pod(CAGE_FALLCLOSED_NS), pod(CAGE_CONTROL_NS)]})


def _cage_pod_state(cluster: Cluster, namespace: str) -> dict:
    """What the cluster holds for one probe pod. `{}` when it holds none."""
    live = cluster.get("-n", namespace, "get", "pod", CAGE_POD)
    if not live:
        return {}
    meta, spec, status = (live.get("metadata") or {}), (live.get("spec") or {}), (live.get("status") or {})
    waiting, reasons = [], []
    for state in (status.get("containerStatuses") or []):
        stuck = ((state.get("state") or {}).get("waiting") or {})
        if stuck:
            reasons.append(str(stuck.get("reason") or ""))
            waiting.append(f"{state.get('name')}: {stuck.get('reason')} "
                           f"({stuck.get('message') or 'no message'})")
    return {
        "namespace": namespace,
        "tier": str((meta.get("labels") or {}).get("posture.acme.io/tier", "")),
        "caged": str((meta.get("labels") or {}).get("posture.acme.io/caged", "")),
        "priority_class": str(spec.get("priorityClassName", "")),
        "priority": spec.get("priority"),
        "containers": [c.get("name") for c in (spec.get("containers") or [])],
        "images": {c.get("name"): c.get("image") for c in (spec.get("containers") or [])},
        "phase": str(status.get("phase", "")),
        "ready": condition(live, "Ready").get("status") == "True",
        "scheduled": condition(live, "PodScheduled").get("status"),
        "scheduling_reason": condition(live, "PodScheduled").get("reason", ""),
        "containers_waiting": waiting,
        "waiting_reasons": reasons,
    }


def _cage_networkpolicies(cluster: Cluster, namespace: str, labels: dict) -> list[str]:
    """The NetworkPolicies in `namespace` whose podSelector matches `labels`.

    Recorded as CORROBORATION, never as the measurement: fact 7 is graded on connections. A
    deny-all that is present and a pod that cannot connect are two observations, and this estate
    has already shipped the failure where reading the policy's own YAML passed while a
    host-network pod walked out of the cage (platform/graded/verify-graded.sh, 2026-08-28).
    """
    listing = cluster.get("-n", namespace, "get", "networkpolicies.networking.k8s.io")
    out = []
    for item in (listing or {}).get("items", []) or []:
        wanted = (((item.get("spec") or {}).get("podSelector") or {}).get("matchLabels") or {})
        if all(str(labels.get(k, "")) == str(v) for k, v in wanted.items()):
            spec = item.get("spec") or {}
            out.append(f"{item['metadata']['name']} policyTypes={spec.get('policyTypes')} "
                       f"ingress={len(spec.get('ingress') or [])} egress={len(spec.get('egress') or [])}")
    return sorted(out)


def _cage_connect(cluster: Cluster, namespace: str, host: str, port: str) -> tuple[bool | None, str]:
    """(reached, why) for one TCP connect from the probe pod. `None` is could-not-look.

    A CONNECTION, never a read of the NetworkPolicy's own YAML. The exit code comes back inside
    the pod's own stdout behind a marker, because `kubectl exec` returns 1 both for "the command
    ran and failed" and for "the command never ran", and those are opposite answers here.
    """
    code, out = cluster.run("-n", namespace, "exec", CAGE_POD, "-c", "app", "--", "sh", "-c",
                            f"nc -w 4 -z {host} {port} >/dev/null 2>&1; echo {CAGE_RC_MARKER}$?")
    match = re.search(re.escape(CAGE_RC_MARKER) + r"(\d+)", out)
    if not match:
        tail = (out.strip().splitlines() or ["no output"])[-1]
        return None, (f"the connect to {host}:{port} from {namespace} could not be RUN "
                      f"(kubectl exec exit {code}): {tail}")
    reached = match.group(1) == "0"
    return reached, (f"{'connected to' if reached else 'could not connect to'} {host}:{port} "
                     f"from {namespace}")


def cage_facts(cluster: Cluster, image: str) -> tuple[dict, dict]:
    """Facts 6 and 7: the bottom rung runs, and it reaches nothing while the control reaches.

    The experiment, in the cage's own terms:

      * two namespaces, neither naming a rung. One is `governed`, so the cage's fall-closed rule
        puts its pod on the bottom rung; one is not, so the cage puts its pod on the loosest rung.
      * one pod each, claiming the policy version whose cage is in force, read off the cluster.
      * fact 6 is what the API SERVER did with the fall-closed pod: admitted, and running.
      * fact 7 is two TCP connects from each pod -- the API server's own ClusterIP, and an address
        outside the cluster -- with the control's pair as the thing that makes the fall-closed
        pair mean something.

    Every could-not-look says which of the two halves could not be looked at and why. A broken
    cluster reaches nothing either, and reads here as unmeasured, never as a cage that held.
    """
    def both(observed, why: str, **extra) -> tuple[dict, dict]:
        return (fact(observed, why, scope=CAGE_SCOPE, **extra),
                fact(observed, why, scope=CAGE_SCOPE, **extra))

    if not cluster.reachable:
        return both(None, "the cluster did not answer, so no workload was placed at any rung")
    if not image:
        return both(None, "no --cage-probe-image was given to this sample, so no workload could "
                          "be placed at a rung; the cage the estate ships injects a WAF sidecar "
                          "image that exists in no registry, and a pod that cannot pull is a "
                          "measurement of a registry rather than of the cage")
    version, why_not = cage_in_force(cluster)
    if not version:
        return both(None, why_not)

    applied_code, applied = cluster.run("apply", "-f", "-", stdin=_cage_objects(version, image))
    fallclosed = _cage_pod_state(cluster, CAGE_FALLCLOSED_NS)
    control = _cage_pod_state(cluster, CAGE_CONTROL_NS)
    # Bounded and best-effort, exactly like the lane's own waits: whatever the pods have or have
    # not become when this returns is what the sample records. A pod that does not exist is
    # SETTLED -- it was refused, and waiting two minutes for a pod the API server declined is the
    # shape of wait ticket 107 removed one level up.
    def settled(state: dict) -> bool:
        return (not state) or bool(state.get("ready")) or state.get("scheduled") == "False" \
            or any(r not in CAGE_TRANSIENT_WAITS for r in (state.get("waiting_reasons") or []))

    for _ in range(60):
        if settled(fallclosed) and settled(control):
            break
        time.sleep(2)
        fallclosed = _cage_pod_state(cluster, CAGE_FALLCLOSED_NS)
        control = _cage_pod_state(cluster, CAGE_CONTROL_NS)

    refusal = ""
    if applied_code != 0 and not fallclosed:
        # The API server's own words, verbatim: an admission refusal is a quotation, not a summary.
        # The sentence carries the last line; the record carries the whole of what kubectl said,
        # because both pods are refused together and the second message is evidence too.
        refusal = (applied.strip().splitlines() or [""])[-1]

    common = {"policy_version_in_force": version, "probe_image": image,
              "fall_closed_namespace": CAGE_FALLCLOSED_NS, "control_namespace": CAGE_CONTROL_NS}

    # ---- fact 6: admitted, and running -------------------------------------
    running = bool(fallclosed) and fallclosed.get("phase") == "Running" and fallclosed.get("ready")
    if not fallclosed:
        six = fact(False,
                   f"the cage REFUSED the workload: "
                   f"{refusal or 'no pod exists and the apply reported nothing'}",
                   scope=CAGE_SCOPE, admission_error=refusal, apply_output=applied[:4000],
                   falsifier=CAGE_FALSIFIER_IDS[0], **common)
    elif running:
        injected = sorted(set(fallclosed["containers"]) - {"app"})
        six = fact(True,
                   f"the workload the cage put on its bottom rung ({fallclosed['tier'] or 'no tier stamped'}) "
                   f"was ADMITTED and is Running, on priority class "
                   f"{fallclosed['priority_class'] or 'none'} (priority {fallclosed['priority']}), "
                   f"carrying {len(fallclosed['containers'])} container(s)"
                   + (f" including {', '.join(injected)} injected by the cage" if injected else ""),
                   scope=CAGE_SCOPE, pod=fallclosed, **common)
    elif fallclosed.get("scheduled") == "False":
        six = fact(None,
                   f"the workload was admitted but the cluster never scheduled it "
                   f"({fallclosed.get('scheduling_reason') or 'no reason given'}), which is the "
                   f"runner's capacity and not the cage's doing",
                   scope=CAGE_SCOPE, pod=fallclosed, **common)
    else:
        stuck = "; ".join(fallclosed.get("containers_waiting") or []) or \
            f"phase {fallclosed.get('phase') or 'unknown'}, Ready={fallclosed.get('ready')}"
        if all(r in CAGE_TRANSIENT_WAITS for r in (fallclosed.get("waiting_reasons") or [])) \
                and fallclosed.get("waiting_reasons"):
            stuck += (" -- still coming up when the bounded wait ran out, which is this "
                      "instrument's bound and not a verdict the cage reached")
        six = fact(False,
                   f"the workload was admitted onto the bottom rung "
                   f"({fallclosed.get('tier') or 'no tier stamped'}) and never ran: {stuck}",
                   scope=CAGE_SCOPE, pod=fallclosed, falsifier=CAGE_FALSIFIER_IDS[0], **common)
    six["ceiling"] = ("the sidecar the cage injects at a hardened rung is a stand-in built from "
                      "platform's own graded/waf-placeholder at the tag this repo pins. Running "
                      "here means the caged workload started with the sidecar the cage added, not "
                      "that a real WAF inspected anything.")

    # ---- fact 7: reaches nothing, while the control reaches -----------------
    seven = _cage_reach_fact(cluster, fallclosed, control, running, common)
    if applied_code != 0 and fallclosed:
        for one in (six, seven):
            one["apply_reported"] = (applied.strip().splitlines() or [""])[-1]
    # The namespaces are the instrument's, never the estate's: deleted whatever happened, so a
    # rehearsal on a real cluster leaves nothing behind and the next sample starts clean.
    cluster.run("delete", "ns", CAGE_FALLCLOSED_NS, CAGE_CONTROL_NS, "--wait=false",
                "--ignore-not-found")
    return six, seven


def _cage_reach_fact(cluster: Cluster, fallclosed: dict, control: dict, running: bool,
                     common: dict) -> dict:
    """Fact 7. Every branch that is not an observed reach or an observed cage is a could-not-look.

    The order of the branches is the whole design. A pod that REACHED falsifies the cage whatever
    else is true, so that is asked first. After it, every remaining path to `true` has to survive
    the control -- a pod in the same cluster, from the same image, running the same two connects,
    that the cage left loose. A cluster whose network is broken silences both, and silencing both
    is unmeasured here, never a cage that held.
    """
    ceiling = ("two pods in two namespaces, not one pod twice: in this cage the rung is a property "
               "of the NAMESPACE (ADR-0022) and never of the pod, so the control cannot be the "
               "same workload. Two TCP connects on two ports each -- the API server's ClusterIP "
               "and one address outside the cluster -- is not a proof that nothing at all is "
               "reachable.")
    def could_not(why: str, **extra) -> dict:
        return fact(None, why, scope=CAGE_SCOPE, ceiling=ceiling, **common, **extra)

    if not running:
        return could_not("no workload was running on the bottom rung, so there was nothing to "
                         "measure reach from; a pod that never ran reaches nothing for a reason "
                         "that is not the cage (fact 6 carries what happened to it)")

    api = cluster.get("-n", "default", "get", "svc", "kubernetes")
    api_ip = str(((api or {}).get("spec") or {}).get("clusterIP", ""))
    if not api_ip:
        return could_not("the kubernetes Service ClusterIP could not be read, so there was no "
                         "API server address to try to reach")

    targets = ((api_ip, "443"), (CAGE_INTERNET_HOST, CAGE_INTERNET_PORT))
    evidence: dict = {"targets": [f"{h}:{p}" for h, p in targets],
                      "fall_closed_tier": fallclosed.get("tier", ""),
                      "control_tier": control.get("tier", ""),
                      "networkpolicies_selecting_the_fall_closed_pod":
                          _cage_networkpolicies(cluster, CAGE_FALLCLOSED_NS,
                                                {"posture.acme.io/caged": fallclosed.get("caged", ""),
                                                 "posture.acme.io/tier": fallclosed.get("tier", "")}),
                      "networkpolicies_selecting_the_control_pod":
                          _cage_networkpolicies(cluster, CAGE_CONTROL_NS,
                                                {"posture.acme.io/caged": control.get("caged", ""),
                                                 "posture.acme.io/tier": control.get("tier", "")})}

    # The cage is generated by a background controller and then programmed by the CNI, so a single
    # early read would observe the admission-to-reach window and call it a cage that leaks. Poll
    # for "cannot connect", and record the elapsed time so a reader can see how long it took.
    caged: dict[str, bool | None] = {}
    why_caged: dict[str, str] = {}
    waited = 0
    for host, port in targets:
        for _ in range(20):
            got, why = _cage_connect(cluster, CAGE_FALLCLOSED_NS, host, port)
            caged[f"{host}:{port}"], why_caged[f"{host}:{port}"] = got, why
            if got is not True:
                break
            time.sleep(3)
            waited += 3
    evidence["fall_closed"] = why_caged
    evidence["seconds_waited_for_the_cage"] = waited

    reached_from_the_cage = [t for t, got in caged.items() if got is True]
    if reached_from_the_cage:
        return fact(False,
                    "the workload on the bottom rung COMPLETED a connection to "
                    + ", ".join(sorted(reached_from_the_cage))
                    + " -- the bottom rung is not a cage",
                    scope=CAGE_SCOPE, ceiling=ceiling, falsifier=CAGE_FALSIFIER_IDS[1],
                    **common, **evidence)

    if not control:
        return could_not("no control pod exists, so nothing says whether this cluster's network "
                         "works at all", **evidence)
    if not (control.get("phase") == "Running" and control.get("ready")):
        return could_not("the control workload is not running "
                         f"({control.get('phase') or 'no phase'}, Ready={control.get('ready')}), "
                         "so the silence from the bottom rung has nothing to be compared against",
                         **evidence)

    control_reach: dict[str, bool | None] = {}
    why_control: dict[str, str] = {}
    for host, port in targets:
        for _ in range(10):
            got, why = _cage_connect(cluster, CAGE_CONTROL_NS, host, port)
            control_reach[f"{host}:{port}"], why_control[f"{host}:{port}"] = got, why
            if got is not False:
                break
            time.sleep(3)
    evidence["control"] = why_control

    unlooked = [t for t, got in caged.items() if got is None] + \
               [t for t, got in control_reach.items() if got is None]
    if unlooked:
        return could_not("a connect could not be RUN at all, so nothing was observed about it: "
                         + "; ".join(sorted(set(
                             list(why_caged.values()) + list(why_control.values())))),
                         **evidence)
    silent = [t for t, got in control_reach.items() if got is not True]
    if silent:
        return could_not(
            "the CONTROL workload could not reach " + ", ".join(sorted(silent))
            + " either, so this cluster's network says nothing about the cage: a pod that reaches "
              "nothing because the cluster is broken must not read the same as a pod that reaches "
              "nothing because the cage holds. Recorded UNMEASURED, which is not a pass",
            falsifier=CAGE_FALSIFIER_IDS[2], **evidence)
    if fallclosed.get("tier") == control.get("tier"):
        return could_not(
            f"the cage in force put the fall-closed workload and the control on the SAME rung "
            f"({fallclosed.get('tier') or 'no tier stamped'}), so it has no bottom rung distinct "
            f"from its loosest one and there was no bottom rung to look at",
            falsifier=CAGE_FALSIFIER_IDS[3], **evidence)
    if not evidence["networkpolicies_selecting_the_fall_closed_pod"]:
        return could_not(
            "the workload on the bottom rung reached nothing, and NOTHING IN THE CAGE SELECTS IT: "
            "no NetworkPolicy in its namespace matches its labels, so nothing observed here "
            "explains the silence and it may not be credited to the cage", **evidence)

    return fact(True,
                f"the workload the cage put on its bottom rung ({fallclosed.get('tier')}) reached "
                f"NEITHER the API server nor {CAGE_INTERNET_HOST}, while the control workload on "
                f"{control.get('tier') or 'the loosest rung'} reached both from the same cluster "
                f"with the same image -- a connection refused by the cage, not a YAML read",
                scope=CAGE_SCOPE, ceiling=ceiling, **common, **evidence)


# --- the sample ---------------------------------------------------------------
def take_sample(context: str, cluster_name: str, ref: str | None,
                cage_probe_image: str = "") -> list[dict]:
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

    # Facts 6 and 7 (ticket 86), taken ONCE like facts 4 and 5: the cage is one thing where the
    # sources are three, and this half of the sample creates real pods, which may happen once per
    # sample and never once per source.
    f6, f7 = cage_facts(cluster, cage_probe_image)

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
            "facts": {**_source_facts(src, live, kustomizations, identity, f4, f5),
                      CAGE_FACT_IDS[0]: f6, CAGE_FACT_IDS[1]: f7},
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
    # `if f in facts`: a record taken before the cage facts were registered carries five, and its
    # verdict is the verdict of the five it actually holds. Scoring an absent fact either way
    # would be scoring a question that had not been asked when the sample was taken, which is the
    # whole of ticket 93's rule.
    values = [facts[f]["observed"] for f in ALL_FACT_IDS if f in facts]
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


def cage_section() -> dict:
    """`cage_behaviour_sample` out of window.yaml. `{}` when the file cannot be read."""
    try:
        with open(WINDOW) as fh:
            doc = yaml.safe_load(fh) or {}
    except (OSError, yaml.YAMLError):
        return {}
    section = doc.get("cage_behaviour_sample")
    return section if isinstance(section, dict) else {}


def cage_registration(ref: str = "refs/remotes/origin/main") -> tuple[dt.datetime | None, str]:
    """(when the cage facts arrived in window.yaml on the served ref, how it is known).

    Ticket 93's rule, applied one level down. A fact scored before it was registered is worthless
    and a question rewritten after it landed moves every score taken against it, so the date is
    not typed anywhere -- it is READ OUT OF GIT, from the first commit on the SERVED ref whose
    diff against its own first parent introduces the fact's id into `drift/window.yaml`. Merged
    through a pull request that is the merge commit, dated by whoever merged it.

    `--first-parent`, so a branch commit that never reached the served ref does not register
    anything: a branch run records nothing (ticket 100), and neither does a branch commit.

    The one thing this cannot do is score a sample it cannot date, so an unreadable git history is
    a could-not-look on the cage facts and never a pass.
    """
    rel = os.path.relpath(WINDOW, REPO)
    try:
        done = subprocess.run(
            ["git", "-C", REPO, "log", "--first-parent", "--reverse", "--format=%cI %H",
             "-S", CAGE_FACT_IDS[0], ref, "--", rel],
            capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as e:
        return None, f"git could not be run here to date the registration ({e})"
    if done.returncode != 0:
        tail = (done.stderr or "").strip().splitlines()[-1:] or [""]
        return None, (f"the served ref {ref} is not readable in this checkout, so when the cage "
                      f"facts were registered cannot be established here: {tail[0]}")
    first = (done.stdout or "").strip().splitlines()[:1]
    if not first:
        return None, (f"no commit on {ref} introduces {CAGE_FACT_IDS[0]} into {rel}, so the cage "
                      f"facts have not been registered on the served ref")
    stamp, sha = first[0].split(" ", 1)
    when = dt.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    return when.astimezone(dt.timezone.utc), f"registered by {sha[:12]} at {stamp} on {ref}"


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

    # Ticket 86's own version of ticket 40's rule: the cage facts are graded only where they are
    # REGISTERED first. A fact scored before it was registered is worthless, so the instrument
    # refuses to grade at all while its own pre-registration is missing rather than quietly
    # dropping two of the seven facts and reporting on five.
    section = cage_section()
    registered_facts = [str(f.get("id")) for f in (section.get("facts") or [])]
    registered_falsifiers = [str(f.get("id")) for f in (section.get("falsifiers") or [])]
    unregistered = [f for f in CAGE_FACT_IDS if f not in registered_facts] + \
                   [f for f in CAGE_FALSIFIER_IDS if f not in registered_falsifiers]
    if unregistered:
        return 1, [f"FAIL: drift/window.yaml does not pre-register {unregistered[0]} under "
                   f"cage_behaviour_sample -- the cage facts are graded only where the question "
                   f"was declared first, and a fact scored before it was registered is worthless "
                   f"(ticket 86, under ticket 93's rule)"]

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

    # WHEN the cage facts were registered, read out of git at the served ref (ticket 93's rule,
    # ticket 86's application of it). A sample taken before that commit is not scored on them:
    # the question had not been asked when the observation was made, and scoring it either way
    # would be scoring an answer to a question nobody had put. Said out loud on the line, because
    # a fact silently dropped is the same shape as a fact silently passed.
    registered, how = cage_registration()
    taken = dt.datetime.strptime(latest, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
    score_cage = registered is not None and taken >= registered
    verdict = 0
    if registered is None:
        lines.append(f"  the cage facts (6, 7) are NOT SCORED here: {how}. A registration that "
                     f"cannot be established is a could-not-look, never a pass")
        verdict = 3
    elif not score_cage:
        lines.append(f"  the cage facts (6, 7) are NOT SCORED on this sample: it was taken "
                     f"{latest}, before they were {how}")
    else:
        lines.append(f"  the cage facts (6, 7) ARE scored on this sample: {how}, and the sample "
                     f"is later")

    for record in sorted(group, key=lambda r: r["source"]):
        for name in ALL_FACT_IDS:
            if name in CAGE_FACT_IDS and not score_cage:
                continue
            got = record["facts"].get(name) or {
                "observed": None,
                "why": "this sample carries no such fact, though it was taken after the fact was "
                       "registered -- the sampler that took it did not look"}
            mark = {True: "true ", False: "FALSE", None: "?    "}[got["observed"]]
            lines.append(f"  {record['source']:<20} {mark} {name}: {got['why']}")
            if got["observed"] is False:
                verdict = max(verdict, 1)
            elif got["observed"] is None and verdict == 0:
                verdict = 3

    # The cage's own falsifiers. Each is set by the branch of `cage_facts` that reaches it, so a
    # firing is DERIVED from the observation rather than read back out of its sentence.
    if score_cage:
        for name in CAGE_FACT_IDS:
            got = (group[0]["facts"].get(name) or {})
            fired = got.get("falsifier")
            if not fired:
                continue
            if got.get("observed") is False:
                lines.append(f"  FALSIFIER FIRED: {fired} -- {got['why']}")
            else:
                lines.append(f"  FALSIFIER: {fired} -- recorded UNMEASURED, which is not a pass")

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

    # --- the cage: facts 6 and 7 (ecosystem ticket 86) -----------------------
    # The pre-registration is real in this checkout, and the instrument's ids are the window's.
    _section = cage_section()
    assert [str(f.get("id")) for f in (_section.get("facts") or [])] == list(CAGE_FACT_IDS), \
        "window.yaml must pre-register the two cage facts, in order, before a sample takes them"
    assert set(CAGE_FALSIFIER_IDS) <= {str(f.get("id")) for f in (_section.get("falsifiers") or [])}, \
        "window.yaml must declare every falsifier the cage facts can fire"
    assert _verdict({f: {"observed": True} for f in ALL_FACT_IDS}) == "PASS"
    assert _verdict({**{f: {"observed": True} for f in ALL_FACT_IDS},
                     CAGE_FACT_IDS[0]: {"observed": False}}) == "FAIL", \
        "a cage fact observed false fails the sample; it does not sit beside it"
    assert _verdict({**{f: {"observed": True} for f in ALL_FACT_IDS},
                     CAGE_FACT_IDS[1]: {"observed": None}}) == "COULD-NOT-LOOK"
    assert _verdict({f: {"observed": True} for f in FACT_IDS}) == "PASS", \
        "a record taken before the cage facts existed is graded on the five it carries"
    # The experiment declares no rung ANYWHERE: the rung is the cage's answer, not this file's.
    assert "isolated" not in _cage_objects("4.0.0", "img") and \
        "posture.acme.io/tier" not in _cage_objects("4.0.0", "img"), \
        "the probe must not name a rung: a tier this file typed would be an assertion, not a " \
        "measurement of where the cage puts an unlabelled workload"
    assert CAGE_TIER_NAME.match("cage-tier-4-0-0") and not CAGE_TIER_NAME.match("cage-tier")

    class _CageFixture(Cluster):
        """A cluster that answers only what fact 7 asks, from a table. No kubectl, no network.

        Six branches, and five of them are the ways a green must not be earned. The one that
        matters most is `control=False`: a pod that reaches nothing because the cluster is broken
        must never read the same as a pod that reaches nothing because the cage holds.
        """

        def __init__(self, *, control: bool, caged: bool, exec_runs: bool = True,
                     netpol: bool = True):
            super().__init__("fixture")
            self.reachable = True
            self.control, self.caged = control, caged
            self.exec_runs, self.netpol = exec_runs, netpol

        def get(self, *args: str) -> dict | None:
            if args[-1] == "kubernetes":
                return {"spec": {"clusterIP": "10.96.0.1"}}
            if "networkpolicies.networking.k8s.io" in args:
                if args[1] == CAGE_FALLCLOSED_NS and self.netpol:
                    return {"items": [{"metadata": {"name": "cage-reach-isolated"},
                                       "spec": {"podSelector": {"matchLabels":
                                                {"posture.acme.io/tier": "isolated"}},
                                                "policyTypes": ["Ingress", "Egress"]}}]}
                return {"items": []}
            return None

        def run(self, *args: str, stdin: str | None = None) -> tuple[int, str]:
            if not self.exec_runs:
                return 1, "error: unable to upgrade connection: container not found"
            reached = self.control if args[1] == CAGE_CONTROL_NS else self.caged
            return (0 if reached else 1), f"{CAGE_RC_MARKER}{0 if reached else 1}"

    _bottom = {"namespace": CAGE_FALLCLOSED_NS, "tier": "isolated", "caged": "true",
               "phase": "Running", "ready": True, "containers": ["app", "waf-sidecar"]}
    _loose = {"namespace": CAGE_CONTROL_NS, "tier": "baseline", "caged": "true",
              "phase": "Running", "ready": True, "containers": ["app"]}
    _common = {"policy_version_in_force": "4.0.0", "probe_image": "stand-in",
               "fall_closed_namespace": CAGE_FALLCLOSED_NS, "control_namespace": CAGE_CONTROL_NS}
    # The polls are real seconds against a real CNI. Here there is neither, and a selfcheck that
    # slept ninety seconds to prove six branches would stop being run.
    _slept, time.sleep = time.sleep, lambda _s: None
    try:
        green = _cage_reach_fact(_CageFixture(control=True, caged=False), _bottom, _loose, True, _common)
        assert green["observed"] is True and "NEITHER" in green["why"]
        leaks = _cage_reach_fact(_CageFixture(control=True, caged=True), _bottom, _loose, True, _common)
        assert leaks["observed"] is False and leaks["falsifier"] == CAGE_FALSIFIER_IDS[1], \
            "a bottom rung that completes a connection is observed FALSE"
        broken = _cage_reach_fact(_CageFixture(control=False, caged=False), _bottom, _loose, True, _common)
        assert broken["observed"] is None and broken["falsifier"] == CAGE_FALSIFIER_IDS[2] \
            and "UNMEASURED" in broken["why"], \
            "a cluster whose control reaches nothing either is unmeasured, never a cage that held"
        flat = _cage_reach_fact(_CageFixture(control=True, caged=False), _bottom,
                                {**_loose, "tier": "isolated"}, True, _common)
        assert flat["observed"] is None and flat["falsifier"] == CAGE_FALSIFIER_IDS[3], \
            "a cage with no rung below its loosest one has no bottom rung to look at"
        unexplained = _cage_reach_fact(_CageFixture(control=True, caged=False, netpol=False),
                                       _bottom, _loose, True, _common)
        assert unexplained["observed"] is None and "SELECTS IT" in unexplained["why"], \
            "silence with nothing in the cage selecting the pod may not be credited to the cage"
        unrun = _cage_reach_fact(_CageFixture(control=True, caged=False, exec_runs=False),
                                 _bottom, _loose, True, _common)
        assert unrun["observed"] is None and "could not be RUN" in unrun["why"], \
            "an exec that never ran the connect is a could-not-look, not a block"
        dead = _cage_reach_fact(_CageFixture(control=True, caged=False), _bottom, _loose, False, _common)
        assert dead["observed"] is None and "nothing to measure reach from" in dead["why"], \
            "a workload that never ran reaches nothing for a reason that is not the cage"
    finally:
        time.sleep = _slept

    # A registration that cannot be read is a could-not-look, and says which ref it looked at.
    _when, _how = cage_registration("refs/remotes/origin/no-such-ref-for-a-selfcheck")
    assert _when is None and "no-such-ref-for-a-selfcheck" in _how, \
        "an unreadable served ref must leave the cage facts unscored, never quietly passed"

    # a hand-typed sample is a rehearsal (ADR-0023, D4) whatever it says about itself.
    assert sample_provenance(SAMPLES, [{"run": "typed-by-hand"}]), \
        "a sample whose run is not an Actions run id must never be graded"
    print(f"ok  three falsifiers declared; verdict is tri-state; {len(sources())} sources read "
          f"from gitops/; fact 2 grades the identity; a hand-typed sample is refused; the two cage facts are pre-registered in "
          f"window.yaml, a cage that refuses or leaks is observed false, and a cluster "
          f"whose control reaches nothing either is unmeasured rather than a cage that held")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    take = sub.add_parser("sample")
    take.add_argument("--context", default=os.environ.get("DRIFT_CONTEXT", "kind-tuppence"))
    take.add_argument("--cluster", default="")
    take.add_argument("--ref", default=None,
                      help="render composed/ from this git ref instead of the worktree")
    take.add_argument("--cage-probe-image", default=os.environ.get("CAGE_PROBE_IMAGE", ""),
                      help="the image facts 6 and 7 place at a rung. The cage injects a WAF "
                           "sidecar whose image exists in no registry, so the lane builds "
                           "platform's own stand-in for it and loads it into the node; without "
                           "one, both cage facts are could-not-look rather than a pod that "
                           "cannot pull")
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
        records = take_sample(args.context, cluster, args.ref, args.cage_probe_image)
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
