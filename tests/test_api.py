from __future__ import annotations

import io
import math
import struct
import wave
from typing import TYPE_CHECKING

from fastapi.testclient import TestClient

from decibench.api.app import app
from decibench.models import CallTrace, TraceSpan, TranscriptSegment
from decibench.store import RunStore

if TYPE_CHECKING:
    from pathlib import Path

client = TestClient(app)


def _wav_bytes(duration_s: float = 0.15, sample_rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        for i in range(int(duration_s * sample_rate)):
            sample = int(0.25 * 32767 * math.sin(2 * math.pi * 440 * (i / sample_rate)))
            wav.writeframes(struct.pack("<h", sample))
    return buf.getvalue()


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert "version" in response.json()


def test_runs_endpoint_returns_json():
    response = client.get("/runs")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_calls_endpoint_returns_json():
    response = client.get("/calls")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_get_invalid_run():
    response = client.get("/runs/invalid-12345")
    assert response.status_code == 404


def test_get_invalid_call():
    response = client.get("/calls/invalid-12345")
    assert response.status_code == 404


def test_call_scenario_endpoint(monkeypatch, tmp_path: Path):
    store_path = tmp_path / "api.sqlite"
    monkeypatch.setenv("DECIBENCH_STORE_PATH", str(store_path))
    store = RunStore(store_path)
    store.save_call_trace(
        CallTrace(
            id="call-123",
            source="jsonl",
            transcript=[
                TranscriptSegment(role="caller", text="Where is my order?"),
                TranscriptSegment(role="agent", text="I can check your order status."),
            ],
        )
    )

    response = client.get("/calls/call-123/scenario")

    assert response.status_code == 200
    assert response.text.startswith("id: regression-call-123")
    assert "source_call_id: call-123" in response.text


def test_call_evaluate_endpoint(monkeypatch, tmp_path: Path):
    store_path = tmp_path / "api.sqlite"
    monkeypatch.setenv("DECIBENCH_STORE_PATH", str(store_path))
    store = RunStore(store_path)
    store.save_call_trace(
        CallTrace(
            id="call-456",
            source="jsonl",
            transcript=[
                TranscriptSegment(role="caller", text="I need help with billing."),
                TranscriptSegment(role="agent", text="I can help with your billing question."),
            ],
        )
    )

    response = client.post("/calls/call-456/evaluate")

    assert response.status_code == 200
    data = response.json()
    assert data["scenario_id"] == "imported-call-456"
    assert "passed" in data

    latest_response = client.get("/calls/call-456/evaluation")
    assert latest_response.status_code == 200
    assert latest_response.json()["scenario_id"] == "imported-call-456"

    list_response = client.get("/call-evaluations", params={"call_id": "call-456"})
    assert list_response.status_code == 200
    evaluations = list_response.json()
    assert len(evaluations) == 1
    assert evaluations[0]["call_id"] == "call-456"

    detail_response = client.get(f"/call-evaluations/{evaluations[0]['id']}")
    assert detail_response.status_code == 200
    assert detail_response.json()["scenario_id"] == "imported-call-456"


def test_audio_upload_test_endpoint_runs_agent_and_persists_results(monkeypatch, tmp_path: Path):
    store_path = tmp_path / "api.sqlite"
    monkeypatch.setenv("DECIBENCH_STORE_PATH", str(store_path))

    response = client.post(
        "/audio-tests",
        data={
            "target": "demo",
            "mode": "deterministic",
            "caller_text": "Hello, I need help booking an appointment.",
            "must_include": "hello, help",
            "max_latency_ms": "1200",
        },
        files={"audio": ("caller.wav", _wav_bytes(), "audio/wav")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["call_id"].startswith("audio-upload-")
    assert payload["evaluation_id"]
    assert 0 <= payload["score"] <= 100
    assert payload["audio_duration_ms"] > 0
    assert payload["agent_audio_bytes"] > 0
    assert payload["evaluation"]["scenario_id"].startswith("audio-upload-")

    store = RunStore(store_path)
    trace = store.get_call_trace(payload["call_id"])
    assert trace is not None
    assert trace.source == "dashboard-audio-upload"
    assert any(event.type.value == "caller_audio_end" for event in trace.events)
    assert any(segment.role == "agent" for segment in trace.transcript)

    latest_response = client.get(f"/calls/{payload['call_id']}/evaluation")
    assert latest_response.status_code == 200
    assert latest_response.json()["scenario_id"] == payload["evaluation"]["scenario_id"]


def test_audio_upload_test_endpoint_invalid_mode(monkeypatch, tmp_path: Path):
    store_path = tmp_path / "api.sqlite"
    monkeypatch.setenv("DECIBENCH_STORE_PATH", str(store_path))

    response = client.post(
        "/audio-tests",
        data={
            "target": "demo",
            "mode": "invalid-mode",
            "caller_text": "Hello",
        },
        files={"audio": ("caller.wav", _wav_bytes(), "audio/wav")},
    )

    assert response.status_code == 400
    assert "mode must be" in response.json()["detail"]


def test_audio_upload_test_endpoint_empty_audio(monkeypatch, tmp_path: Path):
    store_path = tmp_path / "api.sqlite"
    monkeypatch.setenv("DECIBENCH_STORE_PATH", str(store_path))

    response = client.post(
        "/audio-tests",
        data={
            "target": "demo",
            "mode": "deterministic",
            "caller_text": "Hello",
        },
        files={"audio": ("caller.wav", b"", "audio/wav")},
    )

    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()


def test_audio_upload_test_endpoint_must_include_parsing(monkeypatch, tmp_path: Path):
    store_path = tmp_path / "api.sqlite"
    monkeypatch.setenv("DECIBENCH_STORE_PATH", str(store_path))

    response = client.post(
        "/audio-tests",
        data={
            "target": "demo",
            "mode": "deterministic",
            "caller_text": "Hello",
            "must_include": "hello,world\nfoo, bar",
            "must_not_say": "no,way\nnever, say",
        },
        files={"audio": ("caller.wav", _wav_bytes(), "audio/wav")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["call_id"].startswith("audio-upload-")


def test_call_timeline_endpoint(monkeypatch, tmp_path: Path):
    store_path = tmp_path / "api.sqlite"
    monkeypatch.setenv("DECIBENCH_STORE_PATH", str(store_path))
    store = RunStore(store_path)
    store.save_call_trace(
        CallTrace(
            id="call-tl-1",
            source="jsonl",
            duration_ms=2500.0,
            transcript=[
                TranscriptSegment(role="caller", text="Hi", start_ms=0, end_ms=500),
                TranscriptSegment(role="agent", text="Hello", start_ms=500, end_ms=1500),
            ],
            spans=[
                TraceSpan(name="asr", start_ms=0, end_ms=500, duration_ms=500, turn_index=0),
                TraceSpan(name="llm", start_ms=500, end_ms=1200, duration_ms=700, turn_index=0),
                TraceSpan(name="tts", start_ms=1200, end_ms=1500, duration_ms=300, turn_index=0),
            ],
        )
    )

    response = client.get("/calls/call-tl-1/timeline")

    assert response.status_code == 200
    payload = response.json()
    assert payload["call_id"] == "call-tl-1"
    assert payload["duration_ms"] == 2500.0
    assert len(payload["spans"]) == 3
    assert {s["name"] for s in payload["spans"]} == {"asr", "llm", "tts"}
    assert len(payload["turns"]) == 2
    assert payload["turns"][0]["role"] == "caller"


def test_regression_post_endpoint(monkeypatch, tmp_path: Path):
    store_path = tmp_path / "api.sqlite"
    monkeypatch.setenv("DECIBENCH_STORE_PATH", str(store_path))
    store = RunStore(store_path)
    store.save_call_trace(
        CallTrace(
            id="call-reg-1",
            source="jsonl",
            transcript=[
                TranscriptSegment(role="caller", text="Cancel my subscription"),
                TranscriptSegment(role="agent", text="I can help with cancellation."),
            ],
        )
    )

    response = client.post("/calls/call-reg-1/regression")

    assert response.status_code == 200
    payload = response.json()
    assert payload["call_id"] == "call-reg-1"
    assert payload["scenario_id"] == "regression-call-reg-1"
    assert "id: regression-call-reg-1" in payload["yaml"]


def test_failure_inbox_stats_endpoint(monkeypatch, tmp_path: Path):
    store_path = tmp_path / "api.sqlite"
    monkeypatch.setenv("DECIBENCH_STORE_PATH", str(store_path))
    store = RunStore(store_path)

    # Empty store: stats should still respond cleanly.
    empty = client.get("/failure-inbox/stats")
    assert empty.status_code == 200
    assert empty.json()["total_evaluations"] == 0

    # Seed one call + evaluation so the aggregates have something to count.
    store.save_call_trace(
        CallTrace(
            id="call-stats-1",
            source="jsonl",
            transcript=[
                TranscriptSegment(role="caller", text="What time is it?"),
                TranscriptSegment(role="agent", text="It is 3 PM."),
            ],
        )
    )
    eval_response = client.post("/calls/call-stats-1/evaluate")
    assert eval_response.status_code == 200

    stats = client.get("/failure-inbox/stats").json()
    assert stats["total_evaluations"] == 1
    assert stats["sources"].get("jsonl") == 1
    assert stats["score"]["max"] >= 0


def test_call_evaluations_search_and_score_filters(monkeypatch, tmp_path: Path):
    store_path = tmp_path / "api.sqlite"
    monkeypatch.setenv("DECIBENCH_STORE_PATH", str(store_path))
    store = RunStore(store_path)
    store.save_call_trace(
        CallTrace(
            id="filter-call-A",
            source="jsonl",
            transcript=[
                TranscriptSegment(role="caller", text="Question A"),
                TranscriptSegment(role="agent", text="Answer A"),
            ],
        )
    )

    assert client.post("/calls/filter-call-A/evaluate").status_code == 200

    # `q` substring search hits the call id.
    found = client.get("/call-evaluations", params={"q": "filter-call-a"}).json()
    assert len(found) == 1

    missing = client.get("/call-evaluations", params={"q": "nope-no-match"}).json()
    assert missing == []

    # `max_score=0` should exclude any non-failing evaluation.
    capped = client.get("/call-evaluations", params={"max_score": 0}).json()
    for entry in capped:
        assert entry["score"] <= 0
