"""San Francisco Syncope Rule: independent reference, thresholds, clinical examples.

Source: Quinn JV et al. Ann Emerg Med 2004;43(2):224-232, PMID 14747812, results [P]. The
reference is written from the sentence that states the rule: an abnormal ECG, a complaint of
shortness of breath, haematocrit less than 30%, a triage systolic blood pressure less than 90
mmHg, and a history of congestive heart failure; positive with any one. It is deliberately
not derived from the YAML spec.
"""

import pytest

from bounded_calcs import evaluate, load_builtin
from bounded_calcs.testing import assert_matches_reference

CALC = load_builtin()["sf_syncope"]

# A complete input with no predictor. Tests change one thing at a time from here.
ZERO = {
    "abnormal_ecg": "absent",
    "shortness_of_breath": "absent",
    "hematocrit": 40,
    "sbp": 120,
    "history_of_congestive_heart_failure": "absent",
}


def reference(v):
    score = (
        v["abnormal_ecg"]
        + v["shortness_of_breath"]
        + (v["hematocrit"] < 30)
        + (v["sbp"] < 90)
        + v["history_of_congestive_heart_failure"]
    )
    return score, "positive" if score else "negative"


def test_matches_reference():
    assert_matches_reference(CALC, reference)


@pytest.mark.parametrize(
    "change,category",
    [
        ({"hematocrit": 30}, "negative"),  # "hematocrit less than 30%"
        ({"hematocrit": 29}, "positive"),
        ({"sbp": 90}, "negative"),  # "systolic blood pressure less than 90 mm Hg"
        ({"sbp": 89}, "positive"),
        ({"abnormal_ecg": "present"}, "positive"),
        ({"shortness_of_breath": "present"}, "positive"),
        ({"history_of_congestive_heart_failure": "present"}, "positive"),
    ],
)
def test_thresholds_and_each_predictor(change, category):
    assert evaluate(CALC, ZERO | change)["category"] == category


def test_missing_haematocrit_keeps_the_rule_open():
    # Everything else negative and no blood count yet: the rule is negative only if the
    # haematocrit is 30% or more. Reading it as normal would call the rule negative.
    note = {k: v for k, v in ZERO.items() if k != "hematocrit"}
    r = evaluate(CALC, note)
    assert not r["settled"] and r["possible_categories"] == ["negative", "positive"]
    assert [d["item"] for d in r["decisive_unknowns"]] == ["hematocrit"]


def test_one_predictor_settles_it():
    r = evaluate(CALC, {"shortness_of_breath": "present"})
    assert r["settled"] and r["category"] == "positive"
