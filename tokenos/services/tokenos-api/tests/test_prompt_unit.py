from __future__ import annotations

from decimal import Decimal

import pytest

from tokenos_api.optimization import prompts
from tokenos_api.optimization.engine import cost_for_usage
from tokenos_api.optimization.quality import gate_blockers, verify_output


def test_token_estimate_is_deterministic_and_clearly_an_estimate():
    text = "word " * 40
    assert prompts.estimate_tokens(text) == prompts.estimate_tokens(text)
    assert prompts.estimate_tokens(text) >= 40
    assert "ESTIMATE" in (prompts.estimate_tokens.__doc__ or "")


def test_context_decision_engine_allows_minimizes_and_redacts():
    artifacts = [
        ({"fileId": "file_relevant", "filename": "policy.md"}, b"Refund policy: damaged items reported within 14 days qualify for refund."),
        ({"fileId": "file_noise", "filename": "notes.txt"}, b"Office snacks and parking notes are unrelated."),
        ({"fileId": "file_secret", "filename": "secret.txt"}, b"refund escalation api_key=secret-123 should not be sent"),
    ]
    decisions, allowed = prompts.decide_context({"userPrompt": "Can damaged items get a refund?", "desiredOutcome": "refund decision"}, artifacts)
    by_source = {item["sourceId"]: item for item in decisions}
    assert by_source["file_relevant"]["decision"] == "allow"
    assert by_source["file_noise"]["decision"] == "minimize"
    assert by_source["file_secret"]["decision"] == "redact"
    assert "secret-123" not in str(allowed)


def test_output_contract_varies_by_prompt_format():
    text_contract = prompts.output_contract("markdown", 400)
    json_contract = prompts.output_contract("json", 400)
    assert text_contract["required"] == ["response"]
    assert json_contract["required"] == ["decision"]
    assert "response" in text_contract["properties"]
    assert "decision" in json_contract["properties"]


def test_cache_eligibility_and_route_selection():
    long_context = [{"id": "ctx", "text": "stable policy prefix " * 100}]
    status, reason = prompts.cache_eligibility("Stable system", long_context, "")
    assert status == "eligible" and "provider evidence" in reason
    alias, _ = prompts.route_alias({"currentModel": "recommend", "outputFormat": "json", "userPrompt": "classify", "desiredOutcome": "decision"}, {}, [])
    assert alias == "tokenos-efficient"
    alias, _ = prompts.route_alias({"currentModel": "advanced", "outputFormat": "code_patch", "userPrompt": "security patch", "desiredOutcome": "fix"}, {}, [])
    assert alias == "tokenos-advanced"


def test_prompt_quality_blockers_never_auto_pass():
    requirements = {"qualityRequirements": ["same_answer_quality"], "outputContract": prompts.output_contract("text", 500), "maxOutputCharacters": 500}
    item = {"id": "prompt-1", "taskType": "interpretation", "context": [{"id": "ctx", "text": "x"}], "promptMode": True}
    assert "expectedResult" in " ".join(gate_blockers([item], requirements))
    item["_expectedResult"] = "approved"
    assert not gate_blockers([item], requirements)
    checks = verify_output(item, {"response": "approved"}, requirements, 1, False)
    assert all(check["passed"] for check in checks)


def test_required_tests_blocks_for_prompt_mode():
    requirements = {"qualityRequirements": ["required_tests"], "outputContract": prompts.output_contract("text", 500), "maxOutputCharacters": 500}
    item = {"id": "prompt-1", "taskType": "interpretation", "context": [], "promptMode": True}
    assert "unsupported for a single prompt" in " ".join(gate_blockers([item], requirements))


def test_cost_calculation_uses_precise_usage_and_cached_price():
    table = {"deployment": {"input_per_1m_usd": "1", "output_per_1m_usd": "3", "cached_input_per_1m_usd": "0.25"}}
    assert cost_for_usage(table, "deployment", 1000, 100, 400) == Decimal("0.001")
    with pytest.raises(ValueError):
        cost_for_usage(table, "deployment", 100, 10, 101)


def test_provider_prompt_payload_excludes_expected_output_and_redacts_baseline():
    contract = prompts.output_contract("json", 500)
    item = {"id": "prompt-1", "taskType": "interpretation", "input": "safe", "context": [], "promptMode": True,
            "expectedOutput": {"decision": "yes"}, "_outputFormat": "json"}
    _, governed = prompts.provider_payload_for_prompt(item, {"outputContract": contract, "maxOutputCharacters": 500})
    assert "expectedOutput" not in governed
    _, baseline = prompts.provider_payload_for_prompt(
        item, {"outputContract": contract, "maxOutputCharacters": 500}, baseline=True,
        baseline_package={"userPrompt": "authorization: Bearer secret-token", "context": []},
    )
    assert "secret-token" not in baseline and "[REDACTED" in baseline
