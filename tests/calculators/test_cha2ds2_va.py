"""CHA2DS2-VA: independent reference, thresholds, clinical examples.

Source: 2024 ESC Guidelines for the management of atrial fibrillation, Eur Heart J
2024;45(36):3314-3414, doi:10.1093/eurheartj/ehae176, Table 10 and the text after it [P]. The
reference is written from Table 10 (chronic heart failure 1, hypertension 1, age 75 years or
more 2, diabetes mellitus 1, prior stroke/TIA/arterial thromboembolism 2, vascular disease 1,
age 65 to 74 years 1; no sex criterion) and the text (anticoagulation recommended with a score
of 2 or more, should be considered with a score of 1). It is deliberately not derived from the
YAML spec.
"""

import pytest

from bounded_calcs import evaluate, load_builtin
from bounded_calcs.testing import assert_matches_reference

CALC = load_builtin()["cha2ds2_va"]

# A complete input that scores 0. Tests change one thing at a time from here.
ZERO = {
    "chronic_heart_failure": "absent",
    "hypertension": "absent",
    "age": 50,
    "diabetes": "absent",
    "prior_stroke_tia_or_thromboembolism": "absent",
    "vascular_disease": "absent",
}


def reference(v):
    score = 0
    if v["age"] >= 75:
        score += 2
    elif v["age"] >= 65:
        score += 1
    for one_point in ("chronic_heart_failure", "hypertension", "diabetes", "vascular_disease"):
        score += 1 if v[one_point] else 0
    if v["prior_stroke_tia_or_thromboembolism"]:
        score += 2
    if score >= 2:
        return score, "score_2_or_more"
    return score, "score_1" if score == 1 else "score_0"


def test_matches_reference():
    assert_matches_reference(CALC, reference)


@pytest.mark.parametrize(
    "change,score,category",
    [
        ({}, 0, "score_0"),
        ({"age": 64}, 0, "score_0"),
        ({"age": 65}, 1, "score_1"),  # "Age 65-74 years": 1
        ({"age": 74}, 1, "score_1"),
        ({"age": 75}, 2, "score_2_or_more"),  # "Age >= 75 years": 2
        ({"chronic_heart_failure": "present"}, 1, "score_1"),
        ({"hypertension": "present"}, 1, "score_1"),
        ({"diabetes": "present"}, 1, "score_1"),
        ({"vascular_disease": "present"}, 1, "score_1"),
        ({"prior_stroke_tia_or_thromboembolism": "present"}, 2, "score_2_or_more"),
        ({"hypertension": "present", "diabetes": "present"}, 2, "score_2_or_more"),
    ],
)
def test_points_and_categories(change, score, category):
    r = evaluate(CALC, ZERO | change)
    assert (r["score"], r["category"]) == (score, category)


def test_maximum_is_8():
    worst = {"chronic_heart_failure": "present", "hypertension": "present", "age": 80,
             "diabetes": "present", "prior_stroke_tia_or_thromboembolism": "present",
             "vascular_disease": "present"}  # fmt: skip
    assert evaluate(CALC, worst)["score"] == 8  # 1 + 1 + 2 + 1 + 2 + 1


def test_there_is_no_sex_item():
    assert "sex" not in CALC.items


def test_age_alone_can_settle_it():
    # 78 years: 2 points whatever the history is, so "2 or more" is settled and nothing
    # needs asking.
    r = evaluate(CALC, {"age": 78})
    assert r["settled"] and r["category"] == "score_2_or_more" and r["score_range"] == [2, 8]
    assert r["decisive_unknowns"] == []


def test_sparse_note_that_is_not_settled():
    # 58 years, hypertension and diabetes recorded as absent, nothing else known: heart
    # failure (0 or 1), stroke (0 or 2), vascular disease (0 or 1). Score 0 to 4.
    note = {"age": 58, "hypertension": "absent", "diabetes": "absent"}
    r = evaluate(CALC, note)
    assert not r["settled"] and r["score_range"] == [0, 4]
    assert r["possible_categories"] == ["score_0", "score_1", "score_2_or_more"]


def test_one_known_point_leaves_consider_or_recommended():
    # 68 years (1 point), no stroke; the four one-point items (heart failure, hypertension,
    # diabetes, vascular disease) unknown: 1 to 5.
    r = evaluate(CALC, {"age": 68, "prior_stroke_tia_or_thromboembolism": "absent"})
    assert r["possible_categories"] == ["score_1", "score_2_or_more"]
    assert r["score_range"] == [1, 5]
