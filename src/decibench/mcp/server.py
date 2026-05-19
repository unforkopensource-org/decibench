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
    instructions="""Decibench is a voice agent testing and observability platform.

You have access to Decibench's complete evaluation engine. Decibench operates in Three Modes:
1. Deterministic: Fast, script-based matching for quick regression tests.
2. Semantic: LLM-judged criteria evaluation for conversational robustness.
3. Semantic+RAG: Automatically synthesized scenarios based on a knowledge corpus.

Use these tools to help users:
- RAG workflows: Ingest documents (`rag_ingest`), synthesize test suites (`rag_synthesize`), and test agents against them (`synthesize_and_run`).
- Testing: Execute tests (`run_quick_test`, `run_test`) and retrieve detailed traces.
- Analysis: View results, evaluate metrics, and diagnose issues (`doctor`).
""",
)

# Import tool modules to trigger registration with the mcp instance above.
# Each module uses @mcp.tool() to register its tools.
import decibench.mcp.tools_analyze  # noqa: E402
import decibench.mcp.tools_inbox  # noqa: E402
import decibench.mcp.tools_manage  # noqa: E402
import decibench.mcp.tools_rag  # noqa: E402
import decibench.mcp.tools_results  # noqa: E402
import decibench.mcp.tools_run  # noqa: E402, F401
