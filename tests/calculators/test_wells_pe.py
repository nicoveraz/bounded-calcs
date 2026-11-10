"""Wells criteria for PE (two-tier): independent reference, threshold cases, clinical examples.

Sources: Wells PS et al. Thromb Haemost 2000;83(3):416-420. PMID 10744147; two-tier cut-off
from van Belle A et al. JAMA 2006;295(2):172-179. PMID 16403929.
The reference is transcribed from calc-bounds (wells_pe.py). It is deliberately not derived
from the YAML spec.
"""

import pytest

from bounded_calcs import evaluate, load_builtin
from bounded_calcs.testing import assert_matches_reference

CALC = load_builtin()["wells_pe"]

ZERO = {
    "dvt_signs": "absent",
    "pe_most_likely": "absent",
    "heart_rate": 80,
    "immobilization_or_surgery": "absent",
    "prior_vte": "absent",
    "hemoptysis": "absent",
    "malignancy": "absent",
}


def reference(v):
    score = (
        3.0 * v["dvt_signs"]
        + 3.0 * v["pe_most_likely"]
        + 1.5 * (v["heart_rate"] > 100)
        + 1.5 * v["immobilization_or_surgery"]
        + 1.5 * v["prior_vte"]
        + 1.0 * v["hemoptysis"]
        + 1.0 * v["malignancy"]
    )
    return score, "pe_likely" if score > 4 else "pe_unlikely"


def test_matches_reference():
    assert_matches_reference(CALC, reference)


# --- thresholds, from the source's own numbers ------------------------------------------------


@pytest.mark.parametrize("heart_rate,points", [(100, 0), (101, 1.5)])
def test_heart_rate_above_100(heart_rate, points):
    assert evaluate(CALC, ZERO | {"heart_rate": heart_rate})["score"] == points


def test_item_points():
    def score(item):
        return evaluate(CALC, ZERO | {item: "present"})["score"]

    assert score("dvt_signs") == 3
    assert score("pe_most_likely") == 3
    assert score("immobilization_or_surgery") == 1.5
    assert score("prior_vte") == 1.5
    assert score("hemoptysis") == 1
    assert score("malignancy") == 1


def test_cut_off_is_above_four():
    four = ZERO | {"dvt_signs": "present", "hemoptysis": "present"}
    r = evaluate(CALC, four)
    assert (r["score"], r["category"]) == (4, "pe_unlikely")
    r = evaluate(CALC, ZERO | {"dvt_signs": "present", "heart_rate": 110})
    assert (r["score"], r["category"]) == (4.5, "pe_likely")


# --- unknown is not normal ---------------------------------------------------------------------


def test_unmentioned_is_not_normal():
    """A note silent on DVT signs and on the clinician's judgment cannot be called 'PE
    unlikely' just because nothing alarming is written down."""
    note = {"heart_rate": 110, "hemoptysis": "absent", "malignancy": "absent"}
    r = evaluate(CALC, note)
    assert not r["settled"]
    assert r["possible_categories"] == ["pe_unlikely", "pe_likely"]
    assert r["worst_case_category"] == "pe_likely"
    assert r["score_range"] == [1.5, 10.5]
    assert [d["item"] for d in r["decisive_unknowns"]] == ["dvt_signs", "pe_most_likely"]
    assert r["jointly_relevant_unknowns"] == ["immobilization_or_surgery", "prior_vte"]
    assert r["judgment_items_pending"] == ["pe_most_likely"]
    # Filling the silence with "absent" (the common convention) claims a settled answer.
    filled = ZERO | note
    assert evaluate(CALC, filled)["category"] == "pe_unlikely"


def test_settled_while_items_are_still_unknown():
    # Six points already: nothing else can bring the score to four or below.
    r = evaluate(CALC, {"dvt_signs": "present", "pe_most_likely": "present"})
    assert r["settled"] and r["category"] == "pe_likely"
    assert r["decisive_unknowns"] == [] and len(r["irrelevant_unknowns"]) == 5


def test_decisive_unknowns_say_what_each_answer_would_give():
    known = {k: v for k, v in ZERO.items() if k not in ("dvt_signs", "pe_most_likely")}
    r = evaluate(CALC, known)
    first = r["decisive_unknowns"][0]
    assert first["item"] == "dvt_signs"  # a finding is asked before a judgment
    outcomes = {o["if"]: o["possible_categories"] for o in first["outcomes"]}
    assert outcomes == {"present": ["pe_unlikely", "pe_likely"], "absent": ["pe_unlikely"]}
