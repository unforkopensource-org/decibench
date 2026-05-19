"""Real-time send-pacing invariants.

Earlier versions of the WS and process connectors paced caller audio chunks
faster than real-time (WS at ~5x, process at 2x). For a 1s utterance the
agent received the whole thing in 200ms wall-time, which silently biased
every latency / interruption / TTFW measurement low.

v1 ships ``ConnectorConfig.send_speed`` (default 1.0 = real-time, 0 =
burst). These tests pin both behaviors so a future "optimization" can't
silently reintroduce the bias.
"""

from __future__ import annotations

import time
from typing import Any

import pytest
import websockets

from decibench.connectors.websocket import WebSocketConnector
from decibench.models import AudioBuffer

# A 500ms PCM payload at 16kHz mono = 16000 bytes (5 x 100ms chunks).
_PAYLOAD = b"\x00\x01" * 8000


async def _spin_up_echo_server(timestamps: list[float]) -> tuple[Any, int]:
    """Open a localhost WS server that records arrival times of binary frames."""

    async def handler(ws: Any) -> None:
        # Acknowledge the connection with a JSON frame so the auto-detect
        # path classifies the server quickly. We do NOT exercise auto-detect
        # here — protocol is set to raw-pcm.
        async for message in ws:
            if isinstance(message, bytes):
                timestamps.append(time.monotonic())

    server = await websockets.serve(handler, "127.0.0.1", 0)
    port = next(iter(server.sockets)).getsockname()[1]
    return server, port


async def _run_connector_send(send_speed: float, timestamps: list[float]) -> None:
    server, port = await _spin_up_echo_server(timestamps)
    try:
        connector = WebSocketConnector()
        handle = await connector.connect(
            f"ws://127.0.0.1:{port}/",
            {"ws_protocol": "raw-pcm", "send_speed": send_speed},
        )
        try:
            await connector.send_audio(handle, AudioBuffer(data=_PAYLOAD, sample_rate=16000))
        finally:
            await connector.disconnect(handle)
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_ws_default_pacing_is_real_time() -> None:
    """500ms of payload at send_speed=1.0 should take ~500ms to deliver.

    100ms chunks, 5 chunks, 100ms gap between → roughly 500ms wall-time. We
    allow a generous tolerance because the test is asyncio-bound and event
    loop scheduling jitter is non-trivial, but we still assert it's at least
    real-ish-time (≥ 350ms) and not the old 5x-real-time (~100ms).
    """
    timestamps: list[float] = []
    t0 = time.monotonic()
    await _run_connector_send(send_speed=1.0, timestamps=timestamps)
    elapsed_ms = (time.monotonic() - t0) * 1000

    # Server must have observed all five chunks
    assert len(timestamps) >= 5, f"expected ≥5 chunks at server, got {len(timestamps)}"
    # 5 chunks paced at 100ms each → must take ≥ ~350ms wall-time (with slack)
    assert elapsed_ms >= 350, f"pacing too fast: {elapsed_ms:.0f}ms (regression toward burst mode)"


@pytest.mark.asyncio
async def test_ws_burst_mode_skips_pacing() -> None:
    """send_speed=0 must NOT sleep between chunks — used by smoke tests / demo.

    Same payload as the real-time test, but should finish in well under 200ms.
    """
    timestamps: list[float] = []
    t0 = time.monotonic()
    await _run_connector_send(send_speed=0.0, timestamps=timestamps)
    elapsed_ms = (time.monotonic() - t0) * 1000

    assert elapsed_ms < 250, f"burst mode still pacing: {elapsed_ms:.0f}ms"


@pytest.mark.asyncio
async def test_ws_send_speed_2x_halves_wall_time() -> None:
    """send_speed=2.0 halves the per-chunk sleep, so 500ms of payload → ~250ms wall-time."""
    timestamps: list[float] = []
    t0 = time.monotonic()
    await _run_connector_send(send_speed=2.0, timestamps=timestamps)
    elapsed_ms = (time.monotonic() - t0) * 1000

    # Allow wide tolerance — point is "faster than real-time but still paced"
    assert 100 <= elapsed_ms < 400, f"2x pacing wall-time off: {elapsed_ms:.0f}ms"


@pytest.mark.asyncio
async def test_process_connector_honors_send_speed_burst() -> None:
    """Process connector burst mode finishes without per-chunk sleep.

    We spawn a no-op `cat`-style subprocess that drains stdin so the
    connector's stdin.write doesn't backpressure us. Real-time pacing for
    this connector is tested at the orchestrator level; here we just confirm
    the knob plumbs through.
    """
    from decibench.connectors.process import ProcessConnector

    connector = ProcessConnector()
    # `cat` reads stdin and writes to stdout; sufficient as a black hole + echo.
    handle = await connector.connect("exec:cat", {"send_speed": 0.0})
    try:
        t0 = time.monotonic()
        await connector.send_audio(handle, AudioBuffer(data=_PAYLOAD, sample_rate=16000))
        elapsed_ms = (time.monotonic() - t0) * 1000
        assert elapsed_ms < 250, f"process burst mode still pacing: {elapsed_ms:.0f}ms"
    finally:
        await connector.disconnect(handle)


def test_send_speed_is_in_connector_config_defaults() -> None:
    """Smoke: the new knob is wired into ConnectorConfig."""
    from decibench.config import ConnectorConfig

    cfg = ConnectorConfig()
    assert cfg.send_speed == 1.0  # real-time default
