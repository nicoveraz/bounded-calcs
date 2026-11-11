"""`bands`: points for the band one numeric item falls in."""

from __future__ import annotations

from typing import Any

from bounded_calcs.engine.state import State, _fmt
from bounded_calcs.spec import Calculator, Component


def points(comp: Component, state: State) -> set[float]:
    v = state[comp.items[0]]
    return {b.points for i, b in enumerate(comp.bands) if v is None or i in v}


def describe(calc: Calculator, comp: Component) -> dict[str, Any]:
    unit = calc.items[comp.items[0]].unit
    return {
        "item": comp.items[0],
        "bands": [{"when": b.describe(unit), "points": _fmt(b.points)} for b in comp.bands],
    }
