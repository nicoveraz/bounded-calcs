"""`bands`: points for the band one numeric item falls in."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from bounded_calcs._validate import _bands, _item_of, _reachable, _req
from bounded_calcs.engine.state import State, _fmt
from bounded_calcs.model import Calculator, Component, Item, band_probes

KEYS = {"item", "bands"}


def points(comp: Component, state: State) -> set[float]:
    v = state[comp.items[0]]
    return {b.points for i, b in enumerate(comp.bands) if v is None or i in v}


def describe(calc: Calculator, comp: Component) -> dict[str, Any]:
    unit = calc.items[comp.items[0]].unit
    return {
        "item": comp.items[0],
        "bands": [{"when": b.describe(unit), "points": _fmt(b.points)} for b in comp.bands],
    }


def parse(
    raw: dict[str, Any], where: str, comp_id: str, label: str, rule: str, items: Mapping[str, Item]
) -> Component:
    iid = _item_of(items, _req(raw, "item", where), "numeric", where, rule)
    bands = _bands(_req(raw, "bands", where), where)
    _reachable(bands, band_probes(bands), where)
    return Component(comp_id, label, rule, (iid,), bands=bands)
