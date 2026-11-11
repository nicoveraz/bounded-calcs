"""Simplified PESI: independent reference, thresholds, clinical examples.

Source: Jiménez D et al. Arch Intern Med 2010;170(15):1383-1389, PMID 20696966, table 1 and
methods [P]. The reference is written from table 1 (one point each: age over 80 years, history
of cancer, history of heart failure or chronic lung disease, pulse 110 or more, systolic
pressure under 100, saturation under 90%) and the methods (0 is low risk, 1 or more high
risk). It is deliberately not derived from the YAML spec.
"""

import pytest

from bounded_calcs import evaluate, load_builtin
from bounded_calcs.testing import assert_matches_reference

CALC = load_builtin()["spesi"]

# A complete input that scores 0. Tests change one thing at a time from here.
ZERO = {
    "age": 50,
    "history_of_cancer": "absent",
    "history_of_heart_failure": "absent",
    "history_of_chronic_lung_disease": "absent",
    "heart_rate": 80,
    "sbp": 120,
    "sao2": 96,
}


def reference(v):
    score = (
        (v["age"] > 80)
        + v["history_of_cancer"]
        + (v["history_of_heart_failure"] or v["history_of_chronic_lung_disease"])
        + (v["heart_rate"] >= 110)
        + (v["sbp"] < 100)
        + (v["sao2"] < 90)
    )
    return score, "low_risk" if score == 0 else "high_risk"


def test_matches_reference():
    assert_matches_reference(CALC, reference)


@pytest.mark.parametrize(
    "change,score",
    [
        ({"age": 80}, 0),  # "Age >80 y"
        ({"age": 81}, 1),
        ({"heart_rate": 109}, 0),  # "Pulse >=110 beats/min"
        ({"heart_rate": 110}, 1),
        ({"sbp": 100}, 0),  # "Systolic blood pressure <100 mm Hg"
        ({"sbp": 99}, 1),
        ({"sao2": 90}, 0),  # "Arterial oxyhemoglobin saturation level <90%"
        ({"sao2": 89}, 1),
    ],
)
def test_thresholds(change, score):
    r = evaluate(CALC, ZERO | change)
    assert r["score"] == score
    assert r["category"] == ("high_risk" if score else "low_risk")


def test_heart_failure_and_lung_disease_are_one_variable():
    both = {"history_of_heart_failure": "present", "history_of_chronic_lung_disease": "present"}
    assert evaluate(CALC, ZERO | both)["score"] == 1


def test_all_six_variables():
    worst = {"age": 85, "history_of_cancer": "present", "history_of_heart_failure": "present",
             "history_of_chronic_lung_disease": "absent", "heart_rate": 120, "sbp": 90,
             "sao2": 85}  # fmt: skip
    r = evaluate(CALC, worst)
    assert (r["score"], r["category"]) == (6, "high_risk")


def test_sparse_note_cannot_be_called_low_risk():
    # 67-year-old, heart rate 104, blood pressure 128/76, no cancer. Nothing on heart failure
    # or chronic lung disease, no saturation recorded. Known points: 0. Open: the
    # cardiopulmonary variable (0 or 1) and saturation (0 or 1): score 0 to 2.
    note = {"age": 67, "heart_rate": 104, "sbp": 128, "history_of_cancer": "absent"}
    r = evaluate(CALC, note)
    assert not r["settled"] and r["score_range"] == [0, 2]
    assert r["possible_categories"] == ["low_risk", "high_risk"]
    assert {d["item"] for d in r["decisive_unknowns"]} == {
        "history_of_heart_failure",
        "history_of_chronic_lung_disease",
        "sao2",
    }


def test_one_variable_present_settles_high_risk():
    r = evaluate(CALC, {"history_of_cancer": "present"})
    assert r["settled"] and r["category"] == "high_risk"
