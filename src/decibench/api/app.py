"""FastAPI server backing the Decibench dashboard / failure workbench.

This is intentionally a thin layer over `RunStore` and the imported-call
evaluation pipeline. Every endpoint either:

- returns a typed Pydantic model from `decibench.models`, or
- returns a small structured dict the dashboard explicitly needs.

The frontend should never have to crack open large JSON blobs to discover
structure — when a screen needs derived shape (timeline, inbox stats, etc.)
the backend exposes a first-class endpoint for it.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from decibench.config import load_config
from decibench.models import CallTrace, EvalResult, SuiteResult, TraceSpan
from decibench.providers.registry import get_judge
from decibench.rag import RagStore, ingest_paths, ingest_text, retrieve, synthesize_scenarios
from decibench.rag.embed import CloudEgressForbidden
from decibench.replay.evaluate import ImportedCallEvaluator
from decibench.replay.scenario import trace_to_scenario_yaml
from decibench.store import RunStore, default_store_path

app = FastAPI(
    title="Decibench API",
    description="Local-first API for the Decibench failure-analysis workbench.",
    version="0.1.0",
)


# --------------------------------------------------------------------- helpers


_STATIC_DIR = Path(__file__).parent / "static"
_ASSETS_DIR = _STATIC_DIR / "assets"
if _ASSETS_DIR.is_dir():
    # Vite emits hashed bundles into static/assets/*.{js,css}. Mount them so
    # the built `index.html` can resolve `/assets/...` references.
    app.mount("/assets", StaticFiles(directory=str(_ASSETS_DIR)), name="assets")


def get_static_html() -> str:
    path = _STATIC_DIR / "index.html"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return (
        "<h1>Dashboard build missing.</h1>"
        "<p>Run <code>cd dashboard && npm install && npm run build</code> "
        "to produce <code>src/decibench/api/static/index.html</code>.</p>"
    )


def get_store() -> RunStore:
    """Per-request store instance — cheap (just opens a SQLite connection)."""
    return RunStore(default_store_path())


def get_imported_call_evaluator() -> ImportedCallEvaluator:
    """Build the default imported-call evaluator stack from on-disk config.

    Resolves through :meth:`ImportedCallEvaluator.from_config` which pulls the
    canonical :func:`decibench.evaluators.standard_stack` set — the same stack
    the live ``Orchestrator`` uses. This was previously hand-curated to three
    evaluators, producing a different score offline vs. online for the same
    trace; v1 fixes that.
    """
    config = load_config()
    judge = (
        get_judge(
            config.providers.judge,
            model=config.providers.judge_model,
            api_key=config.providers.judge_api_key,
            temperature=config.evaluation.judge_temperature,
            judge_runs=config.evaluation.judge_runs,
        )
        if config.has_judge
        else None
    )
    return ImportedCallEvaluator.from_config(config, judge=judge)


# ------------------------------------------------------------- response models


class CallTimelinePayload(BaseModel):
    """Lightweight timeline view for the call-detail screen.

    The full ``CallTrace`` payload can be heavy (raw audio metadata, tool
    payloads, vendor blobs). The timeline only carries what the timing chart
    and turn list need: spans, transcript turns, and minimal event tags.
    """

    call_id: str
    duration_ms: float
    spans: list[TraceSpan]
    turns: list[dict[str, Any]]
    event_kinds: dict[str, int]


class RegressionScenarioPayload(BaseModel):
    """Structured response for the regression-action button.

    The ``yaml`` field is what the user copies/exports; ``scenario_id`` matches
    what the YAML's ``id:`` field will be so the frontend can pre-fill any
    follow-up view without re-parsing.
    """

    call_id: str
    scenario_id: str
    yaml: str


class FailureInboxStats(BaseModel):
    """Aggregate counters that drive the workbench header."""

    total_evaluations: int
    failed: int
    passed: int
    sources: dict[str, int]
    categories: dict[str, int]
    score: dict[str, float]


# --------------------------------------------------------------- dashboard SPA


@app.get("/", summary="Dashboard index", response_class=HTMLResponse)
@app.get("/dashboard", summary="Web dashboard", response_class=HTMLResponse)
def serve_dashboard() -> str:
    return get_static_html()


@app.get("/health", summary="Health check")
def health() -> dict[str, str]:
    return {"status": "ok", "version": "0.1.0"}


# -------------------------------------------------------------------- runs API


@app.get("/runs", summary="List runs")
def list_runs(limit: int = 50, skip: int = 0) -> list[dict[str, Any]]:
    return get_store().list_runs(limit=limit, offset=skip)


@app.get("/runs/{run_id}", summary="Get run by ID", response_model=SuiteResult)
def get_run(run_id: str) -> SuiteResult:
    result = get_store().get_suite_result(run_id)
    if not result:
        raise HTTPException(status_code=404, detail="Run not found.")
    return result


# ------------------------------------------------------------------- calls API


@app.get("/calls", summary="List call traces")
def list_calls(
    limit: int = 50,
    skip: int = 0,
    source: str | None = None,
    since: str | None = None,
) -> list[dict[str, Any]]:
    return get_store().list_call_traces(limit=limit, offset=skip, source=source, since=since)


@app.get("/calls/{call_id}", summary="Get call by ID", response_model=CallTrace)
def get_call(call_id: str) -> CallTrace:
    trace = get_store().get_call_trace(call_id)
    if not trace:
        raise HTTPException(status_code=404, detail="Call trace not found.")
    return trace


@app.get(
    "/calls/{call_id}/timeline",
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


@app.get(
    "/calls/{call_id}/scenario",
    summary="Render the regression scenario for this call as YAML text",
    response_class=PlainTextResponse,
)
def get_call_scenario(call_id: str) -> str:
    trace = get_call(call_id)
    return trace_to_scenario_yaml(trace)


@app.post(
    "/calls/{call_id}/regression",
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


@app.post(
    "/calls/{call_id}/evaluate",
    summary="Evaluate an imported call trace (and persist the result)",
    response_model=EvalResult,
)
async def evaluate_call(call_id: str) -> EvalResult:
    trace = get_call(call_id)
    evaluator = get_imported_call_evaluator()
    result = await evaluator.evaluate_trace(trace)
    get_store().save_call_evaluation(trace, result)
    return result


@app.get(
    "/calls/{call_id}/evaluation",
    summary="Get the latest stored evaluation for a call",
    response_model=EvalResult,
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


# ---------------------------------------------------------- evaluations / inbox


@app.get("/call-evaluations", summary="List stored imported-call evaluations")
def list_call_evaluations(
    limit: int = Query(50, ge=1, le=500),
    source: str | None = None,
    failed_only: bool = False,
    category: str | None = None,
    call_id: str | None = None,
    since: str | None = None,
    max_score: float | None = Query(None, ge=0, le=100),
    q: str | None = Query(None, description="Substring match on call id, scenario, or source"),
) -> list[dict[str, Any]]:
    return get_store().list_call_evaluations(
        limit=limit,
        source=source,
        failed_only=failed_only,
        category=category,
        call_id=call_id,
        since=since,
        max_score=max_score,
        q=q,
    )


@app.get(
    "/call-evaluations/{evaluation_id}",
    summary="Get stored imported-call evaluation by id",
    response_model=EvalResult,
)
def get_stored_call_evaluation(evaluation_id: str) -> EvalResult:
    result = get_store().get_call_evaluation(evaluation_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Call evaluation not found.")
    return result


@app.get(
    "/failure-inbox/stats",
    summary="Aggregate counters that drive the failure-workbench header",
    response_model=FailureInboxStats,
)
def failure_inbox_stats() -> FailureInboxStats:
    return FailureInboxStats(**get_store().failure_inbox_stats())


# ------------------------------------------------------------------ RAG API
#
# Single backend for the dashboard /rag/* screens, the CLI `decibench rag`
# commands, and the MCP `rag_*` tools. No drift across surfaces.


class RagIngestText(BaseModel):
    """Body for POST /rag/ingest-text — paste-text path from the UI."""

    text: str
    title: str = "pasted-snippet"
    cloud_confirm: bool = False


class RagSynthesizeRequest(BaseModel):
    """Body for POST /rag/synthesize — topics + suite slug."""

    topics: list[str]
    suite: str = "custom-rag"
    out_dir: str | None = None


class RunStartRequest(BaseModel):
    """Body for POST /runs — kick off a run from the dashboard.

    Field names mirror ``decibench run`` flags so users can copy-paste between
    surfaces without re-learning vocabulary.
    """

    target: str
    suite: str = "quick"
    mode: str = "deterministic"  # deterministic | semantic | semantic-local | semantic-rag
    parallel: int = 2
    output_dir: str | None = None


def _rag_store() -> RagStore:
    return RagStore(default_store_path())


@app.get("/rag/documents", summary="List ingested RAG documents")
def rag_list_documents() -> dict[str, Any]:
    docs = _rag_store().list_documents()
    return {"documents": [d.__dict__ for d in docs]}


@app.get("/rag/stats", summary="Corpus statistics")
def rag_stats() -> dict[str, Any]:
    config = load_config()
    s = _rag_store().stats()
    s["configured_embedder"] = config.rag.embedding
    s["allow_cloud"] = config.rag.allow_cloud
    return s


@app.post("/rag/ingest-text", summary="Ingest a text snippet (paste-text path)")
def rag_ingest_text(body: RagIngestText) -> dict[str, Any]:
    config = load_config()
    rag_cfg = config.rag
    try:
        result = ingest_text(
            text=body.text,
            title=body.title,
            store=_rag_store(),
            embedder_uri=rag_cfg.embedding,
            allow_cloud=rag_cfg.allow_cloud or body.cloud_confirm,
            target_tokens=rag_cfg.chunk_size_tokens,
            overlap_tokens=rag_cfg.chunk_overlap_tokens,
        )
    except CloudEgressForbidden as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result.as_dict()


@app.post("/rag/ingest-files", summary="Ingest uploaded files (multipart)")
async def rag_ingest_files(
    files: list[UploadFile] = File(...),  # noqa: B008
    cloud_confirm: bool = Form(False),
) -> dict[str, Any]:
    """Multipart upload — the browser drag-drop path lands here.

    Files are written to a per-request temp directory and ingested via the
    same ``ingest_paths`` function the CLI uses; the temp dir is cleaned
    up regardless of success.
    """
    import tempfile
    from pathlib import Path as _P

    config = load_config()
    rag_cfg = config.rag

    with tempfile.TemporaryDirectory(prefix="decibench-upload-") as tmp:
        paths: list[_P] = []
        for f in files:
            target = _P(tmp) / (f.filename or f"upload-{uuid.uuid4().hex[:8]}.txt")
            data = await f.read()
            target.write_bytes(data)
            paths.append(target)
        try:
            result = ingest_paths(
                paths,
                store=_rag_store(),
                embedder_uri=rag_cfg.embedding,
                allow_cloud=rag_cfg.allow_cloud or cloud_confirm,
                target_tokens=rag_cfg.chunk_size_tokens,
                overlap_tokens=rag_cfg.chunk_overlap_tokens,
            )
        except CloudEgressForbidden as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return result.as_dict()


@app.delete("/rag/documents/{document_id}", summary="Remove a single document")
def rag_remove_document(document_id: str) -> dict[str, Any]:
    store = _rag_store()
    docs = [d for d in store.list_documents() if d.id.startswith(document_id)]
    if not docs:
        raise HTTPException(status_code=404, detail="document not found")
    if len(docs) > 1:
        raise HTTPException(status_code=400, detail="id prefix matches multiple — pass a longer id")
    store.remove_document(docs[0].id)
    return {"removed": docs[0].id}


@app.get("/rag/chunks/{document_id}", summary="Get chunks for a document")
def rag_get_chunks(document_id: str) -> dict[str, Any]:
    store = _rag_store()
    docs = [d for d in store.list_documents() if d.id.startswith(document_id)]
    if not docs:
        raise HTTPException(status_code=404, detail="document not found")
    if len(docs) > 1:
        raise HTTPException(status_code=400, detail="id prefix matches multiple")

    doc = docs[0]
    chunks = store.get_document_chunks(doc.id)
    return {
        "document": doc.__dict__,
        "chunks": [{"id": c.id, "text": c.text, "section_path": c.section_path} for c in chunks],
    }


@app.delete("/rag/documents", summary="Wipe the entire RAG corpus")
def rag_remove_all() -> dict[str, Any]:
    n = _rag_store().remove_all()
    return {"removed": n}


@app.get("/rag/search", summary="Debug retrieval — top-K chunks for a query")
def rag_search_endpoint(query: str, k: int = 5) -> dict[str, Any]:
    config = load_config()
    try:
        hits = retrieve(
            query,
            k=k,
            store=_rag_store(),
            embedder_uri=config.rag.embedding,
            allow_cloud=config.rag.allow_cloud,
        )
    except CloudEgressForbidden as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "hits": [
            {
                "score": h.score,
                "text": h.text,
                "section_path": h.section_path,
                "document_id": h.document_id,
            }
            for h in hits
        ],
    }


@app.post("/rag/synthesize", summary="Synthesize scenarios from the corpus")
def rag_synthesize_endpoint(body: RagSynthesizeRequest) -> dict[str, Any]:
    from importlib import resources
    from pathlib import Path as _P

    config = load_config()
    if not config.has_judge:
        raise HTTPException(
            status_code=400,
            detail="No LLM judge configured. Set [providers] judge in decibench.toml.",
        )
    store = _rag_store()
    if store.chunk_count() == 0:
        raise HTTPException(
            status_code=400,
            detail="Corpus is empty. Ingest something first.",
        )

    topic_list = [
        {
            "id_slug": _slug(t)[:40] or f"topic-{i}",
            "intent": t,
            "tags": "rag,workbench",
            "criterion": f"Agent handles: {t}",
        }
        for i, t in enumerate(body.topics, start=1)
    ]

    if body.out_dir:
        out_path = _P(body.out_dir)
    else:
        out_path = _P(str(resources.files("decibench.scenarios.suites"))) / body.suite

    result = synthesize_scenarios(
        topics=topic_list,
        suite=body.suite,
        out_dir=out_path,
        judge_uri=config.providers.judge,
        judge_model=config.providers.judge_model,
        judge_api_key=config.providers.judge_api_key,
        store=store,
        embedder_uri=config.rag.embedding,
        grounding_threshold=config.rag.grounding_threshold,
    )
    return result.as_dict()


@app.post("/rag/synthesize-preview", summary="Generate a single scenario without writing to disk")
def rag_synthesize_preview(body: RagSynthesizeRequest) -> dict[str, Any]:
    import tempfile
    from pathlib import Path as _P

    config = load_config()
    if not config.has_judge:
        raise HTTPException(status_code=400, detail="No LLM judge configured.")

    store = _rag_store()
    if store.chunk_count() == 0:
        raise HTTPException(status_code=400, detail="Corpus is empty.")

    topic_list = [
        {
            "id_slug": _slug(t)[:40] or f"topic-{i}",
            "intent": t,
            "tags": "rag,workbench,preview",
            "criterion": f"Agent handles: {t}",
        }
        for i, t in enumerate(body.topics[:1], start=1)  # Only take the first topic
    ]

    with tempfile.TemporaryDirectory() as tmp:
        out_path = _P(tmp)
        result = synthesize_scenarios(
            topics=topic_list,
            suite=body.suite,
            out_dir=out_path,
            judge_uri=config.providers.judge,
            judge_model=config.providers.judge_model,
            judge_api_key=config.providers.judge_api_key,
            store=store,
            embedder_uri=config.rag.embedding,
            grounding_threshold=config.rag.grounding_threshold,
        )

        preview_yaml = ""
        if result.written:
            preview_yaml = result.written[0].read_text()

        return {"result": result.as_dict(), "yaml": preview_yaml}


# ----------------------------------------------------- run-start + progress
#
# POST /runs starts a run in the background and returns a task_id. The
# dashboard subscribes to /runs/stream/{task_id} for live progress events
# (scenario start / pass / fail / final score). Same Orchestrator the CLI
# uses; no duplicate logic.


_run_tasks: dict[str, dict[str, Any]] = {}
_run_events: dict[str, asyncio.Queue[dict[str, Any]]] = {}


@app.post("/runs", summary="Start a run; returns a task_id for streaming")
def start_run(body: RunStartRequest) -> dict[str, Any]:
    from decibench.mcp._helpers import preflight_check

    config = load_config()
    preflight = preflight_check(body.target, body.mode, config)
    if not preflight["ok"]:
        summary = preflight.get("summary", "Pre-flight check failed.")
        findings = preflight.get("findings", [])
        detail = summary
        if findings:
            detail += "\n\nFindings:\n- " + "\n- ".join(findings)
        raise HTTPException(status_code=400, detail=detail)

    task_id = f"run-{uuid.uuid4().hex[:12]}"
    _run_events[task_id] = asyncio.Queue()
    _run_tasks[task_id] = {
        "started_at": datetime.now(UTC).isoformat(),
        "target": body.target,
        "mode": body.mode,
        "suite": body.suite,
        "status": "queued",
        "run_id": None,
        "score": None,
    }
    asyncio.create_task(_execute_run(task_id, body))
    return {
        "task_id": task_id,
        "stream_url": f"/runs/stream/{task_id}",
        "status": "queued",
    }


@app.get("/runs/task/{task_id}", summary="Poll a queued/running task's state")
def get_run_task(task_id: str) -> dict[str, Any]:
    if task_id not in _run_tasks:
        raise HTTPException(status_code=404, detail="task not found")
    return _run_tasks[task_id]


@app.websocket("/runs/stream/{task_id}")
async def stream_run(websocket: WebSocket, task_id: str) -> None:
    """WebSocket: live progress events for a running task.

    Events: {type: "started"|"scenario_done"|"complete"|"error", ...}.
    Closes when ``complete`` or ``error`` is emitted.
    """
    if task_id not in _run_events:
        await websocket.close(code=1008, reason="unknown task_id")
        return
    await websocket.accept()
    queue = _run_events[task_id]
    try:
        while True:
            ev = await queue.get()
            await websocket.send_text(json.dumps(ev))
            if ev.get("type") in ("complete", "error"):
                break
    except WebSocketDisconnect:
        return


async def _execute_run(task_id: str, body: RunStartRequest) -> None:
    """Background task: run the orchestrator and emit progress events.

    Single-source-of-truth code path: same Orchestrator the CLI uses, same
    storage path, same evaluator stack. The WebSocket layer here is pure
    plumbing.
    """
    from decibench.orchestrator import Orchestrator

    config = load_config()
    # Mode mapping — semantic-rag uses an already-synthesized suite slug.
    if body.mode == "deterministic":
        config.providers.judge = "none"
    elif body.mode in ("semantic", "semantic-local", "semantic-rag"):
        if not config.has_judge:
            await _emit(
                task_id,
                {
                    "type": "error",
                    "message": f"mode={body.mode} requires a configured judge",
                },
            )
            return

    task = _run_tasks[task_id]
    task["status"] = "running"
    await _emit(task_id, {"type": "started", "target": body.target, "suite": body.suite, "mode": body.mode})

    completed_scenarios: list[str] = []

    def on_progress(scenario_id: str, passed: bool, score: float, current: int, total: int) -> None:
        completed_scenarios.append(scenario_id)
        asyncio.get_event_loop().create_task(
            _emit(
                task_id,
                {
                    "type": "scenario_done",
                    "scenario_id": scenario_id,
                    "passed": passed,
                    "score": score,
                    "current": current,
                    "total": total,
                },
            )
        )

    try:
        orch = Orchestrator(config)
        result = await orch.run_suite(
            target=body.target,
            suite=body.suite,
            parallel=body.parallel,
            on_progress=on_progress,
        )
        store = RunStore(default_store_path())
        run_id = store.save_suite_result(result)
        task["status"] = "complete"
        task["run_id"] = run_id
        task["score"] = result.decibench_score
        await _emit(
            task_id,
            {
                "type": "complete",
                "run_id": run_id,
                "score": result.decibench_score,
                "passed": result.passed,
                "failed": result.failed,
            },
        )
    except Exception as exc:
        task["status"] = "error"
        task["error"] = str(exc)
        await _emit(task_id, {"type": "error", "message": str(exc)})


async def _emit(task_id: str, event: dict[str, Any]) -> None:
    q = _run_events.get(task_id)
    if q is not None:
        await q.put(event)


def _slug(s: str) -> str:
    import re

    return re.sub(r"[^a-z0-9-]+", "-", s.lower()).strip("-")
