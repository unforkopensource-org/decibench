"""Evaluator-parity tests.

The promise: a call evaluated through the imported-call path (`evaluate_calls`,
the dashboard `/calls/{id}/evaluate` endpoint) gets the same Decibench Score
as the same call would get if it had been run live, modulo the inputs that
imported traces don't have (raw audio for MOS/STOI, real-time event timing).

These tests pin the canonical evaluator set and ensure both consumers
resolve to it.
"""

from __future__ import annotations

from decibench.evaluators import standard_stack
from decibench.evaluators.base import BaseEvaluator


def _names(evaluators: list[BaseEvaluator]) -> set[str]:
    return {e.name for e in evaluators}


def test_orchestrator_uses_standard_stack() -> None:
    """Orchestrator construction must go through standard_stack(), not a private list."""
    from decibench.config import DecibenchConfig
    from decibench.orchestrator import Orchestrator

    config = DecibenchConfig.defaults()
    orch = Orchestrator(config)
    expected = standard_stack(has_audio=True, has_events=True, has_judge=False)
    assert _names(orch._evaluators) == _names(expected)


def test_imported_call_evaluator_from_config_uses_standard_stack() -> None:
    """ImportedCallEvaluator.from_config must use the same factory."""
    from decibench.config import DecibenchConfig
    from decibench.replay.evaluate import ImportedCallEvaluator

    config = DecibenchConfig.defaults()
    ev = ImportedCallEvaluator.from_config(config, judge=None, has_audio=False)
    expected = standard_stack(has_audio=False, has_events=True, has_judge=False)
    assert _names(ev._evaluators) == _names(expected)


def test_standard_stack_filters_by_audio_availability() -> None:
    """Audio-requiring evaluators must be excluded when has_audio=False."""
    with_audio = _names(standard_stack(has_audio=True, has_events=True))
    without_audio = _names(standard_stack(has_audio=False, has_events=True))
    audio_only = with_audio - without_audio
    # MOS and STOI are the canonical audio-only metrics
    assert "mos" in audio_only
    assert "intelligibility_estimate" in audio_only


def test_standard_stack_filters_by_judge_availability() -> None:
    """Semantic evaluators are excluded when no judge is configured."""
    with_judge = _names(standard_stack(has_audio=True, has_events=True, has_judge=True))
    without_judge = _names(standard_stack(has_audio=True, has_events=True, has_judge=False))
    semantic = with_judge - without_judge
    assert "hallucination" in semantic
    # task_completion needs judge for the semantic check, but has deterministic
    # signals too — it's allowed without judge so it gets to emit those.
    # Just assert at least one semantic evaluator is filtered out.
    assert len(semantic) >= 1


def test_standard_stack_filters_by_event_availability() -> None:
    """Event-requiring evaluators are excluded when has_events=False."""
    with_events = _names(standard_stack(has_audio=True, has_events=True))
    without_events = _names(standard_stack(has_audio=True, has_events=False))
    event_only = with_events - without_events
    assert "latency" in event_only
    assert "interruption" in event_only


def test_canonical_stack_is_stable_for_v1() -> None:
    """The v1.0 canonical metric names — change requires a CHANGELOG entry.

    This test exists to make any change to the canonical evaluator stack
    surface in code review. If you add or remove an evaluator, you update
    this set + write a CHANGELOG entry under "Changed".
    """
    canonical = _names(standard_stack(has_audio=True, has_events=True, has_judge=True))
    assert canonical == {
        "wer",
        "latency",
        "mos",
        "intelligibility_estimate",
        "silence",
        "compliance",
        "task_completion",
        "hallucination",
        "interruption",
    }
