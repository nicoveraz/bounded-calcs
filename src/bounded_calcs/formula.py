"""Formula calculators: the result is an expression on the items, not a sum of points.

    formula:
      expression: (a / b) / c          # items by id; + - * / **, parentheses, and the
                                       # functions ln, log10, exp, sqrt, min, max
      unit: mL/min                     # optional: the unit of the result
      decimals: 1                      # optional: round the result to this many decimals
      monotonic:                       # every numeric item: does the result rise or fall
        a: increasing                  # when this item rises, the others held the same?
        b: decreasing
        c: decreasing
      values:                          # every ordinal item: the number each level stands for
        sex: {male: 1, female: 0.85}

A boolean item counts as 1 when present and 0 when absent.

Why `monotonic` is required: with unknown inputs the engine bounds the result by evaluating
the expression at the ends of each input's range, which is exact only if the result moves in
one direction with each input. The loader checks every declared direction on a grid over the
items' accepted ranges and rejects a spec whose expression does not behave as declared (or
that cannot be evaluated somewhere in those ranges, such as a division by zero). A formula
that is not monotonic in some input does not fit this format.

The expression is parsed into a small tree and evaluated by this module: it is never passed
to Python's `eval`.
"""

from __future__ import annotations

import ast
import itertools
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

DIRECTIONS = ("increasing", "decreasing")
FORMULA_KEYS = {"expression", "unit", "decimals", "monotonic", "values"}

_FUNCTIONS: dict[str, tuple[Any, int | None]] = {  # name -> (function, number of arguments)
    "ln": (math.log, 1),
    "log10": (math.log10, 1),
    "exp": (math.exp, 1),
    "sqrt": (math.sqrt, 1),
    "min": (min, None),
    "max": (max, None),
}
_BINARY = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.Pow: lambda a, b: a**b,
}


class FormulaError(ValueError):
    """The expression is not allowed, or cannot be evaluated for some input."""


def _check(node: ast.AST, names: set[str]) -> None:
    """Allow only arithmetic on numbers and names, and the listed functions."""
    if isinstance(node, ast.Expression):
        _check(node.body, names)
    elif isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
        _check(node.left, names)
        _check(node.right, names)
    elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        _check(node.operand, names)
    elif isinstance(node, ast.Constant) and type(node.value) in (int, float):
        pass
    elif isinstance(node, ast.Name):
        names.add(node.id)
    elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        if node.func.id not in _FUNCTIONS or node.keywords:
            raise FormulaError(
                f"function '{node.func.id}' is not available; use one of {sorted(_FUNCTIONS)}"
            )
        arity = _FUNCTIONS[node.func.id][1]
        if (arity is not None and len(node.args) != arity) or len(node.args) < 1:
            raise FormulaError(f"wrong number of arguments for '{node.func.id}'")
        if arity is None and len(node.args) < 2:
            raise FormulaError(f"'{node.func.id}' needs at least two arguments")
        for arg in node.args:
            _check(arg, names)
    else:
        raise FormulaError(
            "only numbers, item ids, + - * / **, parentheses and the functions "
            f"{sorted(_FUNCTIONS)} are allowed"
        )


def _eval(node: ast.AST, env: Mapping[str, float]) -> float:
    if isinstance(node, ast.Expression):
        return _eval(node.body, env)
    if isinstance(node, ast.BinOp):
        return _BINARY[type(node.op)](_eval(node.left, env), _eval(node.right, env))
    if isinstance(node, ast.UnaryOp):
        value = _eval(node.operand, env)
        return -value if isinstance(node.op, ast.USub) else value
    if isinstance(node, ast.Constant):
        return float(node.value)
    if isinstance(node, ast.Name):
        return env[node.id]
    assert isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    return float(_FUNCTIONS[node.func.id][0](*(_eval(a, env) for a in node.args)))


@dataclass(frozen=True)
class Formula:
    expression: str
    unit: str | None
    decimals: int | None
    monotonic: dict[str, str]  # numeric item -> "increasing" or "decreasing"
    level_values: dict[str, dict[str, float]]  # ordinal item -> level -> number
    names: frozenset[str]  # the items the expression uses
    tree: ast.Expression = field(compare=False, repr=False)

    def number(self, item_id: str, value: Any) -> float:
        """The number an item's value stands for in the expression."""
        if isinstance(value, bool):
            return 1.0 if value else 0.0
        if item_id in self.level_values:
            return self.level_values[item_id][value]
        return float(value)

    def raw(self, values: Mapping[str, Any]) -> float:
        """The expression for one value per item, before rounding."""
        env = {i: self.number(i, v) for i, v in values.items()}
        try:
            out = _eval(self.tree, env)
        except (ZeroDivisionError, ValueError, OverflowError) as e:
            raise FormulaError(f"cannot evaluate '{self.expression}' for {dict(values)}: {e}")
        if isinstance(out, complex) or out != out or abs(out) == math.inf:
            raise FormulaError(f"'{self.expression}' has no finite value for {dict(values)}")
        return out

    def value(self, values: Mapping[str, Any]) -> float:
        """The result for one value per item (bool, level name or number)."""
        out = self.raw(values)
        return round(out, self.decimals) if self.decimals is not None else out


def grid(lo: float, hi: float, points: int) -> list[float]:
    """`points` evenly spaced numbers from lo to hi, both ends included."""
    if lo == hi or points < 2:
        return [lo]
    inner = [lo + (hi - lo) * k / (points - 1) for k in range(1, points - 1)]
    return [lo, *inner, hi]  # the ends exactly, not within rounding of them


def parse_formula(
    raw: Any,
    where: str,
    numeric: Mapping[str, tuple[float, float] | None],
    ordinal: Mapping[str, Sequence[str]],
    boolean: Sequence[str],
) -> Formula:
    """Read and check the `formula` section. `numeric` maps each numeric item to its accepted
    range (None if it has none), `ordinal` each ordinal item to its levels. Raises
    FormulaError with a message that says what to fix."""
    if not isinstance(raw, dict):
        raise FormulaError(f"{where}: 'formula' must be a mapping with an 'expression'")
    unknown = set(raw) - FORMULA_KEYS
    if unknown:
        raise FormulaError(
            f"{where} formula: unknown key(s) {sorted(unknown)}; allowed: {sorted(FORMULA_KEYS)}"
        )
    expression = raw.get("expression")
    if not isinstance(expression, str) or not expression.strip():
        raise FormulaError(f"{where} formula: 'expression' must be text")
    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except SyntaxError as e:
        raise FormulaError(f"{where} formula: cannot read the expression: {e.msg}") from None
    names: set[str] = set()
    try:
        _check(tree, names)
    except FormulaError as e:
        raise FormulaError(f"{where} formula: {e}") from None
    items = {*numeric, *ordinal, *boolean}
    if names - items:
        raise FormulaError(
            f"{where} formula: the expression uses {sorted(names - items)}, which are not items"
        )
    if items - names:
        raise FormulaError(f"{where}: items not used by the formula: {sorted(items - names)}")

    no_range = sorted(i for i, r in numeric.items() if r is None)
    if no_range:
        raise FormulaError(
            f"{where}: numeric items of a formula need 'accepts' (the range that bounds the "
            f"result while the item is unknown): {no_range}"
        )
    monotonic = raw.get("monotonic", {})
    if not isinstance(monotonic, dict) or set(monotonic) != set(numeric):
        raise FormulaError(
            f"{where} formula: 'monotonic' must give a direction for exactly the numeric "
            f"items {sorted(numeric)}"
        )
    for i, d in monotonic.items():
        if d not in DIRECTIONS:
            raise FormulaError(f"{where} formula: monotonic.{i} must be one of {DIRECTIONS}")
    values = raw.get("values", {})
    if not isinstance(values, dict) or set(values) != set(ordinal):
        raise FormulaError(
            f"{where} formula: 'values' must give numbers for exactly the ordinal items "
            f"{sorted(ordinal)}"
        )
    level_values: dict[str, dict[str, float]] = {}
    for i, mapping in values.items():
        if not isinstance(mapping, dict) or set(mapping) != set(ordinal[i]):
            raise FormulaError(
                f"{where} formula: values.{i} must give a number for each level "
                f"{list(ordinal[i])}"
            )
        for level, x in mapping.items():
            if isinstance(x, bool) or not isinstance(x, (int, float)):
                raise FormulaError(f"{where} formula: values.{i}.{level} must be a number")
        level_values[i] = {level: float(x) for level, x in mapping.items()}
    decimals = raw.get("decimals")
    if decimals is not None and (
        isinstance(decimals, bool) or not isinstance(decimals, int) or not 0 <= decimals <= 6
    ):
        raise FormulaError(f"{where} formula: 'decimals' must be a whole number from 0 to 6")
    unit = raw.get("unit")
    if unit is not None and (not isinstance(unit, str) or not unit.strip()):
        raise FormulaError(f"{where} formula: 'unit' must be text")

    formula = Formula(
        expression=expression.strip(),
        unit=unit,
        decimals=decimals,
        monotonic=dict(monotonic),
        level_values=level_values,
        names=frozenset(names),
        tree=tree,
    )
    _check_monotonic(formula, where, {i: r for i, r in numeric.items() if r}, ordinal, boolean)
    return formula


def _check_monotonic(
    formula: Formula,
    where: str,
    numeric: Mapping[str, tuple[float, float]],
    ordinal: Mapping[str, Sequence[str]],
    boolean: Sequence[str],
) -> None:
    """Evaluate the expression on a grid over the accepted ranges and check that it can be
    evaluated everywhere and moves with each numeric item as declared."""
    discrete = {**{i: [True, False] for i in boolean}, **{i: list(v) for i, v in ordinal.items()}}
    n_discrete = math.prod(len(v) for v in discrete.values())
    points = 5
    while points > 2 and n_discrete * points ** len(numeric) > 50_000:
        points -= 1
    axes = {i: grid(lo, hi, points) for i, (lo, hi) in numeric.items()}
    ids = [*discrete, *axes]
    domains = [*discrete.values(), *axes.values()]
    table: dict[tuple[Any, ...], float] = {}
    for combo in itertools.product(*domains):
        try:
            table[combo] = formula.raw(dict(zip(ids, combo)))
        except FormulaError as e:
            raise FormulaError(f"{where} formula: {e} (inside the accepted ranges)") from None
    for pos, item_id in enumerate(ids):
        if item_id not in axes:
            continue
        sign = 1.0 if formula.monotonic[item_id] == "increasing" else -1.0
        axis = axes[item_id]
        for combo, here in table.items():
            k = axis.index(combo[pos])
            if k + 1 == len(axis):
                continue
            nxt = table[combo[:pos] + (axis[k + 1],) + combo[pos + 1 :]]
            if sign * (nxt - here) < -1e-9 * max(1.0, abs(here), abs(nxt)):
                raise FormulaError(
                    f"{where} formula: the result is not {formula.monotonic[item_id]} in "
                    f"'{item_id}': from {combo[pos]:g} to {axis[k + 1]:g} it goes from "
                    f"{here:g} to {nxt:g} (other items: {dict(zip(ids, combo))}). Correct "
                    "'monotonic', or stop: a formula that is not monotonic does not fit."
                )
