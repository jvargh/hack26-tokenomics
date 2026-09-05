from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tokenos_api.optimization.engine import comparison, cost_for_usage
from tokenos_api.optimization.imports import normalize_telemetry
from tokenos_api.optimization.quality import run_arithmetic_tests


def test_precise_cached_and_reasoning_pricing():
    table = {"test": {"input_per_1m_usd": "0.15", "output_per_1m_usd": "0.6", "cached_input_per_1m_usd": "0.075"}}
    assert cost_for_usage(table, "test", 1000, 100, 800) == Decimal("0.00015")
    with pytest.raises(ValueError):
        cost_for_usage(table, "test", 1000, 100, 1001)
    with pytest.raises(ValueError):
        cost_for_usage({}, "test", 1000, 100)
    with pytest.raises(ValueError, match="cached"):
        cost_for_usage({"test": {"input_per_1m_usd": 1, "output_per_1m_usd": 2}}, "test", 100, 20, 50)


@pytest.mark.parametrize("values", [{"inputTokens": -1}, {"inputTokens": 1.5}, {"latencyMs": float("nan")},
                                    {"inputTokens": 10, "cachedInputTokens": 20},
                                    {"outputTokens": 2, "reasoningTokens": 3}])
def test_invalid_telemetry_not_coerced_to_measured_usage(values):
    with pytest.raises(ValueError):
        normalize_telemetry([values])


def test_arithmetic_adapter_executes_tests_without_exec():
    item = {"input": {"expression": "price + quantity", "tests": [{"args": {"price": 5, "quantity": 3}, "expected": 15}]}}
    result = run_arithmetic_tests(item)
    assert result == [{"testId": "arithmetic-1", "actual": 8, "expected": 15, "passed": False}]
    item["input"]["expression"] = "__import__('os').system('anything')"
    with pytest.raises(ValueError):
        run_arithmetic_tests(item)


def execution(cost):
    return {"completed": True, "qualityPassed": True, "usageComplete": True,
            "contract": {"inputManifestHash": "same", "verifier": "same", "maxOutputTokens": 500},
            "modelUsage": [{"costUsdExact": str(cost), "providerRequestId": "provider"}],
            "outcomes": [{"passed": True}], "operations": [], "qualityGates": [], "modelCalls": 1, "error": None}


@pytest.mark.parametrize("governed_cost,baseline_cost,eligible,label", [
    ("0.001", "0.002", True, "Verified saving"),
    ("0.001", "0.001", False, "No cost saving verified"),
    ("0.002", "0.001", False, "No cost saving verified"),
])
def test_strict_saving_gate(governed_cost, baseline_cost, eligible, label):
    result = comparison(execution(governed_cost), execution(baseline_cost))
    assert result["eligible"] is eligible and result["label"] == label
    assert (result["verifiedSavingUsd"] is not None) is eligible


@pytest.mark.parametrize("key,value", [("qualityPassed", False), ("completed", False), ("usageComplete", False),
                                       ("contract", {"inputManifestHash": "changed"})])
def test_invalid_baseline_never_claims_saving(key, value):
    baseline = execution("1.0")
    baseline[key] = value
    assert comparison(execution("0.001"), baseline)["label"] == "No valid comparison"


def test_unregistered_policy_text_does_not_use_a_registered_rule():
    from tokenos_api.optimization.quality import local_result
    output, _ = local_result({"taskType": "policy", "input": {"chargeType": "standard", "purchaseOrder": "PO-1"},
                              "context": [{"id": "policy#standard", "text": "Standard freight is prohibited."}]})
    assert output is None


def test_strict_provider_mode_rejects_missing_usage_without_retries():
    import asyncio
    from types import SimpleNamespace
    from tokenos_api.modeladapter import FoundryModelAdapter, ModelUnavailable
    calls = []

    class Client:
        def __init__(self):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

        def with_options(self, **kwargs):
            assert kwargs == {"max_retries": 0}
            return self

        async def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(usage=None, choices=[SimpleNamespace(message=SimpleNamespace(content='{"decision":"anything"}'))])

    adapter = FoundryModelAdapter()
    adapter._client = Client()
    with pytest.raises(ModelUnavailable, match="usage"):
        asyncio.run(adapter.generate(route="efficient_ai", system="contract", input_text="request",
                                     strict_usage=True, single_attempt=True))
    assert len(calls) == 1


def test_common_output_length_gate_applies_to_actual_local_and_model_outputs():
    from tokenos_api.optimization.quality import verify_output
    from tokenos_api.optimization.schemas import Requirements
    requirements = Requirements(qualityRequirements=["same_answer_quality"], optimizationGoal="cost_per_accepted_outcome",
                                maxOutputCharacters=100).model_dump()
    item = {"id": "test", "expectedOutput": {"decision": "accepted"}, "context": []}
    output = {"decision": "accepted", "diagnosis": "long" * 100}
    gates = verify_output(item, output, requirements, 0, False)
    assert any(gate["id"] == "output_length" and not gate["passed"] for gate in gates)


@pytest.mark.parametrize("invalid", [-1, 1.5, float("nan"), float("inf"), True])
def test_strict_adapter_never_coerces_invalid_provider_usage(invalid):
    import asyncio
    from types import SimpleNamespace
    from tokenos_api.modeladapter import FoundryModelAdapter, ModelUnavailable

    async def create(**kwargs):
        return SimpleNamespace(usage=SimpleNamespace(prompt_tokens=invalid, completion_tokens=1))

    adapter = FoundryModelAdapter()
    adapter._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    with pytest.raises(ModelUnavailable, match="invalid token usage"):
        asyncio.run(adapter.generate(route="efficient_ai", system="contract", input_text="request",
                                     strict_usage=True, single_attempt=True))


def test_imported_distribution_never_exposes_unregistered_deployment_names():
    import json
    from tokenos_api.optimization.engine import _current_route
    telemetry = normalize_telemetry([{"deployment": name} for name in ("private-one", "private-two", "private-one")])
    route = _current_route({"_telemetry": telemetry, "_requests": []}, {})
    assert route["modelDistribution"] == {"imported-model-1": 2, "imported-model-2": 1}
    assert "private-one" not in json.dumps(route) and "private-two" not in json.dumps(route)
