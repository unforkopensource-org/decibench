"""API routes for call management — upload, list, evaluate."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import PlainTextResponse

from decibench.importers.audio import AudioImporter
from decibench.models import CallTimelinePayload, CallTrace, EvalResult, RegressionScenarioPayload
from decibench.replay.scenario import trace_to_scenario_yaml
from decibench.store import get_store

if TYPE_CHECKING:
    from decibench.config import DecibenchConfig

router = APIRouter(prefix="/calls", tags=["calls"])


@router.get("", summary="List call traces")
def list_calls(
    limit: int = 50,
    skip: int = 0,
    source: str | None = None,
    since: str | None = None,
) -> list[dict[str, Any]]:
    return get_store().list_call_traces(limit=limit, offset=skip, source=source, since=since)


@router.get("/{call_id}", summary="Get call by ID", response_model=CallTrace)
def get_call(call_id: str) -> CallTrace:
    trace = get_store().get_call_trace(call_id)
    if not trace:
        raise HTTPException(status_code=404, detail="Call trace not found.")
    return trace


@router.get(
    "/{call_id}/timeline",
    summary="Get call timeline (spans + turns) for the dashboard timeline view",
    response_model=CallTimelinePayload,
)
def get_call_timeline(call_id: str) -> CallTimelinePayload:
    trace = get_call(call_id)
    event_kinds: dict[str, int] = {}
    for event in trace.events:
        key = event.type.value
        event_kinds[key] = event_kinds.get(key, 0) + 1
    turns = [
        {
            "role": segment.role,
            "text": segment.text,
            "start_ms": segment.start_ms,
            "end_ms": segment.end_ms,
            "confidence": segment.confidence,
        }
        for segment in trace.transcript
    ]
    return CallTimelinePayload(
        call_id=trace.id,
        duration_ms=trace.duration_ms,
        spans=trace.spans,
        turns=turns,
        event_kinds=event_kinds,
    )


@router.get(
    "/{call_id}/scenario",
    summary="Render the regression scenario for this call as YAML text",
    response_class=PlainTextResponse,
)
def get_call_scenario(call_id: str) -> str:
    trace = get_call(call_id)
    return trace_to_scenario_yaml(trace)


@router.post(
    "/{call_id}/regression",
    summary="Generate a regression scenario from a call (structured response)",
    response_model=RegressionScenarioPayload,
)
def generate_regression(call_id: str) -> RegressionScenarioPayload:
    """Workbench action: turn this failed call into a regression scenario.

    Returns the YAML text plus the scenario id so the dashboard can offer
    copy/download without a second round-trip.
    """
    trace = get_call(call_id)
    yaml_text = trace_to_scenario_yaml(trace)
    return RegressionScenarioPayload(
        call_id=trace.id,
        scenario_id=f"regression-{trace.id}",
        yaml=yaml_text,
    )


@router.post(
    "/{call_id}/evaluate",
    summary="Evaluate an imported call trace (and persist the result)",
    response_model=EvalResult,
)
async def evaluate_call(call_id: str) -> EvalResult:
    trace = get_call(call_id)
    from decibench.config import load_config
    from decibench.orchestrator import Orchestrator

    config = load_config()
    orch = Orchestrator(config)
    result = await orch.evaluate_trace(trace)
    get_store().save_call_evaluation(trace, result)
    return result


@router.get(
    "/{call_id}/evaluation", summary="Get the latest stored evaluation for a call", response_model=EvalResult
)
def get_latest_call_evaluation(call_id: str) -> EvalResult:
    store = get_store()
    summaries = store.list_call_evaluations(limit=1, call_id=call_id)
    if not summaries:
        raise HTTPException(status_code=404, detail="Call evaluation not found.")
    result = store.get_call_evaluation(summaries[0]["id"])
    if result is None:
        raise HTTPException(status_code=404, detail="Call evaluation payload not found.")
    return result


@router.post("/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload_call_audio(
    file: UploadFile = File(...),  # noqa: B008
    agent_name: str = Form(default=""),
    scenario_id: str = Form(default=""),
    diarize: bool = Form(default=False),
    config: DecibenchConfig = ...,  # injected via dependency
) -> dict[str, Any]:
    """Upload a call audio file for evaluation.

    Returns immediately with a job ID. The trace is stored and can be
    evaluated via POST /calls/{call_id}/evaluate.
    """
    # Validate extension
    suffix = Path(file.filename or "upload.wav").suffix.lower()
    allowed = {".wav", ".mp3", ".m4a", ".ogg", ".flac"}
    if suffix not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format {suffix}. Allowed: {', '.join(allowed)}",
        )

    # Save to temp file
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        importer = AudioImporter(config)
        trace = await importer.import_file(
            tmp_path,
            source="api_upload",
            agent_name=agent_name,
            diarize=diarize,
        )
    except Exception as e:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=str(e)) from e
    finally:
        tmp_path.unlink(missing_ok=True)

    # Persist to store
    store = get_store()
    store.save_call_trace(trace)

    return {
        "call_id": trace.id,
        "status": "imported",
        "duration_ms": trace.duration_ms,
        "transcript_segments": len(trace.transcript),
        "evaluate_url": f"/api/calls/{trace.id}/evaluate",
    }


@router.post("/{call_id}/evaluate")
async def evaluate_uploaded_call(
    call_id: str,
    suite: str = Form(default="quick"),
    mode: str = Form(default="semantic"),
    config: DecibenchConfig = ...,
) -> dict[str, Any]:
    """Evaluate a previously uploaded call against a test suite."""
    store = get_store()
    trace = store.get_call_trace(call_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="Call not found")

    # Run evaluation using the orchestrator's evaluate-trace path
    from decibench.orchestrator import Orchestrator

    orch = Orchestrator(config)
    result = await orch.evaluate_trace(trace, suite=suite, mode=mode)

    # Persist result
    store.save_call_evaluation(trace, result)

    return {
        "call_id": call_id,
        "suite": suite,
        "score": result.score,
        "passed": result.passed,
        "metrics": result.metric_values,
        "failures": result.failures,
    }
