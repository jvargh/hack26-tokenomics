"""Unit tests for `baseline.evaluate_saving`, the pure saving-eligibility rule.

These are isolated from any model call so every failure branch — including the
boundary where a baseline that costs the same or less than the governed route
stops being a saving — is testable without live Foundry credentials.

Run: .\\.venv\\Scripts\\python.exe -m pytest tests/test_savings_eligibility.py -v
"""

from __future__ import annotations

from tokenos_api.baseline import evaluate_saving
from tokenos_api.comparison import (
    STATUS_ELIGIBLE_SAVING,
    STATUS_INVALID_COMPARISON,
    STATUS_NO_SAVING,
)

BASE_KWARGS = dict(
    baseline_quality_passed=True,
    governed_quality_passed=True,
    governed_decision_complete=True,
    governed_unresolved_items=0,
    contract_matched=True,
    price_configured=True,
    baseline_cost_usd=0.01,
    governed_cost_usd=0.001,
)


def test_eligible_saving_when_baseline_costs_more_and_both_pass():
    result = evaluate_saving(**BASE_KWARGS)

    assert result["claimable"] is True
    assert result["status"] == STATUS_ELIGIBLE_SAVING
    assert result["saving_usd"] == 0.009
    assert result["blocked_reason"] is None


def test_no_saving_when_baseline_costs_the_same():
    kwargs = dict(BASE_KWARGS, baseline_cost_usd=0.001, governed_cost_usd=0.001)

    result = evaluate_saving(**kwargs)

    assert result["claimable"] is False
    assert result["status"] == STATUS_NO_SAVING
    assert result["saving_usd"] == 0.0


def test_no_saving_when_baseline_costs_less():
    kwargs = dict(BASE_KWARGS, baseline_cost_usd=0.0005, governed_cost_usd=0.001)

    result = evaluate_saving(**kwargs)

    assert result["claimable"] is False
    assert result["status"] == STATUS_NO_SAVING
    assert result["saving_usd"] < 0


def test_invalid_comparison_when_baseline_quality_failed():
    kwargs = dict(BASE_KWARGS, baseline_quality_passed=False)

    result = evaluate_saving(**kwargs)

    assert result["claimable"] is False
    assert result["status"] == STATUS_INVALID_COMPARISON
    assert result["saving_usd"] is None
    assert "not comparable" in result["blocked_reason"]


def test_invalid_comparison_when_governed_quality_failed():
    kwargs = dict(BASE_KWARGS, governed_quality_passed=False)

    result = evaluate_saving(**kwargs)

    assert result["claimable"] is False
    assert result["status"] == STATUS_INVALID_COMPARISON
    assert "governed route did not pass verification" in result["blocked_reason"]


def test_invalid_comparison_when_governed_decision_incomplete():
    kwargs = dict(BASE_KWARGS, governed_decision_complete=False, governed_unresolved_items=2)

    result = evaluate_saving(**kwargs)

    assert result["claimable"] is False
    assert result["status"] == STATUS_INVALID_COMPARISON
    assert "2 item(s) unresolved" in result["blocked_reason"]


def test_invalid_comparison_when_contract_mismatched():
    kwargs = dict(BASE_KWARGS, contract_matched=False)

    result = evaluate_saving(**kwargs)

    assert result["claimable"] is False
    assert result["status"] == STATUS_INVALID_COMPARISON
    assert "same prompt version" in result["blocked_reason"]


def test_contract_matched_none_does_not_block():
    """`None` means no governed contract was recorded yet (older proof); treated as
    unverifiable but not as a hard mismatch, matching the app.py call site which
    only receives `False` when a governed contract is actually present."""
    kwargs = dict(BASE_KWARGS, contract_matched=None)

    result = evaluate_saving(**kwargs)

    assert result["claimable"] is True


def test_invalid_comparison_when_price_not_configured():
    kwargs = dict(BASE_KWARGS, price_configured=False)

    result = evaluate_saving(**kwargs)

    assert result["claimable"] is False
    assert result["status"] == STATUS_INVALID_COMPARISON
    assert "No price is configured" in result["blocked_reason"]


def test_checks_are_evaluated_in_priority_order():
    """When multiple things are wrong, the first failure in the documented order is
    the one reported, so the message a judge sees is never ambiguous."""
    kwargs = dict(
        BASE_KWARGS,
        baseline_quality_passed=False,
        governed_quality_passed=False,
        price_configured=False,
    )

    result = evaluate_saving(**kwargs)

    assert "all-AI route did not pass" in result["blocked_reason"]
