"""NEXUS cervical spine criteria: independent reference and clinical examples.

Source: Hoffman JR et al. N Engl J Med 2000;343(2):94-99, PMID 10891516, methods [P]. The
reference is written from the paper's list: a patient has a low probability of injury only
with no posterior midline cervical tenderness, no focal neurologic deficit, a normal level of
alertness, no evidence of intoxication and no painful, distracting injury. The score is the
number of criteria not met. It is deliberately not derived from the YAML spec.
"""

import pytest

from bounded_calcs import evaluate, load_builtin
from bounded_calcs.testing import assert_matches_reference

CALC = load_builtin()["nexus"]

CRITERIA = [
    "midline_cervical_tenderness",
    "focal_neuro_deficit",
    "abnormal_alertness",
    "intoxication",
    "distracting_injury",
]

# All five criteria met: nothing present.
ZERO = {k: "absent" for k in CRITERIA}


def reference(v):
    not_met = sum(v[k] for k in CRITERIA)
    return not_met, "negative" if not_met == 0 else "positive"


def test_matches_reference():
    assert_matches_reference(CALC, reference)


def test_all_five_criteria_met_is_negative():
    r = evaluate(CALC, ZERO)
    assert (r["score"], r["category"]) == (0, "negative")


@pytest.mark.parametrize("item", CRITERIA)
def test_any_single_criterion_not_met_is_positive(item):
    r = evaluate(CALC, ZERO | {item: "present"})
    assert (r["score"], r["category"]) == (1, "positive")


# --- unknown is not normal ---------------------------------------------------------------------


def test_note_cannot_clear_the_neck_without_the_clinician():
    # Triage note after a low-speed collision: "no midline tenderness, neuro intact". Nothing
    # about alertness, intoxication or other injuries. Known: 0 points. Three criteria open:
    # score 0 to 3, negative or positive. Each open item can make it positive, none can make
    # it negative alone, and all three need the clinician.
    note = {"midline_cervical_tenderness": "absent", "focal_neuro_deficit": "absent"}
    r = evaluate(CALC, note)
    assert not r["settled"]
    assert r["score_range"] == [0, 3]
    assert r["possible_categories"] == ["negative", "positive"]
    assert {d["item"] for d in r["decisive_unknowns"]} == {
        "abnormal_alertness",
        "intoxication",
        "distracting_injury",
    }
    assert set(r["judgment_items_pending"]) == {
        "abnormal_alertness",
        "intoxication",
        "distracting_injury",
    }


def test_one_documented_finding_settles_it_positive():
    # Midline tenderness alone: at least 1 point, positive whatever the rest is.
    r = evaluate(CALC, {"midline_cervical_tenderness": "present"})
    assert r["settled"] and r["category"] == "positive"
    assert r["decisive_unknowns"] == []
