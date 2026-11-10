"""End-to-end: start the MCP server over stdio and call it from a real client session."""

import asyncio
import json
import sys

import pytest

pytest.importorskip("mcp")

from mcp import ClientSession  # noqa: E402
from mcp.client.stdio import StdioServerParameters, stdio_client  # noqa: E402


def _payload(res):
    data = getattr(res, "structured_content", None) or json.loads(res.content[0].text)
    return data.get("result", data) if isinstance(data, dict) else data


async def _session_run():
    params = StdioServerParameters(command=sys.executable, args=["-m", "bounded_calcs.mcp_server"])
    async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
        await s.initialize()
        names = {t.name for t in (await s.list_tools()).tools}
        listed = _payload(await s.call_tool("list_calculators", {}))
        ev = _payload(
            await s.call_tool(
                "evaluate",
                {"calculator_id": "wells_pe",
                 "findings": {"heart_rate": 110, "hemoptysis": "absent", "malignancy": "absent"}},
            )
        )
        bad = await s.call_tool("evaluate", {"calculator_id": "nope", "findings": {}})
        return names, listed, ev, bad


def test_mcp_roundtrip():
    names, listed, ev, bad = asyncio.run(_session_run())
    assert names == {"list_calculators", "get_schema", "evaluate"}
    assert {c["id"] for c in listed} == {"heart", "wells_pe", "perc", "curb65"}
    assert ev["settled"] is False
    assert [d["item"] for d in ev["decisive_unknowns"]] == ["dvt_signs", "pe_most_likely"]
    assert bad.is_error and "Available" in bad.content[0].text
