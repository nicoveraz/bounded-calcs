"""The spec loader must reject every mistake that would otherwise be a silent wrong answer."""

import copy

import pytest
import yaml

from bounded_calcs import SpecError, parse

BASE = {
    "id": "toy",
    "name": "Toy",
    "citation": "None",
    "items": [
        {"id": "a", "label": "A", "type": "boolean", "kind": "finding"},
        {"id": "b", "label": "B", "type": "numeric", "kind": "measurement", "unit": "mg"},
        {"id": "c", "label": "C", "type": "ordinal", "kind": "finding", "levels": ["low", "high"]},
        {"id": "d", "label": "D", "type": "boolean", "kind": "finding"},
        {"id": "e", "label": "E", "type": "boolean", "kind": "finding"},
    ],
    "components": [
        {"id": "a", "rule": "present", "item": "a", "points": 1},
        {
            "id": "b",
            "rule": "bands",
            "item": "b",
            "bands": [{"gte": 20, "points": 2}, {"gte": 10, "points": 1}, {"points": 0}],
        },
        {"id": "c", "rule": "levels", "item": "c", "points": {"low": 0, "high": 1}},
        {
            "id": "de",
            "rule": "count",
            "items": ["d", "e"],
            "points": [{"gte": 2, "points": 2}, {"gte": 1, "points": 1}, {"points": 0}],
        },
    ],
    "categories": [{"name": "low"}, {"name": "high", "min": 2}],
}


def broken(fn):
    d = copy.deepcopy(BASE)
    fn(d)
    return d


def test_base_parses():
    assert parse(copy.deepcopy(BASE)).id == "toy"


def swap(lst, i, j):
    lst[i], lst[j] = lst[j], lst[i]


MISTAKES = {
    "item used by two components": lambda d: d["components"].append(
        {"id": "a2", "rule": "present", "item": "a", "points": 1}
    ),
    "item used by no component": lambda d: d["components"].pop(0),
    "unknown item type": lambda d: d["items"][0].update(type="weird"),
    "unknown item kind": lambda d: d["items"][0].update(kind="guess"),
    "numeric item without unit": lambda d: d["items"][1].pop("unit"),
    "unit on a non-numeric item": lambda d: d["items"][0].update(unit="mg"),
    "ordinal item without levels": lambda d: d["items"][2].pop("levels"),
    "duplicate levels": lambda d: d["items"][2].update(levels=["low", "low"]),
    "level named unknown": lambda d: d["items"][2].update(levels=["low", "unknown"]),
    "level YAML read as a boolean": lambda d: d["items"][2].update(levels=[False, "high"]),
    "level points missing a level": lambda d: d["components"][2].update(points={"low": 0}),
    "no default band": lambda d: d["components"][1]["bands"].pop(),
    "bands in the wrong order": lambda d: swap(d["components"][1]["bands"], 0, 1),
    "count thresholds in the wrong order": lambda d: swap(d["components"][3]["points"], 0, 1),
    "count threshold above the number of items": lambda d: d["components"][3]["points"][0].update(
        gte=3
    ),
    "count threshold not gte": lambda d: d["components"][3]["points"][0].update(gt=1),
    "override without points": lambda d: d["components"][3].update(override="a"),
    "categories not ascending": lambda d: d["categories"].append({"name": "mid", "min": 1}),
    "first category with a bound": lambda d: d["categories"][0].update(min=0),
    "category with both min and gt": lambda d: d["categories"][1].update(gt=2),
    "category without a bound": lambda d: d["categories"][1].pop("min"),
    "a single category": lambda d: d["categories"].pop(),
    "duplicate category names": lambda d: d["categories"][1].update(name="low"),
    "component pointing at a missing item": lambda d: d["components"][0].update(item="nope"),
    "wrong rule for the item type": lambda d: d["components"][0].update(rule="levels"),
    "misspelled key in an item": lambda d: d["items"][0].update(questions="Is A present?"),
    "misspelled key in a component": lambda d: d["components"][0].update(point=1),
    "misspelled key in a band": lambda d: d["components"][1]["bands"][0].update(ge=20),
    "misspelled key in a category": lambda d: d["categories"][1].update(minimum=2),
    "misspelled top-level key": lambda d: d.update(reference=["x"]),
    "id not snake_case": lambda d: d.update(id="CHA2DS2-VASc"),
    "item id not snake_case": lambda d: d["items"][0].update(id="Item A"),
    "points that are not halves": lambda d: d["components"][0].update(points=0.3),
    "points as text": lambda d: d["components"][0].update(points="1"),
    "threshold as text": lambda d: d["components"][1]["bands"][0].update(gte="20"),
    "version not a whole number": lambda d: d.update(version="1.0"),
    "higher_is_higher_risk not a boolean": lambda d: d.update(higher_is_higher_risk="no"),
    "note YAML read as a mapping": lambda d: d.update(notes=[{"TODO(physician-review)": "x"}]),
    "empty label": lambda d: d["items"][0].update(label=" "),
    "normal range on a boolean item": lambda d: d["items"][0].update(normal=[0, 1]),
    "normal range that is not a pair": lambda d: d["items"][1].update(normal=[5]),
    "normal range reversed": lambda d: d["items"][1].update(normal=[9, 5]),
    "normal range as text": lambda d: d["items"][1].update(normal=["5", "9"]),
    "accepted range on a boolean item": lambda d: d["items"][0].update(accepts=[0, 1]),
    "accepted range reversed": lambda d: d["items"][1].update(accepts=[30, 5]),
    "accepted range that is not a pair": lambda d: d["items"][1].update(accepts=[5]),
    "normal range outside the accepted range": lambda d: d["items"][1].update(
        normal=[10, 19], accepts=[12, 40]
    ),
    "threshold outside the accepted range": lambda d: d["items"][1].update(accepts=[0, 15]),
    "units on a boolean item": lambda d: d["items"][0].update(units={"x": {"multiply_by": 2}}),
    "units that are not a mapping": lambda d: d["items"][1].update(units=["x"]),
    "units left empty": lambda d: d["items"][1].update(units={}),
    "unit with no factor": lambda d: d["items"][1].update(units={"x": {}}),
    "unit with two factors": lambda d: d["items"][1].update(
        units={"x": {"multiply_by": 2, "divide_by": 2}}
    ),
    "unit factor of zero": lambda d: d["items"][1].update(units={"x": {"divide_by": 0}}),
    "unit factor below zero": lambda d: d["items"][1].update(units={"x": {"multiply_by": -1}}),
    "unit factor as text": lambda d: d["items"][1].update(units={"x": {"multiply_by": "2"}}),
    "unit with a misspelled key": lambda d: d["items"][1].update(units={"x": {"times": 2}}),
    "category on a group no component has": lambda d: d["categories"][1].update(group="g"),
    "group name not snake_case": lambda d: d["components"][0].update(group="High risk"),
    "first category with a group": lambda d: (
        d["components"][0].update(group="g"),
        d["categories"][0].update(group="g"),
    ),
}


@pytest.mark.parametrize("name", list(MISTAKES))
def test_mistake_is_rejected(name):
    with pytest.raises(SpecError):
        parse(broken(MISTAKES[name]))


def test_normal_range_inside_one_band_is_accepted():
    calc = parse(broken(lambda d: d["items"][1].update(normal=[10, 19.9])))
    assert calc.items["b"].normal == (10, 19.9)


def test_normal_range_may_cross_a_threshold():
    # A range across a threshold narrows the item's points instead of deciding them.
    calc = parse(broken(lambda d: d["items"][1].update(normal=[5, 15])))
    assert calc.items["b"].normal == (5, 15)


def test_band_order_error_explains_the_fix():
    with pytest.raises(SpecError, match="most extreme threshold first"):
        parse(broken(lambda d: swap(d["components"][1]["bands"], 0, 1)))


def test_unquoted_note_with_a_colon_is_caught():
    # YAML turns "- TODO(physician-review): text" into a mapping unless it is quoted.
    text = yaml.safe_dump(BASE) + "notes:\n  - TODO(physician-review): which threshold\n"
    with pytest.raises(SpecError, match="double quotes"):
        parse(yaml.safe_load(text))
    quoted = yaml.safe_dump(BASE) + 'notes:\n  - "TODO(physician-review): which threshold"\n'
    assert parse(yaml.safe_load(quoted)).notes == ("TODO(physician-review): which threshold",)


ANY_OF = {
    "id": "anytoy",
    "name": "Any",
    "citation": "None",
    "items": [
        {"id": "x", "label": "X", "type": "numeric", "kind": "measurement", "unit": "u"},
        {"id": "y", "label": "Y", "type": "boolean", "kind": "finding"},
    ],
    "components": [
        {
            "id": "c",
            "rule": "any_of",
            "points": 1,
            "conditions": [{"item": "x", "lt": 5}, {"item": "y"}],
        }
    ],
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
        lambda d: d["components"][0]["conditions"][0].update(points=1),  # unknown key
    ],
)
def test_invalid_any_of_rejected(fn):
    d = copy.deepcopy(ANY_OF)
    fn(d)
    with pytest.raises(SpecError):
        parse(d)


def test_groups_parse_and_bounds_ascend_per_group():
    d = broken(lambda d: d["components"][0].update(group="g"))
    d["categories"] = [{"name": "low"}, {"name": "mid", "min": 2}, {"name": "top", "group": "g", "min": 1}]
    calc = parse(d)
    assert calc.groups == ("g",) and calc.categories[2].on == "g"
    assert calc.category(5, [0]).name == "mid" and calc.category(1, [1]).name == "top"
    # Two bounds on the same group must ascend, like two bounds on the total.
    d["categories"] = [{"name": "low"}, {"name": "a", "group": "g", "min": 1},
                       {"name": "b", "group": "g", "min": 1}]  # fmt: skip
    with pytest.raises(SpecError, match="ascending"):
        parse(d)


def test_bare_on_is_not_a_key():
    # YAML reads a bare `on` as true, so the category key is `group`.
    text = yaml.safe_dump(BASE).replace("min: 2", "min: 2\n  on: g")
    with pytest.raises(SpecError, match="unknown key"):
        parse(yaml.safe_load(text))


def test_accepted_range_parses():
    calc = parse(broken(lambda d: d["items"][1].update(accepts=[0, 40], normal=[10, 19])))
    assert calc.items["b"].accepts == (0, 40)


def test_units_parse_as_factors_to_the_item_unit():
    calc = parse(
        broken(
            lambda d: d["items"][1].update(units={"x": {"multiply_by": 4}, "y": {"divide_by": 4}})
        )
    )
    assert calc.items["b"].units == {"x": 4, "y": 0.25}


def test_a_unit_cannot_repeat_the_item_unit_or_another_unit():
    unit = BASE["items"][1]["unit"]
    for units in ({unit: {"multiply_by": 2}}, {"x": {"multiply_by": 2}, "X": {"divide_by": 2}}):
        with pytest.raises(SpecError):
            parse(broken(lambda d: d["items"][1].update(units=units)))


def test_categories_may_be_left_out_for_a_score_only_calculator():
    calc = parse(broken(lambda d: d.pop("categories")))
    assert calc.categories == ()
    with pytest.raises(ValueError, match="score-only"):
        calc.category(1)
    with pytest.raises(SpecError, match="non-empty list"):  # left out, not left empty
        parse(broken(lambda d: d.update(categories=[])))


def test_a_unit_may_carry_a_label():
    calc = parse(
        broken(
            lambda d: d["items"][1].update(units={"x": {"multiply_by": 4, "label": "x per litre"}})
        )
    )
    assert calc.items["b"].units == {"x": 4} and calc.items["b"].unit_labels == {"x": "x per litre"}
    with pytest.raises(SpecError):  # a label does not replace the factor
        parse(broken(lambda d: d["items"][1].update(units={"x": {"label": "x per litre"}})))


# --- a damaged spec is always a SpecError, never a crash ---------------------------------------


def test_values_of_the_wrong_shape_are_spec_errors_not_crashes():
    # A mapping where a word is expected used to raise TypeError (it cannot be looked up in a
    # set); an item with 'accepts' that no component uses used to raise StopIteration.
    for change in (
        lambda d: d["items"][0].update(type={"a": 1}),
        lambda d: d["items"][0].update(kind=["finding"]),
        lambda d: d["components"][0].update(rule={"a": 1}),
        lambda d: d["components"][0].update(item=["a"]),
        lambda d: d["categories"][1].update(group=["g"]),
        lambda d: d["items"].append(
            {"id": "spare", "label": "spare", "type": "numeric", "kind": "measurement",
             "unit": "x", "accepts": [0, 1]}
        ),
    ):  # fmt: skip
        with pytest.raises(SpecError):
            parse(broken(change))


def test_randomly_damaged_builtin_specs_fail_cleanly():
    import copy
    import random
    from importlib import resources

    import yaml

    docs = [
        yaml.safe_load(f.read_text(encoding="utf-8"))
        for f in resources.files("bounded_calcs.specs").iterdir()
        if f.name.endswith(".yaml")
    ]
    junk = [None, True, 0, -1, 2.5, "x", "", [], {}, ["a"], {"a": 1}, "unknown"]
    rng = random.Random(11)

    def paths(d, pre=()):
        if isinstance(d, dict):
            keys = list(d)
        elif isinstance(d, list):
            keys = list(range(len(d)))
        else:
            return []
        return [p for k in keys for p in ([pre + (k,)] + paths(d[k], pre + (k,)))]

    for _ in range(600):
        d = copy.deepcopy(rng.choice(docs))
        path = rng.choice(paths(d))
        cur = d
        for k in path[:-1]:
            cur = cur[k]
        if rng.random() < 0.3:
            del cur[path[-1]]
        else:
            cur[path[-1]] = copy.deepcopy(rng.choice(junk))
        try:
            parse(d)
        except SpecError:
            pass  # the only acceptable failure; any other exception fails this test


# --- a category nothing can reach -------------------------------------------------------------


def test_a_category_that_can_never_be_reached_is_refused():
    top = len(BASE["categories"]) - 1
    with pytest.raises(SpecError, match="can never be reached"):
        parse(broken(lambda d: d["categories"][top].update(min=1000)))
    try:
        parse(broken(lambda d: d["categories"][top].update(min=1000)))
    except SpecError as e:  # the message names the category and the real score range
        assert BASE["categories"][top]["name"] in str(e) and "The score can be anything from" in str(e)


# --- built-in specs are read once --------------------------------------------------------------


def test_load_builtin_reads_the_files_once_and_returns_a_new_dictionary():
    from bounded_calcs import load_builtin

    first, second = load_builtin(), load_builtin()
    assert first is not second and first == second
    assert all(first[k] is second[k] for k in first)
    first.pop(next(iter(first)))  # a caller changing its dictionary does not affect others
    assert len(load_builtin()) == len(second)
