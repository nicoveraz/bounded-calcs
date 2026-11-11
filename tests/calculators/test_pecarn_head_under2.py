"""PECARN head injury rule, under 2 years: independent reference, thresholds, clinical examples.

Source: Kuppermann N et al. Lancet 2009;374(9696):1160-1170, PMID 19758692, figure 3A [P]
(definitions from figure 2A, panel 1 and methods). The reference is written from figure 3A:
CT recommended if GCS 14 or other signs of altered mental status, or palpable skull fracture;
otherwise observation versus CT if occipital, parietal or temporal scalp haematoma, loss of
consciousness of 5 s or more, severe mechanism, or not acting normally per parent; otherwise
CT not recommended. The score is the procedure's tiered encoding (5 points per high-risk
criterion, 1 per intermediate one). It is deliberately not derived from the YAML spec.
"""

import pytest

from bounded_calcs import evaluate, load_builtin
from bounded_calcs.testing import assert_matches_reference

CALC = load_builtin()["pecarn_head_under2"]

INTERMEDIATE = [
    "nonfrontal_scalp_hematoma",
    "loc_5s_or_more",
    "severe_mechanism_under2",
    "acting_abnormally",
]

# No predictor present: GCS 15 and every finding absent. Score 0, CT not recommended.
ZERO = {
    "gcs": 15,
    "other_ams_signs": "absent",
    "palpable_skull_fracture": "absent",
} | {k: "absent" for k in INTERMEDIATE}


def reference(v):
    altered_mental_status = v["gcs"] < 15 or v["other_ams_signs"]  # "GCS=14 or other signs"
    high = [altered_mental_status, v["palpable_skull_fracture"]]
    intermediate = [v[k] for k in INTERMEDIATE]
    score = 5 * sum(map(bool, high)) + sum(intermediate)
    if any(high):
        return score, "ct_recommended"
    if any(intermediate):
        return score, "observation_vs_ct"
    return score, "ct_not_recommended"


def test_matches_reference():
    assert_matches_reference(CALC, reference)


# --- thresholds and tiers, from the source's own wording ---------------------------------------


@pytest.mark.parametrize(
    "gcs,category",
    [
        (15, "ct_not_recommended"),  # normal mental status
        (14, "ct_recommended"),  # "GCS=14" (figure 3A); "GCS score lower than 15" (methods)
    ],
)
def test_gcs_threshold(gcs, category):
    assert evaluate(CALC, ZERO | {"gcs": gcs})["category"] == category


@pytest.mark.parametrize("item", ["other_ams_signs", "palpable_skull_fracture"])
def test_each_high_risk_criterion_recommends_ct(item):
    r = evaluate(CALC, ZERO | {item: "present"})
    assert (r["score"], r["category"]) == (5, "ct_recommended")


@pytest.mark.parametrize("item", INTERMEDIATE)
def test_each_intermediate_criterion_means_observation_versus_ct(item):
    r = evaluate(CALC, ZERO | {item: "present"})
    assert (r["score"], r["category"]) == (1, "observation_vs_ct")


def test_all_intermediate_criteria_stay_below_ct_recommended():
    # Four intermediate criteria: 4 points, still observation versus CT (the tier, not a count).
    r = evaluate(CALC, ZERO | {k: "present" for k in INTERMEDIATE})
    assert (r["score"], r["category"]) == (4, "observation_vs_ct")


def test_gcs_14_and_other_signs_count_once():
    # One criterion ("GCS=14 or other signs of altered mental status"): 5 points, not 10.
    r = evaluate(CALC, ZERO | {"gcs": 14, "other_ams_signs": "present"})
    assert (r["score"], r["category"]) == (5, "ct_recommended")


# --- unknown is not normal ---------------------------------------------------------------------


def test_sparse_note_with_a_severe_mechanism():
    # Triage note: 14-month-old who fell about 1 m from a changing table (more than 0.9 m:
    # severe mechanism), GCS 15, frontal bump. Not documented: other signs of altered mental
    # status, skull palpation, loss of consciousness, whether the child is acting normally.
    # Known points: 1 (mechanism). The two high-risk criteria are open (0 or 5 each), the two
    # intermediate ones too (0 or 1 each): score 1 to 1 + 5 + 5 + 1 + 1 = 13.
    # Observation versus CT at least; CT recommended if either high-risk finding is present.
    # Once one intermediate criterion is present the others cannot change the tier.
    note = {
        "gcs": 15,
        "severe_mechanism_under2": "present",
        "nonfrontal_scalp_hematoma": "absent",
    }
    r = evaluate(CALC, note)
    assert not r["settled"]
    assert r["score_range"] == [1, 13]
    assert r["possible_categories"] == ["observation_vs_ct", "ct_recommended"]
    assert {d["item"] for d in r["decisive_unknowns"]} == {
        "other_ams_signs",
        "palpable_skull_fracture",
    }
    assert r["jointly_relevant_unknowns"] == []
    assert set(r["irrelevant_unknowns"]) == {"loc_5s_or_more", "acting_abnormally"}


def test_one_undocumented_item_keeps_the_rule_from_being_negative():
    # Everything documented as normal except loss of consciousness, which the note does not
    # mention. Score 0 or 1: CT not recommended only if there was no LOC of 5 s or more.
    # Reading the missing item as absent would call the rule negative.
    note = {k: v for k, v in ZERO.items() if k != "loc_5s_or_more"}
    r = evaluate(CALC, note)
    assert not r["settled"]
    assert r["score_range"] == [0, 1]
    assert r["possible_categories"] == ["ct_not_recommended", "observation_vs_ct"]
    assert [d["item"] for d in r["decisive_unknowns"]] == ["loc_5s_or_more"]


def test_settled_by_gcs_14_while_everything_else_is_unknown():
    # GCS 14 alone puts the child in the CT-recommended tier: at least 5 points.
    r = evaluate(CALC, {"gcs": 14})
    assert r["settled"] and r["category"] == "ct_recommended"
    assert r["decisive_unknowns"] == [] and r["jointly_relevant_unknowns"] == []
