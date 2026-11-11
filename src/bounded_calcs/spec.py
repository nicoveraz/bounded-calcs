"""Calculator specifications: loading and validation.

A calculator is declared in YAML as a set of *items* (what can be known about the patient)
and a set of *components* (how items turn into points). Every item belongs to exactly one
component, so components are independent and the set of reachable scores is exactly the
sumset of each component's reachable points. That is what makes the bounds exact.

Item types:
  boolean   present / absent / unknown
  ordinal   one of `levels`, or unknown (also used for unordered choices such as sex)
  numeric   a number in `unit`, or unknown

A numeric item may declare `normal: [lo, hi]`: the default range assumed when a source says
only that the value is normal ("vital signs normal"). A site can replace it with its own range
(see `evaluate`). A range inside one band decides the item's points; a range that crosses a
threshold only narrows them, and the item stays a question when it matters.

A numeric item may also declare `accepts: [lo, hi]`: the values this calculator takes. A value
outside it is an input error, never scored and never treated as unknown. It catches unit and
transcription slips (a saturation of 0.97, a urea that was really BUN in mg/dL) and values the
score was not made for (a child's age in an adult score). It belongs to the calculator, so two
calculators may accept different ranges of the same item.

A numeric item may declare `units`: other units a value may arrive in, each with how to turn
it into the item's unit, `{multiply_by: x}` or `{divide_by: x}`. The engine converts; the
caller sends the number as written with its unit. Name the analyte in the unit when the bare
unit is ambiguous (`bun_mg/dL`, `urea_mg/dL`).

Item kinds (who can supply the value):
  finding      can be read from a note or chart
  measurement  a number from the chart (vitals, labs, age)
  judgment     clinician-only; never inferred from a note

Component rules:
  present   {item, points}                      points if the boolean item is present
  absent    {item, points}                      points if the boolean item is absent
                                                (e.g. "absence of cough: 1 point")
  levels    {item, points: {level: points}}     points by ordinal level
  bands     {item, bands: [{gte|gt|lte|lt: x, points}, ..., {points}]}
            first matching band wins; the last band has no condition (default)
  count     {items, points: [{gte: n, points}, ..., {points}],
             override?: item, override_points?: p}
            points by number of present boolean items; if `override` is present the
            component scores `override_points` regardless of the count
  any_of    {conditions: [{item} | {item, gte|gt|lte|lt: x}, ...], points}
            points if any condition is met: a boolean item present, or a numeric item
            meeting its threshold (e.g. CURB-65 "SBP < 90 or DBP <= 60")

Points may be negative. They must be whole or half numbers so that sums stay exact.

Categories are listed from lowest to highest; a patient gets the last one whose condition
holds. A condition is a lower bound (`min` or `gt`) on the total score, or, with
`group: <name>`, on the points of one group of components. A component joins a group with the
same key, `group: <name>`; its points still count in the total. Groups express rules that a
single total cannot:
  tiers          "imaging if any high-risk criterion, else observe if any medium-risk one":
                 the criteria of each tier form a group, and each category names its group
  a cut-off that depends on an item (different thresholds for men and women): the item's
                 component stays outside the group the category names
The first category has no condition.

Formula calculators: instead of `components`, a spec may have a `formula` (an expression on
the items; see `formula.py`). Its numeric items must declare `accepts`, which bounds the
result while an item is unknown. Categories, if any, are cut-offs on the result.

Score-only calculators: `categories` may be left out when the source gives a score and no
decision categories (a severity scale). The result is then the score: it is settled when the
score is exact, and every unknown item that can change the score is a question.

Where things live: the dataclasses a spec loads into are in `model.py`; each rule reads its
own keys in its module under `engine/rules/`; this module reads the rest (items, categories,
the top level) and puts them together.

The loader is deliberately strict: unknown keys, values YAML did not read as text, bands that
can never match and non-exact points are errors, because each of them is a silent wrong
answer otherwise.
"""

from __future__ import annotations

import dataclasses
import math
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

from bounded_calcs._validate import (
    _LEVEL,
    _NOT_TEXT,
    SpecError,
    _list,
    _name,
    _number,
    _only,
    _req,
    _text,
    _texts,
)
from bounded_calcs.engine.rules import RULES, component_keys, parse_component
from bounded_calcs.formula import Formula, FormulaError, parse_formula
from bounded_calcs.model import (
    BAND_OPS,
    ITEM_KINDS,
    ITEM_TYPES,
    Band,
    Calculator,
    Category,
    Component,
    Item,
    band_probes,
)

__all__ = [
    "BAND_OPS",
    "ITEM_KINDS",
    "ITEM_TYPES",
    "RULE_TYPES",
    "Band",
    "Calculator",
    "Category",
    "Component",
    "Item",
    "SpecError",
    "band_probes",
    "load_builtin",
    "load_file",
    "parse",
]

RULE_TYPES = set(RULES)

_TOP_KEYS = {
    "id", "name", "version", "purpose", "citation", "references", "higher_is_higher_risk",
    "notes", "items", "components", "categories", "formula",
}  # fmt: skip
_ITEM_KEYS = {
    "id", "label", "type", "kind", "levels", "unit", "units", "normal", "accepts", "question",
    "notes",
}  # fmt: skip
_CATEGORY_KEYS = {"name", "label", "min", "gt", "group", "meaning"}


# --- items ----------------------------------------------------------------------------------


def _range(raw: dict[str, Any], key: str, where: str, *, may_be_a_point: bool) -> tuple[float, float]:
    """A `[lo, hi]` pair of a numeric item (`normal` or `accepts`)."""
    rng = raw[key]
    if not isinstance(rng, list) or len(rng) != 2:
        raise SpecError(f"{where}: '{key}' must be a list [lo, hi], got {rng!r}")
    lo, hi = (_number(x, where, f"'{key}'") for x in rng)
    if lo > hi or (lo == hi and not may_be_a_point):
        sign = "<=" if may_be_a_point else "<"
        raise SpecError(f"{where}: '{key}' must be [lo, hi] with lo {sign} hi, got {rng!r}")
    return lo, hi


def _units(raw: dict[str, Any], where: str) -> tuple[dict[str, float], dict[str, str]]:
    """The other units of a numeric item: each unit's factor to the item's own unit, and the
    label that says what the unit means."""
    units: dict[str, float] = {}
    labels: dict[str, str] = {}
    if not isinstance(raw["units"], dict) or not raw["units"]:
        raise SpecError(f"{where}: 'units' must map each unit to a conversion")
    for uname, conv in raw["units"].items():
        uw = f"{where} unit {uname!r}"
        if not isinstance(uname, str) or not uname.strip() or uname != uname.strip():
            raise SpecError(f"{uw}: the unit must be text; {_NOT_TEXT}")
        if uname.lower() == str(raw["unit"]).lower() or uname.lower() in {u.lower() for u in units}:
            raise SpecError(f"{uw}: listed twice, or the same as the item's own unit")
        if not isinstance(conv, dict):
            raise SpecError(f"{uw}: needs exactly one of 'multiply_by' or 'divide_by'")
        conv = dict(conv)
        if "label" in conv:  # what the unit means and how a note writes it
            labels[uname] = _text(conv.pop("label"), uw, "label")
        if len(conv) != 1 or next(iter(conv)) not in ("multiply_by", "divide_by"):
            raise SpecError(f"{uw}: needs exactly one of 'multiply_by' or 'divide_by'")
        ((how, amount),) = conv.items()
        amount = _number(amount, uw, f"'{how}'")
        if amount <= 0:
            raise SpecError(f"{uw}: '{how}' must be greater than 0")
        units[uname] = amount if how == "multiply_by" else 1.0 / amount
    return units, labels


def _item(raw: Any, where: str, taken: set[str]) -> Item:
    _only(raw, _ITEM_KEYS, f"{where} item")
    iid = _name(_req(raw, "id", where), f"{where} item", "id")
    iw = f"{where} item '{iid}'"
    if iid in taken:
        raise SpecError(f"{iw}: duplicate id")
    itype = _req(raw, "type", iw)
    kind = _req(raw, "kind", iw)
    if not isinstance(itype, str) or itype not in ITEM_TYPES:
        raise SpecError(f"{iw}: type must be one of {sorted(ITEM_TYPES)}")
    if not isinstance(kind, str) or kind not in ITEM_KINDS:
        raise SpecError(f"{iw}: kind must be one of {sorted(ITEM_KINDS)}")
    numeric = itype == "numeric"

    raw_levels = _list(raw["levels"], iw, "levels") if "levels" in raw else []
    levels = tuple(_name(v, iw, "level", _LEVEL) for v in raw_levels)
    if (itype == "ordinal") != bool(levels):
        raise SpecError(f"{iw}: 'levels' is required for ordinal items and only for them")
    if len(set(levels)) != len(levels):
        raise SpecError(f"{iw}: duplicate levels")
    if "unknown" in levels:
        raise SpecError(f"{iw}: 'unknown' is reserved and cannot be a level")
    if numeric != ("unit" in raw):
        raise SpecError(f"{iw}: 'unit' is required for numeric items and only for them")
    for key in ("normal", "accepts", "units"):
        if key in raw and not numeric:
            raise SpecError(f"{iw}: '{key}' is only for numeric items")

    normal = _range(raw, "normal", iw, may_be_a_point=True) if "normal" in raw else None
    accepts = _range(raw, "accepts", iw, may_be_a_point=False) if "accepts" in raw else None
    if normal and accepts and not (accepts[0] <= normal[0] and normal[1] <= accepts[1]):
        raise SpecError(f"{iw}: the normal range must lie inside 'accepts'")
    units, unit_labels = _units(raw, iw) if "units" in raw else ({}, {})
    return Item(
        id=iid,
        label=_text(_req(raw, "label", iw), iw, "label"),
        type=itype,
        kind=kind,
        levels=levels,
        unit=_text(raw["unit"], iw, "unit") if "unit" in raw else None,
        question=_text(raw["question"], iw, "question") if "question" in raw else None,
        notes=_texts(raw.get("notes", []), iw, "notes"),
        normal=normal,
        accepts=accepts,
        units=units,
        unit_labels=unit_labels,
    )


# --- components -----------------------------------------------------------------------------


def _component(raw: Any, where: str, items: dict[str, Item]) -> Component:
    """One component: the keys every rule shares here, the rule's own in its module."""
    if not isinstance(raw, dict):
        raise SpecError(f"{where}: each component must be a mapping, got {raw!r}")
    comp_id = _name(_req(raw, "id", where), f"{where} component", "id")
    cw = f"{where} component '{comp_id}'"
    rule = _req(raw, "rule", cw)
    if not isinstance(rule, str) or rule not in RULES:
        raise SpecError(f"{cw}: rule must be one of {sorted(RULES)}")
    _only(raw, component_keys(rule), cw)
    label = _text(raw.get("label", comp_id), cw, "label")
    comp = parse_component(raw, cw, comp_id, label, rule, items)
    if "group" in raw:
        comp = dataclasses.replace(comp, group=_name(raw["group"], cw, "group"))
    return comp


def _components(data: dict[str, Any], where: str, items: dict[str, Item]) -> list[Component]:
    components: list[Component] = []
    owner: dict[str, str] = {}
    for raw in _list(_req(data, "components", where), where, "components"):
        comp = _component(raw, where, items)
        cw = f"{where} component '{comp.id}'"
        for iid in comp.items:
            if iid in owner:
                raise SpecError(
                    f"{cw}: item '{iid}' already used by component '{owner[iid]}'; "
                    "components must not share items"
                )
            owner[iid] = comp.id
        if comp.id in {c.id for c in components}:
            raise SpecError(f"{cw}: duplicate component id")
        components.append(comp)

    # A threshold outside what the item accepts could never be reached.
    for item in items.values():
        if item.accepts is None or item.id not in owner:
            continue
        comp = next(c for c in components if item.id in c.items)
        bands = comp.bands if comp.rule == "bands" else (comp.conditions[item.id],)
        for b in bands:
            if b.value is not None and not item.accepts[0] <= b.value <= item.accepts[1]:
                raise SpecError(
                    f"{where} item '{item.id}': threshold {b.value:g} of component '{comp.id}' "
                    f"is outside 'accepts' {list(item.accepts)}"
                )

    unused = set(items) - set(owner)
    if unused:
        raise SpecError(f"{where}: items not used by any component: {sorted(unused)}")
    return components


# --- categories -----------------------------------------------------------------------------


def _categories(data: dict[str, Any], where: str, groups: tuple[str, ...]) -> list[Category]:
    """The categories, lowest first. None at all: a score-only calculator."""
    if "categories" not in data:
        return []
    categories: list[Category] = []
    for i, raw in enumerate(_list(data["categories"], where, "categories")):
        _only(raw, _CATEGORY_KEYS, f"{where} category")
        name = _name(_req(raw, "name", where), f"{where} category", "name")
        kw = f"{where} category '{name}'"
        has_min, has_gt = "min" in raw, "gt" in raw
        on = raw.get("group")  # not "on": YAML reads a bare `on` as true
        if on is not None and (not isinstance(on, str) or on not in groups):
            raise SpecError(
                f"{kw}: 'group' must name a component group; this calculator has {list(groups)}"
            )
        if i == 0:
            if has_min or has_gt or on is not None:
                raise SpecError(f"{kw}: the first category must have no lower bound")
            lower, strict = -math.inf, False
        else:
            if has_min == has_gt:
                raise SpecError(f"{kw}: needs exactly one of 'min' or 'gt'")
            key = "min" if has_min else "gt"
            lower, strict = _number(raw[key], kw, f"'{key}'"), has_gt
            # Bounds on the same thing (the total, or one group) must ascend.
            earlier = [c.lower for c in categories if c.on == on]
            if earlier and lower <= earlier[-1]:
                raise SpecError(f"{where}: categories must be listed in ascending score order")
        categories.append(
            Category(
                name,
                _text(raw.get("label", name), kw, "label"),
                lower,
                strict,
                _text(raw["meaning"], kw, "meaning") if "meaning" in raw else "",
                on,
            )
        )
    if len(categories) < 2:
        raise SpecError(
            f"{where}: at least two categories are required (leave 'categories' out for a "
            "score-only calculator)"
        )
    if len({c.name for c in categories}) != len(categories):
        raise SpecError(f"{where}: duplicate category names")
    return categories


# --- the whole spec -------------------------------------------------------------------------


def _formula(data: dict[str, Any], where: str, items: dict[str, Item]) -> Formula:
    if "components" in data:
        raise SpecError(f"{where}: a calculator has 'components' or a 'formula', not both")
    try:
        return parse_formula(
            data["formula"],
            where,
            {i: it.accepts for i, it in items.items() if it.type == "numeric"},
            {i: it.levels for i, it in items.items() if it.type == "ordinal"},
            [i for i, it in items.items() if it.type == "boolean"],
        )
    except FormulaError as e:
        raise SpecError(str(e)) from None


def parse(data: Any) -> Calculator:
    """Build a Calculator from the mapping a YAML spec loads into, or raise SpecError."""
    _only(data, _TOP_KEYS, "spec")
    cid = _name(_req(data, "id", "spec"), "spec", "id")
    where = f"calculator '{cid}'"

    items: dict[str, Item] = {}
    for raw in _list(_req(data, "items", where), where, "items"):
        item = _item(raw, where, set(items))
        items[item.id] = item

    formula = _formula(data, where, items) if "formula" in data else None
    components = [] if formula else _components(data, where, items)
    groups = tuple(dict.fromkeys(c.group for c in components if c.group is not None))
    categories = _categories(data, where, groups)

    version = data.get("version", 1)
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise SpecError(f"{where}: version must be a positive whole number")
    higher = data.get("higher_is_higher_risk", True)
    if not isinstance(higher, bool):
        raise SpecError(f"{where}: higher_is_higher_risk must be true or false")

    return Calculator(
        id=cid,
        name=_text(_req(data, "name", where), where, "name"),
        version=version,
        citation=_text(_req(data, "citation", where), where, "citation"),
        references=_texts(data.get("references", []), where, "references"),
        purpose=_text(data["purpose"], where, "purpose") if "purpose" in data else "",
        higher_is_higher_risk=higher,
        items=items,
        components=tuple(components),
        categories=tuple(categories),
        notes=_texts(data.get("notes", []), where, "notes"),
        groups=groups,
        formula=formula,
    )


def load_file(path: str | Path) -> Calculator:
    """Load one spec from a YAML file."""
    with open(path, encoding="utf-8") as f:
        return parse(yaml.safe_load(f))


def load_builtin() -> dict[str, Calculator]:
    """All calculators shipped in bounded_calcs/specs, keyed by id."""
    out: dict[str, Calculator] = {}
    for entry in resources.files("bounded_calcs.specs").iterdir():
        if entry.name.endswith(".yaml"):
            calc = parse(yaml.safe_load(entry.read_text(encoding="utf-8")))
            if entry.name != f"{calc.id}.yaml":
                raise SpecError(f"{entry.name}: file name must be '{calc.id}.yaml' (its id)")
            out[calc.id] = calc
    return dict(sorted(out.items()))
