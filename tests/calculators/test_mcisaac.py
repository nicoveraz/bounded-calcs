"""McIsaac sore throat score: independent reference, threshold cases and clinical examples.

Source: McIsaac WJ et al. CMAJ 1998;158(1):75-83, PMID 9475915, figure [P]. The reference is
written from that figure: temperature > 38 C, no cough, tender anterior cervical adenopathy
and tonsillar swelling or exudate score 1 point each; age 3-14 years +1, 15-44 years 0, 45
years or more -1. Management by total: 0-1, 2-3, 4. The source counts a total below 0 as 0
and allows at most 4; the calculator reports the plain sum (-1 to 5), which gives the same
categories. It is deliberately not derived from the YAML spec.
"""

import pytest

from bounded_calcs import evaluate, load_builtin
from bounded_calcs.testing import assert_matches_reference

CALC = load_builtin()["mcisaac"]

# An adult of 30 with a cough and no other criterion: score 0.
ZERO = {
    "fever_over_38": "absent",
    "cough": "present",
    "tender_anterior_cervical_nodes": "absent",
    "tonsillar_swelling_or_exudate": "absent",
    "age": 30,
}


def reference(v):
    score = (
        v["fever_over_38"]
        + (not v["cough"])
        + v["tender_anterior_cervical_nodes"]
        + v["tonsillar_swelling_or_exudate"]
        + (-1 if v["age"] >= 45 else 0 if v["age"] >= 15 else 1)
    )
    if score <= 1:
        return score, "no_culture_no_antibiotic"
    return score, "culture_treat_if_positive" if score <= 3 else "culture_treat_on_clinical_grounds"


def test_matches_reference():
    assert_matches_reference(CALC, reference)


# --- points and thresholds, from the source's own numbers --------------------------------------


@pytest.mark.parametrize(
    "change",
    [
        {"fever_over_38": "present"},
        {"cough": "absent"},  # the point is for NO cough
        {"tender_anterior_cervical_nodes": "present"},
        {"tonsillar_swelling_or_exudate": "present"},
    ],
)
def test_each_criterion_scores_one_point(change):
    assert evaluate(CALC, ZERO | change)["score"] == 1


@pytest.mark.parametrize(
    "age,points",
    [
        (3, 1),  # "Age 3-14 yr": 1
        (14, 1),
        (15, 0),  # "Age 15-44 yr": 0
        (44, 0),
        (45, -1),  # "Age >= 45 yr": -1
    ],
)
def test_age_bands(age, points):
    assert evaluate(CALC, ZERO | {"age": age})["score"] == points


ALL_FOUR = {
    "fever_over_38": "present",
    "cough": "absent",
    "tender_anterior_cervical_nodes": "present",
    "tonsillar_swelling_or_exudate": "present",
}


@pytest.mark.parametrize(
    "values,score,category",
    [
        (ZERO | {"cough": "absent"}, 1, "no_culture_no_antibiotic"),  # 0-1
        (ZERO | {"cough": "absent", "fever_over_38": "present"}, 2, "culture_treat_if_positive"),
        (ZERO | ALL_FOUR | {"age": 50}, 3, "culture_treat_if_positive"),  # 4 - 1 = 3
        (ZERO | ALL_FOUR, 4, "culture_treat_on_clinical_grounds"),  # 4
        # The source caps the total at 4 and floors it at 0: same categories as the plain sum.
        (ZERO | ALL_FOUR | {"age": 8}, 5, "culture_treat_on_clinical_grounds"),
        (ZERO | {"age": 60}, -1, "no_culture_no_antibiotic"),
    ],
)
def test_categories(values, score, category):
    r = evaluate(CALC, values)
    assert (r["score"], r["category"]) == (score, category)


# --- unknown is not normal ---------------------------------------------------------------------


def test_cough_not_mentioned_is_not_no_cough():
    # Triage note: 25-year-old, sore throat, reported fever of 38.5 C, tonsillar exudate. Cough
    # and neck nodes are not mentioned. Known points: fever 1 + exudate 1 + age 0 = 2. Cough
    # open (0 or 1), nodes open (0 or 1): score 2 to 4.
    # Culture-and-wait at least; treat on clinical grounds only with no cough AND tender nodes,
    # so neither item settles it alone, but each can.
    note = {"age": 25, "fever_over_38": "present", "tonsillar_swelling_or_exudate": "present"}
    r = evaluate(CALC, note)
    assert not r["settled"]
    assert r["score_range"] == [2, 4]
    assert r["possible_categories"] == [
        "culture_treat_if_positive",
        "culture_treat_on_clinical_grounds",
    ]
    assert {d["item"] for d in r["decisive_unknowns"]} == {
        "cough",
        "tender_anterior_cervical_nodes",
    }
    # Reading "cough not mentioned" as "no cough" would add a point the note does not support.


def test_settled_for_an_older_adult_with_two_items_unknown():
    # 60-year-old (-1) with a cough (0) and no fever (0); nodes and tonsils not documented:
    # score -1 to 1, so no culture or antibiotic whatever they are.
    r = evaluate(CALC, {"age": 60, "cough": "present", "fever_over_38": "absent"})
    assert r["settled"] and r["category"] == "no_culture_no_antibiotic"
    assert r["score_range"] == [-1, 1]
