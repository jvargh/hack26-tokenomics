"""Shared pytest fixtures.

Forces local-only mode and a scratch storage root before `tokenos_api` is ever
imported, so the automated suite never depends on live Foundry credentials and
never writes into the real runtime ledger used by a running demo server.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_SCRATCH_STORAGE = Path(tempfile.mkdtemp(prefix="tokenos-test-"))

os.environ.setdefault("TOKENOS_MODEL_MODE", "local")
os.environ.setdefault("TOKENOS_PHASE_PACING_MS", "0")
os.environ.setdefault("TOKENOS_OPERATION_PACING_MS", "0")
os.environ.setdefault("TOKENOS_STEP_PACING_MS", "0")
os.environ.setdefault("TOKENOS_STREAM_ATTACH_TIMEOUT_SECONDS", "5")
os.environ.setdefault("TOKENOS_STORAGE_ROOT", str(_SCRATCH_STORAGE))

import pytest  # noqa: E402


@pytest.fixture(scope="session")
def api_client():
    from fastapi.testclient import TestClient

    from tokenos_api.app import app

    with TestClient(app) as client:
        yield client


def run_workflow(client, workflow_id: str, inputs: dict, requirements: dict | None = None) -> dict:
    """Drives one workflow through analyze -> run -> proof using bundled sample input."""
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
            "requirements": requirements or {"maximum_cost_usd": 1.0, "required_quality_score": 0.9},
        },
    )
    assert analyze.status_code == 200, analyze.text
    plan = analyze.json()

    start = client.post("/api/runs", json={"plan_id": plan["plan_id"]})
    assert start.status_code == 200, start.text
    run_id = start.json()["run_id"]

    # Local mode has no model latency, but some workflows (e.g. software_validation)
    # spawn a real subprocess and parse a real archive across several phases, which
    # can take several real seconds even with pacing disabled. Poll generously
    # rather than depending on the SSE stream in these tests.
    import time

    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        response = client.get(f"/api/runs/{run_id}/proof")
        if response.status_code == 200:
            return response.json()
        time.sleep(0.1)
    raise AssertionError(f"Run {run_id} never produced a proof.")
