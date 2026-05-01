"""Entry point for running the Decibench MCP server.

Usage (stdio — for Claude Code / Cursor):
    python -m decibench.mcp

Usage (SSE — for web clients):
    python -m decibench.mcp --transport sse --port 8090
"""

from __future__ import annotations

import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="Decibench MCP server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="Transport protocol (default: stdio)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8090,
        help="Port for SSE transport (default: 8090)",
    )
    args = parser.parse_args()

    from decibench.mcp.server import mcp

    if args.transport == "sse":
        mcp.settings.port = args.port

    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
