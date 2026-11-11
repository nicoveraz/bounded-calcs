"""Results: `evaluate` (the bounded result for one patient) and `schema` (what a calculator
takes and returns). The names of the output fields are a public API."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from bounded_calcs.engine.bounds import (
    _categories,
    _category,
    _changes_category,
    _domain,
    _reachable_points,
)
from bounded_calcs.engine.formula_bounds import formula_result
from bounded_calcs.engine.inputs import (
    UNIT_NOT_STATED,
    _normalize,
    _Normalized,
    _unit_factor,
    normal_ranges_in_use,
)
from bounded_calcs.engine.rules import component_points, describe
from bounded_calcs.engine.state import _bound, _fmt, _uncertain
from bounded_calcs.model import Calculator, Item


def _describe_value(calc: Calculator, item: Item, v: Any) -> str:
    if item.type == "boolean":
        return "present" if v else "absent"
    if item.type == "ordinal":
        return str(v)
    (index,) = v
    band = calc.numeric_bands(item.id)[index]
    if calc.component_of(item.id).rule == "any_of" and band.op is None:
        met = calc.numeric_bands(item.id)[0]
        return "not " + met.describe(item.unit)
    return band.describe(item.unit)



def _additive_result(
    calc: Calculator, norm: _Normalized
) -> tuple[dict[str, Any], list[dict[str, Any]], bool, list[str]]:
    """The bounded result of an additive calculator: (result, decisive, settled, unknown ids)."""
    state = norm.state
    reached = _reachable_points(calc, state)
    scores = {p[0] for p in reached}
    cats = {_category(calc, p) for p in reached}
    ordered = calc.by_risk(cats)
    settled = len(cats) == 1
    score_only = not calc.categories
    unknown_ids = [i for i in state if _uncertain(state, i)]

    decisive: list[dict[str, Any]] = []
    irrelevant: list[str] = []
    jointly: list[str] = []
    for iid in unknown_ids:
        item = calc.items[iid]
        if settled:
            irrelevant.append(iid)
            continue
        outcomes = []
        left = []  # how many categories (or scores) stay possible for each answer
        for v in _domain(calc, item, state):
            sub = calc.by_risk(_categories(calc, {**state, iid: v}))
            left.append(len(sub))
            if score_only:
                outcome = {"score_range": [_fmt(min(sub)), _fmt(max(sub))]}
            else:
                outcome = {"possible_categories": sub}
            outcomes.append({"if": _describe_value(calc, item, v), **outcome})
        narrows = any(n < len(cats) for n in left)
        if not narrows:
            # Knowing it alone cannot rule out a category, but it may still change the
            # category for some values of the other unknowns.
            (jointly if _changes_category(calc, state, iid) else irrelevant).append(iid)
            continue
        settling = sum(1 for n in left if n == 1)
        mean_left = sum(left) / len(left)
        entry_d: dict[str, Any] = {
            "item": iid,
            "label": item.label,
            "kind": item.kind,
            "question": item.question or item.label,
            "settles_decision_in": f"{settling} of {len(outcomes)} answers",
            "outcomes": outcomes,
            # Prefer items that settle more often, then narrow more on average; among
            # equals, ask for data before asking for a judgment.
            "_rank": (-settling / len(outcomes), mean_left, item.kind == "judgment"),
        }
        if iid in norm.known_ranges:
            lo, hi = norm.known_ranges[iid]
            entry_d["known_range"] = [_bound(lo), _bound(hi)]
        decisive.append(entry_d)
    decisive.sort(key=lambda d: d["_rank"])
    for d in decisive:
        del d["_rank"]

    components = []
    for comp in calc.components:
        pts = sorted(component_points(comp, state))
        entry: dict[str, Any] = {"component": comp.id, "label": comp.label}
        if len(pts) == 1:
            entry["points"] = _fmt(pts[0])
        else:
            entry["points_range"] = [_fmt(pts[0]), _fmt(pts[-1])]
            entry["unknown_items"] = [i for i in comp.items if _uncertain(state, i)]
        components.append(entry)

    result: dict[str, Any] = {
        "calculator": calc.id,
        "calculator_version": calc.version,
        "settled": settled,
        "category": ordered[0] if settled and not score_only else None,
        "possible_categories": [] if score_only else ordered,
        "worst_case_category": None if score_only else ordered[-1],
        "score": _fmt(next(iter(scores))) if len(scores) == 1 else None,
        "score_range": [_fmt(min(scores)), _fmt(max(scores))],
        "decisive_unknowns": decisive,
        "jointly_relevant_unknowns": jointly,
        "irrelevant_unknowns": irrelevant,
        "components": components,
    }
    return result, decisive, settled, unknown_ids


def evaluate(
    calc: Calculator,
    inputs: dict[str, Any] | None = None,
    *,
    normal_ranges: Mapping[str, Any] | None = None,
    units: Mapping[str, Any] | None = None,
    require_units: bool = False,
) -> dict[str, Any]:
    """Evaluate a calculator on partial inputs.

    `inputs` maps item id to a value. Items that are omitted, None, or "unknown" are unknown.
    Boolean items take present/absent (or true/false); ordinal items take one of their
    levels; numeric items take a number in the item's unit, a range {"min": x, "max": y}
    (either bound may be left out), or "normal" when the item has a normal range.

    `normal_ranges` maps item ids to a site's own [lo, hi] (for example its laboratory's
    reference range), replacing the spec's default for "normal". Ids this calculator does not
    have are ignored, so one mapping can serve every calculator.

    `units` maps item ids to the unit the site reports that item in (one the item declares):
    a number sent without a unit, or with the unit "not stated", is read in it and converted.
    A unit sent with the value wins. With `require_units`, an item that declares other units
    never takes a number alone: the caller sends the unit the source gives, or "not stated",
    which is accepted only when the site has a unit for the item. Normal ranges and the
    accepted range are always in the item's own unit.
    """
    ranges = normal_ranges_in_use(calc, normal_ranges)
    norm = _normalize(calc, inputs, ranges, units, require_units)
    if calc.formula is not None:
        result, decisive, settled, unknown_ids = formula_result(calc, norm)
    else:
        result, decisive, settled, unknown_ids = _additive_result(calc, norm)
    score_only = not calc.categories
    if settled and unknown_ids:
        what = "score" if score_only else "category"
        result["note"] = (
            f"The {what} is settled: no value of the remaining unknown items can change it."
        )
    elif not settled:
        ask = "a decisive unknown" if decisive else "the jointly relevant unknowns"
        what = "score" if score_only else "category"
        result["note"] = (
            f"Not settled. Unknown items were not assumed normal. Resolve {ask} (ask the "
            f"clinician) and evaluate again; do not report a single {what} yet."
        )
    if score_only:
        result["score_only"] = True
    if norm.normal_assumed:
        result["normal_assumed"] = {
            iid: {"range": [_fmt(lo), _fmt(hi)], "unit": calc.items[iid].unit, "source": source}
            for iid, (lo, hi, source) in norm.normal_assumed.items()
        }
    if norm.converted:
        result["converted"] = norm.converted
    judgment_pending = [d["item"] for d in decisive if d["kind"] == "judgment"]
    if judgment_pending:
        result["judgment_items_pending"] = judgment_pending
        result["judgment_note"] = (
            "These items are clinician judgments. Ask the clinician; do not infer them from a note."
        )
    return result


def schema(
    calc: Calculator,
    *,
    normal_ranges: Mapping[str, Any] | None = None,
    units: Mapping[str, Any] | None = None,
    require_units: bool = False,
) -> dict[str, Any]:
    """A description of a calculator's inputs and outputs, for clients and LLMs.
    `normal_ranges`, `units` and `require_units` are as in `evaluate`."""
    ranges = normal_ranges_in_use(calc, normal_ranges)
    items = []
    for item in calc.items.values():
        entry: dict[str, Any] = {
            "id": item.id,
            "label": item.label,
            "type": item.type,
            "kind": item.kind,
        }
        if item.type == "boolean":
            entry["values"] = ["present", "absent", "unknown"]
        elif item.type == "ordinal":
            entry["values"] = [*item.levels, "unknown"]
        else:
            entry["unit"] = item.unit
            if item.accepts is not None:
                entry["accepts"] = [_fmt(item.accepts[0]), _fmt(item.accepts[1])]
            if item.units:
                entry["other_units"] = list(item.units)
                if item.unit_labels:
                    entry["unit_labels"] = dict(item.unit_labels)
            ranged = 'a range {"min": x, "max": y} when the source gives only bounds'
            number = f"number in {item.unit}"
            site_unit = None
            if units and item.id in units:
                site_unit, _ = _unit_factor(calc, item, units[item.id])
                entry["site_unit"] = site_unit
            if require_units and item.units:
                entry["unit_required"] = True
                no_unit = (
                    f'"unit": "{UNIT_NOT_STATED}" only if the source gives the number with no '
                    f"unit at all (this site's unit, {site_unit}, is then used)"
                    if site_unit
                    else "if the source gives no unit, ask for it"
                )
                number = (
                    '{"value": x, "unit": u} with u one of '
                    f"{[item.unit, *item.units]}, as the source gives it; {no_unit}; a number "
                    "alone is refused"
                )
                ranged = ranged.replace('"max": y}', '"max": y, "unit": u}')
            elif site_unit and site_unit != item.unit:
                number = (
                    f"number in {site_unit} (this site's unit; the tool converts it to "
                    f"{item.unit})"
                )
            if item.id in ranges:
                lo, hi, source = ranges[item.id]
                entry["normal"] = [_fmt(lo), _fmt(hi)]
                entry["normal_source"] = source
                entry["values"] = (
                    f"{number}; 'normal' when the source says only that it is "
                    f"normal (assumed {lo:g} to {hi:g} {item.unit}); {ranged}; or unknown"
                )
            else:
                entry["values"] = (
                    f"{number}; {ranged}; or unknown (no 'normal' for this item)"
                )
        if item.question:
            entry["question"] = item.question
        if item.notes:
            entry["notes"] = list(item.notes)
        items.append(entry)

    components = []
    for comp in calc.components:
        c: dict[str, Any] = {"id": comp.id, "label": comp.label, "rule": comp.rule}
        c.update(describe(calc, comp))
        if comp.group is not None:
            c["group"] = comp.group
        components.append(c)

    out: dict[str, Any] = {
        "id": calc.id,
        "name": calc.name,
        "version": calc.version,
        "purpose": calc.purpose,
        "citation": calc.citation,
        "references": list(calc.references),
        "items": items,
        "components": components,
        "categories": [
            {
                "name": c.name,
                "label": c.label,
                "when": c.condition(),
                "meaning": c.meaning,
            }
            for c in calc.categories
        ],
        "score_only": not calc.categories,
        "notes": list(calc.notes),
        "input_rules": (
            "Pass only what is documented or known. Omit an item, or send 'unknown', when the "
            "source does not mention it: never fill it in as absent or normal. A numeric item "
            "the source describes only as normal takes 'normal' if the item has a normal range, "
            "and is unknown otherwise; one the source gives only as bounds ('heart rate over "
            "100') takes a range {\"min\": x, \"max\": y}. Never invent a number. A value in "
            "one of an item's other_units goes as {\"value\": x, \"unit\": u}: the tool "
            "converts it. An item marked unit_required takes only that form, with the "
            "unit the source gives, or 'not stated' when it gives none and the item has a "
            "site_unit. Items of kind 'judgment' must come from the clinician, not from a "
            "note."
        ),
    }
    if calc.formula is not None:
        f = calc.formula
        out["formula"] = {
            "expression": f.expression,
            "where": dict(f.where),
            "unit": f.unit,
            "decimals": f.decimals,
            "monotonic": dict(f.monotonic),
            "values": {i: {k: _fmt(v) for k, v in m.items()} for i, m in f.level_values.items()},
            "note": (
                "The result is this expression on the items (present = 1, absent = 0). An "
                "unknown numeric item is bounded by the range the calculator accepts."
            ),
        }
    return out
