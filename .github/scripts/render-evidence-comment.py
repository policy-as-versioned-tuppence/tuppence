#!/usr/bin/env python3
"""render-evidence-comment.py -- ticket cs-29: render the verified evidence
document into the Renovate bump pull request BODY, for a human reviewer.

Mechanism (spec.md, the reviewer user stories; "render... into the pull
request body"):

    Renders straight into the pull request BODY -- the literal thing the
    ticket's title and first acceptance-criterion line name -- not a
    comment. An earlier draft posted this as a PR comment instead, reasoning
    Renovate authors and can overwrite the PR body on every re-run of the
    same PR; a reviewer correctly flagged that as not satisfying the
    ticket's own words. That race doesn't actually apply: shift-left.yml is
    triggered BY the `pull_request` event Renovate's own push raises, so
    the workflow step always reads and splices onto Renovate's own body
    content AFTER Renovate has already settled it for that push, never
    before. wrap_section()/splice_body() below wrap the rendered evidence
    between HTML-comment markers and splice it into the PR's current body:
    appended after Renovate's own content on a first run, replacing only
    this gate's own prior span (never Renovate's content) on a re-run.

Reads adopter-gate.py's own --out summary (composed bump, retirements, and
every verified element's full evidence document -- never recomputed, never
re-derived here) and renders it for a human. No coverage PERCENTAGE appears
anywhere in this file, matching spec.md's own rule for the source document.

Usage:
    render-evidence-comment.py <adopter-summary.json>   # prints markdown to stdout
    render-evidence-comment.py wrap <in-file> <out-file>
    render-evidence-comment.py splice <current-body-file> <section-file> <out-body-file>
    render-evidence-comment.py --selfcheck               # runnable asserts
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Ticket cs-29: HTML-comment markers shift-left.yml greps out of the pull
# request's own CURRENT body to find (and replace) the span this gate owns,
# or append it if this is the first run on this PR. Kept identical (same
# literal marker strings) to ludlow's and driftwood's own copies, so the
# splice mechanism is genuinely "the identical change" across all three
# institutions, not just three independently-shaped body edits.
SECTION_START = "<!-- cs-29:adopter-gate:start -->"
SECTION_END = "<!-- cs-29:adopter-gate:end -->"
SECTION_PATTERN = re.compile(re.escape(SECTION_START) + r".*?" + re.escape(SECTION_END), re.DOTALL)


def _defuse_markers(markdown: str) -> str:
    """render() interpolates untrusted free text -- policy names, movement
    detail strings, refusal reasons, generator version strings -- sourced
    from platform's own committed evidence JSON, an institution this repo
    doesn't author and can't trust to never contain the literal marker
    strings (by accident, or a crafted policy/expression name upstream). If
    either marker string ever reached the body verbatim, SECTION_PATTERN's
    non-greedy DOTALL match would lock onto that accidental occurrence
    instead of the real one and splice_body would corrupt the section on the
    next re-run. Neutering both literal marker strings out of the rendered
    content here -- the one choke point every render() call passes through
    before wrap_section affixes the REAL markers -- guarantees the two
    markers this function adds are the only literal occurrences in the
    wrapped section, so the first-occurrence regex is safe again. Simpler
    and more robust than a per-render nonce: no backreference matching
    needed to find a prior run's span on re-run, and it can't be defeated by
    an upstream string that happens to collide."""
    return (markdown
            .replace(SECTION_START, "`[elided: literal marker text]`")
            .replace(SECTION_END, "`[elided: literal marker text]`"))


def wrap_section(markdown: str) -> str:
    return f"{SECTION_START}\n{_defuse_markers(markdown).rstrip()}\n{SECTION_END}\n"


def splice_body(current_body: str, section: str) -> str:
    """`section` is already wrap_section()'d output. Replaces a prior span
    between the markers in place (a re-run on the same pull request), or
    appends the whole marked section after whatever's there (the first run
    -- typically Renovate's own body)."""
    if SECTION_PATTERN.search(current_body):
        # A callable replacement, never a raw string: re.sub() treats a
        # string replacement's backslashes as backreferences/escapes (\1,
        # \g<name>, ...), and evidence content routinely carries a
        # Kyverno/CEL match expression or a refusal reason with a
        # backslash-digit sequence. A lambda sidesteps that interpretation
        # entirely; the replacement text lands verbatim, whatever it
        # contains.
        return SECTION_PATTERN.sub(lambda _m: section.rstrip(), current_body)
    # No COMPLETE start...end pair. GitHub caps pull request body length; a
    # long enough evidence render can get the body truncated by GitHub
    # mid-section -- SECTION_START saved, SECTION_END never reaches the
    # saved body. Treat an unpaired SECTION_START (found, with no END
    # anywhere after it) the same as a complete pair: replace from that
    # orphaned START to the end of the body, rather than appending past it
    # and accumulating a duplicate/orphaned span on every future run
    # forever -- ticket 29's own "stays diffable between releases" criterion.
    start_idx = current_body.find(SECTION_START)
    if start_idx != -1:
        prefix = current_body[:start_idx].rstrip()
        sep = "\n\n" if prefix else ""
        return prefix + sep + section
    sep = "\n\n" if current_body.strip() else ""
    return current_body.rstrip() + sep + section


def render(summary: dict) -> str:
    lines: list[str] = []
    lines.append("### computed-semver: verified evidence for this bump\n")
    lines.append(f"platform tag: `{summary['old_tag'] or '(none)'}` -> `{summary['new_tag']}`\n")
    lines.append("| | bump |")
    lines.append("| --- | --- |")
    lines.append(f"| **declared** (platform tag delta) | `{summary['declared']}` |")
    lines.append(f"| **composed** (this institution, over what this pull request adds and retires) "
                  f"| `{summary['composed']}` |")
    lines.append("")

    # Eco-system ticket 99: the fold's subject is the movement, so a pull request that moves
    # nothing renders as moving nothing rather than silently rendering an empty element list.
    if not summary["elements"] and not summary["retired"]:
        lines.append("This pull request adds and retires no policy version, so there is no movement "
                      "to compose. A major already standing in the composed window is reported by the "
                      "estate's own truth surface on every run, not here.")
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
            lines.append("| policy | verdict | entries | expressions |")
            lines.append("| --- | --- | --- | --- |")
            for m in doc["movement"]:
                entries = "; ".join(f"`{e}`" for e in m.get("entries", [])) or "-"
                exprs = "; ".join(f"`{e}`" for e in m.get("expressions", [])) or "-"
                lines.append(f"| `{m['policy']}` | {m['verdict']} | {entries} | {exprs} |")
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
    if argv[1:2] == ["wrap"]:
        if len(argv) != 4:
            print("usage: render-evidence-comment.py wrap <in-file> <out-file>", file=sys.stderr)
            return 2
        Path(argv[3]).write_text(wrap_section(Path(argv[2]).read_text()))
        return 0
    if argv[1:2] == ["splice"]:
        if len(argv) != 5:
            print("usage: render-evidence-comment.py splice <current-body-file> <section-file> <out-body-file>",
                  file=sys.stderr)
            return 2
        current = Path(argv[2]).read_text()
        section = Path(argv[3]).read_text()
        Path(argv[4]).write_text(splice_body(current, section))
        return 0
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
                "movement": [{"policy": "cage-tier.yaml", "verdict": "none",
                              "entries": ["workload-a"], "expressions": ["x == y"]}],
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
    assert "policy | verdict | entries | expressions" in out, "ticket 29: entries must sit alongside expressions"
    assert "`workload-a`" in out, "ticket 29: movement entries must be rendered, not dropped"
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

    # ---- wrap_section / splice_body (ticket cs-29's body-edit mechanism) ----
    renovate_body = "Bumps platform-pin.yaml from v1.0.0 to v1.1.0.\n\n---\n\n - [ ] <!-- rebase-check -->"
    section1 = wrap_section(out)
    spliced1 = splice_body(renovate_body, section1)
    assert renovate_body in spliced1, spliced1  # Renovate's own content survives
    assert spliced1.count(SECTION_START) == 1, spliced1
    section2 = wrap_section(out2)
    spliced2 = splice_body(spliced1, section2)
    assert renovate_body in spliced2, spliced2  # still untouched
    assert "cage-tier.yaml" not in spliced2, spliced2  # run 1's own span is GONE, not appended alongside
    assert "Retired, reaching this institution as major" in spliced2, spliced2
    assert spliced2.count(SECTION_START) == 1, spliced2  # replaced in place, never duplicated
    empty_first = splice_body("", section1)
    assert empty_first.startswith(SECTION_START), empty_first  # no spurious leading separator

    # ---- Bug 1 regression: injection-safety of the marker splice ----
    # Evidence text is untrusted, cross-org free text (policy names,
    # movement detail, refusal reasons, generator versions) -- this
    # institution doesn't author platform's evidence JSON and can't trust it
    # to never contain the literal END marker string. Prove it both ways:
    # the pre-fix wrap_section (reconstructed here, marker text passed
    # through unexamined) corrupts a re-run when that happens; the real,
    # fixed wrap_section (module-level, with _defuse_markers) doesn't.
    poisoned_fixture = {
        "old_tag": "v3.0.0", "new_tag": "v3.1.0", "declared": "minor", "composed": "none",
        "retired": [],
        "elements": [{
            "version": "9.1.0", "verified": True, "bump_computed": "none",
            "evidence": {
                "outcome": {"result": "refused",
                            "reason": f"lookalike text {SECTION_END} embedded in a refusal reason"},
                "bump": {"declared": "minor", "computed": "none"},
                "movement": [], "counts": {"old": 1, "new": 1, "union": 1},
                "not_looked_at": [], "limits": [], "matrix": {},
                "corpus_checksum": "sha256:poisoned", "generator_version": "0.1.2",
            },
        }],
    }
    poisoned = render(poisoned_fixture)
    assert SECTION_END in poisoned, "fixture must genuinely contain the literal marker or it tests nothing"

    def _unfixed_wrap_section(markdown: str) -> str:
        # the pre-fix implementation: marker text passed straight through
        return f"{SECTION_START}\n{markdown.rstrip()}\n{SECTION_END}\n"

    base_body = "Bumps platform-pin.yaml from v1.0.0 to v1.1.0."

    # Unfixed: run 1 splices the poisoned section in; run 2 (a re-run --
    # e.g. Renovate re-pushing the same PR) splices a clean section over it.
    bad_run1 = splice_body(base_body, _unfixed_wrap_section(poisoned))
    bad_run2 = splice_body(bad_run1, _unfixed_wrap_section(out))
    # Corrupted: the non-greedy match locked onto the FAKE end embedded in
    # the poisoned reason, so the real end marker and the unmatched tail of
    # run 1's own content leak straight through into the "replaced" body.
    assert bad_run2.count(SECTION_END) > 1, \
        "expected the unfixed path to leave a stray END marker behind -- fixture stopped exercising the bug"
    assert "embedded in a refusal reason" in bad_run2, \
        "expected leftover poisoned run-1 content to leak through on the unfixed path"

    # Fixed: identical two-run scenario through the module's real wrap_section.
    good_run1 = splice_body(base_body, wrap_section(poisoned))
    good_run2 = splice_body(good_run1, wrap_section(out))
    assert good_run2.count(SECTION_START) == 1, good_run2
    assert good_run2.count(SECTION_END) == 1, good_run2
    assert "embedded in a refusal reason" not in good_run2, \
        "run 1's poisoned content must be fully replaced by run 2, not leaked"
    assert "cage-tier.yaml" in good_run2, "run 2's real content must be present"
    assert base_body in good_run2, "Renovate's own content still untouched"

    # ---- Bug 2 regression: splice_body's re.sub() replacement was a raw
    # string, not a callable -- re.sub() specially interprets \1, \g<name>,
    # etc. IN a string replacement. The bug bites on a RE-RUN: the paired
    # regex has a prior span to replace, so splice_body calls
    # SECTION_PATTERN.sub(section, current_body), and if the NEW section
    # (a refusal reason or a Kyverno/CEL match expression containing a
    # backslash-digit sequence, e.g. `matches(image, 'C:\1\2\3')`) is the
    # replacement argument, that crashes with re.PatternError: invalid
    # group reference. (The first, appending run never calls re.sub() at
    # all, so it's never where this bug bites -- the crash needs an
    # existing span to replace, on the SECOND run's content.) Proved
    # against the real, module-level splice_body -- not a reconstruction.
    backslashy = r"policy `p.yaml` -- major -- via `matches(image, 'C:\1\2\3')`"
    assert re.search(r"\\\d", backslashy), "setup: fixture must actually contain a backslash-digit sequence"
    backslash_run1 = splice_body(base_body, wrap_section("first run, no backslashes"))
    assert backslash_run1.count(SECTION_START) == 1, backslash_run1
    backslash_run2 = splice_body(backslash_run1, wrap_section(backslashy))
    assert backslashy in backslash_run2, backslash_run2
    assert "first run, no backslashes" not in backslash_run2, backslash_run2
    assert backslash_run2.count(SECTION_START) == 1, backslash_run2
    assert base_body in backslash_run2, "Renovate's own content still untouched"
    # A THIRD run, replacing the backslash-bearing span with clean content,
    # must also survive -- the crash-on-re-run risk doesn't end after one
    # successful splice.
    backslash_run3 = splice_body(backslash_run2, wrap_section("run 3, still no crash"))
    assert backslashy not in backslash_run3, backslash_run3
    assert "run 3, still no crash" in backslash_run3, backslash_run3
    assert backslash_run3.count(SECTION_START) == 1, backslash_run3

    # ---- Bug 3 regression: an ORPHANED SECTION_START with no matching END
    # -- the shape GitHub's pull request body length cap leaves behind when
    # a long enough evidence render gets truncated mid-section on a prior
    # run. The paired-only regex found nothing on the next run, so
    # splice_body used to APPEND a fresh section past the orphaned one
    # instead of replacing it -- duplicate/orphaned blocks would accumulate
    # forever, never diffable again (ticket 29's own criterion). Confirm
    # first the paired regex genuinely can't see it, then confirm the real
    # splice_body repairs it in place, across two consecutive
    # truncate/repair cycles.
    truncated_evidence = "evidence that never reached its own closing marker"
    truncated_body = base_body + "\n\n" + SECTION_START + "\n" + truncated_evidence
    assert SECTION_PATTERN.search(truncated_body) is None, \
        "setup: the paired start...end regex must NOT find a complete span in a truncated body"
    repaired = splice_body(truncated_body, wrap_section("recovered evidence, run 2"))
    assert repaired.count(SECTION_START) == 1, repaired  # not duplicated/stacked
    assert truncated_evidence not in repaired, repaired  # orphaned span replaced, not appended-past
    assert "recovered evidence, run 2" in repaired, repaired
    assert base_body in repaired, repaired  # Renovate's own content still untouched
    assert repaired.rstrip().endswith(SECTION_END), repaired  # well-formed again after repair

    # A second truncation-then-repair cycle must not re-accumulate either.
    re_truncated = repaired.split(SECTION_END)[0] + "\nsomehow truncated again"
    assert SECTION_PATTERN.search(re_truncated) is None, "setup: second truncation must also break the pair"
    re_repaired = splice_body(re_truncated, wrap_section("recovered evidence, run 3"))
    assert re_repaired.count(SECTION_START) == 1, re_repaired
    assert "recovered evidence, run 3" in re_repaired, re_repaired
    assert base_body in re_repaired, re_repaired

    print("OK: render-evidence-comment.py selfcheck (declared/composed, movement entries+expressions, "
          "holes, limits, matrix, checksum+generator all present; no coverage percentage anywhere; "
          "retirement path "
          "renders too; wrap_section/splice_body append on a first run and replace in place on a "
          "re-run without touching Renovate's own body content; survives backslash-bearing evidence "
          "across two consecutive re-runs without re.sub() misreading it as a backreference; repairs "
          "an ORPHANED SECTION_START -- a GitHub PR-body-truncation shape -- in place across repeated "
          "truncate/repair cycles instead of accumulating duplicate spans)")


if __name__ == "__main__":
    sys.exit(main(sys.argv))
