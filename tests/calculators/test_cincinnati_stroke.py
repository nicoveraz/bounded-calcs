"""Cincinnati Prehospital Stroke Scale: independent reference and examples.

Source: Kothari RU et al. Ann Emerg Med 1999;33(4):373-378, PMID 10092713, figure [P]. The
reference is written from the figure: three items (facial droop, arm drift, speech), each
normal or abnormal; the score is the number of abnormal items; and from the abstract, which
evaluates 'an abnormality in any 1 of the 3 stroke scale items'. It is deliberately not
derived from the YAML spec.
"""

import pytest

from bounded_calcs import evaluate, load_builtin
from bounded_calcs.testing import assert_matches_reference

CALC = load_builtin()["cincinnati_stroke"]

ITEMS = ["facial_droop", "arm_drift", "abnormal_speech"]
ZERO = {k: "absent" for k in ITEMS}


def reference(v):
    score = sum(v[k] for k in ITEMS)
    return score, "any_abnormal" if score else "all_normal"


def test_matches_reference():
    assert_matches_reference(CALC, reference)


@pytest.mark.parametrize("item", ITEMS)
def test_each_abnormal_item_is_one_point(item):
    r = evaluate(CALC, ZERO | {item: "present"})
    assert r["settled"] and r["score"] == 1 and r["category"] == "any_abnormal"


def test_all_normal():
    r = evaluate(CALC, ZERO)
    assert (r["score"], r["category"]) == (0, "all_normal")


def test_all_three_abnormal():
    assert evaluate(CALC, {k: "present" for k in ITEMS})["score"] == 3


def test_an_item_not_examined_is_not_normal():
    # Face symmetric, speech normal, arms not tested (patient restrained): 0 or 1, so the
    # scale cannot be called normal.
    r = evaluate(CALC, {"abnormal_speech": "absent", "facial_droop": "absent"})
    assert not r["settled"] and r["score_range"] == [0, 1]
    assert r["possible_categories"] == ["all_normal", "any_abnormal"]
    assert [d["item"] for d in r["decisive_unknowns"]] == ["arm_drift"]


def test_one_abnormal_item_settles_it():
    # Speech slurred: abnormal whatever the other two show; the score is still 1 to 3.
    r = evaluate(CALC, {"abnormal_speech": "present"})
    assert r["settled"] and r["category"] == "any_abnormal" and r["score_range"] == [1, 3]
