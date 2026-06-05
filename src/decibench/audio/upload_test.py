"""Uploaded-audio agent test runner.

This path lets the dashboard send a real caller recording to a configured
voice-agent target, capture the agent response, and score it with the same
canonical evaluator stack used by live suite runs.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from decibench.audio.transcode import ensure_mono, transcode
from decibench.connectors.registry import get_connector
from decibench.connectors.session import ConnectorSession
from decibench.evaluators import standard_stack
from decibench.evaluators.score import _METRIC_CATEGORIES, DecibenchScorer
from decibench.models import (
    AgentEvent,
    AudioBuffer,
    AudioEncoding,
    CallSummary,
    CallTrace,
    ConversationTurn,
    EvalResult,
    EventType,
    MetricResult,
    Scenario,
    SuccessCriterion,
    TraceSpan,
    TranscriptResult,
    TranscriptSegment,
    TurnExpectation,
)
from decibench.providers.registry import get_judge, get_stt

if TYPE_CHECKING:
    from decibench.config import DecibenchConfig


@dataclass
class UploadedAudioTestSpec:
    target: str
    audio_path: Path
    filename: str
    content_type: str | None = None
    mode: str = "deterministic"
    caller_text: str = ""
    goal: str = ""
    must_include: list[str] = field(default_factory=list)
    must_not_say: list[str] = field(default_factory=list)
    max_latency_ms: int | None = None


@dataclass
class UploadedAudioTestOutcome:
    trace: CallTrace
    evaluation: EvalResult
    scenario: Scenario
    audio_duration_ms: float
    agent_audio_bytes: int


def decode_audio_file(path: Path) -> AudioBuffer:
    """Decode a user-uploaded audio file to mono PCM16.

    ``soundfile`` covers WAV/FLAC/OGG on most installs. ``librosa`` is used as
    a fallback for formats such as MP3 where the local soundfile backend may
    not have a decoder.
    """
    try:
        import soundfile as sf

        samples, sample_rate = sf.read(path, dtype="float32", always_2d=True)
        samples = samples.mean(axis=1)
    except Exception:
        import librosa

        samples, sample_rate = librosa.load(str(path), sr=None, mono=True)

    if samples.size == 0:
        msg = "Uploaded audio is empty."
        raise ValueError(msg)

    samples = np.asarray(samples, dtype=np.float32)
    samples = np.nan_to_num(samples, nan=0.0, posinf=0.0, neginf=0.0)
    pcm16 = (np.clip(samples, -1.0, 1.0) * 32767.0).astype("<i2")
    return AudioBuffer(
        data=pcm16.tobytes(),
        sample_rate=int(sample_rate),
        channels=1,
        bit_depth=16,
        encoding=AudioEncoding.PCM_S16LE,
    )


async def run_uploaded_audio_test(
    config: DecibenchConfig,
    spec: UploadedAudioTestSpec,
) -> UploadedAudioTestOutcome:
    """Send an uploaded caller recording to a voice agent and evaluate it."""
    caller_audio = decode_audio_file(spec.audio_path)
    connector = get_connector(spec.target)
    connector_audio = transcode(
        ensure_mono(caller_audio),
        connector.required_sample_rate,
        connector.required_encoding,
    )
    if connector.required_channels == 1:
        connector_audio = connector_audio.model_copy(update={"channels": 1})

    scenario = _build_uploaded_audio_scenario(spec, caller_audio.duration_ms)
    summary, spans = await _run_agent_turn(config, spec, connector_audio, connector)

    stt = None
    try:
        if spec.target not in ("demo", "demo://"):
            stt = get_stt(config.providers.stt)
        transcript = await _build_transcript(summary, stt, connector_audio, spec.caller_text)
    finally:
        if stt is not None and hasattr(stt, "close"):
            await stt.close()

    trace = _build_trace(spec, summary, transcript, spans, caller_audio, connector_audio)

    judge = None
    try:
        if spec.mode != "deterministic" and config.has_judge:
            judge = get_judge(
                config.providers.judge,
                model=config.providers.judge_model,
                api_key=config.providers.judge_api_key,
                temperature=config.evaluation.judge_temperature,
                judge_runs=config.evaluation.judge_runs,
            )
        evaluation = await _evaluate_uploaded_call(config, scenario, summary, transcript, judge, caller_audio)
    finally:
        if judge is not None and hasattr(judge, "close"):
            await judge.close()

    return UploadedAudioTestOutcome(
        trace=trace,
        evaluation=evaluation,
        scenario=scenario,
        audio_duration_ms=caller_audio.duration_ms,
        agent_audio_bytes=len(summary.agent_audio),
    )


async def _run_agent_turn(
    config: DecibenchConfig,
    spec: UploadedAudioTestSpec,
    caller_audio: AudioBuffer,
    connector: Any,
) -> tuple[CallSummary, list[TraceSpan]]:
    connector_cfg = config.connector.model_dump()
    connector_overrides = {k: v for k, v in connector_cfg.items() if v}
    connector_config: dict[str, Any] = {
        **config.auth.model_dump(),
        "sample_rate": config.audio.sample_rate,
        "channels": config.audio.channels,
        "bit_depth": config.audio.bit_depth,
        **connector_overrides,
    }

    spans: list[TraceSpan] = []
    session = ConnectorSession(connector, spec.target, connector_config)
    handle = await session.connect()
    if spec.caller_text:
        handle.state["caller_text_1"] = spec.caller_text

    try:
        turn_start = time.monotonic()
        await connector.send_audio(handle, caller_audio)
        send_duration = (time.monotonic() - turn_start) * 1000
        caller_end_ms = (time.monotonic_ns() - handle.start_time_ns) / 1_000_000
        caller_end = AgentEvent(
            type=EventType.CALLER_AUDIO_END,
            timestamp_ms=caller_end_ms,
            data={"turn_index": 0, "source": "uploaded_audio"},
        )

        received_events: list[AgentEvent] = []
        async for event in connector.receive_events(handle):
            received_events.append(event)

        spans.append(
            TraceSpan(
                name="uploaded_audio_send",
                start_ms=max(0.0, caller_end_ms - send_duration),
                end_ms=caller_end_ms,
                duration_ms=send_duration,
                turn_index=0,
                metadata={"filename": spec.filename},
            )
        )

        summary = await session.disconnect() or CallSummary(duration_ms=0, turn_count=1)
        event_keys = {_event_key(event) for event in summary.events}
        merged_events = list(summary.events) + [caller_end]
        for event in received_events:
            key = _event_key(event)
            if key not in event_keys:
                merged_events.append(event)
        merged_events.sort(key=lambda e: e.timestamp_ms)
        return summary.model_copy(
            update={
                "turn_count": max(summary.turn_count, 1),
                "events": merged_events,
                "spans": [*summary.spans, *spans],
            }
        ), spans
    finally:
        await session.disconnect()


async def _build_transcript(
    summary: CallSummary,
    stt: Any | None,
    caller_audio: AudioBuffer,
    caller_text: str,
) -> TranscriptResult:
    from decibench.orchestrator import Orchestrator

    segments: list[TranscriptSegment] = []
    if caller_text.strip():
        segments.append(
            TranscriptSegment(
                role="caller",
                text=caller_text.strip(),
                start_ms=0.0,
                end_ms=caller_audio.duration_ms,
            )
        )

    agent_parts = Orchestrator._collapse_agent_transcript_events(summary.events)
    if agent_parts:
        segments.extend(TranscriptSegment(role="agent", text=text) for text in agent_parts)
    elif stt is not None and summary.agent_audio:
        agent_transcript = await stt.transcribe(AudioBuffer(data=summary.agent_audio))
        for segment in agent_transcript.segments:
            segments.append(segment.model_copy(update={"role": "agent"}))
        if not agent_transcript.segments and agent_transcript.text:
            segments.append(TranscriptSegment(role="agent", text=agent_transcript.text))

    text = "\n".join(f"{segment.role}: {segment.text}" for segment in segments if segment.text)
    return TranscriptResult(
        text=text,
        segments=segments,
        language="en",
        duration_ms=summary.duration_ms,
    )


async def _evaluate_uploaded_call(
    config: DecibenchConfig,
    scenario: Scenario,
    summary: CallSummary,
    transcript: TranscriptResult,
    judge: Any | None,
    caller_audio: AudioBuffer,
) -> EvalResult:
    evaluators = standard_stack(
        has_audio=bool(summary.agent_audio),
        has_events=True,
        has_judge=judge is not None,
    )
    all_metrics: dict[str, MetricResult] = {}
    bands = config.scoring.latency_bands
    eval_context: dict[str, Any] = {
        "judge": judge,
        "config": config,
        "latency_bands": bands,
        "p50_max_ms": bands.p50[1],
        "p95_max_ms": bands.p95[1],
        "p99_max_ms": bands.p99[1],
        "ttfw_max_ms": bands.ttfw[1],
        "reference_audio": caller_audio.data,
        "is_uploaded_audio_test": True,
    }

    start = time.monotonic()
    for evaluator in evaluators:
        if evaluator.requires_judge and judge is None:
            continue
        if getattr(evaluator, "requires_audio", False) and not summary.agent_audio:
            continue
        metrics = await evaluator.evaluate(scenario, summary, transcript, eval_context)
        for metric in metrics:
            all_metrics[metric.name] = metric

    scoring_cfg = config.scoring
    failures = [
        f"{m.name}: {m.value} (threshold: {m.threshold})"
        for m in all_metrics.values()
        if not m.passed and scoring_cfg.get_policy(m.name) == "blocking"
    ]
    all_failures = [f"{m.name}: {m.value} (threshold: {m.threshold})" for m in all_metrics.values() if not m.passed]
    failed_categories = {
        _METRIC_CATEGORIES[m.name]
        for m in all_metrics.values()
        if not m.passed and m.name in _METRIC_CATEGORIES
    }
    passed = not failures

    scorer = DecibenchScorer()
    tmp = EvalResult(scenario_id=scenario.id, passed=passed, score=0.0, metrics=all_metrics)
    score, _ = scorer.calculate(
        [tmp],
        config.scoring.weights,
        has_judge=(judge is not None),
        policies=scoring_cfg,
    )

    return EvalResult(
        scenario_id=scenario.id,
        passed=passed,
        score=score,
        metrics=all_metrics,
        failures=all_failures,
        failure_summary=sorted(failed_categories),
        latency={k: m.value for k, m in all_metrics.items() if "latency" in k or "ttfw" in k or "gap" in k},
        duration_ms=(time.monotonic() - start) * 1000,
        transcript=[segment.model_dump(mode="json") for segment in transcript.segments],
        spans=summary.spans,
    )


def _build_uploaded_audio_scenario(spec: UploadedAudioTestSpec, duration_ms: float) -> Scenario:
    expect = TurnExpectation(
        must_include=spec.must_include,
        must_not_say=spec.must_not_say,
        max_latency_ms=spec.max_latency_ms,
    )
    criteria = []
    if spec.goal:
        criteria.append(SuccessCriterion(type="task_completion", description=spec.goal, check="hybrid"))
    if spec.must_include:
        criteria.append(
            SuccessCriterion(
                type="custom",
                description="Agent response includes: " + ", ".join(spec.must_include),
                check="deterministic",
            )
        )
    if spec.must_not_say:
        criteria.append(
            SuccessCriterion(
                type="custom",
                description="Agent response avoids: " + ", ".join(spec.must_not_say),
                check="deterministic",
            )
        )

    scenario_id = f"audio-upload-{uuid.uuid4().hex[:12]}"
    caller_text = spec.caller_text.strip() or f"[uploaded audio: {spec.filename}]"
    return Scenario(
        id=scenario_id,
        description=f"Uploaded audio test from {spec.filename}",
        tags=["uploaded-audio", "dashboard"],
        metadata={
            "filename": spec.filename,
            "content_type": spec.content_type or "",
            "audio_duration_ms": round(duration_ms, 1),
            "source": "dashboard_upload",
        },
        conversation=[
            ConversationTurn(role="caller", text=caller_text),
            ConversationTurn(role="agent", expect=expect),
        ],
        goal=spec.goal or None,
        success_criteria=criteria,
        timeout_seconds=120,
        max_turns=2,
    )


def _event_key(event: AgentEvent) -> tuple[str, float, str, int]:
    label = str(event.data.get("text") or event.data.get("message") or event.data.get("name") or "")
    return (event.type.value, round(event.timestamp_ms, 3), label, len(event.audio or b""))


def _build_trace(
    spec: UploadedAudioTestSpec,
    summary: CallSummary,
    transcript: TranscriptResult,
    spans: list[TraceSpan],
    original_audio: AudioBuffer,
    connector_audio: AudioBuffer,
) -> CallTrace:
    trace_id = f"audio-upload-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}"
    now = datetime.now(UTC).isoformat()
    return CallTrace(
        id=trace_id,
        source="dashboard-audio-upload",
        target=spec.target,
        started_at=now,
        duration_ms=summary.duration_ms,
        transcript=transcript.segments,
        events=[event.model_copy(update={"audio": None}) for event in summary.events],
        spans=summary.spans,
        metadata={
            "filename": spec.filename,
            "content_type": spec.content_type or "",
            "mode": spec.mode,
            "original_audio": {
                "duration_ms": round(original_audio.duration_ms, 1),
                "sample_rate": original_audio.sample_rate,
                "channels": original_audio.channels,
                "encoding": original_audio.encoding.value,
            },
            "connector_audio": {
                "duration_ms": round(connector_audio.duration_ms, 1),
                "sample_rate": connector_audio.sample_rate,
                "channels": connector_audio.channels,
                "encoding": connector_audio.encoding.value,
            },
            "agent_audio_bytes": len(summary.agent_audio),
        },
        imported_at=now,
    )
