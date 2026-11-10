import copy

import pytest

from bounded_calcs import SpecError, parse

BASE = {
    "id": "toy",
    "name": "Toy",
    "citation": "None",
    "items": [
        {"id": "a", "label": "A", "type": "boolean", "kind": "finding"},
        {"id": "b", "label": "B", "type": "numeric", "kind": "measurement", "unit": "mg"},
    ],
    "components": [
        {"id": "a", "rule": "present", "item": "a", "points": 1},
        {"id": "b", "rule": "bands", "item": "b", "bands": [{"gte": 10, "points": 1}, {"points": 0}]},
    ],
    "categories": [{"name": "low"}, {"name": "high", "min": 2}],
}


def mutate(fn):
    d = copy.deepcopy(BASE)
    fn(d)
    return d


def test_base_parses():
    assert parse(copy.deepcopy(BASE)).id == "toy"


@pytest.mark.parametrize(
    "fn",
    [
        lambda d: d["components"].append({"id": "a2", "rule": "present", "item": "a", "points": 1}),
        lambda d: d["components"].pop(),  # item b unused
        lambda d: d["items"][0].update(type="weird"),
        lambda d: d["items"][0].update(kind="guess"),
        lambda d: d["items"][1].pop("unit"),
        lambda d: d["components"][1]["bands"].pop(),  # no default band
        lambda d: d["categories"].append({"name": "mid", "min": 1}),  # not ascending
        lambda d: d["categories"][0].update(min=0),  # first category with a bound
        lambda d: d["categories"][1].update(gt=2),  # both min and gt
        lambda d: d["components"][0].update(item="nope"),
        lambda d: d["components"][0].update(rule="levels"),  # wrong rule for a boolean
    ],
)
def test_invalid_specs_rejected(fn):
    with pytest.raises(SpecError):
        parse(mutate(fn))


ANY_OF = {
    "id": "anytoy", "name": "Any", "citation": "None",
    "items": [
        {"id": "x", "label": "X", "type": "numeric", "kind": "measurement", "unit": "u"},
        {"id": "y", "label": "Y", "type": "boolean", "kind": "finding"},
    ],
    "components": [{"id": "c", "rule": "any_of", "points": 1,
                    "conditions": [{"item": "x", "lt": 5}, {"item": "y"}]}],
    "categories": [{"name": "low"}, {"name": "high", "min": 1}],
}


def test_any_of_parses():
    assert parse(copy.deepcopy(ANY_OF)).components[0].rule == "any_of"


@pytest.mark.parametrize(
    "fn",
    [
        lambda d: d["components"][0]["conditions"][0].pop("lt"),  # numeric without threshold
        lambda d: d["components"][0]["conditions"][1].update(gt=1),  # boolean with threshold
        lambda d: d["components"][0]["conditions"].pop(),  # fewer than two conditions
        lambda d: d["components"][0]["conditions"].append({"item": "y"}),  # repeated item
    ],
)
def test_invalid_any_of_rejected(fn):
    d = copy.deepcopy(ANY_OF)
    fn(d)
    with pytest.raises(SpecError):
        parse(d)
