"""Configuration loading and validation for Decibench.

Loads decibench.toml, expands environment variables, validates with Pydantic,
and resolves profiles. The config object is immutable after creation.
"""

from __future__ import annotations

import os
import re
import tomllib
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

# Metric policy tiers:
#   blocking  — metric failure fails the scenario AND triggers score hard caps
#   scoring   — metric failure reduces score but does NOT fail the scenario
#   advisory  — metric is reported but excluded from score and pass/fail
MetricPolicy = Literal["blocking", "scoring", "advisory"]

# Sensible defaults: only PII is blocking out of the box.
# Everything else scores normally. Users override in [scoring.policies].
DEFAULT_METRIC_POLICIES: dict[str, MetricPolicy] = {
    "pii_violations": "blocking",
    "ai_disclosure": "scoring",
    "compliance_score": "scoring",
    "hipaa_verification_order": "blocking",
    "pci_no_echo": "blocking",
    "task_completion": "scoring",
    "tool_call_correctness": "scoring",
    "slot_extraction_accuracy": "scoring",
    "hallucination_rate": "scoring",
    "ttfw_ms": "scoring",
    "turn_latency_p50_ms": "scoring",
    "turn_latency_p95_ms": "scoring",
    "turn_latency_p99_ms": "scoring",
    "response_gap_avg_ms": "scoring",
    "mos_ovrl": "scoring",
    "audio_quality_estimate": "scoring",
    "intelligibility_estimate": "scoring",
    "snr": "scoring",
    "wer": "scoring",
    "cer": "scoring",
    "silence_pct": "scoring",
    "silence_segments": "scoring",
    "turn_gap_avg_ms": "scoring",
    "interruption_recovery": "scoring",
    "barge_in_handling": "scoring",
}

from decibench.llm_catalog import judge_provider_from_uri
from decibench.secrets import resolve_secret

_ENV_VAR_PATTERN = re.compile(r"\$\{([^}]+)\}")

DEFAULT_CONFIG_NAME = "decibench.toml"


def _expand_env_vars(value: Any) -> Any:
    """Recursively expand ${VAR} patterns in strings from environment."""
    if isinstance(value, str):

        def _replace(match: re.Match[str]) -> str:
            var_name = match.group(1)
            env_val = os.environ.get(var_name)
            if env_val is None:
                return match.group(0)  # Leave unexpanded if not set
            return env_val

        return _ENV_VAR_PATTERN.sub(_replace, value)
    if isinstance(value, dict):
        return {k: _expand_env_vars(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env_vars(item) for item in value]
    return value


class ProjectConfig(BaseModel):
    """[project] section."""

    name: str = "my-voice-agent"


class TargetConfig(BaseModel):
    """[target] section."""

    default: str = "demo"


class AuthConfig(BaseModel):
    """[auth] section — values may come from config, env vars, or keyring."""

    model_config = {"extra": "allow"}

    vapi_api_key: str = ""
    retell_api_key: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    gemini_api_key: str = ""


class ProvidersConfig(BaseModel):
    """[providers] section — pluggable TTS, STT, and LLM judge."""

    tts: str = "edge-tts"
    tts_voice: str = "en-US-JennyNeural"
    stt: str = "faster-whisper:base"
    judge: str = "none"
    judge_model: str = ""
    judge_api_key: str = ""


class AudioConfig(BaseModel):
    """[audio] section."""

    sample_rate: int = 16000
    channels: int = 1
    bit_depth: int = 16
    noise_profiles_dir: str = "./noise_profiles"


class ConnectorConfig(BaseModel):
    """[connector] section — WebSocket protocol and transport settings."""

    ws_protocol: str = "auto"
    ws_send_format: str = ""
    ws_setup_message: str = ""
    ws_commit_message: str = ""
    ws_recv_timeout: float = 0
    ws_silence_max: int = 0
    # Send pacing relative to real-time. Earlier versions paced WS chunks at
    # ~5x real-time and process chunks at 2x — which warped latency/bargein
    # measurements because the agent saw the caller speak faster than a real
    # caller could. Default 1.0 = real-time. 0 = burst (no pacing) — only for
    # smoke tests and the demo connector.
    send_speed: float = Field(default=1.0, ge=0.0, le=10.0)


class EvaluationConfig(BaseModel):
    """[evaluation] section."""

    runs_per_scenario: int = Field(default=1, ge=1, le=20)
    judge_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    judge_runs: int = Field(default=1, ge=1, le=5)  # 3 = median-of-3 for stability
    timeout_seconds: int = Field(default=120, ge=10, le=600)


# (green_ms, yellow_ms, red_ms) latency bands. The boundary semantics are:
#   value ≤ green_ms   → score 100  (excellent)
#   value = yellow_ms  → score 50   (acceptable; same value as the pass/fail threshold)
#   value ≥ red_ms     → score 0    (fail)
# Pass/fail threshold lives at ``yellow_ms`` so the curve and the threshold
# can never disagree — the historical bug was a curve saying 800 ms = 50
# while the threshold said 800 ms passes.
class LatencyScoringConfig(BaseModel):
    """Latency band configuration consumed by both the evaluator and the scorer.

    Single source of truth for the latency contract. The evaluator reads
    ``yellow_ms`` as its pass threshold; the scorer maps the (green, yellow,
    red) triple onto a piecewise-linear 100/50/0 curve. Anyone tuning
    latency expectations changes them in exactly one place.
    """

    p50: tuple[int, int, int] = (300, 800, 2000)
    p95: tuple[int, int, int] = (500, 1200, 3000)
    p99: tuple[int, int, int] = (800, 2000, 5000)
    ttfw: tuple[int, int, int] = (300, 800, 2000)

    @staticmethod
    def score_band(value: float, band: tuple[int, int, int]) -> float:
        """Piecewise-linear 100/50/0 curve over a (green, yellow, red) triple."""
        green, yellow, red = band
        if value <= green:
            return 100.0
        if value >= red:
            return 0.0
        if value <= yellow:
            # green→yellow maps to 100→50
            return 100.0 - 50.0 * (value - green) / max(1, yellow - green)
        # yellow→red maps to 50→0
        return 50.0 - 50.0 * (value - yellow) / max(1, red - yellow)


class ScoringWeights(BaseModel):
    """[scoring.weights] section — all weights must sum to 1.0."""

    task_completion: float = 0.25
    latency: float = 0.20
    audio_quality: float = 0.15
    conversation: float = 0.15
    robustness: float = 0.10
    interruption: float = 0.10
    compliance: float = 0.05

    @model_validator(mode="after")
    def _validate_weights_sum(self) -> ScoringWeights:
        total = (
            self.task_completion
            + self.latency
            + self.audio_quality
            + self.conversation
            + self.robustness
            + self.interruption
            + self.compliance
        )
        if abs(total - 1.0) > 0.01:
            msg = f"Scoring weights must sum to 1.0, got {total:.3f}"
            raise ValueError(msg)
        return self


class ScoringConfig(BaseModel):
    """[scoring] section."""

    weights: ScoringWeights = Field(default_factory=ScoringWeights)
    policies: dict[str, MetricPolicy] = Field(default_factory=dict)
    latency_bands: LatencyScoringConfig = Field(default_factory=LatencyScoringConfig)

    @property
    def resolved_policies(self) -> dict[str, MetricPolicy]:
        """Return full policy map: user overrides merged onto defaults."""
        merged = dict(DEFAULT_METRIC_POLICIES)
        merged.update(self.policies)
        return merged

    def get_policy(self, metric_name: str) -> MetricPolicy:
        """Get the effective policy for a metric (user override > default > 'scoring')."""
        if metric_name in self.policies:
            return self.policies[metric_name]
        # Handle keyword_presence_t0, keyword_absence_t1, etc.
        for prefix in ("keyword_presence", "keyword_absence"):
            if metric_name.startswith(prefix):
                return self.policies.get(prefix, DEFAULT_METRIC_POLICIES.get(prefix, "scoring"))
        return DEFAULT_METRIC_POLICIES.get(metric_name, "scoring")


class CIConfig(BaseModel):
    """[ci] section."""

    min_score: float = Field(default=80.0, ge=0.0, le=100.0)
    max_p95_latency_ms: int = Field(default=1500, ge=100)
    fail_on_compliance_violation: bool = True


class RagConfig(BaseModel):
    """[rag] section — knowledge-store + synthesis settings.

    Defaults are local-first: the embedding provider is the on-CPU
    sentence-transformers model and cloud egress is disabled. Users who
    want a cloud embedder must set both ``embedding`` to a cloud URI AND
    ``allow_cloud = true`` — the inconvenience is intentional.
    """

    embedding: str = "embed://local/all-MiniLM-L6-v2"
    allow_cloud: bool = False
    chunk_size_tokens: int = Field(default=800, ge=64, le=4000)
    chunk_overlap_tokens: int = Field(default=100, ge=0, le=1000)
    # Grounding gate threshold for synthesized scenarios. Lowering this lets
    # the synthesizer invent more — at the cost of caller-turn fidelity.
    grounding_threshold: float = Field(default=0.9, ge=0.0, le=1.0)


class ProfileConfig(BaseModel):
    """A named configuration profile (e.g., dev, ci, benchmark)."""

    suite: str = "quick"
    runs_per_scenario: int = Field(default=1, ge=1, le=20)
    min_score: float = Field(default=0.0, ge=0.0, le=100.0)
    noise_levels: list[str] = Field(default_factory=lambda: ["clean"])
    accents: list[str] = Field(default_factory=lambda: ["en-US"])


class DecibenchConfig(BaseModel):
    """Root configuration model for decibench.toml."""

    project: ProjectConfig = Field(default_factory=ProjectConfig)
    target: TargetConfig = Field(default_factory=TargetConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)
    connector: ConnectorConfig = Field(default_factory=ConnectorConfig)
    audio: AudioConfig = Field(default_factory=AudioConfig)
    evaluation: EvaluationConfig = Field(default_factory=EvaluationConfig)
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    ci: CIConfig = Field(default_factory=CIConfig)
    rag: RagConfig = Field(default_factory=RagConfig)
    profiles: dict[str, ProfileConfig] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _populate_runtime_secrets(self) -> DecibenchConfig:
        return _resolve_config_secrets(self)

    @classmethod
    def from_toml(cls, path: Path) -> DecibenchConfig:
        """Load config from a TOML file, expanding environment variables."""
        with open(path, "rb") as f:
            raw = tomllib.load(f)
        expanded = _expand_env_vars(raw)
        return cls.model_validate(expanded)

    @classmethod
    def defaults(cls) -> DecibenchConfig:
        """Return default configuration (no file needed)."""
        return cls()

    def redacted_dump(self) -> dict[str, Any]:
        """Return a JSON-safe config view with secrets replaced by sentinels.

        Used as the canonical input to ``SuiteResult.compute_config_hash`` and
        to the reproducibility seal. Two engineers running identical scoring
        configs but with different provider API keys MUST produce the same
        hash — anything else breaks the "same config, same score" promise.

        Replacement strategy: every field whose name ends in ``_api_key`` or
        ``_secret`` is replaced with ``"<set>"`` (if it had a value) or
        ``"<unset>"`` (if empty). Field structure is preserved so the hash
        still varies on every non-secret change.
        """
        data = self.model_dump(mode="json")
        return _redact_secrets(data)

    def with_profile(self, profile_name: str) -> DecibenchConfig:
        """Return a new config with profile overrides applied."""
        if profile_name not in self.profiles:
            msg = f"Profile '{profile_name}' not found. Available: {list(self.profiles.keys())}"
            raise ValueError(msg)
        profile = self.profiles[profile_name]
        data = self.model_dump()
        data["evaluation"]["runs_per_scenario"] = profile.runs_per_scenario
        data["ci"]["min_score"] = profile.min_score
        return DecibenchConfig.model_validate(data)

    @property
    def has_judge(self) -> bool:
        """Whether an LLM judge is configured."""
        return self.providers.judge != "none"


def find_config(start_dir: Path | None = None) -> Path | None:
    """Walk up from start_dir looking for decibench.toml."""
    current = start_dir or Path.cwd()
    for directory in [current, *current.parents]:
        candidate = directory / DEFAULT_CONFIG_NAME
        if candidate.is_file():
            return candidate
    return None


def load_config(
    config_path: Path | None = None,
    profile: str | None = None,
) -> DecibenchConfig:
    """Load config from file or defaults, optionally applying a profile."""
    if config_path is None:
        config_path = find_config()

    if config_path is not None and config_path.is_file():
        config = DecibenchConfig.from_toml(config_path)
    else:
        config = DecibenchConfig.defaults()

    if profile is not None:
        config = config.with_profile(profile)

    return config


_SECRET_FIELD_PATTERNS = ("api_key", "secret", "token", "password", "credentials", "key")


def _redact_secrets(value: Any) -> Any:
    """Recursively replace secret-looking fields with set/unset sentinels."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if isinstance(k, str) and any(s in k.lower() for s in _SECRET_FIELD_PATTERNS):
                out[k] = "<set>" if v else "<unset>"
            else:
                out[k] = _redact_secrets(v)
        return out
    if isinstance(value, list):
        return [_redact_secrets(item) for item in value]
    return value


def _resolve_config_secrets(config: DecibenchConfig) -> DecibenchConfig:
    """Populate secret-bearing config fields from env vars or keyring."""
    config.auth.vapi_api_key = resolve_secret("vapi", config.auth.vapi_api_key)
    config.auth.retell_api_key = resolve_secret("retell", config.auth.retell_api_key)
    config.auth.openai_api_key = resolve_secret("openai", config.auth.openai_api_key)
    config.auth.anthropic_api_key = resolve_secret("anthropic", config.auth.anthropic_api_key)
    config.auth.gemini_api_key = resolve_secret("gemini", config.auth.gemini_api_key)

    judge_provider = judge_provider_from_uri(config.providers.judge)
    if judge_provider == "openai":
        config.providers.judge_api_key = resolve_secret(
            "openai",
            config.providers.judge_api_key or config.auth.openai_api_key,
        )
    elif judge_provider == "anthropic":
        config.providers.judge_api_key = resolve_secret(
            "anthropic",
            config.providers.judge_api_key or config.auth.anthropic_api_key,
        )
    elif judge_provider == "gemini":
        config.providers.judge_api_key = resolve_secret(
            "gemini",
            config.providers.judge_api_key or config.auth.gemini_api_key,
        )

    return config
