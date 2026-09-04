#!/usr/bin/env python3
"""verify-pinned-checkouts.py -- eco-system tickets 62 and 77.

The composing jobs check every cross-organisation parent out at the TAG one of this
repository's own GitRepository pin files names. A tag is what carries the publisher's
gitsign signature, so the tag -- not the SHA -- is what `ref:` says; this script closes
the other half of the {tag, commit} pair by asserting that the tree the runner actually
got is the commit the pin names. Without it the `commit:` field is decoration.

Exits non-zero with the reason on stderr; the workflow step it runs in is `set -euo
pipefail`, so a mismatch stops the job before anything is composed or tagged.

Usage: verify-pinned-checkouts.py <pin.yaml> <dir> [<pin.yaml> <dir> ...]
       verify-pinned-checkouts.py --selfcheck
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile

import yaml


def read_pin(path: str) -> tuple[str, str]:
    docs = [d for d in yaml.safe_load_all(open(path)) if d]
    ref = next(d for d in docs if d.get("kind") == "GitRepository")["spec"]["ref"]
    return ref["tag"], ref["commit"]


def head_of(directory: str) -> str:
    return subprocess.run(["git", "-C", directory, "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()


def check(pin_path: str, directory: str) -> str | None:
    """None when the checkout is at the pinned commit, else the reason it is not."""
    if not os.path.isdir(os.path.join(directory, ".git")):
        return f"{directory} is not a git checkout, so its commit cannot be read"
    tag, commit = read_pin(pin_path)
    head = head_of(directory)
    if head != commit:
        return (f"{directory} is at {head}, but {pin_path} pins {tag} at {commit} -- "
                f"the tag has been moved, or the checkout did not use the pin")
    return None


def main(argv: list[str]) -> int:
    pairs = list(zip(argv[1::2], argv[2::2]))
    if not pairs:
        print("usage: verify-pinned-checkouts.py <pin.yaml> <dir> [...]", file=sys.stderr)
        return 2
    bad = [r for r in (check(p, d) for p, d in pairs) if r]
    for reason in bad:
        print(f"REFUSED: {reason}", file=sys.stderr)
    for pin_path, directory in pairs:
        tag, commit = read_pin(pin_path)
        print(f"ok  {directory} is {tag} ({commit[:9]}) per {pin_path}")
    return 1 if bad else 0


def selfcheck() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        pin = os.path.join(tmp, "pin.yaml")
        repo = os.path.join(tmp, "repo")
        os.makedirs(repo)
        for cmd in (["init", "-q", "-b", "main"], ["config", "user.email", "s@e"],
                    ["config", "user.name", "s"]):
            subprocess.run(["git", "-C", repo] + cmd, check=True)
        open(os.path.join(repo, "f"), "w").write("x")
        subprocess.run(["git", "-C", repo, "add", "f"], check=True)
        subprocess.run(["git", "-C", repo, "commit", "-qm", "x"], check=True)
        sha = head_of(repo)
        body = ("apiVersion: source.toolkit.fluxcd.io/v1\nkind: GitRepository\n"
                "metadata: {{name: p}}\nspec:\n  ref:\n    tag: v1.0.0\n    commit: {c}\n")
        open(pin, "w").write(body.format(c=sha))
        assert check(pin, repo) is None, "a checkout at the pinned commit passes"
        open(pin, "w").write(body.format(c="0" * 40))
        reason = check(pin, repo)
        assert reason and "pins v1.0.0" in reason, reason
        assert "not a git checkout" in (check(pin, os.path.join(tmp, "nope")) or "")
    print("ok  selfcheck: matching commit passes; a moved tag and a missing checkout both refuse")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--selfcheck":
        selfcheck(); raise SystemExit(0)
    raise SystemExit(main(sys.argv))
