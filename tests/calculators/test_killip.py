"""Killip classification: independent reference and clinical examples.

Source: Killip T, Kimball JT. Am J Cardiol 1967;20(4):457-464, PMID 6059183, methods [P]. The
reference is written from the paragraph that defines the groups: A no heart failure; B heart
failure (rales, S3 gallop, venous hypertension); C severe heart failure (frank pulmonary
oedema); D cardiogenic shock. The most severe group present applies. It is deliberately not
derived from the YAML spec.
"""

import pytest

from bounded_calcs import evaluate, load_builtin
from bounded_calcs.testing import assert_matches_reference

CALC = load_builtin()["killip"]

B_SIGNS = ["rales", "s3_gallop", "venous_hypertension"]
ZERO = {k: "absent" for k in B_SIGNS} | {
    "frank_pulmonary_edema": "absent",
    "cardiogenic_shock": "absent",
}


def reference(v):
    b = any(v[k] for k in B_SIGNS)
    score = b + v["frank_pulmonary_edema"] + v["cardiogenic_shock"]
    if v["cardiogenic_shock"]:
        return score, "d_cardiogenic_shock"
    if v["frank_pulmonary_edema"]:
        return score, "c_severe_heart_failure"
    return score, "b_heart_failure" if b else "a_no_heart_failure"


def test_matches_reference():
    assert_matches_reference(CALC, reference)


def test_no_signs_is_group_a():
    assert evaluate(CALC, ZERO)["category"] == "a_no_heart_failure"


@pytest.mark.parametrize("sign", B_SIGNS)
def test_each_sign_of_heart_failure_is_group_b(sign):
    assert evaluate(CALC, ZERO | {sign: "present"})["category"] == "b_heart_failure"


def test_pulmonary_oedema_is_group_c_with_or_without_the_other_signs():
    assert evaluate(CALC, ZERO | {"frank_pulmonary_edema": "present"})["category"] == (
        "c_severe_heart_failure"
    )
    both = ZERO | {"frank_pulmonary_edema": "present", "rales": "present"}
    assert evaluate(CALC, both)["category"] == "c_severe_heart_failure"


def test_shock_is_group_d_whatever_else_is_found():
    r = evaluate(CALC, {"cardiogenic_shock": "present"})
    assert r["settled"] and r["category"] == "d_cardiogenic_shock"


def test_lungs_not_examined_leaves_the_group_open():
    # No shock, no S3, neck veins flat; the note says nothing about the chest. Rales and
    # pulmonary oedema are open: A, B or C.
    note = {"cardiogenic_shock": "absent", "s3_gallop": "absent", "venous_hypertension": "absent"}
    r = evaluate(CALC, note)
    assert not r["settled"]
    assert r["possible_categories"] == [
        "a_no_heart_failure",
        "b_heart_failure",
        "c_severe_heart_failure",
    ]
    assert {d["item"] for d in r["decisive_unknowns"]} == {"rales", "frank_pulmonary_edema"}
