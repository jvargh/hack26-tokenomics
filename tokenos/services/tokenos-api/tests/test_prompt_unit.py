from __future__ import annotations

from decimal import Decimal

import pytest

from tokenos_api.optimization import prompts
from tokenos_api.optimization.engine import cost_for_usage
from tokenos_api.optimization.fixtures import PROMPT_EXAMPLE_REQUIREMENTS
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


def test_output_contract_requires_a_verifiable_decision_when_an_expected_result_is_set():
    graded = prompts.output_contract("markdown", 400, None, True)
    assert graded["required"] == ["response", "decision"]
    assert "decision" in graded["properties"]


def test_prose_expected_result_is_blocked_before_any_model_spend():
    """A prose expectation can never be matched exactly, so TokenOS must refuse to run it."""
    requirements = {"qualityRequirements": ["same_answer_quality"],
                    "outputContract": prompts.output_contract("text", 500, None, True), "maxOutputCharacters": 500}
    item = {"id": "prompt-1", "taskType": "interpretation", "promptMode": True,
            "context": [{"id": "ctx", "text": "Damaged items qualify for replacement or refund."}],
            "_expectedResult": "The customer is eligible for replacement or refund under the damaged-on-arrival policy."}
    assert "free prose" in " ".join(gate_blockers([item], requirements))

    item["_expectedResult"] = "replacement_or_refund"
    assert not gate_blockers([item], requirements)

    item["_expectedResult"] = "Damaged items qualify for replacement or refund."
    assert not gate_blockers([item], requirements), "text quoted from approved context is reproducible"


def test_outcome_acceptance_grades_the_decision_not_the_prose_wording():
    """A real model words its reply freely; only the decision value is exact-matched."""
    requirements = {"qualityRequirements": ["same_answer_quality"],
                    "outputContract": prompts.output_contract("markdown", 500, None, True), "maxOutputCharacters": 500}
    item = {"id": "prompt-1", "taskType": "interpretation", "promptMode": True,
            "context": [{"id": "ctx", "text": "policy"}], "_expectedResult": "replacement_or_refund"}

    accepted = verify_output(item, {"response": "Thanks for getting in touch. Your mixer arrived damaged, so you may "
                                                "choose a replacement or a refund under policy DOA-14.",
                                    "decision": "replacement_or_refund", "citations": ["ctx"]}, requirements, 1, False)
    assert all(check["passed"] for check in accepted), [check for check in accepted if not check["passed"]]

    wrong = verify_output(item, {"response": "Your mixer arrived damaged, so you may choose a replacement or a refund.",
                                 "decision": "not_eligible", "citations": ["ctx"]}, requirements, 1, False)
    by_id = {check["id"]: check["passed"] for check in wrong}
    assert by_id["outcome_acceptance"] is False and by_id["same_answer_quality"] is False, "a wrong decision is never accepted"


def test_bundled_prompt_samples_can_actually_be_verified():
    """Every shipped sample must be able to pass, or it spends real money to fail."""
    from tokenos_api.optimization.fixtures import PROMPT_FIXTURES

    for example_id, fixture in PROMPT_FIXTURES.items():
        inputs = fixture["inputs"]
        artifacts = [({"fileId": f"file_{index}", "filename": item["filename"]}, item["content"].encode())
                     for index, item in enumerate(fixture["contextArtifacts"], 1)]
        compiled = prompts.build_prompt_plan(inputs, dict(PROMPT_EXAMPLE_REQUIREMENTS, maxOutputCharacters=2000), artifacts)
        requirements = dict(PROMPT_EXAMPLE_REQUIREMENTS, maxOutputCharacters=2000,
                            outputContract=compiled["plan"]["candidate"]["outputContract"])
        assert not gate_blockers([compiled["request"]], requirements), example_id
        # The model can only emit the graded value if the approved context defines it.
        approved = " ".join(source["text"] for source in compiled["request"]["context"])
        assert inputs["expectedResult"] in approved, example_id


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
