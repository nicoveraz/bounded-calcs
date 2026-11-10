"""Verify a calculator spec against an independent reference function.

A YAML spec is trusted only after it has been compared with a plain-Python function written
separately from the primary source. `assert_matches_reference` makes three comparisons:

1. Complete inputs. For every combination of item values (numeric items are probed at each
   threshold and on both sides of it), score and category must be identical.
2. Partial inputs. For random sets of known items, the engine's score range and possible
   categories must equal what trying every completion in the reference gives.
3. Unknown items. The engine's decisive / jointly relevant / irrelevant lists must match the
   same brute-force enumeration. An unknown item is decisive if knowing it alone can rule out
   a category; jointly relevant if it is not decisive but, for some values of the other
   unknowns, changing it changes the category; irrelevant otherwise.

4. "normal". For a numeric item with a normal range, the reference must give the same score
   everywhere in the range (so the range crosses no threshold of the source), and the engine
   must treat "normal" exactly like a number inside the range.

The partial inputs include random ones and, for every component with more than one item,
every combination of known, absent and unknown for its items, because interactions inside a
component (a count of risk factors, "A or B") are where the classification is hardest.

One call therefore checks both the spec and the bounding engine against the source. It cannot
catch a threshold that is wrong in the same way in the spec and in the reference: boundary
tests written from the source's own numbers, and physician review, cover that.

    def reference(v):            # v: bool / level name / number per item id
        score = v["confusion"] + (v["urea"] > 7) + ...
        return score, "low" if score <= 1 else "moderate" if score == 2 else "high"

    assert_matches_reference(calc, reference)
"""

from __future__ import annotations

import itertools
import math
import random
from collections.abc import Callable, Iterator, Mapping
from typing import Any

from bounded_calcs.engine import _fmt, evaluate
from bounded_calcs.spec import Calculator, band_probes

Reference = Callable[[Mapping[str, Any]], tuple[float, str]]

# Above this many combinations, complete inputs are sampled instead of enumerated.
MAX_EXHAUSTIVE = 200_000


def item_values(calc: Calculator, item_id: str, extra: Any = ()) -> list[Any]:
    """Every value worth testing for an item: both booleans, every level, or numbers at and on
    both sides of each threshold (plus any `extra` numbers)."""
    item = calc.items[item_id]
    if item.type == "boolean":
        return [True, False]
    if item.type == "ordinal":
        return list(item.levels)
    return sorted({*band_probes(calc.numeric_bands(item_id)), *(float(x) for x in extra)})


def complete_inputs(
    calc: Calculator,
    extra_values: Mapping[str, Any] | None = None,
    limit: int = MAX_EXHAUSTIVE,
    seed: int = 0,
) -> Iterator[dict[str, Any]]:
    """Complete inputs for a calculator: every combination of `item_values` when there are at
    most `limit` of them, otherwise `limit` random combinations (fixed seed)."""
    ids = list(calc.items)
    domains = [item_values(calc, i, (extra_values or {}).get(i, ())) for i in ids]
    if math.prod(len(d) for d in domains) <= limit:
        for combo in itertools.product(*domains):
            yield dict(zip(ids, combo))
    else:
        rng = random.Random(seed)
        for _ in range(limit):
            yield {i: rng.choice(d) for i, d in zip(ids, domains)}


def _show(label: str, calc: Calculator, values: Mapping[str, Any], lines: list[str]) -> str:
    return (
        f"{calc.id}: {label}\n  inputs: {dict(values)}\n"
        + "\n".join(f"  {line}" for line in lines)
        + "\nRe-read the source to decide which side is wrong. Never fix one by copying the other."
    )


def assert_matches_reference(
    calc: Calculator,
    reference: Reference,
    extra_values: Mapping[str, Any] | None = None,
    *,
    trials: int = 150,
    max_completions: int = 4000,
    seed: int = 0,
) -> dict[str, int]:
    """Compare `calc` with `reference` on complete and partial inputs (see module docstring).

    `reference(values)` returns `(score, category_name)` for a complete input, where `values`
    maps each item id to a bool (boolean items), a level name (ordinal items) or a number
    (numeric items). `extra_values` adds numbers to probe for numeric items, e.g.
    `{"age": [44, 45, 64, 65]}`. Raises AssertionError on the first disagreement.
    """
    extra_values = dict(extra_values or {})
    bad = [i for i in extra_values if i not in calc.items or calc.items[i].type != "numeric"]
    if bad:
        raise ValueError(f"{calc.id}: extra_values only apply to numeric items, got {bad}")
    names = [c.name for c in calc.categories]
    ids = list(calc.items)
    domains = {i: item_values(calc, i, extra_values.get(i, ())) for i in ids}
    exhaustive = math.prod(len(d) for d in domains.values()) <= MAX_EXHAUSTIVE

    def ref(values: dict[str, Any]) -> tuple[float, str]:
        out = reference(values)
        if not (isinstance(out, tuple) and len(out) == 2 and out[1] in names):
            raise AssertionError(
                f"{calc.id}: reference must return (score, category) with category one of "
                f"{names}; got {out!r} for {values}"
            )
        return out

    # 1. Complete inputs.
    n_complete = 0
    seen: set[str] = set()
    for values in complete_inputs(calc, extra_values, seed=seed):
        result = evaluate(calc, values)
        exp_score, exp_category = ref(dict(values))
        if not result["settled"] or (result["score"], result["category"]) != (
            exp_score,
            exp_category,
        ):
            raise AssertionError(
                _show(
                    "spec and reference disagree on a complete input",
                    calc,
                    values,
                    [
                        f"spec:      score {result['score']}, category {result['category']}",
                        f"reference: score {exp_score}, category {exp_category}",
                    ],
                )
            )
        seen.add(exp_category)
        n_complete += 1
    if exhaustive and seen != set(names):
        raise AssertionError(
            f"{calc.id}: no input ever reaches {sorted(set(names) - seen)}; "
            "check the category cut-offs in the spec and in the reference"
        )

    # 2 and 3. Partial inputs: bounds and the classification of unknown items.
    def check(known: dict[str, Any], unknown: list[str]) -> None:
        combos = list(itertools.product(*(domains[i] for i in unknown)))
        outcomes = [ref({**known, **dict(zip(unknown, combo))}) for combo in combos]
        scores = {s for s, _ in outcomes}
        cats = {c for _, c in outcomes}
        possible = calc.by_risk(cats)
        settled = len(cats) == 1

        expected: dict[str, Any] = {
            "settled": settled,
            "category": possible[0] if settled else None,
            "possible_categories": possible,
            "worst_case_category": possible[-1],
            "score": next(iter(scores)) if len(scores) == 1 else None,
            "score_range": [min(scores), max(scores)],
        }
        classes: dict[str, set[str]] = {"decisive": set(), "jointly": set(), "irrelevant": set()}
        outcomes_by_item: dict[str, dict[Any, list[str]]] = {}
        for pos, item_id in enumerate(unknown):
            cats_by: dict[Any, set[str]] = {}
            cats_by_rest: dict[tuple[Any, ...], set[str]] = {}
            for combo, (_, c) in zip(combos, outcomes):
                cats_by.setdefault(combo[pos], set()).add(c)
                cats_by_rest.setdefault(combo[:pos] + combo[pos + 1 :], set()).add(c)
            narrows = any(len(c) < len(cats) for c in cats_by.values())
            changes = any(len(c) > 1 for c in cats_by_rest.values())
            kind = (
                "irrelevant" if settled else "decisive" if narrows else "jointly" if changes
                else "irrelevant"
            )  # fmt: skip
            classes[kind].add(item_id)
            outcomes_by_item[item_id] = {v: calc.by_risk(c) for v, c in cats_by.items()}
        expected["decisive_unknowns"] = classes["decisive"]
        expected["jointly_relevant_unknowns"] = classes["jointly"]
        expected["irrelevant_unknowns"] = classes["irrelevant"]

        result = evaluate(calc, known)
        got = {k: result[k] for k in expected}
        got["decisive_unknowns"] = {d["item"] for d in result["decisive_unknowns"]}
        got["jointly_relevant_unknowns"] = set(result["jointly_relevant_unknowns"])
        got["irrelevant_unknowns"] = set(result["irrelevant_unknowns"])
        wrong = [
            f"{k}: engine {got[k]!r}, brute force over the reference {expected[k]!r}"
            for k in expected
            if got[k] != expected[k]
        ]
        for d in result["decisive_unknowns"]:
            item = calc.items[d["item"]]
            if item.type == "numeric" or d["item"] not in outcomes_by_item:
                continue
            want = {
                ("present" if v else "absent") if item.type == "boolean" else v: c
                for v, c in outcomes_by_item[d["item"]].items()
            }
            listed = {o["if"]: o["possible_categories"] for o in d["outcomes"]}
            if listed != want:
                wrong.append(
                    f"outcomes of '{d['item']}': engine {listed!r}, brute force over the "
                    f"reference {want!r}"
                )
        if wrong:
            raise AssertionError(
                _show(
                    f"engine and reference disagree on a partial input (unknown: {unknown})",
                    calc,
                    known,
                    wrong,
                )
            )

    rng = random.Random(seed)
    n_partial = 0
    for _ in range(trials):
        order = ids[:]
        rng.shuffle(order)
        unknown: list[str] = []
        size = 1
        for i in order[: rng.randint(0, len(order))]:
            if size * len(domains[i]) <= max_completions:
                unknown.append(i)
                size *= len(domains[i])
        check({i: rng.choice(domains[i]) for i in ids if i not in unknown}, unknown)
        n_partial += 1

    # Interactions inside one component: every pattern of its items, against one setting of
    # the other items for each score they can add.
    for comp in calc.components:
        if len(comp.items) < 2:
            continue
        others = [i for i in ids if i not in comp.items]
        baseline = {i: domains[i][0] for i in comp.items}
        by_rest: dict[float, dict[str, Any]] = {}
        for values in _sample_assignments(others, domains, rng):
            rest = ref({**values, **baseline})[0]
            by_rest.setdefault(rest, values)
        for pattern in _component_patterns(calc, comp, domains):
            unknown = [i for i, v in pattern.items() if v is None]
            fixed = {i: v for i, v in pattern.items() if v is not None}
            for values in by_rest.values():
                check({**values, **fixed}, unknown)
                n_partial += 1
    # 4. "normal" for numeric items.
    for item in calc.items.values():
        if item.normal is None:
            continue
        lo, hi = item.normal
        inside = sorted({lo, hi, (lo + hi) / 2, *(x for x in domains[item.id] if lo <= x <= hi)})
        for values in complete_inputs(calc, extra_values, limit=2000, seed=seed):
            out = {x: ref({**values, item.id: x})[0] for x in inside}
            if len(set(out.values())) > 1:
                raise AssertionError(
                    _show(
                        f"the normal range of '{item.id}' [{lo:g}, {hi:g}] crosses a threshold "
                        "of the reference",
                        calc,
                        values,
                        [f"reference score with {item.id}={x:g}: {s}" for x, s in out.items()],
                    )
                )
        expected_note = {item.id: {"range": [_fmt(lo), _fmt(hi)], "unit": item.unit}}
        for _ in range(trials):
            known = {i: rng.choice(domains[i]) for i in ids if i != item.id and rng.random() < 0.5}
            got = evaluate(calc, {**known, item.id: "normal"})
            want = evaluate(calc, {**known, item.id: (lo + hi) / 2})
            note = got.pop("normal_assumed", None)
            if got != want or note != expected_note:
                raise AssertionError(
                    _show(
                        f"'normal' for '{item.id}' is not treated like a number in its range",
                        calc,
                        known,
                        [f"normal_assumed: {note!r}", "results differ" if got != want else ""],
                    )
                )
    return {"complete_inputs": n_complete, "partial_inputs": n_partial}


def _sample_assignments(
    ids: list[str], domains: Mapping[str, list[Any]], rng: random.Random, limit: int = 20_000
) -> Iterator[dict[str, Any]]:
    """Every assignment of `ids` when there are at most `limit`, otherwise `limit` random ones."""
    if math.prod(len(domains[i]) for i in ids) <= limit:
        for combo in itertools.product(*(domains[i] for i in ids)):
            yield dict(zip(ids, combo))
    else:
        for _ in range(limit):
            yield {i: rng.choice(domains[i]) for i in ids}


def _component_patterns(
    calc: Calculator, comp: Any, domains: Mapping[str, list[Any]]
) -> Iterator[dict[str, Any]]:
    """Known and unknown patterns for the items of one component (None means unknown).

    For a count, members are interchangeable, so one pattern per number of present, absent
    and unknown members is enough; the override item takes each of its states."""
    if comp.rule == "count":
        members = [i for i in comp.items if i != comp.override]
        overrides = [True, False, None] if comp.override else [None]
        m = len(members)
        for present in range(m + 1):
            for absent in range(m - present + 1):
                states = [True] * present + [False] * absent + [None] * (m - present - absent)
                for ov in overrides:
                    pattern = dict(zip(members, states))
                    if comp.override:
                        pattern[comp.override] = ov
                    yield pattern
        return
    for combo in itertools.product(*([*domains[i], None] for i in comp.items)):
        yield dict(zip(comp.items, combo))
