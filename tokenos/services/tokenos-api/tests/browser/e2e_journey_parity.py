"""The optimization journey should feel like the other workflows.

Run explicitly: python -m pytest -c pytest-browser.ini tests/browser/e2e_journey_parity.py -v

Two properties are protected here:

  1. A sample run reaches Prove from a single click. The Describe action is
     where model cost is authorized, so the decision is still explicit; it just
     is not repeated on a later phase.

  2. The optimization Prove screen uses the same before/after presentation as
     the other workflows, so a user does not learn two different layouts.
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect

from e2e_optimization import START_MEASURE, START_PROMPT

OPTIMIZE = "Optimize an existing AI workflow"
DEADLINE = "Process records by a deadline"
MEASURE = "Measure an optimized workflow"
PROMPT = "Optimize a prompt before you run it"


def open_optimization(page, mode=MEASURE):
    page.get_by_role("button", name=re.compile("^" + re.escape(OPTIMIZE))).click()
    page.get_by_role("radio", name=re.compile("^" + re.escape(mode))).check()


def stepper_states(page):
    return page.evaluate(
        """() => Array.from(
             document.querySelectorAll('nav[aria-label="Optimization workflow progress"] li')
           ).map(li => ({
             label: li.querySelector('.step-label').textContent,
             reached: !li.className.includes('is-future')
           }))"""
    )


def test_sample_run_reaches_prove_with_one_click(page, browser_servers):
    """One deliberate click: submitting the work also authorizes its spend."""
    open_optimization(page)
    page.get_by_role("button", name="Use a measured example", exact=True).click()

    page.get_by_role("button", name=START_MEASURE, exact=True).click()

    # Every remaining phase follows without further prompting.
    expect(page.locator(".optimization-hero")).to_be_visible(timeout=30000)
    expect(page.locator(".work-avoided")).to_be_visible()

    for step in stepper_states(page):
        assert step["reached"], f"{step['label']} was never reached"


def test_prompt_example_reaches_prove_with_one_click(page, browser_servers):
    open_optimization(page, PROMPT)
    page.get_by_role("button", name="Use a prompt example", exact=True).click()
    examples = page.request.get(
        f"{browser_servers['api']}/api/optimization/prompt-examples"
    ).json()["examples"]
    lookup = next(item for item in examples if item["id"] == "repeated_policy_lookup")
    page.get_by_role("radio", name=re.compile("^" + re.escape(lookup["title"]))).check()

    page.get_by_role("button", name=START_PROMPT, exact=True).click()
    expect(page.locator(".optimization-hero")).to_be_visible(timeout=30000)

    for step in stepper_states(page):
        assert step["reached"], f"{step['label']} was never reached"


def test_no_model_runs_without_a_recorded_authorization(page, browser_servers):
    """A run held by a failed safeguard is never authorized and never executes."""
    open_optimization(page)
    page.get_by_role("button", name="Use a measured example", exact=True).click()
    page.get_by_role("radio", name=re.compile("^Policy document review")).check()

    with page.expect_response(
        lambda response: response.url == browser_servers["api"] + "/api/runs"
        and response.request.method == "POST"
    ) as created:
        page.get_by_role("button", name=START_MEASURE, exact=True).click()
    run_id = created.value.json()["runId"]

    expect(page.get_by_role("heading", name="Execution safeguards", exact=True)).to_be_visible(timeout=30000)
    state = page.request.get(f"{browser_servers['api']}/api/runs/{run_id}").json()
    assert state["status"] == "optimized", "A blocked draft must not execute."
    assert state["proof"] is None
    assert not state.get("modelUsage")

    # The server refuses execution until an authorization is recorded.
    assert page.request.post(
        f"{browser_servers['api']}/api/runs/{run_id}/execute",
        data="{}",
        headers={"content-type": "application/json"},
    ).status == 409


def test_optimization_prove_matches_the_shared_layout(page, browser_servers):
    """Both Prove surfaces use the same components, so users learn one layout."""
    open_optimization(page)
    page.get_by_role("button", name="Use a measured example", exact=True).click()
    page.get_by_role("button", name=START_MEASURE, exact=True).click()
    expect(page.locator(".optimization-hero")).to_be_visible(timeout=30000)

    # The same primitives as the legacy Prove screen.
    expect(page.locator(".work-avoided")).to_be_visible()
    assert page.locator(".prove-cards .comparison-card").count() == 4
    # The retired bespoke metric tiles are gone.
    expect(page.locator(".optimization-metric")).to_have_count(0)

    for title in ("What this run cost", "How often AI was needed", "Is the answer still correct?"):
        expect(page.get_by_text(title, exact=True)).to_be_visible()

    # No saving is claimed before a paired comparison.
    expect(page.get_by_role("heading", name="Comparison not run", exact=True)).to_be_visible()
    expect(page.get_by_role("heading", name="Verified saving", exact=True)).to_have_count(0)


def test_legacy_and_optimization_prove_share_card_titles(page, browser_servers):
    """A user moving between workflows should see the same headings."""
    page.get_by_role("button", name=re.compile("^" + re.escape(DEADLINE))).click()
    page.get_by_role("radio", name=re.compile("^Use sample data")).check()
    page.get_by_role("button", name="Load sample data", exact=True).click()
    page.get_by_role("button", name="Analyze with TokenOS", exact=True).click()
    prove = page.get_by_role("navigation", name="Run progress").get_by_role(
        "button", name=re.compile("^Prove")
    )
    expect(prove).to_be_enabled(timeout=60000)
    prove.click()

    legacy_titles = page.locator(".prove-cards .comparison-card-title").all_inner_texts()
    assert "What this run cost" in legacy_titles
    assert "Is the answer still correct?" in legacy_titles

    page.get_by_role("button", name="New run", exact=True).click()
    open_optimization(page)
    page.get_by_role("button", name="Use a measured example", exact=True).click()
    page.get_by_role("button", name=START_MEASURE, exact=True).click()
    expect(page.locator(".optimization-hero")).to_be_visible(timeout=30000)

    optimization_titles = page.locator(".prove-cards .comparison-card-title").all_inner_texts()
    shared = set(legacy_titles) & set(optimization_titles)
    assert {"What this run cost", "Is the answer still correct?"} <= shared


# ----------------------------------------------------------------- theme toggle


def test_theme_toggle_switches_and_remembers(page):
    """One bulb switches light/dark and the choice survives a reload."""
    toggle = page.get_by_role("button", name=re.compile("^Switch to "))
    expect(toggle).to_be_visible()

    # Dark is the product default so the surface never follows the OS setting.
    assert page.evaluate("() => document.documentElement.getAttribute('data-theme')") != "light"
    expect(toggle).to_have_attribute("aria-label", "Switch to light mode")

    toggle.click()
    assert page.evaluate("() => document.documentElement.getAttribute('data-theme')") == "light"
    expect(toggle).to_have_attribute("aria-label", "Switch to dark mode")
    expect(toggle).to_have_attribute("aria-pressed", "true")

    page.reload(wait_until="domcontentloaded")
    assert page.evaluate("() => document.documentElement.getAttribute('data-theme')") == "light"

    page.get_by_role("button", name=re.compile("^Switch to ")).click()
    assert page.evaluate("() => document.documentElement.getAttribute('data-theme')") == "dark"


def test_light_mode_keeps_text_readable(page):
    """The light palette must not leave low-contrast text behind."""
    page.get_by_role("button", name=re.compile("^Switch to light mode")).click()

    contrast = page.evaluate(
        """() => {
            // Colours arrive either as rgb(0-255) or color(srgb 0-1); mixing the
            // two scales silently reports black and invents contrast failures.
            const parse = (value) => {
                const parts = (value.match(/[\\d.]+/g) || []).slice(0, 3).map(Number);
                if (parts.length < 3) return [255, 255, 255];
                return value.includes('color(') ? parts.map((c) => c * 255) : parts;
            };
            const luminance = ([r, g, b]) => {
                const channel = (c) => {
                    const s = c / 255;
                    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
                };
                return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
            };
            const backdrop = (node) => {
                let el = node;
                while (el) {
                    const bg = getComputedStyle(el).backgroundColor;
                    if (bg && !bg.includes('rgba(0, 0, 0, 0)') && bg !== 'transparent') return parse(bg);
                    el = el.parentElement;
                }
                return [255, 255, 255];
            };
            const worst = [];
            for (const node of document.querySelectorAll('h1, h2, h3, p, button, label')) {
                if (!node.textContent.trim() || !node.getClientRects().length) continue;
                const fg = luminance(parse(getComputedStyle(node).color));
                const bg = luminance(backdrop(node));
                const ratio = (Math.max(fg, bg) + 0.05) / (Math.min(fg, bg) + 0.05);
                worst.push({ text: node.textContent.trim().slice(0, 40), ratio: +ratio.toFixed(2) });
            }
            return worst.sort((a, b) => a.ratio - b.ratio).slice(0, 5);
        }"""
    )
    # 3:1 is the large-text floor; anything below that is unreadable, not just tight.
    for item in contrast:
        assert item["ratio"] >= 3.0, f"Low contrast in light mode: {contrast}"
