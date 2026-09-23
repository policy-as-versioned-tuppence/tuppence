#!/usr/bin/env python3
"""The offline render of tuppence's composed policy set (ecosystem ticket 40, fact 4).

Fact 4 of the five-fact sample is "every rendered policy object is live and byte-equal to an
offline render". Something has to produce that render without a cluster, without Flux and without
kustomize, or the fact compares the cluster to itself.

READ-ONLY over `composed/`. This script never writes into that tree and never edits it; it is the
offline twin of what the ResourceSet in `gitops/composed/` installs, in the same spirit as
platform's `render-orphan-guard.py` is the offline twin of its ResourceSet.

    render_composed.py --list                    the objects, one `kind/name` per line
    render_composed.py                           the canonical render, one JSON object per line
    render_composed.py --ref v1.1.0              render the tree at a git ref, not the worktree
    render_composed.py reach [--ref REF]         the delivery check (ticket 130), exit 1 on a fault
    render_composed.py selfcheck

## Two sources, read from where each one really comes from (ticket 130)

The ResourceSet is applied from the CHECKOUT (`kubectl apply -k gitops/composed/`), so
`gitops/composed/composed-set.yaml` is always read from the working tree. The Kustomizations it
generates reconcile `composed/` from the TAG the ResourceSet pins, so `composed/` is read at
`--ref`. Until ticket 130 both were read at `--ref`, and the day the pin moved to a tag cut
before the move, the array came from the old composed-set.yaml inside that tag and named version
directories the tag does not carry.

The set rendered is exactly the set the ResourceSet installs. The ResourceSet's own template is
expanded over its own array: every Kustomization it generates over this repository's composed
source is a route, and every other object in the template is installed inline. A route whose
directory holds a `kustomization.yaml` delivers exactly its `resources`; one without delivers
every manifest under it, which is what Flux generates. `HEADER.yaml` and `evidence.json` are
advisory and are not objects.

## The delivery check (ticket 130)

`reach()` refuses, naming each fault, when:

  * the array is not the set of `composed/policies/v*/` directories at the pinned tag;
  * a route names a directory the tag does not carry;
  * an object under `composed/` is reached by no route, or by two;
  * a route reaches a file that holds no object;
  * one kind and name is delivered twice (a route and the template, or two routes);
  * a machinery allow-list is not the array (a claim on a version outside the array that the
    allow-list admits reaches no cage at all);
  * nothing cages or refuses an orphan claim.

## The ceiling, named

The API server fills in defaults, so a live object is NEVER byte-identical to the YAML that
created it. `compare()` therefore returns two verdicts and the caller records both:

  * `declared_equal` -- every field this render DECLARES is present and equal live. This is what
    fact 4 is graded on.
  * `strict_equal`   -- the canonical forms are identical after the server-owned metadata is
    stripped. Recorded so the weaker verdict is visible rather than implied.

Upgrade path if `declared_equal` ever proves too weak: pull the CRD's structural schema and prune
defaulted fields from the live object instead of ignoring live-only keys.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
COMPOSED = "composed"
RESOURCESET_PATH = "gitops/composed/composed-set.yaml"
RESOURCESET = os.path.join(REPO, RESOURCESET_PATH)
KUSTOMIZE_CONFIG = "kustomize.config.k8s.io/"
MACHINERY_LABEL = ("policy-as-versioned.dev/policy", "platform-machinery")
VERSION_LIST = re.compile(r"\[\s*'\d+\.\d+\.\d+'(?:\s*,\s*'\d+\.\d+\.\d+')*\s*\]")

# Everything the API server owns. Stripped from a live object before any comparison, because none
# of it was ever declared by the render and its presence is not drift.
SERVER_METADATA = (
    "uid", "resourceVersion", "generation", "creationTimestamp", "managedFields",
    "selfLink", "deletionTimestamp", "deletionGracePeriodSeconds",
)
SERVER_ANNOTATIONS = ("kubectl.kubernetes.io/last-applied-configuration",)


class CouldNotLook(Exception):
    """The install cannot be read, so nothing about it can be graded."""


# --- reading the tree at a ref -------------------------------------------------------------------
def _read(path: str, ref: str | None, repo: str = REPO) -> str:
    if ref is None:
        with open(os.path.join(repo, path)) as fh:
            return fh.read()
    return subprocess.run(["git", "-C", repo, "show", f"{ref}:{path}"],
                          capture_output=True, text=True, check=True).stdout


def _exists(path: str, ref: str | None, repo: str = REPO) -> bool:
    try:
        _read(path, ref, repo)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


def _tree(path: str, ref: str | None, repo: str = REPO) -> list[str]:
    """Every file under `path`, recursively, repository-relative and sorted."""
    path = path.rstrip("/")
    if ref is None:
        base = os.path.join(repo, path)
        out = []
        for d, _, names in os.walk(base):
            for n in names:
                out.append(os.path.relpath(os.path.join(d, n), repo))
        return sorted(out)
    done = subprocess.run(["git", "-C", repo, "ls-tree", "-r", "--name-only", ref, path + "/"],
                          capture_output=True, text=True)
    return sorted(done.stdout.split()) if done.returncode == 0 else []


def _is_dir(path: str, ref: str | None, repo: str = REPO) -> bool:
    if ref is None:
        return os.path.isdir(os.path.join(repo, path))
    return bool(_tree(path, ref, repo))


def _objects(text: str) -> list[dict]:
    return [d for d in yaml.safe_load_all(text)
            if isinstance(d, dict) and d.get("kind")
            and not str(d.get("apiVersion", "")).startswith(KUSTOMIZE_CONFIG)]


# --- the install: composed-set.yaml, always from the checkout ------------------------------------
def install(repo: str = REPO) -> tuple[dict, dict]:
    """(the GitRepository, the ResourceSet) as the checkout declares them."""
    try:
        docs = [d for d in yaml.safe_load_all(_read(RESOURCESET_PATH, None, repo)) if isinstance(d, dict)]
    except OSError as e:
        raise CouldNotLook(f"{RESOURCESET_PATH} cannot be read: {e}") from e
    source = next((d for d in docs if d.get("kind") == "GitRepository"), None)
    rset = next((d for d in docs if d.get("kind") == "ResourceSet"), None)
    if source is None or rset is None:
        raise CouldNotLook(f"{RESOURCESET_PATH} declares no GitRepository and ResourceSet pair")
    return source, rset


def pinned_tag(repo: str = REPO) -> str:
    source, _ = install(repo)
    tag = ((source.get("spec") or {}).get("ref") or {}).get("tag")
    if not tag:
        raise CouldNotLook(f"{RESOURCESET_PATH} pins no tag")
    return str(tag)


def versions(ref: str | None = None, repo: str = REPO) -> list[str]:
    """The version array the ResourceSet declares, read from the checkout. `ref` is accepted for
    the callers that pass it and ignored: the ResourceSet is applied from the checkout, never from
    the tag it pins (ticket 130)."""
    _, rset = install(repo)
    array = (rset.get("spec", {}).get("inputs") or [{}])[0].get("versions") or []
    return [str(v["version"]) for v in array]


# --- expanding the ResourceSet template ----------------------------------------------------------
_TOKEN = re.compile(r"<<\s*(.*?)\s*>>", re.S)
_RANGE = re.compile(r'^range\s+(?:(\$\w+)\s*,\s*)?(\$\w+)\s*:=\s*\(index\s+\(inputs\)\s+"versions"\)$')


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _parse(template: str) -> list:
    """The subset of flux-operator's template language the adopters' ResourceSets use: a range
    over the versions input (with or without an index), `if $i`, `end`, `$v.version` and
    `$v.version | slugify`. Anything else is could-not-look, never a guess."""
    root: list = []
    stack = [root]
    pos = 0
    for m in _TOKEN.finditer(template):
        stack[-1].append(template[pos:m.start()])
        pos = m.end()
        tok = m.group(1)
        rng = _RANGE.match(tok)
        if rng:
            body: list = []
            stack[-1].append({"range": (rng.group(1), rng.group(2)), "body": body})
            stack.append(body)
        elif re.fullmatch(r"if\s+\$\w+", tok):
            body = []
            stack[-1].append({"if": tok.split()[1], "body": body})
            stack.append(body)
        elif tok == "end":
            if len(stack) == 1:
                raise CouldNotLook("the ResourceSet template closes a block it never opened")
            stack.pop()
        elif re.fullmatch(r"\$\w+\.version(\s*\|\s*slugify)?", tok):
            stack[-1].append({"var": tok.split(".")[0], "slug": "slugify" in tok})
        else:
            raise CouldNotLook(f"the ResourceSet template uses `<< {tok} >>`, which this render "
                               "does not read")
    if len(stack) != 1:
        raise CouldNotLook("the ResourceSet template leaves a block open")
    stack[-1].append(template[pos:])
    return root


def _eval(nodes: list, env: dict, array: list[str]) -> str:
    out = []
    for n in nodes:
        if isinstance(n, str):
            out.append(n)
        elif "range" in n:
            idx, var = n["range"]
            for i, v in enumerate(array):
                scope = dict(env, **{var: v})
                if idx:
                    scope[idx] = i
                out.append(_eval(n["body"], scope, array))
        elif "if" in n:
            if n["if"] not in env:
                raise CouldNotLook(f"the ResourceSet template tests {n['if']} outside its range")
            if env[n["if"]]:
                out.append(_eval(n["body"], env, array))
        else:
            if n["var"] not in env:
                raise CouldNotLook(f"the ResourceSet template reads {n['var']} outside its range")
            value = str(env[n["var"]])
            out.append(_slugify(value) if n["slug"] else value)
    return "".join(out)


def expand(repo: str = REPO) -> list[dict]:
    """Every object the ResourceSet generates, as the checkout declares it."""
    source, rset = install(repo)
    template = (rset.get("spec") or {}).get("resourcesTemplate") or ""
    text = _eval(_parse(template), {}, versions(None, repo))
    return [d for d in yaml.safe_load_all(text) if isinstance(d, dict) and d.get("kind")]


def routes(repo: str = REPO) -> tuple[list[str], list[dict]]:
    """(the composed paths the generated Kustomizations reconcile, the objects installed inline)."""
    source, _ = install(repo)
    name = source["metadata"]["name"]
    paths, inline = [], []
    for doc in expand(repo):
        spec = doc.get("spec") or {}
        ref = spec.get("sourceRef") or {}
        if (doc["kind"] == "Kustomization" and str(doc.get("apiVersion", "")).startswith("kustomize.toolkit.fluxcd.io/")
                and ref.get("kind") == "GitRepository" and ref.get("name") == name):
            paths.append(os.path.normpath(str(spec.get("path") or ".")))
        else:
            inline.append(doc)
    return paths, inline


def reached_files(path: str, ref: str | None, repo: str = REPO) -> list[str]:
    """The files one route delivers: its kustomization's `resources`, or every manifest under it."""
    kz = f"{path}/kustomization.yaml"
    if _exists(kz, ref, repo):
        doc = yaml.safe_load(_read(kz, ref, repo)) or {}
        return [os.path.normpath(f"{path}/{r}") for r in doc.get("resources") or []]
    return [p for p in _tree(path, ref, repo) if p.endswith((".yaml", ".yml", ".json"))]


def _holds_objects(f: str, ref: str | None, repo: str = REPO) -> bool:
    try:
        return bool(_objects(_read(f, ref, repo)))
    except (OSError, subprocess.CalledProcessError, yaml.YAMLError):
        return False


def broken_files(path: str, ref: str | None, repo: str = REPO) -> list[str]:
    """The files a route reaches that hold no cluster object. One is enough to fail the build:
    measured with flux 2.9.5, `flux build kustomization --dry-run` over a composed/ tree with no
    kustomization.yaml stops at `failed to decode Kubernetes YAML from .../composed/HEADER.yaml:
    missing Resource metadata`, and applies nothing from that route."""
    return [f for f in reached_files(path, ref, repo)
            if os.path.basename(f) != "kustomization.yaml" and not _holds_objects(f, ref, repo)]


# --- the render fact 4 compares against ----------------------------------------------------------
def key(obj: dict) -> str:
    return f"{obj.get('apiVersion')}/{obj.get('kind')}/{obj.get('metadata', {}).get('name')}"


def canonical(obj: dict) -> str:
    """One stable string per object. Sorted keys, no whitespace: two canonical strings are equal
    iff the objects are, whatever order the YAML or the API server happened to emit."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def strip_server_fields(live: dict) -> dict:
    """A live object reduced to what a render could have declared."""
    out = {k: v for k, v in live.items() if k != "status"}
    meta = dict(out.get("metadata") or {})
    for field in SERVER_METADATA:
        meta.pop(field, None)
    annotations = {k: v for k, v in (meta.get("annotations") or {}).items()
                   if k not in SERVER_ANNOTATIONS}
    if annotations:
        meta["annotations"] = annotations
    else:
        meta.pop("annotations", None)
    out["metadata"] = meta
    return out


def _contains(declared, live) -> list[str]:
    """Every path at which `declared` is not matched by `live`. Empty means declared_equal."""
    if isinstance(declared, dict):
        if not isinstance(live, dict):
            return [f"want an object, live is {type(live).__name__}"]
        bad = []
        for k, v in declared.items():
            if k not in live:
                bad.append(f".{k} absent live")
            else:
                bad += [f".{k}{p}" for p in _contains(v, live[k])]
        return bad
    if isinstance(declared, list):
        if not isinstance(live, list) or len(declared) != len(live):
            return [f" list of {len(declared)}, live {len(live) if isinstance(live, list) else type(live).__name__}"]
        bad = []
        for i, (d, l) in enumerate(zip(declared, live)):
            bad += [f"[{i}]{p}" for p in _contains(d, l)]
        return bad
    return [] if declared == live else [f" want {declared!r}, live {live!r}"]


def compare(declared: dict, live: dict) -> dict:
    """The two verdicts fact 4 records. See the ceiling in this module's docstring."""
    reduced = strip_server_fields(live)
    differences = _contains(declared, reduced)
    return {
        "declared_equal": not differences,
        "strict_equal": canonical(declared) == canonical(reduced),
        "differences": differences[:10],
    }


def _delivered(ref: str | None, repo: str = REPO) -> list[tuple[str, dict]]:
    """(where it came from, object) for everything the install delivers, in delivery order."""
    paths, inline = routes(repo)
    out: list[tuple[str, dict]] = []
    for path in paths:
        if broken_files(path, ref, repo):
            continue  # kustomize refuses the whole build, so the route delivers nothing
        for f in reached_files(path, ref, repo):
            try:
                text = _read(f, ref, repo)
            except (OSError, subprocess.CalledProcessError):
                continue
            for doc in _objects(text):
                out.append((f, doc))
    for doc in inline:
        out.append((RESOURCESET_PATH, doc))
    return out


def render(ref: str | None = None, repo: str = REPO) -> dict[str, dict]:
    """{key: object} -- the composed set as bytes, with no cluster in the loop. The generated
    Kustomizations themselves are Flux machinery, not policy, and are not rendered."""
    objects: dict[str, dict] = {}
    for source, doc in _delivered(ref, repo):
        if doc["kind"] == "Kustomization" and str(doc.get("apiVersion", "")).startswith("kustomize.toolkit"):
            continue
        doc = dict(doc)
        doc.setdefault("_source_path", source)
        objects[key(doc)] = doc
    return objects


# --- the delivery check (ticket 130) -------------------------------------------------------------
def _strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for v in node.values():
            yield from _strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from _strings(v)


def _is_machinery(doc: dict) -> bool:
    labels = (doc.get("metadata") or {}).get("labels") or {}
    return labels.get(MACHINERY_LABEL[0]) == MACHINERY_LABEL[1]


def reach(ref: str | None = None, repo: str = REPO) -> list[str]:
    """Every fault in the delivery of `composed/` at `ref` (default: the tag the ResourceSet
    pins). Empty means every object the composer rendered reaches the cluster once, the array is
    the tree, and no claim falls between the machinery and the served cages."""
    faults: list[str] = []
    if ref is None:
        ref = pinned_tag(repo)
    array = versions(None, repo)
    paths, inline = routes(repo)

    tree_versions = sorted({p.split("/")[2][1:] for p in _tree(f"{COMPOSED}/policies", ref, repo)
                            if p.count("/") >= 3})
    if sorted(array) != tree_versions:
        faults.append(f"array-not-tree: the ResourceSet installs {sorted(array)} and "
                      f"{COMPOSED}/policies/ at {ref} carries {tree_versions}")

    reached: dict[str, list[str]] = {}
    for path in paths:
        if not _is_dir(path, ref, repo):
            faults.append(f"missing-route: a Kustomization reconciles ./{path}, which {ref} does not carry")
            continue
        for f in reached_files(path, ref, repo):
            reached.setdefault(f, []).append(path)

    for f, by in sorted(reached.items()):
        if len(by) > 1:
            faults.append(f"reached-twice: {f} is delivered by {len(by)} routes ({', '.join('./' + b for b in by)})")
        if not _exists(f, ref, repo):
            faults.append(f"missing-file: ./{by[0]} names {f}, which {ref} does not carry")
        elif os.path.basename(f) != "kustomization.yaml" and not _holds_objects(f, ref, repo):
            faults.append(f"not-an-object: ./{by[0]} reaches {f}, which holds no cluster object, "
                          f"so that route fails to build and delivers nothing")

    for f in _tree(COMPOSED, ref, repo):
        if not f.endswith((".yaml", ".yml")):
            continue
        if _objects(_read(f, ref, repo)) and f not in reached:
            faults.append(f"unreached: {f} is rendered at {ref} and no Kustomization the "
                          f"ResourceSet generates delivers it")

    delivered = _delivered(ref, repo)
    owners: dict[str, list[str]] = {}
    for source, doc in delivered:
        owners.setdefault(f"{doc['kind']}/{doc['metadata']['name']}", []).append(source)
    for name, by in sorted(owners.items()):
        if len(by) > 1:
            faults.append(f"two-owners: {name} is delivered by {' and '.join(by)}")

    for source, doc in delivered:
        if not _is_machinery(doc):
            continue
        for s in _strings(doc.get("spec")):
            for lst in VERSION_LIST.findall(s):
                allowed = sorted(re.findall(r"'(\d+\.\d+\.\d+)'", lst))
                if allowed != sorted(array):
                    faults.append(f"allow-list: {doc['kind']}/{doc['metadata']['name']} ({source}) "
                                  f"admits {allowed} and the ResourceSet installs {sorted(array)}; "
                                  f"a claim on a version in one and not the other reaches no cage")

    caged = any(d["kind"] == "MutatingPolicy" and d["metadata"]["name"] == "policy-version-orphan-cage"
                for _, d in delivered)
    refused = any(d["kind"] == "ValidatingPolicy" and d["metadata"]["name"] == "policy-version-orphan-guard"
                  and "Deny" in ((d.get("spec") or {}).get("validationActions") or [])
                  for _, d in delivered)
    if not caged and not refused:
        faults.append("orphan-uncaged: nothing delivered cages or refuses a pod that claims a "
                      "version outside the array (no policy-version-orphan-cage, no Deny "
                      "policy-version-orphan-guard)")
    return faults


def main(argv: list[str]) -> int:
    ref = None
    if "--ref" in argv:
        ref = argv[argv.index("--ref") + 1]
    if argv[:1] == ["reach"]:
        try:
            at = ref or pinned_tag()
            faults = reach(at)
        except CouldNotLook as e:
            print(f"COULD NOT LOOK: {e}")
            return 3
        for f in faults:
            print(f"FAULT {f}")
        if faults:
            print(f"REFUSED: {len(faults)} fault(s) in the delivery of composed/ at {at}")
            return 1
        print(f"OK: every object under composed/ at {at} is delivered exactly once, the array is "
              f"the tree, and every machinery allow-list is the array")
        return 0
    objects = render(ref)
    if "--list" in argv:
        for k in sorted(objects):
            print(k)
        return 0
    for k in sorted(objects):
        obj = dict(objects[k])
        source = obj.pop("_source_path", "")
        print(json.dumps({"key": k, "source_path": source, "canonical": canonical(obj)},
                         sort_keys=True))
    return 0


def selfcheck() -> int:
    """One runnable check: the comparison is not vacuous in either direction."""
    declared = {"apiVersion": "v1", "kind": "ConfigMap",
                "metadata": {"name": "a", "labels": {"x": "1"}}, "data": {"k": "v"}}
    live = json.loads(json.dumps(declared))
    live["metadata"].update({"uid": "u", "resourceVersion": "9", "creationTimestamp": "t"})
    live["status"] = {"whatever": True}
    assert compare(declared, live)["declared_equal"], "server fields must not read as drift"
    assert compare(declared, live)["strict_equal"], "stripping must make the two identical"
    live["metadata"]["extraLabelHolder"] = "defaulted-by-the-server"
    got = compare(declared, live)
    assert got["declared_equal"] and not got["strict_equal"], "a live-only key is not drift, but it is not byte identity either"
    live["data"]["k"] = "tampered"
    assert not compare(declared, live)["declared_equal"], "a changed declared field IS drift"
    missing = json.loads(json.dumps(declared))
    del missing["data"]
    assert not compare(declared, missing)["declared_equal"], "an absent declared field IS drift"
    # The render that matters is the one at the tag the ResourceSet pins: that is the tree the
    # Kustomizations reconcile. The working tree is the fallback where the tag is not fetched.
    try:
        at: str | None = pinned_tag()
        subprocess.run(["git", "-C", REPO, "rev-parse", "--verify", "--quiet", f"{at}^{{commit}}"],
                       check=True, capture_output=True)
    except (CouldNotLook, subprocess.CalledProcessError):
        at = None
    objects = render(at)
    assert objects, "the composed set rendered to nothing"
    print(f"ok  compare() bites both ways; the composed set renders {len(objects)} objects "
          f"at {at or 'the working tree'}")
    return 0


if __name__ == "__main__":
    sys.exit(selfcheck() if "selfcheck" in sys.argv[1:] else main(sys.argv[1:]))
