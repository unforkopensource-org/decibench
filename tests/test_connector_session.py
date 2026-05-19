"""ConnectorSession lifecycle invariants.

The orchestrator previously called ``connector.disconnect()`` twice on the
happy path — once to collect the summary, once in the surrounding
``finally``. For connectors that reset their buffers in ``disconnect()``,
the second call returned an empty ``CallSummary``, silently corrupting the
data downstream evaluators saw.

These tests pin the contract: every connector, on every code path, sees
exactly one connect + exactly one disconnect.
"""

from __future__ import annotations

from typing import Any

import pytest

from decibench.connectors.base import BaseConnector
from decibench.connectors.session import ConnectorSession
from decibench.models import (
    AgentEvent,
    AudioBuffer,
    CallSummary,
    ConnectionHandle,
    EventType,
)


class _CountingConnector(BaseConnector):
    """Fake connector that counts connect/disconnect calls."""

    def __init__(self, **kwargs: Any) -> None:
        self.connect_count = 0
        self.disconnect_count = 0
        self.send_count = 0

    async def connect(self, target: str, config: dict[str, Any]) -> ConnectionHandle:
        self.connect_count += 1
        return ConnectionHandle(connector_type="counting")

    async def send_audio(self, handle: ConnectionHandle, audio: AudioBuffer) -> None:
        self.send_count += 1

    async def receive_events(self, handle: ConnectionHandle):  # type: ignore[no-untyped-def]
        return
        yield  # pragma: no cover

    async def disconnect(self, handle: ConnectionHandle) -> CallSummary:
        self.disconnect_count += 1
        # Simulate a real connector that surfaces its events only ONCE.
        # If this is called twice, the second call gets empty data — exactly
        # the bug the session wrapper prevents.
        return CallSummary(
            duration_ms=100.0,
            turn_count=1,
            events=[AgentEvent(type=EventType.AGENT_AUDIO, timestamp_ms=10.0)]
            if self.disconnect_count == 1
            else [],
        )


@pytest.mark.asyncio
async def test_session_calls_disconnect_exactly_once_on_happy_path() -> None:
    conn = _CountingConnector()
    session = ConnectorSession(conn, "test", {})
    await session.connect()
    summary = await session.disconnect()
    await session.disconnect()  # defensive double-call (the historical bug)
    await session.disconnect()  # belt-and-suspenders
    assert conn.connect_count == 1
    assert conn.disconnect_count == 1
    assert summary is not None
    assert len(summary.events) == 1


@pytest.mark.asyncio
async def test_session_context_manager_is_idempotent_on_exit() -> None:
    conn = _CountingConnector()
    async with ConnectorSession(conn, "test", {}) as session:
        summary = await session.disconnect()  # explicit collect
        assert summary is not None
    # __aexit__ also called disconnect — must still be exactly one connector call.
    assert conn.disconnect_count == 1


@pytest.mark.asyncio
async def test_session_handles_disconnect_exception_without_re_raising() -> None:
    """If the connector raises during disconnect, the session returns None and stays disposed.

    This matters because the orchestrator's `finally` block must not be able
    to crash the run by re-raising a cleanup error.
    """

    class _RaisingConnector(_CountingConnector):
        async def disconnect(self, handle: ConnectionHandle) -> CallSummary:
            self.disconnect_count += 1
            raise RuntimeError("teardown blew up")

    conn = _RaisingConnector()
    session = ConnectorSession(conn, "test", {})
    await session.connect()
    summary = await session.disconnect()
    assert summary is None  # the session swallowed the error
    # A second call must NOT retry — the session is disposed.
    await session.disconnect()
    assert conn.disconnect_count == 1


@pytest.mark.asyncio
async def test_session_rejects_double_connect() -> None:
    conn = _CountingConnector()
    session = ConnectorSession(conn, "test", {})
    await session.connect()
    with pytest.raises(RuntimeError, match="connect.*twice"):
        await session.connect()


@pytest.mark.asyncio
async def test_session_disconnect_before_connect_is_safe() -> None:
    conn = _CountingConnector()
    session = ConnectorSession(conn, "test", {})
    assert await session.disconnect() is None
    assert conn.connect_count == 0
    assert conn.disconnect_count == 0
