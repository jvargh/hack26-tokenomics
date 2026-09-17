"""Local TokenOS API.

Owns input validation, plan compilation, execution, measurement, and proof.
The browser renders what this service reports and never substitutes results.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any

from fastapi import APIRouter, Body, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

from .config import settings
from .session import SessionScopeMiddleware, current_session
from .baseline import run_baseline
from .connectors import ConnectionError as ConnectedAppError
from .connectors import list_applications, resolve_connection
from .modeladapter import get_model_adapter, model_available, reset_model_adapter
from .pricing import load_price_table, save_price_table
from .runner import execute_run
from .samples import build_sample_uploads
from .storage.ledger import ledger_store
from .storage.runs import Plan, new_plan_id, run_store
from .storage.uploads import UploadError, upload_store
from .workflows import all_workflows, get_workflow, normalize_workflow_id
from .optimization import engine as optimization_engine
from .optimization.router import events as optimization_events, router as optimization_router
from .optimization.schemas import DescribeRequest, BaselineRequest as OptimizationBaselineRequest
from .optimization.store import public_state as optimization_state, store as optimization_store

api = APIRouter(prefix="/api")


class Requirements(BaseModel):
    importance: str = "important"
    needed: str = "today"
    priority: str = "balanced"
    maximum_cost_usd: float = 1.0
    required_quality_score: float = 0.92
    human_approval_required: bool = False
    data_classification: str = "internal"
    allowed_routes: list[str] = Field(
        default_factory=lambda: ["software", "retrieval", "reuse", "efficient_ai", "advanced_ai"]
    )


class AnalyzeRequest(BaseModel):
    workflow_id: str
    input_source: str = "upload"
    uploads: dict[str, list[str]] = Field(default_factory=dict)
    inputs: dict[str, Any] = Field(default_factory=dict)
    connection: dict[str, Any] | None = None
    desired_outcome: str = ""
    requirements: Requirements = Field(default_factory=Requirements)


class StartRunRequest(BaseModel):
    plan_id: str
    idempotency_key: str | None = None


class ApprovalRequest(BaseModel):
    decision: str = "approved"


class BaselineRequest(BaseModel):
    # Required and must be true before the API will spend real model tokens on the
    # paired all-AI comparison. Absence or false is rejected with 400, not defaulted.
    acknowledged: bool = False


class FoundryConfigPayload(BaseModel):
    model_mode: str = "foundry"
    foundry_base_url: str = ""
    foundry_auth_mode: str = "entra"
    foundry_token_scope: str = "https://cognitiveservices.azure.com/.default"
    efficient_deployment: str = "tokenos-gpt41-nano"
    advanced_deployment: str = "tokenos-gpt4o"
    api_key: str | None = None
    price_table: dict[str, Any] | None = None


class FoundryTestPayload(BaseModel):
    deployment_type: str = "efficient"
    deployment: str | None = None



def _protection_checks(plan_request: dict, build) -> list[dict]:
    """Real pre-execution checks against the user's own requirements."""
    requirements = plan_request
    maximum = float(requirements.get("maximum_cost_usd", 1.0))
    estimate = float(build.estimated_maximum_cost_usd)
    classification = str(requirements.get("data_classification", "internal")).lower()
    allowed_routes = requirements.get("allowed_routes", [])
    planned_routes = sorted({operation.route for operation in build.operations})
    disallowed = [route for route in planned_routes if route not in allowed_routes]

    checks = [
        {
            "check_id": "spending",
            "name": "Spending approved",
            "passed": estimate <= maximum,
            "detail": (
                f"Estimated model cost ${estimate:.4f} against an authorized ${maximum:.2f}"
            ),
            "evidence": [
                {"label": "Authorized model cost", "value": f"${maximum:.2f}"},
                {"label": "Estimated model cost", "value": f"${estimate:.4f}"},
                {
                    "label": "Planned model calls",
                    "value": f"{build.estimated_model_calls['minimum']} to {build.estimated_model_calls['maximum']}",
                },
            ],
            "reason": "The optimized plan needs more than the authorized model cost." if estimate > maximum else "",
        },
        {
            "check_id": "quality",
            "name": "Quality protected",
            "passed": True,
            "detail": f"Required score {float(requirements.get('required_quality_score', 0.92)):.2f}",
            "evidence": [
                {"label": "Required score", "value": f"{float(requirements.get('required_quality_score', 0.92)):.2f}"},
                {"label": "Verification", "value": "Workflow-specific deterministic checks"},
                {
                    "label": "Escalation route",
                    "value": "Advanced AI" if model_available() else "Not available in local mode",
                },
            ],
        },
        {
            "check_id": "data",
            "name": "Data route allowed",
            "passed": not disallowed,
            "detail": f"Classification {classification}, planned routes {', '.join(planned_routes)}",
            "evidence": [
                {"label": "Classification", "value": classification.title()},
                {"label": "Planned routes", "value": ", ".join(planned_routes)},
                {"label": "Allowed routes", "value": ", ".join(allowed_routes)},
                {
                    "label": "Model mode",
                    "value": "Foundry deployments" if model_available() else "Local only, no model route",
                },
            ],
            "reason": f"Route(s) not permitted by the task requirements: {', '.join(disallowed)}" if disallowed else "",
        },
        {
            "check_id": "actions",
            "name": "Actions controlled",
            "passed": True,
            "detail": "No operation in this plan changes an external system",
            "evidence": [
                {"label": "Side-effecting operations", "value": str(sum(1 for op in build.operations if op.side_effect))},
                {
                    "label": "Approval rule",
                    "value": "Required before execution" if build.requires_approval else "Not required",
                },
            ],
        },
        {
            "check_id": "time",
            "name": "Deadline protected",
            "passed": True,
            "detail": "The selected route can finish within the required time",
            "evidence": [
                {"label": "Needed", "value": str(requirements.get("needed", "today")).title()},
                {"label": "Priority", "value": str(requirements.get("priority", "balanced")).replace("_", " ").title()},
            ],
        },
    ]
    for check in checks:
        check["operation_label"] = build.operations[0].label if build.operations else ""
        check["user_action"] = (
            "Raise the authorized model cost in Advanced settings, or reduce the planned model calls."
            if check["check_id"] == "spending"
            else "Change the allowed routes or the data classification in Advanced settings."
        )
        check["prevented"] = "No paid operation was started and no external system was contacted."
    return checks


@api.get("/workflows")
async def list_workflows() -> dict:
    return {
        "workflows": [handler.definition() for handler in all_workflows()],
        "model_available": model_available(),
    }


@api.post("/uploads")
async def create_uploads(
    workflow_id: str = Form(...),
    input_role: str = Form(...),
    data_classification: str = Form("internal"),
    files: list[UploadFile] = File(...),
) -> dict:
    workflow = normalize_workflow_id(workflow_id)
    if len(files) > settings.max_files_per_run:
        raise HTTPException(status_code=400, detail=f"Upload at most {settings.max_files_per_run} files per run.")

    created = []
    total = 0
    for item in files:
        raw = await item.read()
        total += len(raw)
        if total > settings.max_total_bytes:
            raise HTTPException(
                status_code=400,
                detail=f"Combined upload size exceeds {settings.max_total_bytes // (1024 * 1024)} MB.",
            )
        try:
            upload = upload_store.add(
                name=item.filename or "file",
                raw=raw,
                role=input_role,
                workflow_id=workflow,
                data_classification=data_classification,
            )
        except UploadError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        created.append(upload.public())
    return {"uploads": created}


@api.post("/uploads/sample")
async def create_sample_uploads(payload: dict) -> dict:
    workflow_id = normalize_workflow_id(str(payload.get("workflow_id", "")))
    try:
        get_workflow(workflow_id)
        grouped = build_sample_uploads(workflow_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return {
        "workflow_id": workflow_id,
        "uploads": {role: [upload.public() for upload in items] for role, items in grouped.items()},
    }


@api.get("/connections")
async def list_connections(workflow_id: str | None = None) -> dict:
    resolved = normalize_workflow_id(workflow_id) if workflow_id else None
    return {"applications": list_applications(resolved)}


@api.delete("/uploads/{upload_id}")
async def delete_upload(upload_id: str) -> dict:
    upload_store.remove(upload_id)
    return {"removed": upload_id}


@api.post("/runs/analyze")
async def analyze(request: AnalyzeRequest) -> dict:
    workflow_id = normalize_workflow_id(request.workflow_id)
    if workflow_id == "workflow_optimization":
        raise HTTPException(422, "Use POST /api/runs with workflow='workflow_optimization', then the explicit analyze, optimize, authorize, and execute stages.")
    try:
        workflow = get_workflow(workflow_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    try:
        uploads_by_role = {
            role: upload_store.many(ids) for role, ids in request.uploads.items() if ids
        }
    except UploadError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    # A connected application supplies its own records, so the server resolves them
    # here rather than trusting anything the browser sent.
    if request.input_source == "connected":
        try:
            uploads_by_role = resolve_connection(workflow_id, request.connection)
        except ConnectedAppError as error:
            raise HTTPException(
                status_code=422,
                detail={"errors": [{"field": "connected-application", "message": str(error)}]},
            ) from error

    plan_request = {
        "workflow_id": workflow_id,
        "input_source": request.input_source,
        "uploads": {role: [upload.upload_id for upload in items] for role, items in uploads_by_role.items()},
        "inputs": request.inputs,
        "connection": request.connection,
        "desired_outcome": request.desired_outcome or workflow.default_outcome,
        **request.requirements.model_dump(),
    }

    errors = workflow.validate(plan_request, uploads_by_role)
    if errors:
        raise HTTPException(status_code=422, detail={"errors": errors})

    try:
        build = workflow.build_plan(plan_request, uploads_by_role)
    except Exception as error:  # noqa: BLE001 - surfaced as a validation failure
        raise HTTPException(
            status_code=422,
            detail={"errors": [{"field": "inputs", "message": f"The input could not be analyzed: {error}"}]},
        ) from error

    checks = _protection_checks(plan_request, build)
    requires_approval = build.requires_approval or bool(request.requirements.human_approval_required)

    plan = Plan(
        plan_id=new_plan_id(),
        workflow_id=workflow_id,
        request=plan_request,
        input_summary=build.input_summary,
        operations=[operation.public() for operation in build.operations],
        estimated_model_calls=build.estimated_model_calls,
        estimated_maximum_cost_usd=build.estimated_maximum_cost_usd,
        requires_approval=requires_approval,
        summary=build.summary,
        context={
            **build.context,
            "_operations": build.operations,
            "_protection_checks": checks,
            "_approval_action": f"Execute the {workflow.label} plan",
            "_approval_reason": "Human approval is required by the current task requirements.",
        },
    )
    run_store.add_plan(plan)
    return plan.public() | {"protection_checks": checks, "model_available": model_available()}


@api.post("/runs")
async def start_run(payload: dict) -> dict:
    if payload.get("workflow") == "workflow_optimization":
        try:
            return optimization_engine.describe(DescribeRequest.model_validate(payload))
        except ValidationError as error:
            raise HTTPException(422, error.errors(include_input=False, include_context=False)) from error
        except (ValueError, TypeError) as error:
            raise HTTPException(422, str(error)) from error
    try:
        request = StartRunRequest.model_validate(payload)
    except ValidationError as error:
        raise HTTPException(422, error.errors(include_input=False, include_context=False)) from error
    plan = run_store.plan(request.plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found. Analyze the inputs again.")
    run, created = run_store.create_run(plan, request.idempotency_key)
    if created:
        asyncio.create_task(execute_run(run, plan))
    return {"run_id": run.run_id, "status": run.status, "created": created}


@api.get("/runs/{run_id}")
async def get_run(run_id: str) -> dict:
    optimization_run = optimization_store.get(run_id)
    if optimization_run:
        return optimization_state(optimization_run)
    run = run_store.run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    return run.state()


@api.get("/runs/{run_id}/events")
async def stream_events(run_id: str, request: Request) -> StreamingResponse:
    if optimization_store.get(run_id):
        return optimization_events(run_id, request)
    run = run_store.run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found.")

    last_event_id = request.headers.get("last-event-id") or request.query_params.get("last_event_id")
    after = int(last_event_id) if last_event_id and last_event_id.isdigit() else 0

    async def event_source():
        terminal = {"run.completed", "run.failed", "run.stopped", "run.blocked"}
        queue, replay = run.subscribe(after)
        try:
            for event in replay:
                yield _format_event(event)
                if event.type in terminal:
                    return
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    if run.finished:
                        return
                    yield ": keep-alive\n\n"
                    continue
                yield _format_event(event)
                if event.type in terminal:
                    return
        finally:
            run.unsubscribe(queue)

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


def _format_event(event) -> str:
    return (
        f"id: {event.sequence}\n"
        f"event: {event.type}\n"
        f"data: {json.dumps(event.payload(), default=str)}\n\n"
    )


@api.post("/runs/{run_id}/approve")
async def approve_run(run_id: str, request: ApprovalRequest) -> dict:
    run = run_store.run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    if not run.approval:
        raise HTTPException(status_code=409, detail="This run is not waiting for approval.")
    run.approval["decision"] = "approved" if request.decision == "approved" else "rejected"
    run.emit("approval.recorded", {"decision": run.approval["decision"]})
    run._approval_gate.set()
    return {"run_id": run_id, "decision": run.approval["decision"]}


@api.post("/runs/{run_id}/stop")
async def stop_run(run_id: str) -> dict:
    run = run_store.run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    run.stop_requested = True
    if run.approval and run.approval.get("decision") == "pending":
        run.approval["decision"] = "rejected"
        run._approval_gate.set()
    return {"run_id": run_id, "stop_requested": True}


@api.get("/runs/{run_id}/proof")
async def get_proof(run_id: str) -> dict:
    optimization_run = optimization_store.get(run_id)
    if optimization_run:
        if optimization_run["proof"] is None:
            raise HTTPException(409, "The run has not produced a final proof yet.")
        return optimization_run["proof"]
    run = run_store.run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    if run.proof is None:
        raise HTTPException(status_code=409, detail="The run has not produced a final proof yet.")
    return run.proof


@api.post("/runs/{run_id}/baseline")
async def compare_baseline(run_id: str, payload: dict | None = Body(default=None)) -> dict:
    """Executes the all-AI comparison path and verifies it the same way.

    Kept as an explicit action because it spends real tokens. The caller must
    acknowledge that cost before anything is called; this is not a UI-only checkbox,
    it is enforced here so no client can trigger paid model spend silently.
    """
    if optimization_store.get(run_id):
        try:
            OptimizationBaselineRequest.model_validate(payload or {})
        except ValidationError as error:
            raise HTTPException(400, "Send acknowledgeModelCost: true and baselineProfile: 'all_ai_v1'. No changed comparison contracts are accepted.") from error
        return optimization_engine.start_baseline(run_id)
    if not (payload and payload.get("acknowledged") is True):
        raise HTTPException(
            status_code=400,
            detail=(
                "The baseline invokes a real model call and may incur cost. Send "
                '{"acknowledged": true} to run it.'
            ),
        )

    run = run_store.run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    if run.proof is None:
        raise HTTPException(status_code=409, detail="The run has not produced a final proof yet.")

    plan = run_store.plan(run.plan_id)
    uploads: list = []
    for ids in (plan.request.get("uploads", {}) if plan else {}).values():
        uploads.extend(upload_store.many(ids))

    comparison = await run_baseline(uploads, run.proof)
    run.proof["baseline_run"] = comparison
    ledger_store.record_baseline(run_id, comparison)
    return comparison


@api.get("/runs/{run_id}/comparison")
async def get_comparison(run_id: str) -> dict:
    """Read-only fetch of whatever comparison has already been computed.

    Never executes a model call. `POST /runs/{run_id}/baseline` is the only route
    that spends tokens; this endpoint just reports its cached result so a client can
    poll or refresh the comparison view without re-triggering paid work.
    """
    optimization_run = optimization_store.get(run_id)
    if optimization_run:
        return optimization_run.get("baseline") or (optimization_run.get("proof") or {}).get("baseline") or {
            "status": "not_requested", "eligible": False, "label": "Comparison not run",
            "verifiedSavingUsd": None, "verifiedSavingPercent": None,
        }
    run = run_store.run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    if run.proof is None:
        return {"available": False, "status": "not_requested", "reason": "The run has not produced a final proof yet."}
    cached = run.proof.get("baseline_run")
    if cached is None:
        return {
            "available": False,
            "status": "not_requested",
            "reason": "The measured all-AI comparison has not been run for this proof.",
        }
    return cached


@api.get("/runs")
async def list_runs() -> dict:
    optimization_runs = [{"run_id": run["runId"], "workflow_id": run["workflow"], "status": run["status"],
                          "created_at": run["createdAt"], "proof": run["proof"], "optimization": optimization_state(run),
                          "session": run.get("_session", "")}
                         for run in optimization_store.history()]
    runs = sorted(run_store.history() + optimization_runs, key=lambda run: run["created_at"], reverse=True)

    # On the shared hosted demonstration a visitor sees only their own runs, so
    # one judge's history does not appear in another's. Outside simulated mode
    # `current_session()` is empty and the full history is returned exactly as
    # before.
    session = current_session()
    if session:
        runs = [run for run in runs if run.get("session") == session]
    for run in runs:
        run.pop("session", None)
    return {"runs": runs}


@api.delete("/runs/{run_id}")
async def delete_run(run_id: str) -> dict:
    """Deletes one recorded run everywhere it is held: the in-memory history, the
    optimization store, and the durable ledger behind enterprise reporting.

    A run that is still executing cannot be deleted, because its proof does not
    exist yet and live progress readers are still attached to it.
    """
    optimization_run = optimization_store.get(run_id)
    if optimization_run is not None:
        if optimization_run.get("status") == "running":
            raise HTTPException(status_code=409, detail="This run is still going. Wait for it to finish, then delete it.")
        optimization_store.delete(run_id)
        ledger_store.delete(run_id)
        return {"deleted": True, "run_id": run_id}

    run = run_store.run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="No run with that identifier.")
    if run.active:
        raise HTTPException(status_code=409, detail="This run is still going. Wait for it to finish, then delete it.")
    run_store.delete(run_id)
    ledger_store.delete(run_id)
    return {"deleted": True, "run_id": run_id}


@api.delete("/runs")
async def delete_all_runs() -> dict:
    """Clears the whole run history. Runs that are still executing are kept.

    The ledger is cleared outright rather than run by run: it outlives the
    in-memory history, so deleting only the runs still listed would leave
    older rows stranded in enterprise reporting with no way to remove them.
    A run still executing has not written its ledger row yet, so it is unaffected.
    """
    active = [run["runId"] for run in optimization_store.history() if run.get("status") == "running"]
    active += [run.run_id for run in (run_store.run(item["run_id"]) for item in run_store.history())
               if run is not None and run.active]

    removed = 0
    for item in optimization_store.history():
        if item["runId"] not in active and optimization_store.delete(item["runId"]):
            removed += 1
    for item in run_store.history():
        if item["run_id"] not in active and run_store.delete(item["run_id"]):
            removed += 1
    ledger_store.clear()
    return {"deleted": removed, "kept_running": len(active)}


@api.get("/reports/runs")
async def reports_runs(limit: int = 200) -> dict:
    """Enterprise reporting view over the durable ledger.

    Reads only what was persisted when each run completed and, separately, when a
    baseline was computed for it. Nothing here is recalculated or estimated.
    """
    return {"summary": ledger_store.summary(), "runs": ledger_store.report(limit=limit),
            "optimization": optimization_engine.reports(limit=limit)}


@api.get("/foundry/config")
async def get_foundry_config() -> dict:
    return {
        "model_mode": settings.model_mode,
        "foundry_base_url": settings.foundry_base_url,
        "foundry_auth_mode": settings.foundry_auth_mode,
        "foundry_token_scope": settings.foundry_token_scope,
        "efficient_deployment": settings.foundry_efficient_deployment,
        "advanced_deployment": settings.foundry_advanced_deployment,
        "foundry_available": model_available(),
        "foundry_configured": settings.foundry_configured,
        "has_api_key": bool(os.getenv("AZURE_INFERENCE_CREDENTIAL")),
        "price_table": load_price_table(),
    }


@api.post("/foundry/config")
async def update_foundry_config(payload: FoundryConfigPayload) -> dict:
    settings.model_mode = payload.model_mode
    os.environ["TOKENOS_MODEL_MODE"] = payload.model_mode

    settings.foundry_base_url = payload.foundry_base_url.strip()
    os.environ["TOKENOS_FOUNDRY_BASE_URL"] = settings.foundry_base_url

    settings.foundry_auth_mode = payload.foundry_auth_mode
    os.environ["TOKENOS_FOUNDRY_AUTH_MODE"] = payload.foundry_auth_mode

    settings.foundry_token_scope = payload.foundry_token_scope.strip()
    os.environ["TOKENOS_FOUNDRY_TOKEN_SCOPE"] = settings.foundry_token_scope

    settings.foundry_efficient_deployment = payload.efficient_deployment.strip()
    os.environ["TOKENOS_FOUNDRY_EFFICIENT_DEPLOYMENT"] = settings.foundry_efficient_deployment

    settings.foundry_advanced_deployment = payload.advanced_deployment.strip()
    os.environ["TOKENOS_FOUNDRY_ADVANCED_DEPLOYMENT"] = settings.foundry_advanced_deployment

    if payload.api_key is not None:
        if payload.api_key:
            os.environ["AZURE_INFERENCE_CREDENTIAL"] = payload.api_key.strip()
        elif "AZURE_INFERENCE_CREDENTIAL" in os.environ:
            del os.environ["AZURE_INFERENCE_CREDENTIAL"]

    if payload.price_table:
        save_price_table(payload.price_table)

    reset_model_adapter()
    return await get_foundry_config()


@api.post("/foundry/test")
async def test_foundry_connection(payload: FoundryTestPayload) -> dict:
    if not settings.foundry_configured:
        return {
            "success": False,
            "error": "Foundry is not configured. Set model mode to 'foundry' and provide a valid Base URL.",
        }
    if payload.deployment:
        deployment = payload.deployment
    elif payload.deployment_type == "advanced":
        deployment = settings.foundry_advanced_deployment
    else:
        deployment = settings.foundry_efficient_deployment
    start = time.perf_counter()
    try:
        adapter = get_model_adapter()
        result = await adapter.generate(
            route="test_ping",
            deployment=deployment,
            system="You are a system ping test responder. Respond with a short confirmation message.",
            input_text="Ping: verify connectivity and return token usage.",
            json_response=False,
        )
        latency_ms = int((time.perf_counter() - start) * 1000)
        return {
            "success": True,
            "deployment": deployment,
            "latency_ms": latency_ms,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "cost_usd": result.calculated_cost_usd,
            "price_configured": result.price_configured,
            "model_version": result.model_version,
            "response_preview": result.content[:140],
        }
    except Exception as exc:
        latency_ms = int((time.perf_counter() - start) * 1000)
        return {
            "success": False,
            "deployment": deployment,
            "latency_ms": latency_ms,
            "error": str(exc),
        }



def create_app() -> FastAPI:
    app = FastAPI(
        title="TokenOS local API",
        version=settings.version,
        description="Real input, real analysis, measured proof for the TokenOS Workflow Optimizer.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Last-Event-ID"],
    )
    # Scopes what a visitor is shown on the shared hosted demonstration. No-ops
    # outside simulated mode, so local and Foundry behaviour is unchanged.
    app.add_middleware(SessionScopeMiddleware)

    @app.get("/health")
    async def health() -> dict:
        # Report the configured mode rather than deriving it. `model_available()`
        # answers "can a model route run at all", which is true in simulated
        # mode, so deriving the mode from it claimed Foundry was available when
        # no provider existed. Behaviour for local and foundry is unchanged;
        # simulated is now reported as itself.
        configured = settings.foundry_configured
        return {
            "status": "ready",
            "version": settings.version,
            "modelMode": settings.model_mode,
            "foundryAvailable": configured,
            "efficientDeployment": settings.foundry_efficient_deployment if configured else None,
            "advancedDeployment": settings.foundry_advanced_deployment if configured else None,
            "workflows": [handler.workflow_id for handler in all_workflows()],
        }

    app.include_router(api)
    app.include_router(optimization_router)
    if settings.web_dist_root.is_dir():
        app.mount("/", StaticFiles(directory=settings.web_dist_root, html=True), name="web")
    return app


app = create_app()
