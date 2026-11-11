"""Formula calculators: the expression language, the loader's checks and the bounds.

The calculators here are toys with made-up items; expected values are worked out by hand in
the comments.
"""

import copy

import pytest

from bounded_calcs import InputError, SpecError, evaluate, parse, schema
from bounded_calcs.testing import (
    assert_formula_matches_reference,
    assert_matches_reference,
)


def _num(iid, lo, hi, unit="units", **more):
    return {"id": iid, "label": iid, "type": "numeric", "kind": "measurement", "unit": unit,
            "accepts": [lo, hi], **more}  # fmt: skip


RATIO = {
    "id": "toy_ratio",
    "name": "Toy ratio",
    "citation": "None",
    "higher_is_higher_risk": False,
    "items": [_num("a", 50, 100), _num("b", 0.2, 1.0), _num("c", 5, 60)],
    "formula": {
        "expression": "(a / b) / c",
        "decimals": 2,
        "monotonic": {"a": "increasing", "b": "decreasing", "c": "decreasing"},
    },
    "categories": [{"name": "below"}, {"name": "between", "min": 3}, {"name": "above", "min": 5}],
}

VOLUME = {  # score-only, with a second unit for one item
    "id": "toy_volume",
    "name": "Toy volume",
    "citation": "None",
    "items": [
        _num("weight", 1, 200, "kg", units={"lb": {"multiply_by": 0.5}}),  # a toy factor
        _num("pct", 0, 100, "%"),
    ],
    "formula": {
        "expression": "4 * weight * pct",
        "unit": "mL",
        "monotonic": {"weight": "increasing", "pct": "increasing"},
    },
}

MIXED = {  # a number, an ordinal factor, a yes/no term and a floor
    "id": "toy_mixed",
    "name": "Toy mixed",
    "citation": "None",
    "items": [
        _num("base", 0, 10),
        {"id": "size", "label": "size", "type": "ordinal", "kind": "finding",
         "levels": ["small", "large"]},
        {"id": "flag", "label": "flag", "type": "boolean", "kind": "finding"},
    ],
    "formula": {
        "expression": "max(base, 1) * size + 3 * flag",
        "monotonic": {"base": "increasing"},
        "values": {"size": {"small": 1, "large": 2}},
    },
}  # fmt: skip


def broken(spec, change):
    d = copy.deepcopy(spec)
    change(d)
    return d


# --- complete inputs ---------------------------------------------------------------------------


def test_complete_input_gives_the_result_and_its_category():
    # (90 / 0.5) / 30 = 6.0: "above" (5 or more).
    r = evaluate(parse(RATIO), {"a": 90, "b": 0.5, "c": 30})
    assert r["settled"] and r["score"] == 6 and r["category"] == "above"
    assert r["formula"]["expression"] == "(a / b) / c" and r["components"] == []
    # (80 / 0.5) / 40 = 4.0: "between"; (60 / 1.0) / 30 = 2.0: "below".
    assert evaluate(parse(RATIO), {"a": 80, "b": 0.5, "c": 40})["category"] == "between"
    assert evaluate(parse(RATIO), {"a": 60, "b": 1.0, "c": 30})["category"] == "below"


def test_cut_offs_are_inclusive_as_written_and_the_result_is_rounded():
    # (90 / 1.0) / 30 = 3.0 exactly: "between" starts at 3.
    assert evaluate(parse(RATIO), {"a": 90, "b": 1.0, "c": 30})["category"] == "between"
    # (89.9 / 1.0) / 30 = 2.99666..., rounded to 2 decimals 3.0: "between".
    r = evaluate(parse(RATIO), {"a": 89.9, "b": 1.0, "c": 30})
    assert r["score"] == 3 and r["category"] == "between"
    # (89.8 / 1.0) / 30 = 2.99333..., rounded 2.99: "below".
    assert evaluate(parse(RATIO), {"a": 89.8, "b": 1.0, "c": 30})["category"] == "below"


def test_mixed_items_and_functions():
    calc = parse(MIXED)
    # max(4, 1) * 2 + 3 * 0 = 8;  max(0.5, 1) * 1 + 3 * 1 = 4.
    assert evaluate(calc, {"base": 4, "size": "large", "flag": "absent"})["score"] == 8
    assert evaluate(calc, {"base": 0.5, "size": "small", "flag": "present"})["score"] == 4


# --- unknown inputs ----------------------------------------------------------------------------


def test_an_unknown_input_is_bounded_by_its_accepted_range():
    # c anywhere in 5 to 60: (90 / 0.5) / 60 = 3.0 up to (90 / 0.5) / 5 = 36.
    r = evaluate(parse(RATIO), {"a": 90, "b": 0.5})
    assert not r["settled"] and r["score"] is None and r["score_range"] == [3, 36]
    assert r["possible_categories"] == ["above", "between"]  # lower result is higher risk
    assert r["worst_case_category"] == "between"
    (d,) = r["decisive_unknowns"]
    assert d["item"] == "c" and d["known_range"] == [5, 60]
    assert d["outcomes"] == [
        {"if": "5 units", "possible_categories": ["above"]},
        {"if": "60 units", "possible_categories": ["between"]},
    ]


def test_nothing_known_gives_the_whole_range():
    # Lowest: (50 / 1.0) / 60 = 0.8333 -> 0.83. Highest: (100 / 0.2) / 5 = 100.
    r = evaluate(parse(RATIO), {})
    assert r["score_range"] == [0.83, 100]
    assert r["possible_categories"] == ["above", "between", "below"]
    # Knowing b or c alone can rule a category out: b = 0.2 gives at least (50 / 0.2) / 60 =
    # 4.17 (not "below"); c = 5 gives at least (50 / 1.0) / 5 = 10 ("above" only). Knowing a
    # alone cannot: even at a = 100 the result runs from (100 / 1.0) / 60 = 1.67 to 100. It
    # still matters together with the others.
    assert {d["item"] for d in r["decisive_unknowns"]} == {"b", "c"}
    assert r["jointly_relevant_unknowns"] == ["a"] and r["irrelevant_unknowns"] == []


def test_a_range_can_settle_the_category_without_an_exact_result():
    # c at least 40: (90 / 0.5) / 60 = 3.0 up to (90 / 0.5) / 40 = 4.5, all "between".
    r = evaluate(parse(RATIO), {"a": 90, "b": 0.5, "c": {"min": 40}})
    assert r["settled"] and r["category"] == "between"
    assert r["score"] is None and r["score_range"] == [3, 4.5]
    assert r["irrelevant_unknowns"] == ["c"] and r["decisive_unknowns"] == []


def test_score_only_formula():
    calc = parse(VOLUME)
    r = evaluate(calc, {"weight": 70, "pct": 20})  # 4 * 70 * 20 = 5600
    assert r["settled"] and r["score"] == 5600 and r["score_only"] is True
    assert r["category"] is None and r["possible_categories"] == []
    # Weight known only as 60 to 80: 4 * 60 * 20 = 4800 to 4 * 80 * 20 = 6400.
    r = evaluate(calc, {"weight": {"min": 60, "max": 80}, "pct": 20})
    assert not r["settled"] and r["score_range"] == [4800, 6400]
    (d,) = r["decisive_unknowns"]
    assert d["outcomes"] == [
        {"if": "60 kg", "score_range": [4800, 4800]},
        {"if": "80 kg", "score_range": [6400, 6400]},
    ]


def test_units_and_accepted_range_apply_to_formula_inputs():
    calc = parse(VOLUME)
    # 140 lb at the toy factor 0.5 is 70 kg: the same 5600.
    r = evaluate(calc, {"weight": {"value": 140, "unit": "lb"}, "pct": 20})
    assert r["score"] == 5600 and r["converted"]["weight"]["value"] == 70
    with pytest.raises(InputError, match="outside the values this calculator accepts"):
        evaluate(calc, {"weight": 700, "pct": 20})


def test_unknown_discrete_items_are_enumerated():
    calc = parse(MIXED)
    # base 4, flag present, size unknown: 4 * 1 + 3 = 7 or 4 * 2 + 3 = 11.
    r = evaluate(calc, {"base": 4, "flag": "present"})
    assert r["score_range"] == [7, 11]
    (d,) = r["decisive_unknowns"]
    assert d["outcomes"] == [
        {"if": "small", "score_range": [7, 7]},
        {"if": "large", "score_range": [11, 11]},
    ]


def test_an_input_that_cannot_move_the_result_is_irrelevant():
    calc = parse(MIXED)
    # base known only as at most 0.8: max(base, 1) is 1 whatever it is. 1 * 2 + 0 = 2.
    r = evaluate(calc, {"base": {"max": 0.8}, "size": "large", "flag": "absent"})
    assert r["settled"] and r["score"] == 2 and r["irrelevant_unknowns"] == ["base"]


# --- against an independent reference ----------------------------------------------------------


def test_ratio_matches_a_reference():
    def reference(v):
        x = round(v["a"] / v["b"] / v["c"], 2)
        return x, "above" if x >= 5 else "between" if x >= 3 else "below"

    assert_formula_matches_reference(parse(RATIO), reference)


def test_volume_and_mixed_match_references():
    assert_formula_matches_reference(parse(VOLUME), lambda v: (4 * v["weight"] * v["pct"], None))

    def mixed(v):
        base = v["base"] if v["base"] > 1 else 1
        return base * (2 if v["size"] == "large" else 1) + (3 if v["flag"] else 0), None

    assert_formula_matches_reference(parse(MIXED), mixed)


def test_the_reference_check_catches_a_wrong_formula():
    wrong = broken(RATIO, lambda d: d["formula"].update(expression="(a / b) / c + 0.01"))
    with pytest.raises(AssertionError, match="disagree"):
        assert_formula_matches_reference(
            parse(wrong), lambda v: (round(v["a"] / v["b"] / v["c"], 2), "below")
        )
    with pytest.raises(ValueError, match="not a formula calculator"):
        assert_formula_matches_reference(
            parse(
                {
                    "id": "t", "name": "t", "citation": "None",
                    "items": [{"id": "x", "label": "x", "type": "boolean", "kind": "finding"}],
                    "components": [{"id": "x", "rule": "present", "item": "x", "points": 1}],
                    "categories": [{"name": "no"}, {"name": "yes", "min": 1}],
                }
            ),
            lambda v: (0, "no"),
        )  # fmt: skip
    assert assert_matches_reference  # the additive check is a separate function


# --- schema ------------------------------------------------------------------------------------


def test_schema_describes_the_formula():
    s = schema(parse(MIXED))
    assert s["components"] == [] and s["score_only"] is True
    assert s["formula"]["expression"] == "max(base, 1) * size + 3 * flag"
    assert s["formula"]["values"] == {"size": {"small": 1, "large": 2}}
    assert s["formula"]["monotonic"] == {"base": "increasing"}
    assert schema(parse(RATIO))["score_only"] is False


# --- what the loader rejects -------------------------------------------------------------------

MISTAKES = {
    "components and a formula": lambda d: d.update(components=[]),
    "formula that is not a mapping": lambda d: d.update(formula="a / b"),
    "no expression": lambda d: d["formula"].pop("expression"),
    "unknown key": lambda d: d["formula"].update(rounding=2),
    "expression that cannot be read": lambda d: d["formula"].update(expression="(a / b"),
    "a name that is not an item": lambda d: d["formula"].update(expression="(a / b) / c * d"),
    "an item the formula does not use": lambda d: d["formula"].update(expression="a / b"),
    "a function that is not available": lambda d: d["formula"].update(
        expression="abs(a) / b / c"
    ),
    "an attribute or call trick": lambda d: d["formula"].update(
        expression="a.__class__ / b / c"
    ),
    "a comparison": lambda d: d["formula"].update(expression="(a > b) / c"),
    "text in the expression": lambda d: d["formula"].update(expression="a / b / c + 'x'"),
    "numeric item without accepts": lambda d: d["items"][0].pop("accepts"),
    "monotonic missing an item": lambda d: d["formula"]["monotonic"].pop("c"),
    "monotonic with a bad word": lambda d: d["formula"]["monotonic"].update(a="up"),
    "direction declared the wrong way": lambda d: d["formula"]["monotonic"].update(
        c="increasing"
    ),
    "expression that is not monotonic": lambda d: d["formula"].update(
        expression="(a - 75) ** 2 / b / c"
    ),
    "division by zero inside the ranges": lambda d: d["items"][1].update(accepts=[0, 1.0]),
    "decimals that is not a small whole number": lambda d: d["formula"].update(decimals=2.5),
    "values for an item that is not ordinal": lambda d: d["formula"].update(
        values={"a": {"x": 1}}
    ),
    "category on a group": lambda d: d["categories"][1].update(group="g"),
}


@pytest.mark.parametrize("name", MISTAKES)
def test_loader_rejects(name):
    with pytest.raises(SpecError):
        parse(broken(RATIO, MISTAKES[name]))


def test_ordinal_values_must_cover_the_levels():
    with pytest.raises(SpecError, match="each level"):
        parse(broken(MIXED, lambda d: d["formula"]["values"]["size"].pop("large")))
    with pytest.raises(SpecError, match="must be a number"):
        parse(broken(MIXED, lambda d: d["formula"]["values"]["size"].update(large="2")))


def test_the_not_monotonic_message_says_what_to_do():
    with pytest.raises(SpecError, match="not increasing in 'c'"):
        parse(broken(RATIO, MISTAKES["direction declared the wrong way"]))


# --- named parts -------------------------------------------------------------------------------

NAMED = broken(
    RATIO,
    lambda d: d["formula"].update(where={"ratio": "a / b", "per_c": "ratio / c"}, expression="per_c"),
)


def test_named_parts_give_the_same_calculator():
    plain, named = parse(RATIO), parse(NAMED)
    for values in ({"a": 90, "b": 0.5, "c": 30}, {"a": 90, "b": 0.5}, {}):
        a, b = evaluate(plain, values), evaluate(named, values)
        assert (a["score"], a["score_range"], a["possible_categories"]) == (
            b["score"], b["score_range"], b["possible_categories"],
        )  # fmt: skip
    assert schema(named)["formula"]["where"] == {"ratio": "a / b", "per_c": "ratio / c"}
    assert schema(plain)["formula"]["where"] == {}


@pytest.mark.parametrize(
    "where",
    [
        {"a": "b / c"},  # the name of an item
        {"max": "a / b"},  # the name of a function
        {"per_c": "ratio / c", "ratio": "a / b"},  # uses a name defined below it
        {"ratio": "a / b", "spare": "a * 2"},  # defined but never used
        {"ratio": "a / d"},  # uses something that is nothing
        {"ratio": 3},  # not text
        {"my ratio": "a / b"},  # not a usable name
        ["ratio"],  # not a mapping
    ],
)
def test_bad_named_parts_are_refused(where):
    with pytest.raises(SpecError):
        parse(broken(RATIO, lambda d: d["formula"].update(where=where, expression="ratio / c")))


def test_a_named_part_does_not_excuse_an_unused_item():
    with pytest.raises(SpecError, match="not used by the formula"):
        parse(broken(RATIO, lambda d: d["formula"].update(where={"r": "a / b"}, expression="r")))
