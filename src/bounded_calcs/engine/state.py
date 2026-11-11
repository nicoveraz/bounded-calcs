"""What the engine knows about each item, and small helpers shared by its modules."""

from __future__ import annotations

from typing import Any

# Internal state per item: bool (boolean), str level (ordinal), frozenset of band indices
# (numeric: the bands its value may fall in; one band means known), or None (unknown).
State = dict[str, Any]


INF = float("inf")


Points = tuple[float, ...]
"""The total score followed by the points of each group of the calculator."""


def _uncertain(state: State, iid: str) -> bool:
    """True if the item's value is not settled: unknown, or a range over several bands."""
    v = state[iid]
    return v is None or (isinstance(v, frozenset) and len(v) > 1)


def _fmt(x: float) -> float | int:
    return int(x) if float(x).is_integer() else x


def _bound(x: float) -> float | int | None:
    """A range bound for JSON output: None for an open end."""
    return None if abs(x) == INF else _fmt(x)
