#!/usr/bin/env python3
"""The offline render of tuppence's composed policy set (ecosystem ticket 40, fact 4).

Fact 4 of the five-fact sample is "every rendered policy object is live and byte-equal to an
offline render". Something has to produce that render without a cluster, without Flux and without
kustomize, or the fact compares the cluster to itself.

READ-ONLY over `composed/`. This script never writes into that tree and never edits it; it is the
offline twin of what the ResourceSet in `gitops/composed/` installs, in the same spirit as
platform's `render-orphan-guard.py` is the offline twin of its ResourceSet.

    render_composed.py --list                    the objects, one `kind/name` per line
    render_composed.py                           the canonical render, one JSON object per line
    render_composed.py --ref v1.1.0              render the tree at a git ref, not the worktree

The set rendered is exactly the set the ResourceSet installs: every version in the ResourceSet's
own array (read from gitops/composed/composed-set.yaml, so the two cannot drift apart) plus the
orphan guard. `HEADER.yaml` and `evidence.json` are advisory and are not objects.

## The ceiling, named

The API server fills in defaults, so a live object is NEVER byte-identical to the YAML that
created it. `compare()` therefore returns two verdicts and the caller records both:

  * `declared_equal` -- every field this render DECLARES is present and equal live. This is what
    fact 4 is graded on.
  * `strict_equal`   -- the canonical forms are identical after the server-owned metadata is
    stripped. Recorded so the weaker verdict is visible rather than implied.

Upgrade path if `declared_equal` ever proves too weak: pull the CRD's structural schema and prune
defaulted fields from the live object instead of ignoring live-only keys.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
COMPOSED = "composed"
RESOURCESET = os.path.join(REPO, "gitops", "composed", "composed-set.yaml")

# Everything the API server owns. Stripped from a live object before any comparison, because none
# of it was ever declared by the render and its presence is not drift.
SERVER_METADATA = (
    "uid", "resourceVersion", "generation", "creationTimestamp", "managedFields",
    "selfLink", "deletionTimestamp", "deletionGracePeriodSeconds",
)
SERVER_ANNOTATIONS = ("kubectl.kubernetes.io/last-applied-configuration",)


def _read(path: str, ref: str | None) -> str:
    if ref is None:
        with open(os.path.join(REPO, path)) as fh:
            return fh.read()
    return subprocess.run(["git", "-C", REPO, "show", f"{ref}:{path}"],
                          capture_output=True, text=True, check=True).stdout


def _ls(path: str, ref: str | None) -> list[str]:
    if ref is None:
        directory = os.path.join(REPO, path)
        if not os.path.isdir(directory):
            return []
        return [f"{path}/{n}" for n in sorted(os.listdir(directory)) if n.endswith(".yaml")]
    done = subprocess.run(["git", "-C", REPO, "ls-tree", "-r", "--name-only", ref, path + "/"],
                          capture_output=True, text=True, check=True)
    return sorted(n for n in done.stdout.split() if n.endswith(".yaml"))


def versions(ref: str | None = None) -> list[str]:
    """The version array the ResourceSet declares. Read from the ResourceSet itself so the render
    and the install can never name different sets; a version added there is rendered here on the
    next run with no edit to this file."""
    try:
        docs = [d for d in yaml.safe_load_all(_read("gitops/composed/composed-set.yaml", ref))
                if isinstance(d, dict) and d.get("kind") == "ResourceSet"]
        doc = docs[0]
    except (OSError, IndexError, subprocess.CalledProcessError):
        # No ResourceSet yet (or not at that ref): fall back to what composed/ carries, so the
        # renderer still answers rather than crashing during the build that adds the ResourceSet.
        prefix = f"{COMPOSED}/policies/"
        found = set()
        for path in _ls(f"{COMPOSED}/policies", ref) or []:
            found.add(path[len(prefix):].split("/")[0])
        if not found:
            done = subprocess.run(["git", "-C", REPO, "ls-tree", "--name-only",
                                   ref or "HEAD", f"{COMPOSED}/policies/"],
                                  capture_output=True, text=True)
            found = {p.rstrip("/").split("/")[-1] for p in done.stdout.split() if p.strip()}
        return sorted(v.lstrip("v") for v in found if v)
    array = (doc.get("spec", {}).get("inputs") or [{}])[0].get("versions") or []
    return [str(v["version"]) for v in array]


def key(obj: dict) -> str:
    return f"{obj.get('apiVersion')}/{obj.get('kind')}/{obj.get('metadata', {}).get('name')}"


def canonical(obj: dict) -> str:
    """One stable string per object. Sorted keys, no whitespace: two canonical strings are equal
    iff the objects are, whatever order the YAML or the API server happened to emit."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def strip_server_fields(live: dict) -> dict:
    """A live object reduced to what a render could have declared."""
    out = {k: v for k, v in live.items() if k != "status"}
    meta = dict(out.get("metadata") or {})
    for field in SERVER_METADATA:
        meta.pop(field, None)
    annotations = {k: v for k, v in (meta.get("annotations") or {}).items()
                   if k not in SERVER_ANNOTATIONS}
    if annotations:
        meta["annotations"] = annotations
    else:
        meta.pop("annotations", None)
    out["metadata"] = meta
    return out


def _contains(declared, live) -> list[str]:
    """Every path at which `declared` is not matched by `live`. Empty means declared_equal."""
    if isinstance(declared, dict):
        if not isinstance(live, dict):
            return [f"want an object, live is {type(live).__name__}"]
        bad = []
        for k, v in declared.items():
            if k not in live:
                bad.append(f".{k} absent live")
            else:
                bad += [f".{k}{p}" for p in _contains(v, live[k])]
        return bad
    if isinstance(declared, list):
        if not isinstance(live, list) or len(declared) != len(live):
            return [f" list of {len(declared)}, live {len(live) if isinstance(live, list) else type(live).__name__}"]
        bad = []
        for i, (d, l) in enumerate(zip(declared, live)):
            bad += [f"[{i}]{p}" for p in _contains(d, l)]
        return bad
    return [] if declared == live else [f" want {declared!r}, live {live!r}"]


def compare(declared: dict, live: dict) -> dict:
    """The two verdicts fact 4 records. See the ceiling in this module's docstring."""
    reduced = strip_server_fields(live)
    differences = _contains(declared, reduced)
    return {
        "declared_equal": not differences,
        "strict_equal": canonical(declared) == canonical(reduced),
        "differences": differences[:10],
    }


def render(ref: str | None = None) -> dict[str, dict]:
    """{key: object} -- the composed set as bytes, with no cluster in the loop."""
    paths = [f"{COMPOSED}/orphan-guard.yaml"]
    for version in versions(ref):
        paths += _ls(f"{COMPOSED}/policies/v{version}", ref)
    objects: dict[str, dict] = {}
    for path in paths:
        try:
            text = _read(path, ref)
        except (OSError, subprocess.CalledProcessError):
            continue
        for doc in yaml.safe_load_all(text):
            if isinstance(doc, dict) and doc.get("kind"):
                doc.setdefault("_source_path", path)
                objects[key(doc)] = doc
    return objects


def main(argv: list[str]) -> int:
    ref = None
    if "--ref" in argv:
        ref = argv[argv.index("--ref") + 1]
    objects = render(ref)
    if "--list" in argv:
        for k in sorted(objects):
            print(k)
        return 0
    for k in sorted(objects):
        obj = dict(objects[k])
        source = obj.pop("_source_path", "")
        print(json.dumps({"key": k, "source_path": source, "canonical": canonical(obj)},
                         sort_keys=True))
    return 0


def selfcheck() -> int:
    """One runnable check: the comparison is not vacuous in either direction."""
    declared = {"apiVersion": "v1", "kind": "ConfigMap",
                "metadata": {"name": "a", "labels": {"x": "1"}}, "data": {"k": "v"}}
    live = json.loads(json.dumps(declared))
    live["metadata"].update({"uid": "u", "resourceVersion": "9", "creationTimestamp": "t"})
    live["status"] = {"whatever": True}
    assert compare(declared, live)["declared_equal"], "server fields must not read as drift"
    assert compare(declared, live)["strict_equal"], "stripping must make the two identical"
    live["metadata"]["extraLabelHolder"] = "defaulted-by-the-server"
    got = compare(declared, live)
    assert got["declared_equal"] and not got["strict_equal"], "a live-only key is not drift, but it is not byte identity either"
    live["data"]["k"] = "tampered"
    assert not compare(declared, live)["declared_equal"], "a changed declared field IS drift"
    missing = json.loads(json.dumps(declared))
    del missing["data"]
    assert not compare(declared, missing)["declared_equal"], "an absent declared field IS drift"
    objects = render()
    assert objects, "the composed set rendered to nothing"
    print(f"ok  compare() bites both ways; the composed set renders {len(objects)} objects")
    return 0


if __name__ == "__main__":
    sys.exit(selfcheck() if "selfcheck" in sys.argv[1:] else main(sys.argv[1:]))
