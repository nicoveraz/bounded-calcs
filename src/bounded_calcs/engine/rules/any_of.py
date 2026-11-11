"""`any_of`: the points once, when at least one of several conditions is met."""

from __future__ import annotations

from typing import Any

from bounded_calcs.engine.state import State, _fmt
from bounded_calcs.spec import Calculator, Component


def condition_met(comp: Component, state: State, item_id: str) -> bool | None:
    """Whether one condition of an any_of component is met (None when unknown)."""
    v = state[item_id]
    if v is None:
        return None
    if item_id not in comp.conditions:
        return bool(v)
    # Numeric condition: band 0 is "met", band 1 is "not met".
    return None if len(v) > 1 else 0 in v


def points(comp: Component, state: State) -> set[float]:
    assert comp.points is not None
    flags = [condition_met(comp, state, i) for i in comp.items]
    if any(f is True for f in flags):
        return {comp.points}
    return {0.0, comp.points} if any(f is None for f in flags) else {0.0}


def flip_pairs(comp: Component, state: State, item_id: str) -> set[tuple[float, float]]:
    assert comp.points is not None
    others = [i for i in comp.items if i != item_id]
    if any(condition_met(comp, state, i) is True for i in others):
        return set()
    return {(0.0, comp.points)}


def describe(calc: Calculator, comp: Component) -> dict[str, Any]:
    conds = []
    for i in comp.items:
        if i in comp.conditions:
            conds.append(f"{i} {comp.conditions[i].describe(calc.items[i].unit)}")
        else:
            conds.append(f"{i} present")
    return {"any_of": conds, "points": _fmt(comp.points or 0)}
