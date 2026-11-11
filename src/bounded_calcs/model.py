"""The data model of a calculator: what a loaded spec is.

Plain frozen dataclasses with no parsing and no scoring. `spec.py` builds them from YAML, the
engine reads them, and each scoring rule (`engine/rules/`) both parses and scores its own kind
of component. The YAML format itself is described in `spec.py`.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from bounded_calcs.formula import Formula

ITEM_TYPES = {"boolean", "ordinal", "numeric"}

ITEM_KINDS = {"finding", "measurement", "judgment"}

BAND_OPS = ("gte", "gt", "lte", "lt")


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
    accepts: tuple[float, float] | None = None
    units: dict[str, float] = field(default_factory=dict)  # other unit -> factor to `unit`
    unit_labels: dict[str, str] = field(default_factory=dict)  # other unit -> how notes write it


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
    group: str | None = None


@dataclass(frozen=True)
class Category:
    name: str
    label: str
    lower: float  # points >= lower (or > lower when lower_strict)
    lower_strict: bool
    meaning: str = ""
    on: str | None = None  # the group whose points are compared; None = the total score

    def admits(self, points: float) -> bool:
        return points > self.lower if self.lower_strict else points >= self.lower

    def condition(self) -> str:
        if self.lower == -math.inf:
            return "lowest"
        what = "score" if self.on is None else f"points in group '{self.on}'"
        return f"{what} {'>' if self.lower_strict else '>='} {self.lower:g}"


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
    # Lowest first; the last whose condition holds applies. Empty: a score-only calculator.
    categories: tuple[Category, ...]
    notes: tuple[str, ...]
    groups: tuple[str, ...] = ()  # component groups, in order of first use
    formula: Formula | None = None  # set for a formula calculator, which has no components

    def category(self, score: float, group_points: Sequence[float] = ()) -> Category:
        """The category for a total score and, for calculators with groups, the points of
        each group (in the order of `groups`)."""
        if not self.categories:
            raise ValueError(f"{self.id}: a score-only calculator has no categories")
        if len(group_points) != len(self.groups):
            raise ValueError(f"{self.id}: expected the points of groups {list(self.groups)}")
        found = self.categories[0]
        for c in self.categories[1:]:
            points = score if c.on is None else group_points[self.groups.index(c.on)]
            if c.admits(points):
                found = c
        return found

    def by_risk(self, names: set[Any]) -> list[Any]:
        """Category names ordered from lowest to highest risk (for a score-only calculator,
        scores in that order)."""
        if not self.categories:
            return sorted(names, reverse=not self.higher_is_higher_risk)
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
        if self.formula is not None:  # a formula uses the number itself: one band, everything
            return (Band(None, None, 0.0),)
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
