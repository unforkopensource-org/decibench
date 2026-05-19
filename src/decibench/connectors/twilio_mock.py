"""Twilio Media Streams mock connector.

Simulates Twilio's bidirectional Media Streams WebSocket protocol. Connects
to your voice agent's WebSocket server and pretends to be Twilio — sends the
same ``connected``, ``start``, ``media``, and ``stop`` messages that Twilio
would send during a real phone call.

This lets you test Twilio-based voice agents locally without making real
phone calls or spending Twilio credits.

Usage:
    decibench run --target twilio://localhost:3000/media-stream --suite quick

Audio format: mulaw 8kHz mono (standard telephony), base64 encoded in JSON.
The orchestrator transcodes from PCM 16kHz automatically.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
import uuid
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlparse

from decibench.connectors.base import BaseConnector
from decibench.connectors.registry import register_connector
from decibench.models import (
    AgentEvent,
    AudioBuffer,
    AudioEncoding,
    CallSummary,
    ConnectionHandle,
    EventType,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = logging.getLogger(__name__)

# 20ms of mulaw 8kHz mono = 160 bytes (1 byte per sample)
_MULAW_CHUNK_BYTES = 160
_RECV_TIMEOUT = 5.0
_SILENCE_MAX = 3


def _generate_sid(prefix: str) -> str:
    """Generate a Twilio-style SID (e.g., CA + 32 hex chars)."""
    return prefix + uuid.uuid4().hex


@register_connector("twilio")
class TwilioMockConnector(BaseConnector):
    """Mock Twilio Media Streams — test voice agents without real phone calls."""

    required_sample_rate: int = 8000
    required_encoding: AudioEncoding = AudioEncoding.MULAW
    required_channels: int = 1

    def __init__(self, **kwargs: Any) -> None:
        self._ws: Any = None
        self._recorded_audio = bytearray()
        self._events: list[AgentEvent] = []
        self._send_count = 0
        self._sequence_number = 0
        self._stream_sid = ""
        self._call_sid = ""
        self._custom_params: dict[str, str] = {}

    async def connect(self, target: str, config: dict[str, Any]) -> ConnectionHandle:
        import websockets

        # Parse target: twilio://host:port/path?params
        prefix = "twilio://"
        if not target.startswith(prefix):
            raise ValueError(f"Twilio connector expects twilio://<host:port/path>, got: {target!r}")

        raw = target[len(prefix) :]
        parsed = urlparse(f"ws://{raw}")
        ws_url = f"ws://{parsed.netloc}{parsed.path}"

        # Extract custom parameters from query string
        self._custom_params = {k: v[0] for k, v in parse_qs(parsed.query).items()}

        # Also merge any twilio_* config keys as custom params
        for key, val in config.items():
            if key.startswith("twilio_param_") and val:
                self._custom_params[key[len("twilio_param_") :]] = str(val)

        self._stream_sid = _generate_sid("MZ")
        self._call_sid = _generate_sid("CA")
        account_sid = config.get("twilio_account_sid", _generate_sid("AC"))

        logger.info("Connecting to Twilio-compatible server: %s", ws_url)

        try:
            self._ws = await websockets.connect(
                ws_url,
                max_size=10 * 1024 * 1024,
                ping_interval=30,
                ping_timeout=30,
                close_timeout=10,
            )
        except Exception as exc:
            raise ConnectionError(
                f"Twilio mock connection to {ws_url} failed: {exc}. "
                "Check that your voice agent server is running."
            ) from exc

        # Send Twilio handshake: connected → start
        self._sequence_number = 0

        connected_msg = {
            "event": "connected",
            "protocol": "Call",
            "version": "1.0.0",
        }
        await self._ws.send(json.dumps(connected_msg))
        self._sequence_number += 1

        start_msg = {
            "event": "start",
            "sequenceNumber": str(self._sequence_number),
            "start": {
                "accountSid": account_sid,
                "streamSid": self._stream_sid,
                "callSid": self._call_sid,
                "tracks": ["inbound"],
                "mediaFormat": {
                    "encoding": "audio/x-mulaw",
                    "sampleRate": 8000,
                    "channels": 1,
                },
                "customParameters": self._custom_params,
            },
            "streamSid": self._stream_sid,
        }
        await self._ws.send(json.dumps(start_msg))
        self._sequence_number += 1

        logger.info(
            "Twilio mock session: callSid=%s streamSid=%s params=%s",
            self._call_sid,
            self._stream_sid,
            self._custom_params,
        )

        handle = ConnectionHandle(
            connector_type="twilio",
            start_time_ns=time.monotonic_ns(),
            state={
                "url": ws_url,
                "call_sid": self._call_sid,
                "stream_sid": self._stream_sid,
                "custom_params": self._custom_params,
            },
        )
        self._recorded_audio.clear()
        self._events.clear()
        self._send_count = 0
        return handle

    async def send_audio(self, handle: ConnectionHandle, audio: AudioBuffer) -> None:
        if self._ws is None:
            raise RuntimeError("Twilio mock connector not connected")

        self._send_count += 1
        data = audio.data
        chunk_num = 0
        # Timestamp in milliseconds relative to stream start
        timestamp_ms = 0

        for offset in range(0, len(data), _MULAW_CHUNK_BYTES):
            chunk = data[offset : offset + _MULAW_CHUNK_BYTES]
            chunk_num += 1
            self._sequence_number += 1

            media_msg = {
                "event": "media",
                "sequenceNumber": str(self._sequence_number),
                "media": {
                    "track": "inbound",
                    "chunk": str(chunk_num),
                    "timestamp": str(timestamp_ms),
                    "payload": base64.b64encode(chunk).decode(),
                },
                "streamSid": self._stream_sid,
            }
            await self._ws.send(json.dumps(media_msg))

            # 20ms per chunk at 8kHz
            timestamp_ms += 20
            await asyncio.sleep(0.02)

    async def receive_events(self, handle: ConnectionHandle) -> AsyncIterator[AgentEvent]:
        if self._ws is None:
            return

        start_ns = handle.start_time_ns
        silence_count = 0

        while silence_count < _SILENCE_MAX:
            try:
                message = await asyncio.wait_for(self._ws.recv(), timeout=_RECV_TIMEOUT)
            except TimeoutError:
                silence_count += 1
                continue
            except Exception as exc:
                logger.warning("Twilio mock receive error: %s: %s", type(exc).__name__, exc)
                err_event = AgentEvent(
                    type=EventType.ERROR,
                    timestamp_ms=(time.monotonic_ns() - start_ns) / 1_000_000,
                    data={"error": str(exc), "type": type(exc).__name__},
                )
                self._events.append(err_event)
                yield err_event
                break

            silence_count = 0
            event = self._parse_event(message, start_ns)
            if event is None:
                continue
            self._events.append(event)
            yield event

    async def disconnect(self, handle: ConnectionHandle) -> CallSummary:
        duration_ms = (time.monotonic_ns() - handle.start_time_ns) / 1_000_000

        # Send Twilio stop message
        if self._ws is not None:
            try:
                self._sequence_number += 1
                stop_msg = {
                    "event": "stop",
                    "sequenceNumber": str(self._sequence_number),
                    "stop": {
                        "accountSid": handle.state.get("account_sid", ""),
                        "callSid": self._call_sid,
                    },
                    "streamSid": self._stream_sid,
                }
                await self._ws.send(json.dumps(stop_msg))
            except Exception:
                pass

            try:
                await self._ws.close()
            except Exception:
                logger.debug("Twilio mock WebSocket close error (non-fatal)", exc_info=True)
            self._ws = None

        turn_count = max(self._send_count, 1)

        summary = CallSummary(
            duration_ms=duration_ms,
            turn_count=turn_count,
            agent_audio=bytes(self._recorded_audio),
            events=list(self._events),
            platform_metadata={
                "twilio_call_sid": self._call_sid,
                "twilio_stream_sid": self._stream_sid,
                "twilio_custom_params": self._custom_params,
            },
        )
        self._recorded_audio = bytearray()
        self._events = []
        return summary

    # ------------------------------------------------------------------ internal

    def _parse_event(self, message: str | bytes, start_ns: int) -> AgentEvent | None:
        """Parse a message from the voice agent server (Twilio response format)."""
        now_ms = (time.monotonic_ns() - start_ns) / 1_000_000

        if isinstance(message, bytes):
            # Raw binary audio (uncommon for Twilio but handle it)
            self._recorded_audio.extend(message)
            return AgentEvent(type=EventType.AGENT_AUDIO, timestamp_ms=now_ms, audio=message)

        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            return None

        event = data.get("event", "")

        # Agent audio — server sends media back to "Twilio" (us)
        if event == "media":
            payload = data.get("media", {}).get("payload", "")
            if payload:
                audio_bytes = base64.b64decode(payload)
                self._recorded_audio.extend(audio_bytes)
                return AgentEvent(
                    type=EventType.AGENT_AUDIO,
                    timestamp_ms=now_ms,
                    audio=audio_bytes,
                )
            return None

        # Mark — playback position checkpoint
        if event == "mark":
            mark_name = data.get("mark", {}).get("name", "")
            return AgentEvent(
                type=EventType.METADATA,
                timestamp_ms=now_ms,
                data={"mark": mark_name},
            )

        # Clear — agent cleared audio buffer (barge-in / interruption)
        if event == "clear":
            return AgentEvent(
                type=EventType.INTERRUPTION,
                timestamp_ms=now_ms,
                data={"source": "twilio_clear"},
            )

        # Some Twilio-integrated agents also send JSON with transcripts, tool calls
        # Handle these generically
        if "transcript" in data or "text" in data:
            text = data.get("transcript", data.get("text", ""))
            return AgentEvent(
                type=EventType.AGENT_TRANSCRIPT,
                timestamp_ms=now_ms,
                data={"text": text, "is_final": True},
            )

        if "tool_call" in data or "function_call" in data:
            return AgentEvent(
                type=EventType.TOOL_CALL,
                timestamp_ms=now_ms,
                data=data.get("tool_call", data.get("function_call", data)),
            )

        # Unknown event — store as metadata
        return AgentEvent(
            type=EventType.METADATA,
            timestamp_ms=now_ms,
            data=data,
        )
