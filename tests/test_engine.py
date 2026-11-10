"""Engine behaviour that is not specific to one calculator: every rule type against an inline
reference, input handling, and the shape of the output."""

import random

import pytest

from bounded_calcs import InputError, evaluate, load_builtin, parse, schema
from bounded_calcs.testing import assert_matches_reference, item_values

CALCS = load_builtin()
WELLS = CALCS["wells_pe"]
HEART = CALCS["heart"]


def item(iid, type_, kind="finding", **more):
    return {"id": iid, "label": iid, "type": type_, "kind": kind, **more}


# --- rule types the built-in calculators do not all exercise -----------------------------------


def test_negative_points_absent_rule_and_strict_cut_off():
    calc = parse(
        {
            "id": "toy_negative",
            "name": "Toy",
            "citation": "None",
            "items": [
                item("a", "boolean"),
                item("b", "boolean"),
                item("alt", "boolean", "judgment", question="Is an alternative as likely?"),
                item("temp", "numeric", "measurement", unit="C"),
                item("cough", "boolean"),
            ],
            "components": [
                {"id": "a", "rule": "present", "item": "a", "points": 1},
                {"id": "b", "rule": "present", "item": "b", "points": 1.5},
                {"id": "alt", "rule": "present", "item": "alt", "points": -2},
                {"id": "no_cough", "rule": "absent", "item": "cough", "points": 1},
                {
                    "id": "temp",
                    "rule": "bands",
                    "item": "temp",
                    "bands": [{"gt": 38, "points": 1}, {"lt": 35, "points": -1}, {"points": 0}],
                },
            ],
            "categories": [
                {"name": "low"},
                {"name": "mid", "gt": 0},
                {"name": "high", "min": 2.5},
            ],
        }
    )

    def reference(v):
        s = v["a"] + 1.5 * v["b"] - 2 * v["alt"] + (not v["cough"])
        s += 1 if v["temp"] > 38 else -1 if v["temp"] < 35 else 0
        return s, "high" if s >= 2.5 else "mid" if s > 0 else "low"

    assert_matches_reference(calc, reference)
    r = evaluate(calc, {})
    assert r["score_range"] == [-3, 4.5]
    # Absence earns the point; presence does not.
    full = {"a": "absent", "b": "absent", "alt": "absent", "temp": 37}
    assert evaluate(calc, full | {"cough": "absent"})["score"] == 1
    assert evaluate(calc, full | {"cough": "present"})["score"] == 0
    assert r["possible_categories"] == ["low", "mid", "high"]


def test_count_levels_any_of_and_lower_is_higher_risk():
    calc = parse(
        {
            "id": "toy_reverse",
            "name": "Toy",
            "citation": "None",
            "higher_is_higher_risk": False,
            "items": [
                item("x", "boolean"),
                item("y", "boolean"),
                item("z", "boolean"),
                item("sex", "ordinal", levels=["male", "female"]),
                item("flag", "boolean"),
                item("sat", "numeric", "measurement", unit="%"),
            ],
            "components": [
                {
                    "id": "n",
                    "rule": "count",
                    "items": ["x", "y", "z"],
                    "points": [{"gte": 2, "points": 2}, {"gte": 1, "points": 1}, {"points": 0}],
                },
                {"id": "sex", "rule": "levels", "item": "sex", "points": {"male": 0, "female": 1}},
                {
                    "id": "either",
                    "rule": "any_of",
                    "conditions": [{"item": "flag"}, {"item": "sat", "gte": 95}],
                    "points": 2,
                },
            ],
            "categories": [{"name": "poor"}, {"name": "fair", "min": 2}, {"name": "good", "min": 4}],
        }
    )

    def reference(v):
        n = v["x"] + v["y"] + v["z"]
        s = (2 if n >= 2 else n) + (v["sex"] == "female") + 2 * (v["flag"] or v["sat"] >= 95)
        return s, "good" if s >= 4 else "fair" if s >= 2 else "poor"

    assert_matches_reference(calc, reference)
    # Lower score = higher risk: the worst case is the lowest category.
    r = evaluate(calc, {})
    assert r["possible_categories"] == ["good", "fair", "poor"]
    assert r["worst_case_category"] == "poor"


# --- properties over every built-in calculator -------------------------------------------------


@pytest.mark.parametrize("calc", list(CALCS.values()), ids=lambda c: c.id)
def test_unsettled_results_always_offer_something_to_ask(calc):
    rng = random.Random(2)
    for _ in range(200):
        p_known = rng.random()
        known = {
            i: rng.choice(item_values(calc, i)) for i in calc.items if rng.random() < p_known
        }
        r = evaluate(calc, known)
        assert r["settled"] == (len(r["possible_categories"]) == 1)
        if r["settled"]:
            assert r["decisive_unknowns"] == [] and r["jointly_relevant_unknowns"] == []
            assert r["category"] == r["possible_categories"][0]
        else:
            assert r["category"] is None
            assert r["decisive_unknowns"] or r["jointly_relevant_unknowns"]


@pytest.mark.parametrize("calc", list(CALCS.values()), ids=lambda c: c.id)
def test_nothing_known_means_nothing_assumed(calc):
    r = evaluate(calc, {})
    assert not r["settled"]
    assert r["possible_categories"] == calc.by_risk({c.name for c in calc.categories})


# --- input handling ----------------------------------------------------------------------------


@pytest.mark.parametrize("value", [None, "unknown", "not_mentioned", "Unknown"])
def test_unknown_spellings(value):
    assert evaluate(WELLS, {"hemoptysis": value}) == evaluate(WELLS, {})


def test_boolean_spellings():
    assert evaluate(WELLS, {"hemoptysis": True}) == evaluate(WELLS, {"hemoptysis": "present"})
    assert evaluate(WELLS, {"hemoptysis": "no"}) == evaluate(WELLS, {"hemoptysis": "absent"})


@pytest.mark.parametrize(
    "inputs",
    [
        {"bogus": "present"},
        {"hemoptysis": "maybe"},
        {"hemoptysis": "normal"},
        {"heart_rate": "fast"},
        {"heart_rate": True},
    ],
)
def test_bad_inputs_are_rejected_not_guessed(inputs):
    with pytest.raises(InputError):
        evaluate(WELLS, inputs)


def test_normal_is_rejected_for_an_item_without_a_normal_range():
    with pytest.raises(InputError, match="no normal range"):
        evaluate(HEART, {"age": "normal"})


@pytest.mark.parametrize("word", ["normal", "Normal", " NORMAL "])
def test_normal_means_a_number_inside_the_declared_range(word):
    # Wells: heart rate > 100 scores 1.5; the declared normal range is 60 to 99.
    with_word = evaluate(WELLS, {"heart_rate": word, "dvt_signs": "present"})
    with_number = evaluate(WELLS, {"heart_rate": 80, "dvt_signs": "present"})
    assert with_word.pop("normal_assumed") == {"heart_rate": {"range": [60, 99], "unit": "/min"}}
    assert with_word == with_number
    assert "normal_assumed" not in with_number


def test_schema_lists_the_normal_range():
    items = {i["id"]: i for i in schema(WELLS)["items"]}
    assert items["heart_rate"]["normal"] == [60, 99]
    assert "'normal'" in items["heart_rate"]["values"]
    assert "normal" not in {i["id"]: i for i in schema(HEART)["items"]}["age"]


def test_bad_level_rejected():
    with pytest.raises(InputError):
        evaluate(HEART, {"heart_ecg": "abnormal"})


# --- output shape (a public API: clients and LLMs depend on these names) -----------------------


def test_result_fields():
    r = evaluate(WELLS, {"heart_rate": 110})
    assert set(r) == {
        "calculator",
        "calculator_version",
        "settled",
        "category",
        "possible_categories",
        "worst_case_category",
        "score",
        "score_range",
        "decisive_unknowns",
        "jointly_relevant_unknowns",
        "irrelevant_unknowns",
        "components",
        "note",
        "judgment_items_pending",
        "judgment_note",
    }
    assert set(r["decisive_unknowns"][0]) == {
        "item",
        "label",
        "kind",
        "question",
        "settles_decision_in",
        "outcomes",
    }


def test_schema_shape():
    s = schema(HEART)
    assert s["id"] == "heart" and "PMID 18665203" in s["citation"]
    kinds = {i["id"]: i["kind"] for i in s["items"]}
    assert kinds["heart_history"] == "judgment"
    assert [c["name"] for c in s["categories"]] == ["low", "moderate", "high"]
    assert "normal" in s["input_rules"]


def test_count_component_never_leaves_an_unsettled_result_without_questions():
    # Every pattern of present / absent / unknown risk factors in HEART, combined with every
    # total the other components can add, must offer something to ask whenever the result is
    # not settled. (0.1.0 could return an unsettled result with nothing to ask.)
    calc = HEART
    factors = ["hypertension", "hypercholesterolemia", "diabetes", "obesity", "smoking",
               "family_history_cad", "atherosclerotic_disease"]
    rest_settings = [  # history, ECG, troponin, age: totals 0 to 8
        {"heart_history": h, "heart_ecg": e, "heart_troponin": t, "age": a}
        for h in ("slightly_suspicious", "highly_suspicious")
        for e in ("normal", "nonspecific_repolarization", "significant_st_deviation")
        for t in ("le_normal", "gt_3x_normal")
        for a in (30, 50, 70)
    ]
    import itertools

    checked = 0
    for states in itertools.product(("present", "absent", None), repeat=len(factors)):
        pattern = {f: s for f, s in zip(factors, states) if s is not None}
        for rest in rest_settings:
            r = evaluate(calc, rest | pattern)
            if not r["settled"]:
                assert r["decisive_unknowns"] or r["jointly_relevant_unknowns"], rest | pattern
            checked += 1
    assert checked == 3 ** 7 * 36
