"""Reporting API aggregation coverage."""

from __future__ import annotations

import csv
import io
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tokenos_api.app import app
from tokenos_api.config import settings
from tokenos_api.optimization import engine
from tokenos_api.optimization.store import store


@pytest.fixture
def client(monkeypatch):
    root = Path(__file__).resolve().parent.parent / ".optimization-test-runtime" / uuid.uuid4().hex
    root.mkdir(parents=True)
    monkeypatch.setattr(settings, "storage_root", root)
    monkeypatch.setattr(settings, "model_mode", "local")
    monkeypatch.setattr(settings, "foundry_base_url", "")
    monkeypatch.setenv("TOKENOS_TENANT_ID", "local")
    monkeypatch.setattr(engine, "load_price_table", lambda: {})
    with TestClient(app) as api:
        yield api
    shutil.rmtree(root)
    if root.parent.exists() and not any(root.parent.iterdir()):
        root.parent.rmdir()


def save_report_run(
    *,
    run_id: str | None = None,
    created_at: str = "2026-01-01T00:00:00+00:00",
    application: str = "support",
    environment: str = "local",
    proof_type: str = "measured",
    optimization_target: str = "measured_workflow",
    governed_spend: float | None = 0.0,
    baseline_spend: float | None = None,
    verified_saving: float | None = None,
    accepted_outcomes: int = 0,
    model_calls: int = 0,
    local_operations: int = 0,
    reuse_operations: int = 0,
    efficient_calls: int = 0,
    advanced_calls: int = 0,
    cost_per_outcome: float | None = None,
    metrics: dict | None = None,
    model_usage: list[dict] | None = None,
) -> str:
    run_id = run_id or f"run_{uuid.uuid4().hex}"
    metrics = dict(metrics or {})
    proof = {
        "runId": run_id,
        "createdAt": created_at,
        "dimensions": {
            "application": application,
            "environment": environment,
            "workflow": "workflow_optimization",
            "inputSource": "test",
            "optimizationTarget": optimization_target,
            "proofType": proof_type,
            "owner": "",
            "costCenter": "",
            "priceTableVersion": "test-prices-v1",
        },
        "cost": {
            "modelSpendUsd": governed_spend,
            "modelCalls": model_calls,
            "localOperations": local_operations,
            "reuseOperations": reuse_operations,
            "efficientCalls": efficient_calls,
            "advancedCalls": advanced_calls,
            "acceptedOutcomes": accepted_outcomes,
            "costPerAcceptedOutcomeUsd": cost_per_outcome,
            "projection": None,
        },
        "baseline": {
            "eligible": verified_saving is not None,
            "baselineModelSpendUsd": baseline_spend,
            "verifiedSavingUsd": verified_saving,
        },
        "metrics": metrics,
        "modelUsage": model_usage or [],
    }
    store.save({
        "runId": run_id,
        "_tenant": "local",
        "status": "completed",
        "createdAt": created_at,
        "proof": proof,
    })
    return run_id


def test_rate_metric_is_mean_not_sum(client):
    for index in range(10):
        save_report_run(
            run_id=f"run_quality_{index}",
            created_at=f"2026-01-{index + 1:02d}T00:00:00+00:00",
            metrics={"qualityPassRate": 0.9},
        )
    rate = client.get("/api/optimization/reports").json()["groups"]["measured"]["rates"]["qualityPassRate"]
    assert rate["sum"] == pytest.approx(9.0)
    assert rate["count"] == 10
    assert 0 <= rate["mean"] <= 1
    assert rate["mean"] == pytest.approx(0.9)
    assert rate["mean"] != pytest.approx(9.0)


def test_none_rate_values_do_not_inflate_count(client):
    save_report_run(run_id="run_null", metrics={"measuredCachedTokenRate": None})
    save_report_run(run_id="run_missing", created_at="2026-01-02T00:00:00+00:00", metrics={})
    save_report_run(run_id="run_value", created_at="2026-01-03T00:00:00+00:00",
                    metrics={"measuredCachedTokenRate": 0.5})
    rate = client.get("/api/optimization/reports").json()["groups"]["measured"]["rates"]["measuredCachedTokenRate"]
    assert rate == {"sum": 0.5, "count": 1, "mean": 0.5}


def test_cost_per_accepted_outcome_is_ratio_of_sums(client):
    save_report_run(run_id="run_small", governed_spend=9.0, accepted_outcomes=1, cost_per_outcome=9.0)
    save_report_run(run_id="run_large", created_at="2026-01-02T00:00:00+00:00",
                    governed_spend=1.0, accepted_outcomes=999, cost_per_outcome=1.0 / 999)
    measured = client.get("/api/optimization/reports").json()["groups"]["measured"]
    assert measured["governedModelSpendUsd"] == pytest.approx(10.0)
    assert measured["acceptedOutcomes"] == 1000
    assert measured["costPerAcceptedOutcomeUsd"] == pytest.approx(0.01)
    assert measured["costPerAcceptedOutcomeUsd"] != pytest.approx((9.0 + 1.0 / 999) / 2)


def test_from_to_filter_includes_lower_and_excludes_upper(client):
    lower = save_report_run(run_id="run_lower", created_at="2026-01-01T00:00:00+00:00")
    middle = save_report_run(run_id="run_middle", created_at="2026-01-02T00:00:00+00:00")
    save_report_run(run_id="run_upper", created_at="2026-01-03T00:00:00+00:00")
    response = client.get(
        "/api/optimization/reports?from=2026-01-01T00:00:00Z&to=2026-01-03T00:00:00Z"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["groups"]["measured"]["runCount"] == 2
    assert {run["runId"] for run in body["runs"]} == {lower, middle}
    assert all(run["createdAt"] for run in body["runs"])


def test_report_query_validation(client):
    naive = client.get("/api/optimization/reports?from=2026-01-01T00:00:00")
    assert naive.status_code == 422
    assert "from" in naive.text
    assert client.get("/api/optimization/reports?bucket=month").status_code == 422
    assert client.get("/api/optimization/reports?optimizationTarget=other").status_code == 422


def test_previous_is_null_without_window_and_populated_with_window(client):
    save_report_run(run_id="run_previous", created_at="2026-01-01T00:00:00+00:00", governed_spend=1.0)
    save_report_run(run_id="run_current", created_at="2026-01-02T00:00:00+00:00", governed_spend=2.0)
    assert client.get("/api/optimization/reports").json()["previous"] is None
    body = client.get(
        "/api/optimization/reports?from=2026-01-02T00:00:00Z&to=2026-01-03T00:00:00Z"
    ).json()
    assert body["groups"]["measured"]["runCount"] == 1
    assert body["groups"]["measured"]["governedModelSpendUsd"] == pytest.approx(2.0)
    assert body["previous"]["measured"]["runCount"] == 1
    assert body["previous"]["measured"]["governedModelSpendUsd"] == pytest.approx(1.0)


def test_empty_range_returns_empty_series_and_opportunities(client):
    save_report_run(run_id="run_old", created_at="2026-01-01T00:00:00+00:00",
                    metrics={"contextMinimizationRate": 0.1})
    body = client.get(
        "/api/optimization/reports?from=2030-01-01T00:00:00Z&to=2030-01-02T00:00:00Z"
    ).json()
    assert body["groups"]["measured"]["runCount"] == 0
    assert body["series"] == []
    assert body["opportunities"] == []


def test_route_tiers_events_and_opportunities_use_measured_evidence(client):
    run_id = save_report_run(
        run_id="run_evidence",
        governed_spend=10.0,
        accepted_outcomes=5,
        model_calls=1,
        local_operations=3,
        reuse_operations=2,
        advanced_calls=1,
        metrics={
            "cacheEligibility": "eligible",
            "measuredCachedTokenRate": 0.05,
            "qualityPassRate": 0.95,
            "contextMinimizationRate": 0.1,
        },
        model_usage=[{"deploymentAlias": "tokenos-advanced", "costUsdExact": "10.0"}],
    )
    for index in range(2):
        save_report_run(
            run_id=f"run_context_{index}",
            created_at=f"2026-01-0{index + 2}T00:00:00+00:00",
            metrics={
                "cacheEligibility": "eligible",
                "measuredCachedTokenRate": 0.05,
                "qualityPassRate": 0.95,
                "contextMinimizationRate": 0.1,
            },
        )
    run = store.require(run_id)
    store.event(run, "model.authorized", {"maximumModelSpendUsd": 1.0})
    store.event(run, "operation.completed", {"route": "tokenos-advanced"})
    store.event(run, "quality.result", {"passed": False})
    store.event(run, "baseline.completed", {"label": "Verified saving"})
    body = client.get("/api/optimization/reports").json()
    assert [tier["tier"] for tier in body["routeTiers"]] == ["local", "reuse", "efficient", "advanced"]
    assert body["routeTiers"][0]["operations"] == 3
    assert body["routeTiers"][1]["operations"] == 2
    assert body["routeTiers"][3]["calls"] == 1
    assert body["routeTiers"][3]["spendUsd"] == pytest.approx(10.0)
    severities = {event["type"]: event["severity"] for event in body["events"]}
    assert severities["cost.authorized"] == "info"
    assert severities["route.selected"] == "warning"
    assert severities["quality.result"] == "risk"
    assert severities["baseline.completed"] == "info"
    assert {item["id"] for item in body["opportunities"]} == {
        "cache-gap", "advanced-tier-share", "context-headroom",
    }
    assert {item["tier"] for item in body["opportunities"]} == {"estimated"}


def test_csv_export_quotes_commas_and_renders_none_empty(client):
    save_report_run(
        run_id="run_csv",
        application="sales, ops",
        governed_spend=1.25,
        baseline_spend=None,
        accepted_outcomes=2,
        cost_per_outcome=None,
        metrics={"qualityPassRate": 1.0, "escalationRate": None},
    )
    response = client.get("/api/optimization/reports/export?format=csv")
    assert response.status_code == 200
    assert '"sales, ops"' in response.text
    assert "None" not in response.text
    rows = list(csv.reader(io.StringIO(response.text)))
    assert rows[0][0:4] == ["runId", "createdAt", "application", "environment"]
    assert rows[1][2] == "sales, ops"
    assert rows[1][8] == ""
    assert rows[1][11] == ""
    assert rows[1][16] == ""
