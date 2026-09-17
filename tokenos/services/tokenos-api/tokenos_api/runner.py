"""Executes a compiled plan and emits the seven-phase event stream.

All phase transitions, measurements, and the final proof originate here. The
browser only renders what this module reports.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

from .comparison import contract, test_set_id
from .config import settings
from .modeladapter import model_available
from .pricing import price_source
from .simulator import SIMULATION_ORIGIN
from .storage.runs import Plan, Run
from .storage.ledger import ledger_store
from .storage.uploads import upload_store
from .tokenomics import TokenomicsLedger
from .workflows import get_workflow
from .workflows.base import Operation, RunContext

GENERATIVE_ROUTES = {"efficient_ai", "advanced_ai"}


def _measurement_label(input_source: str) -> str:
    if input_source == "sample":
        return "measured_sample_run"
    if input_source == "connected":
        return "measured_connected_stub"
    return "measured"


async def execute_run(run: Run, plan: Plan) -> None:
    """Drives Plan through Prove, emitting one event per meaningful step."""
    workflow = get_workflow(plan.workflow_id)
    request = plan.request
    started = time.perf_counter()

    # Presentation pacing is tracked separately so it never inflates the
    # measured work time reported in the proof.
    paced_seconds = 0.0

    async def pace(kind: str = "phase") -> None:
        nonlocal paced_seconds
        milliseconds = {
            "phase": settings.phase_pacing_ms,
            "operation": settings.operation_pacing_ms,
            "step": settings.step_pacing_ms
        }.get(kind, 0)
        if milliseconds > 0:
            paced_seconds += milliseconds / 1000
            await asyncio.sleep(milliseconds / 1000)

    uploads_by_role: dict[str, list] = {}
    for role, ids in request.get("uploads", {}).items():
        uploads_by_role[role] = upload_store.many(ids)

    context = RunContext(
        workflow_id=plan.workflow_id,
        request=request,
        uploads_by_role=uploads_by_role,
        artifacts=dict(plan.context),
    )
    operations: list[Operation] = plan.context["_operations"]

    # Both sides of the economic comparison are accumulated as work completes.
    ledger = TokenomicsLedger()
    source_text = "\n".join(
        upload.extracted_text for items in uploads_by_role.values() for upload in items
    )

    run.status = "running"
    run.operations = [operation.public() | {"status": "pending"} for operation in operations]
    run.metrics = {
        "operations_total": len(operations),
        "completed": 0,
        "without_generative_ai": 0,
        "model_calls": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "calculated_model_cost_usd": 0.0,
        "authorized_model_cost_usd": float(request.get("maximum_cost_usd", 1.0)),
        "quality_state": "checking",
        "measurement": _measurement_label(request.get("input_source", "upload")),
    }

    run.emit("run.created", {"workflow_id": plan.workflow_id, "plan_id": plan.plan_id})

    # Wait for the browser to attach before streaming, so no phase is missed.
    await run.wait_for_subscriber(settings.stream_attach_timeout_seconds)

    try:
        # ---------------------------------------------------------- Plan phase
        run.phase = "plan"
        await pace("phase")
        run.emit(
            "phase.started",
            {"phase": "plan", "title": plan.summary.get("title", ""), "description": plan.summary.get("description", "")},
        )
        await pace("phase")
        run.emit(
            "plan.compiled",
            {
                "operation_count": len(operations),
                "input_summary": plan.input_summary,
                "facts": plan.summary.get("facts", []),
                "operations": [operation.public() for operation in operations],
            },
        )

        # ------------------------------------------------------ Optimize phase
        run.phase = "optimize"
        await pace("phase")
        run.emit("phase.started", {"phase": "optimize", "title": "Choosing the best routes"})
        run.emit("optimization.started", {})
        for operation in operations:
            await pace("step")
            run.emit(
                "route.selected",
                {
                    "operation_id": operation.id,
                    "route": operation.route,
                    "reason": operation.reason,
                    "label": operation.label,
                },
            )
        run.emit(
            "optimization.completed",
            {
                "without_generative_ai": sum(
                    1 for operation in operations if operation.route not in GENERATIVE_ROUTES
                ),
                "efficient_ai": sum(1 for operation in operations if operation.route == "efficient_ai"),
                "advanced_ai": sum(1 for operation in operations if operation.route == "advanced_ai"),
                "model_available": model_available(),
            },
        )

        # ------------------------------------------------------- Protect phase
        run.phase = "protect"
        await pace("phase")
        run.emit("phase.started", {"phase": "protect", "title": "Checking enterprise safeguards"})
        run.emit("protection.started", {})
        for check in plan.context.get("_protection_checks", []):
            await pace("step")
            if not check["passed"]:
                run.status = "blocked"
                run.emit("run.blocked", check)
                return
            run.emit("check.passed", check)
        await pace("step")
        run.emit(
            "cost.authorized",
            {"maximum_model_cost_usd": float(request.get("maximum_cost_usd", 1.0))},
        )

        if plan.requires_approval:
            run.status = "waiting"
            run.approval = {
                "action": plan.context.get("_approval_action", "Execute the approved plan"),
                "reason": plan.context.get(
                    "_approval_reason", "Human approval is required before execution."
                ),
                "maximum_cost_usd": float(request.get("maximum_cost_usd", 1.0)),
                "rollback": "No operation has started. Rejecting stops the run safely.",
                "decision": "pending",
            }
            run.emit("approval.required", run.approval)
            await run._approval_gate.wait()
            if run.approval.get("decision") != "approved":
                run.status = "blocked"
                run.emit(
                    "run.blocked",
                    {
                        "check": "Actions",
                        "reason": "The required human approval was rejected.",
                        "operation_label": run.approval["action"],
                        "user_action": "Change the task requirements or approval rule and start a new run.",
                        "prevented": "No operation executed.",
                    },
                )
                return
            run.status = "running"

        run.emit("protection.passed", {})

        # ----------------------------------------------------------- Run phase
        run.phase = "run"
        await pace("phase")
        run.emit("phase.started", {"phase": "run", "title": "Running approved operations"})
        run.emit("run.started", {})

        for index, operation in enumerate(operations):
            if run.stop_requested:
                run.status = "stopped"
                run.emit(
                    "run.stopped",
                    {"reason": "Stopped safely by the operator. No further operations were started."},
                )
                return

            run.operations[index]["status"] = "running"
            run.emit("operation.started", {"operation_id": operation.id, "label": operation.label})
            await pace("operation")
            operation_started = time.perf_counter()

            if operation.handler is None:  # pragma: no cover - defensive
                result = None
            else:
                result = await operation.handler(context)

            duration_ms = int((time.perf_counter() - operation_started) * 1000)
            actual_route = (result.route if result and result.route else operation.route)
            cost = result.cost_usd if result else 0.0

            if result:
                for usage in result.all_model_usages():
                    context.model_calls.append(usage)
                    run.metrics["model_calls"] += 1
                    run.metrics["input_tokens"] += usage.get("input_tokens", 0)
                    run.metrics["output_tokens"] += usage.get("output_tokens", 0)
                    run.emit("model.invoked", usage)

            run.metrics["calculated_model_cost_usd"] = round(
                run.metrics["calculated_model_cost_usd"] + cost, 6
            )
            run.metrics["completed"] += 1
            if actual_route not in GENERATIVE_ROUTES:
                run.metrics["without_generative_ai"] += 1

            # What this operation would have cost had it gone to the advanced model.
            ledger.record(
                operation_id=operation.id,
                label=operation.label,
                route=actual_route,
                source_text=source_text,
                result=(result.detail if result else {}),
            )

            run.operations[index] |= {
                "status": "complete",
                "route": actual_route,
                "reason": (result.reason if result and result.reason else operation.reason),
                "actual_cost_usd": cost,
                "duration_ms": duration_ms,
                "detail": (result.detail if result else {}),
            }

            if result and result.quality:
                run.emit("quality.checked", {"operation_id": operation.id, **result.quality})

            run.emit(
                "operation.completed",
                {
                    "operation_id": operation.id,
                    "route": actual_route,
                    "reason": run.operations[index]["reason"],
                    "actual_cost_usd": cost,
                    "duration_ms": duration_ms,
                    "detail": run.operations[index]["detail"],
                },
            )
            run.emit("run.metrics", dict(run.metrics))

        run.emit("execution.completed", {})

        # -------------------------------------------------------- Verify phase
        run.phase = "verify"
        await pace("phase")
        run.emit("phase.started", {"phase": "verify", "title": "Verifying the completed outcome"})
        run.emit("verification.started", {})
        outcome = workflow.verify(context)
        await pace("phase")
        run.metrics["quality_state"] = "passed" if outcome.quality_passed else "failed"
        run.emit(
            "verification.completed",
            {
                "checks": [check.public() for check in outcome.checks],
                "quality_score": outcome.quality_score,
                "quality_passed": outcome.quality_passed,
                "deadline_met": outcome.deadline_met,
                "facts": outcome.facts,
            },
        )
        if not outcome.quality_passed:
            run.emit("verification.failed", {"reason": "The workflow quality requirement was not met."})
        else:
            run.emit("verification.passed", {})

        # --------------------------------------------------------- Prove phase
        # Measured work time excludes presentation pacing.
        duration_ms = max(int((time.perf_counter() - started - paced_seconds) * 1000), 0)
        run.status = "completed" if outcome.quality_passed else "completed_with_findings"
        proof = build_proof(run, plan, context, outcome, duration_ms, ledger)
        run.proof = proof
        ledger_store.record_proof(run.run_id, plan.workflow_id, proof)
        run.phase = "prove"
        await pace("phase")
        run.emit("phase.started", {"phase": "prove", "title": "Completed"})
        run.emit("run.completed", {"proof": proof})

    except asyncio.CancelledError:  # pragma: no cover - shutdown path
        raise
    except Exception as error:  # noqa: BLE001 - reported to the UI as a run failure
        run.status = "failed"
        run.error = {"message": str(error), "type": type(error).__name__}
        run.emit("run.failed", run.error)


def build_proof(run: Run, plan: Plan, context: RunContext, outcome, duration_ms: int,
                ledger: TokenomicsLedger | None = None) -> dict:
    request = plan.request
    operations = run.operations
    efficient = sum(1 for item in operations if item.get("route") == "efficient_ai")
    advanced = sum(1 for item in operations if item.get("route") == "advanced_ai")
    without_generative = sum(
        1 for item in operations if item.get("route") not in GENERATIVE_ROUTES
    )
    deployments = sorted({call["deployment"] for call in context.model_calls})
    price_configured = all(price_source(name) and price_source(name).get("effective_date") for name in deployments)

    actual_cost = run.metrics["calculated_model_cost_usd"]
    actual_tokens = run.metrics["input_tokens"] + run.metrics["output_tokens"]
    tokenomics = (
        ledger.summary(actual_cost, actual_tokens, outcome.quality_passed) if ledger else None
    )
    if tokenomics is not None:
        tokenomics["routing"] = ledger.routing_story(operations, model_available())
    # A workflow that builds its own comparison keeps it; otherwise the route
    # comparison is the baseline.
    baseline = outcome.baseline or (
        ledger.baseline_table(actual_cost, outcome.quality_passed) if ledger else None
    )

    findings_list = context.artifacts.get("findings", [])
    unresolved = [
        item
        for item in findings_list
        if item.get("resolved_by") == "unresolved"
        or item.get("recommendation") == "needs_interpretation"
    ]
    decision_complete = outcome.quality_passed and not unresolved

    return {
        "run_id": run.run_id,
        "plan_id": plan.plan_id,
        "workflow_id": plan.workflow_id,
        "status": run.status,
        "created_at": run.created_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "input_evidence": request.get("input_source", "upload"),
        # Stated on the proof itself so a downloaded artifact declares its own
        # provenance once separated from the page that produced it.
        "origin": SIMULATION_ORIGIN if settings.simulated else "live",
        "measurement": run.metrics["measurement"],
        "measurement_label": (
            "Simulated demonstration run"
            if settings.simulated
            else "Measured sample run"
            if run.metrics["measurement"] == "measured_sample_run"
            else "Measured run, local connector stub"
            if run.metrics["measurement"] == "measured_connected_stub"
            else "Measured usage, calculated cost"
        ),
        "outcome": {
            "successful": outcome.quality_passed,
            "quality_passed": outcome.quality_passed,
            "quality_score": outcome.quality_score,
            "required_quality_score": float(request.get("required_quality_score", 0.92)),
            "deadline_met": outcome.deadline_met,
            # Deterministic checks passing is not the same as the business decision
            # being finished. An item left for a model or a human keeps this false.
            "decision_complete": decision_complete,
            "unresolved_items": len(unresolved),
            "quality_label": (
                "All checks passed. Decision complete."
                if decision_complete
                else "Deterministic checks passed. Final decision incomplete."
                if outcome.quality_passed
                else "Deterministic checks reported issues."
            ),
            "headline": (
                "Verified review decision. Minimal AI use. Measured cost proof."
                if decision_complete
                else f"Known findings resolved locally. {len(unresolved)} material ambiguity "
                f"requires AI or human review."
                if outcome.quality_passed and unresolved
                else "Completed with findings."
            ),
        },
        "usage": {
            "model_calls": run.metrics["model_calls"],
            "input_tokens": run.metrics["input_tokens"],
            "output_tokens": run.metrics["output_tokens"],
            "duration_ms": duration_ms,
            "deployments": deployments,
            "model_mode": settings.model_mode if model_available() else "local",
        },
        "economics": {
            "calculated_model_cost_usd": run.metrics["calculated_model_cost_usd"],
            "tool_cost_usd": 0.0,
            "total_calculated_cost_usd": run.metrics["calculated_model_cost_usd"],
            "authorized_model_cost_usd": run.metrics["authorized_model_cost_usd"],
            "price_configured": bool(deployments) and price_configured,
            # Every economic number carries the status of its evidence, so a
            # projection can never be mistaken for measured spend.
            "actual_cost_status": (
                "Measured from model response usage"
                if run.metrics["model_calls"]
                else "No model spend — all work completed locally"
            ),
            "comparator_status": "Projection, not measured spend",
            "difference_status": "Projected, not a verified saving",
            "verified_saving_status": "Requires a paired all-AI run with an equal-quality outcome",
            "token_source": (
                "model response usage" if run.metrics["model_calls"] else "no model call was made"
            ),
        },
        "routing": {
            "operations": len(operations),
            "completed_without_generative_ai": without_generative,
            "efficient_ai": efficient,
            "advanced_ai": advanced,
        },
        "verification": [check.public() for check in outcome.checks],
        "facts": outcome.facts,
        "finding": outcome.finding,
        # Findings are server-verified evidence. The browser may render them, but
        # it never derives or changes a decision.
        "findings": context.artifacts.get("findings", []),
        "reviewed_items": context.artifacts.get("reviewed_charges", []),
        "tokenomics": tokenomics,
        "baseline": baseline,
        "inputs": [upload.public() for upload in context.uploads],
        "operations": operations,
        "model_calls": context.model_calls,
        # Recorded so a reviewer can confirm the paired baseline was asked for the
        # same thing under the same constraints, rather than trusting the claim.
        "comparison_contract": contract(test_set_id(context.uploads)),
        # One compact governance record per paid call: which deployment, why a model
        # was allowed at all, what it cost, and how much ceiling was left.
        "why_ai": [
            {
                "route": call.get("route"),
                "deployment": call.get("deployment"),
                "why_ai": call.get("why_ai", "No reason was recorded for this call."),
                "input_tokens": call.get("input_tokens", 0),
                "output_tokens": call.get("output_tokens", 0),
                "calculated_cost_usd": call.get("calculated_cost_usd", 0.0),
                "quality_check": call.get("quality_check"),
                "token_source": call.get("token_source", "model response usage"),
                "ceiling_remaining_usd": round(
                    max(
                        run.metrics["authorized_model_cost_usd"]
                        - run.metrics["calculated_model_cost_usd"],
                        0.0,
                    ),
                    6,
                ),
            }
            for call in context.model_calls
        ],
    }
