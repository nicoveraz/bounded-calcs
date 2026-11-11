"""BISAP: independent reference, thresholds, clinical examples.

Source: Wu BU et al. Gut 2008;57(12):1698-1703, PMID 18519429, methods and results [P]. The
reference is written from the scoring sentence (one point each during the first 24 h: BUN
over 25 mg/dL, impaired mental status, SIRS, age over 60 years, pleural effusion) and the
methods definition of SIRS (2 or more of four criteria); and from Singh 2009 (abstract) for
the cut-off at a score of 3 or more [A]. It is deliberately not derived from the YAML spec.
"""

import pytest

from bounded_calcs import evaluate, load_builtin
from bounded_calcs.testing import assert_matches_reference

CALC = load_builtin()["bisap"]

SIRS = ["sirs_pulse_over_90", "sirs_respiratory", "sirs_temperature", "sirs_white_cells"]

# A complete input that scores 0. Tests change one thing at a time from here.
ZERO = {
    "bun": 15,
    "impaired_mental_status": "absent",
    "age": 50,
    "pleural_effusion": "absent",
} | {k: "absent" for k in SIRS}


def reference(v):
    sirs = sum(v[k] for k in SIRS) >= 2
    score = (
        (v["bun"] > 25) + v["impaired_mental_status"] + sirs + (v["age"] > 60)
        + v["pleural_effusion"]
    )  # fmt: skip
    return score, "three_or_more" if score >= 3 else "below_3"


def test_matches_reference():
    assert_matches_reference(CALC, reference)


@pytest.mark.parametrize(
    "change,score",
    [
        ({"bun": 25}, 0),  # "BUN >25 mg/dl"
        ({"bun": 26}, 1),
        ({"age": 60}, 0),  # "age >60 years"
        ({"age": 61}, 1),
        ({"sirs_pulse_over_90": "present"}, 0),  # one criterion is not SIRS
        ({"sirs_pulse_over_90": "present", "sirs_temperature": "present"}, 1),  # "2 or more"
        ({k: "present" for k in SIRS}, 1),  # still one point
    ],
)
def test_thresholds(change, score):
    r = evaluate(CALC, ZERO | change)
    assert r["settled"] and r["score"] == score and r["category"] == "below_3"


def test_all_five():
    worst = {"bun": 40, "impaired_mental_status": "present", "age": 75,
             "pleural_effusion": "present"} | {k: "present" for k in SIRS}  # fmt: skip
    r = evaluate(CALC, worst)
    assert (r["score"], r["category"]) == (5, "three_or_more")


def test_cut_off_at_3():  # "a BISAP score >=3 was associated with ..." (Singh 2009)
    two = {"bun": 40, "age": 75}
    assert evaluate(CALC, ZERO | two)["category"] == "below_3"
    three = evaluate(CALC, ZERO | two | {"pleural_effusion": "present"})
    assert (three["score"], three["category"]) == (3, "three_or_more")


def test_urea_in_other_units_is_converted_to_urea_nitrogen():
    # Urea 10 mmol/L x 2.8014 = 28.0 mg/dL of urea nitrogen: over 25. Urea 8 mmol/L = 22.4.
    over = evaluate(CALC, ZERO | {"bun": {"value": 10, "unit": "urea_mmol/L"}})
    under = evaluate(CALC, ZERO | {"bun": {"value": 8, "unit": "urea_mmol/L"}})
    assert (over["score"], under["score"]) == (1, 0)
    # Urea 60 mg/dL / 2.1439 = 28.0 mg/dL of urea nitrogen: over 25.
    assert evaluate(CALC, ZERO | {"bun": {"value": 60, "unit": "urea_mg/dL"}})["score"] == 1


def test_sparse_note_gives_a_range():
    # First day: BUN 30 (1), age 70 (1), alert and oriented (0), no effusion on the chest
    # film (0), pulse 104 (one SIRS criterion). Respiratory rate, temperature and white cell
    # count are not in the note. Known points 2; SIRS needs one more criterion: score 2 or 3.
    note = {
        "bun": 30,
        "age": 70,
        "impaired_mental_status": "absent",
        "pleural_effusion": "absent",
        "sirs_pulse_over_90": "present",
    }
    r = evaluate(CALC, note)
    assert not r["settled"] and r["score"] is None and r["score_range"] == [2, 3]
    assert r["possible_categories"] == ["below_3", "three_or_more"]
    assert {d["item"] for d in r["decisive_unknowns"]} == {
        "sirs_respiratory",
        "sirs_temperature",
        "sirs_white_cells",
    }


def test_sirs_already_met_makes_the_other_criteria_irrelevant():
    note = ZERO | {"sirs_pulse_over_90": "present", "sirs_temperature": "present"}
    del note["sirs_white_cells"]
    r = evaluate(CALC, note)
    assert r["settled"] and r["score"] == 1 and r["irrelevant_unknowns"] == ["sirs_white_cells"]
