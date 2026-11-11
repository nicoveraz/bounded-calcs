"""MELD-Na (Kim 2008): independent reference, limits, worked examples.

Source: Kim WR et al. N Engl J Med 2008;359(10):1018-1026, PMID 18768945 [P]. The reference is
written from the paper's text: MELD = 11.2 ln(INR) + 9.57 ln(creatinine) + 3.78 ln(bilirubin)
+ 6.43, each variable at least 1, creatinine at most 4 and set at 4 on renal-replacement
therapy, range 6 to 40; MELDNa = MELD - Na - [0.025 x MELD x (140 - Na)] + 140 with Na bound
between 125 and 140, rounded to the nearest integer. It is deliberately not derived from the
YAML spec. The source defines no categories, so the reference returns the score alone.
"""

import math

import pytest

from bounded_calcs import InputError, evaluate, load_builtin
from bounded_calcs.testing import assert_matches_reference

CALC = load_builtin()["meld_na"]

# Every variable at its lower limit of 1 and a normal sodium: the lowest score.
BASE = {
    "inr": 1,
    "creatinine": 1,
    "bilirubin": 1,
    "sodium": 140,
    "renal_replacement_therapy": "absent",
}


def reference(v):
    creatinine = 4.0 if v["renal_replacement_therapy"] else min(max(v["creatinine"], 1.0), 4.0)
    meld = (
        11.2 * math.log(max(v["inr"], 1.0))
        + 9.57 * math.log(creatinine)
        + 3.78 * math.log(max(v["bilirubin"], 1.0))
        + 6.43
    )
    meld = min(meld, 40.0)
    na = min(max(v["sodium"], 125.0), 140.0)
    score = meld - na - 0.025 * meld * (140.0 - na) + 140.0
    return round(min(max(score, 6.0), 40.0)), None


def test_matches_reference():
    assert_matches_reference(CALC, reference)


@pytest.mark.parametrize(
    "change,score",
    [
        # ln(1) = 0 for all three: MELD 6.43; sodium 140 adds nothing. Rounded: 6.
        ({}, 6),
        # Sodium 125: 6.43 - 125 - 0.025 x 6.43 x 15 + 140 = 19.02. Rounded: 19.
        ({"sodium": 125}, 19),
        # Renal-replacement therapy: creatinine 4. 9.57 x ln(4) = 13.27; MELD 19.70: 20.
        ({"renal_replacement_therapy": "present"}, 20),
        # The same with sodium 125: 19.70 - 125 - 0.025 x 19.70 x 15 + 140 = 27.31: 27.
        ({"renal_replacement_therapy": "present", "sodium": 125}, 27),
        # INR e: 11.2 x 1 = 11.2; MELD 17.63: 18.
        ({"inr": math.e}, 18),
        # Bilirubin e: 3.78 x 1; MELD 10.21: 10.
        ({"bilirubin": math.e}, 10),
    ],
)
def test_worked_values(change, score):
    r = evaluate(CALC, BASE | change)
    assert r["settled"] and r["score"] == score and r["category"] is None


def test_the_example_in_the_source():
    # "a MELD score of 10 and a serum sodium concentration of 125 ... MELDNa score of 21".
    # Creatinine 1.452: 9.57 x ln(1.452) = 3.57, so MELD = 10.00.
    # 10 - 125 - 0.025 x 10 x 15 + 140 = 21.25. Rounded: 21.
    assert evaluate(CALC, BASE | {"creatinine": 1.452, "sodium": 125})["score"] == 21


@pytest.mark.parametrize(
    "inside,outside",
    [
        ({"inr": 1}, {"inr": 0.8}),  # "a lower limit of 1 for all variables"
        ({"creatinine": 1}, {"creatinine": 0.6}),
        ({"bilirubin": 1}, {"bilirubin": 0.4}),
        ({"creatinine": 4}, {"creatinine": 6}),  # "creatinine capped at 4"
        ({"sodium": 140}, {"sodium": 150}),  # "bound between 125 and 140"
        ({"sodium": 125}, {"sodium": 110}),
    ],
)
def test_limits_on_the_inputs(inside, outside):
    assert evaluate(CALC, BASE | inside)["score"] == evaluate(CALC, BASE | outside)["score"]


def test_the_score_stays_between_6_and_40():
    worst = {"inr": 20, "creatinine": 10, "bilirubin": 60, "sodium": 110,
             "renal_replacement_therapy": "present"}  # fmt: skip
    assert evaluate(CALC, worst)["score"] == 40
    assert evaluate(CALC, {})["score_range"] == [6, 40]


def test_unknown_sodium_gives_a_range_not_a_normal_value():
    # Sodium not reported: anywhere from 6 (sodium 140 or more) to 19 (125 or less).
    known = {k: v for k, v in BASE.items() if k != "sodium"}
    r = evaluate(CALC, known)
    assert not r["settled"] and r["score"] is None and r["score_range"] == [6, 19]
    assert [d["item"] for d in r["decisive_unknowns"]] == ["sodium"]


def test_sodium_known_only_as_normal_range_can_settle_it():
    # "Sodium at least 140" is enough: the formula uses 140 for anything higher.
    r = evaluate(CALC, BASE | {"sodium": {"min": 140}})
    assert r["settled"] and r["score"] == 6


def test_creatinine_in_micromol_per_litre():
    # 353.6 micromol/L / 88.4 = 4 mg/dL: the same 20 as renal-replacement therapy gives.
    r = evaluate(CALC, BASE | {"creatinine": {"value": 353.6, "unit": "umol/L"}})
    assert r["score"] == 20
    with pytest.raises(InputError, match="outside the values this calculator accepts"):
        evaluate(CALC, BASE | {"creatinine": 353.6})  # the same number read as mg/dL
