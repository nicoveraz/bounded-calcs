"""Calculator specifications: loading and validation.

A calculator is declared in YAML as a set of *items* (what can be known about the patient)
and a set of *components* (how items turn into points). Every item belongs to exactly one
component, so components are independent and the set of reachable scores is exactly the
sumset of each component's reachable points. That is what makes the bounds exact.

Item types:
  boolean   present / absent / unknown
  ordinal   one of `levels`, or unknown
  numeric   a number in `unit`, or unknown

Item kinds (who can supply the value):
  finding      can be read from a note or chart
  measurement  a number from the chart (vitals, labs, age)
  judgment     clinician-only; never inferred from a note

Component rules:
  present   {item, points}                      points if the boolean item is present
  levels    {item, points: {level: points}}     points by ordinal level
  bands     {item, bands: [{gte|gt|lte|lt: x, points}, ..., {points}]}
            first matching band wins; the last band has no condition (default)
  count     {items, points: [{gte: n, points}, ..., {points}],
             override?: item, override_points?: p}
            points by number of present boolean items; if `override` is present the
            component scores `override_points` regardless of the count
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

ITEM_TYPES = {"boolean", "ordinal", "numeric"}
ITEM_KINDS = {"finding", "measurement", "judgment"}
RULE_TYPES = {"present", "levels", "bands", "count"}
BAND_OPS = ("gte", "gt", "lte", "lt")


class SpecError(ValueError):
    pass


@dataclass(frozen=True)
class Item:
    id: str
    label: str
    type: str
    kind: str
    levels: tuple[str, ...] = ()
    unit: str | None = None
    question: str | None = None
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class Band:
    op: str | None  # None = default band
    value: float | None
    points: float

    def matches(self, x: float) -> bool:
        if self.op is None:
            return True
        assert self.value is not None
        return {
            "gte": x >= self.value,
            "gt": x > self.value,
            "lte": x <= self.value,
            "lt": x < self.value,
        }[self.op]

    def describe(self, unit: str | None) -> str:
        if self.op is None:
            return "otherwise"
        sym = {"gte": ">=", "gt": ">", "lte": "<=", "lt": "<"}[self.op]
        return f"{sym} {self.value:g}" + (f" {unit}" if unit else "")


@dataclass(frozen=True)
class Component:
    id: str
    label: str
    rule: str
    items: tuple[str, ...]
    points: float | None = None  # present
    level_points: dict[str, float] = field(default_factory=dict)  # levels
    bands: tuple[Band, ...] = ()  # bands, and count thresholds (op gte on the count)
    override: str | None = None  # count
    override_points: float | None = None  # count


@dataclass(frozen=True)
class Category:
    name: str
    label: str
    lower: float  # score >= lower (or > lower when lower_strict)
    lower_strict: bool
    meaning: str = ""

    def admits(self, score: float) -> bool:
        return score > self.lower if self.lower_strict else score >= self.lower


@dataclass(frozen=True)
class Calculator:
    id: str
    name: str
    version: int
    citation: str
    references: tuple[str, ...]
    purpose: str
    higher_is_higher_risk: bool
    items: dict[str, Item]
    components: tuple[Component, ...]
    categories: tuple[Category, ...]  # ascending by score
    notes: tuple[str, ...]

    def category(self, score: float) -> Category:
        found = None
        for c in self.categories:
            if c.admits(score):
                found = c
        if found is None:
            raise SpecError(f"{self.id}: score {score} below all categories")
        return found

    def by_risk(self, names: set[str]) -> list[str]:
        """Category names ordered from lowest to highest risk."""
        order = [c.name for c in self.categories]
        if not self.higher_is_higher_risk:
            order = order[::-1]
        return [n for n in order if n in names]

    def component_of(self, item_id: str) -> Component:
        for c in self.components:
            if item_id in c.items:
                return c
        raise KeyError(item_id)


def _req(d: dict[str, Any], key: str, where: str) -> Any:
    if key not in d:
        raise SpecError(f"{where}: missing '{key}'")
    return d[key]


def _band(raw: dict[str, Any], where: str) -> Band:
    ops = [op for op in BAND_OPS if op in raw]
    if len(ops) > 1:
        raise SpecError(f"{where}: band has more than one condition")
    pts = float(_req(raw, "points", where))
    if not ops:
        return Band(None, None, pts)
    return Band(ops[0], float(raw[ops[0]]), pts)


def _bands(raw: list[dict[str, Any]], where: str) -> tuple[Band, ...]:
    bands = tuple(_band(b, where) for b in raw)
    if not bands or bands[-1].op is not None:
        raise SpecError(f"{where}: the last band must be a default (points only)")
    if any(b.op is None for b in bands[:-1]):
        raise SpecError(f"{where}: only the last band may be a default")
    return bands


def parse(data: dict[str, Any]) -> Calculator:
    cid = _req(data, "id", "spec")
    where = f"calculator '{cid}'"

    items: dict[str, Item] = {}
    for raw in _req(data, "items", where):
        iid = _req(raw, "id", where)
        iw = f"{where} item '{iid}'"
        if iid in items:
            raise SpecError(f"{iw}: duplicate id")
        itype = _req(raw, "type", iw)
        kind = _req(raw, "kind", iw)
        if itype not in ITEM_TYPES:
            raise SpecError(f"{iw}: type must be one of {sorted(ITEM_TYPES)}")
        if kind not in ITEM_KINDS:
            raise SpecError(f"{iw}: kind must be one of {sorted(ITEM_KINDS)}")
        levels = tuple(raw.get("levels", ()))
        if (itype == "ordinal") != bool(levels):
            raise SpecError(f"{iw}: 'levels' is required for ordinal items and only for them")
        if "unknown" in levels:
            raise SpecError(f"{iw}: 'unknown' is reserved and cannot be a level")
        if itype == "numeric" and not raw.get("unit"):
            raise SpecError(f"{iw}: numeric items need a unit")
        items[iid] = Item(
            id=iid,
            label=_req(raw, "label", iw),
            type=itype,
            kind=kind,
            levels=levels,
            unit=raw.get("unit"),
            question=raw.get("question"),
            notes=tuple(raw.get("notes", ())),
        )

    components: list[Component] = []
    owner: dict[str, str] = {}
    for raw in _req(data, "components", where):
        comp_id = _req(raw, "id", where)
        cw = f"{where} component '{comp_id}'"
        rule = _req(raw, "rule", cw)
        if rule not in RULE_TYPES:
            raise SpecError(f"{cw}: rule must be one of {sorted(RULE_TYPES)}")
        label = raw.get("label", comp_id)

        def item_of(iid: str, want: str) -> str:
            if iid not in items:
                raise SpecError(f"{cw}: unknown item '{iid}'")
            if items[iid].type != want:
                raise SpecError(f"{cw}: item '{iid}' must be {want} for rule '{rule}'")
            return iid

        if rule == "present":
            iid = item_of(_req(raw, "item", cw), "boolean")
            comp = Component(comp_id, label, rule, (iid,), points=float(_req(raw, "points", cw)))
        elif rule == "levels":
            iid = item_of(_req(raw, "item", cw), "ordinal")
            pts = {str(k): float(v) for k, v in _req(raw, "points", cw).items()}
            if set(pts) != set(items[iid].levels):
                raise SpecError(f"{cw}: points must cover exactly the levels of '{iid}'")
            comp = Component(comp_id, label, rule, (iid,), level_points=pts)
        elif rule == "bands":
            iid = item_of(_req(raw, "item", cw), "numeric")
            comp = Component(comp_id, label, rule, (iid,), bands=_bands(_req(raw, "bands", cw), cw))
        else:  # count
            members = tuple(item_of(i, "boolean") for i in _req(raw, "items", cw))
            bands = _bands(_req(raw, "points", cw), cw)
            if any(b.op not in ("gte", None) for b in bands):
                raise SpecError(f"{cw}: count thresholds must use 'gte'")
            override = raw.get("override")
            if override is not None:
                item_of(override, "boolean")
                if "override_points" not in raw:
                    raise SpecError(f"{cw}: 'override' needs 'override_points'")
            all_items = members + ((override,) if override else ())
            comp = Component(
                comp_id,
                label,
                rule,
                all_items,
                bands=bands,
                override=override,
                override_points=float(raw["override_points"]) if override else None,
            )
        for iid in comp.items:
            if iid in owner:
                raise SpecError(
                    f"{cw}: item '{iid}' already used by component '{owner[iid]}'; "
                    "components must not share items"
                )
            owner[iid] = comp_id
        components.append(comp)

    unused = set(items) - set(owner)
    if unused:
        raise SpecError(f"{where}: items not used by any component: {sorted(unused)}")

    categories: list[Category] = []
    for i, raw in enumerate(_req(data, "categories", where)):
        name = _req(raw, "name", where)
        has_min, has_gt = "min" in raw, "gt" in raw
        if i == 0:
            if has_min or has_gt:
                raise SpecError(f"{where}: the first category must have no lower bound")
            lower, strict = -math.inf, False
        else:
            if has_min == has_gt:
                raise SpecError(f"{where}: category '{name}' needs exactly one of 'min' or 'gt'")
            lower, strict = (float(raw["min"]), False) if has_min else (float(raw["gt"]), True)
            if lower <= categories[-1].lower:
                raise SpecError(f"{where}: categories must be listed in ascending score order")
        categories.append(Category(name, raw.get("label", name), lower, strict, raw.get("meaning", "")))
    if len({c.name for c in categories}) != len(categories):
        raise SpecError(f"{where}: duplicate category names")

    return Calculator(
        id=cid,
        name=_req(data, "name", where),
        version=int(data.get("version", 1)),
        citation=_req(data, "citation", where),
        references=tuple(data.get("references", ())),
        purpose=data.get("purpose", ""),
        higher_is_higher_risk=bool(data.get("higher_is_higher_risk", True)),
        items=items,
        components=tuple(components),
        categories=tuple(categories),
        notes=tuple(data.get("notes", ())),
    )


def load_file(path: str | Path) -> Calculator:
    with open(path, encoding="utf-8") as f:
        return parse(yaml.safe_load(f))


def load_builtin() -> dict[str, Calculator]:
    """All calculators shipped in bounded_calcs/specs, keyed by id."""
    out: dict[str, Calculator] = {}
    for entry in resources.files("bounded_calcs.specs").iterdir():
        if entry.name.endswith(".yaml"):
            calc = parse(yaml.safe_load(entry.read_text(encoding="utf-8")))
            if calc.id in out:
                raise SpecError(f"duplicate calculator id '{calc.id}'")
            out[calc.id] = calc
    return dict(sorted(out.items()))
