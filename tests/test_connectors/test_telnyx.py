"""Tests for the Telnyx Media Streaming mock connector."""

from __future__ import annotations

import base64
import json

import pytest

from decibench.connectors.registry import get_connector
from decibench.connectors.telnyx import _L16_CHUNK_BYTES, TelnyxConnector
from decibench.models import AudioBuffer, AudioEncoding, EventType


def test_telnyx_connector_registered() -> None:
    connector = get_connector("telnyx://localhost:5050/media")
    assert isinstance(connector, TelnyxConnector)


def test_telnyx_connector_audio_format() -> None:
    connector = TelnyxConnector()
    assert connector.required_sample_rate == 16000
    assert connector.required_encoding == AudioEncoding.PCM_S16LE
    assert connector.required_channels == 1


@pytest.mark.asyncio
async def test_invalid_target_scheme() -> None:
    connector = TelnyxConnector()
    with pytest.raises(ValueError, match="telnyx://"):
        await connector.connect("ws://localhost:3000", {})


@pytest.mark.asyncio
async def test_empty_target() -> None:
    connector = TelnyxConnector()
    with pytest.raises(ValueError, match="target is empty"):
        await connector.connect("telnyx://", {})


def test_parse_media_event() -> None:
    connector = TelnyxConnector()
    audio_data = b"\x00\x01\x02\x03"
    payload_b64 = base64.b64encode(audio_data).decode()
    msg = json.dumps(
        {
            "event": "media",
            "media": {"payload": payload_b64},
        }
    )

    event = connector._parse_event(msg, start_ns=0)

    assert event is not None
    assert event.type == EventType.AGENT_AUDIO
    assert event.audio == audio_data
    assert audio_data in bytes(connector._recorded_audio)


def test_parse_stop_event() -> None:
    connector = TelnyxConnector()
    msg = json.dumps({"event": "stop", "stream_id": "abc123"})

    event = connector._parse_event(msg, start_ns=0)

    assert event is not None
    assert event.type == EventType.METADATA
    assert event.data.get("stream_ended") is True


def test_parse_mark_event() -> None:
    connector = TelnyxConnector()
    msg = json.dumps({"event": "mark", "mark": {"name": "end-of-chunk"}})

    event = connector._parse_event(msg, start_ns=0)

    assert event is not None
    assert event.type == EventType.METADATA
    assert event.data.get("mark") == "end-of-chunk"


def test_parse_dtmf_event() -> None:
    connector = TelnyxConnector()
    msg = json.dumps({"event": "dtmf", "dtmf": {"digit": "5"}})

    event = connector._parse_event(msg, start_ns=0)

    assert event is not None
    assert event.type == EventType.METADATA
    assert event.data.get("dtmf") == "5"


def test_parse_error_event() -> None:
    connector = TelnyxConnector()
    msg = json.dumps({"event": "error", "payload": {"code": 100004, "title": "invalid_media"}})

    event = connector._parse_event(msg, start_ns=0)

    assert event is not None
    assert event.type == EventType.ERROR
    assert event.data.get("code") == 100004


def test_parse_transcript_event() -> None:
    connector = TelnyxConnector()
    msg = json.dumps({"transcript": "Hello, how can I help?"})

    event = connector._parse_event(msg, start_ns=0)

    assert event is not None
    assert event.type == EventType.AGENT_TRANSCRIPT
    assert event.data.get("text") == "Hello, how can I help?"


def test_parse_interrupt_event() -> None:
    connector = TelnyxConnector()
    msg = json.dumps({"event": "clear"})

    event = connector._parse_event(msg, start_ns=0)

    assert event is not None
    assert event.type == EventType.INTERRUPTION


def test_parse_tool_call_event() -> None:
    connector = TelnyxConnector()
    msg = json.dumps({"tool_call": {"name": "lookup", "args": {"id": "123"}}})

    event = connector._parse_event(msg, start_ns=0)

    assert event is not None
    assert event.type == EventType.TOOL_CALL
    assert event.data.get("name") == "lookup"


def test_parse_unknown_event() -> None:
    connector = TelnyxConnector()
    msg = json.dumps({"event": "custom", "foo": "bar"})

    event = connector._parse_event(msg, start_ns=0)

    assert event is not None
    assert event.type == EventType.METADATA
    assert event.data.get("foo") == "bar"


def test_parse_invalid_json() -> None:
    connector = TelnyxConnector()
    event = connector._parse_event("not json at all", start_ns=0)
    assert event is None


def test_parse_binary_message() -> None:
    connector = TelnyxConnector()
    data = b"\x00\x01\x02"

    event = connector._parse_event(data, start_ns=0)

    assert event is not None
    assert event.type == EventType.AGENT_AUDIO
    assert event.audio == data


def test_parse_media_event_empty_payload() -> None:
    connector = TelnyxConnector()
    msg = json.dumps({"event": "media", "media": {"payload": ""}})
    event = connector._parse_event(msg, start_ns=0)
    assert event is None


def test_l16_chunk_size() -> None:
    assert _L16_CHUNK_BYTES == 640


class _FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, message: str) -> None:
        self.sent.append(message)


@pytest.mark.asyncio
async def test_send_audio_emits_telnyx_media_frames() -> None:
    connector = TelnyxConnector()
    connector._ws = _FakeWebSocket()
    connector._stream_id = "stream-1"

    audio = AudioBuffer(data=b"\x01" * (_L16_CHUNK_BYTES + 1), sample_rate=16000)
    await connector.send_audio(None, audio)  # type: ignore[arg-type]

    assert len(connector._ws.sent) == 2
    first = json.loads(connector._ws.sent[0])
    second = json.loads(connector._ws.sent[1])
    assert first["event"] == "media"
    assert first["sequence_number"] == "1"
    assert first["media"]["track"] == "inbound"
    assert first["media"]["chunk"] == "1"
    assert first["media"]["timestamp"] == "0"
    assert first["stream_id"] == "stream-1"
    assert base64.b64decode(first["media"]["payload"]) == b"\x01" * _L16_CHUNK_BYTES
    assert second["sequence_number"] == "2"
    assert second["media"]["chunk"] == "2"
    assert base64.b64decode(second["media"]["payload"]) == b"\x01"


@pytest.mark.asyncio
async def test_send_start_frame_uses_telnyx_shape() -> None:
    connector = TelnyxConnector()
    connector._ws = _FakeWebSocket()
    connector._stream_id = "stream-1"
    connector._call_control_id = "v3:test"
    connector._call_session_id = "session-1"
    connector._custom_params = {"tenant": "demo"}

    await connector._send_start({"telnyx_from": "+15550001111", "telnyx_to": "+15550002222"})

    message = json.loads(connector._ws.sent[0])
    assert message["event"] == "start"
    assert message["sequence_number"] == "1"
    assert message["stream_id"] == "stream-1"
    assert message["start"]["call_control_id"] == "v3:test"
    assert message["start"]["call_session_id"] == "session-1"
    assert message["start"]["from"] == "+15550001111"
    assert message["start"]["to"] == "+15550002222"
    assert message["start"]["media_format"] == {
        "encoding": "L16",
        "sample_rate": 16000,
        "channels": 1,
    }
    assert message["start"]["custom_parameters"] == {"tenant": "demo"}
