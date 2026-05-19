"""WebSocket auto-detect fail-fast invariant.

Previously, if the binary probe was rejected AND the follow-up reconnect to
text mode also failed, the connector silently kept the dead ``_ws`` attribute
and pretended it was in text mode. The first ``send_audio()`` raised
``RuntimeError("Not connected")`` with no hint about what happened.

v1 surfaces a real ``ConnectionError`` at ``connect()`` time, with an
actionable hint to override ``ws_protocol`` explicitly.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
import websockets

from decibench.connectors.websocket import WebSocketConnector


@pytest.mark.asyncio
async def test_failed_reconnect_raises_connection_error() -> None:
    """Binary-reject + reconnect-reject must raise ConnectionError, not silently downgrade.

    We stand up a server that:
      1. Accepts the first WS handshake.
      2. Closes the connection the instant it sees any binary frame.
      3. Stops listening immediately after — so the reconnect attempt fails.

    The connector must raise a `ConnectionError` with a hint to set
    ``ws_protocol`` explicitly.
    """

    async def handler(ws: Any) -> None:
        try:
            async for message in ws:
                if isinstance(message, bytes):
                    await ws.close()
                    return
        except Exception:
            return

    server = await websockets.serve(handler, "127.0.0.1", 0)
    port = next(iter(server.sockets)).getsockname()[1]

    async def close_server_soon() -> None:
        # Wait long enough for binary probe to land + close, then kill the
        # listener so the reconnect attempt fails.
        await asyncio.sleep(0.2)
        server.close()
        await server.wait_closed()

    close_task = asyncio.create_task(close_server_soon())
    try:
        connector = WebSocketConnector()
        with pytest.raises(ConnectionError, match="(reconnect|auto-detect|ws_protocol)"):
            await connector.connect(
                f"ws://127.0.0.1:{port}/",
                {"ws_protocol": "auto"},
            )
    finally:
        # close_server_soon already closed the server — just await the task
        # so the test loop doesn't leak it.
        await close_task


@pytest.mark.asyncio
async def test_explicit_protocol_skips_autodetect_probe() -> None:
    """Setting ws_protocol explicitly must skip the binary probe entirely.

    This is the user-facing escape hatch the error message tells them about.
    If a user passes ``ws_protocol='raw-pcm'``, we never call
    ``_auto_detect_protocol`` and the fail-fast path is irrelevant.
    """

    async def handler(ws: Any) -> None:
        async for _ in ws:
            pass

    server = await websockets.serve(handler, "127.0.0.1", 0)
    port = next(iter(server.sockets)).getsockname()[1]

    try:
        connector = WebSocketConnector()
        # Should connect without error and without sending a probe.
        handle = await connector.connect(
            f"ws://127.0.0.1:{port}/",
            {"ws_protocol": "raw-pcm"},
        )
        assert handle.state["protocol"] == "raw-pcm"
        await connector.disconnect(handle)
    finally:
        server.close()
        await server.wait_closed()
