"""CURB-65: independent reference, threshold cases and clinical examples.

Source: Lim WS et al. Thorax 2003;58(5):377-382, Figure 2. PMID 12728155.
The reference is transcribed from calc-bounds (curb65.py), which was written from that
figure. It is deliberately not derived from the YAML spec.
"""

import pytest

from bounded_calcs import evaluate, load_builtin
from bounded_calcs.testing import assert_matches_reference

CALC = load_builtin()["curb65"]

# A complete input that scores 0. Tests change one thing at a time from here.
ZERO = {"confusion": "absent", "urea": 5, "resp_rate": 18, "sbp": 120, "dbp": 80, "age": 50}


def reference(v):
    score = (
        v["confusion"]
        + (v["urea"] > 7)
        + (v["resp_rate"] >= 30)
        + (v["sbp"] < 90 or v["dbp"] <= 60)
        + (v["age"] >= 65)
    )
    return score, "low" if score <= 1 else "moderate" if score == 2 else "high"


def test_matches_reference():
    assert_matches_reference(CALC, reference)


# --- thresholds, from the source's own numbers ------------------------------------------------


@pytest.mark.parametrize(
    "change,points",
    [
        ({"urea": 7}, 0),  # urea > 7 mmol/L
        ({"urea": 7.1}, 1),
        ({"resp_rate": 29}, 0),  # respiratory rate >= 30
        ({"resp_rate": 30}, 1),
        ({"sbp": 90}, 0),  # SBP < 90
        ({"sbp": 89}, 1),
        ({"dbp": 61}, 0),  # DBP <= 60
        ({"dbp": 60}, 1),
        ({"age": 64}, 0),  # age >= 65
        ({"age": 65}, 1),
    ],
)
def test_thresholds(change, points):
    assert evaluate(CALC, ZERO | change)["score"] == points


def test_low_systolic_and_low_diastolic_count_once():
    assert evaluate(CALC, ZERO | {"sbp": 85, "dbp": 50})["score"] == 1


@pytest.mark.parametrize("score,category", [(0, "low"), (1, "low"), (2, "moderate"), (3, "high")])
def test_categories(score, category):
    changes = [{"confusion": "present"}, {"urea": 9}, {"resp_rate": 32}][:score]
    values = dict(ZERO)
    for c in changes:
        values |= c
    r = evaluate(CALC, values)
    assert (r["score"], r["category"]) == (score, category)


# --- unknown is not normal ---------------------------------------------------------------------


def test_blood_pressure_point_with_one_reading_missing():
    base = {k: v for k, v in ZERO.items() if k not in ("sbp", "dbp")}
    # SBP already low: the point is earned whatever the DBP is.
    r = evaluate(CALC, base | {"sbp": 85})
    assert r["settled"] and r["score"] == 1
    # SBP normal and DBP unknown: the point is still open.
    assert evaluate(CALC, base | {"sbp": 120})["score_range"] == [0, 1]


def test_sparse_note_is_not_settled():
    # 70 years old with urea 9: two points known. Confusion, respiratory rate and blood
    # pressure are not documented, so the patient is moderate or high, not "moderate".
    r = evaluate(CALC, {"age": 70, "urea": 9})
    assert not r["settled"]
    assert r["possible_categories"] == ["moderate", "high"]
    assert r["worst_case_category"] == "high"
    assert {d["item"] for d in r["decisive_unknowns"]} == {"confusion", "resp_rate", "sbp", "dbp"}
