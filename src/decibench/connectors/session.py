"""ConnectorSession — single-shot connect/disconnect helper.

Earlier orchestrator code called ``connector.disconnect(handle)`` once in the
happy path and once again in the surrounding ``finally``. For connectors that
collect a ``CallSummary`` in ``disconnect()`` and reset their internal
buffers, the second call returned an empty summary, and any caller relying
on its events lost data.

``ConnectorSession`` makes that bug impossible: ``disconnect()`` is
idempotent at the session level, so the orchestrator can call it defensively
in cleanup without double-billing the connector.

Usage::

    async with ConnectorSession(connector, target, config) as session:
        await session.send_audio(audio)
        async for event in session.receive_events():
            ...
        summary = await session.disconnect()   # explicit; returns CallSummary
    # __aexit__ also calls disconnect() but it's a no-op since we already did.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from decibench.connectors.base import BaseConnector
    from decibench.models import AgentEvent, AudioBuffer, CallSummary, ConnectionHandle

logger = logging.getLogger(__name__)


class ConnectorSession:
    """Lifecycle wrapper that guarantees ``disconnect`` happens exactly once."""

    def __init__(
        self,
        connector: BaseConnector,
        target: str,
        config: dict[str, Any],
    ) -> None:
        self._connector = connector
        self._target = target
        self._config = config
        self._handle: ConnectionHandle | None = None
        self._summary: CallSummary | None = None
        self._disconnected = False

    @property
    def connector(self) -> BaseConnector:
        return self._connector

    @property
    def handle(self) -> ConnectionHandle:
        if self._handle is None:
            raise RuntimeError("ConnectorSession used before connect()")
        return self._handle

    async def connect(self) -> ConnectionHandle:
        if self._handle is not None:
            raise RuntimeError("ConnectorSession.connect() called twice")
        self._handle = await self._connector.connect(self._target, self._config)
        return self._handle

    async def send_audio(self, audio: AudioBuffer) -> None:
        await self._connector.send_audio(self.handle, audio)

    async def receive_events(self) -> AsyncIterator[AgentEvent]:
        async for event in self._connector.receive_events(self.handle):
            yield event

    async def disconnect(self) -> CallSummary | None:
        """Collect the summary exactly once.

        Returns the cached ``CallSummary`` from the first call and ``None`` on
        any subsequent call. The orchestrator should treat a ``None`` return
        as "already-collected — use the value you got before."
        """
        if self._disconnected:
            return None
        self._disconnected = True
        if self._handle is None:
            return None
        try:
            self._summary = await self._connector.disconnect(self._handle)
            return self._summary
        except Exception as exc:
            # Log but don't re-raise: the caller is past the point of being
            # able to recover the session.
            logger.warning(
                "Connector %s disconnect raised: %s",
                type(self._connector).__name__,
                exc,
            )
            return None

    @property
    def summary(self) -> CallSummary | None:
        return self._summary

    async def __aenter__(self) -> ConnectorSession:
        await self.connect()
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self.disconnect()
