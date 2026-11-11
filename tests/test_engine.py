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
    assert with_word.pop("normal_assumed") == {
        "heart_rate": {"range": [60, 99], "unit": "/min", "source": "default"}
    }
    assert with_word == with_number
    assert "normal_assumed" not in with_number


# --- ranges: "normal", explicit bounds, site ranges -----------------------------------------

CURB = CALCS["curb65"]
# CURB-65 with everything known except urea: age 70 (1 point), the rest 0. Urea > 7 mmol/L
# adds 1 point and moves the patient from low (1) to moderate (2).
CURB_BUT_UREA = {"confusion": "absent", "resp_rate": 18, "sbp": 120, "dbp": 80, "age": 70}


@pytest.mark.parametrize(
    "urea,settled,category",
    [
        ({"min": 5, "max": 7}, True, "low"),  # never above 7
        ({"min": 7.5}, True, "moderate"),  # always above 7
        ({"max": 6}, True, "low"),
        ({"min": 5, "max": 9}, False, None),  # either side of 7
    ],
)
def test_range_input(urea, settled, category):
    r = evaluate(CURB, CURB_BUT_UREA | {"urea": urea})
    assert (r["settled"], r["category"]) == (settled, category)
    if not settled:
        (d,) = r["decisive_unknowns"]
        assert d["item"] == "urea" and d["known_range"] == [urea["min"], urea["max"]]


def test_open_range_bound_is_reported_as_none():
    r = evaluate(CURB, CURB_BUT_UREA | {"urea": {"max": 9}})
    urea = next(d for d in r["decisive_unknowns"] if d["item"] == "urea")
    assert urea["known_range"] == [None, 9]


@pytest.mark.parametrize(
    "bad",
    [{}, {"min": 9, "max": 5}, {"min": "5"}, {"min": True}, {"low": 5}, {"min": float("nan")}],
)
def test_bad_ranges_are_rejected(bad):
    with pytest.raises(InputError):
        evaluate(CURB, {"urea": bad})


def test_site_range_replaces_the_default():
    # Default urea range 2.5 to 8 crosses 7, so "urea normal" leaves the point open.
    r = evaluate(CURB, CURB_BUT_UREA | {"urea": "normal"})
    assert not r["settled"] and [d["item"] for d in r["decisive_unknowns"]] == ["urea"]
    assert r["normal_assumed"]["urea"]["source"] == "default"
    # A laboratory whose upper limit is 7: "normal" settles it (score 1, low).
    site = {"urea": [2.5, 7.0]}
    r = evaluate(CURB, CURB_BUT_UREA | {"urea": "normal"}, normal_ranges=site)
    assert r["settled"] and (r["score"], r["category"]) == (1, "low")
    assert r["normal_assumed"] == {"urea": {"range": [2.5, 7], "unit": "mmol/L", "source": "site"}}
    # Site ranges for items a calculator does not have are ignored.
    assert evaluate(WELLS, {}, normal_ranges=site) == evaluate(WELLS, {})


def test_site_range_gives_normal_to_an_item_without_a_default():
    r = evaluate(HEART, {"age": "normal"}, normal_ranges={"age": [20, 40]})
    assert r["normal_assumed"]["age"]["source"] == "site"


@pytest.mark.parametrize("bad", [[7], [8, 2], ["2", "7"], "2-7"])
def test_bad_site_ranges_are_rejected(bad):
    with pytest.raises(InputError):
        evaluate(CURB, {}, normal_ranges={"urea": bad})


def test_site_ranges_are_checked_against_all_calculators():
    from bounded_calcs import check_site_ranges

    check_site_ranges(CALCS, {"urea": [2.5, 7], "heart_rate": [50, 100]})
    with pytest.raises(InputError, match="no calculator"):
        check_site_ranges(CALCS, {"ureaa": [2.5, 7]})
    with pytest.raises(InputError, match="no calculator"):
        check_site_ranges(CALCS, {"hemoptysis": [0, 1]})  # boolean, not numeric


def test_schema_lists_the_normal_range():
    items = {i["id"]: i for i in schema(WELLS)["items"]}
    assert items["heart_rate"]["normal"] == [60, 99]
    assert items["heart_rate"]["normal_source"] == "default"
    site = {i["id"]: i for i in schema(CURB, normal_ranges={"urea": [2.5, 7]})["items"]}
    assert (site["urea"]["normal"], site["urea"]["normal_source"]) == ([2.5, 7], "site")
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


# --- component groups ----------------------------------------------------------------------


def test_groups_cut_off_that_depends_on_an_item():
    # A score with a point for female sex and a treatment cut-off of 2 for men and 3 for
    # women: the cut-off is on the points outside the sex component.
    calc = parse(
        {
            "id": "toy_sex",
            "name": "Toy with a sex-dependent cut-off",
            "citation": "None",
            "items": [
                {"id": "sex", "label": "Sex", "type": "ordinal", "kind": "finding",
                 "levels": ["male", "female"]},
                {"id": "age", "label": "Age", "type": "numeric", "kind": "measurement",
                 "unit": "years"},
                {"id": "htn", "label": "Hypertension", "type": "boolean", "kind": "finding"},
                {"id": "dm", "label": "Diabetes", "type": "boolean", "kind": "finding"},
            ],
            "components": [
                {"id": "sex", "rule": "levels", "item": "sex", "points": {"male": 0, "female": 1}},
                {"id": "age", "rule": "bands", "item": "age", "group": "other",
                 "bands": [{"gte": 75, "points": 2}, {"gte": 65, "points": 1}, {"points": 0}]},
                {"id": "htn", "rule": "present", "item": "htn", "points": 1, "group": "other"},
                {"id": "dm", "rule": "present", "item": "dm", "points": 1, "group": "other"},
            ],
            "categories": [
                {"name": "no_treatment"},
                {"name": "consider", "group": "other", "min": 1},
                {"name": "treat", "group": "other", "min": 2},
            ],
        }
    )  # fmt: skip

    def reference(v):
        female = v["sex"] == "female"
        score = female + (2 if v["age"] >= 75 else 1 if v["age"] >= 65 else 0) + v["htn"] + v["dm"]
        if score >= (3 if female else 2):
            return score, "treat"
        return score, "consider" if score >= (2 if female else 1) else "no_treatment"

    assert_matches_reference(calc, reference)
    # A woman of 70 with nothing else: score 2, but the cut-off for women is 3.
    r = evaluate(calc, {"sex": "female", "age": 70, "htn": "absent", "dm": "absent"})
    assert (r["score"], r["category"]) == (2, "consider")
    # Sex unknown: the score is open (1 or 2) but the category is not, so sex is not asked.
    r = evaluate(calc, {"age": 70, "htn": "absent", "dm": "absent"})
    assert r["settled"] and r["category"] == "consider" and r["score_range"] == [1, 2]
    assert r["irrelevant_unknowns"] == ["sex"]


def test_groups_tiers():
    # "Image if any high-risk criterion; otherwise observe if any medium-risk one."
    calc = parse(
        {
            "id": "toy_tiers",
            "name": "Toy tiers",
            "citation": "None",
            "items": [
                {"id": i, "label": i, "type": "boolean", "kind": "finding"}
                for i in ("h1", "h2", "m1", "m2", "m3")
            ],
            "components": [
                {"id": i, "rule": "present", "item": i, "points": 1,
                 "group": "high" if i.startswith("h") else "medium"}
                for i in ("h1", "h2", "m1", "m2", "m3")
            ],
            "categories": [
                {"name": "none"},
                {"name": "observe", "group": "medium", "min": 1},
                {"name": "image", "group": "high", "min": 1},
            ],
        }
    )  # fmt: skip

    def reference(v):
        score = sum(v.values())
        if v["h1"] or v["h2"]:
            return score, "image"
        return score, "observe" if v["m1"] or v["m2"] or v["m3"] else "none"

    assert_matches_reference(calc, reference)
    # One medium criterion present: the other medium ones no longer matter, the high ones do.
    r = evaluate(calc, {"m1": "present"})
    assert r["possible_categories"] == ["observe", "image"]
    assert {d["item"] for d in r["decisive_unknowns"]} == {"h1", "h2"}
    assert set(r["irrelevant_unknowns"]) == {"m2", "m3"}
    # Three medium criteria score more than one high-risk one and still only "observe".
    medium = {"h1": "absent", "h2": "absent", "m1": "present", "m2": "present", "m3": "present"}
    assert evaluate(calc, medium)["category"] == "observe"
    assert schema(calc)["components"][0]["group"] == "high"
    assert schema(calc)["categories"][2]["when"] == "points in group 'high' >= 1"


def test_groups_items_that_matter_only_together():
    # "High if two or more major criteria": no single answer rules a category out, but each
    # major criterion can change it; the minor one adds points and never matters.
    calc = parse(
        {
            "id": "toy_two_major",
            "name": "Toy two major criteria",
            "citation": "None",
            "items": [
                {"id": i, "label": i, "type": "boolean", "kind": "finding"}
                for i in ("a", "b", "c", "minor")
            ],
            "components": [
                {"id": "a", "rule": "present", "item": "a", "points": 1, "group": "major"},
                {"id": "b", "rule": "present", "item": "b", "points": 1, "group": "major"},
                {"id": "c", "rule": "present", "item": "c", "points": 1, "group": "major"},
                {"id": "minor", "rule": "present", "item": "minor", "points": 3},
            ],
            "categories": [{"name": "low"}, {"name": "high", "group": "major", "min": 2}],
        }
    )

    def reference(v):
        return v["a"] + v["b"] + v["c"] + 3 * v["minor"], (
            "high" if v["a"] + v["b"] + v["c"] >= 2 else "low"
        )

    assert_matches_reference(calc, reference)
    r = evaluate(calc, {})
    assert r["decisive_unknowns"] == []
    assert set(r["jointly_relevant_unknowns"]) == {"a", "b", "c"}
    assert r["irrelevant_unknowns"] == ["minor"]


# --- accepted ranges -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "inputs",
    [
        {"spo2": 0.97},  # a fraction instead of a percentage
        {"age": 500},
        {"age": 16},  # an adult score
        {"heart_rate": {"min": 300}},  # a bound outside the range
        {"spo2": {"min": 90, "max": 101}},
    ],
)
def test_values_outside_the_accepted_range_are_errors_not_scores(inputs):
    with pytest.raises(InputError, match="outside the values this calculator accepts"):
        evaluate(CALCS["perc"], inputs)


def test_the_ends_of_the_accepted_range_are_accepted():
    perc = CALCS["perc"]
    assert perc.items["age"].accepts == (18, 110)
    evaluate(perc, {"age": 18, "spo2": 100, "heart_rate": 250})
    evaluate(perc, {"age": 110, "spo2": 50, "heart_rate": {"min": 20, "max": 250}})
    evaluate(perc, {"heart_rate": {"min": 100}})  # an open bound stays open


def test_accepted_range_is_per_calculator_and_in_the_schema():
    # The same item can be accepted over different ranges: a child's age in a child's score.
    assert CALCS["mcisaac"].items["age"].accepts is None
    evaluate(CALCS["mcisaac"], {"age": 8})
    items = {i["id"]: i for i in schema(CALCS["curb65"])["items"]}
    assert items["urea"]["accepts"] == [1, 60]


def test_site_normal_range_must_be_inside_the_accepted_range():
    with pytest.raises(InputError, match="outside what 'curb65' accepts"):
        evaluate(CURB, {"urea": "normal"}, normal_ranges={"urea": [2.5, 70]})


# --- units: the engine converts declared units and refuses the rest ----------------------------

_CURB_REST = {"confusion": "absent", "resp_rate": 18, "sbp": 120, "dbp": 80, "age": 70}


def test_a_declared_unit_is_converted_to_the_item_unit():
    # BUN 28.014 mg/dL / 2.8014 = 10 mmol/L of urea; urea 60.06 mg/dL / 6.006 = 10 mmol/L.
    plain = evaluate(CURB, _CURB_REST | {"urea": 10})
    for given in ({"value": 28.014, "unit": "bun_mg/dL"}, {"value": 60.06, "unit": "urea_mg/dL"}):
        r = evaluate(CURB, _CURB_REST | {"urea": given})
        assert (r["score"], r["category"]) == (plain["score"], plain["category"])
        assert r["converted"] == {"urea": {"given": given, "value": 10.0, "unit": "mmol/L"}}
    assert "converted" not in plain or not plain["converted"]


def test_conversion_decides_the_threshold():
    # CURB-65 scores urea > 7 mmol/L. BUN 19 mg/dL = 6.78 mmol/L (no point); BUN 20 mg/dL =
    # 7.14 mmol/L (one point). Read as mmol/L, both numbers would score.
    below = evaluate(CURB, _CURB_REST | {"urea": {"value": 19, "unit": "bun_mg/dL"}})
    above = evaluate(CURB, _CURB_REST | {"urea": {"value": 20, "unit": "bun_mg/dL"}})
    assert (below["score"], above["score"]) == (1, 2)  # age 70 gives the other point


def test_the_item_unit_and_letter_case_are_taken():
    r = evaluate(CURB, _CURB_REST | {"urea": {"value": 10, "unit": "MMOL/L"}})
    assert r["score"] == 2 and not r.get("converted")
    r = evaluate(CURB, _CURB_REST | {"urea": {"value": 28.014, "unit": "BUN_mg/dl"}})
    assert r["score"] == 2


def test_bounds_are_converted_too():
    # Urea over 60.06 mg/dL is over 10 mmol/L: above the threshold whatever the value.
    r = evaluate(CURB, _CURB_REST | {"urea": {"min": 60.06, "unit": "urea_mg/dL"}})
    assert r["settled"] and r["score"] == 2
    assert r["converted"]["urea"]["range"][0] == pytest.approx(10.0)


@pytest.mark.parametrize(
    "given",
    [
        {"value": 25, "unit": "mg/dL"},  # which analyte? BUN and urea differ by a factor of 2.1
        {"value": 25, "unit": "g/L"},
        {"value": 25, "unit": 3},
        {"value": 25, "unit": None},
    ],
)
def test_an_undeclared_unit_is_an_error_never_a_guess(given):
    with pytest.raises(InputError, match="is not one this item takes"):
        evaluate(CURB, _CURB_REST | {"urea": given})


def test_a_unit_on_an_item_without_other_units_must_be_its_own():
    evaluate(CURB, {"sbp": {"value": 120, "unit": "mmHg"}})
    with pytest.raises(InputError, match="is not one this item takes"):
        evaluate(CURB, {"sbp": {"value": 16, "unit": "kPa"}})


def test_the_accepted_range_applies_after_conversion():
    # BUN 150 mg/dL = 53.5 mmol/L: inside 1 to 60. As a bare number 150 is refused, and so is
    # a BUN of 400 mg/dL (142.8 mmol/L).
    evaluate(CURB, {"urea": {"value": 150, "unit": "bun_mg/dL"}})
    for given in (150, {"value": 400, "unit": "bun_mg/dL"}):
        with pytest.raises(InputError, match="outside the values this calculator accepts"):
            evaluate(CURB, {"urea": given})


@pytest.mark.parametrize(
    "given",
    [
        {"value": "normal", "unit": "bun_mg/dL"},
        {"value": 25, "min": 20, "unit": "bun_mg/dL"},
        {"unit": "bun_mg/dL"},
        {"value": True, "unit": "bun_mg/dL"},
    ],
)
def test_malformed_values_with_a_unit_are_errors(given):
    with pytest.raises(InputError):
        evaluate(CURB, {"urea": given})


def test_other_units_are_in_the_schema():
    s = schema(CURB)
    items = {i["id"]: i for i in s["items"]}
    assert items["urea"]["other_units"] == ["bun_mg/dL", "urea_mg/dL"]
    assert "other_units" not in items["sbp"]
    assert "other_units" in s["input_rules"]
