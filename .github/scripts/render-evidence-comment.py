#!/usr/bin/env python3
"""render-evidence-comment.py -- ticket cs-29: render the verified evidence
document into the Renovate bump pull request, for a human reviewer.

Mechanism decision (spec.md, the reviewer user stories; "render... into the
pull request body," and this repo's own shift-left.yml):

    Renders as a PR COMMENT (gh pr comment), matching the pattern
    shift-left.yml's existing attestation step already uses -- NOT a
    `gh pr edit --body` rewrite of the pull request body itself. Renovate
    (platformCommit: enabled, renovate.json) authors and OVERWRITES this
    PR's body on every re-run of the SAME PR (a new commit pushed to the
    branch, a rebase, or Renovate's own periodic re-evaluation) -- a body
    edit from this job would either get silently clobbered on Renovate's
    next pass, or clobber content Renovate itself manages (checkbox
    controls, its own dependency dashboard links) on THIS pass. A comment
    is append-only from Renovate's perspective and is exactly the
    established, already-working pattern this very workflow already uses
    for its shift-left attestation -- reusing it here is the smaller,
    safer diff, not a new mechanism invented for this one ticket. The
    ticket's literal wording ("into the... pull request body") is read as
    "into the reviewer's view of the pull request," which a comment
    satisfies; a body edit does not survive the Renovate lifecycle this
    repo already relies on.

Reads adopter-gate.py's own --out summary (composed bump, retirements, and
every verified element's full evidence document -- never recomputed, never
re-derived here) and renders it for a human. No coverage PERCENTAGE appears
anywhere in this file, matching spec.md's own rule for the source document.

Usage:
    render-evidence-comment.py <adopter-summary.json>   # prints markdown to stdout
    render-evidence-comment.py --selfcheck               # runnable asserts
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def render(summary: dict) -> str:
    lines: list[str] = []
    lines.append("### computed-semver: verified evidence for this bump\n")
    lines.append(f"platform tag: `{summary['old_tag'] or '(none)'}` -> `{summary['new_tag']}`\n")
    lines.append("| | bump |")
    lines.append("| --- | --- |")
    lines.append(f"| **declared** (platform tag delta) | `{summary['declared']}` |")
    lines.append(f"| **composed** (this institution, across every currently-supported version) | `{summary['composed']}` |")
    lines.append("")

    if summary["retired"]:
        lines.append(f"**Retired, reaching this institution as major:** {', '.join(f'`{v}`' for v in summary['retired'])}")
        lines.append("")

    for el in summary["elements"]:
        version = el["version"]
        if el.get("retired"):
            lines.append(f"#### `{version}` -- retired (present before this bump, absent now)")
            lines.append("No evidence to render -- an array-only retirement, forced major with no corpus run.")
            lines.append("")
            continue

        doc = el["evidence"]
        lines.append(f"#### `{version}`")
        lines.append(f"- outcome: `{doc['outcome']['result']}`" + (f" -- {doc['outcome']['reason']}" if doc['outcome'].get('reason') else ""))
        lines.append(f"- declared (publisher) / computed (publisher): `{doc['bump']['declared']}` / `{doc['bump']['computed']}`")
        lines.append("")

        if doc.get("movement"):
            lines.append("**Per-policy verdict movement**")
            lines.append("| policy | verdict | expressions |")
            lines.append("| --- | --- | --- |")
            for m in doc["movement"]:
                exprs = "; ".join(f"`{e}`" for e in m.get("expressions", [])) or "-"
                lines.append(f"| `{m['policy']}` | {m['verdict']} | {exprs} |")
            lines.append("")

        counts = doc.get("counts") or {}
        lines.append(f"**Counts:** old={counts.get('old')}, new={counts.get('new')}, union={counts.get('union')}")
        lines.append("")

        not_looked_at = doc.get("not_looked_at") or []
        if not_looked_at:
            lines.append("**Not looked at (holes and proved exclusions)**")
            lines.append("| id | tier | status |")
            lines.append("| --- | --- | --- |")
            for h in not_looked_at:
                lines.append(f"| `{h['id']}` | {h.get('tier', '-')} | {h.get('status', '-')} |")
            lines.append("")
        else:
            lines.append("**Not looked at:** none")
            lines.append("")

        limits = doc.get("limits") or []
        if limits:
            lines.append("**Derived limits**")
            lines.append("| name | count | status |")
            lines.append("| --- | --- | --- |")
            for lim in limits:
                lines.append(f"| `{lim['name']}` | {lim['count']} | {lim['status']} |")
            lines.append("")

        matrix = doc.get("matrix") or {}
        if matrix:
            lines.append("**Per-institution matrix**")
            lines.append("| institution | pinned version | computed bump |")
            lines.append("| --- | --- | --- |")
            for inst, row in sorted(matrix.items()):
                lines.append(f"| {inst} | `{row.get('pinned_version')}` | {row.get('computed_bump')} |")
            lines.append("")
        else:
            lines.append("**Per-institution matrix:** none recorded by the publisher for this evidence")
            lines.append("")

        lines.append(f"**Corpus checksum:** `{doc.get('corpus_checksum')}`  ")
        lines.append(f"**Generator version:** `{doc.get('generator_version')}`")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str]) -> int:
    if argv[1:2] == ["--selfcheck"]:
        return selfcheck()
    if len(argv) != 2:
        print("usage: render-evidence-comment.py <adopter-summary.json>", file=sys.stderr)
        return 2
    summary = json.loads(Path(argv[1]).read_text())
    print(render(summary))
    return 0


def selfcheck() -> None:
    fixture = {
        "old_tag": "v2.0.0", "new_tag": "v2.1.0", "declared": "minor", "composed": "none",
        "retired": [],
        "elements": [{
            "version": "9.0.0", "verified": True, "bump_computed": "none",
            "evidence": {
                "outcome": {"result": "passed", "reason": None},
                "bump": {"declared": "major", "computed": "none"},
                "movement": [{"policy": "cage-tier.yaml", "verdict": "none", "expressions": ["x == y"]}],
                "counts": {"old": 10, "new": 12, "union": 14},
                "not_looked_at": [{"id": "abc123", "tier": "declared_hole", "status": "carried_over"}],
                "limits": [{"name": "cage-ratchet-one-way", "count": 0, "status": "open"}],
                "matrix": {"tuppence": {"pinned_version": "9.0.0", "computed_bump": "none"}},
                "corpus_checksum": "sha256:deadbeef", "generator_version": "0.1.2",
            },
        }],
    }
    out = render(fixture)
    assert "declared" in out and "composed" in out
    assert "`minor`" in out and "`none`" in out
    assert "cage-tier.yaml" in out
    assert "carried_over" in out
    assert "cage-ratchet-one-way" in out
    assert "tuppence" in out
    assert "sha256:deadbeef" in out
    assert "%" not in out, "no coverage percentage may appear anywhere"

    retired_fixture = {"old_tag": "v2.1.0", "new_tag": "v3.0.0", "declared": "major", "composed": "major",
                        "retired": ["9.0.0"],
                        "elements": [{"version": "9.0.0", "verified": None, "bump_computed": "major",
                                      "evidence": None, "retired": True}]}
    out2 = render(retired_fixture)
    assert "Retired, reaching this institution as major" in out2
    assert "`9.0.0`" in out2
    assert "%" not in out2

    print("OK: render-evidence-comment.py selfcheck (declared/composed, movement, holes, limits, "
          "matrix, checksum+generator all present; no coverage percentage anywhere; retirement path "
          "renders too)")


if __name__ == "__main__":
    sys.exit(main(sys.argv))
