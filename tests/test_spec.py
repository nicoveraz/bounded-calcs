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
