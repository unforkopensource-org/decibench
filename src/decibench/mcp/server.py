"""Decibench MCP server — the main FastMCP instance and tool registry.

This is the entry point. Each tool module registers its tools with the
shared ``mcp`` instance at import time. The server exposes:

- **Tools**: run tests, list runs, get results, analyze failures, doctor
- **Resources**: score breakdowns, scenario definitions, run history

Usage (stdio — for Claude Code / Cursor):
    python -m decibench.mcp

Usage (SSE — for web clients):
    python -m decibench.mcp --transport sse --port 8090
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "Decibench",
    instructions=(
        "Decibench is a voice agent testing framework. Use these tools to "
        "run quality tests against voice agents (ElevenLabs, Retell, Vapi, "
        "Twilio, WebSocket, HTTP, or local processes), view results, analyze "
        "failures, and track quality over time. All data is stored locally "
        "in .decibench/decibench.sqlite."
    ),
)

# Import tool modules to trigger registration with the mcp instance above.
# Each module uses @mcp.tool() to register its tools.
import decibench.mcp.tools_run  # noqa: E402, F401
import decibench.mcp.tools_results  # noqa: E402, F401
import decibench.mcp.tools_analyze  # noqa: E402, F401
import decibench.mcp.tools_manage  # noqa: E402, F401
