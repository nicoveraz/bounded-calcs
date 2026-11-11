"""Small checks shared by the loader (`spec.py`) and the rule parsers (`engine/rules/`).

Each raises `SpecError` with a message that says where the problem is and how to fix it.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from bounded_calcs.model import BAND_OPS, Band, Item

_ID = re.compile(r"^[a-z][a-z0-9_]*$")

_LEVEL = re.compile(r"^[a-z0-9][a-z0-9_]*$")

_BAND_KEYS = {*BAND_OPS, "points"}


_NOT_TEXT = (
    "YAML reads bare yes/no/on/off/true/false and numbers as non-text, and turns an unquoted "
    "'key: value' into a mapping; wrap the value in double quotes"
)


class SpecError(ValueError):
    pass




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


def _item_of(items: Mapping[str, Item], iid: Any, want: str, where: str, rule: str) -> str:
    """The id of an item that a component names, checked to exist and to have the type the
    rule needs."""
    if not isinstance(iid, str) or iid not in items:
        raise SpecError(f"{where}: unknown item {iid!r}")
    if items[iid].type != want:
        raise SpecError(f"{where}: item '{iid}' must be {want} for rule '{rule}'")
    return iid
