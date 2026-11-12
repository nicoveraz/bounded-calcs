"""`bands_by`: points for the band a numeric item falls in, with one band table per level of
an ordinal item (haemoglobin scored by sex).

The numeric item is resolved against the thresholds of every table together, so one value
range is enough whichever level applies; the points of each table for each of those ranges
are worked out once, when the spec loads.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from bounded_calcs._validate import SpecError, _bands, _item_of, _reachable, _req
from bounded_calcs.engine.state import State, _fmt
from bounded_calcs.model import Band, Calculator, Component, Item, band_probes

KEYS = {"item", "by", "bands"}


def _choices(comp: Component, state: State) -> tuple[list[str], list[int]]:
    """The levels and the value ranges that are still possible."""
    numeric, by = comp.items
    level, ranges = state[by], state[numeric]
    levels = list(comp.by_points) if level is None else [level]
    return levels, sorted(ranges) if ranges is not None else list(range(len(comp.bands)))


def points(comp: Component, state: State) -> set[float]:
    levels, ranges = _choices(comp, state)
    return {comp.by_points[level][i] for level in levels for i in ranges}


def flip_pairs(comp: Component, state: State, item_id: str) -> set[tuple[float, float]]:
    levels, ranges = _choices(comp, state)
    if item_id == comp.items[0]:  # the number changes, the level stays
        table = comp.by_points
        return {(table[lv][i], table[lv][j]) for lv in levels for i in ranges for j in ranges}
    return {(comp.by_points[a][i], comp.by_points[b][i]) for i in ranges for a in levels for b in levels}


def describe(calc: Calculator, comp: Component) -> dict[str, Any]:
    numeric, by = comp.items
    unit = calc.items[numeric].unit
    return {
        "item": numeric,
        "by": by,
        "bands": {
            level: [{"when": b.describe(unit), "points": _fmt(b.points)} for b in bands]
            for level, bands in comp.by_bands.items()
        },
    }


def _merged(tables: Mapping[str, tuple[Band, ...]]) -> tuple[Band, ...]:
    """Bands that cut the number line at every threshold of every table, highest first, so
    that within one of them every table gives a single number of points."""
    # A threshold cuts either just below its value (gte, lt) or just above it (gt, lte).
    cuts = {(b.value, b.op in ("gt", "lte")) for t in tables.values() for b in t if b.op}
    ordered = sorted(cuts, key=lambda c: (c[0], c[1]), reverse=True)
    return (*(Band("gt" if above else "gte", v, 0.0) for v, above in ordered), Band(None, None, 0.0))


def parse(
    raw: dict[str, Any], where: str, comp_id: str, label: str, rule: str, items: Mapping[str, Item]
) -> Component:
    numeric = _item_of(items, _req(raw, "item", where), "numeric", where, rule)
    by = _item_of(items, _req(raw, "by", where), "ordinal", where, rule)
    raw_tables = _req(raw, "bands", where)
    levels = items[by].levels
    if not isinstance(raw_tables, dict) or set(raw_tables) != set(levels):
        raise SpecError(
            f"{where}: bands must be a mapping with exactly the levels of '{by}' "
            f"({list(levels)}) as keys, each with its own list of bands"
        )
    tables: dict[str, tuple[Band, ...]] = {}
    for level in levels:
        bands = _bands(raw_tables[level], f"{where} bands for '{level}'")
        _reachable(bands, band_probes(bands), f"{where} bands for '{level}'")
        tables[level] = bands
    merged = _merged(tables)
    # One number inside each merged band, and what each table gives there.
    inside = {}
    for x in band_probes(merged):
        inside.setdefault(next(i for i, b in enumerate(merged) if b.matches(x)), x)
    assert len(inside) == len(merged)
    by_points = {
        level: tuple(
            next(b.points for b in bands if b.matches(inside[i])) for i in range(len(merged))
        )
        for level, bands in tables.items()
    }
    return Component(
        comp_id, label, rule, (numeric, by), bands=merged, by_bands=tables, by_points=by_points
    )
