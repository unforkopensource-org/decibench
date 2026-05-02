"""Tests for the Telnyx connector."""

from __future__ import annotations

import json
import base64

import pytest

from decibench.connectors.telnyx import TelnyxConnector
from decibench.connectors.registry import get_connector
from decibench.models import AudioBuffer, EventType


# ---------------------------------------------------------------------------
# Registration tests
# ---------------------------------------------------------------------------


def test_telnyx_connector_registered():
    """The 'telnyx' scheme resolves to TelnyxConnector."""
    connector = get_connector("telnyx://+1234567890")
    assert isinstance(connector, TelnyxConnector)


def test_telnyx_connector_audio_format():
    """Telnyx uses PCM16 16kHz mono (native Decibench format)."""
    connector = TelnyxConnector()
    assert connector.required_sample_rate == 16000
    from decibench.models import AudioEncoding
    assert connector.required_encoding == AudioEncoding.PCM_S16LE
    assert connector.required_channels == 1


# ---------------------------------------------------------------------------
# Credential resolution tests
# ---------------------------------------------------------------------------


def test_credentials_from_config():
    connector = TelnyxConnector()
    config = {
        "telnyx_api_key": "test_key_123",
        "telnyx_connection_id": "conn_abc",
        "telnyx_from": "+15551234567",
    }
    connector._resolve_credentials(config)
    assert connector._api_key == "test_key_123"
    assert connector._connection_id == "conn_abc"
    assert connector._from_number == "+15551234567"


def test_credentials_from_env(monkeypatch):
    monkeypatch.setenv("TELNYX_API_KEY", "env_key_456")
    monkeypatch.setenv("TELNYX_CONNECTION_ID", "env_conn")
    monkeypatch.setenv("TELNYX_FROM", "+15559876543")

    connector = TelnyxConnector()
    connector._resolve_credentials({})
    assert connector._api_key == "env_key_456"
    assert connector._connection_id == "env_conn"
    assert connector._from_number == "+15559876543"


def test_config_overrides_env(monkeypatch):
    monkeypatch.setenv("TELNYX_API_KEY", "env_key")

    connector = TelnyxConnector()
    connector._resolve_credentials({"telnyx_api_key": "config_key"})
    assert connector._api_key == "config_key"


# ---------------------------------------------------------------------------
# Target URI parsing tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_target_scheme():
    connector = TelnyxConnector()
    with pytest.raises(ValueError, match="telnyx://"):
        await connector.connect("ws://localhost:3000", {})


@pytest.mark.asyncio
async def test_empty_destination():
    connector = TelnyxConnector()
    with pytest.raises(ValueError, match="destination number"):
        await connector.connect("telnyx://", {})


@pytest.mark.asyncio
async def test_missing_api_key():
    """API key missing triggers ValueError before call initiation."""
    connector = TelnyxConnector()
    # Without an API key, we should get a ValueError
    with pytest.raises(ValueError, match="(API key|connection_id)"):
        await connector.connect("telnyx://+1234567890", {})


# ---------------------------------------------------------------------------
# Event parsing tests (unit-level, no WebSocket required)
# ---------------------------------------------------------------------------


def test_parse_media_event():
    """Parsing a Telnyx media event produces an AGENT_AUDIO event."""
    connector = TelnyxConnector()
    connector._recorded_audio = bytearray()

    audio_data = b"\x00\x01\x02\x03"
    payload_b64 = base64.b64encode(audio_data).decode()
    msg = json.dumps({
        "event": "media",
        "media": {"payload": payload_b64},
    })

    event = connector._parse_event(msg, start_ns=0)
    assert event is not None
    assert event.type == EventType.AGENT_AUDIO
    assert event.audio == audio_data
    assert audio_data in bytes(connector._recorded_audio)


def test_parse_stream_stop_event():
    connector = TelnyxConnector()
    msg = json.dumps({"event": "stream_stop", "stream_id": "abc123"})
    event = connector._parse_event(msg, start_ns=0)
    assert event is not None
    assert event.type == EventType.METADATA
    assert event.data.get("stream_ended") is True


def test_parse_dtmf_event():
    connector = TelnyxConnector()
    msg = json.dumps({"event": "dtmf", "dtmf": {"digit": "5"}})
    event = connector._parse_event(msg, start_ns=0)
    assert event is not None
    assert event.type == EventType.METADATA
    assert event.data.get("dtmf") == "5"


def test_parse_transcript_event():
    connector = TelnyxConnector()
    msg = json.dumps({"transcript": "Hello, how can I help?"})
    event = connector._parse_event(msg, start_ns=0)
    assert event is not None
    assert event.type == EventType.AGENT_TRANSCRIPT
    assert event.data.get("text") == "Hello, how can I help?"


def test_parse_interrupt_event():
    connector = TelnyxConnector()
    msg = json.dumps({"event": "interrupt"})
    event = connector._parse_event(msg, start_ns=0)
    assert event is not None
    assert event.type == EventType.INTERRUPTION


def test_parse_tool_call_event():
    connector = TelnyxConnector()
    msg = json.dumps({"tool_call": {"name": "lookup", "args": {"id": "123"}}})
    event = connector._parse_event(msg, start_ns=0)
    assert event is not None
    assert event.type == EventType.TOOL_CALL
    assert event.data.get("name") == "lookup"


def test_parse_unknown_event():
    connector = TelnyxConnector()
    msg = json.dumps({"event": "custom", "foo": "bar"})
    event = connector._parse_event(msg, start_ns=0)
    assert event is not None
    assert event.type == EventType.METADATA
    assert event.data.get("foo") == "bar"


def test_parse_invalid_json():
    connector = TelnyxConnector()
    event = connector._parse_event("not json at all", start_ns=0)
    assert event is None


def test_parse_binary_message():
    connector = TelnyxConnector()
    connector._recorded_audio = bytearray()
    data = b"\x00\x01\x02"
    event = connector._parse_event(data, start_ns=0)
    assert event is not None
    assert event.type == EventType.AGENT_AUDIO
    assert event.audio == data


def test_parse_media_event_empty_payload():
    connector = TelnyxConnector()
    msg = json.dumps({"event": "media", "media": {"payload": ""}})
    event = connector._parse_event(msg, start_ns=0)
    assert event is None


# ---------------------------------------------------------------------------
# Send audio chunking test (verifies 640-byte chunk boundary)
# ---------------------------------------------------------------------------


def test_pcm16_chunk_size():
    """Verify the chunk size matches 20ms of PCM16 16kHz mono."""
    from decibench.connectors.telnyx import _PCM16_CHUNK_BYTES
    assert _PCM16_CHUNK_BYTES == 640  # 2 bytes/sample * 16000 samples/sec * 0.02 sec
