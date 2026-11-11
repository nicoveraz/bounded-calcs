"""MCP server exposing the bounded calculators (stdio by default, so notes stay local).

Tools:
  list_calculators()                   ids, names and purposes
  get_schema(calculator_id)            items, allowed values, scoring, categories, citation
  evaluate(calculator_id, findings)    bounded result: settled?, possible categories,
                                       decisive unknowns to ask about

Usage: bounded-calcs-mcp [--normal-ranges FILE] [--units FILE] [stdio | sse | streamable-http]

FILE is a YAML or JSON mapping from numeric item id to the site's own normal range, for
example a laboratory's reference range: `urea: [2.5, 7.0]`. It replaces the default range
used when a note says only "normal", in every calculator that has the item.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from bounded_calcs.engine import (
    InputError,
    check_site_ranges,
    check_site_units,
    evaluate as _evaluate,
    schema as _schema,
)
from bounded_calcs.spec import load_builtin

INSTRUCTIONS = """\
Clinical calculators that never assume an unmentioned finding is normal.

Workflow:
1. list_calculators, then get_schema for the calculator you need.
2. Read the note and send to `evaluate` only what it actually documents: present, absent, a
   level, or a number. Leave out (or send "unknown") anything the note does not mention.
   Never fill an unmentioned item as absent or normal. If the note says only that a numeric
   item is normal ("vital signs normal"), send "normal" when the schema gives that item a
   normal range, and leave it unknown otherwise. If it gives only bounds ("heart rate over
   100", "SBP in the 90s"), send {"min": x, "max": y}, leaving out the bound it does not
   give. Never invent a number. Send a plain number only in the unit the schema states for
   that item. If the note gives another unit that the schema lists for the item
   (other_units), send {"value": x, "unit": "the note's unit"} and the tool converts it.
   An item the schema marks unit_required always goes that way, with the unit exactly as
   the note gives it (unit_labels says what each listed unit means). Only if the note gives
   the number with no unit at all, send "unit": "not stated" when the schema shows a
   site_unit for the item, and otherwise ask for the unit. Never guess a unit, and convert
   one yourself only when the schema does not list it.
3. If the result is settled, report its category (for a score-only calculator, one whose
   schema has no categories, its score). If not, ask the clinician about the
   decisive unknowns (in the order given), add the answers, and call evaluate again.
4. Items of kind "judgment" (for example HEART history, Wells "alternative diagnosis less
   likely") must come from the clinician, never from your reading of the note.

Research and reference use only. Not a medical device; not for unsupervised clinical decisions.
"""

CALCS = load_builtin()
SITE_RANGES: dict[str, Any] = {}
"""The site's normal ranges, set at startup by --normal-ranges."""
SITE_UNITS: dict[str, Any] = {}
"""The unit the site reports each item in, set at startup by --units. An item that declares
other units and has no site unit must come with its unit: the server never assumes one."""
server = MCPServer(name="bounded-calcs", instructions=INSTRUCTIONS, version="0.2.0")


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
    return _schema(
        _get(calculator_id), normal_ranges=SITE_RANGES, units=SITE_UNITS, require_units=True
    )


@server.tool()
def evaluate(calculator_id: str, findings: dict[str, Any] | None = None) -> dict[str, Any]:
    """Evaluate a calculator on what is actually known.

    `findings` maps item ids to values: "present" / "absent" for boolean items, one of the
    listed levels for ordinal items, a number for numeric items ("normal" for those with a
    normal range, when the note gives no number; {"min": x, "max": y} when it gives only
    bounds). Omit items that are not documented (or send "unknown"); they are treated as
    unknown, never as normal.

    Returns whether the decision category is settled, every category still possible, the
    worst case, the score range, and the decisive unknowns: the only items worth asking the
    clinician about, each with what the category would be for each possible answer.
    """
    try:
        return _evaluate(
            _get(calculator_id),
            findings or {},
            normal_ranges=SITE_RANGES,
            units=SITE_UNITS,
            require_units=True,
        )
    except InputError as e:
        raise ToolError(str(e)) from None


def load_site_ranges(path: str | Path) -> dict[str, Any]:
    """Read and validate a site's normal ranges file (YAML or JSON)."""
    try:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as e:
        raise InputError(f"cannot read normal ranges from {path}: {e}") from None
    if not isinstance(data, dict):
        raise InputError(f"{path}: expected a mapping like 'urea: [2.5, 7.0]', got {data!r}")
    check_site_ranges(CALCS, data)
    return data


def load_site_units(path: str | Path) -> dict[str, Any]:
    """Read and validate a site's units file (YAML or JSON): item id to the unit the site
    reports it in, for example `urea: bun_mg/dL`."""
    try:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as e:
        raise InputError(f"cannot read site units from {path}: {e}") from None
    if not isinstance(data, dict):
        raise InputError(f"{path}: expected a mapping like 'urea: bun_mg/dL', got {data!r}")
    check_site_units(CALCS, data)
    return data


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="bounded-calcs-mcp", description=__doc__.split("\n")[0])
    parser.add_argument("transport", nargs="?", default="stdio",
                        choices=["stdio", "sse", "streamable-http"])
    parser.add_argument("--normal-ranges", metavar="FILE",
                        help="YAML or JSON mapping of item id to the site's [lo, hi] normal range")
    parser.add_argument("--units", metavar="FILE",
                        help="YAML or JSON mapping of item id to the unit the site reports it in")
    args = parser.parse_args(argv)
    if args.units:
        try:
            SITE_UNITS.update(load_site_units(args.units))
        except InputError as e:
            sys.exit(f"bounded-calcs-mcp: {e}")
    if args.normal_ranges:
        try:
            SITE_RANGES.update(load_site_ranges(args.normal_ranges))
        except InputError as e:
            sys.exit(f"bounded-calcs-mcp: {e}")
    server.run(transport=args.transport)  # type: ignore[arg-type]


if __name__ == "__main__":
    main()
