"""`levels`: points for each level of one ordinal item."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from bounded_calcs._validate import _NOT_TEXT, SpecError, _item_of, _points, _req
from bounded_calcs.engine.state import State, _fmt
from bounded_calcs.model import Calculator, Component, Item

KEYS = {"item", "points"}


def points(comp: Component, state: State) -> set[float]:
    v = state[comp.items[0]]
    return {comp.level_points[v]} if v is not None else set(comp.level_points.values())


def describe(calc: Calculator, comp: Component) -> dict[str, Any]:
    return {
        "item": comp.items[0],
        "points": {k: _fmt(v) for k, v in comp.level_points.items()},
    }


def parse(
    raw: dict[str, Any], where: str, comp_id: str, label: str, rule: str, items: Mapping[str, Item]
) -> Component:
    iid = _item_of(items, _req(raw, "item", where), "ordinal", where, rule)
    raw_pts = _req(raw, "points", where)
    if not isinstance(raw_pts, dict) or set(raw_pts) != set(items[iid].levels):
        raise SpecError(
            f"{where}: points must be a mapping with exactly the levels of '{iid}' "
            f"({list(items[iid].levels)}) as keys, got {raw_pts!r}. {_NOT_TEXT}"
        )
    pts = {k: _points(v, where) for k, v in raw_pts.items()}
    return Component(comp_id, label, rule, (iid,), level_points=pts)
