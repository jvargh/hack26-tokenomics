"""End-to-end check: every workflow runs through the real API path.

Run with:  .\.venv\Scripts\python.exe tests\test_workflows_e2e.py
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from tokenos_api.app import app  # noqa: E402

client = TestClient(app)

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


def run_case(workflow_id: str, inputs: dict) -> dict:
    started = time.perf_counter()

    sample = client.post("/api/uploads/sample", json={"workflow_id": workflow_id})
    assert sample.status_code == 200, sample.text
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
            "desired_outcome": "",
            "requirements": {"maximum_cost_usd": 1.0, "required_quality_score": 0.9},
        },
    )
    assert analyze.status_code == 200, analyze.text
    plan = analyze.json()

    start = client.post("/api/runs", json={"plan_id": plan["plan_id"]})
    assert start.status_code == 200, start.text
    run_id = start.json()["run_id"]

    events: list[str] = []
    with client.stream("GET", f"/api/runs/{run_id}/events") as stream:
        for line in stream.iter_lines():
            if line.startswith("event:"):
                events.append(line.split(":", 1)[1].strip())

    proof = client.get(f"/api/runs/{run_id}/proof")
    assert proof.status_code == 200, proof.text
    body = proof.json()
    elapsed = time.perf_counter() - started

    return {
        "workflow": workflow_id,
        "seconds": round(elapsed, 2),
        "operations": plan["operation_count"],
        "events": len(events),
        "phases": [event for event in events if event == "phase.started"].__len__(),
        "status": body["status"],
        "quality": body["outcome"]["quality_score"],
        "quality_passed": body["outcome"]["quality_passed"],
        "model_calls": body["usage"]["model_calls"],
        "without_generative_ai": body["routing"]["completed_without_generative_ai"],
        "measurement": body["measurement_label"],
        "cost": body["economics"]["total_calculated_cost_usd"],
        "facts": body["facts"],
        "finding": (body.get("finding") or {}).get("title"),
        "failed_checks": [check["name"] for check in body["verification"] if not check["passed"]],
    }


def main() -> int:
    health = client.get("/health").json()
    print(f"health: {health['status']} modelMode={health['modelMode']}\n")

    failures = 0
    for workflow_id, inputs in CASES.items():
        result = run_case(workflow_id, inputs)
        ok = result["status"].startswith("completed") and not result["failed_checks"]
        failures += 0 if ok else 1
        print(json.dumps(result, indent=2))
        print("-" * 70)
    return failures


if __name__ == "__main__":
    raise SystemExit(main())
