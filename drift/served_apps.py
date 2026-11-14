#!/usr/bin/env python3
"""Ticket 155: observe served workloads and their reference copies on the same node."""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

import yaml

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "drift"
REFERENCE_NS = "cage-app-reference"
FACT_ID = "fact_8_each_served_workload_runs_in_its_cage"
SECTION = "workload_behaviour_sample"
KIND = "flux.served-workloads/v1"
LOG = HERE / "workload-samples.jsonl"
CLAIM = "policy-as-versioned.dev/policy-version"


def selfcheck() -> int:
    pod: dict = {"apiVersion": "v1", "kind": "Pod", "metadata": {"name": "ledger", "namespace": "ludlow",
           "labels": {CLAIM: "5.0.0", "posture.acme.io/tier": "isolated"}},
           "spec": {"containers": [{"name": "app", "image": "example@sha256:" + "a" * 64}]}}
    ref = reference(pod, "node-a")
    assert ref["spec"]["nodeName"] == "node-a"
    assert ref["spec"]["containers"] == pod["spec"]["containers"]
    assert not ref["metadata"]["labels"] and ref["metadata"]["namespace"] == REFERENCE_NS
    assert pod["metadata"]["labels"][CLAIM] == "5.0.0", "the reference cannot mutate the served object"
    assert verdict(True, True, True)[0] is True
    assert verdict(False, True, True)[0] is False, "only a running reference establishes does-not-fit"
    assert verdict(False, False, True)[0] is None, "two stopped workloads do not evidence a cage fault"
    assert verdict(False, True, False)[0] is None, "different nodes cannot isolate the cage's effect"
    assert verdict(None, True, True)[0] is None, "an unreadable workload is not observed false"
    print("ok  fact 8: same workload, unclaimed reference, same node, tri-state fit verdict")
    return 0


def reference(pod: dict, node: str) -> dict:
    out = copy.deepcopy(pod)
    meta = out.setdefault("metadata", {})
    meta["name"] = str(meta["name"]) + "-reference"
    meta["namespace"] = REFERENCE_NS
    meta["labels"] = {k: v for k, v in (meta.get("labels") or {}).items()
                      if k != CLAIM and not k.startswith("posture.acme.io/")}
    for key in ("uid", "resourceVersion", "creationTimestamp", "managedFields", "ownerReferences"):
        meta.pop(key, None)
    out.pop("status", None)
    out["spec"]["nodeName"] = node
    return out


def verdict(caged: bool | None, outside: bool | None, same_node: bool) -> tuple[bool | None, str]:
    if not same_node:
        return None, "the two copies did not run on the same node"
    if outside is not True:
        return None, "the reference copy did not run, so it cannot isolate a cage outcome"
    if caged is None:
        return None, "the API server could not say whether the caged workload runs"
    return caged, "both copies run" if caged else "the reference runs and the caged copy does not fit its cage"


def instrument():
    spec = importlib.util.spec_from_file_location("five_facts_instrument", HERE / "five-facts.py")
    if spec is None or spec.loader is None:
        raise ImportError("the pinned instrument has no readable module loader")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, stderr=subprocess.DEVNULL)


def pinned_workloads() -> tuple[str, list[dict]]:
    sync = list(yaml.safe_load_all((ROOT / "gitops/flux-system/gotk-sync.yaml").read_text()))
    source = next(d for d in sync if d and d.get("kind") == "GitRepository")
    pin = source["spec"]["ref"]
    tag = str(pin["tag"])
    actual = git("rev-parse", tag + "^{commit}").strip()
    if actual != pin["commit"]:
        raise ValueError("the apps source's tag and commit disagree")
    manifest = yaml.safe_load(git("show", tag + ":gitops/apps/kustomization.yaml")) or {}
    pods = []
    for entry in manifest.get("resources") or []:
        if not isinstance(entry, str) or "/" in entry or ".." in entry:
            raise ValueError(f"apps resource {entry!r} is not an accounted manifest file")
        for doc in yaml.safe_load_all(git("show", tag + ":gitops/apps/" + entry)):
            if doc and doc.get("kind") == "Pod":
                doc["_manifest"] = "gitops/apps/" + entry
                pods.append(doc)
    if not pods:
        raise ValueError("the signed apps source carries no served Pod")
    return tag, pods


def pod_state(live: dict | None, reachable: bool) -> dict:
    if live is None:
        return {"running": False if reachable else None, "node": "", "phase": "Absent", "containers": []}
    statuses = (live.get("status") or {}).get("containerStatuses") or []
    phase = (live.get("status") or {}).get("phase", "Unknown")
    return {"running": (all("running" in (s.get("state") or {}) for s in statuses) if phase == "Running" and statuses
                        else (False if phase in ("Pending", "Failed", "Succeeded") else None)),
            "node": (live.get("spec") or {}).get("nodeName", ""), "phase": phase,
            "containers": [{"name": s.get("name"), "state": s.get("state"), "restartCount": s.get("restartCount")}
                           for s in statuses],
            "labels": (live.get("metadata") or {}).get("labels") or {}}


def sample(context: str, timeout: float = 60) -> dict:
    sampler = instrument()
    cluster = sampler.Cluster(context)
    record = {"kind": KIND, "ts": sampler.now(), "run": os.environ.get("GITHUB_RUN_ID", ""), "event": os.environ.get("GITHUB_EVENT_NAME", ""),
              "context": context, "fact": FACT_ID, "workloads": [], "observed": None}
    try:
        tag, pods = pinned_workloads()
    except (OSError, ValueError, KeyError, StopIteration, subprocess.SubprocessError, yaml.YAMLError) as exc:
        record["why"] = f"the signed apps source could not be read: {exc}"
        return record
    record["apps_ref"] = tag
    nodes = cluster.get("get", "nodes") or {}
    record["runner_ceiling"] = {"wait_seconds_per_workload": timeout,
                                "nodes": [{"name": n["metadata"]["name"],
                                           "capacity": (n.get("status") or {}).get("capacity"),
                                           "allocatable": (n.get("status") or {}).get("allocatable")}
                                          for n in nodes.get("items") or []]}
    namespace = {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": REFERENCE_NS}}
    cluster.run("apply", "-f", "-", stdin=yaml.safe_dump(namespace))
    try:
        for pod in pods:
            meta = pod["metadata"]
            live = cluster.get("-n", meta["namespace"], "get", "pod", meta["name"])
            caged = pod_state(live, bool(cluster.reachable))
            node = caged["node"]
            # An unscheduled caged copy gives no same-node comparison. Still try a reference
            # on the runner's first node and record the scheduling ceiling explicitly.
            target = node or next((n["metadata"]["name"] for n in nodes.get("items") or []), "")
            if not target:
                record["workloads"].append({"name": meta["name"], "observed": None,
                                             "why": "the API server named no node for a reference copy"})
                continue
            ref = reference({k: v for k, v in pod.items() if k != "_manifest"}, target)
            code, output = cluster.run("apply", "-f", "-", stdin=yaml.safe_dump(ref))
            deadline = time.monotonic() + max(0, timeout)
            outside = pod_state(None, bool(cluster.reachable))
            while True:
                caged_live = cluster.get("-n", meta["namespace"], "get", "pod", meta["name"])
                caged = pod_state(caged_live, bool(cluster.reachable))
                ref_live = cluster.get("-n", REFERENCE_NS, "get", "pod", ref["metadata"]["name"])
                outside = pod_state(ref_live, bool(cluster.reachable))
                if (caged["running"] and outside["running"]) or time.monotonic() >= deadline:
                    break
                time.sleep(min(2, max(0, deadline - time.monotonic())))
            same = bool(caged["node"]) and caged["node"] == outside["node"]
            seen, why = verdict(caged["running"], outside["running"], same)
            cage_labels = caged.get("labels") or {}
            if not cage_labels.get("posture.acme.io/tier") or cage_labels.get("posture.acme.io/caged") != "true":
                seen, why = None, "the API server has not recorded this workload inside its cage"
            labels = outside.get("labels") or {}
            if labels.get("posture.acme.io/tier") or labels.get("posture.acme.io/caged"):
                seen, why = None, "the cage selected the reference copy; this is not an outside comparison"
            record["workloads"].append({"name": meta["name"], "manifest": pod["_manifest"],
                                         "observed": seen, "why": why, "caged": caged,
                                         "reference": outside, "reference_apply_rc": code,
                                         "reference_apply_output": output[-2000:],
                                         "image": [c["image"] for c in pod["spec"]["containers"]]})
    finally:
        cluster.run("delete", "ns", REFERENCE_NS, "--wait=false", "--ignore-not-found=true")
    values = [w["observed"] for w in record["workloads"]]
    record["observed"] = False if False in values else (True if values and all(v is True for v in values) else None)
    record["why"] = " ; ".join(w["name"] + ": " + w["why"] for w in record["workloads"])
    return record


def section_text(text: str) -> str:
    start = re.search(r"^" + SECTION + r":", text, re.M)
    if not start:
        return ""
    rest = text[start.end():]
    end = re.search(r"^\S", rest, re.M)
    return text[start.start():start.end() + (end.start() if end else len(rest))].rstrip() + "\n"


def registration() -> tuple[dt.datetime | None, str]:
    last = None
    previous = ""
    try:
        for line in git("log", "--reverse", "--first-parent", "--format=%H %cI",
                        "refs/remotes/origin/main", "--", "drift/window.yaml").splitlines():
            commit, date = line.split(" ", 1)
            section = section_text(git("show", commit + ":drift/window.yaml"))
            if section and section != previous:
                last = (dt.datetime.fromisoformat(date), commit)
            previous = section
    except subprocess.SubprocessError:
        return None, "the served registration history is unreadable"
    return last if last is not None else (None, "no committed workload registration has reached origin/main")


def grade(path: Path = LOG) -> tuple[int, str]:
    try:
        rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        row = max((r for r in rows if r.get("kind") == KIND), key=lambda r: r["ts"])
    except (OSError, ValueError, KeyError):
        return 3, "SKIP: no scheduled workload sample has landed for the registered instrument"
    stamp = dt.datetime.fromisoformat(row["ts"].replace("Z", "+00:00"))
    registered, how = registration()
    if registered is None or stamp < registered:
        return 3, f"SKIP: the workload sample predates or cannot establish its own registration: {how}"
    if dt.datetime.now(dt.timezone.utc) - stamp > dt.timedelta(hours=48):
        return 3, "SKIP: the newest workload sample is older than the 48h freshness bound"
    rehearsal = instrument().sample_provenance(str(path), [row])
    if rehearsal:
        return 3, "SKIP: " + rehearsal.replace("drift/samples.jsonl", "drift/workload-samples.jsonl").replace("five-fact sample", "workload sample")
    observed = row.get("observed")
    if observed is True and row.get("event") != "schedule":
        return 3, "SKIP: a workload lane run started by hand cannot establish a cited pass"
    mark, rc = ("PASS", 0) if observed is True else (("FAIL", 1) if observed is False else ("SKIP", 3))
    return rc, f"{mark}: {FACT_ID}: {row.get('why', 'no reason recorded')}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    take = sub.add_parser("sample")
    take.add_argument("--context", required=True)
    take.add_argument("--timeout", type=float, default=60)
    take.add_argument("--out", type=Path, default=LOG)
    sub.add_parser("selfcheck")
    sub.add_parser("grade")
    args = parser.parse_args()
    if args.command == "selfcheck":
        return selfcheck()
    if args.command == "sample":
        row = sample(args.context, args.timeout)
        with args.out.open("a") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
        print(json.dumps(row, sort_keys=True))
        return 0
    rc, line = grade()
    print(line)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
