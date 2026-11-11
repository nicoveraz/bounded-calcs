"""`levels`: points for each level of one ordinal item."""

from __future__ import annotations

from typing import Any

from bounded_calcs.engine.state import State, _fmt
from bounded_calcs.spec import Calculator, Component


def points(comp: Component, state: State) -> set[float]:
    v = state[comp.items[0]]
    return {comp.level_points[v]} if v is not None else set(comp.level_points.values())


def describe(calc: Calculator, comp: Component) -> dict[str, Any]:
    return {
        "item": comp.items[0],
        "points": {k: _fmt(v) for k, v in comp.level_points.items()},
    }
