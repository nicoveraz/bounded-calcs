"""CHA2DS2-VASc: independent reference, thresholds, clinical examples.

Source: Lip GYH et al. Chest 2010;137(2):263-272, PMID 19762550, table 2 and methods [P]. The
reference is written from table 2 (heart failure or LV dysfunction 1, hypertension 1, age 75
or more 2, diabetes 1, stroke/TIA/thromboembolism 2, vascular disease 1, age 65 to 74 1,
female sex 1) and the methods (0 low, 1 intermediate, 2 or more high). It is deliberately not
derived from the YAML spec.
"""

import pytest

from bounded_calcs import evaluate, load_builtin
from bounded_calcs.testing import assert_matches_reference

CALC = load_builtin()["cha2ds2_vasc"]

# A complete input that scores 0. Tests change one thing at a time from here.
ZERO = {
    "chf_or_lv_dysfunction": "absent",
    "hypertension": "absent",
    "age": 50,
    "diabetes": "absent",
    "prior_stroke_tia_or_thromboembolism": "absent",
    "vascular_disease": "absent",
    "sex": "male",
}


def reference(v):
    age = 2 if v["age"] >= 75 else 1 if v["age"] >= 65 else 0
    score = (
        v["chf_or_lv_dysfunction"]
        + v["hypertension"]
        + age
        + v["diabetes"]
        + 2 * v["prior_stroke_tia_or_thromboembolism"]
        + v["vascular_disease"]
        + (v["sex"] == "female")
    )
    return score, "low" if score == 0 else "intermediate" if score == 1 else "high"


def test_matches_reference():
    assert_matches_reference(CALC, reference)


@pytest.mark.parametrize(
    "change,score,category",
    [
        ({"age": 64}, 0, "low"),
        ({"age": 65}, 1, "intermediate"),  # "Age 65-74 y": 1
        ({"age": 74}, 1, "intermediate"),
        ({"age": 75}, 2, "high"),  # "Age >=75 y": 2
        ({"sex": "female"}, 1, "intermediate"),
        ({"prior_stroke_tia_or_thromboembolism": "present"}, 2, "high"),
        ({"hypertension": "present", "diabetes": "present"}, 2, "high"),
    ],
)
def test_points_and_categories(change, score, category):
    r = evaluate(CALC, ZERO | change)
    assert (r["score"], r["category"]) == (score, category)


def test_maximum_is_9():
    worst = {"chf_or_lv_dysfunction": "present", "hypertension": "present", "age": 80,
             "diabetes": "present", "prior_stroke_tia_or_thromboembolism": "present",
             "vascular_disease": "present", "sex": "female"}  # fmt: skip
    assert evaluate(CALC, worst)["score"] == 9  # 1 + 1 + 2 + 1 + 2 + 1 + 1


def test_sparse_note_is_already_high_risk():
    # 78-year-old woman: 2 + 1 = 3 whatever her history is. High risk is settled; the
    # history items cannot change it.
    r = evaluate(CALC, {"age": 78, "sex": "female"})
    assert r["settled"] and r["category"] == "high" and r["score_range"] == [3, 9]


def test_sparse_note_that_is_not_settled():
    # 58-year-old man, no hypertension or diabetes recorded as absent, nothing else known:
    # heart failure (0 or 1), stroke (0 or 2), vascular disease (0 or 1). Score 0 to 4.
    note = {"age": 58, "sex": "male", "hypertension": "absent", "diabetes": "absent"}
    r = evaluate(CALC, note)
    assert not r["settled"] and r["score_range"] == [0, 4]
    assert r["possible_categories"] == ["low", "intermediate", "high"]
