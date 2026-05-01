"""Tests for MCP management tools — doctor, list_connectors, list_suites."""

from __future__ import annotations

from decibench.mcp.tools_manage import doctor, list_connectors, list_suites


def test_doctor_runs():
    output = doctor()
    assert "Environment Check" in output
    assert "Decibench" in output
    assert "Python" in output
    assert "checks passed" in output


def test_doctor_shows_store():
    output = doctor()
    assert "Store" in output


def test_list_connectors_shows_registered():
    output = list_connectors()
    assert "Available Connectors" in output
    assert "demo" in output.lower()
    assert "ws" in output.lower()


def test_list_connectors_has_elevenlabs():
    output = list_connectors()
    assert "elevenlabs" in output.lower()


def test_list_connectors_has_twilio():
    output = list_connectors()
    assert "twilio" in output.lower()


def test_list_suites():
    output = list_suites()
    assert "quick" in output
    assert "full" in output
    assert "10 scenarios" in output
    assert "21 scenarios" in output
