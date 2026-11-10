"""Entry point of the `bounded-calcs-mcp` command.

The command is installed with the package, but the MCP SDK is an optional extra. Without it,
say what to install instead of showing a traceback.
"""

import sys

MISSING_SDK = (
    "bounded-calcs-mcp needs the MCP SDK, which is an optional extra. Install it with\n"
    '    pip install "bounded-calcs[mcp]"\n'
    "or run the server without installing anything:\n"
    '    uvx --from "bounded-calcs[mcp]" bounded-calcs-mcp'
)


def main() -> None:
    try:
        from bounded_calcs.mcp_server import main as run
    except ModuleNotFoundError as e:
        if e.name is None or e.name.split(".")[0] != "mcp":
            raise
        sys.exit(MISSING_SDK)
    run()
