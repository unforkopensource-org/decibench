"""Telnyx Call Control media stream connector.

Connects to a Telnyx Call Control application's WebSocket media stream
endpoint and exchanges PCM16 audio in real time, enabling benchmarking
of Telnyx-powered voice agents without modification.

Telnyx's media stream works similarly to Twilio Media Streams: a
WebSocket carries bidirectional audio as base64-encoded PCM16 in JSON
envelope messages. The connector initiates a call via the Telnyx Call
Control API, receives media stream events on a webhook WebSocket, and
streams caller audio (TTS) while collecting agent audio responses.

Usage:
    decibench run --target telnyx://<destination_number> --suite quick

Audio format: PCM16 16kHz mono (native Decibench format), base64 encoded
in JSON messages on the WebSocket.

Configuration (decibench.toml [auth]):
    telnyx_api_key        — Telnyx API key (required)
    telnyx_connection_id — Call Control connection ID (required for outbound)
    telnyx_from          — Caller ID number (optional, defaults to config)
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import time
import uuid
from typing import TYPE_CHECKING, Any

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

# 20ms of PCM16 16kHz mono = 640 bytes (2 bytes per sample * 16000 * 0.02)
_PCM16_CHUNK_BYTES = 640
_RECV_TIMEOUT = 5.0
_SILENCE_MAX = 3


@register_connector("telnyx")
class TelnyxConnector(BaseConnector):
    """Telnyx Call Control media stream connector.

    Initiates an outbound call via the Telnyx Call Control API and streams
    audio through the WebSocket media stream protocol. Supports
    ``telnyx://<destination_number>`` target URIs.
    """

    required_sample_rate: int = 16000
    required_encoding: AudioEncoding = AudioEncoding.PCM_S16LE
    required_channels: int = 1

    def __init__(self, **kwargs: Any) -> None:
        self._ws: Any = None
        self._recorded_audio = bytearray()
        self._events: list[AgentEvent] = []
        self._send_count = 0
        self._call_control_id: str = ""
        self._stream_id: str = ""
        self._call_leg_id: str = ""
        self._api_key: str = ""
        self._connection_id: str = ""
        self._from_number: str = ""

    def _resolve_credentials(self, config: dict[str, Any]) -> None:
        """Resolve Telnyx credentials from config or environment."""
        self._api_key = (
            config.get("telnyx_api_key")
            or os.environ.get("TELNYX_API_KEY", "")
        )
        self._connection_id = (
            config.get("telnyx_connection_id")
            or os.environ.get("TELNYX_CONNECTION_ID", "")
        )
        self._from_number = (
            config.get("telnyx_from")
            or os.environ.get("TELNYX_FROM", "")
        )

    async def connect(self, target: str, config: dict[str, Any]) -> ConnectionHandle:
        import websockets

        prefix = "telnyx://"
        if not target.startswith(prefix):
            raise ValueError(
                f"Telnyx connector expects telnyx://<destination>, got: {target!r}"
            )

        self._resolve_credentials(config)

        destination = target[len(prefix):].strip()
        if not destination:
            raise ValueError("Telnyx connector: destination number is required")

        if not self._api_key:
            raise ValueError(
                "Telnyx connector needs an API key. Set telnyx_api_key in "
                "decibench.toml [auth] or export TELNYX_API_KEY."
            )

        # Generate stream/call identifiers
        self._stream_id = uuid.uuid4().hex
        self._call_leg_id = uuid.uuid4().hex

        # For WebSocket-based media streams, the target may be a direct WS URL
        # (telnyx://ws://host:port/path) or a phone number that requires
        # Call Control API to initiate.
        #
        # Two modes:
        #   1. telnyx://ws://host:port/path — direct WebSocket (testing/mocking)
        #   2. telnyx://+1234567890 — phone number, requires Call Control API
        if destination.startswith("ws://") or destination.startswith("wss://"):
            ws_url = destination
            self._call_control_id = ""
        else:
            # Phone number mode: use Call Control API to dial, then connect
            # to the media stream WebSocket returned in the call.answered event.
            ws_url = await self._initiate_call(destination, config)

        logger.info("Connecting to Telnyx media stream: %s", ws_url)

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
                f"Telnyx media stream connection to {ws_url} failed: {exc}. "
                "Check that your voice agent server is running."
            ) from exc

        # Send Telnyx media stream handshake
        # Telnyx WebSocket media stream starts with a session description
        connected_msg = {
            "event": "session_connected",
            "session_id": self._stream_id,
            "protocol": "TelnyxMediaStream",
            "version": "1.0.0",
        }
        await self._ws.send(json.dumps(connected_msg))

        start_msg = {
            "event": "stream_start",
            "stream_id": self._stream_id,
            "call_leg_id": self._call_leg_id,
            "media_format": {
                "encoding": "audio/pcm",
                "sample_rate": 16000,
                "channels": 1,
            },
        }
        await self._ws.send(json.dumps(start_msg))

        logger.info(
            "Telnyx session: stream_id=%s call_leg_id=%s",
            self._stream_id, self._call_leg_id,
        )

        handle = ConnectionHandle(
            connector_type="telnyx",
            start_time_ns=time.monotonic_ns(),
            state={
                "ws_url": ws_url,
                "stream_id": self._stream_id,
                "call_leg_id": self._call_leg_id,
                "call_control_id": self._call_control_id,
                "destination": destination,
            },
        )
        self._recorded_audio.clear()
        self._events.clear()
        self._send_count = 0
        return handle

    async def _initiate_call(self, destination: str, config: dict[str, Any]) -> str:
        """Initiate an outbound call via Telnyx Call Control API.

        Uses the Telnyx REST API to dial the destination number and
        negotiate a WebSocket media stream. Returns the WS URL for
        the media stream.
        """
        import httpx

        if not self._connection_id:
            raise ValueError(
                "Telnyx connector needs a connection_id for outbound calls. "
                "Set telnyx_connection_id in decibench.toml [auth] or "
                "export TELNYX_CONNECTION_ID."
            )

        base_url = "https://api.telnyx.com/v2"

        # Use the Call Control API to initiate a call with media stream
        # The Telnyx Call Control API supports WebSocket media streams
        # via the `media_stream` parameter on call creation.
        call_payload = {
            "connection_id": self._connection_id,
            "to": destination,
            "from": self._from_number or "",
            "media_stream": {
                "enable": True,
                "sample_rate": 16000,
                "encoding": "audio/pcm",
            },
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{base_url}/calls",
                json=call_payload,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )

        if resp.status_code not in (200, 201):
            raise ConnectionError(
                f"Telnyx call initiation failed (HTTP {resp.status_code}): "
                f"{resp.text}"
            )

        data = resp.json()
        call_data = data.get("data", {})
        self._call_control_id = call_data.get("call_control_id", "")

        # The media stream WebSocket URL is returned in the response
        # when media_stream is enabled on the call
        stream_url = call_data.get("media_stream", {}).get("ws_url", "")
        self._call_leg_id = call_data.get("call_leg_id", "")

        if not stream_url:
            # Fallback: construct WS URL from call control ID
            # (Telnyx returns the WS URL in the call.answered webhook
            # in production, but for testing we construct it)
            stream_url = f"wss://api.telnyx.com/v2/calls/{self._call_control_id}/media_stream"

        return stream_url

    async def send_audio(self, handle: ConnectionHandle, audio: AudioBuffer) -> None:
        if self._ws is None:
            raise RuntimeError("Telnyx connector not connected")

        self._send_count += 1
        data = audio.data
        chunk_num = 0
        timestamp_ms = 0

        for offset in range(0, len(data), _PCM16_CHUNK_BYTES):
            chunk = data[offset : offset + _PCM16_CHUNK_BYTES]
            chunk_num += 1

            media_msg = {
                "event": "media",
                "stream_id": self._stream_id,
                "media": {
                    "track": "inbound",
                    "chunk": chunk_num,
                    "timestamp": timestamp_ms,
                    "payload": base64.b64encode(chunk).decode(),
                },
            }
            await self._ws.send(json.dumps(media_msg))

            # 20ms per chunk at 16kHz
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
                logger.warning("Telnyx receive error: %s: %s", type(exc).__name__, exc)
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

        # Send stream stop message
        if self._ws is not None:
            try:
                stop_msg = {
                    "event": "stream_stop",
                    "stream_id": self._stream_id,
                    "call_leg_id": self._call_leg_id,
                }
                await self._ws.send(json.dumps(stop_msg))
            except Exception:
                pass

            try:
                await self._ws.close()
            except Exception:
                logger.debug("Telnyx WebSocket close error (non-fatal)", exc_info=True)
            self._ws = None

        # If we initiated the call via Call Control API, hang up
        if self._call_control_id:
            await self._hangup_call()

        turn_count = max(self._send_count, 1)

        summary = CallSummary(
            duration_ms=duration_ms,
            turn_count=turn_count,
            agent_audio=bytes(self._recorded_audio),
            events=list(self._events),
            platform_metadata={
                "telnyx_stream_id": self._stream_id,
                "telnyx_call_leg_id": self._call_leg_id,
                "telnyx_call_control_id": self._call_control_id,
            },
        )
        self._recorded_audio = bytearray()
        self._events = []
        return summary

    async def _hangup_call(self) -> None:
        """Hang up the call via Telnyx Call Control API."""
        import httpx

        base_url = "https://api.telnyx.com/v2"

        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"{base_url}/calls/{self._call_control_id}/actions/hangup",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    timeout=10.0,
                )
        except Exception:
            logger.debug("Telnyx hangup error (non-fatal)", exc_info=True)

    # ------------------------------------------------------------------ internal

    def _parse_event(self, message: str | bytes, start_ns: int) -> AgentEvent | None:
        """Parse a message from the Telnyx media stream."""
        now_ms = (time.monotonic_ns() - start_ns) / 1_000_000

        if isinstance(message, bytes):
            # Raw binary audio
            self._recorded_audio.extend(message)
            return AgentEvent(type=EventType.AGENT_AUDIO, timestamp_ms=now_ms, audio=message)

        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            return None

        event = data.get("event", "")

        # Agent audio — outbound media from the agent
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

        # Stream ended
        if event == "stream_stop" or event == "session_ended":
            return AgentEvent(
                type=EventType.METADATA,
                timestamp_ms=now_ms,
                data={"stream_ended": True, "stream_id": data.get("stream_id", "")},
            )

        # DTMF digits
        if event == "dtmf":
            digit = data.get("dtmf", {}).get("digit", "")
            return AgentEvent(
                type=EventType.METADATA,
                timestamp_ms=now_ms,
                data={"dtmf": digit},
            )

        # Transcription (if Telnyx speech recognition is enabled on the stream)
        if "transcript" in data or "text" in data:
            text = data.get("transcript", data.get("text", ""))
            return AgentEvent(
                type=EventType.AGENT_TRANSCRIPT,
                timestamp_ms=now_ms,
                data={"text": text, "is_final": True},
            )

        # Tool / function calls from the agent
        if "tool_call" in data or "function_call" in data:
            return AgentEvent(
                type=EventType.TOOL_CALL,
                timestamp_ms=now_ms,
                data=data.get("tool_call", data.get("function_call", data)),
            )

        # Intention / barge-in
        if event == "clear" or event == "interrupt":
            return AgentEvent(
                type=EventType.INTERRUPTION,
                timestamp_ms=now_ms,
                data={"source": "telnyx_interrupt"},
            )

        # Unknown event — store as metadata
        return AgentEvent(
            type=EventType.METADATA,
            timestamp_ms=now_ms,
            data=data,
        )
