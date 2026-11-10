"""Release hygiene: things that must agree before a version is published
(see docs/RELEASING.md)."""

import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]


def test_mcp_server_reports_the_package_version():
    pytest.importorskip("mcp")
    from bounded_calcs.mcp_server import server

    assert server.version == PROJECT["version"], (
        "set the same version in pyproject.toml and in mcp_server.py, then run `uv lock`"
    )


def test_readme_links_work_on_pypi():
    # The README is the PyPI project page, where relative links lead nowhere.
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    relative = [
        target
        for target in re.findall(r"\]\(([^)]+)\)", readme)
        if not target.startswith(("https://", "#"))
    ]
    assert not relative, f"use absolute URLs in README.md: {relative}"


def test_mcp_bound_is_the_same_everywhere():
    (bound,) = PROJECT["optional-dependencies"]["mcp"]
    for name in (".github/workflows/publish.yml", "scripts/smoke_test.py", "docs/RELEASING.md"):
        assert f'"{bound}"' in (ROOT / name).read_text(encoding="utf-8"), (
            f"{name} must use the MCP SDK bound from pyproject.toml ({bound})"
        )


def test_mcp_command_without_the_extra_says_what_to_install():
    import subprocess
    import sys

    # Setting sys.modules["mcp"] to None makes any import of the MCP SDK fail, as it does
    # when the package was installed without the [mcp] extra.
    code = (
        "import sys; sys.modules['mcp'] = None\n"
        "from bounded_calcs._mcp_launcher import main\n"
        "main()\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert out.returncode == 1
    assert 'pip install "bounded-calcs[mcp]"' in out.stderr
    assert "Traceback" not in out.stderr


def test_console_script_points_to_the_launcher():
    scripts = PROJECT["scripts"]
    assert scripts["bounded-calcs-mcp"] == "bounded_calcs._mcp_launcher:main"
