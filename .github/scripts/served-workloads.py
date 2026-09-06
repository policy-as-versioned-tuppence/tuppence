#!/usr/bin/env python3
"""The workload manifests this repository SERVES, one path per line.

Eco-system ticket 33. `gitops/flux-system/gotk-sync.yaml`'s Kustomization reconciles
`path: ./apps`, and kustomize accumulates exactly the entries of `gitops/apps/kustomization.yaml`'s
`resources[]` -- so the served set is that list, not a listing of the directory. A manifest sitting
in `gitops/apps/` that the kustomization does not name is served to nobody, and a shift-left gate
that globbed the directory would grade a file the cluster never sees while missing one it does.

Printed paths are relative to the directory given (default: this repository's root), so a CI job
that checked this repository out under a path prefix can pass that prefix and feed the result
straight to `platform/shift-left/ci-check.py --resource`.

Only workload manifests are printed: a resource carrying no
`policy-as-versioned.dev/policy-version` label is not a workload this gate has anything to say
about (ci-check.py itself calls that "unversioned -- out of scope"), and printing it would put
ConfigMaps and the Namespace through a pod check for no reason. A resource entry that is a
DIRECTORY, or a file this script cannot parse, is printed to stderr and exits 2 rather than being
skipped quietly: the point of the script is that the served set is known, so a served thing it
cannot account for is a failure, never a shrug.

    served-workloads.py                # paths relative to the repository root
    served-workloads.py --prefix tuppence
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

LABEL = "policy-as-versioned.dev/policy-version"
APPS = Path("gitops/apps")


def served(root: Path) -> tuple[list[str], list[str]]:
    """(workload paths relative to root, problems)."""
    k = root / APPS / "kustomization.yaml"
    if not k.is_file():
        return [], [f"{APPS}/kustomization.yaml is missing: nothing under {APPS} is served"]
    doc = yaml.safe_load(k.read_text()) or {}
    out: list[str] = []
    problems: list[str] = []
    for entry in doc.get("resources") or []:
        target = root / APPS / entry
        if target.is_dir():
            problems.append(f"{APPS}/{entry} is a directory; this script accounts for files only")
            continue
        if not target.is_file():
            problems.append(f"{APPS}/{entry} is named by the kustomization and does not exist")
            continue
        try:
            docs = [d for d in yaml.safe_load_all(target.read_text()) if d]
        except yaml.YAMLError as exc:
            problems.append(f"{APPS}/{entry} does not parse as YAML: {exc}")
            continue
        for d in docs:
            labels = ((d.get("metadata") or {}).get("labels") or {})
            if LABEL in labels:
                out.append(f"{APPS}/{entry}")
                break
    return out, problems


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2],
                    help="the repository root to read (default: this script's own repository)")
    ap.add_argument("--prefix", default="",
                    help="prepend this to every printed path (a CI checkout path)")
    args = ap.parse_args(argv)
    paths, problems = served(args.root)
    for p in problems:
        print(f"served-workloads: {p}", file=sys.stderr)
    for p in paths:
        print(f"{args.prefix.rstrip('/')}/{p}" if args.prefix else p)
    return 2 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
