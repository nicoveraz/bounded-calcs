"""ROX index: independent reference and worked examples.

Sources: Roca O et al. J Crit Care 2016;35:200-205, PMID 27481760 [P], and Roca O et al. Am J
Respir Crit Care Med 2019;199(11):1368-1376, PMID 30576221 [P]. The reference is written from
the definition in both: the ratio of SpO2/FiO2 to respiratory rate, with SpO2 in % and FiO2
as a fraction. The cut-offs depend on the time point, so the calculator has no categories and
the reference returns the index alone. It is deliberately not derived from the YAML spec.
"""

import pytest

from bounded_calcs import InputError, evaluate, load_builtin
from bounded_calcs.testing import assert_matches_reference

CALC = load_builtin()["rox"]


def reference(v):
    return round(v["spo2_on_oxygen"] / v["fio2"] / v["resp_rate"], 2), None


def test_matches_reference():
    assert_matches_reference(CALC, reference)


@pytest.mark.parametrize(
    "spo2,fio2,rr,rox",
    [
        (95, 0.5, 25, 7.6),  # 95 / 0.5 = 190; 190 / 25 = 7.6
        (90, 1.0, 30, 3.0),  # 90 / 1 = 90; 90 / 30 = 3
        (92, 0.6, 32, 4.79),  # 92 / 0.6 = 153.33; / 32 = 4.7917
        (96, 0.4, 20, 12.0),  # 96 / 0.4 = 240; / 20 = 12
    ],
)
def test_worked_values(spo2, fio2, rr, rox):
    r = evaluate(CALC, {"spo2_on_oxygen": spo2, "fio2": fio2, "resp_rate": rr})
    assert r["settled"] and r["score"] == rox and r["category"] is None


def test_fio2_as_a_percentage_needs_its_unit():
    values = {"spo2_on_oxygen": 95, "resp_rate": 25}
    # 50 percent is 0.5: the same 7.6.
    assert evaluate(CALC, values | {"fio2": {"value": 50, "unit": "percent"}})["score"] == 7.6
    # 50 sent alone would be a fraction of 50: refused, not scored.
    with pytest.raises(InputError, match="outside the values this calculator accepts"):
        evaluate(CALC, values | {"fio2": 50})


def test_unknown_respiratory_rate_gives_a_range():
    # 95 / 0.5 = 190. Respiratory rate anywhere from 4 to 60: 190 / 60 = 3.17 up to 190 / 4 =
    # 47.5. That range spans every published cut-off, so the rate has to be asked for.
    r = evaluate(CALC, {"spo2_on_oxygen": 95, "fio2": 0.5})
    assert not r["settled"] and r["score_range"] == [3.17, 47.5]
    assert [d["item"] for d in r["decisive_unknowns"]] == ["resp_rate"]


def test_a_rate_known_only_as_over_30_bounds_the_index_from_above():
    # Rate over 30: at most 190 / 30 = 6.33, at least 190 / 60 = 3.17.
    r = evaluate(CALC, {"spo2_on_oxygen": 95, "fio2": 0.5, "resp_rate": {"min": 30}})
    assert r["score_range"] == [3.17, 6.33]
