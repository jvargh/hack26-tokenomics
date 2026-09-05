"""Paired baseline run: what the naive all-AI implementation actually costs.

The projection in `tokenomics.py` states what the same text *would* cost on the
advanced model. It cannot claim a saving, because nothing verified that the model
route would reach an acceptable answer.

This module closes that gap. It runs the comparison people actually build — hand the
whole document and policy to the advanced model and ask for the findings — then puts
the result through the *same* verification the governed route passed. Only when both
paths clear the same checks is a saving asserted.

Requires a model deployment. Without one it says so and claims nothing.
"""

from __future__ import annotations

import json
import time

from .comparison import (
    CITATION_REQUIREMENT,
    MAX_OUTPUT_TOKENS,
    OUTPUT_SCHEMA_VERSION,
    STATUS_BASELINE_FAILED,
    STATUS_ELIGIBLE_SAVING,
    STATUS_INVALID_COMPARISON,
    STATUS_NO_SAVING,
    STATUS_UNAVAILABLE,
    contract,
    matches,
    test_set_id,
)
from .modeladapter import ModelUnavailable, model_adapter, model_available
from .pricing import price_source
from .workflows._util import MONEY_PATTERN

BASELINE_SYSTEM = (
    "You are reviewing supplier charges against a policy. Reply with JSON only, shaped as "
    '{"findings":[{"document":"...","line":"...","amount_usd":0,"finding":"...",'
    '"policy_citation":"...","recommendation":"reject|request_evidence"}]}. '
    f"{CITATION_REQUIREMENT} Do not invent amounts, line numbers, or sections. "
    f"(schema {OUTPUT_SCHEMA_VERSION})"
)


def _amount(value: str) -> float:
    return float(value.replace(",", "").lstrip("$").strip())


def evaluate_saving(
    *,
    baseline_quality_passed: bool,
    governed_quality_passed: bool,
    governed_decision_complete: bool,
    governed_unresolved_items: int,
    contract_matched: bool | None,
    price_configured: bool,
    baseline_cost_usd: float,
    governed_cost_usd: float,
) -> dict:
    """The pure saving-eligibility rule.

    Isolated from any model call so every failure branch, and the boundary where a
    baseline that costs the same or less than the governed route stops being a
    saving, can be unit tested directly.
    """
    if not baseline_quality_passed:
        return {
            "claimable": False,
            "saving_usd": None,
            "status": STATUS_INVALID_COMPARISON,
            "blocked_reason": (
                "The all-AI route did not pass the same verification, so its lower or higher cost "
                "is not comparable. No saving is claimed."
            ),
        }
    if not governed_quality_passed:
        return {
            "claimable": False,
            "saving_usd": None,
            "status": STATUS_INVALID_COMPARISON,
            "blocked_reason": "The governed route did not pass verification, so no saving is claimed.",
        }
    if not governed_decision_complete:
        # Cheaper because it stopped early is not cheaper for the same outcome.
        return {
            "claimable": False,
            "saving_usd": None,
            "status": STATUS_INVALID_COMPARISON,
            "blocked_reason": (
                f"The governed route left {governed_unresolved_items} item(s) unresolved, so it did "
                "not produce the same completed decision. No saving is claimed."
            ),
        }
    if contract_matched is False:
        return {
            "claimable": False,
            "saving_usd": None,
            "status": STATUS_INVALID_COMPARISON,
            "blocked_reason": (
                "The two routes did not run under the same prompt version, output schema, output "
                "ceiling, and test set, so the comparison is not valid."
            ),
        }
    if not price_configured:
        return {
            "claimable": False,
            "saving_usd": None,
            "status": STATUS_INVALID_COMPARISON,
            "blocked_reason": "No price is configured for the advanced deployment.",
        }

    saving = round(baseline_cost_usd - governed_cost_usd, 6)
    if saving <= 0:
        # A valid, equal-quality comparison that simply did not cost more on the
        # all-AI path is not a failure of the comparison, only the absence of a saving.
        return {
            "claimable": False,
            "saving_usd": saving,
            "status": STATUS_NO_SAVING,
            "blocked_reason": (
                "The measured all-AI baseline did not cost more than the governed route, so no "
                "saving is verified."
            ),
        }
    return {
        "claimable": True,
        "saving_usd": saving,
        "status": STATUS_ELIGIBLE_SAVING,
        "blocked_reason": None,
    }


async def run_baseline(uploads: list, governed_proof: dict) -> dict:
    """Executes the all-AI comparison path and verifies it the same way.

    Returns a block describing both paths. Every number is measured: tokens and cost
    come from the model response, and the verification is the same grounding and
    amount check applied to the governed route.
    """
    governed_cost = governed_proof["economics"]["total_calculated_cost_usd"]
    governed_quality = governed_proof["outcome"]["quality_passed"]
    governed_findings = len(governed_proof.get("findings", []))

    if not model_available():
        return {
            "available": False,
            "status": STATUS_UNAVAILABLE,
            "reason": (
                "A paired baseline needs a model deployment. Set TOKENOS_MODEL_MODE=foundry "
                "and the deployment variables, then run the comparison to turn the projection "
                "into a verified saving."
            ),
            "saving_claimable": False,
            "governed": {
                "cost_usd": governed_cost,
                "quality_passed": governed_quality,
                "findings": governed_findings,
                "model_calls": governed_proof["usage"]["model_calls"],
                "tokens": governed_proof["usage"]["input_tokens"] + governed_proof["usage"]["output_tokens"],
            },
            "baseline": None,
        }

    source_text = "\n\n".join(
        f"### {upload.name} ({upload.role})\n{upload.extracted_text}" for upload in uploads
    )
    started = time.perf_counter()
    try:
        result = await model_adapter.generate(
            route="advanced_ai",
            system=BASELINE_SYSTEM,
            input_text=source_text,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            json_response=True,
        )
    except ModelUnavailable as error:
        return {
            "available": False,
            "status": STATUS_BASELINE_FAILED,
            "reason": f"The advanced route failed: {error}",
            "saving_claimable": False,
            "governed": {
                "cost_usd": governed_cost,
                "quality_passed": governed_quality,
                "findings": governed_findings,
                "model_calls": governed_proof["usage"]["model_calls"],
                "tokens": governed_proof["usage"]["input_tokens"] + governed_proof["usage"]["output_tokens"],
            },
            "baseline": None,
        }

    duration_ms = int((time.perf_counter() - started) * 1000)
    produced = (result.parsed or {}).get("findings", []) if result.parsed else []

    # The same grounding and amount checks the governed route had to pass.
    document_names = {upload.name for upload in uploads}
    amounts_in_source = {round(_amount(match), 2) for match in MONEY_PATTERN.findall(source_text)}
    grounded, amounts_ok, cited = 0, 0, 0
    for item in produced:
        if str(item.get("document", "")) in document_names:
            grounded += 1
        value = item.get("amount_usd")
        if value is None or round(float(value), 2) in amounts_in_source:
            amounts_ok += 1
        if str(item.get("policy_citation", "")).strip():
            cited += 1

    total = len(produced)
    checks = {
        "findings_grounded": total > 0 and grounded == total,
        "amounts_verified": total > 0 and amounts_ok == total,
        "citations_present": total > 0 and cited == total,
    }
    baseline_quality_passed = all(checks.values())

    baseline_cost = result.calculated_cost_usd
    governed_contract = governed_proof.get("comparison_contract")
    run_contract = contract(test_set_id(uploads))
    contract_matched = matches(governed_contract, run_contract) if governed_contract else None

    evaluation = evaluate_saving(
        baseline_quality_passed=baseline_quality_passed,
        governed_quality_passed=governed_quality,
        governed_decision_complete=governed_proof["outcome"].get("decision_complete", True),
        governed_unresolved_items=governed_proof["outcome"].get("unresolved_items", 0),
        contract_matched=contract_matched,
        price_configured=result.price_configured,
        baseline_cost_usd=baseline_cost,
        governed_cost_usd=governed_cost,
    )
    saving = evaluation["saving_usd"]
    claimable = evaluation["claimable"]
    blocked = evaluation["blocked_reason"]

    return {
        "available": True,
        "status": evaluation["status"],
        "saving_claimable": claimable,
        "saving_usd": saving,
        "saving_per_1k_runs_usd": (round(saving * 1000, 2) if saving is not None else None),
        "saving_blocked_reason": blocked,
        "equal_quality": baseline_quality_passed and governed_quality,
        "governed": {
            "cost_usd": governed_cost,
            "quality_passed": governed_quality,
            "findings": governed_findings,
            "model_calls": governed_proof["usage"]["model_calls"],
            "tokens": governed_proof["usage"]["input_tokens"] + governed_proof["usage"]["output_tokens"],
        },
        "baseline": {
            "cost_usd": baseline_cost,
            "quality_passed": baseline_quality_passed,
            "findings": total,
            "model_calls": 1,
            "tokens": result.input_tokens + result.output_tokens,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "cached_input_tokens": result.cached_input_tokens,
            "reasoning_tokens": result.reasoning_tokens,
            "duration_ms": duration_ms,
            "deployment": result.deployment,
            "price_configured": result.price_configured,
            "checks": checks,
            "grounded": f"{grounded} of {total}",
            "amounts_verified": f"{amounts_ok} of {total}",
            "citations_present": f"{cited} of {total}",
        },
        "price_effective_date": (price_source(result.deployment) or {}).get("effective_date"),
        "comparison_contract": run_contract,
        "contract_matched": contract_matched,
        "model_version": result.model_version,
        "note": (
            "Both paths were executed under the same prompt version, output schema, output "
            "ceiling, and test set, and put through the same grounding, amount, and citation "
            "checks. A saving is stated only when both passed and the governed decision was "
            "complete."
        ),
    }
