"""Wells criteria for DVT (two-tier): independent reference, cut-off cases, clinical examples.

Source: Wells PS et al. N Engl J Med 2003;349(13):1227-1235, PMID 14507948, table 1 [P]
(NICE NG158 table 1 agrees [S]). The reference is written from that table: nine features score
1 point each, "alternative diagnosis at least as likely as deep-vein thrombosis" scores -2; a
score of two or higher means DVT likely, less than two means unlikely. It is deliberately not
derived from the YAML spec.
"""

import pytest

from bounded_calcs import evaluate, load_builtin
from bounded_calcs.testing import assert_matches_reference

CALC = load_builtin()["wells_dvt"]

ONE_POINT = [
    "malignancy",
    "paralysis_or_cast",
    "bedridden_or_major_surgery",
    "deep_vein_tenderness",
    "entire_leg_swollen",
    "calf_swelling_3cm",
    "pitting_edema",
    "collateral_veins",
    "prior_dvt",
]

# Nothing present: score 0.
ZERO = {k: "absent" for k in ONE_POINT} | {"alternative_dx_as_likely": "absent"}


def reference(v):
    score = sum(v[k] for k in ONE_POINT) - 2 * v["alternative_dx_as_likely"]
    return score, "dvt_likely" if score >= 2 else "dvt_unlikely"


def test_matches_reference():
    assert_matches_reference(CALC, reference)


# --- points and cut-off, from the source's own numbers -----------------------------------------


@pytest.mark.parametrize("item", ONE_POINT)
def test_each_feature_scores_one_point(item):
    assert evaluate(CALC, ZERO | {item: "present"})["score"] == 1


def test_alternative_diagnosis_subtracts_two():
    r = evaluate(CALC, ZERO | {"alternative_dx_as_likely": "present"})
    assert (r["score"], r["category"]) == (-2, "dvt_unlikely")


@pytest.mark.parametrize(
    "present,score,category",
    [
        (["entire_leg_swollen"], 1, "dvt_unlikely"),  # "less than two"
        (["entire_leg_swollen", "pitting_edema"], 2, "dvt_likely"),  # "two or higher"
        # 3 features minus 2 for the alternative diagnosis: 1 point, unlikely.
        (["entire_leg_swollen", "pitting_edema", "malignancy", "alternative_dx_as_likely"], 1,
         "dvt_unlikely"),
    ],
)
def test_cut_off(present, score, category):
    r = evaluate(CALC, ZERO | {k: "present" for k in present})
    assert (r["score"], r["category"]) == (score, category)


# --- unknown is not normal ---------------------------------------------------------------------


def test_sparse_note_asks_for_the_judgment_first():
    # The note documents deep vein tenderness and calf swelling of 4 cm (2 points), and no
    # cancer or previous DVT. Five features and the clinician's judgment are not mentioned:
    # the score is 2 - 2 = 0 at least and 2 + 5 = 7 at most, so unlikely or likely.
    # If no alternative diagnosis is as likely, the score is at least 2: likely, settled.
    # No single other feature settles it, but each changes the category in some combination
    # (for example with the alternative diagnosis present and one more feature present).
    note = {
        "deep_vein_tenderness": "present",
        "calf_swelling_3cm": "present",
        "malignancy": "absent",
        "prior_dvt": "absent",
    }
    r = evaluate(CALC, note)
    assert not r["settled"]
    assert r["score_range"] == [0, 7]
    assert r["possible_categories"] == ["dvt_unlikely", "dvt_likely"]
    assert [d["item"] for d in r["decisive_unknowns"]] == ["alternative_dx_as_likely"]
    assert r["judgment_items_pending"] == ["alternative_dx_as_likely"]
    assert set(r["jointly_relevant_unknowns"]) == {
        "paralysis_or_cast",
        "bedridden_or_major_surgery",
        "entire_leg_swollen",
        "pitting_edema",
        "collateral_veins",
    }
    # The common convention (unmentioned = absent, judgment = absent) would answer "likely"
    # here; with the judgment present and nothing else, the truth could be "unlikely".


def test_settled_while_the_judgment_is_unknown():
    # Four features present: at least 4 - 2 = 2 points whatever the judgment, so DVT likely.
    four = ["deep_vein_tenderness", "calf_swelling_3cm", "entire_leg_swollen", "pitting_edema"]
    r = evaluate(CALC, {k: "present" for k in four})
    assert r["settled"] and r["category"] == "dvt_likely"
    assert r["decisive_unknowns"] == [] and r["jointly_relevant_unknowns"] == []
