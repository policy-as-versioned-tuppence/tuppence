#!/usr/bin/env python3
"""read-two-pins.py -- ticket 18's compose-check job: reads two GitRepository
pin files (platform-pin.yaml, gotk-sync-nist.yaml) and prints their tag/commit
as GITHUB_OUTPUT-shaped lines.

Standalone rather than reusing any adopter's own adopter-gate.py: that
script's CLI shape has evolved independently per adopter (ticket cs-28's own
module docstring says it is built per institution) and is not uniform, so
this avoids depending on it.

Usage: read-two-pins.py <path1> <prefix1> <path2> <prefix2>
Prints: <prefix1>_tag=..., <prefix1>_commit=..., <prefix2>_tag=..., <prefix2>_commit=...
"""
from __future__ import annotations

import sys

import yaml


def read_pin(path: str) -> tuple[str, str]:
    docs = [d for d in yaml.safe_load_all(open(path)) if d]
    ref = next(d for d in docs if d.get("kind") == "GitRepository")["spec"]["ref"]
    return ref["tag"], ref["commit"]


def main(argv: list[str]) -> int:
    path1, prefix1, path2, prefix2 = argv[1:5]
    for path, prefix in ((path1, prefix1), (path2, prefix2)):
        tag, commit = read_pin(path)
        print(f"{prefix}_tag={tag}")
        print(f"{prefix}_commit={commit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
