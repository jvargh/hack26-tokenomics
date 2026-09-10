"""The reporting screen in the browser.

Run explicitly: python -m pytest -c pytest-browser.ini -v

The reporting screen is where TokenOS is most tempted to overstate itself: it
aggregates many runs into a few confident-looking numbers. These tests defend the
invariants that keep it honest.

  * Every figure carries an evidence tier. A number without a tier is a claim
    without a source.
  * A verified saving of zero is a neutral fact, not an achievement. Green is
    earned by a baseline-eligible pair or not at all.
  * Absent data reads as absent, never as zero. "Not measured yet" is a
    legitimate thing for this product to say.
  * Zero runs is the ordinary first-run condition, not an error.

Uses the harness's own local-mode servers, so no model tokens are ever spent.
"""

from __future__ import annotations

from pathlib import Path
import re
import time

import pytest
from playwright.sync_api import expect

WEB_SRC = Path(__file__).resolve().parents[3].parent / "apps" / "web" / "src"

DESCRIBE = {
    "workflow": "workflow_optimization",
    "inputSource": "sample",
    "mode": "measure",
    "inputs": {
        "workflowDescription": "An assistant sends full context for every request.",
        "sampleId": "customer_assistance",
    },
    "requirements": {
        "qualityRequirements": ["same_answer_quality"],
        "optimizationGoal": "cost_per_accepted_outcome",
        "maxModelSpendUsd": 0.05,
        "allowAdvancedEscalation": False,
    },
}

KPIS = (
    "kpi-verified-saving",
    "kpi-governed-spend",
    "kpi-cost-per-outcome",
    "kpi-calls-avoided",
    "kpi-quality-pass",
    "kpi-projected",
)

PANELS = (
    "panel-spend-trend",
    "panel-route-tiers",
    "panel-projection",
    "panel-recent-runs",
    "panel-events",
)

# Numbers that mean the maths broke rather than that the data is missing.
BROKEN_NUMBER = re.compile(r"\bNaN\b|\bInfinity\b|\bundefined\b|\bnull\b|\[object Object\]")


def seed_run(page, api_url) -> str:
    """Drive a run to completion.

    A described run carries no proof, and reporting only counts runs that have
    one. So the whole governed lifecycle has to happen: describe, analyze,
    approve the plan, authorize the cost, then execute.
    """
    response = page.request.post(f"{api_url}/api/runs", data=DESCRIBE)
    assert response.status == 200, response.text()
    run_id = response.json()["runId"]

    steps = (
        ("analyze", None),
        ("optimize", {"approvePlan": True}),
        ("authorize", {"authorizeModelCost": True, "humanApprovalGranted": True}),
        ("execute", None),
    )
    for step, body in steps:
        url = f"{api_url}/api/runs/{run_id}/{step}"
        result = page.request.post(url, data=body) if body else page.request.post(url)
        assert result.status == 200, f"{step} failed: {result.text()}"
    return run_id


def wait_for_reported_runs(page, api_url, expected: int, timeout: float = 60.0) -> list:
    """Runs only reach reporting once they carry a recorded proof."""
    deadline = time.monotonic() + timeout
    seen = 0
    while time.monotonic() < deadline:
        response = page.request.get(f"{api_url}/api/optimization/reports")
        assert response.status == 200, response.text()
        runs = response.json().get("runs", [])
        seen = len(runs)
        if seen >= expected:
            return runs
        time.sleep(0.25)
    pytest.fail(f"Only {seen} of {expected} runs reached reporting within {timeout}s")


def open_reports(page):
    page.get_by_test_id("reports-nav").click()
    screen = page.get_by_test_id("reports-screen")
    expect(screen).to_be_visible()
    assert_not_fixture(page)
    return screen


def assert_not_fixture(page):
    """Guard against passing on fabricated data.

    These tests run against the vite dev server, where a failed API call makes
    the screen fall back to a bundled development fixture. That fallback is
    legitimate for a developer with no API running, but it would let every
    assertion below succeed against numbers no run ever produced. Treat it as a
    hard failure so a broken API can never look like a passing suite.
    """
    body = page.locator("body").inner_text()
    assert "development reporting fixture" not in body, (
        "Reports screen fell back to the development fixture, so these "
        "assertions would be checking invented numbers rather than the API."
    )


# ------------------------------------------------------------------ navigation


def test_workflow_remains_the_landing_view(page):
    """Adding a destination must not move anyone's cheese on load."""
    expect(page.get_by_test_id("reports-screen")).to_have_count(0)
    expect(page.get_by_test_id("reports-nav")).to_be_visible()


def test_navigation_moves_between_workflow_and_reports(page):
    open_reports(page)
    expect(page.get_by_test_id("reports-nav")).to_have_attribute("aria-current", "page")

    page.get_by_test_id("workflow-nav").click()
    expect(page.get_by_test_id("reports-screen")).to_have_count(0)
    expect(page.get_by_test_id("workflow-nav")).to_have_attribute("aria-current", "page")


def test_history_is_still_reachable_from_reports(page):
    """The overlays belong to the shell, not to one destination."""
    open_reports(page)
    page.get_by_role("button", name="History", exact=True).click()
    expect(page.get_by_role("dialog", name="Run history", exact=True)).to_be_visible()


# ------------------------------------------------------------------ empty state


def test_no_runs_is_an_empty_state_not_an_error(page, browser_servers):
    """First use is the commonest state this screen will ever be in.

    The server storage is shared for the whole session and this file sorts last,
    so by the time it runs another suite may already have produced runs. Assert
    against what the API actually holds rather than assuming an empty store,
    otherwise this passes alone and fails in the full run.
    """
    response = page.request.get(f"{browser_servers['api']}/api/optimization/reports")
    assert response.status == 200, response.text()
    reported = len(response.json().get("runs", []))

    screen = open_reports(page)
    if reported == 0:
        expect(page.get_by_test_id("reports-empty")).to_be_visible()
    else:
        expect(page.get_by_test_id("reports-empty")).to_have_count(0)
    assert not BROKEN_NUMBER.search(screen.inner_text())


# ------------------------------------------------------------------ the figures


def test_every_kpi_declares_its_evidence_tier(page, browser_servers):
    """A number without a tier is a claim without a source."""
    seed_run(page, browser_servers["api"])
    wait_for_reported_runs(page, browser_servers["api"], 1)
    page.reload(wait_until="networkidle")
    open_reports(page)

    for kpi in KPIS:
        card = page.get_by_test_id(kpi)
        expect(card).to_be_visible()
        tier = page.get_by_test_id(f"{kpi}-tier")
        expect(tier).to_be_visible()
        assert tier.inner_text().strip(), f"{kpi} rendered a value with an empty tier"


def test_figures_never_render_as_broken_numbers(page, browser_servers):
    """Missing data must read as missing, not as NaN or undefined."""
    seed_run(page, browser_servers["api"])
    wait_for_reported_runs(page, browser_servers["api"], 1)
    page.reload(wait_until="networkidle")
    screen = open_reports(page)

    text = screen.inner_text()
    match = BROKEN_NUMBER.search(text)
    assert match is None, f"Reporting screen rendered {match.group(0)!r}"


def test_a_rate_is_never_rendered_as_an_accumulated_total(page, browser_servers):
    """Regression guard: rates were previously summed, so ten runs read as 1000%.

    Quality pass rate is a proportion. Whatever else it is, it is not above 100%.
    """
    for _ in range(3):
        seed_run(page, browser_servers["api"])
    wait_for_reported_runs(page, browser_servers["api"], 3)
    page.reload(wait_until="networkidle")
    open_reports(page)

    value = page.get_by_test_id("kpi-quality-pass-value").inner_text()
    percentages = [float(found) for found in re.findall(r"(\d+(?:\.\d+)?)\s*%", value)]
    for percentage in percentages:
        assert percentage <= 100.0, f"Quality pass rate rendered as {percentage}%"


def test_zero_verified_saving_is_neutral_not_celebrated(page, browser_servers):
    """A sample run earns no verified saving, and the screen must not imply one.

    Green is the vocabulary of a proven win. Spending it on an unproven zero is
    how a measurement product starts lying by decoration.
    """
    seed_run(page, browser_servers["api"])
    wait_for_reported_runs(page, browser_servers["api"], 1)
    page.reload(wait_until="networkidle")
    open_reports(page)

    card = page.get_by_test_id("kpi-verified-saving")
    value = page.get_by_test_id("kpi-verified-saving-value").inner_text()
    if not re.search(r"[1-9]", value):
        colour = card.evaluate("node => getComputedStyle(node).color")
        good = page.evaluate(
            "() => getComputedStyle(document.documentElement).getPropertyValue('--tos-good').trim()"
        )
        assert good, "--tos-good is expected to be defined by the token sheet"
        assert colour.strip() != good, "An unearned zero saving is styled as a win"


# ---------------------------------------------------------------------- panels


def test_panels_render_once_there_is_something_to_report(page, browser_servers):
    seed_run(page, browser_servers["api"])
    wait_for_reported_runs(page, browser_servers["api"], 1)
    page.reload(wait_until="networkidle")
    open_reports(page)

    for panel in PANELS:
        expect(page.get_by_test_id(panel)).to_be_visible()


def test_filters_are_offered(page, browser_servers):
    seed_run(page, browser_servers["api"])
    wait_for_reported_runs(page, browser_servers["api"], 1)
    page.reload(wait_until="networkidle")
    open_reports(page)

    expect(page.get_by_test_id("report-range")).to_be_visible()
    expect(page.get_by_test_id("report-target")).to_be_visible()
    expect(page.get_by_test_id("report-export")).to_be_visible()


def test_export_returns_both_formats(page, browser_servers):
    """The evidence has to be able to leave the building."""
    seed_run(page, browser_servers["api"])
    wait_for_reported_runs(page, browser_servers["api"], 1)
    api = browser_servers["api"]

    as_json = page.request.get(f"{api}/api/optimization/reports/export?format=json")
    assert as_json.status == 200, as_json.text()
    assert "groups" in as_json.json()

    as_csv = page.request.get(f"{api}/api/optimization/reports/export?format=csv")
    assert as_csv.status == 200, as_csv.text()
    body = as_csv.text()
    assert "runId" in body.splitlines()[0]
    assert "None" not in body, "A missing value leaked into the CSV as the string 'None'"


def test_opportunities_are_estimates_or_absent(page, browser_servers):
    """Opportunities are the weakest claim on the screen and must say so."""
    seed_run(page, browser_servers["api"])
    wait_for_reported_runs(page, browser_servers["api"], 1)
    page.reload(wait_until="networkidle")
    open_reports(page)

    cards = page.get_by_test_id("opportunity-card")
    for index in range(cards.count()):
        expect(cards.nth(index)).to_contain_text(re.compile("estimate", re.IGNORECASE))


# --------------------------------------------------------------- accessibility


def test_charts_carry_a_text_alternative(page, browser_servers):
    """A chart that only speaks in colour excludes part of its audience."""
    seed_run(page, browser_servers["api"])
    wait_for_reported_runs(page, browser_servers["api"], 1)
    page.reload(wait_until="networkidle")
    screen = open_reports(page)

    charts = screen.locator("svg")
    for index in range(charts.count()):
        chart = charts.nth(index)
        described = chart.evaluate(
            """node => Boolean(
                node.querySelector('title')
                || node.getAttribute('aria-label')
                || node.getAttribute('aria-labelledby')
                || node.getAttribute('aria-hidden') === 'true'
            )"""
        )
        assert described, f"Chart {index} has no accessible name and is not hidden from AT"


# ------------------------------------------------------- theming (source guard)


def test_report_components_use_tokens_rather_than_literal_colour():
    """Hard-coded colour silently breaks the light theme.

    Cheaper to catch here than to notice as a washed-out screenshot later.
    """
    reports = WEB_SRC / "components" / "reports"
    if not reports.exists():
        pytest.skip("Reporting components not present")

    offenders = []
    hex_colour = re.compile(r"#[0-9a-fA-F]{3,8}\b")
    for source in list(reports.rglob("*.tsx")) + list(reports.rglob("*.ts")):
        for number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
            if hex_colour.search(line):
                offenders.append(f"{source.name}:{number}: {line.strip()}")
    assert not offenders, "Literal colour found; use CSS custom properties:\n" + "\n".join(offenders)
