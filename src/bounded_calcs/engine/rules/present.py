"""`present` and `absent`: points when one yes/no finding is present (or is absent)."""

from __future__ import annotations

from typing import Any

from bounded_calcs.engine.state import State, _fmt
from bounded_calcs.spec import Calculator, Component


def points(comp: Component, state: State) -> set[float]:
    v = state[comp.items[0]]
    assert comp.points is not None
    if v is None:
        return {comp.points, 0.0}
    return {comp.points if v == (comp.rule == "present") else 0.0}


def describe(calc: Calculator, comp: Component) -> dict[str, Any]:
    return {"item": comp.items[0], "points": _fmt(comp.points or 0)}
