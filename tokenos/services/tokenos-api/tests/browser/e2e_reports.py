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


def seed_workflow_run(page, api_url, workflow: str = "document_review") -> str:
    """Drive one of the first three workflows to a recorded proof.

    These runs persist to the durable ledger rather than the optimization store.
    Reporting has to read them from there, so this covers the path that
    previously produced an empty report despite a completed run.
    """
    sample = page.request.post(f"{api_url}/api/uploads/sample",
                               data={"workflow_id": workflow})
    assert sample.status == 200, sample.text()
    uploads = {role: [item["upload_id"] for item in items]
               for role, items in sample.json()["uploads"].items()}

    analyze = page.request.post(f"{api_url}/api/runs/analyze", data={
        "workflow_id": workflow,
        "input_source": "sample",
        "uploads": uploads,
        "inputs": {"review-focus": "Unsupported charges"},
        "desired_outcome": "",
        "requirements": {"maximum_cost_usd": 1.0, "required_quality_score": 0.9},
    })
    assert analyze.status == 200, analyze.text()

    started = page.request.post(f"{api_url}/api/runs",
                                data={"plan_id": analyze.json()["plan_id"]})
    assert started.status == 200, started.text()
    run_id = started.json()["run_id"]

    deadline = time.monotonic() + 120.0
    while time.monotonic() < deadline:
        if page.request.get(f"{api_url}/api/runs/{run_id}/proof").status == 200:
            return run_id
        time.sleep(0.25)
    pytest.fail(f"Workflow run {run_id} never produced a proof")


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


# -------------------------------------------- cross-workflow run coverage


def test_a_completed_workflow_run_reaches_reporting(page, browser_servers):
    """Reporting spans every proof-bearing run, not just optimization runs.

    The first three workflows persist to the durable ledger while the fourth
    writes to the optimization store. Reporting once read only the latter, so a
    finished document review left the screen claiming there was nothing to show.
    """
    api = browser_servers["api"]
    run_id = seed_workflow_run(page, api)

    response = page.request.get(f"{api}/api/optimization/reports?source=workflow")
    assert response.status == 200, response.text()
    reported = {run["runId"] for run in response.json()["runs"]}
    assert run_id in reported, "A completed workflow run never reached reporting"

    open_reports(page)
    expect(page.get_by_test_id("reports-empty")).to_have_count(0)
    expect(page.get_by_test_id("panel-recent-runs")).to_be_visible()
    # `.first` because the sparkline title also names the run.
    expect(
        page.get_by_test_id("panel-recent-runs").locator("td", has_text=run_id).first
    ).to_be_visible()


def test_a_workflow_run_reports_its_own_workflow_not_a_default(page, browser_servers):
    """The row must name the workflow that actually ran.

    The table used to read flat keys off a nested payload, so every row silently
    fell back to a default label. A row that cannot be attributed is worse than
    useless: it invites the reader to trust the wrong provenance.
    """
    api = browser_servers["api"]
    run_id = seed_workflow_run(page, api)
    open_reports(page)

    row = page.get_by_test_id("panel-recent-runs").locator("tr", has_text=run_id).first
    expect(row).to_be_visible()
    text = row.inner_text()
    assert "document_review" in text, f"Row did not name its workflow: {text!r}"
    assert "Optimization workflow" not in text, (
        f"Workflow run mislabelled as an optimization run: {text!r}"
    )


def test_a_sample_run_is_never_labelled_measured(page, browser_servers):
    """Evidence strength must survive the round trip.

    A run over bundled fixtures is reproducible input. Rendering it as
    "measured" would present a demo figure as production spend, which is the one
    thing this screen must never do.
    """
    api = browser_servers["api"]
    run_id = seed_workflow_run(page, api)

    response = page.request.get(f"{api}/api/optimization/reports?source=workflow")
    reported = next(run for run in response.json()["runs"] if run["runId"] == run_id)
    assert reported["dimensions"]["proofType"] == "sample", (
        "A bundled-sample run must not be classified as measured"
    )

    open_reports(page)
    row = page.get_by_test_id("panel-recent-runs").locator("tr", has_text=run_id).first
    cells = row.locator("td")
    # The Proof column must name the evidence honestly.
    assert cells.nth(3).inner_text().strip() == "sample", (
        f"Proof column read {cells.nth(3).inner_text()!r} for a fixture run"
    )
    # And no figure on the row may be tiered as governed production spend.
    assert row.locator(".tier.is-measured-governed").count() == 0, (
        "A fixture run's figures were tiered as governed production spend"
    )
    assert row.locator(".tier.is-measured-sample").count() > 0, (
        "A fixture run's figures should be tiered as a measured sample run"
    )


def test_a_workflow_run_without_a_baseline_claims_no_saving(page, browser_servers):
    """No paired baseline means no verified saving, however cheap the run was."""
    api = browser_servers["api"]
    run_id = seed_workflow_run(page, api)

    response = page.request.get(f"{api}/api/optimization/reports?source=workflow")
    reported = next(run for run in response.json()["runs"] if run["runId"] == run_id)
    assert not reported.get("baseline"), "A run with no baseline reported one"

    open_reports(page)
    row = page.get_by_test_id("panel-recent-runs").locator("tr", has_text=run_id).first
    assert not row.locator(".tier-verified-saving").count(), (
        "A verified saving was claimed without a paired baseline"
    )


def active_basis(page, api_url) -> tuple[str, dict]:
    """Which evidence group the headline should be drawn from, and that group.

    Storage is shared across the whole browser session, so by the time this file
    runs another suite may already have produced measured runs. The basis is
    therefore a property of current state, not a constant: asserting a fixed
    basis passes in isolation and fails in a full run.
    """
    report = page.request.get(f"{api_url}/api/optimization/reports").json()
    measured = report["groups"]["measured"]
    sample = report["groups"]["sample"]
    if measured["runCount"] > 0 or sample["runCount"] == 0:
        return "measured", measured
    return "sample", sample


def test_kpis_reflect_evidence_that_exists(page, browser_servers):
    """The headline must not read zero while the runs table shows finished runs.

    Every KPI card used to read `groups.measured`, so a range containing only
    sample runs rendered $0.00 across the board while the runs table and
    route-tier panel showed real data. That looks like broken reporting rather
    than like a set of sample runs, and it hides genuine results.
    """
    api = browser_servers["api"]
    seed_workflow_run(page, api)
    basis, group = active_basis(page, api)
    assert group["runCount"] > 0, "Expected the active basis to contain runs"

    open_reports(page)
    expect(page.locator(".kpi-grid")).to_be_visible()

    def card_value(test_id: str) -> str:
        """Second line of a KPI card is its value. Read that rather than the
        whole card: the tier label contains an em-dash, which would collide with
        the em-dash used for an unknown value."""
        lines = [line.strip() for line in page.get_by_test_id(test_id).inner_text().splitlines()]
        return next(line for line in lines[1:] if line)

    if group["governedModelSpendUsd"] > 0:
        spend = card_value("kpi-governed-spend")
        assert spend not in {"$0.00", "—"}, (
            f"Governed spend read {spend!r} on the {basis} basis despite "
            f"{group['governedModelSpendUsd']} of measured spend"
        )

    if group["rates"]["qualityPassRate"]["mean"] is not None:
        quality = card_value("kpi-quality-pass")
        assert quality != "—", "Quality pass rate rendered as unknown despite a completed run"
        assert quality.endswith("%"), f"Quality pass rate rendered as {quality!r}"


def test_headline_figures_are_tiered_to_the_evidence_behind_them(page, browser_servers):
    """Falling back to sample evidence must not quietly relabel it.

    Showing fixture numbers under a "Measured — governed" chip would present a
    demonstration as production spend, which is worse than showing zeros.
    """
    api = browser_servers["api"]
    seed_workflow_run(page, api)
    basis, _ = active_basis(page, api)

    open_reports(page)
    grid = page.locator(".kpi-grid")
    expect(grid).to_be_visible()

    if basis == "sample":
        assert grid.locator(".tier.is-measured-sample").count() > 0, (
            "Sample-basis KPIs were not tiered as a measured sample run"
        )
        assert grid.locator(".tier.is-measured-governed").count() == 0, (
            "Sample evidence was tiered as governed production spend"
        )
    else:
        assert grid.locator(".tier.is-measured-governed").count() > 0, (
            "Measured-basis KPIs were not tiered as governed spend"
        )
        assert grid.locator(".tier.is-measured-sample").count() == 0, (
            "Measured evidence was tiered as a sample run"
        )


def test_the_sample_notice_appears_exactly_when_the_basis_is_sample(page, browser_servers):
    """The caveat has to track the figures. Shown on measured evidence it
    understates them; missing on sample evidence it overstates them."""
    api = browser_servers["api"]
    seed_workflow_run(page, api)
    basis, _ = active_basis(page, api)

    open_reports(page)
    expect(page.locator(".kpi-grid")).to_be_visible()
    notice = page.get_by_test_id("reports-sample-basis")

    if basis == "sample":
        expect(notice).to_be_visible()
        text = notice.inner_text().lower()
        assert "sample" in text
        assert "production spend" in text
    else:
        expect(notice).to_have_count(0)



def test_the_source_filter_is_rejected_when_unknown(page, browser_servers):
    api = browser_servers["api"]
    response = page.request.get(f"{api}/api/optimization/reports?source=nonsense")
    assert response.status == 422, response.text()


def test_export_names_the_run_source(page, browser_servers):
    """An exported row has to say where it came from, or the two run kinds are
    indistinguishable once the file leaves the product."""
    api = browser_servers["api"]
    seed_workflow_run(page, api)

    response = page.request.get(
        f"{api}/api/optimization/reports/export?format=csv&source=workflow"
    )
    assert response.status == 200, response.text()
    body = response.text()
    header = body.splitlines()[0]
    assert "source" in header and "workflowId" in header, header
    assert "workflow" in body
    assert "None" not in body, "CSV leaked a Python None instead of an empty cell"


# ------------------------------------------------------------------ layout


OVERFLOW_PROBE = """
() => {
  const problems = [];
  const tolerance = 1;
  document.querySelectorAll('.reports .metric-number').forEach((node) => {
    const holder = node.closest('.kpi-card, td, .panel');
    if (!holder) return;
    const value = node.getBoundingClientRect();
    const bounds = holder.getBoundingClientRect();
    const style = window.getComputedStyle(holder);
    const left = bounds.left + (parseFloat(style.paddingLeft) || 0);
    const right = bounds.right - (parseFloat(style.paddingRight) || 0);
    if (value.right > right + tolerance || value.left < left - tolerance) {
      problems.push({
        text: node.textContent.trim(),
        holder: holder.getAttribute('data-testid') || holder.tagName,
        overflowRight: Math.round(value.right - right),
        overflowLeft: Math.round(left - value.left)
      });
    }
  });
  return problems;
}
"""


@pytest.mark.parametrize("width,height", [(1280, 900), (1024, 900), (820, 1000)])
def test_no_reported_figure_overflows_its_card(page, browser_servers, width, height):
    """Figures must stay inside the card that frames them.

    Sub-cent unit economics need six decimal places to avoid reading as $0.00,
    which makes them far wider than a percentage. The headline size was tied to
    viewport width rather than card width, so those values ran past the card
    edge and the reader could not finish the number.
    """
    api = browser_servers["api"]
    seed_workflow_run(page, api)
    page.set_viewport_size({"width": width, "height": height})
    open_reports(page)
    expect(page.locator(".kpi-grid")).to_be_visible()

    problems = page.evaluate(OVERFLOW_PROBE)
    assert not problems, f"Figures overflow their container at {width}px: {problems}"


def test_the_reports_screen_does_not_scroll_sideways(page, browser_servers):
    """A horizontal scrollbar on the whole page means something is pushing the
    layout wider than the window, which hides content off-screen."""
    api = browser_servers["api"]
    seed_workflow_run(page, api)
    page.set_viewport_size({"width": 1280, "height": 900})
    open_reports(page)

    overflow = page.evaluate(
        "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    assert overflow <= 1, f"Reports screen scrolls sideways by {overflow}px"


def test_a_long_figure_is_sized_down_rather_than_clipped(page, browser_servers):
    """The sizing hook has to be present, or the guarantee above is accidental."""
    api = browser_servers["api"]
    seed_workflow_run(page, api)
    open_reports(page)
    # eval_on_selector_all does not auto-wait, so wait for the grid explicitly.
    expect(page.locator(".kpi-grid")).to_be_visible()

    bands = page.eval_on_selector_all(
        ".kpi-value .metric-number",
        "nodes => nodes.map(node => node.getAttribute('data-length'))"
    )
    assert bands, "No KPI figures rendered"
    assert all(band in {"short", "medium", "long", "xlong"} for band in bands), bands


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
