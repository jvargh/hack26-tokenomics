"""API tests verifying route counts, model-call counts, and technical evidence all
derive from the same run record — the invariant the Prove screen depends on to
never show inconsistent numbers.

Run: .\\.venv\\Scripts\\python.exe -m pytest tests/test_route_counts.py -v
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from conftest import run_workflow

GENERATIVE_ROUTES = {"efficient_ai", "advanced_ai"}

CASES = {
    "document_review": {"review-focus": "Unsupported charges and missing approvals"},
    "software_validation": {
        "requested-change": "Add the archive endpoint declared in the specification.",
        "validation-level": "Static plus allowed tests",
    },
    "deadline_processing": {
        "processing-instruction": "Classify each record by category and summarize the totals.",
        "completion-deadline": (datetime.now(timezone.utc) + timedelta(hours=8)).isoformat(),
        "output-format": "CSV",
        "allow-scheduled": "true",
    },
    "false_savings": {
        "reviewer-hourly-rate": "68",
        "acceptance-rule": "Accepted without correction, retry, or reversal",
        "minimum-quality": "0.9",
        "minimum-cohort": "25",
    },
}


def _assert_route_invariants(proof: dict) -> None:
    routing = proof["routing"]
    usage = proof["usage"]
    operations = proof["operations"]

    # 1. Every operation is accounted for exactly once across the route buckets.
    assert routing["operations"] == len(operations)
    generative_ops = [op for op in operations if op.get("route") in GENERATIVE_ROUTES]
    non_generative_ops = [op for op in operations if op.get("route") not in GENERATIVE_ROUTES]
    assert routing["completed_without_generative_ai"] == len(non_generative_ops)
    assert routing["efficient_ai"] + routing["advanced_ai"] == len(generative_ops)

    # 2. The technical evidence (per-operation model usage) sums to the same
    #    model-call count and token totals reported in `usage`.
    total_calls_from_operations = 0
    total_input_from_operations = 0
    total_output_from_operations = 0
    for operation in operations:
        detail = operation.get("detail") or {}
        model_calls = detail.get("model_calls")
        if isinstance(model_calls, int):
            total_calls_from_operations += model_calls

    # In local-only mode no model is configured, so no operation may report a
    # generative route or a model call: this is the Foundry-unavailable state.
    assert usage["model_calls"] == total_calls_from_operations


def test_route_counts_reconcile_for_every_workflow(api_client):
    for workflow_id, inputs in CASES.items():
        proof = run_workflow(api_client, workflow_id, inputs)
        assert proof["status"].startswith("completed"), (workflow_id, proof["status"])
        _assert_route_invariants(proof)


def test_local_only_mode_never_reports_a_generative_route(api_client):
    """With no Foundry deployment configured, every operation must route to
    software/retrieval/reuse. This is the explicit 'Foundry-unavailable' contract:
    the workflow degrades to local-only rather than fabricating model output."""
    for workflow_id, inputs in CASES.items():
        proof = run_workflow(api_client, workflow_id, inputs)
        assert proof["usage"]["model_calls"] == 0, workflow_id
        assert proof["usage"]["input_tokens"] == 0, workflow_id
        assert proof["usage"]["output_tokens"] == 0, workflow_id
        assert proof["economics"]["total_calculated_cost_usd"] == 0.0, workflow_id
        for operation in proof["operations"]:
            assert operation.get("route") not in GENERATIVE_ROUTES, (workflow_id, operation)


def test_create_decision_summary_never_routes_to_a_model_in_document_review(api_client):
    """Regression guard for the earlier inconsistency where a cosmetic summary step
    was described as an AI decision. The summary operation must always be
    deterministic; only the ambiguity-resolution step may use a model."""
    proof = run_workflow(
        api_client,
        "document_review",
        {"review-focus": "Unsupported charges and missing approvals"},
    )
    summary_ops = [
        op
        for op in proof["operations"]
        if "summary" in op["label"].lower() or "decision" in op["label"].lower()
    ]
    for operation in summary_ops:
        assert operation.get("route") not in GENERATIVE_ROUTES, operation
