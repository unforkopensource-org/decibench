from __future__ import annotations

from decibench.models import AgentEvent, EventType
from decibench.orchestrator import Orchestrator


def _event(text: str) -> AgentEvent:
    return AgentEvent(
        type=EventType.AGENT_TRANSCRIPT,
        timestamp_ms=0.0,
        data={"text": text, "is_final": True},
    )


def _metadata(kind: str) -> AgentEvent:
    return AgentEvent(
        type=EventType.METADATA,
        timestamp_ms=0.0,
        data={"kind": kind},
    )


def _turn_end() -> AgentEvent:
    return AgentEvent(
        type=EventType.TURN_END,
        timestamp_ms=0.0,
        data={"role": "agent"},
    )


def test_collapse_agent_transcript_events_handles_cumulative_updates() -> None:
    parts = Orchestrator._collapse_agent_transcript_events(
        [
            _event("Hi, "),
            _event("Hi, is "),
            _event("Hi, is this Angela?"),
        ]
    )

    assert parts == ["Hi, is this Angela?"]


def test_collapse_agent_transcript_events_prefers_best_partial_within_same_turn() -> None:
    parts = Orchestrator._collapse_agent_transcript_events(
        [
            _event("Hi there."),
            _event("How can I help?"),
        ]
    )

    assert parts == ["How can I help?"]


def test_collapse_agent_transcript_events_uses_turn_boundaries() -> None:
    parts = Orchestrator._collapse_agent_transcript_events(
        [
            _metadata("agent_start_talking"),
            _event("Hi"),
            _event("Hi, is this Angela?"),
            _turn_end(),
            _metadata("agent_start_talking"),
            _event("Hey"),
            _event("Hey, um, just checking in."),
            _turn_end(),
        ]
    )

    assert parts == ["Hi, is this Angela?", "Hey, um, just checking in."]


def test_collapse_agent_transcript_events_merges_boundary_split_partials() -> None:
    parts = Orchestrator._collapse_agent_transcript_events(
        [
            _metadata("agent_start_talking"),
            _event("Hi,"),
            _turn_end(),
            _metadata("agent_start_talking"),
            _event("Hi, is this Angela?"),
            _turn_end(),
        ]
    )

    assert parts == ["Hi, is this Angela?"]
