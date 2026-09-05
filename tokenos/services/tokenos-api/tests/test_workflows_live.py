"""End-to-end check against a running TokenOS API.

Start the API first, then run:
    .\.venv\Scripts\python.exe tests\test_workflows_live.py
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timedelta, timezone

import httpx

BASE = "http://127.0.0.1:8000"

CASES = {
    "false_savings": {
        "reviewer-hourly-rate": "68",
        "acceptance-rule": "Accepted without correction, retry, or reversal",
        "minimum-quality": "0.9",
        "minimum-cohort": "25",
    },
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
}


def run_case(client: httpx.Client, workflow_id: str, inputs: dict) -> dict:
    started = time.perf_counter()

    sample = client.post("/api/uploads/sample", json={"workflow_id": workflow_id})
    sample.raise_for_status()
    uploads = {
        role: [item["upload_id"] for item in items]
        for role, items in sample.json()["uploads"].items()
    }

    analyze = client.post(
        "/api/runs/analyze",
        json={
            "workflow_id": workflow_id,
            "input_source": "sample",
            "uploads": uploads,
            "inputs": inputs,
            "requirements": {"maximum_cost_usd": 1.0, "required_quality_score": 0.9},
        },
    )
    if analyze.status_code != 200:
        raise AssertionError(f"analyze failed: {analyze.status_code} {analyze.text[:500]}")
    plan = analyze.json()

    start = client.post("/api/runs", json={"plan_id": plan["plan_id"]})
    start.raise_for_status()
    run_id = start.json()["run_id"]

    events: list[str] = []
    with client.stream("GET", f"/api/runs/{run_id}/events", timeout=60.0) as stream:
        for line in stream.iter_lines():
            if line.startswith("event:"):
                events.append(line.split(":", 1)[1].strip())
                if events[-1] in {"run.completed", "run.failed", "run.blocked", "run.stopped"}:
                    break

    proof = client.get(f"/api/runs/{run_id}/proof")
    proof.raise_for_status()
    body = proof.json()

    return {
        "workflow": workflow_id,
        "seconds": round(time.perf_counter() - started, 2),
        "operations": plan["operation_count"],
        "sse_events": len(events),
        "phases": sum(1 for event in events if event == "phase.started"),
        "status": body["status"],
        "quality": body["outcome"]["quality_score"],
        "quality_passed": body["outcome"]["quality_passed"],
        "deadline_met": body["outcome"]["deadline_met"],
        "model_calls": body["usage"]["model_calls"],
        "model_mode": body["usage"]["model_mode"],
        "without_generative_ai": body["routing"]["completed_without_generative_ai"],
        "measurement": body["measurement_label"],
        "cost_usd": body["economics"]["total_calculated_cost_usd"],
        "finding": (body.get("finding") or {}).get("title"),
        "facts": body["facts"],
        "failed_checks": [check["name"] for check in body["verification"] if not check["passed"]],
    }


def main() -> int:
    with httpx.Client(base_url=BASE, timeout=60.0) as client:
        health = client.get("/health").json()
        print(f"health: {health['status']}  modelMode={health['modelMode']}\n")

        failures = 0
        for workflow_id, inputs in CASES.items():
            try:
                result = run_case(client, workflow_id, inputs)
            except Exception as error:  # noqa: BLE001 - test harness
                print(f"{workflow_id}: FAILED {error}")
                failures += 1
                continue
            ok = result["status"].startswith("completed")
            failures += 0 if ok else 1
            print(json.dumps(result, indent=2))
            print("-" * 72)
        return failures


if __name__ == "__main__":
    sys.exit(main())
