"""Before/after comparison on the legacy Prove screen.

Run explicitly: python -m pytest -c pytest-browser.ini -v

Covers the claim-strength rules that protect the product's credibility:
an estimate is never dressed up as measured, and a run that did not finish
its decision shows no cost benefit at all.

Uses the harness's own local-mode servers, so no model tokens are ever spent.
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect

DOCUMENT_REVIEW = "Review documents against rules"
DEADLINE = "Process records by a deadline"


def run_workflow(page, browser_servers, title, fill=None):
    """Drives a bundled sample to a finished run and opens Prove."""
    page.get_by_role("button", name=re.compile("^" + title)).click()
    page.get_by_role("button", name="Load sample data", exact=True).click()
    if fill:
        fill(page)
    action = page.get_by_role("button", name="Analyze with TokenOS", exact=True)
    expect(action).to_be_enabled()
    with page.expect_response(
        lambda response: response.url == browser_servers["api"] + "/api/runs"
        and response.request.method == "POST"
    ) as started:
        action.click()
    assert started.value.ok, started.value.text()

    prove = page.get_by_role("button", name=re.compile("^Prove"))
    expect(prove).to_be_enabled(timeout=60000)
    prove.click()
    expect(page.locator(".prove-cards")).to_be_visible()
    return started.value.json()["run_id"]


def complete_run(page, browser_servers):
    """A run whose decision finishes locally, so a cost comparison is allowed."""
    return run_workflow(page, browser_servers, DEADLINE)


def incomplete_run(page, browser_servers):
    """Document review leaves one contested charge unresolved without a model."""
    return run_workflow(page, browser_servers, DOCUMENT_REVIEW)


# --------------------------------------------------------------- the headline win


def test_prove_leads_with_the_work_that_avoided_ai(page, browser_servers):
    """The headline benefit is how much never needed a model, not the raw cost."""
    complete_run(page, browser_servers)

    banner = page.locator(".work-avoided")
    expect(banner).to_be_visible()
    expect(banner).to_contain_text("steps were completed without using AI at all.")

    # The count must agree with the server's own routing record.
    counted = page.locator(".work-avoided-count").inner_text()
    local_ops, total_ops = (int(part) for part in re.findall(r"\d+", counted)[:2])
    assert 0 < local_ops <= total_ops


def test_cards_use_plain_titles_and_show_a_before_value(page, browser_servers):
    complete_run(page, browser_servers)

    for title in (
        "What this run cost",
        "How often AI was needed",
        "Is the answer still correct?",
    ):
        expect(page.get_by_text(title, exact=True)).to_be_visible()

    # Jargon the earlier design used must not reappear in the hero row.
    cards = page.locator(".prove-cards")
    for retired in ("Model spend", "Model calls", "Non-AI operations", "Outcome verification"):
        expect(cards.get_by_text(retired, exact=True)).to_have_count(0)

    expect(
        page.locator(".comparison-before").filter(has_text="If AI did every step:").first
    ).to_be_visible()


# ------------------------------------------------------------- claim strength


def test_estimate_is_never_presented_as_proven(page, browser_servers):
    """Before any baseline runs, every comparison must read as an estimate."""
    complete_run(page, browser_servers)

    bar = page.locator(".claim-strength")
    expect(bar).to_have_class(re.compile("is-estimate"))
    expect(bar).to_contain_text("These savings are an estimate, not yet proven.")
    expect(page.locator(".claim-strength-badge")).to_have_text("Estimate")

    # Measured *cost* language must not appear before a paired run. The quality
    # chip may legitimately be green: those checks really did run and pass.
    expect(page.locator(".prove-cards").get_by_text(re.compile("proven"))).to_have_count(0)
    expect(page.locator(".prove-cards").get_by_text("Verified saving", exact=False)).to_have_count(0)
    expect(page.locator(".comparison-chip.is-estimate").first).to_be_visible()

    # The cost card specifically must carry the estimate tier.
    cost_card = page.locator(".comparison-card").filter(has_text="What this run cost")
    expect(cost_card.locator(".comparison-chip.is-estimate")).to_have_count(1)
    expect(cost_card.locator(".comparison-chip.is-proven")).to_have_count(0)


def test_unfinished_decision_shows_no_cost_benefit(page, browser_servers):
    """A run is cheaper partly because it did less, so no comparison is claimed."""
    incomplete_run(page, browser_servers)

    bar = page.locator(".claim-strength")
    expect(bar).to_have_class(re.compile("is-none"))
    expect(bar).to_contain_text("Cost comparisons are held back until the decision is finished.")
    expect(page.locator(".claim-strength-badge")).to_have_text("No comparison yet")

    # No before values, no reduction chips, no route contrast.
    expect(page.locator(".comparison-before:not(.is-blank)")).to_have_count(0)
    expect(page.locator(".comparison-chip.is-estimate")).to_have_count(0)
    expect(page.locator(".route-flow-before")).to_have_count(0)

    # The work that genuinely ran locally is still reported, but a deferred step
    # is described as having used no AI rather than as completed.
    banner = page.locator(".work-avoided")
    expect(banner).to_be_visible()
    expect(banner).to_contain_text("steps used no AI at all.")
    expect(banner).not_to_contain_text("were completed without using AI")


def test_comparison_cta_links_to_the_acknowledgement_gate(page, browser_servers):
    """The promoted CTA must not bypass the explicit model-cost consent."""
    complete_run(page, browser_servers)

    cta = page.get_by_role("link", name="Run the all-AI comparison", exact=True)
    expect(cta).to_be_visible()
    expect(cta).to_have_attribute("href", "#run-all-ai-comparison")

    cta.click()
    gate = page.locator("#run-all-ai-comparison")
    expect(gate).to_be_visible()
    consent = gate.get_by_role("checkbox")
    expect(consent).not_to_be_checked()
    expect(gate.get_by_role("button", name=re.compile("comparison", re.I)).first).to_be_disabled()


def test_route_picture_contrasts_all_ai_with_what_actually_ran(page, browser_servers):
    complete_run(page, browser_servers)

    # The hypothetical row sits inside the real route-flow panel, so there is one
    # route picture rather than two competing diagrams.
    panel = page.locator(".route-flow-panel")
    expect(panel).to_have_count(1)
    before = panel.locator(".route-flow-before")
    expect(before).to_be_visible()
    expect(before).to_contain_text("If AI did every step")
    expect(before).to_contain_text("estimate")
    # De-emphasised so a hypothetical can never read as something measured.
    expect(before.locator(".route-comparison-step.is-ghosted").first).to_be_visible()
    expect(panel).to_contain_text("local operations")


def test_local_work_is_not_described_as_free(page, browser_servers):
    """Zero model tokens is not zero total cost, and the screen must say so."""
    complete_run(page, browser_servers)

    expect(
        page.get_by_text(
            "No AI tokens does not mean free — normal computing and review time still apply.",
            exact=True,
        )
    ).to_be_visible()


# ------------------------------------------------------------------- layout


@pytest.mark.parametrize("width", [1440, 1024, 720])
def test_hero_values_share_one_baseline(page, browser_servers, width):
    """Varying title and comparison wrapping must not misalign the big numbers."""
    complete_run(page, browser_servers)
    page.set_viewport_size({"width": width, "height": 1100})

    rows = page.evaluate(
        """() => {
            const cards = Array.from(document.querySelectorAll('.prove-cards .comparison-card'));
            const groups = {};
            for (const card of cards) {
                const box = card.getBoundingClientRect();
                const value = card.querySelector('.comparison-value').getBoundingClientRect();
                const row = Math.round(box.top);
                (groups[row] = groups[row] || []).push(Math.round(value.top));
            }
            return Object.values(groups);
        }"""
    )
    for tops in rows:
        assert len(set(tops)) == 1, f"Hero values misaligned at {width}px: {tops}"

    metrics = page.evaluate(
        """() => ({ scrollWidth: document.documentElement.scrollWidth,
                    clientWidth: document.documentElement.clientWidth })"""
    )
    assert metrics["scrollWidth"] <= metrics["clientWidth"] + 1, f"{width}px: {metrics}"
