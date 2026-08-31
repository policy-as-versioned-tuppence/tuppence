#!/usr/bin/env python3
"""adopter-gate.py -- ticket cs-28: the adopter gate, run from shift-left.yml
on the Renovate bump pull request that edits gitops/platform/platform-pin.yaml.

Fixes the two live bugs spec.md names (Further Notes, "Two live bugs"):

  1. Checks out platform at the TAG the pull request head names (`--new-tag`),
     never platform's default branch.
  2. Verifies the resolved commit against platform-pin.yaml's own pinned
     `commit` field (`--new-commit`) and refuses on any disagreement -- this
     is what makes ADR-0001's belt-and-braces commit pin load-bearing
     instead of decorative.

It does not recompute the publisher's bump ("a second answer to the same
question has no tie-breaker" -- spec.md, Solution). It verifies the
publisher's signed evidence -- cosign verify-blob, offline, identity-pinned
to a constant THIS repo holds (`--identity-regexp` / `--issuer`, wired from
shift-left.yml's own env block, never read from anything platform supplies)
-- then reads that evidence's own `bump.computed` field for every policy
version distribution/versions.yaml's array currently supports. Composition,
for tuppence's single pinned party (platform), is exactly this: the
strictest of

  * every currently-supported array element's own verified `bump.computed`,
  * MAJOR for every version present in the OLD array (as pinned before this
    PR) and absent from the NEW array -- a retirement, forced major with no
    special case, exactly comparison_window.py's own rule one level up
    (spec.md: "a retired version reaches the institution as major").

against the DECLARED bump -- the plain semver delta of platform's own pinned
tag (old -> new), visible directly in the PR diff, no evidence needed to
read it.

Cross-party composition (more than one policy-bearing party) is explicitly
out of scope for this whole effort (spec.md, "Out of Scope";
.scratch/policy-composition/map.md). tuppence pins exactly one such party --
platform -- so "the institution's own composed bump" here IS "platform's own
computed bump, re-verified", never a general N-party merge.

Usage:
    adopter-gate.py \
        --platform-dir DIR --new-pin-yaml tuppence/gitops/platform/platform-pin.yaml \
        --old-pin-yaml FILE_OR_EMPTY \
        --identity-regexp REGEXP --issuer ISSUER \
        --out evidence-summary.json
    adopter-gate.py --selfcheck    # runnable asserts, no network, no cosign
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import tempfile
import subprocess
import sys
from pathlib import Path

import yaml


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def ensure_tag(platform_dir: Path, tag: str) -> bool:
    """The tag is already present locally (a full/local clone -- true for
    every offline-twin scenario this repo's own tests build) -> use it as
    is. Otherwise fetch it from `origin` (the shallow clone shape
    `actions/checkout` actually leaves in CI). Returns False, never raising,
    when neither has it -- callers decide what an absent tag means for them
    (a missing NEW tag is a hard refusal; a missing OLD tag is "no
    predecessor recorded")."""
    if _git(platform_dir, "rev-parse", "-q", "--verify", f"refs/tags/{tag}").returncode == 0:
        return True
    fetched = _git(platform_dir, "fetch", "--depth", "1", "origin", f"+refs/tags/{tag}:refs/tags/{tag}")
    return fetched.returncode == 0


def checkout_tag(platform_dir: Path, tag: str) -> None:
    """Live bug #1's fix: check out platform at the exact tag the pull
    request head names -- never the branch `actions/checkout` left it on."""
    if not ensure_tag(platform_dir, tag):
        raise SystemExit(f"REFUSED: could not find or fetch platform tag {tag!r}")
    co = _git(platform_dir, "checkout", "--quiet", tag)
    if co.returncode != 0:
        raise SystemExit(f"REFUSED: could not check out platform tag {tag!r}: {co.stderr.strip()}")


def resolved_commit(platform_dir: Path) -> str:
    out = _git(platform_dir, "rev-parse", "HEAD")
    if out.returncode != 0:
        raise SystemExit(f"REFUSED: could not resolve platform HEAD: {out.stderr.strip()}")
    return out.stdout.strip()


def parse_pin(pin_yaml_text: str) -> tuple[str, str]:
    """gitops/platform/platform-pin.yaml -> (tag, commit).

    The real committed file is a TWO-document YAML stream (GitRepository,
    then a Kustomization, separated by `---`) -- confirmed directly against
    gitops/platform/platform-pin.yaml itself, which is what shift-left.yml
    actually hands this function on every single PR (both as --new-pin-yaml
    and, via `git show`, as --old-pin-yaml). `yaml.safe_load()` is a
    single-document loader and raises ComposerError on that file; platform's
    own shift-left/ci-check.py:target_version() already established the
    fix for this exact multi-document shape (`yaml.safe_load_all`, skipping
    blank documents) -- reused here rather than re-solving it. The tag/commit
    live on the GitRepository document (the one with `.spec.ref`); the
    Kustomization document has no `ref` and is skipped."""
    for doc in yaml.safe_load_all(pin_yaml_text):
        if doc and "ref" in doc.get("spec", {}):
            ref = doc["spec"]["ref"]
            return ref["tag"], ref["commit"]
    raise SystemExit("REFUSED: no document with spec.ref (tag/commit) found in pin YAML")


def _import_by_path(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def array_at_worktree(platform_dir: Path) -> dict[str, dict]:
    """distribution/versions.yaml's array, keyed by version -- read through
    platform's OWN render-orphan-guard.elements(), the one parse point
    platform's own tooling already uses (shift-left/ci-check.py reuses the
    sibling `versions()` the same way). Reused here rather than a second,
    hand-rolled YAML-array parser."""
    rog = _import_by_path("render_orphan_guard", platform_dir / "distribution" / "render-orphan-guard.py")
    els = rog.elements(platform_dir / "distribution" / "versions.yaml")
    return {e["version"]: e for e in els}


def array_at_ref(platform_dir: Path, ref: str) -> dict[str, dict]:
    """The same array, read from a git ref's tree without disturbing the
    current worktree checkout (`git show`) -- used for the OLD tag, so the
    NEW tag stays checked out throughout for every other step."""
    if not ensure_tag(platform_dir, ref):
        # No predecessor tag reachable (e.g. a tag cut before versions.yaml
        # existed, or the institution's very first pin) -- treat as an empty
        # prior array. Nothing "retires" out of a baseline nobody recorded.
        return {}
    show = _git(platform_dir, "show", f"{ref}:distribution/versions.yaml")
    if show.returncode != 0:
        return {}
    doc = yaml.safe_load(show.stdout)
    try:
        versions = doc["spec"]["inputs"][0]["versions"]
    except (KeyError, IndexError, TypeError):
        return {}
    return {e["version"]: e for e in versions}


def versions_from_composed_evidence(adopter_dir: Path, ref: str) -> dict[str, dict]:
    """ADR-0011 (policy-composition ticket 18): 'the adopter gate reads the
    composed artefact as its subject.' The set of live policy versions
    THIS institution's own signed composed/evidence.json records as
    members, at `ref` (a commit-ish in tuppence's own repo -- ticket 18's
    compose-check job keeps that file fresh and byte-verified on every pull
    request). Returned dict-shaped (version -> {}) to match
    array_at_worktree/array_at_ref's own return shape -- compose() below
    only ever reads the KEYS of either. A platform-machinery member (the
    orphan guard, the governed-namespace guard) carries no `version` --
    excluded, same as distribution/versions.yaml's own array never lists it
    either."""
    show = _git(adopter_dir, "show", f"{ref}:composed/evidence.json")
    if show.returncode != 0:
        raise SystemExit(
            f"REFUSED: could not read composed/evidence.json at {ref!r} in tuppence's own repo: "
            f"{show.stderr.strip()}"
        )
    doc = json.loads(show.stdout)
    return {m["version"]: {} for m in doc["members"] if m.get("version") is not None}


TAG_VERSION_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")


def classify_tag_bump(old_tag: str | None, new_tag: str) -> str:
    """The DECLARED bump -- pure semver delta of platform's own pinned tag,
    old -> new. Visible straight from the PR diff; no evidence needed to
    read it. "no predecessor" when there is no old tag at all (the
    institution's first-ever pin). "none" when old and new are the SAME tag
    -- shift-left.yml runs with no `paths:` filter on purpose (its own
    header comment: "this check must report a status on every PR"), so this
    is the ordinary case for the large majority of PRs, which never touch
    gitops/platform/platform-pin.yaml at all: the PR base and PR head copies
    of the pin are byte-identical, old_tag == new_tag, and that must be a
    real no-op classification, not a refusal -- only an actual BACKWARDS
    move is a refusal."""
    if old_tag is None:
        return "no predecessor"
    om, on = TAG_VERSION_RE.match(old_tag), TAG_VERSION_RE.match(new_tag)
    if not om or not on:
        raise SystemExit(f"REFUSED: platform tag not a plain vMAJOR.MINOR.PATCH: {old_tag!r} -> {new_tag!r}")
    old_v, new_v = tuple(int(x) for x in om.groups()), tuple(int(x) for x in on.groups())
    if new_v == old_v:
        return "none"
    if new_v < old_v:
        raise SystemExit(f"REFUSED: proposed platform tag {new_tag!r} does not move forward from {old_tag!r}")
    leftmost = next(i for i in range(3) if new_v[i] != old_v[i])
    return ("major", "minor", "patch")[leftmost]


def verify_evidence(platform_dir: Path, version: str, identity_regexp: str, issuer: str,
                     skip_cosign_verify: bool = False) -> dict:
    """cosign verify-blob, offline, identity-pinned to THIS institution's own
    constant -- never discovered from anything platform supplies. Returns
    the parsed evidence document on success; raises SystemExit (refusal) on
    any missing file or failed verification.

    `skip_cosign_verify`: TEST-ONLY escape hatch, never set by shift-left.yml
    (mirrors platform's own CUT_RELEASE_TEST_MODE: it wraps only the cosign
    subprocess call, never the file-existence checks or the decision logic
    around it). A real keyless signature needs a live Fulcio-issued
    certificate from GitHub Actions' ambient OIDC -- confirmed unavailable
    here directly (`cosign sign-blob --yes` hangs on the interactive flow
    until it times out; even a LOCAL key pair still requires reaching
    Sigstore's TUF CDN for the mandatory bundle-format signing config, also
    confirmed unreachable from this sandbox by a direct dial timeout) -- the
    same CI-only boundary cs-13's and cs-27's own offline twins already
    disclosed, now confirmed one layer deeper. `cosign verify-blob` itself
    DOES run for real here and DOES correctly refuse (proved in
    verify-adopter-gate.sh's Scenarios C and D, against a real missing-file
    case and a real malformed-bundle case, each with the real binary) --
    it is only the SIGN side, needed to build a fixture with a genuinely
    ACCEPTED signature, that this sandbox cannot produce. The
    identity-regexp STRING itself (anchoring, escaping, and "a platform
    workflow rename breaks verification") is proved separately and
    deterministically in verify-identity-regexp.sh, with no cosign process
    involved at all."""
    evidence = platform_dir / "computed-semver" / "evidence" / f"{version}.json"
    bundle = evidence.with_name(evidence.name + ".bundle")
    if not evidence.exists():
        raise SystemExit(
            f"REFUSED: no signed evidence committed for policy version {version} at "
            f"computed-semver/evidence/{version}.json -- the institution cannot trust an "
            f"unverified bump"
        )
    if not bundle.exists():
        raise SystemExit(f"REFUSED: evidence for {version} has no cosign bundle at {bundle.name}")
    if not skip_cosign_verify:
        verify = subprocess.run(
            ["cosign", "verify-blob", f"--bundle={bundle}",
             f"--certificate-identity-regexp={identity_regexp}",
             f"--certificate-oidc-issuer={issuer}", str(evidence)],
            capture_output=True, text=True,
        )
        if verify.returncode != 0:
            raise SystemExit(
                f"REFUSED: cosign verify-blob failed for policy version {version} evidence "
                f"(identity {identity_regexp!r}): {verify.stderr.strip()}"
            )
    return json.loads(evidence.read_text())


RANK = {"none": 0, "no predecessor": 0, "patch": 1, "minor": 2, "major": 3}


def compose(platform_dir: Path, new_array: dict[str, dict], old_array: dict[str, dict],
            identity_regexp: str, issuer: str, skip_cosign_verify: bool = False) -> dict:
    retired = sorted(set(old_array) - set(new_array))
    elements = []
    worst = "none"
    worst_rank = -1  # sentinel below every real RANK value (including "none"/"no predecessor" at 0)
    # so the FIRST real element always sets `worst` -- a plain `> RANK[worst]`
    # comparison seeded at "none" would silently swallow a genuine "no
    # predecessor" first element (same rank 0 as the placeholder, so `>`
    # never fires and the placeholder string wins over the real one).
    for version in sorted(new_array):
        doc = verify_evidence(platform_dir, version, identity_regexp, issuer,
                               skip_cosign_verify=skip_cosign_verify)
        computed = doc["bump"]["computed"]
        elements.append({"version": version, "verified": True, "bump_computed": computed, "evidence": doc})
        if RANK.get(computed, 0) >= worst_rank:
            worst_rank = RANK.get(computed, 0)
            worst = computed
    for version in retired:
        elements.append({"version": version, "verified": None, "bump_computed": "major",
                          "evidence": None, "retired": True})
        worst = "major"
    return {"composed": worst, "retired": retired, "elements": elements}


PARTY = "tuppence"

# --------------------------------------------------------------------------
# Ticket 43 (ticket 18 Answer 4): the per-institution matrix row, computed
# HERE, by the adopter.
#
# The publisher's `matrix` is empty and says so: NORTH-STAR §2 forbids
# platform reading this repository, and a hub-maintained pins file is the
# central catalogue ticket 04 refused. So the row about tuppence's own pin is
# computed by tuppence, running platform's PUBLISHED computed-semver package
# against tuppence's OWN claimed policy versions, with tuppence's OWN workloads
# added to the generated corpus, and lands in tuppence's own composed
# evidence.
#
# This is not "recomputing the publisher's answer" (ADR-0011 still holds):
# the publisher's number is the strictest band across its whole window, and
# this is the band for ONE pin -- the one this institution is actually
# running. Two different questions, and only the adopter can ask the second,
# because only the adopter knows what it claims and what it runs.
# --------------------------------------------------------------------------
CLAIM_LABEL = "policy-as-versioned.dev/policy-version"
GOVERNED_LABEL = "policy-as-versioned.dev/governed"


def _docs(path: Path) -> list[dict]:
    try:
        return [d for d in yaml.safe_load_all(path.read_text()) if isinstance(d, dict)]
    except (yaml.YAMLError, UnicodeDecodeError):
        return []


def claimed_versions(adopter_dir: Path) -> dict[str, list[Path]]:
    """Every policy version THIS repository's own manifests claim, and the
    workload files claiming it. Read here, never from the publisher: the row
    is about what this institution actually runs. `composed/` is skipped --
    those are the rendered policy bodies, not workloads."""
    claims: dict[str, list[Path]] = {}
    for path in sorted(adopter_dir.rglob("*.yaml")):
        if ".git" in path.parts or "composed" in path.parts:
            continue
        for doc in _docs(path):
            if doc.get("kind") != "Pod":
                continue
            version = ((doc.get("metadata") or {}).get("labels") or {}).get(CLAIM_LABEL)
            if version:
                claims.setdefault(str(version), []).append(path)
    return claims


def governed_namespace(adopter_dir: Path) -> dict | None:
    """This institution's own governed Namespace manifest -- the object that
    declares the cage tier (ADR-0022). It rides beside every extra corpus
    entry as the `.ns.yaml` sibling cage_engine.namespace_for reads, so the
    workload is classified in the cage it really runs in, not in the
    unlabelled default."""
    for path in sorted(adopter_dir.rglob("*.yaml")):
        if ".git" in path.parts:
            continue
        for doc in _docs(path):
            if doc.get("kind") == "Namespace" and \
                    ((doc.get("metadata") or {}).get("labels") or {}).get(GOVERNED_LABEL) == "true":
                return doc
    return None


def matrix_row(platform_dir: Path, adopter_dir: Path, party: str = PARTY) -> dict:
    """One row per policy version this institution claims: the bump IT takes
    moving from its own pin to the version the publisher's array now
    declares, computed with the published package over the published corpus
    plus this institution's own workloads."""
    sys.path.insert(0, str(Path(platform_dir) / "computed-semver"))
    import comparison_window          # noqa: E402  -- the PUBLISHED package
    import corpus_generator           # noqa: E402

    dist = Path(platform_dir) / "distribution"
    array = [str(e["version"])
             for e in corpus_generator._orphan_guard.elements(dist / "versions.yaml")]
    if not array:
        raise SystemExit("FAIL: platform's versions.yaml declares no versions")
    declared = max(array, key=comparison_window.parse_semver)
    tree_for = lambda v: dist / "policies" / f"v{v}"          # noqa: E731
    ns = governed_namespace(Path(adopter_dir))

    rows: dict[str, dict] = {}
    for version, workloads in sorted(claimed_versions(Path(adopter_dir)).items(),
                                      key=lambda kv: comparison_window.parse_semver(kv[0])):
        relative = [str(w.relative_to(adopter_dir)) for w in workloads]
        if version not in array:
            rows[version] = {
                "pinned_version": version, "computed_bump": None, "movement": [],
                "extra_corpus_entries": relative,
                "note": (f"{version} is not in the publisher's declared version array "
                         f"({', '.join(array)}) -- it is retired or was never published, so there "
                         f"is no line to classify. This institution is claiming a version nothing "
                         f"serves; that is the row, not a missing row."),
            }
            continue
        if comparison_window.parse_semver(version) >= comparison_window.parse_semver(declared):
            rows[version] = {
                "pinned_version": version, "computed_bump": "none", "movement": [],
                "extra_corpus_entries": relative,
                "note": f"already on the newest declared version ({declared}) -- nothing to move to",
            }
            continue

        corpus_dir = Path(tempfile.mkdtemp(prefix=f"matrix-{party}-{version}-"))
        manifest = corpus_generator.build_manifest(
            tree_for(version), tree_for(declared), inside_pin=declared, out_dir=corpus_dir)
        pods = [corpus_dir / rec["file"]
                for rec in manifest["populations"]["generated-spine"]["entries"]]
        # This institution's OWN workloads, added to the generated corpus as
        # extra entries -- each beside a copy of its real governed Namespace,
        # so the cage that classifies it is the cage it actually runs in.
        for i, workload in enumerate(workloads):
            for j, doc in enumerate(d for d in _docs(workload) if d.get("kind") == "Pod"):
                own = corpus_dir / f"own-{i}-{j}.yaml"
                own.write_text(yaml.safe_dump(doc, sort_keys=True))
                if ns is not None:
                    own.with_name(own.stem + ".ns.yaml").write_text(yaml.safe_dump(ns, sort_keys=True))
                pods.append(own)

        window = comparison_window.ComparisonWindow(
            old_window=[version], new_window=array, subject_tree_for=tree_for,
            institution_pins={party: version})
        outcome = comparison_window.evaluate(window, declared, tree_for(declared), pods)
        if outcome.pairing_failure is not None:
            rows[version] = {"pinned_version": version, "computed_bump": None, "movement": [],
                             "extra_corpus_entries": relative,
                             "note": f"pairing failure: {outcome.pairing_failure}"}
            continue
        row = dict(outcome.matrix[party])
        row["extra_corpus_entries"] = relative
        row["corpus_checksum"] = manifest["populations"]["generated-spine"]["checksum"]
        rows[version] = row

    return {
        "party": party,
        "declared_by_publisher": declared,
        "computed_by": "the adopter, with platform's published computed-semver package "
                       "(ticket 18 Answer 4) -- the publisher's own matrix is empty on purpose",
        "generator_version": corpus_generator.GENERATOR_VERSION,
        "rows": rows,
    }


def write_matrix_row(platform_dir: Path, adopter_dir: Path, party: str = PARTY) -> dict:
    """Compute the row and land it in this institution's own composed
    evidence, under `semver_matrix`.
      ponytail: composition.py rewrites composed/evidence.json wholesale on a
      re-compose, so this is re-run after one (shift-left.yml runs it after
      the compose step). Upgrade path: composition carries the key through.
    """
    row = matrix_row(platform_dir, adopter_dir, party)
    evidence_path = Path(adopter_dir) / "composed" / "evidence.json"
    document = json.loads(evidence_path.read_text()) if evidence_path.exists() else {}
    document["semver_matrix"] = row
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(json.dumps(document, indent=2))
    return row


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--platform-dir", type=Path)
    p.add_argument("--new-pin-yaml", type=Path, help="tuppence's platform-pin.yaml at the PR head")
    p.add_argument("--old-pin-yaml", type=Path, default=None,
                    help="tuppence's platform-pin.yaml at the PR base (empty/missing => no predecessor)")
    p.add_argument("--identity-regexp", default=None)
    p.add_argument("--issuer", default=None)
    p.add_argument("--out", type=Path, default=None)
    p.add_argument("--skip-cosign-verify", action="store_true",
                    help="TEST-ONLY: skip the cosign subprocess call (file-existence checks still "
                         "run). Never set by shift-left.yml -- see verify_evidence()'s docstring.")
    p.add_argument("--adopter-dir", type=Path, default=None,
                    help="ADR-0011: read added/retired from THIS repo's own composed/evidence.json "
                         "member set (versions_from_composed_evidence), not platform's raw array")
    p.add_argument("--base-ref", default=None, help="commit-ish for composed/evidence.json 'before' "
                                                      "(with --adopter-dir)")
    p.add_argument("--head-ref", default=None, help="commit-ish for composed/evidence.json 'after' "
                                                      "(with --adopter-dir)")
    p.add_argument("--selfcheck", action="store_true")
    p.add_argument("--matrix-row", action="store_true",
                    help="ticket 43 (18 Answer 4): compute THIS institution's per-institution "
                         "matrix row with platform's published computed-semver package, over its "
                         "own claimed versions and its own workloads, and land it in "
                         "composed/evidence.json (needs --platform-dir and --adopter-dir)")
    p.add_argument("--print-only", action="store_true",
                    help="with --matrix-row: print the row without writing composed/evidence.json")
    args = p.parse_args(argv[1:])

    if args.selfcheck:
        return selfcheck()

    if args.matrix_row:
        for name in ("platform_dir",):
            if getattr(args, name) is None:
                p.error(f"--{name.replace('_', '-')} is required with --matrix-row")
        adopter_dir = args.adopter_dir or Path(".")
        row = (matrix_row(args.platform_dir, adopter_dir) if args.print_only
               else write_matrix_row(args.platform_dir, adopter_dir))
        print(json.dumps(row, indent=2))
        return 0

    for name in ("platform_dir", "new_pin_yaml", "identity_regexp", "issuer"):
        if getattr(args, name) is None:
            p.error(f"--{name.replace('_', '-')} is required")

    new_tag, new_commit = parse_pin(args.new_pin_yaml.read_text())

    checkout_tag(args.platform_dir, new_tag)
    resolved = resolved_commit(args.platform_dir)
    if resolved != new_commit:
        raise SystemExit(
            f"REFUSED: platform-pin.yaml names commit {new_commit} for tag {new_tag}, but the "
            f"tag actually resolves to {resolved} -- ADR-0001's pin disagrees with reality"
        )
    print(f"ok  platform checked out at {new_tag}, resolved commit matches the pinned commit field ({resolved})")

    old_tag = None
    old_array: dict[str, dict] = {}
    if args.old_pin_yaml is not None and args.old_pin_yaml.exists() and args.old_pin_yaml.stat().st_size > 0:
        old_tag, _old_commit = parse_pin(args.old_pin_yaml.read_text())
        old_array = array_at_ref(args.platform_dir, old_tag)

    declared = classify_tag_bump(old_tag, new_tag)
    if args.adopter_dir is not None and args.base_ref is not None and args.head_ref is not None:
        new_array = versions_from_composed_evidence(args.adopter_dir, args.head_ref)
        old_array = versions_from_composed_evidence(args.adopter_dir, args.base_ref)
    else:
        new_array = array_at_worktree(args.platform_dir)

    result = compose(args.platform_dir, new_array, old_array, args.identity_regexp, args.issuer,
                      skip_cosign_verify=args.skip_cosign_verify)
    composed = result["composed"]

    summary = {
        "old_tag": old_tag, "new_tag": new_tag, "new_commit": new_commit,
        "declared": declared, "composed": composed,
        "retired": result["retired"], "elements": result["elements"],
    }
    if args.out:
        args.out.write_text(json.dumps(summary, indent=2))

    print(f"declared (platform tag {old_tag or '(none)'} -> {new_tag}): {declared}")
    print(f"composed (this institution, across {sorted(new_array)} and retired {result['retired']}): {composed}")
    if result["retired"]:
        print(f"RETIRED, reaching this institution as major: {', '.join(result['retired'])}")
    if RANK.get(composed, 0) < RANK.get(declared, 0):
        print(f"NOTE: composed bump ({composed!r}) is weaker than the publisher's tag ({declared!r}) -- "
              f"informational only, this institution's obligation is never lowered by a local view")

    if composed == "major":
        print(f"FAIL: composed bump is major -- refusing to adopt {new_tag} without human review", file=sys.stderr)
        return 1

    print(f"PASS: composed bump {composed!r} does not exceed major; {new_tag} may be adopted")
    return 0


def selfcheck() -> None:
    """Runnable asserts, no network, no cosign, no live platform clone --
    the pure logic this module owns on top of platform's own imported
    helpers. The real end-to-end path (checkout, commit-mismatch refusal,
    real evidence verification, real retirement detection) is proved by
    verify-adopter-gate.sh against a real throwaway git clone -- see that
    script's own header for why this split exists."""
    assert classify_tag_bump(None, "v1.0.0") == "no predecessor"
    assert classify_tag_bump("v1.0.0", "v2.0.0") == "major"
    assert classify_tag_bump("v1.0.0", "v1.1.0") == "minor"
    assert classify_tag_bump("v1.0.0", "v1.0.1") == "patch"
    # Regression: the ordinary PR that never touches
    # gitops/platform/platform-pin.yaml at all -- old_tag == new_tag because
    # the PR base and PR head copies are byte-identical. shift-left.yml has
    # no `paths:` filter specifically so this required check reports on
    # every PR, so this MUST classify as a real no-op ("none"), never a
    # refusal -- a refusal here would fail the required check on the large
    # majority of ordinary PRs.
    assert classify_tag_bump("v1.0.0", "v1.0.0") == "none"
    try:
        classify_tag_bump("v2.0.0", "v1.0.0")
        raise AssertionError("expected a backwards tag move to refuse")
    except SystemExit:
        pass

    assert RANK["major"] > RANK["minor"] > RANK["patch"] > RANK["none"] == RANK["no predecessor"]

    # Regression: parse_pin() against the REAL, committed
    # gitops/platform/platform-pin.yaml -- a genuine two-document YAML
    # stream (GitRepository, then a Kustomization, separated by `---`).
    # yaml.safe_load() (single-document) raises ComposerError on this file;
    # this is the exact, unmodified file shift-left.yml hands parse_pin() as
    # --new-pin-yaml on literally every PR.
    real_pin = Path(__file__).resolve().parent.parent.parent / "gitops" / "platform" / "platform-pin.yaml"
    tag, commit = parse_pin(real_pin.read_text())
    assert tag.startswith("v") and len(commit) == 40, (tag, commit)

    old = {"2.0.0": {}, "3.0.0": {}}
    new = {"3.0.0": {}}  # 2.0.0 retired, nothing new added
    retired = sorted(set(old) - set(new))
    assert retired == ["2.0.0"], retired

    # Regression (ADR-0011, policy-composition ticket 18): the SAME
    # retirement, but discovered through versions_from_composed_evidence
    # against a REAL two-commit adopter repo -- no policy diff anywhere in
    # tuppence's own repo, only the composed evidence document's own member
    # set changes, exactly the shape a retired platform version produces.
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        adopter = Path(td)
        _git(adopter, "init", "-q")

        def _write_evidence(members_versions):
            doc = {"members": [{"name": f"member-{v}", "version": v} for v in members_versions]
                              + [{"name": "policy-version-orphan-guard", "version": None}]}
            (adopter / "composed").mkdir(exist_ok=True)
            (adopter / "composed" / "evidence.json").write_text(json.dumps(doc))

        _write_evidence(["2.0.0", "3.0.0"])
        subprocess.run(["git", "-C", str(adopter), "add", "-A"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(adopter), "-c", "user.name=t", "-c", "user.email=t@t",
                         "commit", "-q", "-m", "base"], check=True, capture_output=True)
        base_sha = subprocess.run(["git", "-C", str(adopter), "rev-parse", "HEAD"],
                                   check=True, capture_output=True, text=True).stdout.strip()

        _write_evidence(["3.0.0"])  # 2.0.0 retired, nothing added
        subprocess.run(["git", "-C", str(adopter), "add", "-A"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(adopter), "-c", "user.name=t", "-c", "user.email=t@t",
                         "commit", "-q", "-m", "head"], check=True, capture_output=True)
        head_sha = subprocess.run(["git", "-C", str(adopter), "rev-parse", "HEAD"],
                                   check=True, capture_output=True, text=True).stdout.strip()

        new_from_evidence = versions_from_composed_evidence(adopter, head_sha)
        old_from_evidence = versions_from_composed_evidence(adopter, base_sha)
        assert set(old_from_evidence) == {"2.0.0", "3.0.0"}, old_from_evidence
        assert set(new_from_evidence) == {"3.0.0"}, new_from_evidence

        # compose() still verifies every SURVIVING version's evidence (not
        # just what was added) -- a minimal fixture evidence file for the
        # one version that survives (3.0.0), skip_cosign_verify=True so the
        # cosign subprocess itself is never reached (same TEST-ONLY flag
        # verify_evidence's own docstring names).
        (adopter / "computed-semver" / "evidence").mkdir(parents=True)
        (adopter / "computed-semver" / "evidence" / "3.0.0.json").write_text(
            json.dumps({"bump": {"computed": "none"}}))
        (adopter / "computed-semver" / "evidence" / "3.0.0.json.bundle").write_text("{}")

        result = compose(adopter, new_from_evidence, old_from_evidence, "unused", "unused",
                          skip_cosign_verify=True)
        assert result["retired"] == ["2.0.0"], result
        assert result["composed"] == "major", result

    # Regression: a SINGLE element whose real bump is "no predecessor" (rank
    # 0, same as "none") must surface as "no predecessor" in `composed`, not
    # get silently swallowed by a same-ranked placeholder default. Built
    # with a real fixture on disk and `skip_cosign_verify=True` (this
    # module's own TEST-ONLY flag) so `compose()` runs its real code path,
    # not a hand-substituted return value.
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        (tdp / "computed-semver" / "evidence").mkdir(parents=True)
        (tdp / "computed-semver" / "evidence" / "9.0.0.json").write_text(
            json.dumps({"bump": {"computed": "no predecessor"}}))
        (tdp / "computed-semver" / "evidence" / "9.0.0.json.bundle").write_text("{}")
        result = compose(tdp, {"9.0.0": {}}, {}, "unused", "unused", skip_cosign_verify=True)
        assert result["composed"] == "no predecessor", (
            f"expected 'no predecessor' to survive composition, got {result['composed']!r} -- "
            f"this is exactly the bug an initial worst='none' sentinel at the same RANK (0) hides"
        )

    print("OK: adopter-gate.py selfcheck (pure logic, no network; one real cosign-skipped disk fixture)")


if __name__ == "__main__":
    sys.exit(main(sys.argv))
