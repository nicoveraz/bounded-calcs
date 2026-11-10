"""The reference check must have teeth: wrong specs and wrong references have to fail."""

import copy

import pytest

from bounded_calcs import parse
from bounded_calcs.testing import assert_matches_reference, complete_inputs, item_values

SPEC = {
    "id": "toy",
    "name": "Toy",
    "citation": "None",
    "items": [
        {"id": "a", "label": "A", "type": "boolean", "kind": "finding"},
        {"id": "age", "label": "Age", "type": "numeric", "kind": "measurement", "unit": "years"},
    ],
    "components": [
        {"id": "a", "rule": "present", "item": "a", "points": 2},
        {
            "id": "age",
            "rule": "bands",
            "item": "age",
            "bands": [{"gte": 65, "points": 2}, {"gte": 45, "points": 1}, {"points": 0}],
        },
    ],
    "categories": [{"name": "low"}, {"name": "high", "min": 3}],
}


def reference(v):
    s = 2 * v["a"] + (2 if v["age"] >= 65 else 1 if v["age"] >= 45 else 0)
    return s, "high" if s >= 3 else "low"


def test_correct_spec_passes():
    counts = assert_matches_reference(parse(copy.deepcopy(SPEC)), reference)
    assert counts["complete_inputs"] == 2 * len(item_values(parse(copy.deepcopy(SPEC)), "age"))


def wrong_points(d):
    d["components"][0]["points"] = 1


def strict_instead_of_inclusive(d):
    band = d["components"][1]["bands"][0]
    del band["gte"]
    band["gt"] = 65


def wrong_band_points(d):
    d["components"][1]["bands"][1]["points"] = 2


def wrong_cut_off(d):
    d["categories"][1]["min"] = 4


@pytest.mark.parametrize(
    "break_spec", [wrong_points, strict_instead_of_inclusive, wrong_band_points, wrong_cut_off]
)
def test_wrong_spec_fails(break_spec):
    d = copy.deepcopy(SPEC)
    break_spec(d)
    with pytest.raises(AssertionError, match="disagree"):
        assert_matches_reference(parse(d), reference)


def test_wrong_reference_fails():
    def off_by_one(v):
        s = 2 * v["a"] + (2 if v["age"] > 65 else 1 if v["age"] >= 45 else 0)
        return s, "high" if s >= 3 else "low"

    with pytest.raises(AssertionError, match="disagree"):
        assert_matches_reference(parse(copy.deepcopy(SPEC)), off_by_one)


def test_reference_must_return_a_known_category():
    with pytest.raises(AssertionError, match="must return"):
        assert_matches_reference(parse(copy.deepcopy(SPEC)), lambda v: (0, "medium"))


def test_category_nothing_reaches_fails_even_if_both_sides_agree():
    d = copy.deepcopy(SPEC)
    d["categories"][1]["min"] = 5  # the maximum score is 4

    def agrees(v):
        return reference(v)[0], "low"

    with pytest.raises(AssertionError, match="ever reaches"):
        assert_matches_reference(parse(d), agrees)


def test_extra_values_only_for_numeric_items():
    calc = parse(copy.deepcopy(SPEC))
    assert 50.0 in item_values(calc, "age", [50])
    with pytest.raises(ValueError):
        assert_matches_reference(calc, reference, {"a": [1]})


def test_large_input_spaces_are_sampled():
    calc = parse(copy.deepcopy(SPEC))
    assert len(list(complete_inputs(calc, limit=5))) == 5
