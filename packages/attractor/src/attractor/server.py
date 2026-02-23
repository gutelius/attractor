"""HTTP server for pipeline management."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from attractor.engine import EngineConfig, PipelineEngine
from attractor.parser import parse_dot
from attractor.transforms import VariableExpansionTransform, StylesheetTransform
from attractor.validator import validate_or_raise, ValidationError
from attractor.interviewer import (
    Answer,
    AnswerValue,
    CallbackInterviewer,
    Question,
)

app = FastAPI(title="Attractor Pipeline Server")

# In-memory pipeline store
_pipelines: dict[str, dict[str, Any]] = {}


class PipelineSubmission(BaseModel):
    dot_source: str
    goal: str = ""
    log_dir: str = ""


class AnswerSubmission(BaseModel):
    value: str


@app.post("/pipelines")
async def submit_pipeline(submission: PipelineSubmission):
    """Submit a DOT source and start execution."""
    pipeline_id = str(uuid.uuid4())[:8]

    try:
        graph = parse_dot(submission.dot_source)
        graph = VariableExpansionTransform().apply(graph)
        graph = StylesheetTransform().apply(graph)
        if submission.goal:
            graph.goal = submission.goal
        validate_or_raise(graph)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Parse error: {e}")

    # Question queue for human-in-the-loop
    question_queue: asyncio.Queue[tuple[Question, asyncio.Future]] = asyncio.Queue()

    async def question_callback(question: Question) -> Answer:
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        await question_queue.put((question, future))
        return await future

    interviewer = CallbackInterviewer(lambda q: Answer(value=AnswerValue.SKIPPED))
    logs_root = submission.log_dir or f"/tmp/attractor-server/{pipeline_id}"
    config = EngineConfig(logs_root=logs_root, interviewer=interviewer)
    engine = PipelineEngine(config)

    _pipelines[pipeline_id] = {
        "id": pipeline_id,
        "status": "running",
        "graph": graph,
        "engine": engine,
        "question_queue": question_queue,
        "events": engine._events,
        "outcome": None,
        "start_time": time.time(),
    }

    # Run in background
    async def run_pipeline():
        try:
            outcome = await engine.run(graph)
            _pipelines[pipeline_id]["outcome"] = outcome
            _pipelines[pipeline_id]["status"] = "completed" if outcome.is_success else "failed"
        except Exception as e:
            _pipelines[pipeline_id]["status"] = "error"
            _pipelines[pipeline_id]["error"] = str(e)

    asyncio.create_task(run_pipeline())

    return {"id": pipeline_id, "status": "running"}


@app.get("/pipelines/{pipeline_id}")
async def get_pipeline(pipeline_id: str):
    """Get pipeline status."""
    p = _pipelines.get(pipeline_id)
    if not p:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    result = {
        "id": p["id"],
        "status": p["status"],
        "event_count": len(p["events"]),
    }
    if p["outcome"]:
        result["outcome"] = p["outcome"].status.value
        result["notes"] = p["outcome"].notes
    return result


@app.get("/pipelines/{pipeline_id}/events")
async def get_events_sse(pipeline_id: str):
    """SSE stream of pipeline events."""
    p = _pipelines.get(pipeline_id)
    if not p:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    async def event_stream():
        sent = 0
        while True:
            events = p["events"]
            while sent < len(events):
                event = events[sent]
                data = json.dumps({"kind": event.kind, "node_id": event.node_id, "data": event.data})
                yield f"data: {data}\n\n"
                sent += 1
            if p["status"] in ("completed", "failed", "error"):
                yield f"data: {json.dumps({'kind': 'done', 'status': p['status']})}\n\n"
                break
            await asyncio.sleep(0.1)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/pipelines/{pipeline_id}/cancel")
async def cancel_pipeline(pipeline_id: str):
    """Cancel a running pipeline."""
    p = _pipelines.get(pipeline_id)
    if not p:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    p["status"] = "cancelled"
    return {"id": pipeline_id, "status": "cancelled"}


@app.get("/pipelines/{pipeline_id}/context")
async def get_context(pipeline_id: str):
    """Get current pipeline context."""
    p = _pipelines.get(pipeline_id)
    if not p:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    engine = p["engine"]
    # Return last checkpoint context if available
    return {"pipeline_id": pipeline_id, "event_count": len(p["events"])}


@app.get("/pipelines/{pipeline_id}/graph")
async def get_graph(pipeline_id: str):
    """Get pipeline graph info."""
    p = _pipelines.get(pipeline_id)
    if not p:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    graph = p["graph"]
    return {
        "name": graph.name,
        "goal": graph.goal,
        "nodes": list(graph.nodes.keys()),
        "edges": [{"source": e.source, "target": e.target, "label": e.label} for e in graph.edges],
    }
