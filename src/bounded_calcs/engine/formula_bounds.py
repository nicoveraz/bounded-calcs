"""Bounds for formula calculators: the result is an expression on the items.

Each item has a set of values it can still take: one value when known; both, or every level,
for an unknown yes/no or ordinal item; an interval for a numeric item (its known range, or the
range its calculator accepts when nothing is known). The spec declares, and the loader has
checked, that the result moves in one direction with each numeric item, so for each
combination of the yes/no and ordinal items the lowest and highest results are at the ends of
the numeric intervals. The result range is therefore exact, and every category whose cut-off
range it touches is possible.

Which unknown items matter is decided conservatively: an unknown item is called irrelevant
only when the category is settled or the item cannot move the result at all. Otherwise it is
decisive if fixing it at some value in its range rules a category out, and jointly relevant
if not. An unneeded question is possible; a needed one is never dropped.
"""

from __future__ import annotations

import itertools
from typing import Any

from bounded_calcs.engine.inputs import _Normalized
from bounded_calcs.engine.state import _fmt, _uncertain
from bounded_calcs.formula import grid
from bounded_calcs.spec import Calculator

Domains = dict[str, Any]
"""Per item: a list of values (yes/no and ordinal items) or a (lo, hi) pair (numeric items)."""


def domains(calc: Calculator, norm: _Normalized) -> Domains:
    out: Domains = {}
    for iid, item in calc.items.items():
        known = norm.state[iid]
        if item.type == "boolean":
            out[iid] = [True, False] if known is None else [known]
        elif item.type == "ordinal":
            out[iid] = list(item.levels) if known is None else [known]
        else:
            assert item.accepts is not None
            if iid in norm.exact:
                out[iid] = (norm.exact[iid], norm.exact[iid])
            else:
                lo, hi = norm.known_ranges.get(iid, item.accepts)
                out[iid] = (max(lo, item.accepts[0]), min(hi, item.accepts[1]))
    return out


def _intervals(calc: Calculator, doms: Domains) -> list[tuple[float, float]]:
    """The result's lowest and highest value for each combination of the discrete items."""
    formula = calc.formula
    assert formula is not None
    discrete = [i for i, d in doms.items() if isinstance(d, list)]
    low: dict[str, float] = {}
    high: dict[str, float] = {}
    for iid, d in doms.items():
        if isinstance(d, tuple):
            rising = formula.monotonic[iid] == "increasing"
            low[iid], high[iid] = (d[0], d[1]) if rising else (d[1], d[0])
    out = []
    for combo in itertools.product(*(doms[i] for i in discrete)):
        fixed = dict(zip(discrete, combo))
        out.append((formula.value({**fixed, **low}), formula.value({**fixed, **high})))
    return out


def _outcomes(calc: Calculator, intervals: list[tuple[float, float]]) -> set[Any]:
    """What the result decides over these intervals: the categories they touch or, for a
    score-only calculator, the distinct results (a single one only when the result is exact)."""
    if not calc.categories:
        return {x for a, b in intervals for x in (a, b)}
    formula = calc.formula
    assert formula is not None
    step = 10.0**-formula.decimals if formula.decimals is not None else None
    found = set()
    for a, b in intervals:
        probes = [a, b]
        for c in calc.categories[1:]:
            t = c.lower
            if a <= t <= b:
                eps = step if step is not None else 1e-9 * max(1.0, abs(t))
                probes += [t, t - eps, t + eps]
        found |= {calc.category(x).name for x in probes if a <= x <= b}
    return found


def _describe(calc: Calculator, iid: str, value: Any) -> str:
    item = calc.items[iid]
    if item.type == "boolean":
        return "present" if value else "absent"
    if item.type == "ordinal":
        return str(value)
    return f"{value:g} {item.unit}"


def formula_result(
    calc: Calculator, norm: _Normalized
) -> tuple[dict[str, Any], list[dict[str, Any]], bool, list[str]]:
    """The bounded result of a formula calculator: (result, decisive, settled, unknown ids)."""
    formula = calc.formula
    assert formula is not None
    score_only = not calc.categories
    doms = domains(calc, norm)
    intervals = _intervals(calc, doms)
    lo, hi = min(a for a, _ in intervals), max(b for _, b in intervals)
    outcomes = _outcomes(calc, intervals)
    ordered = calc.by_risk(outcomes)
    settled = len(outcomes) == 1
    unknown_ids = [
        i
        for i, d in doms.items()
        if (isinstance(d, list) and len(d) > 1) or (isinstance(d, tuple) and d[0] < d[1])
    ]
    assert set(unknown_ids) >= {i for i in norm.state if _uncertain(norm.state, i)}

    def left(sub: Domains) -> tuple[list[Any], tuple[float, float]]:
        ivs = _intervals(calc, sub)
        return (
            calc.by_risk(_outcomes(calc, ivs)),
            (min(a for a, _ in ivs), max(b for _, b in ivs)),
        )

    decisive: list[dict[str, Any]] = []
    irrelevant: list[str] = []
    jointly: list[str] = []
    for iid in unknown_ids:
        item = calc.items[iid]
        d = doms[iid]
        if isinstance(d, list):
            shown = interior = list(d)
        else:
            shown = [d[0], d[1]]
            interior = grid(d[0], d[1], 5)
        fixed = lambda v: {**doms, iid: [v] if isinstance(d, list) else (v, v)}  # noqa: E731
        moves = len({left(fixed(v))[1] for v in interior}) > 1
        if settled or not moves:
            irrelevant.append(iid)
            continue
        listed = []
        counts = []
        for v in shown:
            cats, (a, b) = left(fixed(v))
            counts.append(len(cats))
            outcome: dict[str, Any] = (
                {"score_range": [_fmt(a), _fmt(b)]} if score_only else {"possible_categories": cats}
            )
            listed.append({"if": _describe(calc, iid, v), **outcome})
        narrows = any(len(left(fixed(v))[0]) < len(outcomes) for v in interior)
        if not narrows and not score_only:
            jointly.append(iid)
            continue
        settling = sum(1 for n in counts if n == 1)
        entry: dict[str, Any] = {
            "item": iid,
            "label": item.label,
            "kind": item.kind,
            "question": item.question or item.label,
            "settles_decision_in": f"{settling} of {len(listed)} answers",
            "outcomes": listed,
            "_rank": (-settling / len(listed), sum(counts) / len(counts), item.kind == "judgment"),
        }
        if isinstance(d, tuple):
            entry["known_range"] = [_fmt(d[0]), _fmt(d[1])]
            entry["outcomes_shown_for"] = "the lowest and the highest value the item can take"
        decisive.append(entry)
    decisive.sort(key=lambda e: e["_rank"])
    for e in decisive:
        del e["_rank"]

    result: dict[str, Any] = {
        "calculator": calc.id,
        "calculator_version": calc.version,
        "settled": settled,
        "category": ordered[0] if settled and not score_only else None,
        "possible_categories": [] if score_only else ordered,
        "worst_case_category": None if score_only else ordered[-1],
        "score": _fmt(lo) if lo == hi else None,
        "score_range": [_fmt(lo), _fmt(hi)],
        "decisive_unknowns": decisive,
        "jointly_relevant_unknowns": jointly,
        "irrelevant_unknowns": irrelevant,
        "components": [],
        "formula": {
            "expression": formula.expression,
            "unit": formula.unit,
            "inputs": {
                i: (_describe(calc, i, d[0]) if len(d) == 1 else "unknown")
                if isinstance(d, list)
                else (_fmt(d[0]) if d[0] == d[1] else [_fmt(d[0]), _fmt(d[1])])
                for i, d in doms.items()
            },
        },
    }
    return result, decisive, settled, unknown_ids
