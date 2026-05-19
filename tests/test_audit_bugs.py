"""Tests for bugs identified in the functional audit."""

from __future__ import annotations

import os
from unittest.mock import patch
from typing import Any
import pytest
import sqlite3

from decibench.mcp._helpers import format_run_result_rich
from decibench.models import SuiteResult
from decibench.store.privacy import RedactionPolicy
from decibench.config import _redact_secrets
from decibench.store.sqlite import RunStore


def test_bug_001_format_run_result_rich():
    """BUG-001: format_run_result_rich accepts run_id as arg."""
    result = SuiteResult(
        suite="quick",
        target="demo",
        decibench_score=85.0,
        total_scenarios=10,
        passed=9,
        failed=1,
    )
    run_id = "test-run-123"
    formatted = format_run_result_rich(result, run_id)
    assert formatted["run_id"] == "test-run-123"
    assert "10 total scenarios" in formatted["summary"]


def test_bug_003_privacy_redacts_api_keys():
    """BUG-003: API keys and secret keys are redacted from metadata."""
    policy = RedactionPolicy()

    # Test key redaction
    payload = {
        "metadata": {
            "vapi_api_key": "sk-something",
            "normal_field": "hello",
            "nested_credentials": {
                "secret_token": "abc123xyz"
            }
        }
    }
    redacted = policy.redact_dict(payload)
    assert redacted["metadata"]["vapi_api_key"] == "[REDACTED_SECRET]"
    assert redacted["metadata"]["normal_field"] == "hello"
    assert redacted["metadata"]["nested_credentials"] == "[REDACTED_SECRET]"

    # Test string regex redaction
    text_payload = {
        "response": "Here is the key: sk-abcdefghijklmnopqrstuvwxyz123"
    }
    redacted_text = policy.redact_dict(text_payload)
    assert "[REDACTED_API_KEY]" in redacted_text["response"]
    assert "sk-abcdefghijklmnopqrstuvwxyz123" not in redacted_text["response"]


def test_bug_005_config_custom_secrets_redacted():
    """BUG-005: Custom secret fields in config are redacted."""
    config_dict = {
        "providers": {
            "judge_api_key": "real-key",
            "custom_secret_v2": "my-secret-key"
        },
        "auth": {
            "my_credentials": "password123",
            "token": ""
        }
    }
    redacted = _redact_secrets(config_dict)
    assert redacted["providers"]["judge_api_key"] == "<set>"
    assert redacted["providers"]["custom_secret_v2"] == "<set>"
    assert redacted["auth"]["my_credentials"] == "<set>"
    assert redacted["auth"]["token"] == "<unset>"


def test_bug_007_bridge_client_generates_token():
    """BUG-007: BridgeClient generates a token and passes it to sidecar."""
    from decibench.bridge.client import BridgeClient
    client = BridgeClient()
    assert client._token is not None
    assert len(client._token) > 0


def test_bug_008_schema_version_insert_or_ignore(tmp_path):
    """BUG-008: sqlite uses INSERT OR IGNORE for schema version."""
    db_path = tmp_path / "test.sqlite"
    # Create the db and set schema version to something else to simulate prior migration
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.execute("INSERT INTO meta (key, value) VALUES ('schema_version', '4')")
    conn.commit()
    conn.close()

    # Initializing RunStore should not overwrite schema_version with '1'
    store = RunStore(path=db_path)
    
    with store._connect() as conn2:
        row = conn2.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
        assert row["value"] == "4"
