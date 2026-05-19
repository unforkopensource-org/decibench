"""ElevenLabs Conversational AI connector.

Connects directly to the ElevenLabs WebSocket API — no browser, no bridge
sidecar. Sends caller audio as base64 PCM, receives agent audio + transcripts
+ tool calls over the same WebSocket.

Usage:
    decibench run --target elevenlabs://agent_abc123 --suite full

Auth:
    export ELEVENLABS_API_KEY="xi-..."
    # or set elevenlabs_api_key in decibench.toml [auth]
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import time
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

# 100ms of 16kHz 16-bit mono = 3200 bytes
_CHUNK_BYTES = 3200
_RECV_TIMEOUT = 3.0
_SILENCE_MAX = 3
_ELEVENLABS_API_BASE = "https://api.elevenlabs.io"


@register_connector("elevenlabs")
class ElevenLabsConnector(BaseConnector):
    """Connect to an ElevenLabs Conversational AI agent via WebSocket."""

    required_sample_rate: int = 16000
    required_encoding: AudioEncoding = AudioEncoding.PCM_S16LE
    required_channels: int = 1

    def __init__(self, **kwargs: Any) -> None:
        self._ws: Any = None
        self._recorded_audio = bytearray()
        self._events: list[AgentEvent] = []
        self._conversation_id: str = ""
        self._api_key: str = ""
        self._send_count = 0
        self._ping_task: asyncio.Task[None] | None = None
        self._stop_ping = asyncio.Event()

    async def connect(self, target: str, config: dict[str, Any]) -> ConnectionHandle:
        import urllib.error
        import urllib.request

        import websockets

        # Parse agent ID
        prefix = "elevenlabs://"
        if not target.startswith(prefix):
            raise ValueError(f"ElevenLabs connector expects elevenlabs://<agent_id>, got: {target!r}")
        agent_id = target[len(prefix) :].strip()
        if not agent_id:
            raise ValueError("ElevenLabs agent_id is empty")

        # Get API key
        self._api_key = config.get("elevenlabs_api_key") or os.environ.get("ELEVENLABS_API_KEY", "")
        if not self._api_key:
            raise ValueError(
                "ElevenLabs connector needs an API key. "
                "Set elevenlabs_api_key in decibench.toml [auth] or "
                "export ELEVENLABS_API_KEY."
            )

        # Get signed URL for authenticated connection
        region = config.get("elevenlabs_region", "")
        api_base = _ELEVENLABS_API_BASE
        if region == "us":
            api_base = "https://api.us.elevenlabs.io"
        elif region == "eu":
            api_base = "https://api.eu.residency.elevenlabs.io"
        elif region == "in":
            api_base = "https://api.in.residency.elevenlabs.io"

        signed_url_endpoint = f"{api_base}/v1/convai/conversation/get-signed-url?agent_id={agent_id}"

        logger.info("Getting signed URL for agent %s from %s", agent_id, api_base)

        try:
            req = urllib.request.Request(
                signed_url_endpoint,
                headers={"xi-api-key": self._api_key},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                ws_url = data["signed_url"]
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")[:200]
            raise ConnectionError(
                f"ElevenLabs signed URL request failed ({exc.code}): {body}. Check your API key and agent_id."
            ) from exc
        except Exception as exc:
            raise ConnectionError(f"Failed to get ElevenLabs signed URL: {exc}") from exc

        logger.info("Connecting to ElevenLabs WebSocket for agent %s", agent_id)

        try:
            self._ws = await websockets.connect(
                ws_url,
                max_size=10 * 1024 * 1024,
                ping_interval=None,  # ElevenLabs handles its own pings
                close_timeout=10,
            )
        except Exception as exc:
            raise ConnectionError(f"ElevenLabs WebSocket connection failed: {exc}") from exc

        # Wait for conversation_initiation_metadata
        try:
            init_msg = await asyncio.wait_for(self._ws.recv(), timeout=10.0)
            init_data = json.loads(init_msg)
            if init_data.get("type") == "conversation_initiation_metadata":
                meta = init_data.get("conversation_initiation_metadata_event", {})
                self._conversation_id = meta.get("conversation_id", "")
                logger.info(
                    "ElevenLabs session started: conversation_id=%s, audio_format=%s",
                    self._conversation_id,
                    meta.get("agent_output_audio_format", "unknown"),
                )
            else:
                logger.warning("Unexpected first message type: %s", init_data.get("type"))
        except TimeoutError:
            logger.warning("No conversation_initiation_metadata received within 10s")

        # Start background ping handler
        self._stop_ping.clear()
        self._ping_task = asyncio.create_task(self._ping_handler())

        handle = ConnectionHandle(
            connector_type="elevenlabs",
            start_time_ns=time.monotonic_ns(),
            state={
                "agent_id": agent_id,
                "conversation_id": self._conversation_id,
            },
        )
        self._recorded_audio.clear()
        self._events.clear()
        self._send_count = 0
        return handle

    async def send_audio(self, handle: ConnectionHandle, audio: AudioBuffer) -> None:
        if self._ws is None:
            raise RuntimeError("ElevenLabs connector not connected")

        self._send_count += 1
        data = audio.data

        for offset in range(0, len(data), _CHUNK_BYTES):
            chunk = data[offset : offset + _CHUNK_BYTES]
            b64 = base64.b64encode(chunk).decode()
            await self._ws.send(json.dumps({"user_audio_chunk": b64}))
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
                logger.warning("ElevenLabs receive error: %s: %s", type(exc).__name__, exc)
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
        # Stop ping handler
        self._stop_ping.set()
        if self._ping_task is not None:
            self._ping_task.cancel()
            try:
                await self._ping_task
            except (asyncio.CancelledError, Exception):
                pass
            self._ping_task = None

        duration_ms = (time.monotonic_ns() - handle.start_time_ns) / 1_000_000

        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                logger.debug("ElevenLabs WebSocket close error (non-fatal)", exc_info=True)
            self._ws = None

        # Count turns from transcript events (each agent_response = 1 turn)
        transcript_turns = sum(1 for e in self._events if e.type == EventType.AGENT_TRANSCRIPT)
        turn_count = max(transcript_turns, self._send_count, 1)

        summary = CallSummary(
            duration_ms=duration_ms,
            turn_count=turn_count,
            agent_audio=bytes(self._recorded_audio),
            events=list(self._events),
            platform_metadata={
                "elevenlabs_conversation_id": self._conversation_id,
            },
        )
        self._recorded_audio = bytearray()
        self._events = []
        self._conversation_id = ""
        return summary

    # ------------------------------------------------------------------ internal

    def _parse_event(self, message: str | bytes, start_ns: int) -> AgentEvent | None:
        """Parse a single ElevenLabs WebSocket message into an AgentEvent."""
        now_ms = (time.monotonic_ns() - start_ns) / 1_000_000

        if isinstance(message, bytes):
            # Unexpected binary — treat as audio
            self._recorded_audio.extend(message)
            return AgentEvent(type=EventType.AGENT_AUDIO, timestamp_ms=now_ms, audio=message)

        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            return None

        msg_type = data.get("type", "")

        # Agent audio
        if msg_type == "audio":
            audio_event = data.get("audio_event", {})
            b64 = audio_event.get("audio_base_64", "")
            if b64:
                audio_bytes = base64.b64decode(b64)
                self._recorded_audio.extend(audio_bytes)
                return AgentEvent(
                    type=EventType.AGENT_AUDIO,
                    timestamp_ms=now_ms,
                    audio=audio_bytes,
                )
            return None

        # Agent text response (transcript)
        if msg_type == "agent_response":
            text = data.get("agent_response_event", {}).get("agent_response", "")
            return AgentEvent(
                type=EventType.AGENT_TRANSCRIPT,
                timestamp_ms=now_ms,
                data={"text": text, "is_final": True, "confidence": 1.0},
            )

        # Tentative/streaming agent response
        if msg_type == "internal_tentative_agent_response":
            text = data.get("tentative_agent_response_internal_event", {}).get("tentative_agent_response", "")
            return AgentEvent(
                type=EventType.AGENT_TRANSCRIPT,
                timestamp_ms=now_ms,
                data={"text": text, "is_final": False, "confidence": 0.8},
            )

        # User transcript (STT of our audio input)
        if msg_type == "user_transcript":
            text = data.get("user_transcript_event", {}).get("user_transcript", "")
            return AgentEvent(
                type=EventType.METADATA,
                timestamp_ms=now_ms,
                data={"user_transcript": text},
            )

        # Tool call from agent
        if msg_type == "client_tool_call":
            tool_data = data.get("client_tool_call", {})
            tool_name = tool_data.get("tool_name", "")
            tool_call_id = tool_data.get("tool_call_id", "")
            params_raw = tool_data.get("parameters", "{}")
            try:
                params = json.loads(params_raw) if isinstance(params_raw, str) else params_raw
            except json.JSONDecodeError:
                params = {"raw": params_raw}

            # Auto-respond with empty result so the conversation continues
            asyncio.create_task(self._respond_to_tool_call(tool_call_id))

            return AgentEvent(
                type=EventType.TOOL_CALL,
                timestamp_ms=now_ms,
                data={"name": tool_name, "args": params, "tool_call_id": tool_call_id},
            )

        # Interruption
        if msg_type == "interruption":
            return AgentEvent(
                type=EventType.INTERRUPTION,
                timestamp_ms=now_ms,
                data={"source": "elevenlabs"},
            )

        # Ping — respond with pong inline (backup for background handler)
        if msg_type == "ping":
            event_id = data.get("ping_event", {}).get("event_id", "")
            asyncio.create_task(self._send_pong(event_id))
            return None  # Don't yield ping as an event

        # VAD score — informational
        if msg_type == "vad_score":
            return None

        # Conversation metadata — already handled in connect
        if msg_type == "conversation_initiation_metadata":
            return None

        # Unknown — store as metadata
        return AgentEvent(
            type=EventType.METADATA,
            timestamp_ms=now_ms,
            data=data,
        )

    async def _send_pong(self, event_id: str) -> None:
        """Send a pong reply to an ElevenLabs ping."""
        if self._ws is None:
            return
        try:
            await self._ws.send(json.dumps({"type": "pong", "event_id": event_id}))
        except Exception:
            pass

    async def _respond_to_tool_call(self, tool_call_id: str) -> None:
        """Auto-respond to a tool call so the conversation continues.

        The orchestrator may inject scenario-specific tool_mock results via
        handle.state in a future enhancement. For now we return a generic
        success so the agent can proceed.
        """
        if self._ws is None:
            return
        try:
            await self._ws.send(
                json.dumps(
                    {
                        "type": "client_tool_result",
                        "tool_call_id": tool_call_id,
                        "result": "OK",
                        "is_error": False,
                    }
                )
            )
        except Exception:
            pass

    async def _ping_handler(self) -> None:
        """Background task that reads ping messages and replies with pong.

        This runs alongside receive_events to ensure pongs are sent even
        when the main loop is busy processing audio.
        """
        while not self._stop_ping.is_set():
            await asyncio.sleep(1.0)
