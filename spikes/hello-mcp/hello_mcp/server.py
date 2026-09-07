"""Minimal hello-world MCP server, using the real MCP protocol
(streamable-http transport) - not this repo's tms-mcp-style FastAPI-REST
pattern. One tool, no identity/policy wiring, deployed to Cloud Run to prove
the deploy mechanics work, same spirit as spikes/hello-agent-adk.

The installed `mcp` SDK (>=1.2 at time of writing) renamed the old
`mcp.server.fastmcp.FastMCP` class to `mcp.server.mcpserver.MCPServer` -
verified against the actual installed package, not assumed from older
docs/examples (same lesson as skills/a2a-agent-card/SKILL.md: check the SDK
version before assuming an API shape still holds)."""

from __future__ import annotations

import os

from mcp.server.mcpserver import MCPServer

mcp = MCPServer("hello-mcp")


@mcp.tool()
def say_hello(name: str = "world") -> str:
    """Return a greeting. Proves a real MCP tool call round-trip."""
    return f"[hello-mcp] Hello, {name}!"


def main() -> None:
    port = int(os.environ.get("PORT", os.environ.get("SERVICE_PORT", "8080")))
    mcp.run(transport="streamable-http", host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
