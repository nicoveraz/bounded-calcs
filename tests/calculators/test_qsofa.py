"""qSOFA: independent reference, threshold cases and clinical examples.

Sources: Singer M et al. (Sepsis-3). JAMA 2016;315(8):801-810. PMID 26903338 (full text,
PMC4968574); Seymour CW et al. JAMA 2016;315(8):762-774. PMID 26903335 (abstract).
The reference is written from the Sepsis-3 criteria: respiratory rate of 22/min or greater,
altered mentation, systolic blood pressure of 100 mm Hg or less; positive with at least 2.
It is deliberately not derived from the YAML spec.
"""

import pytest

from bounded_calcs import evaluate, load_builtin
from bounded_calcs.testing import assert_matches_reference

CALC = load_builtin()["qsofa"]

# No criterion met: score 0.
ZERO = {"resp_rate": 16, "altered_mentation": "absent", "sbp": 120}


def reference(v):
    score = (v["resp_rate"] >= 22) + v["altered_mentation"] + (v["sbp"] <= 100)
    return score, "positive" if score >= 2 else "negative"


def test_matches_reference():
    assert_matches_reference(CALC, reference)


# --- thresholds, from the source's own numbers ------------------------------------------------


@pytest.mark.parametrize(
    "change,points",
    [
        ({"resp_rate": 21}, 0),  # "respiratory rate of 22/min or greater"
        ({"resp_rate": 22}, 1),
        ({"sbp": 101}, 0),  # "systolic blood pressure of 100 mm Hg or less"
        ({"sbp": 100}, 1),
        ({"altered_mentation": "present"}, 1),
    ],
)
def test_thresholds(change, points):
    assert evaluate(CALC, ZERO | change)["score"] == points


@pytest.mark.parametrize(
    "met,category",
    [
        ([], "negative"),
        (["resp_rate"], "negative"),
        (["resp_rate", "sbp"], "positive"),  # "at least 2 of the following"
        (["resp_rate", "sbp", "altered_mentation"], "positive"),
    ],
)
def test_categories(met, category):
    values = dict(ZERO)
    if "resp_rate" in met:
        values["resp_rate"] = 24
    if "sbp" in met:
        values["sbp"] = 95
    if "altered_mentation" in met:
        values["altered_mentation"] = "present"
    r = evaluate(CALC, values)
    assert (r["score"], r["category"]) == (len(met), category)


# --- unknown is not normal ---------------------------------------------------------------------


def test_sparse_note_is_not_settled():
    # Only the respiratory rate is documented (24/min: 1 point). Blood pressure and mental
    # status are not mentioned, so the score is 1 to 3: negative or positive. Either unknown
    # settles it if present (2 points, positive); absent leaves the other one open.
    r = evaluate(CALC, {"resp_rate": 24})
    assert not r["settled"]
    assert r["score_range"] == [1, 3]
    assert r["possible_categories"] == ["negative", "positive"]
    assert {d["item"] for d in r["decisive_unknowns"]} == {"altered_mentation", "sbp"}


def test_two_criteria_settle_it_whatever_the_third():
    # RR 24 (1) and SBP 90 (1): 2 points already, so mentation cannot change the category.
    r = evaluate(CALC, {"resp_rate": 24, "sbp": 90})
    assert r["settled"] and r["category"] == "positive"
    assert r["irrelevant_unknowns"] == ["altered_mentation"]


def test_vital_signs_described_only_as_normal():
    # "Vital signs normal, GCS 15": respiratory rate 12-20 and SBP 101-139 score 0, so the
    # score is 0 and the result is negative without asking anything.
    r = evaluate(CALC, {"resp_rate": "normal", "sbp": "normal", "altered_mentation": "absent"})
    assert r["settled"] and (r["score"], r["category"]) == (0, "negative")
    assert set(r["normal_assumed"]) == {"resp_rate", "sbp"}
