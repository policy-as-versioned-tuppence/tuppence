#!/usr/bin/env python3
"""The offline half of the cage probe (eco-system ticket 161, item 4; ticket 152 Q9).

`verify-cage-probe.sh` calls this. It runs the SAMPLER'S OWN probe objects -- imported from
`drift/five-facts.py`'s `_cage_objects`, never a second copy -- through the pinned kyverno CLI
against the composed documents this repository SERVES: the tree under `composed/` at the tag that
`gitops/composed/composed-set.yaml` pins, and the same tree at HEAD. It reads the version array
out of the ResourceSet, so an adopter whose array declares a different set gets its own answer.

    cage_probe.py declared-engine                 print `<version> <file>` for the engine this
                                                  repository declares (ticket 147's file, or
                                                  KYVERNO_VERSION in drift-sample.yml until then)
    cage_probe.py cli-version --cli PATH          print the version the CLI reports
    cage_probe.py namespace-labels --cli PATH --ref REF
                                                  exit 0 when the CLI reads Namespace labels
                                                  through a Values file `namespaces:` list, 3 when
                                                  it does not (the quirk ticket 152's harness found)
    cage_probe.py prove --cli PATH --ref REF      exit 0 when, for every version the array installs,
                                                  the fall-closed pod lands on the ladder's BOTTOM
                                                  and nothing selects the reference pod; 1 when
                                                  the documents say otherwise; 3 could not look

What PASS rests on, said once (ticket 152 Q7 and Q6):

  * the fall-closed pod's `priority` equals the LOWEST value among the PriorityClasses the tree
    serves whose names start `cage-`, and the class the mutation names is served;
  * a generated NetworkPolicy selects the fall-closed pod, and every one that does carries no
    ingress rule and no egress rule and declares both policy types;
  * no mutation touched the reference pod (no tier, no caged label, spec unchanged) and no
    generated NetworkPolicy selects it.

Generation is judged by the OBJECTS the CLI writes, never by its result table: on 1.18.2 the table
reports a GeneratingPolicy as passed for a pod it generated nothing for (ticket 71 recorded that
upstream fixed the report). A PASS here is a statement about the documents. The lane's facts 6 and
7 are the statement about a cluster, and the two do not conflict.
"""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "scripts"))
import render_composed as rc  # noqa: E402

ENGINE_FILE = "gitops/engine/kyverno.yaml"
LANE = ".github/workflows/drift-sample.yml"
CAGE_PRIORITY_PREFIX = "cage-"
SEMVER = re.compile(r"\d+\.\d+\.\d+")


class CouldNotLook(Exception):
    """Something this proof needs is missing, so nothing about the documents was graded."""


def _five_facts():
    """The sampler, imported by path (its file name has a hyphen), so the probe objects are its."""
    spec = importlib.util.spec_from_file_location("five_facts", os.path.join(HERE, "five-facts.py"))
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


# --- the engine ------------------------------------------------------------------------------
def declared_engine(repo: str = REPO) -> tuple[str, str]:
    """(version, where) for the engine this adopter declares.

    Ticket 147's `gitops/engine/kyverno.yaml` carries a top-level `version`. Until that file exists
    the declaration is `KYVERNO_VERSION` in the lane's workflow, the pin every lane carried before.
    """
    path = os.path.join(repo, ENGINE_FILE)
    if os.path.exists(path):
        with open(path) as fh:
            doc = yaml.safe_load(fh) or {}
        version = str((doc or {}).get("version", "")) if isinstance(doc, dict) else ""
        if not SEMVER.fullmatch(version):
            raise CouldNotLook(f"{ENGINE_FILE} exists but carries no exact `version:` "
                               f"(read {version!r}), so the declared engine cannot be read")
        return version, ENGINE_FILE
    with open(os.path.join(repo, LANE)) as fh:
        for line in fh:
            match = re.match(r"^\s*KYVERNO_VERSION:\s*['\"]?(\d+\.\d+\.\d+)['\"]?\s*$", line)
            if match:
                return match.group(1), LANE
    raise CouldNotLook(f"neither {ENGINE_FILE} nor a KYVERNO_VERSION line in {LANE} declares an "
                       f"engine, so there is nothing to compare the CLI with")


def cli_version(cli: str) -> str:
    try:
        done = subprocess.run([cli, "version"], capture_output=True, text=True, timeout=60)
    except OSError as e:
        raise CouldNotLook(f"the kyverno CLI {cli!r} could not be run: {e}") from e
    match = re.search(r"Version:\s*v?(\d+\.\d+\.\d+)", done.stdout + done.stderr)
    if not match:
        raise CouldNotLook(f"the kyverno CLI {cli!r} printed no `Version:` line: "
                           f"{(done.stdout + done.stderr).strip()[:200]!r}")
    return match.group(1)


# --- the served tree at a ref ----------------------------------------------------------------
def extract(ref: str, into: str, repo: str = REPO) -> str:
    """`composed/` at `ref`, as files the CLI can read. The ref must be present in this checkout."""
    if subprocess.run(["git", "-C", repo, "rev-parse", "-q", "--verify", f"{ref}^{{commit}}"],
                      capture_output=True).returncode != 0:
        raise CouldNotLook(f"the ref {ref} is not present in this checkout, so the documents it "
                           f"serves cannot be read here (fetch it: git fetch origin tag {ref})")
    archive = subprocess.run(["git", "-C", repo, "archive", ref, "composed"], capture_output=True)
    if archive.returncode != 0:
        raise CouldNotLook(f"git archive {ref} composed failed: "
                           f"{archive.stderr.decode(errors='replace').strip()}")
    subprocess.run(["tar", "-x", "-C", into], input=archive.stdout, check=True)
    return os.path.join(into, "composed")


def _objects(path: str) -> list[dict]:
    with open(path) as fh:
        try:
            return [d for d in yaml.safe_load_all(fh) if isinstance(d, dict) and d.get("kind")]
        except yaml.YAMLError:
            return []


def served(tree: str) -> dict[str, list[tuple[str, dict]]]:
    """{kind: [(file, object)]} for everything under the extracted composed/ tree."""
    out: dict[str, list[tuple[str, dict]]] = {}
    for root, _, names in os.walk(tree):
        for name in sorted(names):
            if not name.endswith((".yaml", ".yml")):
                continue
            path = os.path.join(root, name)
            for doc in _objects(path):
                out.setdefault(str(doc["kind"]), []).append((os.path.relpath(path, tree), doc))
    return out


def _write(dirpath: str, name: str, docs: list[dict]) -> str:
    path = os.path.join(dirpath, name)
    with open(path, "w") as fh:
        yaml.safe_dump_all(docs, fh, sort_keys=False)
    return path


# --- running the CLI -------------------------------------------------------------------------
def _apply(cli: str, policies: list[str], resource: str, values: str, out: str) -> tuple[int, str]:
    cmd = [cli, "apply", *policies, "--resource", resource, "-f", values, "--remove-color", "-o", out]
    done = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    return done.returncode, done.stdout + done.stderr


def _docs(path: str) -> list[dict]:
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return []
    with open(path) as fh:
        return [d for d in yaml.safe_load_all(fh) if isinstance(d, dict)]


def _values(namespace: dict) -> dict:
    """The Values document that hands the CLI the pod's Namespace. `namespaces:` is the list the
    CLI resolves `namespaceObject` from; a Namespace given as `--resource` is not (ticket 152's
    harness, SANE-quirk)."""
    return {"apiVersion": "cli.kyverno.io/v1alpha1", "kind": "Value",
            "metadata": {"name": "values"}, "namespaces": [namespace]}


def run_pod(cli: str, work: str, tag: str, pod: dict, namespace: dict,
            mutating: list[str], generating: list[str]) -> tuple[dict, list[dict], str]:
    """(the pod after every served mutation, the NetworkPolicies the generators wrote, the CLI log).

    Mutate first, with every served MutatingPolicy at once, as the API server would. The CLI writes
    one document per evaluation; the LAST is the pod as admitted. If it wrote nothing, nothing
    mutated the pod. Then generate from that pod. The generators write objects, and it is those
    objects, not the CLI's pass/skip table, that this proof reads.
    """
    pod_path = os.path.join(work, f"{tag}.pod.json")
    with open(pod_path, "w") as fh:
        json.dump(pod, fh)
    values_path = os.path.join(work, f"{tag}.values.json")
    with open(values_path, "w") as fh:
        json.dump(_values(namespace), fh)
    mut_out = os.path.join(work, f"{tag}.mutated.yaml")
    code, log = _apply(cli, mutating, pod_path, values_path, mut_out)
    if code != 0:
        raise CouldNotLook(f"the CLI could not apply the served MutatingPolicies to {tag} "
                           f"(exit {code}): {log.strip().splitlines()[-1:] or ['no output']}")
    pods = [d for d in _docs(mut_out) if d.get("kind") == "Pod"]
    admitted = pods[-1] if pods else copy.deepcopy(pod)
    admitted_path = os.path.join(work, f"{tag}.admitted.json")
    with open(admitted_path, "w") as fh:
        json.dump(admitted, fh)
    gen_out = os.path.join(work, f"{tag}.generated.yaml")
    code2, log2 = _apply(cli, generating, admitted_path, values_path, gen_out)
    if code2 != 0:
        raise CouldNotLook(f"the CLI could not apply the served GeneratingPolicies to {tag} "
                           f"(exit {code2}): {log2.strip().splitlines()[-1:] or ['no output']}")
    policies = [d for d in _docs(gen_out) if d.get("kind") == "NetworkPolicy"]
    return admitted, policies, log + log2


def selects(policy: dict, pod: dict) -> bool:
    """Does this NetworkPolicy select this pod: same namespace, and matchLabels a subset of the
    pod's labels. matchExpressions are not evaluated and never count (the sampler's own limit)."""
    spec = policy.get("spec") or {}
    selector = spec.get("podSelector") or {}
    if selector.get("matchExpressions"):
        return False
    if (policy.get("metadata") or {}).get("namespace") != (pod.get("metadata") or {}).get("namespace"):
        return False
    labels = (pod.get("metadata") or {}).get("labels") or {}
    return all(str(labels.get(k)) == str(v) for k, v in (selector.get("matchLabels") or {}).items())


def _rules(policy: dict) -> tuple[int, int, list[str]]:
    spec = policy.get("spec") or {}
    return (len(spec.get("ingress") or []), len(spec.get("egress") or []),
            sorted(str(t) for t in (spec.get("policyTypes") or [])))


# --- the proofs ------------------------------------------------------------------------------
def prove(cli: str, ref: str, repo: str = REPO) -> tuple[list[str], list[str]]:
    """(ok lines, fault lines) for the served documents at `ref`."""
    ff = _five_facts()
    versions = rc.versions(None, repo)
    if not versions:
        raise CouldNotLook("gitops/composed/composed-set.yaml installs no version, so there is no "
                           "served cage to run the probe against")
    work = tempfile.mkdtemp(prefix="cage-probe-")
    try:
        tree = extract(ref, work, repo)
        docs = served(tree)
        mutating = sorted({os.path.join(tree, f) for f, _ in docs.get("MutatingPolicy", [])})
        generating = sorted({os.path.join(tree, f) for f, _ in docs.get("GeneratingPolicy", [])})
        classes = {str(d["metadata"]["name"]): int(d.get("value"))
                   for _, d in docs.get("PriorityClass", []) if isinstance(d.get("value"), int)}
        cage_classes = {n: v for n, v in classes.items() if n.startswith(CAGE_PRIORITY_PREFIX)}
        oks: list[str] = []
        faults: list[str] = []
        if not mutating:
            raise CouldNotLook(f"composed/ at {ref} serves no MutatingPolicy, so there is no cage to run the probe against")
        if not generating:
            faults.append(f"{ref}: composed/ serves no GeneratingPolicy, so nothing can generate a reach policy for the bottom rung")
        if not cage_classes:
            faults.append(f"{ref}: composed/ serves no PriorityClass whose name starts `{CAGE_PRIORITY_PREFIX}`, so the ladder has no bottom")
        lowest_name = min(cage_classes, key=lambda n: (cage_classes[n], n)) if cage_classes else ""
        lowest = cage_classes.get(lowest_name)
        oks.append(f"{ref}: {len(mutating)} MutatingPolicy file(s), {len(generating)} GeneratingPolicy "
                   f"file(s), {len(cage_classes)} `cage-` PriorityClass(es) served; the lowest is "
                   f"{lowest_name} = {lowest}")

        # The reference pod claims nothing, whatever the array: one run.
        probe = json.loads(ff._cage_objects(versions[0], "ghcr.io/acme/coraza-waf:cage"))["items"]
        namespaces = {o["metadata"]["name"]: o for o in probe if o["kind"] == "Namespace"}
        pods = {o["metadata"]["namespace"]: o for o in probe if o["kind"] == "Pod"}
        ref_ns, fc_ns = ff.CAGE_REFERENCE_NS, ff.CAGE_FALLCLOSED_NS
        before = copy.deepcopy(pods[ref_ns])
        admitted, generated, _ = run_pod(cli, work, "reference", pods[ref_ns], namespaces[ref_ns],
                                         mutating, generating or mutating[:1])
        labels = (admitted.get("metadata") or {}).get("labels") or {}
        touched = [k for k in ("posture.acme.io/tier", "posture.acme.io/caged") if k in labels]
        if touched or admitted.get("spec") != before.get("spec"):
            faults.append(f"{ref}: a served mutation TOUCHED the reference pod: labels {touched or 'none'}, "
                          f"spec {'changed' if admitted.get('spec') != before.get('spec') else 'unchanged'} "
                          f"(ecosystem 119 decision 2 keeps an unclaimed pod in an unlabelled Namespace outside the cage)")
        selecting_ref = [p for p in generated if selects(p, admitted)]
        if selecting_ref:
            faults.append(f"{ref}: generated NetworkPolicy {[p['metadata']['name'] for p in selecting_ref]} "
                          f"select(s) the reference pod")
        if not touched and not selecting_ref and admitted.get("spec") == before.get("spec"):
            oks.append(f"{ref}: the reference pod (no claim, Namespace declares nothing) is untouched by "
                       f"every served mutation and selected by no generated NetworkPolicy "
                       f"({len(generated)} written)")

        # The fall-closed pod, once per version the array installs.
        for version in versions:
            probe = json.loads(ff._cage_objects(version, "ghcr.io/acme/coraza-waf:cage"))["items"]
            namespaces = {o["metadata"]["name"]: o for o in probe if o["kind"] == "Namespace"}
            pod = next(o for o in probe if o["kind"] == "Pod" and o["metadata"]["namespace"] == fc_ns)
            admitted, generated, _ = run_pod(cli, work, f"fallclosed-{version}", pod,
                                             namespaces[fc_ns], mutating, generating or mutating[:1])
            labels = (admitted.get("metadata") or {}).get("labels") or {}
            tier = labels.get("posture.acme.io/tier", "")
            spec = admitted.get("spec") or {}
            named = str(spec.get("priorityClassName") or "")
            priority = spec.get("priority")
            problems = []
            if not tier or labels.get("posture.acme.io/caged") != "true":
                problems.append("no served cage-tier stamped it (no tier, or caged is not true)")
            if named and named not in classes:
                problems.append(f"the mutation names PriorityClass {named}, which composed/ at {ref} does not serve")
            if not named:
                problems.append("the mutation names no PriorityClass")
            if lowest is not None and (priority is None or int(priority) > lowest):
                problems.append(f"its priority {priority} is above the lowest served `cage-` class ({lowest_name} = {lowest})")
            selecting = [p for p in generated if selects(p, admitted)]
            if not selecting:
                problems.append("no generated NetworkPolicy selects it")
            for p in selecting:
                ingress, egress, types = _rules(p)
                if ingress or egress:
                    problems.append(f"NetworkPolicy {p['metadata']['name']} selects it with {ingress} ingress and {egress} egress rule(s)")
                if types != ["Egress", "Ingress"]:
                    problems.append(f"NetworkPolicy {p['metadata']['name']} selects it and declares policyTypes={types}, not both")
            if problems:
                faults.append(f"{ref}: v{version}: the fall-closed pod (tier {tier or 'none'}, priority {priority}) "
                              f"is NOT on the ladder's bottom: " + "; ".join(problems))
            else:
                oks.append(f"{ref}: v{version}: the fall-closed pod lands on {tier} at priority {priority} = "
                           f"{lowest_name}, the lowest served `cage-` class, named class {named} is served, "
                           f"and {[p['metadata']['name'] for p in selecting]} select(s) it with no rules and both types")
        return oks, faults
    finally:
        shutil.rmtree(work, ignore_errors=True)


def namespace_labels(cli: str, ref: str, repo: str = REPO) -> str:
    """The CLI must read a Namespace's labels through a Values file `namespaces:` list. A
    Namespace that declares `restricted` must put a claiming pod on `restricted`. Returns the tier
    the pod landed on."""
    ff = _five_facts()
    versions = rc.versions(None, repo)
    work = tempfile.mkdtemp(prefix="cage-probe-ns-")
    try:
        tree = extract(ref, work, repo)
        docs = served(tree)
        tiers = [os.path.join(tree, f) for f, d in docs.get("MutatingPolicy", [])
                 if str(d["metadata"]["name"]).startswith("cage-tier-")]
        if not tiers:
            raise CouldNotLook(f"composed/ at {ref} serves no cage-tier MutatingPolicy to prove the CLI with")
        probe = json.loads(ff._cage_objects(versions[0], "ghcr.io/acme/coraza-waf:cage"))["items"]
        namespace = next(o for o in probe if o["kind"] == "Namespace"
                         and o["metadata"]["name"] == ff.CAGE_FALLCLOSED_NS)
        namespace["metadata"]["labels"]["posture.acme.io/tier"] = "restricted"
        pod = next(o for o in probe if o["kind"] == "Pod" and o["metadata"]["namespace"] == ff.CAGE_FALLCLOSED_NS)
        admitted, _, log = run_pod(cli, work, "nslabels", pod, namespace, tiers, tiers[:1])
        return str(((admitted.get("metadata") or {}).get("labels") or {}).get("posture.acme.io/tier", ""))
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("declared-engine")
    p = sub.add_parser("cli-version"); p.add_argument("--cli", required=True)
    p = sub.add_parser("namespace-labels"); p.add_argument("--cli", required=True); p.add_argument("--ref", required=True)
    p = sub.add_parser("prove"); p.add_argument("--cli", required=True); p.add_argument("--ref", required=True)
    args = parser.parse_args(argv)
    try:
        if args.cmd == "declared-engine":
            version, where = declared_engine()
            print(f"{version} {where}")
            return 0
        if args.cmd == "cli-version":
            print(cli_version(args.cli))
            return 0
        if args.cmd == "namespace-labels":
            tier = namespace_labels(args.cli, args.ref)
            if tier != "restricted":
                print(f"COULD NOT LOOK: the kyverno CLI put a claiming pod on {tier or 'no tier'!r} while its "
                      f"Namespace, given through a Values file `namespaces:` list, declares `restricted`: "
                      f"this CLI does not read Namespace labels the way the API server does, so nothing "
                      f"it says about the served documents can be trusted (ticket 152 harness, SANE-quirk)")
                return 3
            print(f"ok  the CLI reads Namespace labels: a Namespace declaring `restricted` put a claiming "
                  f"pod on `restricted` (served cage-tier at {args.ref})")
            return 0
        oks, faults = prove(args.cli, args.ref)
        for line in oks:
            print("ok  " + line)
        for line in faults:
            print("FAULT " + line)
        return 1 if faults else 0
    except CouldNotLook as e:
        print(f"COULD NOT LOOK: {e}")
        return 3


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
