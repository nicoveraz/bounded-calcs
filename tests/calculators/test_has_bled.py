"""HAS-BLED: independent reference, thresholds, clinical examples.

Source: Pisters R et al. Chest 2010;138(5):1093-1100, PMID 20299623, methods and table 2 [P].
The reference is written from table 2: one point each for hypertension, abnormal renal
function, abnormal liver function, stroke, bleeding, labile INRs, elderly (over 65 years),
drugs, alcohol; and from the 2010 ESC guideline for the cut-off (a score of 3 or more is high
risk) [S]. It is deliberately not derived from the YAML spec.
"""

import pytest

from bounded_calcs import evaluate, load_builtin
from bounded_calcs.testing import assert_matches_reference

CALC = load_builtin()["has_bled"]

FLAGS = [
    "uncontrolled_hypertension",
    "abnormal_renal_function",
    "abnormal_liver_function",
    "prior_stroke",
    "bleeding_history_or_predisposition",
    "labile_inr",
    "antiplatelet_or_nsaid",
    "alcohol_excess",
]

# A complete input that scores 0. Tests change one thing at a time from here.
ZERO = {k: "absent" for k in FLAGS} | {"age": 50}


def reference(v):
    score = sum(v[k] for k in FLAGS) + (v["age"] > 65)
    return score, "high_risk" if score >= 3 else "not_high_risk"


def test_matches_reference():
    assert_matches_reference(CALC, reference)


@pytest.mark.parametrize("age,score", [(65, 0), (66, 1)])
def test_age_threshold(age, score):  # "elderly (> 65 years)"
    assert evaluate(CALC, ZERO | {"age": age})["score"] == score


@pytest.mark.parametrize("item", FLAGS)
def test_each_factor_is_one_point(item):
    assert evaluate(CALC, ZERO | {item: "present"})["score"] == 1


def test_renal_and_liver_and_drugs_and_alcohol_count_separately():
    # "1 or 2 (1 point each)" for A and for D.
    four = {"abnormal_renal_function": "present", "abnormal_liver_function": "present",
            "antiplatelet_or_nsaid": "present", "alcohol_excess": "present"}  # fmt: skip
    assert evaluate(CALC, ZERO | four)["score"] == 4


def test_maximum_is_9():
    assert evaluate(CALC, {k: "present" for k in FLAGS} | {"age": 80})["score"] == 9


def test_sparse_note_gives_a_range():
    # 72-year-old (1) on aspirin (1), blood pressure controlled (0), no prior stroke (0).
    # Renal and liver function, bleeding history, INR control and alcohol are not in the
    # note: five open points. Score 2 to 7.
    note = {"age": 72, "antiplatelet_or_nsaid": "present", "uncontrolled_hypertension": "absent",
            "prior_stroke": "absent"}  # fmt: skip
    r = evaluate(CALC, note)
    assert not r["settled"] and r["score_range"] == [2, 7]
    assert r["possible_categories"] == ["not_high_risk", "high_risk"]
    assert len(r["decisive_unknowns"]) == 5  # any one of them present reaches 3


@pytest.mark.parametrize("n,category", [(2, "not_high_risk"), (3, "high_risk")])
def test_cut_off_at_3(n, category):  # "a score of >=3 indicates high risk" (ESC 2010)
    r = evaluate(CALC, ZERO | {k: "present" for k in FLAGS[:n]})
    assert (r["score"], r["category"]) == (n, category)


def test_three_known_points_settle_high_risk_with_the_rest_unknown():
    # Age 80 (1), prior stroke (1), on an NSAID (1): 3 already. Nothing else needs asking.
    r = evaluate(CALC, {"age": 80, "prior_stroke": "present", "antiplatelet_or_nsaid": "present"})
    assert r["settled"] and r["category"] == "high_risk" and r["decisive_unknowns"] == []
    assert r["score_range"] == [3, 9]
