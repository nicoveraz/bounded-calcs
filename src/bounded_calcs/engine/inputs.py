"""Inputs: what a caller may send for each item, and how it becomes the engine's state.

Words for present, absent and unknown; numbers, ranges and "normal"; units and their
conversion; accepted ranges; a site's normal ranges and units. Nothing here knows how points
are assigned.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from bounded_calcs.engine.state import INF, State, _bound
from bounded_calcs.spec import Calculator, Item

UNKNOWN_WORDS = {"unknown", "not_mentioned", "not mentioned", "unk", ""}

NORMAL_WORD = "normal"

TRUE_WORDS = {"present", "yes", "true", "y", "1"}

FALSE_WORDS = {"absent", "no", "false", "n", "0"}


class InputError(ValueError):
    pass


@dataclass(frozen=True)
class _Normalized:
    state: State
    known_ranges: dict[str, tuple[float, float]]
    normal_assumed: dict[str, tuple[float, float, str]]
    converted: dict[str, dict[str, Any]]
    exact: dict[str, float]  # numeric items given as one number, in the item's unit


def _check_range(where: str, value: Any) -> tuple[float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise InputError(f"{where}: a normal range must be [lo, hi], got {value!r}")
    lo, hi = value
    for x in (lo, hi):
        if isinstance(x, bool) or not isinstance(x, (int, float)) or x != x or abs(x) == INF:
            raise InputError(f"{where}: a normal range needs two finite numbers, got {value!r}")
    if lo > hi:
        raise InputError(f"{where}: a normal range must have lo <= hi, got {value!r}")
    return float(lo), float(hi)


def normal_ranges_in_use(
    calc: Calculator, site_ranges: Mapping[str, Any] | None = None
) -> dict[str, tuple[float, float, str]]:
    """Effective normal range per numeric item: the site's range when one is given, otherwise
    the spec's default. Site ranges for items this calculator does not have are ignored."""
    out: dict[str, tuple[float, float, str]] = {}
    for iid, item in calc.items.items():
        if item.type != "numeric":
            continue
        if site_ranges and iid in site_ranges:
            lo, hi = _check_range(f"site normal range for '{iid}'", site_ranges[iid])
            if item.accepts is not None and not (item.accepts[0] <= lo and hi <= item.accepts[1]):
                raise InputError(
                    f"site normal range for '{iid}': {lo:g} to {hi:g} is outside what "
                    f"'{calc.id}' accepts ({item.accepts[0]:g} to {item.accepts[1]:g} {item.unit})"
                )
            out[iid] = (lo, hi, "site")
        elif item.normal is not None:
            out[iid] = (item.normal[0], item.normal[1], "default")
    return out


def check_site_ranges(calcs: Mapping[str, Calculator], site_ranges: Mapping[str, Any]) -> None:
    """Validate a site's normal ranges against a set of calculators: every id must be a
    numeric item of at least one of them, and every range [lo, hi] with lo <= hi."""
    numeric = {i for c in calcs.values() for i, it in c.items.items() if it.type == "numeric"}
    for iid, value in site_ranges.items():
        if iid not in numeric:
            raise InputError(
                f"site normal range for '{iid}': no calculator has a numeric item with this "
                f"id; numeric items: {sorted(numeric)}"
            )
        _check_range(f"site normal range for '{iid}'", value)


UNIT_NOT_STATED = "not stated"
"""Sent as the unit of a value whose source gives none: the site's unit is then used."""


def check_site_units(calcs: Mapping[str, Calculator], site_units: Mapping[str, Any]) -> None:
    """Validate a site's units against a set of calculators: every id must be a numeric item
    of at least one of them, and the unit one that every calculator with that item takes."""
    numeric = {i for c in calcs.values() for i, it in c.items.items() if it.type == "numeric"}
    for iid, unit in site_units.items():
        if iid not in numeric:
            raise InputError(
                f"site unit for '{iid}': no calculator has a numeric item with this id; "
                f"numeric items: {sorted(numeric)}"
            )
        for calc in calcs.values():
            if iid in calc.items and calc.items[iid].type == "numeric":
                _unit_factor(calc, calc.items[iid], unit)


def _unit_factor(calc: Calculator, item: Item, unit: Any) -> tuple[str, float]:
    """The declared unit matching `unit` (letter case ignored) and its factor to the item's
    unit. An undeclared unit is an error: the engine never guesses a conversion."""
    known = {item.unit: 1.0, **item.units}
    if isinstance(unit, str):
        for name, factor in known.items():
            if name is not None and name.lower() == unit.strip().lower():
                return name, factor
    raise InputError(
        f"{calc.id}.{item.id}: unit {unit!r} is not one this item takes; send the value in "
        f"one of {list(known)}. It was not converted and not scored."
    )


def _bands_touched(calc: Calculator, iid: str, lo: float, hi: float) -> frozenset[int]:
    """Indices of the bands that contain some value in [lo, hi]. Bands are intervals bounded
    by thresholds, so probing both ends and each threshold inside, with a point on either
    side of it, finds all of them."""
    bands = calc.numeric_bands(iid)
    probes = [lo, hi]
    for t in {b.value for b in bands if b.value is not None}:
        if lo <= t <= hi:
            eps = 1e-9 * max(1.0, abs(t))
            probes += [t, t - eps, t + eps]
    return frozenset(
        next(i for i, b in enumerate(bands) if b.matches(x)) for x in probes if lo <= x <= hi
    )


def _normalize(
    calc: Calculator,
    inputs: dict[str, Any] | None,
    ranges: dict[str, tuple[float, float, str]],
    site_units: Mapping[str, Any] | None = None,
    require_units: bool = False,
) -> _Normalized:
    inputs = dict(inputs or {})
    extra = set(inputs) - set(calc.items)
    if extra:
        raise InputError(
            f"{calc.id}: unknown item(s) {sorted(extra)}; valid items: {sorted(calc.items)}"
        )
    state: State = {}
    known_ranges: dict[str, tuple[float, float]] = {}
    normal_assumed: dict[str, tuple[float, float, str]] = {}
    converted: dict[str, dict[str, Any]] = {}
    exact: dict[str, float] = {}
    for iid, item in calc.items.items():
        v = inputs.get(iid)
        if v is None or (isinstance(v, str) and v.strip().lower() in UNKNOWN_WORDS):
            state[iid] = None
            continue
        if item.type == "boolean":
            if isinstance(v, bool):
                state[iid] = v
            elif isinstance(v, str) and v.strip().lower() in TRUE_WORDS:
                state[iid] = True
            elif isinstance(v, str) and v.strip().lower() in FALSE_WORDS:
                state[iid] = False
            else:
                raise InputError(f"{calc.id}.{iid}: expected present, absent or unknown, got {v!r}")
        elif item.type == "ordinal":
            if v not in item.levels:
                raise InputError(
                    f"{calc.id}.{iid}: expected one of {list(item.levels)} or unknown, got {v!r}"
                )
            state[iid] = v
        else:  # numeric
            rng = ranges.get(iid)
            normal_text = (
                f"'normal' (assumed {rng[0]:g} to {rng[1]:g} {item.unit}) when the source says "
                "only that it is normal, "
                if rng
                else ""
            )
            units_text = (
                f' (or {{"value": x, "unit": u}} with u one of {list(item.units)})'
                if item.units
                else ""
            )
            hint = (
                f"{calc.id}.{iid}: expected a number in {item.unit}{units_text}, {normal_text}"
                'a range {"min": x, "max": y} (either bound may be left out), or unknown'
                + ("" if rng else "; this item has no normal range")
                + f"; got {v!r}"
            )
            given = v
            factor, unit_name, read_as = 1.0, None, None
            site_unit = site_units.get(iid) if site_units else None
            unit_given = isinstance(v, dict) and "unit" in v
            not_stated = (
                unit_given
                and isinstance(v["unit"], str)
                and v["unit"].strip().lower() == UNIT_NOT_STATED
            )
            if unit_given and not not_stated:
                unit_name, factor = _unit_factor(calc, item, v["unit"])
                v = {k: x for k, x in v.items() if k != "unit"}
            elif not isinstance(v, str):  # a number or bounds with no unit ("normal" needs none)
                units = [item.unit, *item.units]
                if require_units and item.units and not not_stated:
                    # The caller must say what the source gave, so that a number in another
                    # unit is never taken for the site's by omission.
                    raise InputError(
                        f"{calc.id}.{iid}: this item is reported in more than one unit ({units}), "
                        'so a number alone is not accepted. Send {"value": x, "unit": u} with '
                        f'the unit the source gives, or "unit": "{UNIT_NOT_STATED}" if it gives '
                        "none. It was not scored."
                    )
                if require_units and item.units and site_unit is None:
                    raise InputError(
                        f"{calc.id}.{iid}: the source states no unit and the site has not said "
                        f"which one it uses ({units}). Ask for the unit; do not guess it. It "
                        "was not scored."
                    )
                if not_stated:
                    v = {k: x for k, x in v.items() if k != "unit"}
                if site_unit is not None:
                    read_as, factor = _unit_factor(calc, item, site_unit)
            if isinstance(v, dict) and "value" in v:
                if set(v) != {"value"} or isinstance(v["value"], (str, dict)):
                    raise InputError(hint)
                v = v["value"]

            def accepted(x: float) -> float:
                if item.accepts is not None and not item.accepts[0] <= x <= item.accepts[1]:
                    raise InputError(
                        f"{calc.id}.{iid}: {x:g} is outside the values this calculator accepts "
                        f"({item.accepts[0]:g} to {item.accepts[1]:g} {item.unit}). Check the "
                        "value and its unit; if it is right, this calculator does not apply. "
                        "It was not scored."
                    )
                return x

            if isinstance(v, str) and v.strip().lower() == NORMAL_WORD:
                if rng is None:
                    raise InputError(hint)
                lo, hi, source = rng
                state[iid] = _bands_touched(calc, iid, lo, hi)
                known_ranges[iid] = (lo, hi)
                normal_assumed[iid] = rng
                continue
            if isinstance(v, dict):
                keys = set(v)
                if not keys or keys - {"min", "max"}:
                    raise InputError(hint)
                bounds = []
                for key, default in (("min", -INF), ("max", INF)):
                    x = v.get(key, default)
                    if key in v and (
                        isinstance(x, bool)
                        or not isinstance(x, (int, float))
                        or x != x
                        or abs(x) == INF
                    ):
                        raise InputError(hint)
                    bounds.append(accepted(float(x) * factor) if key in v else float(x))
                lo, hi = bounds
                if lo > hi:
                    raise InputError(f"{calc.id}.{iid}: range has min > max: {v!r}")
                state[iid] = _bands_touched(calc, iid, lo, hi)
                known_ranges[iid] = (lo, hi)
                if factor != 1.0:
                    converted[iid] = {
                        "given": given,
                        "range": [_bound(lo), _bound(hi)],
                        "unit": item.unit,
                    }
                    if read_as:
                        converted[iid]["read_as"] = f"{read_as} (site unit)"
                continue
            if isinstance(v, bool):
                raise InputError(hint)
            try:
                x = float(v)
            except (TypeError, ValueError):
                raise InputError(hint) from None
            if x != x or abs(x) == INF:
                raise InputError(hint)
            x = accepted(x * factor)
            state[iid] = _bands_touched(calc, iid, x, x)
            exact[iid] = x
            if factor != 1.0:
                converted[iid] = {"given": given, "value": round(x, 6), "unit": item.unit}
                if read_as:
                    converted[iid]["read_as"] = f"{read_as} (site unit)"
    return _Normalized(state, known_ranges, normal_assumed, converted, exact)
