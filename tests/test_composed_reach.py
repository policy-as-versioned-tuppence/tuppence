"""Eco-system ticket 130: every object under composed/ reaches the cluster through a route the
ResourceSet serves, and nothing claims a version the machinery admits and no cage serves.

These run `scripts/render_composed.py` against throwaway git repositories. Each one carries THIS
repository's own `gitops/composed/composed-set.yaml` (tag and array rewritten) and a small composed
tree committed and tagged, so the check reads a tag exactly as the lane does. No network: git runs
with an empty hooks directory and no signing.

Run: python3 -m unittest discover -s tests -p test_composed_reach.py
"""
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import render_composed as rc  # noqa: E402

TAG = "v9.9.9"
CLAIM = "policy-as-versioned.dev/policy-version"
MACHINERY = {"policy-as-versioned.dev/policy": "platform-machinery"}


def _allow(vs):
    return "[" + ", ".join(f"'{v}'" for v in vs) + "]"


def cage_tier(version):
    return {"apiVersion": "policies.kyverno.io/v1alpha1", "kind": "MutatingPolicy",
            "metadata": {"name": f"cage-tier-{version.replace('.', '-')}"},
            "spec": {"matchConditions": [{"name": "only-this-policy-version",
                                          "expression": f"object.metadata.labels['{CLAIM}'] == '{version}'"}]}}


def orphan_cage(allowed):
    return {"apiVersion": "policies.kyverno.io/v1alpha1", "kind": "MutatingPolicy",
            "metadata": {"name": "policy-version-orphan-cage", "labels": dict(MACHINERY)},
            "spec": {"matchConditions": [{"name": "claims-an-undeclared-version",
                                          "expression": f"!({_allow(allowed)}.exists(v, v == x))"}]}}


def orphan_guard(allowed, action="Audit"):
    return {"apiVersion": "policies.kyverno.io/v1alpha1", "kind": "ValidatingPolicy",
            "metadata": {"name": "policy-version-orphan-guard", "labels": dict(MACHINERY)},
            "spec": {"validationActions": [action],
                     "variables": [{"name": "allowed", "expression": _allow(allowed)}]}}


def priority_class():
    return {"apiVersion": "scheduling.k8s.io/v1", "kind": "PriorityClass",
            "metadata": {"name": "cage-isolated", "labels": dict(MACHINERY)}, "value": -10000}


def composed_tree(versions, allowed=None, root_kustomization=True):
    """{path: text} for a composed tree the way the ticket-130 composer renders one."""
    allowed = versions if allowed is None else allowed
    files = {"composed/HEADER.yaml": "policy-as-versioned.dev/composed: true\n",
             "composed/evidence.json": "{}\n"}
    for v in versions:
        files[f"composed/policies/v{v}/cage-tier.yaml"] = yaml.safe_dump(cage_tier(v))
    root = {"composed/orphan-cage.yaml": orphan_cage(allowed),
            "composed/orphan-guard.yaml": orphan_guard(allowed),
            "composed/bottom-rung-priorityclass.yaml": priority_class()}
    for path, doc in root.items():
        files[path] = yaml.safe_dump(doc)
    if root_kustomization:
        files["composed/kustomization.yaml"] = yaml.safe_dump({
            "apiVersion": "kustomize.config.k8s.io/v1beta1", "kind": "Kustomization",
            "resources": sorted(p.split("/", 1)[1] for p in root)})
    return files


def composed_set(array, source=None, tag=TAG):
    """This repository's own composed-set.yaml, pinned to `tag` with `array` as its versions."""
    text = source if source is not None else (ROOT / rc.RESOURCESET_PATH).read_text()
    text = re.sub(r"(\n    tag: ).*", rf"\g<1>{tag}", text, count=1)
    head, rest = text.split("    - versions:\n", 1)
    body = rest[rest.index("  resourcesTemplate:"):]
    lines = "".join(f'        - {{ version: "{v}" }}\n' for v in array)
    return head + "    - versions:\n" + lines + body


class Fixture:
    def __init__(self, test: unittest.TestCase):
        tmp = tempfile.TemporaryDirectory()
        test.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name) / "adopter"
        self.hooks = Path(tmp.name) / "hooks"
        self.dir.mkdir()
        self.hooks.mkdir()
        self.git("init", "-q")

    def git(self, *args):
        return subprocess.run(
            ["git", "-c", f"core.hooksPath={self.hooks}", "-c", "commit.gpgsign=false",
             "-c", "tag.gpgsign=false", "-c", "user.name=fixture",
             "-c", "user.email=fixture@example.invalid", "-C", str(self.dir), *args],
            check=True, capture_output=True, text=True).stdout

    def write(self, files):
        for rel, text in files.items():
            path = self.dir / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)

    def tag(self, files, tag=TAG):
        self.write(files)
        self.git("add", "--", *files)
        self.git("commit", "-q", "-m", "fixture")
        self.git("tag", tag)

    def reach(self, ref=None):
        return rc.reach(ref, repo=str(self.dir))


def kinds(faults):
    return sorted({f.split(":", 1)[0] for f in faults})


class Reach(unittest.TestCase):
    def build(self, tree, array, source=None):
        fx = Fixture(self)
        fx.tag(dict(tree, **{rc.RESOURCESET_PATH: composed_set(array, source)}))
        return fx

    def test_a_composed_tree_the_set_installs_is_clean(self):
        fx = self.build(composed_tree(["4.0.0", "5.0.0"]), ["4.0.0", "5.0.0"])
        self.assertEqual(fx.reach(), [])

    def test_a_planted_object_outside_every_route_is_refused(self):
        tree = composed_tree(["5.0.0"])
        tree["composed/planted.yaml"] = yaml.safe_dump(orphan_cage(["5.0.0"]) | {
            "metadata": {"name": "planted"}})
        fx = self.build(tree, ["5.0.0"])
        self.assertEqual(fx.reach(), [f"unreached: composed/planted.yaml is rendered at {TAG} "
                                      "and no Kustomization the ResourceSet generates delivers it"])

    def test_a_planted_object_in_a_subdirectory_no_route_serves_is_refused(self):
        tree = composed_tree(["5.0.0"])
        tree["composed/feeds/x/v1/stray.yaml"] = yaml.safe_dump(priority_class() | {
            "metadata": {"name": "stray"}})
        fx = self.build(tree, ["5.0.0"])
        self.assertEqual(kinds(fx.reach()), ["unreached"])

    def test_installing_a_subset_of_what_was_composed_is_refused(self):
        # The rollout's own trap: platform serves 4.0.0 and 5.0.0, so the composition renders
        # both and ranges the orphan cage over both. Installing 5.0.0 alone leaves a pod that
        # claims 4.0.0 admitted by the orphan cage and caged by nothing.
        fx = self.build(composed_tree(["4.0.0", "5.0.0"]), ["5.0.0"])
        faults = fx.reach()
        # ...and the 4.0.0 tree the tag carries is delivered by nothing.
        self.assertEqual(kinds(faults), ["allow-list", "array-not-tree", "unreached"])
        self.assertIn(f"array-not-tree: the ResourceSet installs ['5.0.0'] and composed/policies/ "
                      f"at {TAG} carries ['4.0.0', '5.0.0']", faults)

    def test_an_allow_list_that_is_not_the_array_is_refused(self):
        fx = self.build(composed_tree(["5.0.0"], allowed=["4.0.0", "5.0.0"]), ["5.0.0"])
        faults = fx.reach()
        self.assertEqual(kinds(faults), ["allow-list"])
        self.assertEqual(len(faults), 2)  # the cage and the guard both carry the list

    def test_a_tree_with_no_root_kustomization_is_refused(self):
        # What the tag an adopter pins today looks like: the ./composed route falls back to
        # Flux's generated kustomization, which reaches every version tree a second time and
        # tries to decode the advisory header.
        fx = self.build(composed_tree(["5.0.0"], root_kustomization=False), ["5.0.0"])
        faults = fx.reach()
        # Flux refuses the whole generated build on the header, so the route delivers nothing,
        # and with the inline guard retired nothing is left to cage an orphan claim.
        self.assertEqual(kinds(faults), ["not-an-object", "orphan-uncaged", "reached-twice"])

    def test_the_inline_guard_beside_the_composed_one_is_two_owners(self):
        # The shape an adopter had before ticket 130: an orphan guard written into the template,
        # ranged from the array. Left in beside the machinery route, one name has two owners.
        inline = "\n".join("    " + line for line in yaml.safe_dump(orphan_guard(["5.0.0"]),
                                                                 sort_keys=False).splitlines())
        text = composed_set(["5.0.0"]).rstrip("\n") + "\n    ---\n" + inline + "\n"
        fx = Fixture(self)
        fx.tag(dict(composed_tree(["5.0.0"]), **{rc.RESOURCESET_PATH: text}))
        faults = fx.reach()
        self.assertEqual(kinds(faults), ["two-owners"])
        self.assertIn("ValidatingPolicy/policy-version-orphan-guard", faults[0])

    def test_nothing_that_cages_an_orphan_claim_is_refused(self):
        tree = composed_tree(["5.0.0"])
        del tree["composed/orphan-cage.yaml"]
        tree["composed/kustomization.yaml"] = yaml.safe_dump({
            "apiVersion": "kustomize.config.k8s.io/v1beta1", "kind": "Kustomization",
            "resources": ["bottom-rung-priorityclass.yaml", "orphan-guard.yaml"]})
        fx = self.build(tree, ["5.0.0"])
        self.assertEqual(kinds(fx.reach()), ["orphan-uncaged"])

    def test_a_route_to_a_directory_the_tag_lacks_is_refused(self):
        fx = self.build(composed_tree(["5.0.0"]), ["5.0.0"])
        (fx.dir / rc.RESOURCESET_PATH).write_text(composed_set(["5.0.0", "6.0.0"]))
        self.assertIn("missing-route", kinds(fx.reach()))


class ReadFromWhereItComes(unittest.TestCase):
    def test_the_array_is_read_from_the_checkout_not_the_tag(self):
        # The composed-set move happens AFTER the tag it names is cut, so the copy of this file
        # inside that tag still carries the old array.
        fx = Fixture(self)
        fx.tag(dict(composed_tree(["5.0.0"]), **{rc.RESOURCESET_PATH: composed_set(["3.0.0"])}))
        fx.write({rc.RESOURCESET_PATH: composed_set(["5.0.0"])})
        self.assertEqual(rc.versions(TAG, repo=str(fx.dir)), ["5.0.0"])
        self.assertEqual(fx.reach(), [])

    def test_the_render_carries_the_machinery_and_every_installed_version(self):
        fx = Fixture(self)
        fx.tag(dict(composed_tree(["4.0.0", "5.0.0"]),
                    **{rc.RESOURCESET_PATH: composed_set(["4.0.0", "5.0.0"])}))
        got = sorted(k.split("/", 2)[-1] for k in rc.render(TAG, repo=str(fx.dir)))
        self.assertEqual(got, sorted([
            "MutatingPolicy/cage-tier-4-0-0", "MutatingPolicy/cage-tier-5-0-0",
            "MutatingPolicy/policy-version-orphan-cage",
            "ValidatingPolicy/policy-version-orphan-guard",
            "PriorityClass/cage-isolated"]))

    def test_the_template_is_expanded_not_guessed(self):
        fx = Fixture(self)
        text = composed_set(["5.0.0"]).replace("<< end >>", "<< end >><< $v.tag >>", 1)
        fx.tag(dict(composed_tree(["5.0.0"]), **{rc.RESOURCESET_PATH: text}))
        with self.assertRaises(rc.CouldNotLook):
            fx.reach()


class ThisRepository(unittest.TestCase):
    def test_this_checkout_expands_one_route_per_version_and_the_machinery(self):
        paths, inline = rc.routes()
        self.assertEqual(paths, [f"composed/policies/v{v}" for v in rc.versions()] + ["composed"])
        self.assertEqual(inline, [])


if __name__ == "__main__":
    unittest.main()
