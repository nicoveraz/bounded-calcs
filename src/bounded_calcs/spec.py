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

The loader is deliberately strict: unknown keys, values YAML did not read as text, bands that
can never match and non-exact points are errors, because each of them is a silent wrong
answer otherwise.
"""

from __future__ import annotations

import itertools
import math
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

ITEM_TYPES = {"boolean", "ordinal", "numeric"}
ITEM_KINDS = {"finding", "measurement", "judgment"}
RULE_TYPES = {"present", "absent", "levels", "bands", "count", "any_of"}
BAND_OPS = ("gte", "gt", "lte", "lt")

_ID = re.compile(r"^[a-z][a-z0-9_]*$")
_LEVEL = re.compile(r"^[a-z0-9][a-z0-9_]*$")

_TOP_KEYS = {
    "id", "name", "version", "purpose", "citation", "references", "higher_is_higher_risk",
    "notes", "items", "components", "categories",
}  # fmt: skip
_ITEM_KEYS = {"id", "label", "type", "kind", "levels", "unit", "normal", "question", "notes"}
_COMPONENT_KEYS = {
    "present": {"id", "label", "rule", "item", "points"},
    "absent": {"id", "label", "rule", "item", "points"},
    "levels": {"id", "label", "rule", "item", "points"},
    "bands": {"id", "label", "rule", "item", "bands"},
    "count": {"id", "label", "rule", "items", "points", "override", "override_points"},
    "any_of": {"id", "label", "rule", "conditions", "points"},
}
_BAND_KEYS = {*BAND_OPS, "points"}
_CONDITION_KEYS = {*BAND_OPS, "item"}
_CATEGORY_KEYS = {"name", "label", "min", "gt", "meaning"}

_NOT_TEXT = (
    "YAML reads bare yes/no/on/off/true/false and numbers as non-text, and turns an unquoted "
    "'key: value' into a mapping; wrap the value in double quotes"
)


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
    normal: tuple[float, float] | None = None


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
    points: float | None = None  # present, absent, any_of
    level_points: dict[str, float] = field(default_factory=dict)  # levels
    bands: tuple[Band, ...] = ()  # bands, and count thresholds (op gte on the count)
    override: str | None = None  # count
    override_points: float | None = None  # count
    conditions: dict[str, Band] = field(default_factory=dict)  # any_of: numeric item -> "met"


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

    def numeric_bands(self, item_id: str) -> tuple[Band, ...]:
        """The bands a numeric item is resolved into. For an any_of condition: [met, not met]."""
        comp = self.component_of(item_id)
        if comp.rule == "bands":
            return comp.bands
        met = comp.conditions[item_id]
        return (met, Band(None, None, 0.0))


def band_probes(bands: Sequence[Band]) -> list[float]:
    """Numbers that land in every region the thresholds cut the number line into: each
    threshold itself and a point on either side of it."""
    ts = sorted({b.value for b in bands if b.value is not None})
    if not ts:
        return [0.0]
    gap = min((b - a for a, b in itertools.pairwise(ts)), default=1.0)
    d = min(0.5, gap / 2)
    return sorted({x for t in ts for x in (t - d, t, t + d)})


# --- validation helpers ---------------------------------------------------------------------


def _req(d: dict[str, Any], key: str, where: str) -> Any:
    if key not in d:
        raise SpecError(f"{where}: missing '{key}'")
    return d[key]


def _only(d: Any, allowed: set[str], where: str) -> None:
    if not isinstance(d, dict):
        raise SpecError(f"{where}: expected a mapping, got {d!r}. {_NOT_TEXT}")
    extra = sorted(str(k) for k in d if k not in allowed)
    if extra:
        raise SpecError(f"{where}: unknown key(s) {extra}; allowed: {sorted(allowed)}")


def _list(value: Any, where: str, what: str) -> list[Any]:
    if not isinstance(value, list) or not value:
        raise SpecError(f"{where}: '{what}' must be a non-empty list")
    return value


def _text(value: Any, where: str, what: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SpecError(f"{where}: {what} must be text, got {value!r}. {_NOT_TEXT}")
    return value


def _texts(value: Any, where: str, what: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise SpecError(f"{where}: {what} must be a list")
    return tuple(_text(v, where, f"each entry of {what}") for v in value)


def _name(value: Any, where: str, what: str, pattern: re.Pattern[str] = _ID) -> str:
    if not isinstance(value, str) or not pattern.match(value):
        raise SpecError(
            f"{where}: {what} {value!r} must be lowercase snake_case text (a-z, 0-9, _). "
            f"{_NOT_TEXT}"
        )
    return value


def _number(value: Any, where: str, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise SpecError(f"{where}: {what} must be a number, got {value!r}")
    return float(value)


def _points(value: Any, where: str) -> float:
    p = _number(value, where, "points")
    if not (p * 2).is_integer():
        raise SpecError(
            f"{where}: points {value!r} must be a whole or half number so that sums stay exact"
        )
    return p


def _reachable(bands: Sequence[Band], probes: Iterable[float], where: str) -> None:
    hit = {next(i for i, b in enumerate(bands) if b.matches(x)) for x in probes}
    for i, b in enumerate(bands):
        if i not in hit:
            raise SpecError(
                f"{where}: entry {i + 1} ({b.describe(None)}, {b.points:g} points) can never "
                "apply because an earlier entry always matches first. The first matching entry "
                "wins: list the most extreme threshold first (e.g. gte 65 before gte 45)"
            )


def _band(raw: Any, where: str) -> Band:
    _only(raw, _BAND_KEYS, where)
    ops = [op for op in BAND_OPS if op in raw]
    if len(ops) > 1:
        raise SpecError(f"{where}: band has more than one condition")
    pts = _points(_req(raw, "points", where), where)
    if not ops:
        return Band(None, None, pts)
    return Band(ops[0], _number(raw[ops[0]], where, f"'{ops[0]}'"), pts)


def _bands(raw: Any, where: str) -> tuple[Band, ...]:
    bands = tuple(_band(b, where) for b in _list(raw, where, "bands"))
    if bands[-1].op is not None:
        raise SpecError(f"{where}: the last band must be a default (points only)")
    if any(b.op is None for b in bands[:-1]):
        raise SpecError(f"{where}: only the last band may be a default")
    return bands


# --- parsing --------------------------------------------------------------------------------


def parse(data: Any) -> Calculator:
    _only(data, _TOP_KEYS, "spec")
    cid = _name(_req(data, "id", "spec"), "spec", "id")
    where = f"calculator '{cid}'"

    items: dict[str, Item] = {}
    for raw in _list(_req(data, "items", where), where, "items"):
        _only(raw, _ITEM_KEYS, f"{where} item")
        iid = _name(_req(raw, "id", where), f"{where} item", "id")
        iw = f"{where} item '{iid}'"
        if iid in items:
            raise SpecError(f"{iw}: duplicate id")
        itype = _req(raw, "type", iw)
        kind = _req(raw, "kind", iw)
        if itype not in ITEM_TYPES:
            raise SpecError(f"{iw}: type must be one of {sorted(ITEM_TYPES)}")
        if kind not in ITEM_KINDS:
            raise SpecError(f"{iw}: kind must be one of {sorted(ITEM_KINDS)}")
        raw_levels = _list(raw["levels"], iw, "levels") if "levels" in raw else []
        levels = tuple(_name(v, iw, "level", _LEVEL) for v in raw_levels)
        if (itype == "ordinal") != bool(levels):
            raise SpecError(f"{iw}: 'levels' is required for ordinal items and only for them")
        if len(set(levels)) != len(levels):
            raise SpecError(f"{iw}: duplicate levels")
        if "unknown" in levels:
            raise SpecError(f"{iw}: 'unknown' is reserved and cannot be a level")
        if (itype == "numeric") != ("unit" in raw):
            raise SpecError(f"{iw}: 'unit' is required for numeric items and only for them")
        normal = None
        if "normal" in raw:
            if itype != "numeric":
                raise SpecError(f"{iw}: 'normal' is only for numeric items")
            rng = raw["normal"]
            if not isinstance(rng, list) or len(rng) != 2:
                raise SpecError(f"{iw}: 'normal' must be a list [lo, hi], got {rng!r}")
            lo, hi = (_number(x, iw, "'normal'") for x in rng)
            if lo > hi:
                raise SpecError(f"{iw}: 'normal' must be [lo, hi] with lo <= hi, got {rng!r}")
            normal = (lo, hi)
        items[iid] = Item(
            id=iid,
            label=_text(_req(raw, "label", iw), iw, "label"),
            type=itype,
            kind=kind,
            levels=levels,
            unit=_text(raw["unit"], iw, "unit") if "unit" in raw else None,
            question=_text(raw["question"], iw, "question") if "question" in raw else None,
            notes=_texts(raw.get("notes", []), iw, "notes"),
            normal=normal,
        )

    components: list[Component] = []
    owner: dict[str, str] = {}
    for raw in _list(_req(data, "components", where), where, "components"):
        if not isinstance(raw, dict):
            raise SpecError(f"{where}: each component must be a mapping, got {raw!r}")
        comp_id = _name(_req(raw, "id", where), f"{where} component", "id")
        cw = f"{where} component '{comp_id}'"
        rule = _req(raw, "rule", cw)
        if rule not in RULE_TYPES:
            raise SpecError(f"{cw}: rule must be one of {sorted(RULE_TYPES)}")
        _only(raw, _COMPONENT_KEYS[rule], cw)
        label = _text(raw.get("label", comp_id), cw, "label")

        def item_of(iid: Any, want: str) -> str:
            if iid not in items:
                raise SpecError(f"{cw}: unknown item {iid!r}")
            if items[iid].type != want:
                raise SpecError(f"{cw}: item '{iid}' must be {want} for rule '{rule}'")
            return iid

        if rule in ("present", "absent"):
            iid = item_of(_req(raw, "item", cw), "boolean")
            comp = Component(
                comp_id, label, rule, (iid,), points=_points(_req(raw, "points", cw), cw)
            )
        elif rule == "levels":
            iid = item_of(_req(raw, "item", cw), "ordinal")
            raw_pts = _req(raw, "points", cw)
            if not isinstance(raw_pts, dict) or set(raw_pts) != set(items[iid].levels):
                raise SpecError(
                    f"{cw}: points must be a mapping with exactly the levels of '{iid}' "
                    f"({list(items[iid].levels)}) as keys, got {raw_pts!r}. {_NOT_TEXT}"
                )
            pts = {k: _points(v, cw) for k, v in raw_pts.items()}
            comp = Component(comp_id, label, rule, (iid,), level_points=pts)
        elif rule == "bands":
            iid = item_of(_req(raw, "item", cw), "numeric")
            bands = _bands(_req(raw, "bands", cw), cw)
            _reachable(bands, band_probes(bands), cw)
            comp = Component(comp_id, label, rule, (iid,), bands=bands)
        elif rule == "any_of":
            conds: dict[str, Band] = {}
            members_list: list[str] = []
            for c in _list(_req(raw, "conditions", cw), cw, "conditions"):
                _only(c, _CONDITION_KEYS, f"{cw} condition")
                iid = _req(c, "item", cw)
                if iid not in items:
                    raise SpecError(f"{cw}: unknown item {iid!r}")
                if iid in members_list:
                    raise SpecError(f"{cw}: item '{iid}' appears twice")
                ops = [op for op in BAND_OPS if op in c]
                if items[iid].type == "boolean":
                    if ops:
                        raise SpecError(f"{cw}: boolean condition '{iid}' takes no threshold")
                elif items[iid].type == "numeric":
                    if len(ops) != 1:
                        raise SpecError(f"{cw}: numeric condition '{iid}' needs one threshold")
                    conds[iid] = Band(ops[0], _number(c[ops[0]], cw, f"'{ops[0]}'"), 1.0)
                else:
                    raise SpecError(f"{cw}: ordinal items cannot be any_of conditions")
                members_list.append(iid)
            if len(members_list) < 2:
                raise SpecError(f"{cw}: any_of needs at least two conditions")
            comp = Component(
                comp_id,
                label,
                rule,
                tuple(members_list),
                points=_points(_req(raw, "points", cw), cw),
                conditions=conds,
            )
        else:  # count
            raw_members = _list(_req(raw, "items", cw), cw, "items")
            members = tuple(item_of(i, "boolean") for i in raw_members)
            bands = _bands(_req(raw, "points", cw), cw)
            if any(b.op not in ("gte", None) for b in bands):
                raise SpecError(f"{cw}: count thresholds must use 'gte'")
            _reachable(bands, range(len(members) + 1), cw)
            override = raw.get("override")
            if (override is None) != ("override_points" not in raw):
                raise SpecError(f"{cw}: 'override' and 'override_points' go together")
            if override is not None:
                item_of(override, "boolean")
            all_items = members + ((override,) if override else ())
            comp = Component(
                comp_id,
                label,
                rule,
                all_items,
                bands=bands,
                override=override,
                override_points=_points(raw["override_points"], cw) if override else None,
            )
        for iid in comp.items:
            if iid in owner:
                raise SpecError(
                    f"{cw}: item '{iid}' already used by component '{owner[iid]}'; "
                    "components must not share items"
                )
            owner[iid] = comp_id
        if comp_id in {c.id for c in components}:
            raise SpecError(f"{cw}: duplicate component id")
        components.append(comp)

    unused = set(items) - set(owner)
    if unused:
        raise SpecError(f"{where}: items not used by any component: {sorted(unused)}")

    categories: list[Category] = []
    for i, raw in enumerate(_list(_req(data, "categories", where), where, "categories")):
        _only(raw, _CATEGORY_KEYS, f"{where} category")
        name = _name(_req(raw, "name", where), f"{where} category", "name")
        kw = f"{where} category '{name}'"
        has_min, has_gt = "min" in raw, "gt" in raw
        if i == 0:
            if has_min or has_gt:
                raise SpecError(f"{kw}: the first category must have no lower bound")
            lower, strict = -math.inf, False
        else:
            if has_min == has_gt:
                raise SpecError(f"{kw}: needs exactly one of 'min' or 'gt'")
            key = "min" if has_min else "gt"
            lower, strict = _number(raw[key], kw, f"'{key}'"), has_gt
            if lower <= categories[-1].lower:
                raise SpecError(f"{where}: categories must be listed in ascending score order")
        categories.append(
            Category(
                name,
                _text(raw.get("label", name), kw, "label"),
                lower,
                strict,
                _text(raw["meaning"], kw, "meaning") if "meaning" in raw else "",
            )
        )
    if len(categories) < 2:
        raise SpecError(f"{where}: at least two categories are required")
    if len({c.name for c in categories}) != len(categories):
        raise SpecError(f"{where}: duplicate category names")

    version = data.get("version", 1)
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise SpecError(f"{where}: version must be a positive whole number")
    higher = data.get("higher_is_higher_risk", True)
    if not isinstance(higher, bool):
        raise SpecError(f"{where}: higher_is_higher_risk must be true or false")

    calc = Calculator(
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
    )
    return calc


def load_file(path: str | Path) -> Calculator:
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
