from __future__ import annotations

import asyncio
import copy
import json
import shutil
import time
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tokenos_api.app import app
from tokenos_api.config import settings
from tokenos_api.modeladapter import ModelResult, ModelUnavailable
from tokenos_api.optimization import engine
from tokenos_api.optimization.store import store


@pytest.fixture
def client(monkeypatch):
    root = Path(__file__).resolve().parent.parent / ".prompt-test-runtime" / uuid.uuid4().hex
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


def prompt_payload(context_ids=None, **overrides):
    inputs = {
        "userPrompt": "Please answer using the damaged item refund policy and cite the source.",
        "systemInstructions": "Be concise and cite approved policy sections.",
        "conversationHistory": "Old unrelated loyalty discussion. " * 30,
        "contextFileIds": context_ids or [],
        "currentModel": "recommend",
        "outputFormat": "markdown",
        "desiredOutcome": "Explain whether a damaged item qualifies for refund.",
        "expectedResult": "replacement_or_refund",
    }
    inputs.update(overrides.pop("inputs", {}))
    requirements = {
        "qualityRequirements": ["same_answer_quality", "structured_output", "grounded_citations"],
        "optimizationGoal": "reduce_context",
        "maxModelSpendUsd": 0.05,
        "maxInputTokens": 8000,
        "maxOutputTokens": 200,
        "maxOutputCharacters": 1000,
    }
    requirements.update(overrides.pop("requirements", {}))
    payload = {"workflow": "workflow_optimization", "optimizationTarget": "single_prompt", "inputSource": "paste_prompt",
               "inputs": inputs, "requirements": requirements}
    payload.update(overrides)
    return payload


def upload_context(client, name="policy.md", content=None):
    content = content or b"Damaged on arrival policy: damaged items reported within 14 days qualify for replacement or refund."
    response = client.post("/api/optimization/context", files=[("files", (name, content))])
    assert response.status_code == 200, response.text
    return response.json()["files"][0]


def prepare(client, payload):
    created = client.post("/api/runs", json=payload)
    assert created.status_code == 200, created.text
    run_id = created.json()["runId"]
    assert client.post(f"/api/runs/{run_id}/analyze", json={}).status_code == 200
    optimized = client.post(f"/api/runs/{run_id}/optimize", json={"approvePlan": True})
    assert optimized.status_code == 200, optimized.text
    return run_id


def wait(client, run_id, baseline=False):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        state = client.get(f"/api/runs/{run_id}").json()
        if (state.get("baseline", {}).get("status") in {"completed", "failed"} if baseline else state["status"] in {"completed", "failed"}):
            return state
        time.sleep(0.01)
    raise AssertionError("run did not finish")


class PromptProvider:
    def __init__(self, expected, *, unavailable=False, baseline_costlier=True):
        self.expected = expected
        self.unavailable = unavailable
        self.baseline_costlier = baseline_costlier
        self.calls = []

    async def generate(self, **kwargs):
        self.calls.append(kwargs)
        assert kwargs["strict_usage"] is True and kwargs["single_attempt"] is True
        assert "expectedOutput" not in kwargs["input_text"]
        assert "tokenos-secret" not in kwargs["input_text"]
        if self.unavailable:
            raise ModelUnavailable("private outage diagnostic tokenos-secret")
        payload = json.loads(kwargs["input_text"])
        citations = [item["id"] for item in payload.get("context", [])] or ["file_context#1"]
        if "originalPromptPackage" in payload:
            context = payload["originalPromptPackage"].get("context", [])
            citations = [item["id"] for item in context] or citations
        # A real model words its prose freely and carries the graded value in `decision`.
        output = {"response": f"Here is the customer-safe reply for call {len(self.calls)}.",
                  "decision": self.expected, "citations": citations[:1]}
        input_tokens = 700 if "originalPromptPackage" in payload and self.baseline_costlier else 300
        if kwargs["route"] == "advanced_ai" and "originalPromptPackage" not in payload:
            input_tokens = 320
        await asyncio.sleep(0)
        return ModelResult(route=kwargs["route"], deployment=kwargs["deployment"], content=json.dumps(output),
                           input_tokens=input_tokens, output_tokens=50, duration_ms=3, calculated_cost_usd=999,
                           price_configured=True, request_id=f"provider-{len(self.calls)}", model_version="alias-version",
                           cached_input_tokens=100 if input_tokens > 400 else 0, reasoning_tokens=0)


def provider(monkeypatch, expected, **kwargs):
    fake = PromptProvider(expected, **kwargs)
    table = {"version": "prompt-prices-v1", **{deployment: {"input_per_1m_usd": 1, "output_per_1m_usd": 2,
                                                           "cached_input_per_1m_usd": 0.5}
                                            for deployment in engine._deployments().values()}}
    monkeypatch.setattr(engine, "load_price_table", lambda: copy.deepcopy(table))
    monkeypatch.setattr(engine, "model_available", lambda: True)
    monkeypatch.setattr(engine, "get_model_adapter", lambda: fake)
    return fake


@pytest.mark.parametrize("period", ["day", "week", "month", "year"])
def test_single_prompt_validation_and_volume_periods(client, period):
    context = upload_context(client)
    payload = prompt_payload([context["fileId"]], inputs={"recurringVolume": {"value": 3, "period": period}})
    assert client.post("/api/runs", json=payload).status_code == 200
    bad = prompt_payload([context["fileId"]], inputSource="upload")
    assert client.post("/api/runs", json=bad).status_code == 422
    mismatch = prompt_payload([context["fileId"]], mode="analyze")
    assert client.post("/api/runs", json=mismatch).status_code == 422
    too_low = prompt_payload([context["fileId"]], requirements={"maxInputTokens": 0})
    assert client.post("/api/runs", json=too_low).status_code == 422


def prompt_example_payload(example_id):
    return {
        "workflow": "workflow_optimization",
        "optimizationTarget": "single_prompt",
        "inputSource": "prompt_example",
        "inputs": {"promptExampleId": example_id},
        "requirements": {
            "qualityRequirements": ["same_answer_quality", "structured_output", "grounded_citations"],
            "optimizationGoal": "reduce_context",
            "maxModelSpendUsd": 0.05,
            "maxInputTokens": 8000,
            "maxOutputTokens": 200,
            "maxOutputCharacters": 1000,
        },
    }


def test_prompt_examples_endpoint_lists_both_examples(client):
    examples = client.get("/api/optimization/prompt-examples")
    assert examples.status_code == 200
    ids = {item["id"] for item in examples.json()["examples"]}
    assert {"verbose_support_reply", "repeated_policy_lookup"} <= ids


@pytest.mark.parametrize("example_id", ["verbose_support_reply", "repeated_policy_lookup"])
def test_prompt_example_catalog_supplies_all_plan_defaults(client, monkeypatch, example_id):
    from tokenos_api.optimization.fixtures import prompt_example
    from tokenos_api.optimization.schemas import DescribeRequest

    monkeypatch.setattr(engine, "get_model_adapter", lambda: pytest.fail("Loading example defaults must not call Foundry"))
    response = client.get("/api/optimization/prompt-examples")
    assert response.status_code == 200
    example = next(item for item in response.json()["examples"] if item["id"] == example_id)
    fixture = prompt_example(example_id)
    for key in ("systemInstructions", "conversationHistory", "desiredOutcome", "expectedResult", "currentModel", "outputFormat", "recurringVolume"):
        assert example[key] == fixture["inputs"][key]
        assert example[key]
    assert example["prompt"] == fixture["inputs"]["userPrompt"]
    assert example["contextFilenames"] == [item["filename"] for item in fixture["contextArtifacts"]]
    requirements = example["requirements"]
    assert set(requirements["qualityRequirements"]) == {
        "same_answer_quality", "grounded_citations", "structured_output", "latency_target",
    }
    assert requirements["latencyTargetMs"] > 0
    assert all(requirements[key] > 0 for key in ("maxModelSpendUsd", "maxInputTokens", "maxOutputTokens", "maxAdvancedCalls"))
    assert "humanApprovalGranted" not in requirements
    assert "authorizeModelCost" not in requirements
    inputs = {key: example[key] for key in (
        "systemInstructions", "conversationHistory", "desiredOutcome", "expectedResult",
        "currentModel", "outputFormat", "recurringVolume",
    )}
    inputs.update({"userPrompt": example["prompt"], "promptExampleId": example_id})
    payload = {
        "workflow": "workflow_optimization", "optimizationTarget": "single_prompt",
        "inputSource": "prompt_example", "inputs": inputs, "requirements": requirements,
    }
    DescribeRequest.model_validate(payload)
    created = client.post("/api/runs", json=payload)
    assert created.status_code == 200, created.text
    run_id = created.json()["runId"]
    plan = client.post(f"/api/runs/{run_id}/analyze", json={})
    assert plan.status_code == 200, plan.text
    assert plan.json()["status"] == "planned"
    assert plan.json()["proof"] is None
    assert plan.json()["requirements"] == store.require(run_id)["requirements"]
    assert not store.require(run_id).get("_authorization")
    assert len([item for item in plan.json()["inputManifest"] if item["role"] == "context"]) == example["contextArtifacts"]


def test_repeated_policy_lookup_example_completes_full_journey_locally(client, monkeypatch):
    monkeypatch.setattr(engine, "get_model_adapter", lambda: pytest.fail("Deterministic lookup prompt must not call Foundry"))
    run_id = prepare(client, prompt_example_payload("repeated_policy_lookup"))
    planned = client.get(f"/api/runs/{run_id}").json()
    assert planned["badges"] == ["Measured sample run"]
    assert planned["promptPlan"]["candidate"]["recommendedModelAlias"] == "local"
    assert planned["operations"][0]["route"] == "local"
    assert client.post(f"/api/runs/{run_id}/authorize", json={"authorizeModelCost": False}).status_code == 200
    client.post(f"/api/runs/{run_id}/execute", json={})
    state = wait(client, run_id)
    assert state["status"] == "completed"
    assert state["proof"]["verification"]["passed"]
    assert state["proof"]["cost"]["modelCalls"] == 0
    assert state["proof"]["cost"]["modelSpendUsd"] == 0
    events = [json.loads(line[6:]) for line in client.get(f"/api/runs/{run_id}/events").text.splitlines() if line.startswith("data: ")]
    assert any(event["type"] == "phase.completed" and event.get("phase") == "describe" for event in events)
    assert [event["phase"] for event in events if event["type"] == "phase.started"] == ["plan", "optimize", "protect", "run", "verify", "prove"]
    assert any(event["type"] == "prompt.analyzed" for event in events)
    assert any(event["type"] == "context.decided" for event in events)


def test_verbose_support_reply_example_remains_interpretation_and_blocks_without_foundry(client):
    run_id = prepare(client, prompt_example_payload("verbose_support_reply"))
    planned = client.get(f"/api/runs/{run_id}").json()
    assert planned["promptPlan"]["candidate"]["recommendedModelAlias"] == "tokenos-efficient"
    assert planned["operations"][0]["route"] == "tokenos-efficient"
    response = client.post(f"/api/runs/{run_id}/authorize", json={"authorizeModelCost": True})
    assert response.status_code == 409
    assert any(check["id"] == "provider" and not check["passed"] for check in response.json()["detail"]["protectionChecks"])


def test_pasted_prompt_with_exact_keyed_context_resolves_locally(client, monkeypatch):
    monkeypatch.setattr(engine, "get_model_adapter", lambda: pytest.fail("Pasted deterministic lookup must not call Foundry"))
    context = upload_context(
        client,
        "lookup.json",
        json.dumps({"sources": [{
            "id": "policy#damaged-refund",
            "key": "damaged item refund policy",
            "text": "Damaged item refund policy: damaged items qualify for refund after photo review.",
            "output": {"decision": "eligible", "citations": ["self"]},
        }]}).encode(),
    )
    payload = prompt_payload([context["fileId"]], inputs={
        "userPrompt": "Please check the damaged item refund policy for this order.",
        "outputFormat": "json",
        "desiredOutcome": "Return the decision for the damaged item refund policy.",
        "expectedResult": "eligible",
    })
    run_id = prepare(client, payload)
    assert client.get(f"/api/runs/{run_id}").json()["operations"][0]["route"] == "local"
    assert client.post(f"/api/runs/{run_id}/authorize", json={"authorizeModelCost": False}).status_code == 200
    client.post(f"/api/runs/{run_id}/execute", json={})
    state = wait(client, run_id)
    assert state["status"] == "completed"
    assert state["proof"]["outcomes"][0]["output"] == {"decision": "eligible", "citations": ["policy#damaged-refund"]}


def test_multiple_keyed_matches_do_not_get_marked_local(client):
    context = upload_context(
        client,
        "lookup.json",
        json.dumps({"sources": [
            {"id": "a", "key": "damaged item refund policy", "text": "Damaged item refund policy A", "output": {"decision": "eligible", "citations": ["self"]}},
            {"id": "b", "key": "damaged item refund policy", "text": "Damaged item refund policy B", "output": {"decision": "review", "citations": ["self"]}},
        ]}).encode(),
    )
    payload = prompt_payload([context["fileId"]], inputs={
        "userPrompt": "Please check the damaged item refund policy.",
        "outputFormat": "json",
        "desiredOutcome": "Return damaged item refund policy decision.",
        "expectedResult": "eligible",
    })
    run_id = prepare(client, payload)
    state = client.get(f"/api/runs/{run_id}").json()
    assert state["operations"][0]["route"] == "tokenos-efficient"



@pytest.mark.parametrize(("fmt", "required"), [("markdown", ["response", "decision"]), ("text", ["response", "decision"]),
                                               ("table", ["response", "decision"]), ("code_patch", ["response", "decision"]),
                                               ("json", ["decision"]), ("custom", ["decision"])])
def test_output_contract_per_format(client, fmt, required):
    context = upload_context(client)
    payload = prompt_payload([context["fileId"]], inputs={"outputFormat": fmt}, requirements={"qualityRequirements": ["structured_output"]})
    run_id = prepare(client, payload)
    state = client.get(f"/api/runs/{run_id}").json()
    assert state["promptPlan"]["candidate"]["outputContract"]["required"] == required


def test_prompt_plan_and_protect_do_not_call_provider_before_execute(client, monkeypatch):
    context = upload_context(client)
    fake = provider(monkeypatch, prompt_payload()["inputs"]["expectedResult"])
    run_id = prepare(client, prompt_payload([context["fileId"]]))
    state = client.get(f"/api/runs/{run_id}").json()
    assert state["optimizationTarget"] == "single_prompt"
    assert state["promptPlan"]["evidenceStatus"] == "estimated"
    assert not fake.calls
    blocked = client.post(f"/api/runs/{run_id}/authorize", json={"authorizeModelCost": False})
    assert blocked.status_code == 409 and not fake.calls
    authorized = client.post(f"/api/runs/{run_id}/authorize", json={"authorizeModelCost": True})
    assert authorized.status_code == 200 and not fake.calls
    client.post(f"/api/runs/{run_id}/execute", json={})
    state = wait(client, run_id)
    assert state["status"] == "completed"
    assert len(fake.calls) == 1
    assert state["proof"]["prompt"]["measuredUsage"]["inputTokens"] == 300


def test_escalated_prompt_reports_every_call_not_just_the_first(client, monkeypatch):
    """An escalating prompt makes several calls, and the proof must total them.

    Reporting only the first call understates what the prompt actually cost and
    contradicts the call count shown beside it.
    """
    context = upload_context(client)
    expected = prompt_payload()["inputs"]["expectedResult"]
    fake = provider(monkeypatch, expected)
    original = fake.generate

    async def fail_the_efficient_route(**kwargs):
        # The efficient answer misses the required citation, forcing escalation.
        fake.expected = expected if kwargs["route"] == "advanced_ai" else "Unrelated answer."
        return await original(**kwargs)

    monkeypatch.setattr(fake, "generate", fail_the_efficient_route)
    payload = prompt_payload([context["fileId"]],
                             requirements={"allowAdvancedEscalation": True, "maxAdvancedCalls": 1})
    run_id = prepare(client, payload)
    assert client.post(f"/api/runs/{run_id}/authorize", json={"authorizeModelCost": True}).status_code == 200
    client.post(f"/api/runs/{run_id}/execute", json={})
    state = wait(client, run_id)

    usage = state["proof"]["modelUsage"]
    assert len(usage) == 2, "This test is meaningless unless the prompt escalated."
    measured = state["proof"]["prompt"]["measuredUsage"]
    cost = state["proof"]["prompt"]["measuredCost"]

    assert measured["modelCalls"] == len(usage) == state["proof"]["cost"]["modelCalls"]
    for field in ("inputTokens", "outputTokens", "cachedInputTokens", "reasoningTokens", "totalTokens", "latencyMs"):
        assert measured[field] == sum(call[field] for call in usage), field
    assert measured["deploymentAliases"] == ["tokenos-efficient", "tokenos-advanced"]
    assert measured["deploymentAlias"] == "multiple"
    assert measured["providerRequestIds"] == [call["providerRequestId"] for call in usage]
    # The prompt cost is the run cost. A partial total would flatter TokenOS.
    assert cost["modelSpendUsd"] == pytest.approx(state["proof"]["cost"]["modelSpendUsd"])
    assert cost["modelSpendUsd"] == pytest.approx(sum(call["costUsd"] for call in usage))
    assert cost["modelSpendUsd"] > usage[0]["costUsd"]


def test_prompt_same_answer_without_expected_result_blocks_at_protect(client, monkeypatch):
    context = upload_context(client)
    fake = provider(monkeypatch, "unused")
    payload = prompt_payload([context["fileId"]], inputs={"expectedResult": None})
    run_id = prepare(client, payload)
    response = client.post(f"/api/runs/{run_id}/authorize", json={"authorizeModelCost": True})
    assert response.status_code == 409
    assert "expectedResult" in response.text
    assert not fake.calls


def test_prompt_required_tests_blocks_at_protect(client, monkeypatch):
    context = upload_context(client)
    fake = provider(monkeypatch, "unused")
    payload = prompt_payload([context["fileId"]], requirements={"qualityRequirements": ["required_tests"]})
    run_id = prepare(client, payload)
    response = client.post(f"/api/runs/{run_id}/authorize", json={"authorizeModelCost": True})
    assert response.status_code == 409
    assert "required_tests" in response.text
    assert not fake.calls


def test_prompt_baseline_uses_matched_contract_and_rejects_tamper(client, monkeypatch):
    context = upload_context(client)
    expected = prompt_payload()["inputs"]["expectedResult"]
    fake = provider(monkeypatch, expected)
    run_id = prepare(client, prompt_payload([context["fileId"]]))
    assert client.post(f"/api/runs/{run_id}/authorize", json={"authorizeModelCost": True}).status_code == 200
    client.post(f"/api/runs/{run_id}/execute", json={})
    state = wait(client, run_id)
    assert state["proof"]["verification"]["passed"]
    run = store.require(run_id)
    run["promptPlan"]["candidate"]["governedPrompt"] = "tampered"
    store.save(run)
    rejected = client.post(f"/api/runs/{run_id}/baseline", json={"acknowledgeModelCost": True, "baselineProfile": "all_ai_v1"})
    assert rejected.status_code == 409
    assert len(fake.calls) == 1


def test_prompt_baseline_success_records_verified_saving_and_reduction(client, monkeypatch):
    context = upload_context(client)
    expected = prompt_payload()["inputs"]["expectedResult"]
    fake = provider(monkeypatch, expected)
    run_id = prepare(client, prompt_payload([context["fileId"]]))
    assert client.post(f"/api/runs/{run_id}/authorize", json={"authorizeModelCost": True}).status_code == 200
    client.post(f"/api/runs/{run_id}/execute", json={})
    wait(client, run_id)
    start = client.post(f"/api/runs/{run_id}/baseline", json={"acknowledgeModelCost": True, "baselineProfile": "all_ai_v1"})
    assert start.status_code == 200, start.text
    state = wait(client, run_id, baseline=True)
    baseline = state["proof"]["baseline"]
    assert baseline["eligible"] and baseline["label"] == "Verified saving"
    assert state["proof"]["prompt"]["measuredInputTokenReduction"] == 400
    assert "original system instructions" in baseline["evidence"]
    assert len(fake.calls) == 2


def test_prompt_credentials_are_not_visible_or_sent(client, monkeypatch):
    context = upload_context(client, content=b"Damaged item refund policy. api_key=tokenos-secret")
    expected = prompt_payload()["inputs"]["expectedResult"]
    fake = provider(monkeypatch, expected)
    payload = prompt_payload([context["fileId"]], inputs={"userPrompt": "authorization: Bearer tokenos-secret. Damaged refund?"})
    run_id = prepare(client, payload)
    state = client.get(f"/api/runs/{run_id}").json()
    assert "tokenos-secret" not in json.dumps(state)
    assert any(change["id"] == "secret-redaction" for change in state["promptPlan"]["changes"])
    assert client.post(f"/api/runs/{run_id}/authorize", json={"authorizeModelCost": True}).status_code == 200
    client.post(f"/api/runs/{run_id}/execute", json={})
    final = wait(client, run_id)
    assert "tokenos-secret" not in json.dumps(final)
    assert "tokenos-secret" not in json.dumps(fake.calls)


def test_prompt_foundry_unavailable_blocks_without_fabricated_usage(client):
    context = upload_context(client)
    run_id = prepare(client, prompt_payload([context["fileId"]]))
    response = client.post(f"/api/runs/{run_id}/authorize", json={"authorizeModelCost": True})
    assert response.status_code == 409
    state = client.get(f"/api/runs/{run_id}").json()
    assert state["status"] == "optimized"
    assert state["proof"] is None
    assert any(check["id"] == "provider" and not check["passed"] for check in response.json()["detail"]["protectionChecks"])
