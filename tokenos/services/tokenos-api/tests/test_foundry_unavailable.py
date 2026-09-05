"""API tests for the Foundry-unavailable state: no model deployment configured.

The suite runs entirely in `TOKENOS_MODEL_MODE=local` (see conftest.py), so these
tests exercise the real "no deployment configured" code path rather than mocking
it. They assert the API degrades honestly instead of fabricating model output or
a calculated cost.

Run: .\\.venv\\Scripts\\python.exe -m pytest tests/test_foundry_unavailable.py -v
"""

from __future__ import annotations

from conftest import run_workflow


def test_health_reports_foundry_unavailable(api_client):
    response = api_client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["modelMode"] == "local"
    assert body["foundryAvailable"] is False


def test_workflows_endpoint_reports_model_unavailable(api_client):
    response = api_client.get("/api/workflows")

    assert response.status_code == 200
    assert response.json()["model_available"] is False


def test_document_review_completes_without_a_model_and_reports_unresolved_items(api_client):
    """Ambiguous charges cannot be explained without a model, so the run must
    complete with them explicitly marked unresolved rather than guessed."""
    proof = run_workflow(
        api_client,
        "document_review",
        {"review-focus": "Unsupported charges and missing approvals"},
    )

    assert proof["status"].startswith("completed")
    assert proof["usage"]["model_calls"] == 0
    assert proof["economics"]["total_calculated_cost_usd"] == 0.0
    findings = proof.get("findings", [])
    unresolved = [item for item in findings if item.get("resolved_by") == "unresolved"]
    if unresolved:
        assert proof["outcome"]["decision_complete"] is False
        assert proof["outcome"]["unresolved_items"] == len(unresolved)


def test_baseline_never_spends_when_no_model_is_configured(api_client):
    """The paired all-AI comparison must refuse to run rather than silently
    executing against local rules and calling that an 'all-AI' result."""
    proof = run_workflow(
        api_client,
        "document_review",
        {"review-focus": "Unsupported charges and missing approvals"},
    )
    run_id = proof["run_id"]

    response = api_client.post(f"/api/runs/{run_id}/baseline", json={"acknowledged": True})

    body = response.json()
    assert body["available"] is False
    assert body["status"] == "unavailable"
    assert "model deployment" in body["reason"]
    assert body["baseline"] is None


def test_foundry_config_endpoint_reports_unavailable(api_client):
    response = api_client.get("/api/foundry/config")

    assert response.status_code == 200
    body = response.json()
    assert body["foundry_available"] is False
    assert body["model_mode"] == "local"
