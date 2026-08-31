#!/usr/bin/env python3
"""Print the rank-0 computed bump a signed evidence document records, and
refuse anything else.

verify-adopter-gate.sh's Scenario A needs the publisher's own gate to have
computed a bump that ranks 0, so the adopter's weaker-than-declared note fires
against a declared `minor`. Two different strings rank 0, and which one the
gate records depends on how it found its predecessor:

  "no predecessor"  the declared array gave it nothing to compare against
  "none"            ticket 43's tag-history fallback found the identical tree

The scenario asserts the value the gate ACTUALLY recorded rather than accepting
either, so a change that silently swapped one for the other still has to be
read and understood. Anything of a higher rank exits 1: Scenario A would then
be testing a case it was not built for, which is what happened on 2026-08-29
when a stale copy-from made 9.0.0 a real regression against its predecessor.

Usage:
    rank-zero-bump.py <evidence.json>
"""
import json
import sys
from pathlib import Path

RANK_ZERO = ("none", "no predecessor")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: rank-zero-bump.py <evidence.json>", file=sys.stderr)
        raise SystemExit(2)
    doc = json.loads(Path(sys.argv[1]).read_text())
    bump = doc["bump"]["computed"]
    if bump not in RANK_ZERO:
        print(f"evidence records computed bump {bump!r}; Scenario A needs one of "
              f"{RANK_ZERO} so the weaker-than-declared note fires", file=sys.stderr)
        raise SystemExit(1)
    print(bump)
