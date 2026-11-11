"""Bounds: every score and category the known and unknown items still allow.

Exact, with no sampling: components are independent, so the reachable scores are the sumset
of each component's reachable points (which each rule module computes).
"""

from __future__ import annotations

from typing import Any

from bounded_calcs.engine.rules import component_points, flip_pairs
from bounded_calcs.engine.state import Points, State
from bounded_calcs.model import Calculator, Component, Item


def _domain(calc: Calculator, item: Item, state: State) -> list[Any]:
    """Every value an uncertain item could still take, in the form stored in the state."""
    if item.type == "boolean":
        return [True, False]
    if item.type == "ordinal":
        return list(item.levels)
    v = state[item.id]
    bands = sorted(v) if v is not None else range(len(calc.numeric_bands(item.id)))
    return [frozenset({i}) for i in bands]


def _add(calc: Calculator, comp: Component, base: Points, p: float) -> Points:
    """`base` plus `p` points of `comp`: in the total and in the component's group."""
    out = list(base)
    out[0] += p
    if comp.group is not None:
        out[1 + calc.groups.index(comp.group)] += p
    return tuple(out)


def _category(calc: Calculator, points: Points) -> Any:
    """What a point total decides: its category, or, for a score-only calculator, the score."""
    if not calc.categories:
        return points[0]
    return calc.category(points[0], points[1:]).name


def _reachable_points(calc: Calculator, state: State, skip: Component | None = None) -> set[Points]:
    """Every (total, group points...) the known and unknown items allow. Exact: components
    are independent, so it is the sum over components of each one's reachable points."""
    reached: set[Points] = {(0.0,) * (1 + len(calc.groups))}
    for comp in calc.components:
        if comp is skip:
            continue
        pts = component_points(comp, state)
        reached = {_add(calc, comp, s, p) for s in reached for p in pts}
    return reached


def _changes_category(calc: Calculator, state: State, item_id: str) -> bool:
    """True if, for some values of the other unknown items, changing `item_id` changes the
    category. Exact: components are independent, so the rest of the score ranges over the
    sumset of the other components while this component flips between a pair of values."""
    comp = calc.component_of(item_id)
    pairs = [(a, b) for a, b in flip_pairs(comp, state, item_id) if a != b]
    if not pairs:
        return False
    rest = _reachable_points(calc, state, skip=comp)
    return any(
        _category(calc, _add(calc, comp, r, a)) != _category(calc, _add(calc, comp, r, b))
        for r in rest
        for a, b in pairs
    )


def _categories(calc: Calculator, state: State) -> set[str]:
    return {_category(calc, p) for p in _reachable_points(calc, state)}
