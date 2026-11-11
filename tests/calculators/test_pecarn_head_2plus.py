"""PECARN head injury rule, 2 years and older: independent reference, thresholds, examples.

Source: Kuppermann N et al. Lancet 2009;374(9696):1160-1170, PMID 19758692, figure 3B [P]
(definitions from figure 2B, panel 1 and methods). The reference is written from figure 3B:
CT recommended if GCS 14 or other signs of altered mental status, or signs of basilar skull
fracture; otherwise observation versus CT if history of loss of consciousness, history of
vomiting, severe mechanism, or severe headache; otherwise CT not recommended. The score is the number
of criteria present; the category depends on the tier, not on the score. It is deliberately
not derived from the YAML spec.
"""

import pytest

from bounded_calcs import evaluate, load_builtin
from bounded_calcs.testing import assert_matches_reference

CALC = load_builtin()["pecarn_head_2plus"]

INTERMEDIATE = [
    "loss_of_consciousness",
    "vomiting",
    "severe_mechanism_2plus",
    "severe_headache",
]

# No predictor present: GCS 15 and every finding absent. Score 0, CT not recommended.
ZERO = {
    "gcs": 15,
    "other_ams_signs": "absent",
    "basilar_skull_fracture_signs": "absent",
} | {k: "absent" for k in INTERMEDIATE}


def reference(v):
    altered_mental_status = v["gcs"] < 15 or v["other_ams_signs"]  # "GCS=14 or other signs"
    high = [altered_mental_status, v["basilar_skull_fracture_signs"]]
    intermediate = [v[k] for k in INTERMEDIATE]
    score = sum(map(bool, high)) + sum(intermediate)  # number of criteria present
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
        (14, "ct_recommended"),  # "GCS=14" (figure 3B); "GCS score lower than 15" (methods)
    ],
)
def test_gcs_threshold(gcs, category):
    assert evaluate(CALC, ZERO | {"gcs": gcs})["category"] == category


@pytest.mark.parametrize("item", ["other_ams_signs", "basilar_skull_fracture_signs"])
def test_each_high_risk_criterion_recommends_ct(item):
    r = evaluate(CALC, ZERO | {item: "present"})
    assert (r["score"], r["category"]) == (1, "ct_recommended")


@pytest.mark.parametrize("item", INTERMEDIATE)
def test_each_intermediate_criterion_means_observation_versus_ct(item):
    r = evaluate(CALC, ZERO | {item: "present"})
    assert (r["score"], r["category"]) == (1, "observation_vs_ct")


def test_all_intermediate_criteria_stay_below_ct_recommended():
    # Four intermediate criteria: 4 points, still observation versus CT.
    r = evaluate(CALC, ZERO | {k: "present" for k in INTERMEDIATE})
    assert (r["score"], r["category"]) == (4, "observation_vs_ct")


# --- unknown is not normal ---------------------------------------------------------------------


def test_sparse_note_with_vomiting():
    # Triage note: 8-year-old, helmeted fall from a bicycle with no vehicle involved (not a
    # severe mechanism), GCS 15, vomited once, has a headache of unstated severity. Not
    # documented: other signs of altered mental status, signs of basilar skull fracture, loss
    # of consciousness, headache severity.
    # Known points: 1 (vomiting). High-risk criteria open (0 or 5 each), LOC and severe
    # headache open (0 or 1 each): score 1 to 1 + 1 + 1 + 1 + 1 = 5.
    # Observation versus CT at least; CT recommended if either high-risk finding is present.
    # With vomiting present, LOC and headache severity cannot change the tier.
    note = {"gcs": 15, "vomiting": "present", "severe_mechanism_2plus": "absent"}
    r = evaluate(CALC, note)
    assert not r["settled"]
    assert r["score_range"] == [1, 5]
    assert r["possible_categories"] == ["observation_vs_ct", "ct_recommended"]
    assert {d["item"] for d in r["decisive_unknowns"]} == {
        "other_ams_signs",
        "basilar_skull_fracture_signs",
    }
    assert r["jointly_relevant_unknowns"] == []
    assert set(r["irrelevant_unknowns"]) == {"loss_of_consciousness", "severe_headache"}


def test_gcs_15_does_not_settle_altered_mental_status():
    # GCS 15 with the other signs not documented: the high-risk criterion is still open.
    # Everything else normal: score 0 or 1, CT not recommended or CT recommended.
    note = {k: v for k, v in ZERO.items() if k != "other_ams_signs"}
    r = evaluate(CALC, note)
    assert r["score_range"] == [0, 1]
    assert r["possible_categories"] == ["ct_not_recommended", "ct_recommended"]
    assert [d["item"] for d in r["decisive_unknowns"]] == ["other_ams_signs"]


def test_settled_by_basilar_signs_while_everything_else_is_unknown():
    # Battle's sign alone: CT recommended, whatever else is found.
    r = evaluate(CALC, {"basilar_skull_fracture_signs": "present"})
    assert r["settled"] and r["category"] == "ct_recommended"
    assert r["decisive_unknowns"] == [] and r["jointly_relevant_unknowns"] == []
