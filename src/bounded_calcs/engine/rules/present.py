"""`present` and `absent`: points when one yes/no finding is present (or is absent)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from bounded_calcs._validate import _item_of, _points, _req
from bounded_calcs.engine.state import State, _fmt
from bounded_calcs.model import Calculator, Component, Item

KEYS = {"item", "points"}


def points(comp: Component, state: State) -> set[float]:
    v = state[comp.items[0]]
    assert comp.points is not None
    if v is None:
        return {comp.points, 0.0}
    return {comp.points if v == (comp.rule == "present") else 0.0}


def describe(calc: Calculator, comp: Component) -> dict[str, Any]:
    return {"item": comp.items[0], "points": _fmt(comp.points or 0)}


def parse(
    raw: dict[str, Any], where: str, comp_id: str, label: str, rule: str, items: Mapping[str, Item]
) -> Component:
    iid = _item_of(items, _req(raw, "item", where), "boolean", where, rule)
    return Component(
        comp_id, label, rule, (iid,), points=_points(_req(raw, "points", where), where)
    )
