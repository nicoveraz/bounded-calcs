"""Parkland formula: independent reference and worked examples.

Source: Baxter CR, Shires T. Ann N Y Acad Sci 1968;150(3):874-894, PMID 4973463 [P]. The
reference is written from the sentence that states the volume: 4 cc of lactated Ringer's per
percent burn per kg of body weight, given in 24 hours. The result is a volume, with no
categories. It is deliberately not derived from the YAML spec.
"""

import pytest

from bounded_calcs import InputError, evaluate, load_builtin
from bounded_calcs.testing import assert_matches_reference

CALC = load_builtin()["parkland"]


def reference(v):
    return round(4 * v["weight"] * v["tbsa_burned"]), None


def test_matches_reference():
    assert_matches_reference(CALC, reference)


@pytest.mark.parametrize(
    "weight,tbsa,volume",
    [
        (70, 40, 11200),  # 4 x 70 x 40
        (80, 30, 9600),  # 4 x 80 x 30
        (55, 85, 18700),  # 4 x 55 x 85
        (70, 0, 0),
    ],
)
def test_worked_values(weight, tbsa, volume):
    r = evaluate(CALC, {"weight": weight, "tbsa_burned": tbsa})
    assert r["settled"] and r["score"] == volume and r["category"] is None


def test_weight_in_pounds_is_converted():
    # 150 lb x 0.45359237 = 68.04 kg; 4 x 68.04 x 40 = 10 886 mL. Read as kg, 150 would give
    # 24 000 mL, more than twice as much.
    r = evaluate(CALC, {"weight": {"value": 150, "unit": "lb"}, "tbsa_burned": 40})
    assert r["score"] == 10886
    assert r["converted"]["weight"]["unit"] == "kg"


def test_an_estimated_weight_gives_a_range_of_volumes():
    # Weight estimated at 60 to 80 kg, 40% burned: 9600 to 12 800 mL.
    r = evaluate(CALC, {"weight": {"min": 60, "max": 80}, "tbsa_burned": 40})
    assert not r["settled"] and r["score"] is None and r["score_range"] == [9600, 12800]


def test_impossible_inputs_are_refused():
    with pytest.raises(InputError, match="outside the values this calculator accepts"):
        evaluate(CALC, {"weight": 70, "tbsa_burned": 140})
