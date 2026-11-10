"""Smoke test for a built distribution: is the installed package complete and does it run?

Run it against the wheel or the sdist, never against the source tree:

    uv build
    uv run --isolated --no-project --with dist/*.whl --with "mcp>=2,<3" scripts/smoke_test.py
    uv run --isolated --no-project --with dist/*.tar.gz --with "mcp>=2,<3" scripts/smoke_test.py

It checks what the unit tests cannot: that the YAML specs are inside the distribution, that
the console script is registered, and that the MCP server starts from the installed package.
"""

import asyncio
import importlib.metadata
import json
import sys
from pathlib import Path

import bounded_calcs
from bounded_calcs import evaluate, load_builtin


def main() -> None:
    location = Path(bounded_calcs.__file__).resolve()
    assert "site-packages" in location.parts, f"not an installed package: {location}"

    calcs = load_builtin()
    assert calcs, "no calculator specs inside the distribution"
    result = evaluate(calcs["wells_pe"], {"heart_rate": 110, "hemoptysis": "absent"})
    assert result["settled"] is False
    assert result["possible_categories"] == ["pe_unlikely", "pe_likely"]

    version = importlib.metadata.version("bounded-calcs")
    scripts = importlib.metadata.entry_points(group="console_scripts")
    assert any(s.name == "bounded-calcs-mcp" for s in scripts), "console script missing"

    listed = asyncio.run(_mcp_list())
    assert {c["id"] for c in listed} == set(calcs), "MCP server and library disagree"
    print(f"bounded-calcs {version} from {location.parent}: {len(calcs)} calculators, MCP ok")


async def _mcp_list() -> list[dict]:
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    params = StdioServerParameters(command=sys.executable, args=["-m", "bounded_calcs.mcp_server"])
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        res = await session.call_tool("list_calculators", {})
        data = getattr(res, "structured_content", None) or json.loads(res.content[0].text)
        return data.get("result", data) if isinstance(data, dict) else data


if __name__ == "__main__":
    main()
