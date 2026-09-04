#!/usr/bin/env python3
"""read-pins.py -- the composing jobs' pin reader: reads any number of GitRepository
pin files (gitops/platform/platform-pin.yaml, gitops/flux-system/gotk-sync-*.yaml) and
prints their tag/commit as GITHUB_OUTPUT-shaped lines.

Was read-two-pins.py until eco-system tickets 62 and 77 (2026-09-04), which pinned ico,
feeds and (on driftwood) insurer as well, so "two" stopped being true. Same contract,
any number of pairs.

Standalone rather than reusing any adopter's own adopter-gate.py: that script's CLI shape
has evolved independently per adopter (ticket cs-28's own module docstring says it is
built per institution) and is not uniform, so this avoids depending on it.

Usage: read-pins.py <path1> <prefix1> [<path2> <prefix2> ...]
Prints, per pair: <prefix>_tag=..., <prefix>_commit=...
"""
from __future__ import annotations

import sys

import yaml


def read_pin(path: str) -> tuple[str, str]:
    docs = [d for d in yaml.safe_load_all(open(path)) if d]
    ref = next(d for d in docs if d.get("kind") == "GitRepository")["spec"]["ref"]
    return ref["tag"], ref["commit"]


def main(argv: list[str]) -> int:
    pairs = list(zip(argv[1::2], argv[2::2]))
    if not pairs:
        print("usage: read-pins.py <path> <prefix> [<path> <prefix> ...]", file=sys.stderr)
        return 2
    for path, prefix in pairs:
        tag, commit = read_pin(path)
        print(f"{prefix}_tag={tag}")
        print(f"{prefix}_commit={commit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
