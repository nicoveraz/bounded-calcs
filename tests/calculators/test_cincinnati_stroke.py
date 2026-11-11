"""Cincinnati Prehospital Stroke Scale: independent reference and examples.

Source: Kothari RU et al. Ann Emerg Med 1999;33(4):373-378, PMID 10092713, figure [P]. The
reference is written from the figure: three items (facial droop, arm drift, speech), each
normal or abnormal; the result is the number of abnormal items. The parts read name no
categories, so it returns the score alone. It is deliberately not derived from the YAML spec.
"""

import pytest

from bounded_calcs import evaluate, load_builtin
from bounded_calcs.testing import assert_matches_reference

CALC = load_builtin()["cincinnati_stroke"]

ITEMS = ["facial_droop", "arm_drift", "abnormal_speech"]
ZERO = {k: "absent" for k in ITEMS}


def reference(v):
    return sum(v[k] for k in ITEMS), None


def test_matches_reference():
    assert_matches_reference(CALC, reference)


@pytest.mark.parametrize("item", ITEMS)
def test_each_abnormal_item_is_one_point(item):
    r = evaluate(CALC, ZERO | {item: "present"})
    assert r["settled"] and r["score"] == 1 and r["category"] is None


def test_all_three_abnormal():
    assert evaluate(CALC, {k: "present" for k in ITEMS})["score"] == 3


def test_an_item_not_examined_is_not_normal():
    # Speech slurred, face symmetric, arms not tested (patient restrained): 1 or 2.
    r = evaluate(CALC, {"abnormal_speech": "present", "facial_droop": "absent"})
    assert not r["settled"] and r["score_range"] == [1, 2]
    assert [d["item"] for d in r["decisive_unknowns"]] == ["arm_drift"]
