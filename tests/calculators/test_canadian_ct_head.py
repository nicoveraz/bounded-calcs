"""Canadian CT Head Rule: independent reference, thresholds, clinical examples.

Source: Stiell IG et al. Lancet 2001;357(9266):1391-1396, PMID 11356436, panel 1 [P]. The
reference is written from panel 1: high risk if GCS below 15 at 2 h, suspected open or
depressed skull fracture, any sign of basal skull fracture, vomiting two or more episodes, or
age 65 years or more; otherwise medium risk if amnesia before impact of more than 30 min or a
dangerous mechanism; otherwise no criterion. The score is the number of criteria present. It
is deliberately not derived from the YAML spec.
"""

import pytest

from bounded_calcs import InputError, evaluate, load_builtin
from bounded_calcs.testing import assert_matches_reference

CALC = load_builtin()["canadian_ct_head"]

HIGH = [
    "gcs_below_15_at_2h",
    "suspected_open_or_depressed_skull_fracture",
    "basal_skull_fracture_sign",
    "vomiting_two_or_more_episodes",
]
MEDIUM = ["amnesia_before_impact_over_30_min", "dangerous_mechanism"]

# No criterion present. Tests change one thing at a time from here.
ZERO = {k: "absent" for k in HIGH + MEDIUM} | {"age": 40}


def reference(v):
    high = [v[k] for k in HIGH] + [v["age"] >= 65]
    medium = [v[k] for k in MEDIUM]
    score = sum(high) + sum(medium)
    if any(high):
        return score, "high_risk"
    return score, "medium_risk" if any(medium) else "no_criterion"


def test_matches_reference():
    assert_matches_reference(CALC, reference)


@pytest.mark.parametrize("age,category", [(64, "no_criterion"), (65, "high_risk")])
def test_age_threshold(age, category):  # "Age >=65 years"
    assert evaluate(CALC, ZERO | {"age": age})["category"] == category


@pytest.mark.parametrize("item", HIGH)
def test_each_high_risk_criterion(item):
    r = evaluate(CALC, ZERO | {item: "present"})
    assert (r["score"], r["category"]) == (1, "high_risk")


@pytest.mark.parametrize("item", MEDIUM)
def test_each_medium_risk_criterion(item):
    r = evaluate(CALC, ZERO | {item: "present"})
    assert (r["score"], r["category"]) == (1, "medium_risk")


def test_both_medium_criteria_stay_medium():
    # Two medium-risk criteria (2 points) stay below one high-risk criterion (1 point).
    r = evaluate(CALC, ZERO | {k: "present" for k in MEDIUM})
    assert (r["score"], r["category"]) == (2, "medium_risk")


def test_under_16_is_outside_the_rule():
    with pytest.raises(InputError, match="outside the values this calculator accepts"):
        evaluate(CALC, ZERO | {"age": 15})


def test_sparse_note_with_a_fall():
    # 52-year-old who fell down eight stairs (dangerous mechanism), GCS 15 on arrival. Not
    # documented: GCS at 2 h, skull examination, vomiting, amnesia. Known: 1 medium-risk
    # criterion. Each of the four high-risk findings is open: score 1 to 1 + 4 + 1 = 6.
    # Medium risk at least; high risk if any high-risk finding is present. Amnesia cannot
    # change the tier any more.
    r = evaluate(CALC, {"age": 52, "dangerous_mechanism": "present"})
    assert not r["settled"] and r["score_range"] == [1, 6]
    assert r["possible_categories"] == ["medium_risk", "high_risk"]
    assert {d["item"] for d in r["decisive_unknowns"]} == set(HIGH)
    assert r["irrelevant_unknowns"] == ["amnesia_before_impact_over_30_min"]


def test_age_65_settles_high_risk():
    r = evaluate(CALC, {"age": 70})
    assert r["settled"] and r["category"] == "high_risk"
