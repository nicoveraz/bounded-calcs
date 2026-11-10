import itertools
import random

import pytest

from bounded_calcs import InputError, evaluate, load_builtin, schema
from bounded_calcs.engine import _normalize, _reachable_scores

CALCS = load_builtin()
HEART = CALCS["heart"]
WELLS = CALCS["wells_pe"]

# One representative value inside each numeric band, used to enumerate completions.
NUMERIC_REPS = {"age": [30, 50, 70], "heart_rate": [80, 120]}


def domain(calc, iid):
    item = calc.items[iid]
    if item.type == "boolean":
        return ["present", "absent"]
    if item.type == "ordinal":
        return list(item.levels)
    return NUMERIC_REPS[iid]


def complete_score(calc, full):
    scores = _reachable_scores(calc, _normalize(calc, full).state)
    assert len(scores) == 1
    return next(iter(scores))


def brute_force(calc, partial):
    unknown = [i for i in calc.items if i not in partial]
    scores = set()
    for combo in itertools.product(*(domain(calc, i) for i in unknown)):
        scores.add(complete_score(calc, {**partial, **dict(zip(unknown, combo))}))
    return scores


def random_partial(calc, rng, p_known):
    return {i: rng.choice(domain(calc, i)) for i in calc.items if rng.random() < p_known}


# --- exactness against brute force -------------------------------------------------------


@pytest.mark.parametrize("calc", [HEART, WELLS], ids=lambda c: c.id)
def test_bounds_match_brute_force(calc):
    rng = random.Random(0)
    for _ in range(150):
        partial = random_partial(calc, rng, p_known=rng.choice([0.3, 0.6, 0.85]))
        truth = brute_force(calc, partial)
        r = evaluate(calc, partial)
        assert r["score_range"] == [min(truth), max(truth)]
        assert set(r["possible_categories"]) == {calc.category(s).name for s in truth}
        assert r["settled"] == (len(r["possible_categories"]) == 1)


@pytest.mark.parametrize("calc", [HEART, WELLS], ids=lambda c: c.id)
def test_unknown_classification_matches_brute_force(calc):
    rng = random.Random(1)
    for _ in range(60):
        partial = random_partial(calc, rng, p_known=0.6)
        r = evaluate(calc, partial)
        cats = set(r["possible_categories"])
        decisive = {d["item"] for d in r["decisive_unknowns"]}
        for iid in (i for i in calc.items if i not in partial):
            narrows = any(
                len({calc.category(s).name for s in brute_force(calc, {**partial, iid: v})})
                < len(cats)
                for v in domain(calc, iid)
            )
            assert (iid in decisive) == (narrows and not r["settled"]), iid


def test_unsettled_always_offers_something_to_ask():
    rng = random.Random(2)
    for calc in (HEART, WELLS):
        for _ in range(200):
            r = evaluate(calc, random_partial(calc, rng, p_known=rng.random()))
            if not r["settled"]:
                assert r["decisive_unknowns"] or r["jointly_relevant_unknowns"]


# --- hand-checked values ------------------------------------------------------------------


def test_heart_complete_case():
    r = evaluate(
        HEART,
        {
            "heart_history": "moderately_suspicious",  # 1
            "heart_ecg": "nonspecific_repolarization",  # 1
            "age": 67,  # 2
            "hypertension": "present",
            "hypercholesterolemia": "absent",
            "diabetes": "present",
            "obesity": "absent",
            "smoking": "absent",
            "family_history_cad": "absent",
            "atherosclerotic_disease": "absent",  # 2 factors -> 1
            "heart_troponin": "le_normal",  # 0
        },
    )
    assert r["settled"] and r["score"] == 5 and r["category"] == "moderate"
    assert r["decisive_unknowns"] == [] and r["irrelevant_unknowns"] == []


@pytest.mark.parametrize("age,points", [(44, 0), (45, 1), (64, 1), (65, 2)])
def test_heart_age_boundaries(age, points):
    base = {i: "absent" for i in HEART.items if HEART.items[i].type == "boolean"}
    base |= {"heart_history": "slightly_suspicious", "heart_ecg": "normal",
             "heart_troponin": "le_normal", "age": age}
    assert evaluate(HEART, base)["score"] == points


def test_heart_risk_factor_override_and_count():
    base = {"heart_history": "slightly_suspicious", "heart_ecg": "normal",
            "heart_troponin": "le_normal", "age": 30}
    rf = ["hypertension", "hypercholesterolemia", "diabetes", "obesity", "smoking",
          "family_history_cad"]
    none = {i: "absent" for i in rf} | {"atherosclerotic_disease": "absent"}
    assert evaluate(HEART, base | none)["score"] == 0
    assert evaluate(HEART, base | none | {"diabetes": "present"})["score"] == 1
    three = {"diabetes": "present", "smoking": "present", "obesity": "present"}
    assert evaluate(HEART, base | none | three)["score"] == 2
    athero = none | {"atherosclerotic_disease": "present"}
    assert evaluate(HEART, base | athero)["score"] == 2
    # Override known present: unknown risk factors no longer matter.
    r = evaluate(HEART, base | {"atherosclerotic_disease": "present"})
    assert r["settled"] and r["score"] == 2


@pytest.mark.parametrize("hr,expected", [(100, "pe_unlikely"), (101, "pe_likely")])
def test_wells_heart_rate_boundary(hr, expected):
    # dvt_signs 3 + heart rate 1.5 -> 4.5 likely; at 100/min -> 3 unlikely
    r = evaluate(WELLS, {"dvt_signs": "present", "pe_most_likely": "absent", "heart_rate": hr,
                         "immobilization_or_surgery": "absent", "prior_vte": "absent",
                         "hemoptysis": "absent", "malignancy": "absent"})
    assert r["category"] == expected


def test_wells_score_four_is_unlikely():
    r = evaluate(WELLS, {"dvt_signs": "present", "pe_most_likely": "absent", "heart_rate": 80,
                         "immobilization_or_surgery": "absent", "prior_vte": "absent",
                         "hemoptysis": "present", "malignancy": "absent"})
    assert r["score"] == 4 and r["category"] == "pe_unlikely"


def test_unmentioned_is_not_normal():
    """The core claim: a note silent on DVT signs and the clinician's judgment cannot be
    called 'PE unlikely' just because nothing alarming is written down."""
    note = {"heart_rate": 110, "hemoptysis": "absent", "malignancy": "absent"}
    r = evaluate(WELLS, note)
    assert not r["settled"]
    assert r["possible_categories"] == ["pe_unlikely", "pe_likely"]
    assert r["worst_case_category"] == "pe_likely"
    assert "pe_most_likely" in r["judgment_items_pending"]
    # Treating the silence as absent (the common convention) would claim a settled answer.
    filled = note | {"dvt_signs": "absent", "pe_most_likely": "absent",
                     "immobilization_or_surgery": "absent", "prior_vte": "absent"}
    assert evaluate(WELLS, filled)["category"] == "pe_unlikely"


def test_settled_with_unknowns_left():
    # Score already > 4 regardless of the rest.
    r = evaluate(WELLS, {"dvt_signs": "present", "pe_most_likely": "present"})
    assert r["settled"] and r["category"] == "pe_likely"
    assert r["decisive_unknowns"] == [] and len(r["irrelevant_unknowns"]) == 5


def test_decisive_outcomes_listed():
    r = evaluate(WELLS, {"heart_rate": 80, "immobilization_or_surgery": "absent",
                         "prior_vte": "absent", "hemoptysis": "absent", "malignancy": "absent"})
    # 0 known; dvt_signs (3) and pe_most_likely (3) together could reach 6.
    assert not r["settled"]
    assert {d["item"] for d in r["decisive_unknowns"]} == {"dvt_signs", "pe_most_likely"}
    first = r["decisive_unknowns"][0]
    assert first["item"] == "dvt_signs"  # data before judgment when otherwise equal
    assert {o["if"]: o["possible_categories"] for o in first["outcomes"]}["absent"] == ["pe_unlikely"]


# --- input handling ------------------------------------------------------------------------


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
        {"heart_rate": "fast"},
        {"heart_rate": True},
    ],
)
def test_bad_inputs_rejected(inputs):
    with pytest.raises(InputError):
        evaluate(WELLS, inputs)


def test_bad_level_rejected():
    with pytest.raises(InputError):
        evaluate(HEART, {"heart_ecg": "abnormal"})


def test_schema_shape():
    s = schema(HEART)
    assert s["id"] == "heart" and "PMID 18665203" in s["citation"]
    kinds = {i["id"]: i["kind"] for i in s["items"]}
    assert kinds["heart_history"] == "judgment"
    assert [c["name"] for c in s["categories"]] == ["low", "moderate", "high"]
