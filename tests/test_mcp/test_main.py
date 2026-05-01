"""Tests for MCP __main__ entry point."""

from __future__ import annotations

import subprocess
import sys


def test_main_module_importable():
    """python -m decibench.mcp should be importable."""
    from decibench.mcp.__main__ import main
    assert callable(main)


def test_main_help_flag():
    """--help should exit cleanly with usage info."""
    result = subprocess.run(
        [sys.executable, "-m", "decibench.mcp", "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0
    assert "transport" in result.stdout.lower()
    assert "stdio" in result.stdout.lower()
    assert "sse" in result.stdout.lower()
