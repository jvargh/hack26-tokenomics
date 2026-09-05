from __future__ import annotations

import asyncio
import json
import zipfile

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from ..config import settings
from . import engine, imports
from .fixtures import prompt_example_catalog, sample_catalog
from .schemas import AuthorizeRequest, OptimizeRequest
from .store import store


router = APIRouter(prefix="/api")


@router.get("/optimization/samples")
async def samples() -> dict:
    return {"samples": sample_catalog()}


@router.get("/optimization/prompt-examples")
async def prompt_examples() -> dict:
    return {"examples": prompt_example_catalog()}


@router.post("/optimization/context")
async def context_uploads(files: list[UploadFile] = File(...)) -> dict:
    if not files or len(files) > settings.max_files_per_run:
        raise HTTPException(422, "The context upload exceeds the permitted file count.")
    prepared = []
    total = 0
    for upload in files:
        content = await upload.read(settings.max_file_bytes + 1)
        total += len(content)
        if total > settings.max_total_bytes:
            raise HTTPException(413, "Combined context uploads exceed the size limit.")
        try:
            metadata = imports.context_file_metadata(upload.filename or "context", content)
        except (ValueError, UnicodeDecodeError, zipfile.BadZipFile, RuntimeError, OSError, KeyError, TypeError) as error:
            raise HTTPException(422, str(error)) from error
        prepared.append((metadata, content))
    return {"files": [store.put_file(metadata, content) for metadata, content in prepared]}


@router.get("/optimization/applications")
async def applications() -> dict:
    return {"applications": imports.applications(),
            "notice": "A registered application and approved scope is not automatic Azure subscription access. Credentials stay on the server."}


@router.get("/optimization/import-template")
async def import_template() -> dict:
    return {
        "formatVersion": "normalized_v1",
        "telemetry": {"records": [{"requestId": "req-1", "providerRequestId": "provider-response-id",
                                   "timestamp": "2026-09-01T12:00:00Z", "deployment": "registered-deployment",
                                   "inputTokens": 1200, "outputTokens": 40, "cachedInputTokens": 1000,
                                   "reasoningTokens": 0, "latencyMs": 500, "outcomeStatus": "accepted",
                                   "retryCount": 0, "application": "support", "owner": "team"}]},
        "representativeRequest": {"id": "request-1", "taskType": "lookup", "input": "return window",
                                  "context": [{"id": "returns#window", "text": "The return window is 30 days.",
                                               "key": "return window", "output": {"decision": "30 days", "citations": ["returns#window"]}}],
                                  "expectedOutput": {"decision": "30 days", "citations": ["returns#window"]}},
        "instructions": ["Provide 3 to 20 representative requests with independently specified expectedOutput.",
                         "Native TokenOS proof.modelUsage, model_usage, and model_calls arrays are also accepted.",
                         "CSV context and expectedOutput cells contain JSON. JSONL contains one object per line.",
                         "Prices come only from the administrator's pinned deployment price table.",
                         "TXT/Markdown inputs can be analyzed for shape, but must supply expectedOutput in JSON before Protect.",
                         "The examples are format documentation, not measured telemetry."],
    }


@router.post("/optimization/uploads")
async def uploads(role: str = Form(...), files: list[UploadFile] = File(...)) -> dict:
    if not files or len(files) > settings.max_files_per_run:
        raise HTTPException(422, "The upload exceeds the permitted file count.")
    prepared = []
    total = 0
    for upload in files:
        content = await upload.read(settings.max_file_bytes + 1)
        total += len(content)
        if total > settings.max_total_bytes:
            raise HTTPException(413, "Combined uploads exceed the size limit.")
        try:
            parsed = imports.parse_export(upload.filename or "", content, role)
            if role == "telemetry":
                imports.normalize_telemetry(parsed)
        except (ValueError, UnicodeDecodeError, zipfile.BadZipFile, RuntimeError, OSError, KeyError, TypeError) as error:
            raise HTTPException(422, str(error)) from error
        metadata = imports.file_metadata(upload.filename or "input", content, role)
        metadata["recordCount"] = len(parsed)
        prepared.append((metadata, content))
    return {"files": [store.put_file(metadata, content) for metadata, content in prepared]}


@router.post("/runs/{run_id}/analyze")
async def analyze(run_id: str) -> dict:
    return engine.analyze(run_id)


@router.post("/runs/{run_id}/optimize")
async def optimize(run_id: str, payload: OptimizeRequest) -> dict:
    return engine.optimize(run_id)


@router.post("/runs/{run_id}/authorize")
async def authorize(run_id: str, payload: AuthorizeRequest) -> dict:
    return engine.authorize(run_id, payload)


@router.post("/runs/{run_id}/refresh-safeguards")
async def refresh_safeguards(run_id: str) -> dict:
    return engine.refresh_safeguards(run_id)


@router.post("/runs/{run_id}/execute")
async def execute(run_id: str) -> dict:
    return engine.execute(run_id)


@router.get("/optimization/reports")
async def reports(proofType: str | None = None, application: str | None = None, optimizationTarget: str | None = None, limit: int = 200) -> dict:
    if proofType is not None and proofType not in {"measured", "projected", "sample"}:
        raise HTTPException(422, "proofType must be measured, projected, or sample.")
    return engine.reports(proofType, application, limit, optimizationTarget)


def events(run_id: str, request: Request) -> StreamingResponse:
    store.require(run_id)
    cursor = request.headers.get("last-event-id") or request.query_params.get("last_event_id") or "0"
    if not cursor.isdigit():
        raise HTTPException(422, "Last-Event-ID must be a nonnegative event sequence.")

    async def stream():
        after = int(cursor)
        quiet = 0
        while not await request.is_disconnected():
            replay = store.events(run_id, after)
            for event in replay:
                after = event["sequence"]
                yield f"id: {after}\nevent: {event['type']}\ndata: {json.dumps(event)}\n\n"
            run = store.require(run_id)
            active = run["status"] == "running" or run.get("baseline", {}).get("status") == "running"
            if not active:
                # Re-read after state to avoid dropping the terminal event if the
                # worker committed it between the first event read and state read.
                for event in store.events(run_id, after):
                    yield f"id: {event['sequence']}\nevent: {event['type']}\ndata: {json.dumps(event)}\n\n"
                return
            quiet = 0 if replay else quiet + 1
            if quiet >= 150:
                yield ": keep-alive\n\n"
                quiet = 0
            await asyncio.sleep(0.1)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
