"""Scoring rules: one module per rule a component can use.

A rule module answers three questions about a component, and nothing else in the engine
depends on how it does so:

    points(comp, state)               every number of points the component can still give,
                                      given what is known
    flip_pairs(comp, state, item_id)  for a rule with several items: pairs of points the
                                      component takes for two values of one unknown item,
                                      with its other unknown items held the same
    describe(calc, comp)              the component's entry in the schema

To add a rule: write its module with these functions, register it in `RULES`, and teach
`spec.py` to read it. `bounds.py`, `result.py` and `inputs.py` do not change.
"""

from __future__ import annotations

from types import ModuleType
from typing import Any

from bounded_calcs.engine.rules import any_of, bands, count, levels, present
from bounded_calcs.engine.state import State
from bounded_calcs.spec import Calculator, Component

RULES: dict[str, ModuleType] = {
    "present": present,
    "absent": present,
    "levels": levels,
    "bands": bands,
    "any_of": any_of,
    "count": count,
}


def component_points(comp: Component, state: State) -> set[float]:
    """Every number of points the component can still give."""
    return RULES[comp.rule].points(comp, state)


def flip_pairs(comp: Component, state: State, item_id: str) -> set[tuple[float, float]]:
    """Pairs of points the component can take for two values of the unknown `item_id`, with
    the component's other unknown items held at the same values."""
    if len(comp.items) == 1:
        pts = sorted(component_points(comp, state))
        return {(a, b) for a in pts for b in pts if a < b}
    return RULES[comp.rule].flip_pairs(comp, state, item_id)


def describe(calc: Calculator, comp: Component) -> dict[str, Any]:
    """The rule's part of the component's schema entry."""
    return RULES[comp.rule].describe(calc, comp)
