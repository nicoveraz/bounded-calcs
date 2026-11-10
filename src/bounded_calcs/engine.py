"""Bounded evaluation: what can be concluded when some items are unknown.

The engine never assumes an unknown item is normal or absent. It computes every score the
patient could still have, the decision categories those scores fall into, and which unknown
items could change that set. All results are exact (no sampling): components are independent,
so reachable scores are the sumset of each component's reachable points.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bounded_calcs.spec import Calculator, Component, Item

UNKNOWN_WORDS = {"unknown", "not_mentioned", "not mentioned", "unk", ""}
TRUE_WORDS = {"present", "yes", "true", "y", "1"}
FALSE_WORDS = {"absent", "no", "false", "n", "0"}

# Internal state per item: bool (boolean), str level (ordinal), int band index (numeric),
# or None (unknown).
State = dict[str, Any]


class InputError(ValueError):
    pass


@dataclass(frozen=True)
class _Normalized:
    state: State
    raw_numeric: dict[str, float]


def _normalize(calc: Calculator, inputs: dict[str, Any] | None) -> _Normalized:
    inputs = dict(inputs or {})
    extra = set(inputs) - set(calc.items)
    if extra:
        raise InputError(
            f"{calc.id}: unknown item(s) {sorted(extra)}; valid items: {sorted(calc.items)}"
        )
    state: State = {}
    raw_numeric: dict[str, float] = {}
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
            hint = (
                f"{calc.id}.{iid}: expected a number in {item.unit}, or unknown. Send unknown "
                f"when the source gives no number (for example only 'normal'); got {v!r}"
            )
            if isinstance(v, bool):
                raise InputError(hint)
            try:
                x = float(v)
            except (TypeError, ValueError):
                raise InputError(hint) from None
            if x != x or x in (float("inf"), float("-inf")):
                raise InputError(hint)
            state[iid] = next(i for i, b in enumerate(calc.numeric_bands(iid)) if b.matches(x))
            raw_numeric[iid] = x
    return _Normalized(state, raw_numeric)


def _domain(calc: Calculator, item: Item) -> list[Any]:
    """Every internal value an unknown item could take."""
    if item.type == "boolean":
        return [True, False]
    if item.type == "ordinal":
        return list(item.levels)
    return list(range(len(calc.numeric_bands(item.id))))


def _component_points(comp: Component, state: State) -> set[float]:
    if comp.rule in ("present", "absent"):
        v = state[comp.items[0]]
        assert comp.points is not None
        if v is None:
            return {comp.points, 0.0}
        return {comp.points if v == (comp.rule == "present") else 0.0}
    if comp.rule == "levels":
        v = state[comp.items[0]]
        return {comp.level_points[v]} if v is not None else set(comp.level_points.values())
    if comp.rule == "bands":
        v = state[comp.items[0]]
        return {comp.bands[v].points} if v is not None else {b.points for b in comp.bands}
    if comp.rule == "any_of":
        assert comp.points is not None
        flags = [_condition_met(comp, state, i) for i in comp.items]
        if any(f is True for f in flags):
            return {comp.points}
        return {0.0, comp.points} if any(f is None for f in flags) else {0.0}
    # count
    members = [i for i in comp.items if i != comp.override]
    known = sum(1 for i in members if state[i] is True)
    unknown = sum(1 for i in members if state[i] is None)
    from_count = {_count_points(comp, n) for n in range(known, known + unknown + 1)}
    if comp.override is None:
        return from_count
    ov = state[comp.override]
    assert comp.override_points is not None
    if ov is True:
        return {comp.override_points}
    if ov is False:
        return from_count
    return from_count | {comp.override_points}


def _condition_met(comp: Component, state: State, item_id: str) -> bool | None:
    """Whether one condition of an any_of component is met (None when unknown)."""
    v = state[item_id]
    if v is None:
        return None
    return bool(v) if item_id not in comp.conditions else v == 0


def _count_points(comp: Component, n: int) -> float:
    """Points of a count component when n of its members are present."""
    return next(b.points for b in comp.bands if b.op is None or n >= (b.value or 0))


def _reachable_scores(calc: Calculator, state: State, skip: Component | None = None) -> set[float]:
    scores = {0.0}
    for comp in calc.components:
        if comp is skip:
            continue
        pts = _component_points(comp, state)
        scores = {s + p for s in scores for p in pts}
    return scores


def _flip_pairs(comp: Component, state: State, item_id: str) -> set[tuple[float, float]]:
    """Pairs of points the component can take for two values of the unknown `item_id`, with
    the component's other unknown items held at the same values."""
    if len(comp.items) == 1:
        pts = sorted(_component_points(comp, state))
        return {(a, b) for a in pts for b in pts if a < b}
    if comp.rule == "any_of":
        assert comp.points is not None
        others = [i for i in comp.items if i != item_id]
        if any(_condition_met(comp, state, i) is True for i in others):
            return set()
        return {(0.0, comp.points)}
    # count
    members = [i for i in comp.items if i != comp.override]
    if item_id == comp.override:
        assert comp.override_points is not None
        known = sum(1 for i in members if state[i] is True)
        unknown = sum(1 for i in members if state[i] is None)
        return {
            (comp.override_points, _count_points(comp, n))
            for n in range(known, known + unknown + 1)
        }
    if comp.override is not None and state[comp.override] is True:
        return set()
    others = [i for i in members if i != item_id]
    known = sum(1 for i in others if state[i] is True)
    unknown = sum(1 for i in others if state[i] is None)
    return {
        (_count_points(comp, n), _count_points(comp, n + 1))
        for n in range(known, known + unknown + 1)
    }


def _changes_category(calc: Calculator, state: State, item_id: str) -> bool:
    """True if, for some values of the other unknown items, changing `item_id` changes the
    category. Exact: components are independent, so the rest of the score ranges over the
    sumset of the other components while this component flips between a pair of values."""
    comp = calc.component_of(item_id)
    pairs = [(a, b) for a, b in _flip_pairs(comp, state, item_id) if a != b]
    if not pairs:
        return False
    rest = _reachable_scores(calc, state, skip=comp)
    return any(
        calc.category(r + a).name != calc.category(r + b).name for r in rest for a, b in pairs
    )


def _categories(calc: Calculator, state: State) -> set[str]:
    return {calc.category(s).name for s in _reachable_scores(calc, state)}


def _describe_value(calc: Calculator, item: Item, v: Any) -> str:
    if item.type == "boolean":
        return "present" if v else "absent"
    if item.type == "ordinal":
        return str(v)
    band = calc.numeric_bands(item.id)[v]
    if calc.component_of(item.id).rule == "any_of" and band.op is None:
        met = calc.numeric_bands(item.id)[0]
        return "not " + met.describe(item.unit)
    return band.describe(item.unit)


def _fmt(x: float) -> float | int:
    return int(x) if float(x).is_integer() else x


def evaluate(calc: Calculator, inputs: dict[str, Any] | None = None) -> dict[str, Any]:
    """Evaluate a calculator on partial inputs.

    `inputs` maps item id to a value. Items that are omitted, None, or "unknown" are unknown.
    Boolean items take present/absent (or true/false); ordinal items take one of their
    levels; numeric items take a number in the item's unit.
    """
    norm = _normalize(calc, inputs)
    state = norm.state
    scores = _reachable_scores(calc, state)
    cats = {calc.category(s).name for s in scores}
    ordered = calc.by_risk(cats)
    settled = len(cats) == 1
    unknown_ids = [i for i, v in state.items() if v is None]

    decisive: list[dict[str, Any]] = []
    irrelevant: list[str] = []
    jointly: list[str] = []
    for iid in unknown_ids:
        item = calc.items[iid]
        if settled:
            irrelevant.append(iid)
            continue
        outcomes = []
        for v in _domain(calc, item):
            sub = calc.by_risk(_categories(calc, {**state, iid: v}))
            outcomes.append({"if": _describe_value(calc, item, v), "possible_categories": sub})
        narrows = any(len(o["possible_categories"]) < len(cats) for o in outcomes)
        if not narrows:
            # Knowing it alone cannot rule out a category, but it may still change the
            # category for some values of the other unknowns.
            (jointly if _changes_category(calc, state, iid) else irrelevant).append(iid)
            continue
        settling = sum(1 for o in outcomes if len(o["possible_categories"]) == 1)
        mean_left = sum(len(o["possible_categories"]) for o in outcomes) / len(outcomes)
        decisive.append(
            {
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
        )
    decisive.sort(key=lambda d: d["_rank"])
    for d in decisive:
        del d["_rank"]

    components = []
    for comp in calc.components:
        pts = sorted(_component_points(comp, state))
        entry: dict[str, Any] = {"component": comp.id, "label": comp.label}
        if len(pts) == 1:
            entry["points"] = _fmt(pts[0])
        else:
            entry["points_range"] = [_fmt(pts[0]), _fmt(pts[-1])]
            entry["unknown_items"] = [i for i in comp.items if state[i] is None]
        components.append(entry)

    result: dict[str, Any] = {
        "calculator": calc.id,
        "calculator_version": calc.version,
        "settled": settled,
        "category": ordered[0] if settled else None,
        "possible_categories": ordered,
        "worst_case_category": ordered[-1],
        "score": _fmt(next(iter(scores))) if len(scores) == 1 else None,
        "score_range": [_fmt(min(scores)), _fmt(max(scores))],
        "decisive_unknowns": decisive,
        "jointly_relevant_unknowns": jointly,
        "irrelevant_unknowns": irrelevant,
        "components": components,
    }
    if settled and unknown_ids:
        result["note"] = (
            "The category is settled: no value of the remaining unknown items can change it."
        )
    elif not settled:
        ask = "a decisive unknown" if decisive else "the jointly relevant unknowns"
        result["note"] = (
            f"Not settled. Unknown items were not assumed normal. Resolve {ask} (ask the "
            "clinician) and evaluate again; do not report a single category yet."
        )
    judgment_pending = [d["item"] for d in decisive if d["kind"] == "judgment"]
    if judgment_pending:
        result["judgment_items_pending"] = judgment_pending
        result["judgment_note"] = (
            "These items are clinician judgments. Ask the clinician; do not infer them from a note."
        )
    return result


def schema(calc: Calculator) -> dict[str, Any]:
    """A description of a calculator's inputs and outputs, for clients and LLMs."""
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
            entry["values"] = f"number in {item.unit}, or unknown"
        if item.question:
            entry["question"] = item.question
        if item.notes:
            entry["notes"] = list(item.notes)
        items.append(entry)

    components = []
    for comp in calc.components:
        c: dict[str, Any] = {"id": comp.id, "label": comp.label, "rule": comp.rule}
        if comp.rule in ("present", "absent"):
            c["item"], c["points"] = comp.items[0], _fmt(comp.points or 0)
        elif comp.rule == "levels":
            c["item"] = comp.items[0]
            c["points"] = {k: _fmt(v) for k, v in comp.level_points.items()}
        elif comp.rule == "bands":
            unit = calc.items[comp.items[0]].unit
            c["item"] = comp.items[0]
            c["bands"] = [{"when": b.describe(unit), "points": _fmt(b.points)} for b in comp.bands]
        elif comp.rule == "any_of":
            conds = []
            for i in comp.items:
                if i in comp.conditions:
                    conds.append(f"{i} {comp.conditions[i].describe(calc.items[i].unit)}")
                else:
                    conds.append(f"{i} present")
            c["any_of"], c["points"] = conds, _fmt(comp.points or 0)
        else:
            c["items"] = [i for i in comp.items if i != comp.override]
            c["points_by_count"] = [
                {"when": b.describe("present") if b.op else "otherwise", "points": _fmt(b.points)}
                for b in comp.bands
            ]
            if comp.override:
                c["override"] = {"item": comp.override, "points": _fmt(comp.override_points or 0)}
        components.append(c)

    return {
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
                "when": "lowest" if c.lower == float("-inf")
                else f"score {'>' if c.lower_strict else '>='} {c.lower:g}",
                "meaning": c.meaning,
            }
            for c in calc.categories
        ],
        "notes": list(calc.notes),
        "input_rules": (
            "Pass only what is documented or known. Omit an item, or send 'unknown', when the "
            "source does not mention it: never fill it in as absent or normal. A numeric item "
            "described only as 'normal', with no number, is unknown. Items of kind 'judgment' "
            "must come from the clinician, not from a note."
        ),
    }
