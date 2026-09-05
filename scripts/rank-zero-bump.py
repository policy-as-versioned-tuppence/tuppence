#!/usr/bin/env python3
"""Print the computed bump a signed evidence document records, provided it is
weaker than the declared `minor`, and refuse anything else.

verify-adopter-gate.sh's Scenario A2 (Scenario A until eco-system ticket 99 moved
the arrival case there) needs the publisher's own gate to have computed a bump
weaker than the declared one, so the adopter's weaker-than-declared note fires. Three strings are weaker than `minor`, and which one the
gate records depends on how it found its predecessor:

  "no predecessor"  the declared array gave it nothing to compare against
  "none"            ticket 43's tag-history fallback found the identical tree
  "patch"           it found a real predecessor and a real, small movement

The scenario asserts the value the gate ACTUALLY recorded rather than accepting
either, so a change that silently swapped one for the other still has to be
read and understood. Anything of a higher rank exits 1: Scenario A2 would then
be testing a case it was not built for, which is what happened on 2026-08-29
when a stale copy-from made 9.0.0 a real regression against its predecessor.

Usage:
    rank-zero-bump.py <evidence.json>
"""
import json
import sys
from pathlib import Path

# Anything the adopter gate ranks BELOW the declared `minor`. Scenario A2 needs
# the weaker-than-declared note to fire, and that is a comparison against the
# declared bump, not a demand for a particular value. Pinning it to rank 0 was
# too tight: on 2026-08-31, once the throwaway line cut its own tags, 9.0.0's
# real predecessor changed and the gate honestly computed `patch` -- still
# weaker than `minor`, so the note fires exactly as the scenario needs, and the
# check failed on its own over-specification rather than on anything real.
WEAKER_THAN_MINOR = ("none", "no predecessor", "patch")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: rank-zero-bump.py <evidence.json>", file=sys.stderr)
        raise SystemExit(2)
    doc = json.loads(Path(sys.argv[1]).read_text())
    bump = doc["bump"]["computed"]
    if bump not in WEAKER_THAN_MINOR:
        print(f"evidence records computed bump {bump!r}; Scenario A2 needs one of "
              f"{WEAKER_THAN_MINOR}, all weaker than the declared bump, so the "
              f"weaker-than-declared note fires", file=sys.stderr)
        raise SystemExit(1)
    print(bump)
