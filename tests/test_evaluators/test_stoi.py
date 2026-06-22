"""Tests for STOI intelligibility estimator — multi-signal speech quality proxy."""

from __future__ import annotations

import math
import struct

import pytest

from decibench.evaluators.stoi import STOIEvaluator
from decibench.models import (
    AudioBuffer,
    CallSummary,
    ConversationTurn,
    Scenario,
    TranscriptResult,
    TranscriptSegment,
)


def _scenario() -> Scenario:
    return Scenario(
        id="test-stoi",
        description="Test",
        conversation=[ConversationTurn(role="caller", text="Hello")],
    )


def _summary(audio: bytes | None = None) -> CallSummary:
    return CallSummary(duration_ms=5000, turn_count=1, agent_audio=audio or b"")


def _make_tone(freq: float = 440, duration_s: float = 1.0, sr: int = 16000, amplitude: int = 8000) -> bytes:
    n = int(sr * duration_s)
    data = bytearray(n * 2)
    for i in range(n):
        val = int(amplitude * math.sin(2 * math.pi * freq * i / sr))
        struct.pack_into("<h", data, i * 2, val)
    return bytes(data)


# ---------------------------------------------------------------------------
# _spectral_clarity
# ---------------------------------------------------------------------------


def test_spectral_clarity_short_audio():
    """Audio < 1024 samples -> -1."""
    audio = AudioBuffer(data=b"\x00\x00" * 500)
    assert STOIEvaluator._spectral_clarity(audio) == -1.0


def test_spectral_clarity_silence():
    """All-zero audio -> 0.0 (no energy in any band)."""
    audio = AudioBuffer(data=b"\x00\x00" * 2048)
    assert STOIEvaluator._spectral_clarity(audio) == 0.0


def test_spectral_clarity_tone_in_speech_band():
    """440 Hz tone (speech band) -> high clarity (> 0.5)."""
    audio = AudioBuffer(data=_make_tone(440, 1.0))
    score = STOIEvaluator._spectral_clarity(audio)
    assert 0.5 <= score <= 1.0


def test_spectral_clarity_tone_outside_speech_band():
    """50 Hz tone (below speech band) -> low clarity."""
    audio = AudioBuffer(data=_make_tone(50, 1.0))
    score = STOIEvaluator._spectral_clarity(audio)
    assert score <= 0.3


def test_spectral_clarity_five_second_tone():
    """Long audio is analyzed over full duration, not just first 128ms."""
    audio = AudioBuffer(data=_make_tone(440, 5.0))
    score_short = STOIEvaluator._spectral_clarity(AudioBuffer(data=_make_tone(440, 0.5)))
    score_long = STOIEvaluator._spectral_clarity(audio)
    assert score_long > 0.5
    # Long clean tone should be similar to short clean tone
    assert abs(score_long - score_short) < 0.2


def test_spectral_clarity_mixed_audio():
    """Audio with out-of-band noise mixed in -> clarity drops vs clean tone."""
    tone = _make_tone(440, 0.5)  # speech band
    noise = _make_tone(50, 0.5)  # below speech band
    mixed = bytearray()
    for i in range(0, min(len(tone), len(noise)), 2):
        t = int.from_bytes(tone[i : i + 2], "little", signed=True)
        n = int.from_bytes(noise[i : i + 2], "little", signed=True)
        mixed.extend((t + n).to_bytes(2, "little", signed=True))
    tone_only = _make_tone(440, 1.0)
    score_mixed = STOIEvaluator._spectral_clarity(AudioBuffer(data=bytes(mixed)))
    score_tone = STOIEvaluator._spectral_clarity(AudioBuffer(data=tone_only))
    assert score_mixed < score_tone


# ---------------------------------------------------------------------------
# _stt_confidence_score
# ---------------------------------------------------------------------------


def test_stt_confidence_empty_segments():
    """No segments -> -1."""
    transcript = TranscriptResult(text="hello", segments=[])
    assert STOIEvaluator._stt_confidence_score(transcript) == -1.0


def test_stt_confidence_with_zero():
    """All-zero confidences -> -1."""
    transcript = TranscriptResult(
        text="hello",
        segments=[TranscriptSegment(role="agent", text="hi", confidence=0.0)],
    )
    assert STOIEvaluator._stt_confidence_score(transcript) == -1.0


def test_stt_confidence_average():
    """Multiple segments -> average confidence."""
    transcript = TranscriptResult(
        text="hello world",
        segments=[
            TranscriptSegment(role="agent", text="hello", confidence=0.9),
            TranscriptSegment(role="agent", text="world", confidence=0.7),
        ],
    )
    score = STOIEvaluator._stt_confidence_score(transcript)
    assert score == 0.8


# ---------------------------------------------------------------------------
# _word_rate_score
# ---------------------------------------------------------------------------


def test_word_rate_empty_transcript():
    """No text -> -1."""
    transcript = TranscriptResult(text="", segments=[], duration_ms=10000)
    assert STOIEvaluator._word_rate_score(transcript) == -1.0


def test_word_rate_zero_duration():
    """Zero duration -> -1."""
    transcript = TranscriptResult(text="hello world", segments=[], duration_ms=0)
    assert STOIEvaluator._word_rate_score(transcript) == -1.0


def test_word_rate_optimal():
    """2-3.5 wps -> 1.0."""
    transcript = TranscriptResult(text="hello how can I help you today", segments=[], duration_ms=2000)
    assert STOIEvaluator._word_rate_score(transcript) == 1.0


def test_word_rate_too_fast():
    """> 7 wps -> 0.0."""
    transcript = TranscriptResult(text=" ".join(["word"] * 80), segments=[], duration_ms=10000)
    score = STOIEvaluator._word_rate_score(transcript)
    assert score == 0.0


def test_word_rate_too_slow():
    """< 0.5 wps -> 0.0."""
    transcript = TranscriptResult(text="hello", segments=[], duration_ms=10000)
    score = STOIEvaluator._word_rate_score(transcript)
    assert score == 0.0


# ---------------------------------------------------------------------------
# _estimate_intelligibility
# ---------------------------------------------------------------------------


def test_estimate_no_usable_data():
    """No audio, no transcript -> 0.0 (SNR on empty audio still produces a weight)."""
    audio = AudioBuffer(data=b"")
    transcript = TranscriptResult(text="", segments=[])
    score, components = STOIEvaluator._estimate_intelligibility(audio, transcript)
    assert score == 0.0
    assert "snr_db" in components  # SNR is computed even on empty audio


def test_estimate_clean_audio():
    """Clean tone + confident transcript -> score > 0."""
    audio = AudioBuffer(data=_make_tone(440, 2.0))
    transcript = TranscriptResult(
        text="hello how are you today",
        segments=[TranscriptSegment(role="agent", text="hello how are you today", confidence=0.95)],
        duration_ms=3000,
    )
    score, components = STOIEvaluator._estimate_intelligibility(audio, transcript)
    assert 0.0 <= score <= 1.0
    assert "snr_db" in components
    assert "spectral_clarity" in components
    assert "stt_confidence" in components


# ---------------------------------------------------------------------------
# Full evaluate() flow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evaluate_no_audio():
    """No agent audio -> empty results."""
    evaluator = STOIEvaluator()
    results = await evaluator.evaluate(_scenario(), _summary(), TranscriptResult(text="", segments=[]), {})
    assert results == []


@pytest.mark.asyncio
async def test_evaluate_clean_audio():
    """Clean audio passes default threshold."""
    evaluator = STOIEvaluator()
    audio = _make_tone(440, 2.0)
    transcript = TranscriptResult(
        text="hello how are you today",
        segments=[TranscriptSegment(role="agent", text="hello how are you today", confidence=0.95)],
        duration_ms=3000,
    )
    results = await evaluator.evaluate(_scenario(), _summary(audio), transcript, {})
    assert len(results) == 1
    assert results[0].name == "intelligibility_estimate"
    assert 0.0 <= results[0].value <= 1.0
    assert results[0].details["method"] == "multi_signal_estimate"


@pytest.mark.asyncio
async def test_evaluate_custom_threshold():
    """Custom threshold is reflected in metric."""
    evaluator = STOIEvaluator()
    audio = _make_tone(440, 2.0)
    transcript = TranscriptResult(
        text="hello how are you today",
        segments=[TranscriptSegment(role="agent", text="hello how are you today", confidence=0.95)],
        duration_ms=3000,
    )
    results = await evaluator.evaluate(
        _scenario(), _summary(audio), transcript, {"intelligibility_threshold": 0.9}
    )
    assert results[0].threshold == 0.9
