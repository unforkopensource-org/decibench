# Changelog

All notable changes to Decibench are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and Decibench adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased] — v1.0.0 work in progress

### Tracking implementation plan `140526impplan.md`.

### Added
- `decibench.evaluators.aggregate` module: raw-sample latency percentile aggregator
  that correctly merges per-scenario samples before computing p50 / p95 / p99,
  replacing the previous mean-of-percentiles approximation.
- Property tests (Hypothesis) that pin scoring-math invariants against an
  independent reference implementation of the nearest-rank formula.
- `decibench.evaluators.standard_stack()` factory — single source of truth for
  the evaluator set used by both the live `decibench run` path and the
  imported-call `evaluate_calls` path.
- `decibench.connectors.ConnectorSession` context manager: tracks whether a
  connector has already produced a `CallSummary` so cleanup paths can call
  `disconnect()` defensively without double-billing the connector lifecycle.
- `DecibenchConfig.redacted_dump()` — produces a secret-free view of the config
  for hashing and reproducibility-seal use. The `SuiteResult.config_hash` is
  computed against this view, so two engineers with the same scoring config but
  different API keys now produce identical hashes.
- `SuiteResult.suite_version` — propagated from `suite.toml` files inside each
  built-in suite package, so historical comparisons across suite edits surface
  as warnings instead of silent drift.
- `ConnectorConfig.send_speed` — pacing knob for caller audio chunks
  (1.0 = real-time, 0 = burst). Default is real-time; earlier versions
  silently paced WS at ~5x and process at 2x real-time, biasing every
  latency measurement low.
- `LatencyScoringConfig` — single source of truth for the latency contract.
  `(green, yellow, red)` triples per percentile band drive both the
  `LatencyEvaluator` pass threshold (= `yellow_ms`) and the
  `DecibenchScorer` 100/50/0 curve, so the two contracts can never disagree.
- `EvalResult.score_stddev` / `EvalResult.flaked` / `EvalResult.run_count`
  and `SuiteResult.flake_rate` / `SuiteResult.score_stddev_avg` — surface
  reproducibility telemetry when `runs_per_scenario > 1`.
- Coverage tooling: `pytest-cov`, `hypothesis`, and a `coverage` configuration
  block in `pyproject.toml`. Baseline floor: 50 % (ratcheted up per phase per
  the implementation plan); per-module critical-path floors enforced in
  `tests/test_coverage_floors.py`.
- Repository hygiene files: `CONTRIBUTING.md`, `CODEOWNERS`, `.editorconfig`,
  `Makefile`, `.pre-commit-config.yaml`, GitHub Actions CI workflow, and PR /
  issue templates.

### Changed
- `Orchestrator._aggregate_latency` now operates on the merged distribution of
  all per-turn latency samples in the suite, not on the means of per-scenario
  percentiles. The reported `p95_ms` is now a real observed sample.
- `LatencyEvaluator` records raw `turn_latencies` in
  `MetricResult.details["raw_samples"]` for downstream aggregation.
- `Orchestrator` now resolves its evaluator list through
  `decibench.evaluators.standard_stack(...)`, gated by `requires_audio`,
  `requires_events`, and `requires_judge` traits on each evaluator.
- `docs/support-matrix.yaml` now reflects the real product surface:
  `elevenlabs`, `twilio`, and `mcp_serve` are listed as `shipped` (matching the
  code and README), and `retell` / `vapi` keep their `experimental` status.
- `tests/test_docs_truth.py` gains an inverse-direction check: every connector
  registered in code must appear in the matrix as non-`planned`, every
  evaluator name must appear in the matrix's `evaluators` block, and every
  maintainer doc the README points at must exist on disk.

### Fixed
- **Critical:** percentile-of-percentiles bug in `_aggregate_latency` and
  `_average_runs`. The headline latency number was a mean of medians; it is now
  a true percentile over the full sample population.
- **Critical:** `config_hash` previously included resolved API keys, so two
  developers with the same logical config produced different hashes. Hash input
  is now secret-redacted.
- **Critical:** real-time pacing in `WebSocketConnector` and `ProcessConnector`.
  WS sent 100 ms chunks with 20 ms sleeps (~5x real-time); process used 50 % of
  chunk duration (~2x real-time). Both now pace at true real-time by default
  via `ConnectorConfig.send_speed`, restoring honest latency measurements.
- **Critical:** `LatencyEvaluator` pass thresholds and `DecibenchScorer`
  category curve disagreed — an agent at the threshold "passed" while
  contributing 50/100 to its category. Both consumers now read from
  `ScoringConfig.latency_bands`.
- WebSocket auto-detect previously kept a dead socket alive when the binary
  probe was rejected AND the follow-up reconnect failed, deferring the error
  to the first `send_audio()` with no diagnostic. Now raises `ConnectionError`
  at `connect()` with an actionable hint.
- Double-disconnect of every connector on the happy path — `disconnect()` was
  called once in the orchestrator body and again in the surrounding `finally`.
  This silently zeroed out `CallSummary.events` for bridge connectors that
  reset their internal buffers in `disconnect()`.

### Removed
- The dev-copy of scenarios at `scenarios/core/` is gone — the canonical home
  is `src/decibench/scenarios/suites/`. `tests/test_scenarios_canonical.py`
  fails if any scenario YAML reappears outside the canonical tree.

### Security
- API keys never enter the hash input or the reproducibility seal payload.
- `decibench rag` cloud-egress paths (P5 work) default to off; the existing
  privacy redactor continues to gate writes into the local store.

## [0.1.0] — alpha

Initial alpha release. See README for the alpha feature set.
