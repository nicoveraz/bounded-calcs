"""HEART score: independent reference, threshold cases and clinical examples.

Source: Six AJ, Backus BE, Kelder JC. Neth Heart J 2008;16(6):191-196. PMID 18665203, with the
troponin bands and category cut-offs of the validation papers (see heart.yaml).
The reference is transcribed from calc-bounds (heart.py). It is deliberately not derived from
the YAML spec.
"""

import pytest

from bounded_calcs import evaluate, load_builtin
from bounded_calcs.testing import assert_matches_reference

CALC = load_builtin()["heart"]

HISTORY = ["slightly_suspicious", "moderately_suspicious", "highly_suspicious"]
ECG = ["normal", "nonspecific_repolarization", "significant_st_deviation"]
TROPONIN = ["le_normal", "1_to_3x_normal", "gt_3x_normal"]
RISK_FACTORS = [
    "hypertension",
    "hypercholesterolemia",
    "diabetes",
    "obesity",
    "smoking",
    "family_history_cad",
]

# Six 2008 worked example: a 30-year-old man with non-specific pain, a normal ECG, no risk
# factors and a normal troponin scores 0.
ZERO = {
    "heart_history": "slightly_suspicious",
    "heart_ecg": "normal",
    "age": 30,
    **{k: "absent" for k in RISK_FACTORS},
    "atherosclerotic_disease": "absent",
    "heart_troponin": "le_normal",
}


def reference(v):
    age = 2 if v["age"] >= 65 else 1 if v["age"] >= 45 else 0
    n = sum(v[k] for k in RISK_FACTORS)
    risk = 2 if v["atherosclerotic_disease"] or n >= 3 else 1 if n >= 1 else 0
    score = (
        HISTORY.index(v["heart_history"])
        + ECG.index(v["heart_ecg"])
        + age
        + risk
        + TROPONIN.index(v["heart_troponin"])
    )
    return score, "low" if score <= 3 else "moderate" if score <= 6 else "high"


def test_matches_reference():
    assert_matches_reference(CALC, reference)


# --- examples and thresholds, from the source's own numbers -----------------------------------


def test_six_2008_worked_example_scores_zero():
    r = evaluate(CALC, ZERO)
    assert (r["score"], r["category"]) == (0, "low")


@pytest.mark.parametrize("age,points", [(44, 0), (44.9, 0), (45, 1), (64, 1), (65, 2)])
def test_age_bands(age, points):
    assert evaluate(CALC, ZERO | {"age": age})["score"] == points


def test_risk_factor_counts():
    def score(*present):
        return evaluate(CALC, ZERO | {k: "present" for k in present})["score"]

    assert score("hypertension") == 1
    assert score("hypertension", "diabetes") == 1
    assert score("hypertension", "diabetes", "smoking") == 2
    assert score("hypertension", "diabetes", "smoking", "obesity") == 2
    # Atherosclerotic disease scores 2 whatever the other risk factors are.
    assert score("atherosclerotic_disease") == 2
    assert score("atherosclerotic_disease", "hypertension") == 2


def test_categories():
    # H2 E1 A1 (50 years) R1 T0 = 5 -> moderate.
    r = evaluate(
        CALC,
        ZERO
        | {
            "heart_history": "highly_suspicious",
            "heart_ecg": "nonspecific_repolarization",
            "age": 50,
            "diabetes": "present",
        },
    )
    assert (r["score"], r["category"]) == (5, "moderate")
    # H1 E0 A0 R1 T1 = 3 -> low (upper edge); one more point is moderate.
    edge = ZERO | {
        "heart_history": "moderately_suspicious",
        "diabetes": "present",
        "heart_troponin": "1_to_3x_normal",
    }
    assert evaluate(CALC, edge)["category"] == "low"
    assert evaluate(CALC, edge | {"age": 45})["category"] == "moderate"
    # H2 E2 A2 R0 T1 = 7 -> high (lower edge).
    high = ZERO | {
        "heart_history": "highly_suspicious",
        "heart_ecg": "significant_st_deviation",
        "age": 70,
        "heart_troponin": "1_to_3x_normal",
    }
    r = evaluate(CALC, high)
    assert (r["score"], r["category"]) == (7, "high")


# --- unknown is not normal ---------------------------------------------------------------------


def test_known_atherosclerotic_disease_makes_risk_factors_irrelevant():
    known = {k: v for k, v in ZERO.items() if k not in RISK_FACTORS}
    r = evaluate(CALC, known | {"atherosclerotic_disease": "present"})
    assert r["settled"] and r["score"] == 2
    assert set(r["irrelevant_unknowns"]) == set(RISK_FACTORS)


def test_typical_triage_note_is_not_settled():
    # 58 years old, hypertensive smoker, normal ECG. Troponin pending, and the note does not
    # give the clinician's impression of the history or mention the other risk factors.
    r = evaluate(
        CALC,
        {"age": 58, "hypertension": "present", "smoking": "present", "heart_ecg": "normal"},
    )
    assert not r["settled"]
    assert r["score_range"] == [2, 7]
    assert r["possible_categories"] == ["low", "moderate", "high"]
    # Data before judgment when both are equally informative.
    assert [d["item"] for d in r["decisive_unknowns"]] == ["heart_troponin", "heart_history"]
    assert r["judgment_items_pending"] == ["heart_history"]
    # No single remaining risk factor can change the category, but together they move the score.
    assert set(r["jointly_relevant_unknowns"]) == {
        "hypercholesterolemia",
        "diabetes",
        "obesity",
        "family_history_cad",
        "atherosclerotic_disease",
    }
