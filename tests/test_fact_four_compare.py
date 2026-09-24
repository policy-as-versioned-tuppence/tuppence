"""Eco-system ticket 140: fact 4 reads a declared zero value the API server omits as equal.

The composed set declares `globalDefault: false` on every PriorityClass. The API server never
returns a false `globalDefault`: the Go type is `GlobalDefault bool json:"globalDefault,omitempty"`
(k8s.io/api scheduling/v1), so a false value is dropped when the object is written out. Fact 4
counted that absence as a difference, and every delivered PriorityClass read unequal.

These tests drive the real seam twice: `render_composed.compare()`, which owns `declared_equal`,
and `drift/five-facts.py`'s `composed_set_facts()`, which grades fact 4 from it. The cluster and
the render are stand-ins; nothing here reaches a network.

Run: python3 -m unittest discover -s tests -p test_fact_four_compare.py
"""
import copy
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import render_composed as rc  # noqa: E402

_spec = importlib.util.spec_from_file_location("five_facts", ROOT / "drift" / "five-facts.py")
assert _spec and _spec.loader
ff = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ff)

FACT_4 = "fact_4_rendered_objects_byte_equal_to_an_offline_render"


def priority_class(**fields):
    obj = {"apiVersion": "scheduling.k8s.io/v1", "kind": "PriorityClass",
           "metadata": {"name": "cage-isolated-5-0-0", "labels": {"a": "b"}},
           "value": -10000, "preemptionPolicy": "Never", "description": "the bottom rung"}
    obj.update(fields)
    return obj


def as_served(declared, **server_extra):
    """What the API server hands back: the declared object, minus any false globalDefault
    (omitempty), plus the server-owned metadata the compare strips."""
    live = copy.deepcopy(declared)
    if live.get("globalDefault") is False:
        del live["globalDefault"]
    live["metadata"].update({"uid": "u", "resourceVersion": "1", "generation": 1})
    live.update(server_extra)
    return live


class CompareReadsAnOmittedZeroAsEqual(unittest.TestCase):
    def test_a_declared_false_global_default_absent_live_is_equal(self):
        declared = priority_class(globalDefault=False)
        got = rc.compare(declared, as_served(declared))
        self.assertEqual(got["differences"], [])
        self.assertTrue(got["declared_equal"])
        self.assertEqual(got["omitted_zero"], [".globalDefault"],
                         "the rule must say where it read an absence as the zero value")
        self.assertFalse(got["strict_equal"],
                         "the canonical forms still differ, and strict_equal must keep saying so")

    def test_a_declared_true_global_default_absent_live_is_a_difference(self):
        declared = priority_class(globalDefault=True)
        live = copy.deepcopy(declared)
        del live["globalDefault"]
        got = rc.compare(declared, live)
        self.assertFalse(got["declared_equal"])
        self.assertEqual(got["differences"], [".globalDefault absent live"])
        self.assertEqual(got["omitted_zero"], [])

    def test_a_changed_global_default_is_a_difference(self):
        declared = priority_class(globalDefault=False)
        got = rc.compare(declared, {**declared, "globalDefault": True})
        self.assertFalse(got["declared_equal"])
        self.assertEqual(got["differences"], [".globalDefault want False, live True"])

    def test_a_zero_of_the_wrong_type_is_not_the_omitted_zero(self):
        declared = priority_class(globalDefault=0)
        live = copy.deepcopy(declared)
        del live["globalDefault"]
        self.assertFalse(rc.compare(declared, live)["declared_equal"],
                         "0 is not false: only the Go zero value of the declared type is omitted")

    def test_the_rule_is_narrow_a_false_elsewhere_absent_live_is_a_difference(self):
        # A custom resource keeps a false field (it is stored as unstructured JSON), so an
        # absent one there is a real difference. So is a false field on a kind not in the table.
        policy = {"apiVersion": "policies.kyverno.io/v1alpha1", "kind": "MutatingPolicy",
                  "metadata": {"name": "p"}, "spec": {"globalDefault": False}}
        live = copy.deepcopy(policy)
        del live["spec"]["globalDefault"]
        self.assertFalse(rc.compare(policy, live)["declared_equal"])
        other = {"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": "c"},
                 "globalDefault": False}
        self.assertFalse(rc.compare(other, {"apiVersion": "v1", "kind": "ConfigMap",
                                            "metadata": {"name": "c"}})["declared_equal"])

    def test_the_rule_names_its_reason(self):
        for (group, kind), fields in rc.API_OMITTED_ZERO.items():
            for path, entry in fields.items():
                self.assertIn("omitempty", entry["why"], f"{group}/{kind} {path} gives no reason")


class FakeCluster:
    """Answers the reads composed_set_facts makes: one object, one Flux inventory."""

    def __init__(self, live):
        self.live = live
        self.reachable = True

    def get(self, *args):
        if args[:3] == ("-n", "flux-system", "get"):
            if args[3].startswith("kustomizations"):
                entry = {"id": ff.inventory_id(self.live)}
                return {"items": [{"kind": "Kustomization", "metadata": {"name": "k"},
                                   "status": {"inventory": {"entries": [entry]}}}]}
            return {"items": []}
        if args[0] == "get" and args[1].startswith("priorityclass."):
            return self.live
        return None


class FactFourGradesTheDeliveredPriorityClasses(unittest.TestCase):
    def grade(self, declared, live):
        rendered = {rc.key(declared): declared}
        saved = ff.rc.render
        ff.rc.render = lambda ref: copy.deepcopy(rendered)
        try:
            f4, _f5, bad = ff.composed_set_facts(FakeCluster(live), "v9.9.9")
        finally:
            ff.rc.render = saved
        return f4, bad

    def test_the_delivered_shape_reads_fact_4_true(self):
        declared = priority_class(globalDefault=False)
        f4, bad = self.grade(declared, as_served(declared))
        self.assertIs(f4["observed"], True, f4["why"])
        self.assertEqual(bad, [])

    def test_a_planted_true_absent_live_reads_fact_4_false(self):
        declared = priority_class(globalDefault=True)
        live = copy.deepcopy(declared)
        del live["globalDefault"]
        f4, bad = self.grade(declared, live)
        self.assertIs(f4["observed"], False)
        self.assertEqual(f4["objects_unequal"][0]["differences"], [".globalDefault absent live"])
        self.assertEqual(bad, [rc.key(declared)])

    def test_a_changed_value_reads_fact_4_false(self):
        declared = priority_class(globalDefault=False)
        f4, _bad = self.grade(declared, as_served(declared, value=1000))
        self.assertIs(f4["observed"], False)
        self.assertEqual(f4["objects_unequal"][0]["differences"], [".value want -10000, live 1000"])


if __name__ == "__main__":
    unittest.main()
