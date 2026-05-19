"""Evaluators — three-layer evaluation: deterministic, statistical, semantic.

The canonical evaluator set is exposed via :func:`standard_stack`. Both the
live ``Orchestrator`` and the imported-call ``ImportedCallEvaluator`` resolve
their evaluator list through this factory so a call evaluated offline gets
the same Decibench Score as the same call run live.

Each evaluator advertises three capability requirements:

- ``requires_audio``  — needs ``CallSummary.agent_audio`` to compute
- ``requires_events`` — needs the connector event stream
- ``requires_judge``  — needs an LLM judge

``standard_stack`` filters by these traits, so we never silently run an
evaluator on inputs it can't measure (which would otherwise emit a noisy
zero-score metric).
"""

from __future__ import annotations

from decibench.evaluators.base import BaseEvaluator
from decibench.evaluators.compliance import ComplianceEvaluator
from decibench.evaluators.hallucination import HallucinationEvaluator
from decibench.evaluators.interruption import InterruptionEvaluator
from decibench.evaluators.latency import LatencyEvaluator
from decibench.evaluators.mos import MOSEvaluator
from decibench.evaluators.silence import SilenceEvaluator
from decibench.evaluators.stoi import STOIEvaluator
from decibench.evaluators.task import TaskCompletionEvaluator
from decibench.evaluators.wer import WEREvaluator

__all__ = ["BaseEvaluator", "standard_stack"]


def standard_stack(
    *,
    has_audio: bool = True,
    has_events: bool = True,
    has_judge: bool = False,
) -> list[BaseEvaluator]:
    """Return the canonical evaluator set, filtered to what the inputs support.

    Args:
        has_audio: ``True`` if the source provides raw agent audio. False for
            text-only replays.
        has_events: ``True`` if the source has a per-turn event timeline. False
            for plain-transcript imports (rare; most importers normalize an
            event stream).
        has_judge: ``True`` if an LLM judge is configured.

    Returns:
        Evaluators in deterministic → statistical → semantic order, each one
        whose declared requirements are all satisfied.
    """
    candidates: list[BaseEvaluator] = [
        WEREvaluator(),  # deterministic, transcript-only
        LatencyEvaluator(),  # deterministic, needs events
        MOSEvaluator(),  # statistical, needs audio
        STOIEvaluator(),  # statistical, needs audio
        SilenceEvaluator(),  # statistical, audio + events optional
        ComplianceEvaluator(),  # deterministic, transcript + events
        TaskCompletionEvaluator(),  # semantic (best with judge)
        HallucinationEvaluator(),  # semantic
        InterruptionEvaluator(),  # deterministic, needs events
    ]
    return [
        e
        for e in candidates
        if (has_audio or not e.requires_audio)
        and (has_events or not e.requires_events)
        and (has_judge or not e.requires_judge)
    ]
