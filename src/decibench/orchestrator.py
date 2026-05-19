"""Orchestrator — the central execution engine.

CLI, MCP, and server are all thin wrappers around this.
Same input + same config = same result. Always.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from decibench.audio.recorder import AudioRecorder
from decibench.audio.synthesizer import AudioSynthesizer
from decibench.connectors.registry import get_connector
from decibench.evaluators import standard_stack
from decibench.evaluators.score import DecibenchScorer
from decibench.models import (
    AgentEvent,
    AudioBuffer,
    CallSummary,
    CostBreakdown,
    EvalResult,
    EventType,
    MetricResult,
    Scenario,
    SuiteResult,
    TraceSpan,
    TranscriptResult,
    TranscriptSegment,
)
from decibench.providers.registry import get_judge, get_stt, get_tts
from decibench.scenarios.loader import ScenarioLoader

if TYPE_CHECKING:
    from decibench.config import DecibenchConfig
    from decibench.evaluators.base import BaseEvaluator

logger = logging.getLogger(__name__)


class Orchestrator:
    """Central execution engine for Decibench.

    Composes connectors, providers, evaluators, and scenarios into
    a complete test pipeline. Every external interface (CLI, MCP, server)
    calls this — ensuring identical behavior regardless of entry point.
    """

    # Type for progress callback: (scenario_id, passed, score, current, total)
    ProgressCallback = Any  # Callable[[str, bool, float, int, int], None]

    def __init__(self, config: DecibenchConfig) -> None:
        self._config = config
        self._scenario_loader = ScenarioLoader()
        self._scorer = DecibenchScorer()
        self._progress_callback: Any | None = None
        self._completed_count: int = 0

        # Canonical evaluator stack — same factory the imported-call path uses.
        # Live runs always have audio + events; judge availability is folded in
        # per-run via `has_judge` so the stack auto-skips semantic evaluators
        # when no judge is configured.
        self._evaluators: list[BaseEvaluator] = standard_stack(
            has_audio=True,
            has_events=True,
            has_judge=config.has_judge,
        )

    async def run_suite(
        self,
        target: str,
        suite: str = "quick",
        noise_levels: list[str] | None = None,
        accents: list[str] | None = None,
        parallel: int = 5,
        scenario_filter: str | None = None,
        on_progress: Any | None = None,
    ) -> SuiteResult:
        """Run a complete test suite against a voice agent.

        Args:
            target: Target URI (ws://, exec:, http://, demo)
            suite: Suite name (quick, standard, full)
            noise_levels: Override noise levels for variant expansion
            accents: Override accents for variant expansion
            parallel: Max concurrent scenario runs

        Returns:
            Complete suite results with Decibench Score
        """
        start_time = time.monotonic()

        # 1. Load scenarios
        scenarios = self._scenario_loader.load_suite(suite)

        # 1b. Filter to single scenario if requested
        if scenario_filter:
            scenarios = [s for s in scenarios if s.id == scenario_filter or scenario_filter in s.id]
            if not scenarios:
                logger.error("No scenario matching '%s' found", scenario_filter)

        # 2. Expand variants if requested
        if noise_levels or accents:
            scenarios = self._scenario_loader.expand_variants(scenarios, noise_levels, accents)

        self._progress_callback = on_progress
        self._completed_count = 0

        # 3. Resolve providers (skip TTS/STT for demo target)
        is_demo = target in ("demo", "demo://")
        tts = None if is_demo else get_tts(self._config.providers.tts)
        stt = None if is_demo else get_stt(self._config.providers.stt)
        judge = (
            get_judge(
                self._config.providers.judge,
                model=self._config.providers.judge_model,
                api_key=self._config.providers.judge_api_key,
                temperature=self._config.evaluation.judge_temperature,
                judge_runs=self._config.evaluation.judge_runs,
            )
            if self._config.has_judge
            else None
        )

        synthesizer = (
            AudioSynthesizer(
                tts_provider=tts,
                noise_profiles_dir=self._config.audio.noise_profiles_dir,
            )
            if tts is not None
            else None
        )

        # 4. Run scenarios with concurrency control
        semaphore = asyncio.Semaphore(parallel)
        tasks = [
            self._run_scenario_with_retries(
                scenario=scenario,
                target=target,
                synthesizer=synthesizer,
                stt=stt,
                judge=judge,
                semaphore=semaphore,
            )
            for scenario in scenarios
        ]
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # 5. Process results, handling any exceptions
            total = len(scenarios)
            eval_results: list[EvalResult] = []
            for i, result in enumerate(results):
                if isinstance(result, BaseException):
                    logger.error(
                        "Scenario '%s' failed with error: %s",
                        scenarios[i].id,
                        result,
                    )
                    er = EvalResult(
                        scenario_id=scenarios[i].id,
                        passed=False,
                        score=0.0,
                        failures=[f"Execution error: {result}"],
                    )
                    eval_results.append(er)
                else:
                    eval_results.append(result)

                # Fire progress callback
                if self._progress_callback:
                    r = eval_results[-1]
                    with contextlib.suppress(Exception):
                        self._progress_callback(r.scenario_id, r.passed, r.score, i + 1, total)

            # 6. Calculate composite score with category breakdown
            score, score_breakdown = self._scorer.calculate(
                eval_results,
                self._config.scoring.weights,
                has_judge=self._config.has_judge,
                policies=self._config.scoring,
            )

            # 7. Aggregate latency stats
            latency = self._aggregate_latency(eval_results)

            # 8. Sum costs
            cost = self._aggregate_cost(eval_results)

            duration = time.monotonic() - start_time
            passed = sum(1 for r in eval_results if r.passed)

            # Determine judge model used
            judge_model = self._config.providers.judge_model if self._config.has_judge else "none"
            eval_mode = "semantic" if self._config.has_judge else "deterministic"
            judge_prov = ""
            if self._config.has_judge:
                from decibench.llm_catalog import judge_provider_from_uri

                judge_prov = judge_provider_from_uri(self._config.providers.judge) or ""

            # Reproducibility rollup. flake_rate is the fraction of scenarios
            # whose pass/fail outcome was unstable across runs; only
            # meaningful when ``runs_per_scenario > 1`` and exposed for
            # operator triage ("which scenarios should I rerun?").
            flake_count = sum(1 for r in eval_results if r.flaked)
            flake_rate = flake_count / len(eval_results) if eval_results else 0.0
            score_stddev_avg = (
                sum(r.score_stddev for r in eval_results) / len(eval_results) if eval_results else 0.0
            )

            return SuiteResult(
                suite=suite,
                target=target,
                decibench_score=score,
                score_breakdown=score_breakdown,
                total_scenarios=len(eval_results),
                passed=passed,
                failed=len(eval_results) - passed,
                results=eval_results,
                latency=latency,
                cost=cost,
                duration_seconds=round(duration, 1),
                judge_model=judge_model,
                evaluation_mode=eval_mode,
                judge_provider=judge_prov,
                # Hash the redacted view — API keys MUST NOT enter the hash
                # input, otherwise two engineers with identical scoring config
                # but different env keys produce different hashes and the
                # "same config, same score" promise breaks.
                config_hash=SuiteResult.compute_config_hash(self._config.redacted_dump()),
                suite_version=self._scenario_loader.suite_version(suite),
                flake_rate=round(flake_rate, 3),
                score_stddev_avg=round(score_stddev_avg, 2),
                timestamp=datetime.now(UTC).isoformat(),
            )
        finally:
            # Cleanup
            if synthesizer is not None:
                await synthesizer.close()
            if stt is not None and hasattr(stt, "close"):
                await stt.close()
            if judge is not None and hasattr(judge, "close"):
                await judge.close()

    async def _run_scenario_with_retries(
        self,
        scenario: Scenario,
        target: str,
        synthesizer: AudioSynthesizer | None,
        stt: Any | None,
        judge: Any | None,
        semaphore: asyncio.Semaphore,
    ) -> EvalResult:
        """Run a single scenario with multiple runs for statistical reliability."""
        async with semaphore:
            runs: list[EvalResult] = []
            for run_idx in range(self._config.evaluation.runs_per_scenario):
                try:
                    result = await self._run_single_scenario(
                        scenario=scenario,
                        target=target,
                        synthesizer=synthesizer,
                        stt=stt,
                        judge=judge,
                        run_index=run_idx,
                    )
                    runs.append(result)
                except Exception as e:
                    logger.warning(
                        "Run %d of scenario '%s' failed: %s",
                        run_idx,
                        scenario.id,
                        e,
                    )
                    runs.append(
                        EvalResult(
                            scenario_id=scenario.id,
                            passed=False,
                            score=0.0,
                            failures=[str(e)],
                            run_index=run_idx,
                        )
                    )

            return (
                self._average_runs(runs)
                if runs
                else EvalResult(
                    scenario_id=scenario.id,
                    passed=False,
                    score=0.0,
                    failures=["All runs failed"],
                )
            )

    async def _run_single_scenario(
        self,
        scenario: Scenario,
        target: str,
        synthesizer: AudioSynthesizer | None,
        stt: Any | None,
        judge: Any | None,
        run_index: int,
    ) -> EvalResult:
        """Execute a single scenario run end-to-end."""
        start = time.monotonic()

        # 1. Get connector
        from decibench.connectors.session import ConnectorSession

        connector = get_connector(target)
        is_demo = target in ("demo", "demo://")

        # 2. Connect to agent — merge auth, audio, connector protocol settings,
        # and any extra keys into a single dict so connectors can read
        # sample_rate, ws_protocol, websocket_headers, etc.
        connector_cfg = self._config.connector.model_dump()
        # Only forward non-empty/non-zero connector keys (empty = use preset default)
        connector_overrides = {k: v for k, v in connector_cfg.items() if v}
        connector_config: dict[str, Any] = {
            **self._config.auth.model_dump(),
            "sample_rate": self._config.audio.sample_rate,
            "channels": self._config.audio.channels,
            "bit_depth": self._config.audio.bit_depth,
            **connector_overrides,
        }
        # Session wraps connect+disconnect with idempotency. Even if the body
        # disconnects explicitly to collect a summary, the surrounding
        # cleanup can call disconnect() again without re-triggering the
        # connector's teardown (which on bridge connectors resets buffers
        # and would zero out the CallSummary on the second call).
        session = ConnectorSession(connector, target, connector_config)
        handle = await session.connect()

        try:
            all_metrics: dict[str, MetricResult] = {}
            transcript = TranscriptResult(text="")
            summary = CallSummary(duration_ms=0, turn_count=0)
            last_caller_audio: AudioBuffer | None = None
            spans: list[TraceSpan] = []

            try:
                # 3. For each caller turn, synthesize and send audio
                for turn_idx, turn in enumerate(scenario.caller_turns):
                    if not turn.text:
                        continue

                    if is_demo:
                        caller_audio = AudioBuffer(
                            data=b"\x00" * 3200,
                            sample_rate=16000,
                        )
                    elif synthesizer is not None:
                        tts_start = time.monotonic()
                        caller_audio = await synthesizer.synthesize(
                            text=turn.text,
                            persona=scenario.persona,
                            target_sample_rate=connector.required_sample_rate,
                            target_encoding=connector.required_encoding,
                        )
                        tts_duration = (time.monotonic() - tts_start) * 1000
                        spans.append(
                            TraceSpan(
                                name="tts",
                                start_ms=(tts_start - start) * 1000,
                                end_ms=(tts_start - start) * 1000 + tts_duration,
                                duration_ms=tts_duration,
                                turn_index=turn_idx,
                            )
                        )
                    else:
                        caller_audio = AudioBuffer(data=b"\x00" * 3200, sample_rate=16000)

                    last_caller_audio = caller_audio

                    # Pass caller text to connector via handle state (used by demo connector)
                    handle.state[f"caller_text_{turn_idx + 1}"] = turn.text or ""

                    turn_start = time.monotonic()
                    await connector.send_audio(handle, caller_audio)

                    # Record when caller audio finished sending.
                    # This gives evaluators (interruption, latency) a real
                    # anchor for "caller finished speaking" timing.
                    caller_end_ms = (time.monotonic_ns() - handle.start_time_ns) / 1_000_000
                    handle.state.setdefault("_extra_events", []).append(
                        AgentEvent(
                            type=EventType.CALLER_AUDIO_END,
                            timestamp_ms=caller_end_ms,
                            data={"turn_index": turn_idx},
                        )
                    )

                    async for event in connector.receive_events(handle):
                        # Detect per-turn interruptions for real-time awareness
                        if event.type == EventType.INTERRUPTION:
                            logger.debug(
                                "Interruption detected at %.1fms in scenario '%s'",
                                event.timestamp_ms,
                                scenario.id,
                            )

                    turn_duration = (time.monotonic() - turn_start) * 1000
                    spans.append(
                        TraceSpan(
                            name="turn_latency",
                            start_ms=(turn_start - start) * 1000,
                            end_ms=(turn_start - start) * 1000 + turn_duration,
                            duration_ms=turn_duration,
                            turn_index=turn_idx,
                        )
                    )

                # 4. Disconnect and get summary
                summary = await session.disconnect() or CallSummary(duration_ms=0, turn_count=0)

                # Merge caller-timing events recorded during send_audio
                extra_events = handle.state.get("_extra_events", [])
                if extra_events:
                    merged_events = list(summary.events) + extra_events
                    merged_events.sort(key=lambda e: e.timestamp_ms)
                    summary = summary.model_copy(update={"events": merged_events})

                # 5. Transcribe agent response
                if is_demo:
                    transcript_parts = self._collapse_agent_transcript_events(summary.events)
                    transcript = TranscriptResult(
                        text=" ".join(transcript_parts),
                        segments=[TranscriptSegment(role="agent", text=text) for text in transcript_parts],
                        language="en",
                        duration_ms=summary.duration_ms,
                    )
                else:
                    # Try agent-provided transcript from events first
                    agent_transcript_parts = self._collapse_agent_transcript_events(summary.events)

                    if agent_transcript_parts:
                        transcript = TranscriptResult(
                            text=" ".join(agent_transcript_parts),
                            segments=[
                                TranscriptSegment(role="agent", text=text) for text in agent_transcript_parts
                            ],
                            language="en",
                            duration_ms=summary.duration_ms,
                        )
                    elif stt is not None and summary.agent_audio:
                        stt_start = time.monotonic()
                        agent_audio_buf = AudioBuffer(
                            data=summary.agent_audio,
                            sample_rate=connector.required_sample_rate,
                        )
                        transcript = await stt.transcribe(agent_audio_buf)
                        stt_duration = (time.monotonic() - stt_start) * 1000
                        spans.append(
                            TraceSpan(
                                name="stt",
                                start_ms=(stt_start - start) * 1000,
                                end_ms=(stt_start - start) * 1000 + stt_duration,
                                duration_ms=stt_duration,
                            )
                        )

                # 5b. Save audio to disk if output dir configured
                output_dir = getattr(self._config.evaluation, "output_dir", None)
                if output_dir and summary.agent_audio:
                    try:
                        from pathlib import Path

                        audio_buf = AudioBuffer(
                            data=summary.agent_audio,
                            sample_rate=connector.required_sample_rate,
                        )
                        audio_path = Path(output_dir) / f"{scenario.id}_run{run_index}.wav"
                        AudioRecorder.save_wav(audio_buf, audio_path)
                    except Exception as e:
                        logger.debug("Could not save audio for %s: %s", scenario.id, e)

                # 6. Run evaluators
                # Single source of truth for the latency contract:
                # ``ScoringConfig.latency_bands.yellow_ms`` is BOTH the pass
                # threshold for the evaluator AND the 50/100 inflection point
                # of the scorer's curve. The legacy keys are still populated
                # for backward compatibility with evaluators that consume
                # them directly in tests.
                bands = self._config.scoring.latency_bands
                eval_context: dict[str, Any] = {
                    "judge": judge,
                    "config": self._config,
                    "latency_bands": bands,
                    # Backward-compat keys — kept so test fixtures that
                    # construct context dicts directly keep working.
                    "p50_max_ms": bands.p50[1],
                    "p95_max_ms": bands.p95[1],
                    "p99_max_ms": bands.p99[1],
                    "ttfw_max_ms": bands.ttfw[1],
                    # Fix #4: Pass reference audio for real STOI computation
                    "reference_audio": last_caller_audio.data if last_caller_audio else None,
                }

                for evaluator in self._evaluators:
                    # Skip semantic evaluators when no judge
                    if evaluator.requires_judge and judge is None:
                        continue

                    try:
                        metrics = await evaluator.evaluate(scenario, summary, transcript, eval_context)
                        for metric in metrics:
                            all_metrics[metric.name] = metric
                    except Exception as e:
                        logger.warning(
                            "Evaluator '%s' failed on scenario '%s': %s",
                            evaluator.name,
                            scenario.id,
                            e,
                        )

            except TimeoutError:
                all_metrics["timeout"] = MetricResult(
                    name="timeout",
                    value=1.0,
                    passed=False,
                    details={"timeout_seconds": scenario.timeout_seconds},
                )
            except ConnectionError as e:
                logger.error("Scenario '%s' connection error: %s", scenario.id, e)
                return EvalResult(
                    scenario_id=scenario.id,
                    passed=False,
                    score=0.0,
                    failures=[f"Execution error: {e}"],
                    duration_ms=(time.monotonic() - start) * 1000,
                    run_index=run_index,
                )
            except Exception as e:
                err_str = str(e)
                hint = ""
                if "no close frame" in err_str or "ConnectionClosed" in type(e).__name__:
                    hint = (
                        " Hint: The server closed the connection unexpectedly. "
                        "Check ws_protocol setting (try: openai-realtime, gemini-live, or twilio) "
                        "and verify the sample_rate matches what the agent expects."
                    )
                logger.error("Scenario '%s' execution error: %s%s", scenario.id, e, hint)
                return EvalResult(
                    scenario_id=scenario.id,
                    passed=False,
                    score=0.0,
                    failures=[f"Execution error: {e}{hint}"],
                    duration_ms=(time.monotonic() - start) * 1000,
                    run_index=run_index,
                )

            # 7. Determine pass/fail using metric policies
            #    Only "blocking" metrics cause scenario failure.
            #    "scoring" metrics reduce the score but don't fail.
            #    "advisory" metrics are informational only.
            scoring_cfg = self._config.scoring
            failures = [
                f"{m.name}: {m.value} (threshold: {m.threshold})"
                for m in all_metrics.values()
                if not m.passed and scoring_cfg.get_policy(m.name) == "blocking"
            ]
            passed = len(failures) == 0

            # Also track non-blocking failures for reporting
            all_failures = [
                f"{m.name}: {m.value} (threshold: {m.threshold})"
                for m in all_metrics.values()
                if not m.passed
            ]

            # Build failure_summary: which categories failed
            from decibench.evaluators.score import _METRIC_CATEGORIES

            failed_categories = set()
            for m in all_metrics.values():
                if not m.passed and m.name in _METRIC_CATEGORIES:
                    failed_categories.add(_METRIC_CATEGORIES[m.name])
            failure_summary = sorted(failed_categories)

            # 8. Calculate per-scenario score
            scenario_results = [
                EvalResult(
                    scenario_id=scenario.id,
                    passed=passed,
                    score=0.0,
                    metrics=all_metrics,
                )
            ]
            score, _ = self._scorer.calculate(
                scenario_results,
                self._config.scoring.weights,
                self._config.has_judge,
                policies=scoring_cfg,
            )

            duration_ms = (time.monotonic() - start) * 1000

            return EvalResult(
                scenario_id=scenario.id,
                passed=passed,
                score=score,
                metrics=all_metrics,
                failures=all_failures,
                failure_summary=failure_summary,
                latency={k: m.value for k, m in all_metrics.items() if "latency" in k or "ttfw" in k},
                duration_ms=round(duration_ms, 1),
                transcript=[{"role": seg.role, "text": seg.text} for seg in transcript.segments],
                run_index=run_index,
                spans=spans,
            )
        finally:
            # Idempotent — if the body already disconnected to collect the
            # summary, this is a no-op. If it didn't (exception path), this
            # is the cleanup. Either way, the connector's teardown runs
            # exactly once per scenario.
            await session.disconnect()

    @staticmethod
    def _collapse_agent_transcript_events(events: list[AgentEvent]) -> list[str]:
        """Normalize agent transcript events into stable utterance chunks.

        Connectors vary between cumulative updates ("Hi", "Hi there"),
        delta-style fragments, and repeated partials within a single speaking
        turn. We keep the best transcript seen for each agent turn and flush it
        on explicit turn boundaries.
        """

        def finalize(current: str, utterances: list[str]) -> None:
            current = current.strip()
            if not current:
                return
            if utterances:
                previous = utterances[-1]
                if previous == current or previous.startswith(current):
                    return
                if current.startswith(previous):
                    utterances[-1] = current
                    return
            utterances.append(current)

        def choose_best(current: str, incoming: str) -> str:
            if not current:
                return incoming
            if incoming == current:
                return current
            if incoming.startswith(current) or current in incoming:
                return incoming
            if current.startswith(incoming) or incoming in current:
                return current

            current_words = current.split()
            incoming_words = incoming.split()
            if len(incoming_words) > len(current_words):
                return incoming
            return current

        utterances: list[str] = []
        current = ""
        for event in events:
            if event.type == EventType.METADATA:
                if event.data.get("kind") == "agent_start_talking":
                    finalize(current, utterances)
                    current = ""
                continue

            if event.type == EventType.TURN_END:
                finalize(current, utterances)
                current = ""
                continue

            if event.type != EventType.AGENT_TRANSCRIPT or not event.data:
                continue

            text = (event.data.get("text", "") or event.data.get("message", "")).strip()
            if not text:
                continue

            current = choose_best(current, text)

        finalize(current, utterances)
        return utterances

    @staticmethod
    def _average_runs(runs: list[EvalResult]) -> EvalResult:
        """Average metrics across multiple runs of the same scenario.

        Records reproducibility telemetry alongside the averaged numbers:

        - ``score_stddev``: population std-dev of per-run scores. Tells you
          how reproducible the agent's behavior is independent of pass/fail.
        - ``flaked``: True if pass/fail outcomes differed across runs. A
          flaked scenario is the strongest signal of an unstable agent —
          the averaged score may be 65/100 but if half the runs passed and
          half failed, that 65 is a lie.
        - ``run_count``: number of runs that actually completed (failed
          runs still count; they're a real outcome).
        """
        if len(runs) == 1:
            base = runs[0]
            return base.model_copy(update={"score_stddev": 0.0, "flaked": False, "run_count": 1})

        # Use the first run as template
        base = runs[0]

        # Average numeric metrics
        averaged_metrics: dict[str, MetricResult] = {}
        for metric_name in base.metrics:
            values = [r.metrics[metric_name].value for r in runs if metric_name in r.metrics]
            if values:
                avg_value = sum(values) / len(values)
                template = base.metrics[metric_name]

                # Majority-vote pass/fail across runs (for metrics without thresholds)
                pass_votes = sum(
                    1 for r in runs if metric_name in r.metrics and r.metrics[metric_name].passed
                )
                majority_passed = pass_votes > len(runs) / 2

                averaged_metrics[metric_name] = MetricResult(
                    name=template.name,
                    value=round(avg_value, 2),
                    unit=template.unit,
                    passed=majority_passed,
                    threshold=template.threshold,
                    details={"runs": len(values), "values": values},
                )

        # Re-check pass/fail with averaged values for metrics WITH thresholds
        for metric in averaged_metrics.values():
            if metric.threshold is not None:
                lower_is_better = (
                    "latency" in metric.name
                    or "ttfw" in metric.name
                    or metric.name in ("wer", "cer", "hallucination_rate", "silence_pct")
                )
                if lower_is_better:
                    metric.passed = metric.value <= metric.threshold
                else:
                    metric.passed = metric.value >= metric.threshold

        failures = [
            f"{m.name}: {m.value} (threshold: {m.threshold})"
            for m in averaged_metrics.values()
            if not m.passed
        ]

        avg_score = sum(r.score for r in runs) / len(runs)
        averaged_cost: dict[str, float] = {}
        cost_keys = {key for run in runs for key in run.cost}
        for key in cost_keys:
            averaged_cost[key] = sum(run.cost.get(key, 0.0) for run in runs) / len(runs)

        # Reproducibility telemetry — surfaces flakiness instead of hiding it
        # in the average. A run set where 5 of 10 pass and the average score
        # is 65 is a much weaker signal than 10/10 passes at 65, and we want
        # the dashboard to show both.
        import statistics as _stats

        scores = [r.score for r in runs]
        score_stddev = round(_stats.pstdev(scores), 2) if len(scores) > 1 else 0.0
        pass_outcomes = {r.passed for r in runs}
        flaked = len(pass_outcomes) > 1

        return EvalResult(
            scenario_id=base.scenario_id,
            passed=len(failures) == 0,
            score=round(avg_score, 1),
            metrics=averaged_metrics,
            failures=failures,
            failure_summary=base.failure_summary,  # categories from the first run (usually stable)
            cost=averaged_cost,
            spans=base.spans,
            latency=base.latency,
            duration_ms=sum(r.duration_ms for r in runs) / len(runs),
            transcript=base.transcript,
            score_stddev=score_stddev,
            flaked=flaked,
            run_count=len(runs),
        )

    @staticmethod
    def _aggregate_latency(results: list[EvalResult]) -> dict[str, float]:
        """Aggregate latency over the merged per-turn sample population.

        Delegates to ``decibench.evaluators.aggregate.aggregate_latency``,
        which computes a real nearest-rank percentile over every per-turn
        latency sample emitted by every scenario in the suite. Replaces the
        prior mean-of-per-scenario-percentile approximation, which could
        report a "p95" that no actual call had ever experienced.
        """
        from decibench.evaluators.aggregate import aggregate_latency

        return aggregate_latency(results)

    @staticmethod
    def _aggregate_cost(results: list[EvalResult]) -> CostBreakdown:
        """Sum costs across all scenarios."""
        total = CostBreakdown()
        for r in results:
            total.tts += r.cost.get("tts", 0)
            total.stt += r.cost.get("stt", 0)
            total.judge += r.cost.get("judge", 0)
            total.platform += r.cost.get("platform", 0)
        return total
