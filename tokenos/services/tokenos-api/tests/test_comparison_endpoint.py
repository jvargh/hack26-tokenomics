"""API tests for the baseline/comparison contract: acknowledgement gating, the
read-only comparison cache, and invalid-comparison responses.

Run: .\\.venv\\Scripts\\python.exe -m pytest tests/test_comparison_endpoint.py -v
"""

from __future__ import annotations

from conftest import run_workflow


def test_baseline_requires_acknowledgement(api_client):
    proof = run_workflow(
        api_client,
        "document_review",
        {"review-focus": "Unsupported charges and missing approvals"},
    )
    run_id = proof["run_id"]

    response = api_client.post(f"/api/runs/{run_id}/baseline", json={})

    assert response.status_code == 400
    assert "acknowledged" in response.json()["detail"]


def test_baseline_rejects_explicit_false_acknowledgement(api_client):
    proof = run_workflow(
        api_client,
        "document_review",
        {"review-focus": "Unsupported charges and missing approvals"},
    )
    run_id = proof["run_id"]

    response = api_client.post(f"/api/runs/{run_id}/baseline", json={"acknowledged": False})

    assert response.status_code == 400


def test_baseline_runs_when_acknowledged_and_reports_unavailable_without_a_model(api_client):
    """In local-only test mode (no Foundry configured) the baseline honestly
    reports `unavailable` instead of fabricating a comparison."""
    proof = run_workflow(
        api_client,
        "document_review",
        {"review-focus": "Unsupported charges and missing approvals"},
    )
    run_id = proof["run_id"]

    response = api_client.post(f"/api/runs/{run_id}/baseline", json={"acknowledged": True})

    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert body["status"] == "unavailable"
    assert body["saving_claimable"] is False


def test_comparison_endpoint_is_not_requested_before_baseline_runs(api_client):
    proof = run_workflow(
        api_client,
        "document_review",
        {"review-focus": "Unsupported charges and missing approvals"},
    )
    run_id = proof["run_id"]

    response = api_client.get(f"/api/runs/{run_id}/comparison")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "not_requested"
    assert body["available"] is False


def test_comparison_endpoint_never_triggers_a_model_call(api_client):
    """GET /comparison is read-only. It must return the same cached result twice
    without re-running the baseline (which would spend tokens if a model were
    configured)."""
    proof = run_workflow(
        api_client,
        "document_review",
        {"review-focus": "Unsupported charges and missing approvals"},
    )
    run_id = proof["run_id"]
    api_client.post(f"/api/runs/{run_id}/baseline", json={"acknowledged": True})

    first = api_client.get(f"/api/runs/{run_id}/comparison").json()
    second = api_client.get(f"/api/runs/{run_id}/comparison").json()

    assert first == second


def test_comparison_endpoint_404s_for_unknown_run(api_client):
    response = api_client.get("/api/runs/run-does-not-exist/comparison")

    assert response.status_code == 404


def test_baseline_404s_for_unknown_run(api_client):
    response = api_client.post(
        "/api/runs/run-does-not-exist/baseline", json={"acknowledged": True}
    )

    assert response.status_code == 404
