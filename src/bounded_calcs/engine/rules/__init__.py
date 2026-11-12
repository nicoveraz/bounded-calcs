"""Scoring rules: one module per rule a component can use.

A rule module answers three questions about a component, and nothing else in the engine
depends on how it does so:

    points(comp, state)               every number of points the component can still give,
                                      given what is known
    flip_pairs(comp, state, item_id)  for a rule with several items: pairs of points the
                                      component takes for two values of one unknown item,
                                      with its other unknown items held the same
    describe(calc, comp)              the component's entry in the schema

A rule module also reads its own part of the YAML:

    KEYS                              the keys the rule takes, besides id, label, rule, group
    parse(raw, where, id, label, rule, items)   the Component, or a SpecError that says
                                      where the mistake is

To add a rule: write its module with these, and register it in `RULES`. The loader
(`spec.py`) and `bounds.py`, `result.py` and `inputs.py` do not change.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import ModuleType
from typing import Any

from bounded_calcs.engine.rules import any_of, bands, bands_by, count, levels, present
from bounded_calcs.engine.state import State
from bounded_calcs.model import Calculator, Component, Item

RULES: dict[str, ModuleType] = {
    "present": present,
    "absent": present,
    "levels": levels,
    "bands": bands,
    "bands_by": bands_by,
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


COMMON_KEYS = {"id", "label", "rule", "group"}


def component_keys(rule: str) -> set[str]:
    """Every key a component of this rule may have."""
    return COMMON_KEYS | RULES[rule].KEYS


def parse_component(
    raw: dict[str, Any], where: str, comp_id: str, label: str, rule: str, items: Mapping[str, Item]
) -> Component:
    """Read the rule's own keys of one component (the loader has checked id, label and rule)."""
    return RULES[rule].parse(raw, where, comp_id, label, rule, items)
