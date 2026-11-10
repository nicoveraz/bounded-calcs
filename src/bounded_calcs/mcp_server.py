"""MCP server exposing the bounded calculators (stdio by default, so notes stay local).

Tools:
  list_calculators()                   ids, names and purposes
  get_schema(calculator_id)            items, allowed values, scoring, categories, citation
  evaluate(calculator_id, findings)    bounded result: settled?, possible categories,
                                       decisive unknowns to ask about
"""

from __future__ import annotations

import sys
from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from bounded_calcs.engine import InputError, evaluate as _evaluate, schema as _schema
from bounded_calcs.spec import load_builtin

INSTRUCTIONS = """\
Clinical calculators that never assume an unmentioned finding is normal.

Workflow:
1. list_calculators, then get_schema for the calculator you need.
2. Read the note and send to `evaluate` only what it actually documents: present, absent, a
   level, or a number. Leave out (or send "unknown") anything the note does not mention.
   Never fill an unmentioned item as absent or normal. A numeric item described only as
   "normal", with no number, is unknown: do not invent a value. Convert units yourself to the
   unit the schema states.
3. If the result is settled, report its category. If not, ask the clinician about the
   decisive unknowns (in the order given), add the answers, and call evaluate again.
4. Items of kind "judgment" (for example HEART history, Wells "alternative diagnosis less
   likely") must come from the clinician, never from your reading of the note.

Research and reference use only. Not a medical device; not for unsupervised clinical decisions.
"""

CALCS = load_builtin()
server = MCPServer(name="bounded-calcs", instructions=INSTRUCTIONS, version="0.1.1")


def _get(calculator_id: str):
    if calculator_id not in CALCS:
        raise ToolError(f"Unknown calculator '{calculator_id}'. Available: {sorted(CALCS)}")
    return CALCS[calculator_id]


@server.tool()
def list_calculators() -> list[dict[str, str]]:
    """List the available calculators (id, name, purpose)."""
    return [{"id": c.id, "name": c.name, "purpose": c.purpose} for c in CALCS.values()]


@server.tool()
def get_schema(calculator_id: str) -> dict[str, Any]:
    """Describe a calculator: its items and allowed values, how points are assigned, the
    decision categories, the source citation, and open review notes."""
    return _schema(_get(calculator_id))


@server.tool()
def evaluate(calculator_id: str, findings: dict[str, Any] | None = None) -> dict[str, Any]:
    """Evaluate a calculator on what is actually known.

    `findings` maps item ids to values: "present" / "absent" for boolean items, one of the
    listed levels for ordinal items, a number for numeric items. Omit items that are not
    documented (or send "unknown"); they are treated as unknown, never as normal.

    Returns whether the decision category is settled, every category still possible, the
    worst case, the score range, and the decisive unknowns: the only items worth asking the
    clinician about, each with what the category would be for each possible answer.
    """
    try:
        return _evaluate(_get(calculator_id), findings or {})
    except InputError as e:
        raise ToolError(str(e)) from None


def main() -> None:
    transport = sys.argv[1] if len(sys.argv) > 1 else "stdio"
    server.run(transport=transport)  # type: ignore[arg-type]


if __name__ == "__main__":
    main()
