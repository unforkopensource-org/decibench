"""Telnyx Media Streaming mock connector.

Simulates Telnyx Programmable Voice media streaming over WebSockets. It
connects to your voice agent's WebSocket server and sends the same high-level
``connected``, ``start``, ``media``, and ``stop`` frames a Telnyx call stream
would send.

Usage:
    decibench run target=telnyx://localhost:5050/media suite=quick

Audio format: L16 16 kHz mono, base64 encoded in JSON media frames. Telnyx
supports this codec for bidirectional RTP streams, and it keeps Decibench on
its native PCM16 path.
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

# 20 ms of L16 16 kHz mono = 640 bytes.
_L16_CHUNK_BYTES = 640
_RECV_TIMEOUT = 5.0
_SILENCE_MAX = 3


@register_connector("telnyx")
class TelnyxConnector(BaseConnector):
    """Mock Telnyx Media Streaming for local Telnyx-compatible agents."""

    required_sample_rate: int = 16000
    required_encoding: AudioEncoding = AudioEncoding.PCM_S16LE
    required_channels: int = 1

    def __init__(self, **kwargs: Any) -> None:
        self._ws: Any = None
        self._recorded_audio = bytearray()
        self._events: list[AgentEvent] = []
        self._send_count = 0
        self._sequence_number = 0
        self._stream_id = ""
        self._call_control_id = ""
        self._call_session_id = ""
        self._custom_params: dict[str, str] = {}

    async def connect(self, target: str, config: dict[str, Any]) -> ConnectionHandle:
        import websockets

        prefix = "telnyx://"
        if not target.startswith(prefix):
            raise ValueError(f"Telnyx connector expects telnyx://<host:port/path>, got: {target!r}")

        raw = target[len(prefix) :].strip()
        if not raw:
            raise ValueError("Telnyx connector target is empty")

        parsed = urlparse(f"ws://{raw}")
        ws_url = f"ws://{parsed.netloc}{parsed.path}"
        self._custom_params = {key: value[0] for key, value in parse_qs(parsed.query).items()}

        for key, value in config.items():
            if key.startswith("telnyx_param_") and value:
                self._custom_params[key[len("telnyx_param_") :]] = str(value)

        self._stream_id = str(uuid.uuid4()).upper()
        self._call_control_id = config.get("telnyx_call_control_id") or f"v3:{uuid.uuid4().hex}"
        self._call_session_id = config.get("telnyx_call_session_id") or str(uuid.uuid4())

        logger.info("Connecting to Telnyx-compatible server: %s", ws_url)

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
                f"Telnyx mock connection to {ws_url} failed: {exc}. "
                "Check that your voice agent server is running."
            ) from exc

        await self._send_connected()
        await self._send_start(config)

        handle = ConnectionHandle(
            connector_type="telnyx",
            start_time_ns=time.monotonic_ns(),
            state={
                "url": ws_url,
                "stream_id": self._stream_id,
                "call_control_id": self._call_control_id,
                "call_session_id": self._call_session_id,
                "custom_params": self._custom_params,
            },
        )
        self._recorded_audio.clear()
        self._events.clear()
        self._send_count = 0
        return handle

    async def send_audio(self, handle: ConnectionHandle, audio: AudioBuffer) -> None:
        if self._ws is None:
            raise RuntimeError("Telnyx connector not connected")

        self._send_count += 1
        timestamp_ms = 0

        for offset in range(0, len(audio.data), _L16_CHUNK_BYTES):
            chunk = audio.data[offset : offset + _L16_CHUNK_BYTES]
            self._sequence_number += 1
            chunk_number = offset // _L16_CHUNK_BYTES + 1

            media_msg = {
                "event": "media",
                "sequence_number": str(self._sequence_number),
                "media": {
                    "track": "inbound",
                    "chunk": str(chunk_number),
                    "timestamp": str(timestamp_ms),
                    "payload": base64.b64encode(chunk).decode(),
                },
                "stream_id": self._stream_id,
            }
            await self._ws.send(json.dumps(media_msg))

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
                logger.warning("Telnyx mock receive error: %s: %s", type(exc).__name__, exc)
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

        if self._ws is not None:
            try:
                self._sequence_number += 1
                stop_msg = {
                    "event": "stop",
                    "sequence_number": str(self._sequence_number),
                    "stop": {
                        "call_control_id": self._call_control_id,
                        "call_session_id": self._call_session_id,
                    },
                    "stream_id": self._stream_id,
                }
                await self._ws.send(json.dumps(stop_msg))
            except Exception:
                pass

            try:
                await self._ws.close()
            except Exception:
                logger.debug("Telnyx mock WebSocket close error (non-fatal)", exc_info=True)
            self._ws = None

        turn_count = max(self._send_count, 1)
        summary = CallSummary(
            duration_ms=duration_ms,
            turn_count=turn_count,
            agent_audio=bytes(self._recorded_audio),
            events=list(self._events),
            platform_metadata={
                "telnyx_stream_id": self._stream_id,
                "telnyx_call_control_id": self._call_control_id,
                "telnyx_call_session_id": self._call_session_id,
                "telnyx_custom_params": self._custom_params,
            },
        )
        self._recorded_audio = bytearray()
        self._events = []
        return summary

    async def _send_connected(self) -> None:
        self._sequence_number = 0
        await self._ws.send(json.dumps({"event": "connected", "version": "1.0.0"}))

    async def _send_start(self, config: dict[str, Any]) -> None:
        self._sequence_number += 1
        start_msg = {
            "event": "start",
            "sequence_number": str(self._sequence_number),
            "start": {
                "user_id": config.get("telnyx_user_id", str(uuid.uuid4()).upper()),
                "call_control_id": self._call_control_id,
                "call_session_id": self._call_session_id,
                "from": config.get("telnyx_from", "+15550000001"),
                "to": config.get("telnyx_to", "+15550000002"),
                "tags": [],
                "client_state": "",
                "media_format": {
                    "encoding": "L16",
                    "sample_rate": 16000,
                    "channels": 1,
                },
                "custom_parameters": self._custom_params,
            },
            "stream_id": self._stream_id,
        }
        await self._ws.send(json.dumps(start_msg))

    # ------------------------------------------------------------------ internal

    def _parse_event(self, message: str | bytes, start_ns: int) -> AgentEvent | None:
        now_ms = (time.monotonic_ns() - start_ns) / 1_000_000

        if isinstance(message, bytes):
            self._recorded_audio.extend(message)
            return AgentEvent(type=EventType.AGENT_AUDIO, timestamp_ms=now_ms, audio=message)

        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            return None

        event = data.get("event", "")

        if event == "media":
            payload = data.get("media", {}).get("payload", "")
            if not payload:
                return None
            audio_bytes = base64.b64decode(payload)
            self._recorded_audio.extend(audio_bytes)
            return AgentEvent(type=EventType.AGENT_AUDIO, timestamp_ms=now_ms, audio=audio_bytes)

        if event == "mark":
            mark_name = data.get("mark", {}).get("name", "")
            return AgentEvent(type=EventType.METADATA, timestamp_ms=now_ms, data={"mark": mark_name})

        if event == "dtmf":
            digit = data.get("dtmf", {}).get("digit", "")
            return AgentEvent(type=EventType.METADATA, timestamp_ms=now_ms, data={"dtmf": digit})

        if event == "clear":
            return AgentEvent(
                type=EventType.INTERRUPTION,
                timestamp_ms=now_ms,
                data={"source": "telnyx_clear"},
            )

        if event == "error":
            return AgentEvent(type=EventType.ERROR, timestamp_ms=now_ms, data=data.get("payload", data))

        if event == "stop":
            return AgentEvent(
                type=EventType.METADATA,
                timestamp_ms=now_ms,
                data={"stream_ended": True, "stream_id": data.get("stream_id", "")},
            )

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

        return AgentEvent(type=EventType.METADATA, timestamp_ms=now_ms, data=data)
