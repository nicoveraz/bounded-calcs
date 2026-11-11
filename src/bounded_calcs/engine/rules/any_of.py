"""`any_of`: the points once, when at least one of several conditions is met."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from bounded_calcs._validate import SpecError, _list, _number, _only, _points, _req
from bounded_calcs.engine.state import State, _fmt
from bounded_calcs.model import BAND_OPS, Band, Calculator, Component, Item

KEYS = {"conditions", "points"}
_CONDITION_KEYS = {*BAND_OPS, "item"}


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


def parse(
    raw: dict[str, Any], where: str, comp_id: str, label: str, rule: str, items: Mapping[str, Item]
) -> Component:
    conds: dict[str, Band] = {}
    members: list[str] = []
    for c in _list(_req(raw, "conditions", where), where, "conditions"):
        _only(c, _CONDITION_KEYS, f"{where} condition")
        iid = _req(c, "item", where)
        if not isinstance(iid, str) or iid not in items:
            raise SpecError(f"{where}: unknown item {iid!r}")
        if iid in members:
            raise SpecError(f"{where}: item '{iid}' appears twice")
        ops = [op for op in BAND_OPS if op in c]
        if items[iid].type == "boolean":
            if ops:
                raise SpecError(f"{where}: boolean condition '{iid}' takes no threshold")
        elif items[iid].type == "numeric":
            if len(ops) != 1:
                raise SpecError(f"{where}: numeric condition '{iid}' needs one threshold")
            conds[iid] = Band(ops[0], _number(c[ops[0]], where, f"'{ops[0]}'"), 1.0)
        else:
            raise SpecError(f"{where}: ordinal items cannot be any_of conditions")
        members.append(iid)
    if len(members) < 2:
        raise SpecError(f"{where}: any_of needs at least two conditions")
    return Component(
        comp_id,
        label,
        rule,
        tuple(members),
        points=_points(_req(raw, "points", where), where),
        conditions=conds,
    )
