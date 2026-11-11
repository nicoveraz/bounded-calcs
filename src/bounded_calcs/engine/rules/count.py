"""`count`: points by how many of several findings are present, with an optional item that
overrides the count."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from bounded_calcs._validate import (
    SpecError,
    _bands,
    _item_of,
    _list,
    _points,
    _reachable,
    _req,
)
from bounded_calcs.engine.state import State, _fmt
from bounded_calcs.model import Calculator, Component, Item

KEYS = {"items", "points", "override", "override_points"}


def count_points(comp: Component, n: int) -> float:
    """Points of a count component when n of its members are present."""
    return next(b.points for b in comp.bands if b.op is None or n >= (b.value or 0))


def points(comp: Component, state: State) -> set[float]:
    members = [i for i in comp.items if i != comp.override]
    known = sum(1 for i in members if state[i] is True)
    unknown = sum(1 for i in members if state[i] is None)
    from_count = {count_points(comp, n) for n in range(known, known + unknown + 1)}
    if comp.override is None:
        return from_count
    ov = state[comp.override]
    assert comp.override_points is not None
    if ov is True:
        return {comp.override_points}
    if ov is False:
        return from_count
    return from_count | {comp.override_points}


def flip_pairs(comp: Component, state: State, item_id: str) -> set[tuple[float, float]]:
    members = [i for i in comp.items if i != comp.override]
    if item_id == comp.override:
        assert comp.override_points is not None
        known = sum(1 for i in members if state[i] is True)
        unknown = sum(1 for i in members if state[i] is None)
        return {
            (comp.override_points, count_points(comp, n))
            for n in range(known, known + unknown + 1)
        }
    if comp.override is not None and state[comp.override] is True:
        return set()
    others = [i for i in members if i != item_id]
    known = sum(1 for i in others if state[i] is True)
    unknown = sum(1 for i in others if state[i] is None)
    return {
        (count_points(comp, n), count_points(comp, n + 1))
        for n in range(known, known + unknown + 1)
    }


def describe(calc: Calculator, comp: Component) -> dict[str, Any]:
    out: dict[str, Any] = {
        "items": [i for i in comp.items if i != comp.override],
        "points_by_count": [
            {"when": b.describe("present") if b.op else "otherwise", "points": _fmt(b.points)}
            for b in comp.bands
        ],
    }
    if comp.override:
        out["override"] = {"item": comp.override, "points": _fmt(comp.override_points or 0)}
    return out


def parse(
    raw: dict[str, Any], where: str, comp_id: str, label: str, rule: str, items: Mapping[str, Item]
) -> Component:
    raw_members = _list(_req(raw, "items", where), where, "items")
    members = tuple(_item_of(items, i, "boolean", where, rule) for i in raw_members)
    bands = _bands(_req(raw, "points", where), where)
    if any(b.op not in ("gte", None) for b in bands):
        raise SpecError(f"{where}: count thresholds must use 'gte'")
    _reachable(bands, range(len(members) + 1), where)
    override = raw.get("override")
    if (override is None) != ("override_points" not in raw):
        raise SpecError(f"{where}: 'override' and 'override_points' go together")
    if override is not None:
        _item_of(items, override, "boolean", where, rule)
    return Component(
        comp_id,
        label,
        rule,
        members + ((override,) if override else ()),
        bands=bands,
        override=override,
        override_points=_points(raw["override_points"], where) if override else None,
    )
