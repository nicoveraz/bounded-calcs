"""Verify a calculator spec against an independent reference function.

A YAML spec is trusted only after it has been compared with a plain-Python function written
separately from the primary source. `assert_matches_reference` makes three comparisons:

1. Complete inputs. For every combination of item values (numeric items are probed at each
   threshold and on both sides of it), score and category must be identical.
2. Partial inputs. For random sets of known items, the engine's score range and possible
   categories must equal what trying every completion in the reference gives.
   A score-only calculator (no categories) is compared on the score alone: the reference
   returns `(score, None)`, and the score plays the part of the category below.
3. Unknown items. The engine's decisive / jointly relevant / irrelevant lists must match the
   same brute-force enumeration. An unknown item is decisive if knowing it alone can rule out
   a category; jointly relevant if it is not decisive but, for some values of the other
   unknowns, changing it changes the category; irrelevant otherwise.

4. Ranges. A numeric item given as a range ({"min": x, "max": y}, or "normal" for an item
   with a normal range) must give the same result as trying every value of the range in the
   reference: settled if the range stays on one side of every threshold, otherwise the item
   is still a question.

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

from bounded_calcs.engine import _fmt, evaluate, normal_ranges_in_use
from bounded_calcs.spec import Calculator, band_probes

Reference = Callable[[Mapping[str, Any]], tuple[float, str | None]]

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
    normal_ranges: Mapping[str, Any] | None = None,
    trials: int = 150,
    max_completions: int = 4000,
    seed: int = 0,
) -> dict[str, int]:
    """Compare `calc` with `reference` on complete and partial inputs (see module docstring).

    `reference(values)` returns `(score, category_name)` for a complete input (`(score, None)`
    for a score-only calculator), where `values`
    maps each item id to a bool (boolean items), a level name (ordinal items) or a number
    (numeric items). `extra_values` adds numbers to probe for numeric items, e.g.
    `{"age": [44, 45, 64, 65]}`. `normal_ranges` are a site's own normal ranges, passed to the
    engine as in `evaluate`. Raises AssertionError on the first disagreement.
    """
    extra_values = dict(extra_values or {})
    bad = [i for i in extra_values if i not in calc.items or calc.items[i].type != "numeric"]
    if bad:
        raise ValueError(f"{calc.id}: extra_values only apply to numeric items, got {bad}")
    names = [c.name for c in calc.categories]
    score_only = not names
    ids = list(calc.items)
    domains = {i: item_values(calc, i, extra_values.get(i, ())) for i in ids}
    exhaustive = math.prod(len(d) for d in domains.values()) <= MAX_EXHAUSTIVE

    def ref(values: dict[str, Any]) -> tuple[float, str | None]:
        out = reference(values)
        ok = isinstance(out, tuple) and len(out) == 2
        if not (ok and (out[1] is None if score_only else out[1] in names)):
            want = "None (score-only calculator)" if score_only else f"one of {names}"
            raise AssertionError(
                f"{calc.id}: reference must return (score, category) with category {want}; "
                f"got {out!r} for {values}"
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
    if exhaustive and not score_only and seen != set(names):
        raise AssertionError(
            f"{calc.id}: no input ever reaches {sorted(set(names) - seen)}; "
            "check the category cut-offs in the spec and in the reference"
        )

    # 2 and 3. Partial inputs: bounds and the classification of unknown items.
    def bands_of(item_id: str, values: list[Any]) -> set[int]:
        bands = calc.numeric_bands(item_id)
        return {next(i for i, b in enumerate(bands) if b.matches(x)) for x in values}

    def check(
        known: dict[str, Any],
        unknown: list[str],
        ranged: Mapping[str, tuple[Any, list[float]]] | None = None,
    ) -> None:
        # `ranged` items are given to the engine as a range (or "normal") and tried at every
        # value of the range by the brute force. A range inside one band is known to the
        # engine; a wider one leaves the item uncertain, like an unknown item.
        ranged = dict(ranged or {})
        wide = [i for i, (_, vals) in ranged.items() if len(bands_of(i, vals)) > 1]
        narrow = {i: vals[0] for i, (_, vals) in ranged.items() if i not in wide}
        varying = list(unknown) + wide
        doms = [domains[i] for i in unknown] + [ranged[i][1] for i in wide]
        combos = list(itertools.product(*doms))
        base = {**known, **narrow}
        outcomes = [ref({**base, **dict(zip(varying, combo))}) for combo in combos]
        if score_only:  # the score is what is being decided
            outcomes = [(s, s) for s, _ in outcomes]
        unknown = varying
        scores = {s for s, _ in outcomes}
        cats = {c for _, c in outcomes}
        possible = calc.by_risk(cats)
        settled = len(cats) == 1

        expected: dict[str, Any] = {
            "settled": settled,
            "category": possible[0] if settled and not score_only else None,
            "possible_categories": [] if score_only else possible,
            "worst_case_category": None if score_only else possible[-1],
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

        engine_input = {**known, **{i: given for i, (given, _) in ranged.items()}}
        result = evaluate(calc, engine_input, normal_ranges=normal_ranges)
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
            if score_only:
                want = {k: [min(c), max(c)] for k, c in want.items()}
                listed = {o["if"]: o["score_range"] for o in d["outcomes"]}
            else:
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
                    engine_input,
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
        known = {i: rng.choice(domains[i]) for i in ids if i not in unknown}
        # Sometimes give one known numeric item as a range instead of a number.
        numeric_known = [i for i in known if calc.items[i].type == "numeric"]
        ranged: dict[str, tuple[Any, list[float]]] = {}
        if numeric_known and rng.random() < 0.5:
            i = rng.choice(numeric_known)
            a, b = sorted(rng.sample(domains[i], 2) if len(domains[i]) > 1 else domains[i] * 2)
            given: dict[str, float] = rng.choice([{"min": a, "max": b}, {"min": a}, {"max": b}])
            lo, hi = given.get("min", -math.inf), given.get("max", math.inf)
            ranged[i] = (given, [x for x in domains[i] if lo <= x <= hi])
            del known[i]
        check(known, unknown, ranged)
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
    # 4. "normal" for numeric items: the engine must treat it as every value in the range in
    # use (the site's range when one is given, otherwise the spec's default).
    for iid, (lo, hi, source) in normal_ranges_in_use(calc, normal_ranges).items():
        inside = sorted({lo, hi, (lo + hi) / 2, *(x for x in domains[iid] if lo <= x <= hi)})
        others = [i for i in ids if i != iid]
        for _ in range(trials):
            rng.shuffle(others)
            unknown, size = [], len(inside)
            for i in others[: rng.randint(0, len(others))]:
                if size * len(domains[i]) <= max_completions:
                    unknown.append(i)
                    size *= len(domains[i])
            known = {i: rng.choice(domains[i]) for i in others if i not in unknown}
            check(known, unknown, {iid: ("normal", inside)})
            n_partial += 1
        note = evaluate(calc, {iid: "normal"}, normal_ranges=normal_ranges)["normal_assumed"]
        want = {iid: {"range": [_fmt(lo), _fmt(hi)], "unit": calc.items[iid].unit, "source": source}}
        if note != want:
            raise AssertionError(f"{calc.id}: normal_assumed is {note!r}, expected {want!r}")
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


def assert_formula_matches_reference(
    calc: Calculator,
    reference: Reference,
    *,
    points: int = 4,
    trials: int = 150,
    seed: int = 0,
) -> dict[str, int]:
    """Compare a formula calculator with an independent `reference` (see module docstring).

    `reference(values)` returns `(result, category_name)`, or `(result, None)` for a
    score-only calculator. Numeric items are tried at `points` evenly spaced values of the
    range the calculator accepts, both ends included.

    1. Complete inputs: result and category must be equal on the whole grid.
    2. Partial inputs: for random sets of unknown items, the engine's result range must equal
       the lowest and highest reference result over the grid, every category the reference
       reaches must be among the engine's possible categories, and no item the engine calls
       irrelevant may change the reference's result or category.
    """
    from bounded_calcs.formula import grid

    if calc.formula is None:
        raise ValueError(f"{calc.id}: not a formula calculator; use assert_matches_reference")
    names = [c.name for c in calc.categories]
    domains: dict[str, list[Any]] = {}
    for iid, item in calc.items.items():
        if item.type == "boolean":
            domains[iid] = [True, False]
        elif item.type == "ordinal":
            domains[iid] = list(item.levels)
        else:
            assert item.accepts is not None
            domains[iid] = grid(item.accepts[0], item.accepts[1], points)
    ids = list(domains)

    def close(a: float, b: float) -> bool:
        return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9)

    def ref(values: dict[str, Any]) -> tuple[float, str | None]:
        out = reference(values)
        ok = isinstance(out, tuple) and len(out) == 2
        if not (ok and (out[1] in names if names else out[1] is None)):
            raise AssertionError(f"{calc.id}: reference returned {out!r} for {values}")
        return out

    n_complete = 0
    for combo in itertools.product(*domains.values()):
        values = dict(zip(ids, combo))
        result = evaluate(calc, values)
        exp_score, exp_category = ref(values)
        if not (
            result["score"] is not None
            and close(result["score"], exp_score)
            and result["category"] == exp_category
        ):
            raise AssertionError(
                _show(
                    "spec and reference disagree on a complete input",
                    calc,
                    values,
                    [
                        f"spec:      result {result['score']}, category {result['category']}",
                        f"reference: result {exp_score}, category {exp_category}",
                    ],
                )
            )
        n_complete += 1

    rng = random.Random(seed)
    n_partial = 0
    for _ in range(trials):
        unknown = rng.sample(ids, rng.randint(1, len(ids)))
        known = {i: rng.choice(domains[i]) for i in ids if i not in unknown}
        combos = list(itertools.product(*(domains[i] for i in unknown)))
        outs = [ref({**known, **dict(zip(unknown, c))}) for c in combos]
        result = evaluate(calc, known)
        lo, hi = min(s for s, _ in outs), max(s for s, _ in outs)
        wrong = []
        if not (close(result["score_range"][0], lo) and close(result["score_range"][1], hi)):
            wrong.append(f"score_range: engine {result['score_range']}, reference [{lo}, {hi}]")
        missing = {c for _, c in outs if c is not None} - set(result["possible_categories"])
        if missing:
            wrong.append(f"categories the reference reaches but the engine omits: {missing}")
        for iid in result["irrelevant_unknowns"]:
            pos = unknown.index(iid)
            by_rest: dict[tuple[Any, ...], set[Any]] = {}
            for c, (s, cat) in zip(combos, outs):
                by_rest.setdefault(c[:pos] + c[pos + 1 :], set()).add(cat if names else s)
            if any(len(v) > 1 for v in by_rest.values()):
                wrong.append(f"'{iid}' is called irrelevant but changes the reference's outcome")
        if wrong:
            raise AssertionError(
                _show(
                    f"engine and reference disagree on a partial input (unknown: {unknown})",
                    calc,
                    known,
                    wrong,
                )
            )
        n_partial += 1
    return {"complete_inputs": n_complete, "partial_inputs": n_partial}
