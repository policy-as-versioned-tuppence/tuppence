#!/usr/bin/env python3
"""Released policy trees that carry no policy tag yet, newest last.

verify-adopter-gate.sh builds a throwaway release line and needs one release
that moves nothing, so the publisher's gate records a rank-0 bump. Since ticket
43 (2026-08-29) the gate falls back to the real TAG history for a predecessor
when the declared array holds one line, so a tree with no tag is not a
predecessor. In the real platform repo that leaves the newest tree (4.0.0)
invisible and the newest tagged version two majors behind, and any scratch
release rendered from today's authoring copies is honestly classified major.

The scenario uses this to bring its THROWAWAY clone to the state that exists
the moment the owner lets cut-release.yml sign the tag the repo is already
waiting for. It fakes no signature: a plain local git tag in a scratch repo is
not a release, and the real repo is never touched.

Usage:
    untagged-released-trees.py <repo-root>              # one version per line
    untagged-released-trees.py <repo-root> --newest-tree
"""
import re
import subprocess
import sys
from pathlib import Path

RELEASED = re.compile(r"v(\d+)\.(\d+)\.(\d+)$")
POLICY_TAG = re.compile(r"^policy/v(\d+\.\d+\.\d+)$")


def key(version: str) -> tuple:
    return tuple(int(p) for p in version.split("."))


def released_trees(repo: Path) -> list:
    policies = repo / "distribution" / "policies"
    found = [c.name[1:] for c in sorted(policies.iterdir())
             if c.is_dir() and RELEASED.fullmatch(c.name)]
    if not found:
        raise SystemExit(f"no released policy tree in {policies}")
    return sorted(found, key=key)


def tagged(repo: Path) -> set:
    out = subprocess.run(["git", "-C", str(repo), "tag", "-l", "policy/v*"],
                         capture_output=True, text=True, check=True).stdout
    return {m.group(1) for m in (POLICY_TAG.fullmatch(t.strip()) for t in out.splitlines()) if m}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: untagged-released-trees.py <repo-root> [--newest-tree]", file=sys.stderr)
        raise SystemExit(2)
    root = Path(sys.argv[1])
    trees = released_trees(root)
    if "--newest-tree" in sys.argv[2:]:
        print(trees[-1])
    else:
        have = tagged(root)
        for v in trees:
            if v not in have:
                print(v)
