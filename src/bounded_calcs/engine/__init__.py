"""Bounded evaluation: what can be concluded when some items are unknown.

The engine never assumes an unknown item is normal or absent. It computes every score the
patient could still have, the decision categories those scores fall into, and which unknown
items could change that set. All results are exact (no sampling): components are independent,
so reachable scores are the sumset of each component's reachable points.

Modules, each with one job:

    inputs.py   what a caller may send (words, numbers, ranges, units) -> the engine's state
    rules/      one module per scoring rule: the points a component can still give
    bounds.py   reachable scores and categories; which unknown items can change them
    formula_bounds.py  the same for formula calculators: the result range from the input ranges
    result.py   evaluate() and schema(): the output a caller sees
    state.py    the state's type and small shared helpers

To add a scoring rule, add a module under `rules/` (see its docstring) and its parsing in
`spec.py`; the other modules do not change. Everything a caller used to import from `bounded_calcs.engine` is still here.
"""

from bounded_calcs.engine.inputs import (
    FALSE_WORDS,
    NORMAL_WORD,
    TRUE_WORDS,
    UNIT_NOT_STATED,
    UNKNOWN_WORDS,
    InputError,
    check_site_ranges,
    check_site_units,
    normal_ranges_in_use,
)
from bounded_calcs.engine.result import evaluate, schema
from bounded_calcs.engine.state import INF, Points, State, _bound, _fmt

__all__ = [
    "FALSE_WORDS",
    "INF",
    "NORMAL_WORD",
    "TRUE_WORDS",
    "UNIT_NOT_STATED",
    "UNKNOWN_WORDS",
    "InputError",
    "Points",
    "State",
    "_bound",
    "_fmt",
    "check_site_ranges",
    "check_site_units",
    "evaluate",
    "normal_ranges_in_use",
    "schema",
]
