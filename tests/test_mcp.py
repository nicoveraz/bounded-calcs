"""End-to-end: start the MCP server over stdio and call it from a real client session."""

import asyncio
import json
import sys

import pytest

pytest.importorskip("mcp")

from mcp import ClientSession  # noqa: E402
from mcp.client.stdio import StdioServerParameters, stdio_client  # noqa: E402

from bounded_calcs import load_builtin  # noqa: E402


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
    assert {c["id"] for c in listed} == set(load_builtin())
    assert ev["settled"] is False
    assert [d["item"] for d in ev["decisive_unknowns"]] == ["dvt_signs", "pe_most_likely"]
    assert bad.is_error and "Available" in bad.content[0].text


async def _site_session(path):
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "bounded_calcs.mcp_server", "--normal-ranges", str(path)],
    )
    async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
        await s.initialize()
        findings = {"confusion": "absent", "resp_rate": 18, "sbp": 120, "dbp": 80, "age": 70,
                    "urea": "normal"}
        return _payload(
            await s.call_tool("evaluate", {"calculator_id": "curb65", "findings": findings})
        )


def test_site_normal_ranges_file(tmp_path):
    # A laboratory whose urea upper limit is 7 mmol/L: "urea normal" settles CURB-65 at 1 (low).
    path = tmp_path / "ranges.yaml"
    path.write_text("urea: [2.5, 7.0]\n", encoding="utf-8")
    r = asyncio.run(_site_session(path))
    assert r["settled"] and r["category"] == "low"
    assert r["normal_assumed"]["urea"]["source"] == "site"


@pytest.mark.parametrize("content", ["urea: [8, 2]\n", "ureaa: [2.5, 7]\n", "- urea\n"])
def test_bad_site_normal_ranges_file_stops_the_server(tmp_path, content):
    import subprocess

    path = tmp_path / "ranges.yaml"
    path.write_text(content, encoding="utf-8")
    out = subprocess.run(
        [sys.executable, "-m", "bounded_calcs.mcp_server", "--normal-ranges", str(path)],
        capture_output=True, text=True, timeout=60,
    )
    assert out.returncode == 1 and "bounded-calcs-mcp:" in out.stderr
