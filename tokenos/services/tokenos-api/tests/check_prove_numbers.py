"""Checks the Prove screen invariants against a real governed run record.

Run with:  .venv\\Scripts\\python.exe tests\\check_prove_numbers.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from tokenos_api.app import app  # noqa: E402


async def main() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=120) as client:
        sample = await client.post("/api/uploads/sample", json={"workflow_id": "document_review"})
        sample.raise_for_status()
        uploads = {
            role: [item["upload_id"] for item in items]
            for role, items in sample.json()["uploads"].items()
        }

        analyze = await client.post(
            "/api/runs/analyze",
            json={
                "workflow_id": "document_review",
                "input_source": "sample",
                "uploads": uploads,
                "inputs": {"review-focus": "Unsupported charges and missing approvals"},
                "desired_outcome": "",
                "requirements": {"maximum_cost_usd": 1.0, "required_quality_score": 0.9},
            },
        )
        analyze.raise_for_status()
        plan = analyze.json()

        start = await client.post("/api/runs", json={"plan_id": plan["plan_id"]})
        start.raise_for_status()
        run_id = start.json()["run_id"]

        state: dict = {}
        for _ in range(600):
            await asyncio.sleep(0.25)
            state = (await client.get(f"/api/runs/{run_id}")).json()
            approval = state.get("approval")
            if approval and approval.get("decision") == "pending":
                await client.post(f"/api/runs/{run_id}/approve", json={"decision": "approved"})
                continue
            if state.get("status") in {"completed", "failed", "stopped", "blocked"}:
                break
        else:
            raise SystemExit(f"run did not finish, last status {state.get('status')}")

        if state.get("status") != "completed":
            raise SystemExit(f"run ended as {state.get('status')}: {state.get('error')}")

        proof = (await client.get(f"/api/runs/{run_id}/proof")).json()

        pair = None
        if "--baseline" in sys.argv:
            pair = (await client.post(f"/api/runs/{run_id}/baseline")).json()

    routing = proof["routing"]
    total = routing["operations"]
    local = routing["completed_without_generative_ai"]
    efficient = routing["efficient_ai"]
    advanced = routing["advanced_ai"]
    assisted = efficient + advanced
    calls = proof["usage"]["model_calls"]

    print(f"operations                     : {total}")
    print(f"completed_without_generative_ai: {local}")
    print(f"efficient_ai operations        : {efficient}")
    print(f"advanced_ai operations         : {advanced}")
    print(f"model_calls                    : {calls}")
    print(f"measured cost                  : {proof['economics']['total_calculated_cost_usd']}")
    print(f"decision_complete              : {proof['outcome']['decision_complete']}")
    print(f"why_ai records                 : {len(proof.get('why_ai', []))}")

    assert local + assisted == total, "route counts must sum to the operation total"
    assert len(proof.get("why_ai", [])) == calls, "one governance record per paid call"
    if assisted:
        assert calls >= 1, "a model-assisted operation must record at least one call"

    planned = proof["tokenomics"]["routing"]
    planned_calls = sum(row.get("model_calls", 0) for row in planned["rows"])
    assert planned_calls == calls, f"route table calls {planned_calls} != usage calls {calls}"
    assert planned["total_operations"] == total, "planned and executed totals must match"

    summary_ops = [op for op in proof["operations"] if "summary" in op["label"].lower()]
    assert summary_ops, "the plan must contain a decision-summary operation"
    for operation in summary_ops:
        assert operation["route"] not in {"efficient_ai", "advanced_ai"}, (
            "the decision summary must be deterministic, not a paid model call"
        )

    ambiguity_ops = [
        op for op in proof["operations"] if "interpretation" in op["label"].lower()
    ]
    assert ambiguity_ops, "the plan must reserve an operation for contested interpretation"

    print("\nOperations as recorded:")
    for operation in proof["operations"]:
        print(f"  {operation['label']:<46} {operation['route']:<14} {operation.get('duration_ms')} ms")

    if pair is not None:
        print("\nPaired all-AI baseline:")
        print(f"  available          : {pair.get('available')}")
        print(f"  reason             : {pair.get('reason')}")
        print(f"  governed cost      : {pair['governed']['cost_usd']}")
        if pair.get("baseline"):
            print(f"  all-AI cost        : {pair['baseline']['cost_usd']}")
            print(f"  all-AI model calls : {pair['baseline']['model_calls']}")
            print(f"  equal quality      : {pair.get('equal_quality')}")
            print(f"  saving claimable   : {pair.get('saving_claimable')}")
            print(f"  saving usd         : {pair.get('saving_usd')}")
            print(f"  blocked reason     : {pair.get('saving_blocked_reason')}")
            assert pair["governed"]["cost_usd"] == proof["economics"]["total_calculated_cost_usd"], (
                "the paired comparison must reuse the governed run's measured cost"
            )
            if pair.get("saving_claimable"):
                assert pair.get("equal_quality"), "a saving requires both paths to pass the same checks"

    print("\nAll Prove screen invariants hold.")


asyncio.run(main())
