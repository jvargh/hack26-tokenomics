"""History deletion.

A recorded proof is a durable claim, so deleting one must remove it everywhere
it is held: the run history, the optimization store, and the durable ledger
behind enterprise reporting. A run that is still executing must never be
deletable, because it has no proof yet.

Each test gets its own storage root, so clearing the whole history here cannot
disturb any other suite.
"""

from __future__ import annotations

import shutil
import sys
import time
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tokenos_api.app import app
from tokenos_api.config import settings
from tokenos_api.optimization import engine
from tokenos_api.storage.runs import run_store


@pytest.fixture
def client(monkeypatch):
    root = Path(__file__).resolve().parent.parent / ".history-delete-runtime" / uuid.uuid4().hex
    root.mkdir(parents=True)
    monkeypatch.setattr(settings, "storage_root", root)
    monkeypatch.setattr(settings, "model_mode", "local")
    monkeypatch.setattr(settings, "foundry_base_url", "")
    monkeypatch.setenv("TOKENOS_TENANT_ID", "local")
    monkeypatch.setattr(engine, "load_price_table", lambda: {})
    run_store.clear()
    with TestClient(app) as api:
        yield api
    run_store.clear()
    shutil.rmtree(root, ignore_errors=True)
    if root.parent.exists() and not any(root.parent.iterdir()):
        root.parent.rmdir()


def _history_ids(client) -> list[str]:
    response = client.get("/api/runs")
    assert response.status_code == 200, response.text
    return [run["run_id"] for run in response.json()["runs"]]


def _report_ids(client) -> list[str]:
    response = client.get("/api/reports/runs")
    assert response.status_code == 200, response.text
    return [run["run_id"] for run in response.json()["runs"]]


WORKFLOW_INPUTS = {
    "deadline_processing": {
        "processing-instruction": "Classify each record by category and summarize the totals.",
        "completion-deadline": "2026-12-31T23:59",
        "output-format": "CSV",
    },
    "software_validation": {
        "requested-change": "Add the archive endpoint declared in the specification.",
        "validation-level": "Static plus allowed tests",
    },
}


def _completed_workflow_run(client, workflow: str = "deadline_processing") -> str:
    """Drives a workflow to a recorded proof using bundled sample input."""
    sample = client.post("/api/uploads/sample", json={"workflow_id": workflow})
    assert sample.status_code == 200, sample.text
    uploads = {role: [item["upload_id"] for item in items]
               for role, items in sample.json()["uploads"].items()}

    analyze = client.post("/api/runs/analyze", json={
        "workflow_id": workflow, "input_source": "sample", "uploads": uploads,
        "inputs": WORKFLOW_INPUTS[workflow],
        "desired_outcome": "",
        "requirements": {"maximum_cost_usd": 1.0, "required_quality_score": 0.9},
    })
    assert analyze.status_code == 200, analyze.text

    start = client.post("/api/runs", json={"plan_id": analyze.json()["plan_id"]})
    assert start.status_code == 200, start.text
    run_id = start.json()["run_id"]

    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if client.get(f"/api/runs/{run_id}/proof").status_code == 200:
            return run_id
        time.sleep(0.1)
    raise AssertionError(f"Run {run_id} never produced a proof.")


def _described_optimization_run(client) -> str:
    response = client.post("/api/runs", json={
        "workflow": "workflow_optimization", "inputSource": "sample", "mode": "measure",
        "inputs": {"workflowDescription": "An assistant sends full context for every request.",
                   "sampleId": "customer_assistance"},
        "requirements": {"qualityRequirements": ["same_answer_quality"],
                         "optimizationGoal": "cost_per_accepted_outcome", "maxModelSpendUsd": 0.05,
                         "allowAdvancedEscalation": False},
    })
    assert response.status_code == 200, response.text
    return response.json()["runId"]


def test_delete_removes_run_from_history_and_reporting(client):
    run_id = _completed_workflow_run(client)
    assert run_id in _history_ids(client)
    assert run_id in _report_ids(client)

    response = client.delete(f"/api/runs/{run_id}")
    assert response.status_code == 200, response.text
    assert response.json() == {"deleted": True, "run_id": run_id}

    assert run_id not in _history_ids(client)
    # A deleted run must not survive in the durable reporting view either.
    assert run_id not in _report_ids(client)
    assert client.get(f"/api/runs/{run_id}").status_code == 404


def test_deleting_an_unknown_run_is_reported_clearly(client):
    response = client.delete("/api/runs/run-does-not-exist")
    assert response.status_code == 404
    assert "No run with that identifier." in response.json()["detail"]


def test_delete_removes_an_optimization_run(client):
    run_id = _described_optimization_run(client)
    assert run_id in _history_ids(client)

    response = client.delete(f"/api/runs/{run_id}")
    assert response.status_code == 200, response.text
    assert run_id not in _history_ids(client)
    # The record itself is gone, not merely hidden from the list.
    assert client.get(f"/api/runs/{run_id}").status_code == 404


def test_deleting_one_run_leaves_the_others(client):
    kept = _described_optimization_run(client)
    removed = _described_optimization_run(client)

    assert client.delete(f"/api/runs/{removed}").status_code == 200

    remaining = _history_ids(client)
    assert kept in remaining
    assert removed not in remaining


def test_a_run_that_completed_with_findings_can_be_deleted(client):
    """`completed_with_findings` is a finished run. It must not be mistaken for
    one still in flight and left undeletable."""
    run_id = _completed_workflow_run(client, workflow="software_validation")
    assert client.get(f"/api/runs/{run_id}").json()["status"] == "completed_with_findings"

    assert client.delete(f"/api/runs/{run_id}").status_code == 200
    assert run_id not in _history_ids(client)


def test_clear_all_empties_the_history(client):
    _completed_workflow_run(client)
    _completed_workflow_run(client, workflow="software_validation")
    _described_optimization_run(client)
    assert len(_history_ids(client)) >= 3

    response = client.delete("/api/runs")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["deleted"] >= 3
    assert body["kept_running"] == 0

    assert _history_ids(client) == []
    assert _report_ids(client) == []
