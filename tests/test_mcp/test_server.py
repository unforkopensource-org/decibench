"""Tests for MCP server initialization and tool registration."""

from __future__ import annotations


def test_mcp_instance_exists():
    from decibench.mcp import mcp
    assert mcp is not None
    assert mcp.name == "Decibench"


def test_mcp_server_has_instructions():
    from decibench.mcp.server import mcp
    assert "voice agent" in mcp.instructions.lower()


def test_all_tools_registered():
    """Verify every expected tool is registered on the MCP server."""
    from decibench.mcp.server import mcp

    tool_names = {t.name for t in mcp._tool_manager.list_tools()}
    expected = {
        "run_test",
        "run_quick_test",
        "list_runs",
        "get_run_detail",
        "get_latest_score",
        "analyze_failures",
        "compare_runs",
        "doctor",
        "list_connectors",
        "list_suites",
        "show_scoring",
        "configure_scoring",
    }
    missing = expected - tool_names
    assert not missing, f"Missing tools: {missing}"


def test_no_duplicate_tools():
    from decibench.mcp.server import mcp

    tool_names = [t.name for t in mcp._tool_manager.list_tools()]
    assert len(tool_names) == len(set(tool_names)), f"Duplicate tools found: {tool_names}"
