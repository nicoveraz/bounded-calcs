"""PERC rule: independent reference, threshold cases and clinical examples.

Sources: Kline JA et al. J Thromb Haemost 2004;2(8):1247-1255. PMID 15304025;
Kline JA et al. J Thromb Haemost 2008;6(5):772-780. PMID 18318689.
The reference is transcribed from calc-bounds (perc.py). It is deliberately not derived from
the YAML spec. The score is the number of criteria that are NOT met.
"""

import pytest

from bounded_calcs import evaluate, load_builtin
from bounded_calcs.testing import assert_matches_reference

CALC = load_builtin()["perc"]

# All eight criteria met: PERC negative.
ZERO = {
    "age": 35,
    "heart_rate": 88,
    "spo2": 98,
    "unilateral_leg_swelling": "absent",
    "hemoptysis": "absent",
    "recent_surgery_trauma": "absent",
    "prior_vte": "absent",
    "hormone_use": "absent",
}


def reference(v):
    failed = (
        (v["age"] >= 50)
        + (v["heart_rate"] >= 100)
        + (v["spo2"] < 95)
        + v["unilateral_leg_swelling"]
        + v["hemoptysis"]
        + v["recent_surgery_trauma"]
        + v["prior_vte"]
        + v["hormone_use"]
    )
    return failed, "negative" if failed == 0 else "positive"


def test_matches_reference():
    assert_matches_reference(CALC, reference)


# --- thresholds, from the source's own numbers ------------------------------------------------


def test_all_criteria_met_is_negative():
    r = evaluate(CALC, ZERO)
    assert (r["score"], r["category"]) == (0, "negative")


@pytest.mark.parametrize(
    "change,category",
    [
        ({"age": 49}, "negative"),  # age < 50
        ({"age": 50}, "positive"),
        ({"heart_rate": 99}, "negative"),  # pulse < 100
        ({"heart_rate": 100}, "positive"),
        ({"spo2": 95}, "negative"),  # SaO2 >= 95%
        ({"spo2": 94.9}, "positive"),
        ({"hormone_use": "present"}, "positive"),
    ],
)
def test_thresholds(change, category):
    assert evaluate(CALC, ZERO | change)["category"] == category


# --- unknown is not normal ---------------------------------------------------------------------


def test_negative_needs_every_criterion_documented():
    # A note silent on hormone use cannot be called PERC negative.
    r = evaluate(CALC, {k: v for k, v in ZERO.items() if k != "hormone_use"})
    assert not r["settled"]
    assert r["possible_categories"] == ["negative", "positive"]
    assert [d["item"] for d in r["decisive_unknowns"]] == ["hormone_use"]


def test_one_failed_criterion_settles_it():
    r = evaluate(CALC, {"age": 62})
    assert r["settled"] and r["category"] == "positive"
    assert r["decisive_unknowns"] == []
