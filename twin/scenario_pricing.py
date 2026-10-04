"""Check a standing question's declared consequence basis; never price or observe it."""
import math
import re


class InvalidDeclaration(ValueError):
    pass


def _grade(record):
    grade = record.get("evidence_grade")
    if type(grade) is not int or grade not in range(1, 6):
        raise InvalidDeclaration("the declared basis has no valid evidence grade")
    return grade


def validate_consequence(scenario, perspectives, edges, threshold):
    """Check explicit priced/unpriced prose against this question's native cash-flow basis.

    Existing producer and party-fact checks still validate the actual numeric forecast.
    This check neither constructs a penalty forecast nor records a new observed incident.
    """
    text = " ".join(str(scenario.get("note", "")).lower().split())
    priced = re.search(r"\bprices the consequence\b", text) is not None
    unpriced = re.search(r"\bconsequence (?:is|remains) (?:not yet priced|not priced|unpriced)\b", text) is not None
    if priced == unpriced:
        raise InvalidDeclaration("declare exactly one priced or unpriced consequence; fine or mitigation prose cannot supply it")
    if type(threshold) is not int or threshold not in (2, 3):
        raise InvalidDeclaration("no valid declared pricing threshold")

    components = set(scenario.get("components") or [])
    admitted = []
    for perspective in perspectives:
        for value_id in perspective.get("cash_flow") or []:
            if value_id not in components:
                continue
            value = (perspective.get("values") or {}).get(value_id) or {}
            valuation_grade = _grade(value)
            amount = value.get("amount")
            if amount is None:
                continue  # honest absence, never zero
            if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not math.isfinite(amount):
                raise InvalidDeclaration("the native cash-flow amount is not a finite number")
            relevant = [edge for edge in edges if edge.get("type") == "influences"
                        and edge.get("to") == value_id and edge.get("from") in components]
            if len(relevant) != 1:
                continue  # no unique mechanism behind a priced declaration
            mechanism_grade = _grade(relevant[0])
            if max(valuation_grade, mechanism_grade) <= threshold:
                admitted.append((valuation_grade, mechanism_grade))

    if priced and not admitted:
        raise InvalidDeclaration("the priced consequence has no native cash flow and unique mechanism admitted by the declared threshold")
    if unpriced and admitted:
        raise InvalidDeclaration("the unpriced declaration conflicts with its admitted native cash-flow basis")
    if unpriced:
        return "declared unpriced consequence; no admitted native cash-flow basis"
    valuation_grade = max(v for v, _ in admitted)
    mechanism_grade = max(m for _, m in admitted)
    return (f"declared consequence basis: native valuation grade {valuation_grade}, loss mechanism grade {mechanism_grade}, "
            f"admitted by pricing threshold {threshold}; no new observed incident or numeric standing-question forecast asserted")
