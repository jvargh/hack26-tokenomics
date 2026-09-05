"""Isolated API coverage. No live provider, user data, or external storage."""

from __future__ import annotations

import asyncio
import copy
import io
import json
import shutil
import sys
import time
import uuid
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tokenos_api.app import app
from tokenos_api.config import settings
from tokenos_api.modeladapter import ModelResult, ModelUnavailable
from tokenos_api.optimization import engine, imports
from tokenos_api.optimization.fixtures import sample_requests
from tokenos_api.optimization.quality import local_result
from tokenos_api.optimization.store import OptimizationStore, store


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


def request(sample="customer_assistance", **requirement_overrides):
    return {
        "workflow": "workflow_optimization", "inputSource": "sample", "mode": "measure",
        "inputs": {"workflowDescription": "An assistant sends full context for every request.", "sampleId": sample},
        "requirements": {"qualityRequirements": ["same_answer_quality", "grounded_citations", "structured_output"],
                         "optimizationGoal": "cost_per_accepted_outcome", "maxModelSpendUsd": 0.05,
                         "allowAdvancedEscalation": False, **requirement_overrides},
    }


@pytest.mark.parametrize("mode", ["analyze", "measure"])
@pytest.mark.parametrize("sample_id", ["customer_assistance", "policy_review", "code_validation", "classification"])
def test_workflow_example_defaults_build_a_real_plan(client, monkeypatch, mode, sample_id):
    monkeypatch.setattr(engine, "get_model_adapter", lambda: pytest.fail("Example planning must not call Foundry"))
    response = client.get("/api/optimization/samples")
    assert response.status_code == 200
    sample = next(item for item in response.json()["samples"] if item["id"] == sample_id)
    assert sample["description"] and sample["description"] != sample["title"]
    assert sample["desiredOutcome"] and sample["recurringVolume"]["value"] > 0
    assert sample["requirements"]["qualityRequirements"]
    assert sample["requirements"]["optimizationGoal"]
    payload = {
        "workflow": "workflow_optimization",
        "optimizationTarget": "current_workflow" if mode == "analyze" else "measured_workflow",
        "mode": mode, "inputSource": "workflow_example",
        "inputs": {
            "sampleId": sample_id, "workflowDescription": sample["description"],
            "desiredOutcome": sample["desiredOutcome"], "recurringVolume": sample["recurringVolume"],
        },
        "requirements": sample["requirements"],
    }
    run_id = prepare(client, payload)
    state = client.get(f"/api/runs/{run_id}").json()
    assert state["status"] == "optimized" and state["proof"] is None
    assert state["badges"] == ["Measured sample run"]
    assert state["currentRoute"]["representativeRequests"] == sample["requestCount"]
    assert state["currentRoute"]["modelSpendUsd"] is None
    assert store.require(run_id)["_telemetry"] == []
    assert not store.require(run_id).get("_authorization")
    if mode == "analyze":
        assert sample["analysisNotice"] in state["dataAssumptions"]
        authorized = client.post(f"/api/runs/{run_id}/authorize", json={"authorizeModelCost": False})
        assert authorized.status_code == 200, authorized.text
        assert client.post(f"/api/runs/{run_id}/execute", json={}).status_code == 200
        proof = wait(client, run_id)["proof"]
        assert proof["mode"] == "analyze" and not proof["verification"]["passed"]
        assert proof["modelUsage"] == []
        assert proof["cost"]["modelSpendUsd"] is None
        assert proof["baseline"]["eligible"] is False
        assert client.post(f"/api/runs/{run_id}/baseline", json={
            "acknowledgeModelCost": True, "baselineProfile": "all_ai_v1",
        }).status_code == 409


def test_non_sample_analysis_still_requires_real_telemetry(client):
    payload = request()
    payload.update({"mode": "analyze", "inputSource": "upload"})
    payload["inputs"] = {
        "workflowDescription": "Analyze uploaded requests without historical usage.",
        "representativeRequests": sample_requests("customer_assistance"),
    }
    response = client.post("/api/runs", json=payload)
    assert response.status_code == 422
    assert "actual telemetry" in response.text


def prepare(client, payload=None):
    response = client.post("/api/runs", json=payload or request())
    assert response.status_code == 200, response.text
    run_id = response.json()["runId"]
    response = client.post(f"/api/runs/{run_id}/analyze", json={})
    assert response.status_code == 200, response.text
    response = client.post(f"/api/runs/{run_id}/optimize", json={"approvePlan": True})
    assert response.status_code == 200, response.text
    return run_id


def authorize_execute(client, run_id, **authorization):
    response = client.post(f"/api/runs/{run_id}/authorize", json={"authorizeModelCost": True, **authorization})
    assert response.status_code == 200, response.text
    response = client.post(f"/api/runs/{run_id}/execute", json={})
    assert response.status_code == 200, response.text
    return wait(client, run_id)


def wait(client, run_id, baseline=False):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        state = client.get(f"/api/runs/{run_id}").json()
        if (state.get("baseline", {}).get("status") in {"completed", "failed"} if baseline else state["status"] in {"completed", "failed"}):
            return state
        time.sleep(0.01)
    raise AssertionError("Run did not finish.")


class FakeProvider:
    def __init__(self, *, wrong=False, unavailable=False, delay=0, cached=25):
        self.calls = []
        self.wrong = wrong
        self.unavailable = unavailable
        self.delay = delay
        self.cached = cached

    async def generate(self, **kwargs):
        self.calls.append(kwargs)
        assert kwargs["strict_usage"] and kwargs["single_attempt"]
        assert "expectedOutput" not in kwargs["input_text"]
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.unavailable:
            raise ModelUnavailable("secret provider diagnostic must not reach client")
        item = json.loads(kwargs["input_text"])
        output, _ = local_result(item)
        if output is None:
            if item["taskType"] == "classification":
                output = {"decision": "human_review", "citations": ["labels#ambiguous"]}
            elif item["taskType"] == "code_validation":
                output = {"decision": "change_required", "citations": ["tests#total"]}
            else:
                output = {"decision": "approval_required", "citations": ["policy#exception"]}
        if self.wrong:
            output["decision"] = "wrong"
        return ModelResult(route=kwargs["route"], deployment=kwargs["deployment"], content=json.dumps(output),
                           input_tokens=100, output_tokens=20, duration_ms=4, calculated_cost_usd=999,
                           price_configured=True, request_id=f"provider-{len(self.calls)}", model_version="model-v1",
                           cached_input_tokens=self.cached, reasoning_tokens=5)


def provider(monkeypatch, **kwargs):
    fake = FakeProvider(**kwargs)
    table = {"version": "test-prices-v1", **{deployment: {"input_per_1m_usd": 1, "output_per_1m_usd": 2,
                                                       "cached_input_per_1m_usd": 0.2}
                                            for deployment in engine._deployments().values()}}
    monkeypatch.setattr(engine, "load_price_table", lambda: copy.deepcopy(table))
    monkeypatch.setattr(engine, "model_available", lambda: True)
    monkeypatch.setattr(engine, "get_model_adapter", lambda: fake)
    return fake, table


def test_primary_workflow_ids_and_economics_remain(client):
    workflows = client.get("/api/workflows").json()["workflows"]
    assert [item["workflow_id"] for item in workflows] == [
        "document_review", "software_validation", "deadline_processing", "workflow_optimization",
    ]
    from tokenos_api.workflows import get_workflow
    assert get_workflow("false_savings").workflow_id == "false_savings"
    assert get_workflow("validate_software").workflow_id == "software_validation"
    assert get_workflow("meet_deadline").workflow_id == "deadline_processing"


def test_describe_and_stages_never_call_provider(client, monkeypatch):
    fake, _ = provider(monkeypatch)
    created = client.post("/api/runs", json=request("policy_review")).json()
    assert created["phase"] == "describe" and created["status"] == "described"
    run_id = created["runId"]
    assert client.post(f"/api/runs/{run_id}/execute", json={}).status_code == 409
    assert client.post(f"/api/runs/{run_id}/authorize", json={"authorizeModelCost": True}).status_code == 409
    assert client.post(f"/api/runs/{run_id}/analyze", json={}).status_code == 200
    assert client.post(f"/api/runs/{run_id}/optimize", json={"approvePlan": False}).status_code == 422
    assert client.post(f"/api/runs/{run_id}/optimize", json={"approvePlan": True}).status_code == 200
    assert not fake.calls
    assert client.post(f"/api/runs/{run_id}/authorize", json={}).status_code == 409
    assert not fake.calls
    assert client.post(f"/api/runs/{run_id}/authorize", json={"authorizeModelCost": True}).status_code == 200
    assert not fake.calls


def test_local_sample_executes_verifies_and_persists_sse(client, monkeypatch):
    monkeypatch.setattr(engine, "get_model_adapter", lambda: pytest.fail("Local sample must not call a provider"))
    payload = request()
    payload["inputs"]["recurringVolume"] = {"value": 10000, "period": "month"}
    run_id = prepare(client, payload)
    state = authorize_execute(client, run_id)
    proof = state["proof"]
    assert state["status"] == "completed" and proof["verification"]["passed"]
    assert proof["cost"]["modelCalls"] == 0 and proof["cost"]["modelSpendUsd"] == 0
    assert proof["cost"]["localOperations"] == 2 and proof["cost"]["reuseOperations"] == 2
    assert proof["badges"] == ["Measured sample run"]
    assert proof["cost"]["projection"]["badge"] == "Projected"
    assert proof["baseline"]["label"] == "Comparison not run"
    assert proof["baseline"]["verifiedSavingUsd"] is None
    assert len(proof["outcomes"]) == 4
    reopened = OptimizationStore(settings.storage_root / "optimization.sqlite3")
    assert reopened.get(run_id)["proof"] == proof
    stream = client.get(f"/api/runs/{run_id}/events")
    assert stream.headers["content-type"].startswith("text/event-stream")
    events = [json.loads(line[6:]) for line in stream.text.splitlines() if line.startswith("data: ")]
    phases = [event["phase"] for event in events if event["type"] == "phase.started"]
    assert phases == ["plan", "optimize", "protect", "run", "verify", "prove"]
    assert [event["sequence"] for event in events] == sorted(set(event["sequence"] for event in events))
    resume = client.get(f"/api/runs/{run_id}/events", headers={"Last-Event-ID": str(events[-2]["sequence"])})
    assert resume.text.count("data: ") == 1 and "run.completed" in resume.text
    report = client.get("/api/optimization/reports").json()
    assert report["groups"]["sample"]["runCount"] == 1
    assert report["groups"]["measured"]["runCount"] == 0
    assert report["groups"]["projected"]["projectionCount"] == 1


@pytest.mark.parametrize("sample", ["policy_review", "code_validation", "classification"])
def test_unavailable_samples_block_honestly_at_protect(client, sample):
    run_id = prepare(client, request(sample))
    response = client.post(f"/api/runs/{run_id}/authorize", json={"authorizeModelCost": True})
    assert response.status_code == 409
    checks = response.json()["detail"]["protectionChecks"]
    assert any(check["id"] == "provider" and not check["passed"] for check in checks)
    state = client.get(f"/api/runs/{run_id}").json()
    assert state["status"] == "optimized" and state["proof"] is None


@pytest.mark.parametrize("sample", ["policy_review", "code_validation", "classification"])
def test_real_local_work_and_bounded_provider_usage(client, monkeypatch, sample):
    fake, _ = provider(monkeypatch)
    state = authorize_execute(client, prepare(client, request(sample)))
    proof = state["proof"]
    assert state["status"] == "completed", proof
    assert len(fake.calls) == 1
    assert proof["cost"]["modelSpendUsd"] == pytest.approx(0.00012)
    usage = proof["modelUsage"][0]
    assert usage["totalTokens"] == 120 and usage["cachedInputTokens"] == 25 and usage["reasoningTokens"] == 5
    assert usage["costUsd"] != 999 and usage["cachedUsageEvidence"] == "provider_response"
    assert usage["deploymentAlias"] == "tokenos-efficient"
    assert proof["verification"]["processed"] == proof["verification"]["total"]


def test_provider_failure_is_not_zero_cost_success(client, monkeypatch):
    fake, _ = provider(monkeypatch, unavailable=True)
    state = authorize_execute(client, prepare(client, request("policy_review")))
    assert len(fake.calls) == 1
    assert state["status"] == "failed" and not state["proof"]["verification"]["passed"]
    assert state["error"]["category"] == "Unavailable"
    assert state["proof"]["cost"]["modelSpendUsd"] is None
    assert "secret provider diagnostic" not in json.dumps(state)
    assert state["proof"]["baseline"]["eligible"] is False


def test_incorrect_actual_output_fails_acceptance(client, monkeypatch):
    fake, _ = provider(monkeypatch, wrong=True)
    run_id = prepare(client, request("policy_review"))
    state = authorize_execute(client, run_id)
    assert not state["proof"]["verification"]["passed"]
    assert any(not gate["passed"] and gate["id"] == "outcome_acceptance" for gate in state["proof"]["qualityGates"])
    assert state["proof"]["cost"]["modelSpendUsd"] > 0
    assert client.post(f"/api/runs/{run_id}/baseline", json={"acknowledgeModelCost": True, "baselineProfile": "all_ai_v1"}).status_code == 409


def test_required_tests_do_not_pass_because_diagnosis_looks_valid(client, monkeypatch):
    provider(monkeypatch)
    run_id = prepare(client, request("code_validation", qualityRequirements=["same_answer_quality", "required_tests"]))
    state = authorize_execute(client, run_id)
    assert state["status"] == "failed"
    assert any(gate["id"] == "required_tests" and not gate["passed"] for gate in state["proof"]["qualityGates"])


def test_unsupported_requirement_and_missing_expected_outputs_block(client):
    run_id = prepare(client, request(qualityRequirements=["unsupported_accuracy_evaluator"]))
    blocked = client.post(f"/api/runs/{run_id}/authorize", json={})
    assert blocked.status_code == 409 and "Unsupported quality criterion" in blocked.text
    payload = request()
    payload["inputSource"] = "upload"
    payload["inputs"] = {"workflowDescription": "Unlabeled representative requests", "representativeRequests": ["one", "two", "three"]}
    run_id = prepare(client, payload)
    blocked = client.post(f"/api/runs/{run_id}/authorize", json={"authorizeModelCost": True})
    assert blocked.status_code == 409 and "expectedOutput" in blocked.text


def test_human_approval_requires_protect_acknowledgement(client):
    run_id = prepare(client, request(qualityRequirements=["same_answer_quality", "human_approval"], humanApprovalGranted=True))
    assert client.post(f"/api/runs/{run_id}/authorize", json={"authorizeModelCost": True}).status_code == 409
    state = authorize_execute(client, run_id, humanApprovalGranted=True)
    assert state["proof"]["verification"]["passed"]


def test_baseline_acknowledgement_concurrency_and_valid_saving(client, monkeypatch):
    fake, _ = provider(monkeypatch, delay=0.04)
    run_id = prepare(client)
    state = authorize_execute(client, run_id)
    assert not fake.calls
    for payload in ({}, {"acknowledgeModelCost": False, "baselineProfile": "all_ai_v1"},
                    {"acknowledgeModelCost": True, "baselineProfile": "changed"},
                    {"acknowledgeModelCost": True, "baselineProfile": "all_ai_v1", "maxOutputTokens": 1000}):
        assert client.post(f"/api/runs/{run_id}/baseline", json=payload).status_code == 400
    acknowledgement = {"acknowledgeModelCost": True, "baselineProfile": "all_ai_v1"}
    assert client.post(f"/api/runs/{run_id}/baseline", json=acknowledgement).status_code == 200
    assert client.post(f"/api/runs/{run_id}/baseline", json=acknowledgement).status_code == 409
    state = wait(client, run_id, baseline=True)
    baseline = state["proof"]["baseline"]
    assert len(fake.calls) == 4
    assert baseline["eligible"] and baseline["label"] == "Verified saving"
    assert baseline["verifiedSavingUsd"] == pytest.approx(0.00048)
    assert baseline["verifiedSavingPercent"] == 100
    assert baseline["modelCallsAvoided"] == 4
    assert baseline["contract"]["inputManifestHash"] == state["proof"]["inputManifestHash"]
    assert client.post(f"/api/runs/{run_id}/baseline", json=acknowledgement).status_code == 409


def test_failed_baseline_cannot_claim_saving(client, monkeypatch):
    fake, _ = provider(monkeypatch)
    run_id = prepare(client)
    authorize_execute(client, run_id)
    fake.wrong = True
    client.post(f"/api/runs/{run_id}/baseline", json={"acknowledgeModelCost": True, "baselineProfile": "all_ai_v1"})
    state = wait(client, run_id, baseline=True)
    assert not state["proof"]["baseline"]["eligible"]
    assert state["proof"]["baseline"]["label"] == "No valid comparison"


@pytest.mark.parametrize("mutation", ["manifest", "quality", "contract", "output_limit", "price"])
def test_baseline_rejects_changed_protected_contract(client, monkeypatch, mutation):
    fake, table = provider(monkeypatch)
    run_id = prepare(client)
    authorize_execute(client, run_id)
    run = store.require(run_id)
    if mutation == "manifest":
        run["inputManifest"][0]["sha256"] = "changed"
    elif mutation == "quality":
        run["requirements"]["qualityRequirements"] = ["structured_output"]
    elif mutation == "contract":
        run["requirements"]["outputContract"]["required"] = []
    elif mutation == "output_limit":
        run["requirements"]["maxOutputTokens"] += 1
    else:
        table["version"] = "changed"
    store.save(run)
    result = client.post(f"/api/runs/{run_id}/baseline", json={"acknowledgeModelCost": True, "baselineProfile": "all_ai_v1"})
    assert result.status_code == 409
    assert not fake.calls


@pytest.mark.parametrize("extension", ["json", "jsonl", "csv", "zip"])
def test_upload_representative_formats_and_manifest(client, extension):
    rows = sample_requests("customer_assistance")
    if extension == "json":
        content = json.dumps({"requests": rows}).encode()
    elif extension == "jsonl":
        content = "\n".join(json.dumps(row) for row in rows).encode()
    elif extension == "csv":
        import csv
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=["id", "taskType", "input", "context", "expectedOutput"])
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(row[key]) if isinstance(row[key], (dict, list)) else row[key] for key in writer.fieldnames})
        content = output.getvalue().encode()
    else:
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("requests.json", json.dumps(rows))
        content = output.getvalue()
    response = client.post("/api/optimization/uploads", data={"role": "test_inputs"},
                           files=[("files", (f"requests.{extension}", content))])
    assert response.status_code == 200, response.text
    artifact = response.json()["files"][0]
    assert len(artifact["sha256"]) == 64 and artifact["size"] == len(content)
    payload = request()
    payload["inputSource"] = "upload"
    payload["inputs"] = {"workflowDescription": "Uploaded assistant", "testInputIds": [artifact["fileId"]]}
    run_id = prepare(client, payload)
    state = authorize_execute(client, run_id)
    assert state["proof"]["verification"]["passed"]
    assert state["proof"]["badges"] == []


def test_upload_limits_zip_traversal_and_role_rejection(client, monkeypatch):
    assert client.post("/api/optimization/uploads", data={"role": "telemetry"},
                       files=[("files", ("bad.exe", b"bad"))]).status_code == 422
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("../outside.json", json.dumps([{"input": "bad"}]))
    assert client.post("/api/optimization/uploads", data={"role": "test_inputs"},
                       files=[("files", ("unsafe.zip", output.getvalue()))]).status_code == 422
    monkeypatch.setattr(settings, "max_file_bytes", 16)
    assert client.post("/api/optimization/uploads", data={"role": "test_inputs"},
                       files=[("files", ("huge.json", b" " * 17))]).status_code == 422


@pytest.mark.parametrize("count", [2, 21])
def test_representative_request_bounds(client, count):
    payload = request()
    payload["inputSource"] = "upload"
    payload["inputs"] = {"workflowDescription": "Input bounds", "representativeRequests": [str(i) for i in range(count)]}
    assert client.post("/api/runs", json=payload).status_code == 422


def test_native_and_normalized_telemetry_analysis_is_not_a_verified_replay(client, monkeypatch):
    monkeypatch.setattr(settings, "foundry_efficient_deployment", "private-engineering-deployment")
    fake, _ = provider(monkeypatch)
    deployment = engine._deployments()["tokenos-efficient"]
    records = [{"request_id": f"provider-{i}", "deployment": deployment, "input_tokens": 100,
                "output_tokens": 20, "cached_input_tokens": 25, "status": "accepted"} for i in range(3)]
    upload = client.post("/api/optimization/uploads", data={"role": "telemetry"},
                         files=[("files", ("proof.json", json.dumps({"proof": {"model_usage": records}}).encode()))])
    payload = request()
    payload["inputSource"], payload["mode"] = "upload", "analyze"
    payload["inputs"] = {"workflowDescription": "Provider telemetry", "telemetryExportIds": [upload.json()["files"][0]["fileId"]],
                         "recurringVolume": {"value": 1000, "period": "month"}}
    state = authorize_execute(client, prepare(client, payload))
    assert not fake.calls and state["proof"]["telemetryCompleteness"] == "complete"
    assert state["proof"]["cost"]["label"] == "Measured current cost"
    assert state["proof"]["cost"]["modelSpendUsd"] == pytest.approx(0.00036)
    assert not state["proof"]["verification"]["passed"]
    assert state["proof"]["cost"]["projection"]["badge"] == "Projected"
    assert all(key in state["proof"] for key in ("inputManifest", "executionContract", "outcomes", "metrics", "error"))
    assert state["currentRoute"]["modelDistribution"] == {"tokenos-efficient": 3}
    assert "private-engineering-deployment" not in json.dumps(state)


def test_connection_scopes_tenant_and_no_browser_url_credentials(client, monkeypatch):
    payload = request()
    payload["inputSource"] = "connected"
    payload["inputs"] = {"workflowDescription": "Registered support", "applicationId": "support-archive"}
    state = authorize_execute(client, prepare(client, payload))
    assert state["proof"]["verification"]["passed"]
    assert state["proof"]["badges"] == ["Measured sample run"]
    payload["inputs"]["url"] = "https://not-authorized.invalid"
    assert client.post("/api/runs", json=payload).status_code == 422
    payload["inputs"].pop("url")
    payload["inputs"]["filters"] = {"reference": "outside-scope"}
    assert client.post("/api/runs", json=payload).status_code == 403
    monkeypatch.setenv("TOKENOS_TENANT_ID", "other-tenant")
    assert client.get("/api/optimization/applications").json()["applications"] == []
    assert client.get(f"/api/runs/{state['runId']}").status_code == 404


def test_registered_connection_does_not_gain_model_execution_from_client(client, monkeypatch):
    fake, _ = provider(monkeypatch)
    app_record = copy.deepcopy(imports.APPLICATIONS["support-archive"])
    app_record["fixture"] = "policy_review"
    monkeypatch.setitem(imports.APPLICATIONS, "support-archive", app_record)
    payload = request()
    payload["inputSource"] = "connected"
    payload["inputs"] = {"workflowDescription": "Approved telemetry only", "applicationId": "support-archive"}
    run_id = prepare(client, payload)
    response = client.post(f"/api/runs/{run_id}/authorize", json={"authorizeModelCost": True})
    assert response.status_code == 409 and not fake.calls
    assert any(check["id"] == "scope" and not check["passed"] for check in response.json()["detail"]["protectionChecks"])


def test_advanced_escalation_is_bounded_and_all_attempts_are_priced(client, monkeypatch):
    fake, _ = provider(monkeypatch)
    original = fake.generate

    async def fail_efficient_only(**kwargs):
        fake.wrong = kwargs["route"] == "efficient_ai"
        return await original(**kwargs)

    monkeypatch.setattr(fake, "generate", fail_efficient_only)
    run_id = prepare(client, request("policy_review", allowAdvancedEscalation=True, maxAdvancedCalls=1))
    state = authorize_execute(client, run_id)
    assert state["proof"]["verification"]["passed"]
    assert len(fake.calls) == 2
    assert state["proof"]["cost"]["modelSpendUsd"] == pytest.approx(0.00024)
    assert [usage["deploymentAlias"] for usage in state["proof"]["modelUsage"]] == ["tokenos-efficient", "tokenos-advanced"]
    assert state["proof"]["modelUsage"][0]["qualityPassed"] is False
    assert state["proof"]["modelUsage"][1]["qualityPassed"] is True


def test_budget_reservation_blocks_before_any_provider_call(client, monkeypatch):
    fake, _ = provider(monkeypatch)
    run_id = prepare(client, request("policy_review", maxModelSpendUsd=0.000001))
    response = client.post(f"/api/runs/{run_id}/authorize", json={"authorizeModelCost": True})
    assert response.status_code == 409
    assert any(check["id"] == "budget" and not check["passed"] for check in response.json()["detail"]["protectionChecks"])
    assert not fake.calls


def test_scope_freshness_and_input_changes_prevent_reuse(client):
    rows = sample_requests("customer_assistance")
    rows[2]["freshnessVersion"] = "new"
    rows[3]["reuseScope"] = "other-scope"
    payload = request()
    payload["inputSource"] = "upload"
    payload["inputs"] = {"workflowDescription": "Separate access and freshness", "representativeRequests": rows}
    state = authorize_execute(client, prepare(client, payload))
    assert state["proof"]["cost"]["reuseOperations"] == 0
    assert state["proof"]["cost"]["localOperations"] == 4


def test_plaintext_secrets_are_blocked_and_structured_redaction_preserves_json(client, monkeypatch):
    fake, _ = provider(monkeypatch)
    rows = sample_requests("policy_review")
    rows[-1]["input"] = {"question": "Does retrospective approval require human review?", "password": "do-not-send-this",
                         "contact": "someone@example.org"}
    payload = request()
    payload["inputSource"] = "upload"
    payload["inputs"] = {"workflowDescription": "Sensitive bounded input", "representativeRequests": rows}
    run_id = prepare(client, payload)
    response = client.post(f"/api/runs/{run_id}/authorize", json={"authorizeModelCost": True})
    assert response.status_code == 409 and not fake.calls
    payload["requirements"]["dataHandling"] = "redact"
    state = authorize_execute(client, prepare(client, payload))
    assert state["status"] == "completed"
    sent = json.loads(fake.calls[-1]["input_text"])
    assert sent["input"]["password"] == "[REDACTED]"
    assert sent["input"]["contact"] == "[REDACTED_EMAIL]"
    assert "do-not-send-this" not in json.dumps(fake.calls)


def test_new_requests_reject_boolean_coercion_for_paid_authorization(client, monkeypatch):
    provider(monkeypatch)
    run_id = prepare(client, request("policy_review"))
    for value in ("true", "yes", 1):
        assert client.post(f"/api/runs/{run_id}/authorize", json={"authorizeModelCost": value}).status_code == 422


def test_comparison_get_is_read_only_for_optimization(client, monkeypatch):
    fake, _ = provider(monkeypatch)
    run_id = prepare(client)
    authorize_execute(client, run_id)
    before = client.get(f"/api/runs/{run_id}/comparison")
    assert before.status_code == 200 and before.json()["label"] == "Comparison not run"
    assert client.get(f"/api/runs/{run_id}/comparison").json() == before.json()
    assert not fake.calls


@pytest.mark.parametrize("cost", ["NaN", "Infinity", "-Infinity", "-0.01"])
def test_nonfinite_or_negative_authorized_cost_rejected(client, cost):
    body = json.dumps(request()).replace('"maxModelSpendUsd": 0.05', f'"maxModelSpendUsd": {cost}')
    response = client.post("/api/runs", content=body, headers={"Content-Type": "application/json"})
    assert response.status_code == 422


def test_unknown_goal_duplicate_ids_and_unsupported_schema_rejected(client):
    payload = request()
    payload["requirements"]["optimizationGoal"] = "ignore_quality"
    assert client.post("/api/runs", json=payload).status_code == 422
    payload = request()
    payload["requirements"]["outputContract"] = {"type": "object", "anyOf": []}
    run_id = prepare(client, payload)
    assert client.post(f"/api/runs/{run_id}/authorize", json={}).status_code == 409
    payload = request()
    payload["inputSource"] = "upload"
    rows = sample_requests("customer_assistance")
    rows[1]["id"] = rows[0]["id"]
    payload["inputs"] = {"workflowDescription": "Duplicate request IDs", "representativeRequests": rows}
    assert client.post("/api/runs", json=payload).status_code == 422
    uploaded = client.post("/api/optimization/uploads", data={"role": "test_inputs"},
                           files=[("files", ("requests.json", json.dumps(sample_requests("customer_assistance")).encode()))])
    artifact = uploaded.json()["files"][0]["fileId"]
    payload["inputs"] = {"workflowDescription": "Duplicate artifact IDs", "testInputIds": [artifact, artifact]}
    assert client.post("/api/runs", json=payload).status_code == 422


def test_local_outcomes_are_computed_and_not_copied_from_expected_references(client):
    rows = sample_requests("customer_assistance")
    rows[0]["expectedOutput"]["decision"] = "incorrect-reference-value"
    payload = request()
    payload["inputSource"] = "upload"
    payload["inputs"] = {"workflowDescription": "Independent acceptance reference", "representativeRequests": rows}
    state = authorize_execute(client, prepare(client, payload))
    assert state["status"] == "failed"
    assert state["proof"]["outcomes"][0]["output"]["decision"] == "30 days"
    assert state["proof"]["outcomes"][0]["passed"] is False


def test_changed_context_prevents_reuse_even_when_expected_answer_matches(client):
    rows = sample_requests("customer_assistance")
    rows[2]["context"] = copy.deepcopy(rows[2]["context"])
    rows[2]["context"][0]["text"] = "The same 30-day return policy now has a revised source annotation."
    payload = request()
    payload["inputSource"] = "upload"
    payload["inputs"] = {"workflowDescription": "Context-bound reuse", "representativeRequests": rows}
    state = authorize_execute(client, prepare(client, payload))
    assert state["proof"]["verification"]["passed"]
    assert state["proof"]["cost"]["reuseOperations"] == 1
    assert state["proof"]["cost"]["localOperations"] == 3


def test_refresh_safeguards_repins_only_unapproved_candidate(client, monkeypatch):
    run_id = prepare(client, request("policy_review"))
    before = client.get(f"/api/runs/{run_id}").json()
    assert any(not check["passed"] for check in before["protectionChecks"])
    fake, _ = provider(monkeypatch)
    monkeypatch.setattr(settings, "model_mode", "foundry")
    monkeypatch.setattr(settings, "foundry_base_url", "https://configured-server.example/openai/v1/")
    stale = client.post(f"/api/runs/{run_id}/authorize", json={"authorizeModelCost": True})
    assert stale.status_code == 409
    refreshed = client.post(f"/api/runs/{run_id}/refresh-safeguards", json={})
    assert refreshed.status_code == 200, refreshed.text
    state = refreshed.json()
    assert state["status"] == "optimized" and state["planRevision"] == 2
    assert state["inputManifestHash"] == before["inputManifestHash"]
    assert state["priceTableVersion"] != before["priceTableVersion"]
    assert all(check["passed"] for check in state["protectionChecks"])
    assert not fake.calls
    authorized = client.post(f"/api/runs/{run_id}/authorize", json={"authorizeModelCost": True})
    assert authorized.status_code == 200
    assert client.post(f"/api/runs/{run_id}/refresh-safeguards", json={}).status_code == 409
    assert not fake.calls
    client.post(f"/api/runs/{run_id}/execute", json={})
    completed = wait(client, run_id)
    assert completed["proof"]["verification"]["passed"]
    assert client.post(f"/api/runs/{run_id}/refresh-safeguards", json={}).status_code == 409


def test_refresh_safeguards_does_not_accept_changed_manifest(client):
    run_id = prepare(client)
    run = store.require(run_id)
    run["inputManifest"][0]["sha256"] = "tampered"
    store.save(run)
    assert client.post(f"/api/runs/{run_id}/refresh-safeguards", json={}).status_code == 409
