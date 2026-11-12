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


async def _units_session(args, urea):
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "bounded_calcs.mcp_server", *args]
    )
    async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
        await s.initialize()
        findings = {"confusion": "absent", "resp_rate": 18, "sbp": 120, "dbp": 80, "age": 70,
                    "urea": urea}
        return await s.call_tool("evaluate", {"calculator_id": "curb65", "findings": findings})


def test_server_refuses_a_number_without_a_unit_when_the_site_has_not_set_one():
    # Urea is reported in mmol/L or as BUN or urea in mg/dL: 19 alone means nothing.
    bad = asyncio.run(_units_session([], 19))
    assert bad.is_error and "a number alone is not accepted" in bad.content[0].text
    ok = _payload(asyncio.run(_units_session([], {"value": 19, "unit": "bun_mg/dL"})))
    # BUN 19 mg/dL = 6.78 mmol/L, not over 7: only the age point.
    assert ok["score"] == 1 and ok["category"] == "low"


def test_site_units_file(tmp_path):
    path = tmp_path / "units.yaml"
    path.write_text("urea: bun_mg/dL\n", encoding="utf-8")
    args = ["--units", str(path)]
    r = _payload(asyncio.run(_units_session(args, {"value": 19, "unit": "not stated"})))
    assert r["score"] == 1 and r["converted"]["urea"]["read_as"] == "bun_mg/dL (site unit)"
    bad = asyncio.run(_units_session(args, 19))  # a number alone is still refused
    assert bad.is_error and "a number alone is not accepted" in bad.content[0].text


@pytest.mark.parametrize("content", ["urea: mg/dL\n", "confusion: mmol/L\n", "- urea\n"])
def test_bad_site_units_file_stops_the_server(tmp_path, content):
    import subprocess

    path = tmp_path / "units.yaml"
    path.write_text(content, encoding="utf-8")
    done = subprocess.run(
        [sys.executable, "-m", "bounded_calcs.mcp_server", "--units", str(path)],
        capture_output=True, text=True, timeout=60,
    )  # fmt: skip
    assert done.returncode != 0 and "bounded-calcs-mcp:" in done.stderr


# --- brief and full answers (the tool functions called directly) ---------------------------


def test_brief_schema_keeps_what_filling_in_needs_and_drops_provenance():
    from bounded_calcs import mcp_server as m

    for cid in load_builtin():
        full, brief = m.get_schema(cid, detail="full"), m.get_schema(cid)
        assert "citation" in full and "citation" not in brief and "references" not in brief
        for key in ("id", "name", "purpose", "components", "categories", "input_rules"):
            assert brief[key] == full[key], (cid, key)
        assert [i["id"] for i in brief["items"]] == [i["id"] for i in full["items"]]
        for b, f in zip(brief["items"], full["items"]):
            for key in ("values", "unit", "accepts", "other_units", "unit_labels", "normal"):
                assert b.get(key) == f.get(key), (cid, b["id"], key)
        notes = brief["notes"] + [n for i in brief["items"] for n in i.get("notes", [])]
        assert not any(n.startswith(("TODO(physician-review)", "REVIEWED(physician)"))
                       for n in notes), cid
        assert "full" in brief["detail"]


def test_brief_schema_keeps_notes_on_how_to_read_an_item():
    from bounded_calcs import mcp_server as m

    brief = m.get_schema("pecarn_head_under2")
    assert any(n.startswith("Applies to") for n in brief["notes"])
    assert any("notes" in i for i in brief["items"])


def test_brief_result_differs_from_full_only_by_the_component_breakdown():
    from bounded_calcs import mcp_server as m

    findings = {"confusion": "absent", "age": 70}
    full = m.evaluate("curb65", findings, detail="full")
    brief = m.evaluate("curb65", findings)
    assert full["components"] and "components" not in brief
    assert brief == {k: v for k, v in full.items() if k != "components"}


def test_unknown_detail_is_a_tool_error():
    from mcp.server.mcpserver.exceptions import ToolError

    from bounded_calcs import mcp_server as m

    with pytest.raises(ToolError, match="brief"):
        m.get_schema("curb65", detail="short")
    with pytest.raises(ToolError, match="brief"):
        m.evaluate("curb65", {}, detail="short")


def test_list_gives_the_first_sentence_of_each_purpose():
    from bounded_calcs import mcp_server as m

    calcs = load_builtin()
    for row in m.list_calculators():
        purpose = calcs[row["id"]].purpose
        assert purpose.startswith(row["purpose"].rstrip(".")) and ". " not in row["purpose"]
