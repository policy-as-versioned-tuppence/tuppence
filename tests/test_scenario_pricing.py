"""Public consequence declaration contract, independent of monetary fine screening."""
import copy
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("scenario_pricing", ROOT / "twin/scenario_pricing.py")
pricing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pricing)


class ConsequenceDeclaration(unittest.TestCase):
    def setUp(self):
        self.scenario = {"components": ["record", "fees"],
                         "note": "This scenario prices the consequence on the value chain and never the fine. "
                                 "Grade-5 mitigation remains unpriced; no new incident is observed."}
        self.perspectives = [{"cash_flow": ["fees"], "values": {
            "fees": {"amount": 100, "evidence_grade": 3},
            "standing": {"evidence_grade": 5}}}]
        self.edges = [{"type": "influences", "from": "record", "to": "fees", "evidence_grade": 3}]

    def check(self, scenario=None, perspectives=None, edges=None, threshold=3):
        return pricing.validate_consequence(scenario or self.scenario,
                                            self.perspectives if perspectives is None else perspectives,
                                            self.edges if edges is None else edges, threshold)

    def test_priced_basis_is_admitted_without_regrading_mitigation_or_observation(self):
        before = copy.deepcopy((self.scenario, self.perspectives, self.edges))
        result = self.check()
        self.assertIn("valuation grade 3", result)
        self.assertIn("mechanism grade 3", result)
        self.assertIn("declared", result)
        self.assertEqual(before, (self.scenario, self.perspectives, self.edges))

    def test_explicit_unpriced_consequence_with_missing_native_amount(self):
        self.scenario["note"] = "The consequence is not yet priced. The fine belongs to the estate."
        del self.perspectives[0]["values"]["fees"]["amount"]
        self.perspectives[0]["values"]["fees"]["evidence_grade"] = 5
        self.assertIn("unpriced", self.check())

    def test_ambiguous_or_unrelated_absence_does_not_supply_consequence_declaration(self):
        for note in ("The fine is not priced; mitigation remains unpriced.",
                     "The consequence might eventually have a price.",
                     "This scenario prices the consequence. The consequence remains unpriced."):
            with self.subTest(note=note), self.assertRaises(pricing.InvalidDeclaration):
                self.check({**self.scenario, "note": note})

    def test_priced_claim_requires_real_admitted_native_and_mechanism_grades(self):
        for target, field, value in (("valuation", "evidence_grade", 5),
                                     ("valuation", "evidence_grade", 6),
                                     ("valuation", "amount", None),
                                     ("valuation", "amount", float("nan")),
                                     ("valuation", "amount", True),
                                     ("edge", "evidence_grade", 5),
                                     ("edge", "evidence_grade", None)):
            with self.subTest(target=target, field=field, value=value):
                perspectives, edges = copy.deepcopy(self.perspectives), copy.deepcopy(self.edges)
                record = perspectives[0]["values"]["fees"] if target == "valuation" else edges[0]
                record[field] = value
                with self.assertRaises(pricing.InvalidDeclaration):
                    self.check(perspectives=perspectives, edges=edges)
        for threshold in (None, 2, 5, True):
            with self.subTest(threshold=threshold), self.assertRaises(pricing.InvalidDeclaration):
                self.check(threshold=threshold)

    def test_no_cash_flow_or_no_unique_causal_edge_cannot_back_priced_claim(self):
        for perspectives, edges in (([], self.edges), (self.perspectives, []),
                                   (self.perspectives, self.edges + self.edges)):
            with self.subTest(perspectives=perspectives, edges=edges), self.assertRaises(pricing.InvalidDeclaration):
                self.check(perspectives=perspectives, edges=edges)

    def test_known_zero_is_priced_and_false_absence_fails(self):
        self.perspectives[0]["values"]["fees"]["amount"] = 0
        self.assertIn("valuation grade 3", self.check())
        self.scenario["note"] = "The consequence is not priced."
        with self.assertRaises(pricing.InvalidDeclaration):
            self.check()


if __name__ == "__main__":
    unittest.main()
