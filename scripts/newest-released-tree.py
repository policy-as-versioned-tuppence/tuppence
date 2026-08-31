#!/usr/bin/env python3
"""The version cut-release-gate.py would pick as a predecessor: the newest one
that has BOTH a released tree on disk AND a real policy tag.

verify-adopter-gate.sh's Scenario A renders a throwaway v9.0.0 that must move
NOTHING, so the publisher's gate computes a rank-0 bump and the adopter's
weaker-than-declared note fires. Which body it copies must therefore be the
body the gate will compare it against, and that is not simply the newest
directory: on 2026-08-29 ticket 43 taught cut-release-gate.py to fall back to
the real TAG history when the declared array holds one line

    released_trees = [v for v in legal_history if (policies / f"v{v}").is_dir()]

so a version whose tree exists but whose tag has never been cut -- 4.0.0, which
waits on the owner letting cut-release.yml run -- is not a predecessor. Picking
it would make 9.0.0 a real regression against 3.0.0 and the scenario would fail
on its own scaffolding, which is exactly what happened when the copy-from was
the hardcoded literal "3.0.0" and the authoring copies moved on to the 4.0.0
cage underneath it.

Prereleases are excluded: a degraded publish (ticket 43) is not a body a
scratch release should copy.

Usage:
    newest-released-tree.py <repo-root>
"""
import re
import subprocess
import sys
from pathlib import Path

RELEASED = re.compile(r"v(\d+)\.(\d+)\.(\d+)$")
POLICY_TAG = re.compile(r"^policy/v(\d+\.\d+\.\d+)$")


def tagged_versions(repo: Path) -> set:
    out = subprocess.run(["git", "-C", str(repo), "tag", "-l", "policy/v*"],
                         capture_output=True, text=True, check=True).stdout
    return {m.group(1) for m in (POLICY_TAG.fullmatch(t.strip()) for t in out.splitlines()) if m}


def newest_with_tag_and_tree(repo: Path) -> str:
    policies = repo / "distribution" / "policies"
    tagged = tagged_versions(repo)
    found = []
    for child in sorted(policies.iterdir()):
        if not child.is_dir():
            continue
        m = RELEASED.fullmatch(child.name)
        if m and child.name[1:] in tagged:
            found.append((tuple(int(g) for g in m.groups()), child.name[1:]))
    if not found:
        raise SystemExit(
            f"no version in {policies} has both a released tree and a policy tag; "
            "Scenario A cannot build a release that moves nothing")
    return max(found)[1]


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: newest-released-tree.py <repo-root>", file=sys.stderr)
        raise SystemExit(2)
    print(newest_with_tag_and_tree(Path(sys.argv[1])))
