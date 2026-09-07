"""Pre-handoff sweep: every Step 1 entry path, driven through phases 2-7.

Run explicitly: python -m pytest -c pytest-browser.ini tests/browser/e2e_handoff_sweep.py -v

This is real UI/UX validation, not an API check. Each case clicks through the
browser exactly as a first-time user would, then asserts that the resulting
Plan, Optimize, Protect, Run, Verify and Prove screens actually say something
true and useful.

Everything runs against the harness's own local-mode servers, so no model
tokens are ever spent.
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from datetime import datetime, timedelta

import pytest
from playwright.sync_api import expect

# The four Step 1 workflow cards, exactly as a user reads them.
DOCUMENT_REVIEW = "Review documents against rules"
CODE_CHANGE = "Test a code change"
DEADLINE = "Process records by a deadline"
OPTIMIZE = "Optimize an existing AI workflow"

LEGACY_WORKFLOWS = [DOCUMENT_REVIEW, CODE_CHANGE, DEADLINE]

# The three input sources offered by the legacy workflows.
UPLOAD = "Upload my data"
CONNECTED = "Use a connected application"
SAMPLE = "Use sample data"

PHASES = ["Describe", "Plan", "Optimize", "Protect", "Run", "Verify", "Prove"]


# --------------------------------------------------------------------- helpers


def choose_workflow(page, title):
    page.get_by_role("button", name=re.compile("^" + re.escape(title))).click()


def choose_source(page, source):
    page.get_by_role("radio", name=re.compile("^" + re.escape(source))).check()


def open_phase(page, name):
    """Navigates via the stepper, the way a user inspects a finished run."""
    stepper = page.get_by_role("navigation", name="Run progress")
    button = stepper.get_by_role("button", name=re.compile(f"^{name}"))
    expect(button).to_be_enabled(timeout=60000)
    button.click()
    return button


def start_run(page, browser_servers):
    action = page.get_by_role("button", name="Analyze with TokenOS", exact=True)
    expect(action).to_be_enabled()
    with page.expect_response(
        lambda response: response.url == browser_servers["api"] + "/api/runs"
        and response.request.method == "POST"
    ) as started:
        action.click()
    assert started.value.ok, started.value.text()
    return started.value.json()["run_id"]


def fetch_proof(page, browser_servers, run_id):
    response = page.request.get(f"{browser_servers['api']}/api/runs/{run_id}/proof")
    assert response.status == 200, response.text()
    return response.json()


def run_sample_workflow(page, browser_servers, title):
    """Step 1 via sample data, then wait for the run to reach Prove."""
    choose_workflow(page, title)
    choose_source(page, SAMPLE)
    page.get_by_role("button", name="Load sample data", exact=True).click()
    run_id = start_run(page, browser_servers)
    open_phase(page, "Prove")
    expect(page.locator(".prove-cards")).to_be_visible()
    return run_id


# ------------------------------------------------- Step 1: entry paths exist


@pytest.mark.parametrize("title", LEGACY_WORKFLOWS + [OPTIMIZE])
def test_every_workflow_card_is_selectable(page, title):
    """All four Step 1 cards from the handoff screenshots are present."""
    expect(page.get_by_role("heading", name="What do you want TokenOS to optimize?")).to_be_visible()
    card = page.get_by_role("button", name=re.compile("^" + re.escape(title)))
    expect(card).to_be_visible()
    card.click()
    expect(card).to_have_attribute("aria-pressed", "true")


@pytest.mark.parametrize("width", [1600, 1440, 1280, 1024, 860])
def test_workflow_cards_share_one_layout(page, width):
    """Every card shows a title and a description starting on the same baseline.

    One workflow title is long enough to wrap where the others do not. Without a
    reserved second line its description sits lower than the rest, and the card
    reads as though it is missing the heading the others have.
    """
    page.set_viewport_size({"width": width, "height": 1000})
    cards = page.evaluate(
        """() => Array.from(document.querySelectorAll('.template')).map((card) => {
            const name = card.querySelector('.template-name');
            const support = card.querySelector('.template-support');
            return {
                title: name ? name.textContent.trim() : '',
                description: support ? support.textContent.trim() : '',
                descriptionTop: Math.round(support.getBoundingClientRect().top),
                row: Math.round(card.getBoundingClientRect().top)
            };
        })"""
    )
    assert len(cards) == 4

    for card in cards:
        assert card["title"], "a workflow card has no title"
        assert card["description"], f"{card['title']} has no description"

    # Cards on the same row must start their description at the same height; a
    # wrapped grid legitimately has more than one row.
    rows: dict[int, list[int]] = {}
    for card in cards:
        rows.setdefault(card["row"], []).append(card["descriptionTop"])
    for row, tops in rows.items():
        assert len(set(tops)) == 1, f"descriptions misaligned at {width}px, row {row}: {sorted(set(tops))}"


@pytest.mark.parametrize("title", LEGACY_WORKFLOWS)
def test_each_legacy_workflow_offers_all_three_sources(page, title):
    """Upload / connected / sample are offered for every legacy workflow."""
    choose_workflow(page, title)
    expect(page.get_by_role("heading", name="Provide the work")).to_be_visible()
    for source in (UPLOAD, CONNECTED, SAMPLE):
        radio = page.get_by_role("radio", name=re.compile("^" + re.escape(source)))
        expect(radio).to_be_visible()
        radio.check()
        expect(radio).to_be_checked()


@pytest.mark.parametrize("title", LEGACY_WORKFLOWS)
def test_connected_source_never_implies_azure_access(page, title):
    """The connected path must state plainly that it is not a subscription link."""
    choose_workflow(page, title)
    choose_source(page, CONNECTED)
    # The disclaimer appears both on the source card and beneath it; either is fine
    # so long as the user cannot miss it.
    disclaimer = page.get_by_text(
        re.compile("does not automatically connect to an Azure subscription")
    )
    assert disclaimer.count() >= 1
    expect(disclaimer.first).to_be_visible()

    # Where no adapter is registered, the screen says so instead of showing an
    # empty picker that looks broken.
    picker = page.get_by_label("Registered application", exact=True)
    if picker.count():
        options = picker.locator("option")
        if options.count() <= 1:
            expect(page.get_by_text(re.compile("No applications are registered"))).to_be_visible()


# ------------------------------------------- Phases 2-7 for each legacy workflow


@pytest.mark.parametrize("title", LEGACY_WORKFLOWS)
def test_phases_two_to_seven_are_reachable_and_populated(page, browser_servers, title):
    """Walks the finished run through every phase the way a user would."""
    run_id = run_sample_workflow(page, browser_servers, title)
    proof = fetch_proof(page, browser_servers, run_id)

    # Phase 2 — Plan explains the work before anything is spent.
    open_phase(page, "Plan")
    expect(page.get_by_role("heading", name="Planning the work")).to_be_visible()

    # Phase 3 — Optimize explains the route choice.
    open_phase(page, "Optimize")
    expect(page.get_by_role("heading", name="Choosing the best routes")).to_be_visible()

    # Phase 4 — Protect shows the safeguards that gate any spend.
    open_phase(page, "Protect")
    expect(page.locator(".phase")).to_contain_text(re.compile("protect|safeguard|approv", re.I))

    # Phase 5 — Run shows what actually executed.
    open_phase(page, "Run")
    expect(page.locator(".phase")).not_to_contain_text("The run failed")

    # Phase 6 — Verify reports the outcome against its checks.
    open_phase(page, "Verify")
    expect(page.get_by_role("heading", name="Verifying the completed outcome")).to_be_visible()

    # Phase 7 — Prove. The banner celebrates avoided AI only when the outcome
    # actually passed; the code-change sample deliberately fails a test, and that
    # state must show no benefit framing at all.
    open_phase(page, "Prove")
    expect(page.locator(".claim-strength")).to_be_visible()
    passed = proof["outcome"]["quality_passed"]

    if not passed:
        expect(page.locator(".work-avoided")).to_have_count(0)
        expect(page.locator(".claim-strength")).to_have_class(re.compile("is-none"))
        expect(page.locator(".comparison-before:not(.is-blank)")).to_have_count(0)
        return

    expect(page.locator(".work-avoided")).to_be_visible()

    # Every visible count comes from the one run record.
    counted = page.locator(".work-avoided-count").inner_text()
    local_ops, total_ops = (int(part) for part in re.findall(r"\d+", counted)[:2])
    assert local_ops == proof["routing"]["completed_without_generative_ai"]
    assert total_ops == proof["routing"]["operations"]


@pytest.mark.parametrize("title", LEGACY_WORKFLOWS)
def test_prove_claim_strength_matches_the_run_record(page, browser_servers, title):
    """The claim shown must never be stronger than the evidence behind it."""
    run_id = run_sample_workflow(page, browser_servers, title)
    proof = fetch_proof(page, browser_servers, run_id)

    passed = proof["outcome"]["quality_passed"]
    complete = proof["outcome"].get("decision_complete", True) is not False
    bar = page.locator(".claim-strength")

    if passed and complete:
        expect(bar).to_have_class(re.compile("is-estimate"))
        expect(page.locator(".claim-strength-badge")).to_have_text("Estimate")
        # An estimate must never borrow measured language.
        expect(page.locator(".prove-cards").get_by_text(re.compile("proven"))).to_have_count(0)
    else:
        expect(bar).to_have_class(re.compile("is-none"))
        # No cost benefit is offered for work that did not finish or did not pass.
        expect(page.locator(".comparison-before:not(.is-blank)")).to_have_count(0)
        expect(page.locator(".route-flow-before")).to_have_count(0)

    # A saving is never claimed before a paired run, in any state.
    expect(page.locator(".prove-cards").get_by_text("Verified saving", exact=False)).to_have_count(0)


@pytest.mark.parametrize("title", LEGACY_WORKFLOWS)
def test_prove_copy_is_not_borrowed_from_another_workflow(page, browser_servers, title):
    """Document-review wording must not appear on a code or records workflow."""
    run_sample_workflow(page, browser_servers, title)
    body = page.locator(".phase").inner_text()

    # These read as obvious mistakes to a first-time user on the wrong workflow.
    leaks = ["charge line", "review operation", "policy threshold", "spending limits",
             "source documents", "identical documents"]
    if title != DOCUMENT_REVIEW:
        found = [phrase for phrase in leaks if phrase.lower() in body.lower()]
        assert not found, f"{title} shows document-review copy: {found}"


@pytest.mark.parametrize("title", LEGACY_WORKFLOWS)
def test_no_model_spend_is_ever_triggered_without_consent(page, browser_servers, title):
    """The only paid action stays behind an unchecked acknowledgement."""
    run_sample_workflow(page, browser_servers, title)

    gate = page.locator("#run-all-ai-comparison")
    expect(gate).to_be_visible()
    expect(gate.get_by_role("checkbox")).not_to_be_checked()
    expect(gate.get_by_role("button", name=re.compile("comparison", re.I)).first).to_be_disabled()


def test_failed_outcome_shows_no_cost_benefit_at_all(page, browser_servers):
    """The code-change sample fails a real test, so no saving may be implied."""
    run_id = run_sample_workflow(page, browser_servers, CODE_CHANGE)
    proof = fetch_proof(page, browser_servers, run_id)
    assert proof["outcome"]["quality_passed"] is False, (
        "This case exists to exercise the failed-outcome state."
    )

    bar = page.locator(".claim-strength")
    expect(bar).to_have_class(re.compile("is-none"))
    expect(page.locator(".claim-strength-badge")).to_have_text("No savings shown")
    expect(bar).to_contain_text("Cost comparisons are hidden because the answer was not verified.")
    expect(bar).to_contain_text("A cheaper wrong answer is not a saving.")

    # Nothing celebratory survives a failed outcome.
    expect(page.locator(".work-avoided")).to_have_count(0)
    expect(page.locator(".comparison-chip.is-estimate")).to_have_count(0)
    expect(page.locator(".comparison-chip.is-proven")).to_have_count(0)
    expect(page.locator(".route-flow-before")).to_have_count(0)
    expect(page.locator(".prove-cards").get_by_text(re.compile("lower|avoided|saving"))).to_have_count(0)

    # The spend itself is still reported honestly.
    expect(page.get_by_text("What this run cost", exact=True)).to_be_visible()


# ------------------------------------------------------- Upload entry path


def test_document_review_upload_path_runs_end_to_end(page, browser_servers):
    """The upload source accepts real files and reaches a verified Prove screen."""
    choose_workflow(page, DOCUMENT_REVIEW)
    choose_source(page, UPLOAD)

    invoice = (
        b"Acme Supplies: Charge Review\n\n"
        b"| Line | Description | Amount | Reference |\n"
        b"| --- | --- | ---: | --- |\n"
        b"| 1 | Standard ground delivery | $700.00 | Shipment GB-1 |\n"
        b"| 2 | Weekend delivery surcharge | $150.00 | Shipment 990112 |\n"
    )
    policy = (
        b"Acme Freight Policy\n\n"
        b"## 1. Standard freight\n"
        b"Standard ground delivery is payable when it references a shipment.\n\n"
        b"## 2. Weekend delivery\n"
        b"Weekend delivery charges are payable only when a valid approval ID is listed.\n"
    )

    file_inputs = page.locator(".phase input[type=file]")
    expect(file_inputs.first).to_be_attached()
    file_inputs.nth(0).set_input_files(
        {"name": "invoice.md", "mimeType": "text/markdown", "buffer": invoice}
    )
    file_inputs.nth(1).set_input_files(
        {"name": "policy.md", "mimeType": "text/markdown", "buffer": policy}
    )

    run_id = start_run(page, browser_servers)
    open_phase(page, "Prove")
    proof = fetch_proof(page, browser_servers, run_id)

    # Real uploaded bytes, not a bundled sample.
    assert proof["status"].startswith("completed")
    assert proof.get("measurement_label") != "Measured sample run"
    expect(page.locator(".work-avoided")).to_be_visible()
    expect(page.locator(".claim-strength")).to_be_visible()


def test_code_change_upload_accepts_an_archive(page, browser_servers):
    """The code-change path takes a real ZIP and still routes locally first."""
    choose_workflow(page, CODE_CHANGE)
    choose_source(page, UPLOAD)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("app.py", "def total(price, quantity):\n    return price * quantity\n")
        archive.writestr(
            "test_app.py",
            "import unittest, app\n\n"
            "class T(unittest.TestCase):\n"
            "    def test_total(self):\n"
            "        self.assertEqual(app.total(5, 3), 15)\n",
        )

    page.locator(".phase input[type=file]").first.set_input_files(
        {"name": "project.zip", "mimeType": "application/zip", "buffer": buffer.getvalue()}
    )

    for field in page.locator(".phase textarea").all():
        if field.is_visible() and not field.input_value().strip():
            field.fill("Confirm the total calculation is correct.")
            break

    run_id = start_run(page, browser_servers)
    open_phase(page, "Prove")
    proof = fetch_proof(page, browser_servers, run_id)
    assert proof["usage"]["model_calls"] == 0, "Local mode must not invoke a model."
    expect(page.locator(".claim-strength")).to_be_visible()


# --------------------------------------------- Optimize workflow: three modes


@pytest.mark.parametrize(
    "mode",
    [
        "Analyze current workflow",
        "Optimize a prompt before you run it",
        "Measure an optimized workflow",
    ],
)
def test_optimize_workflow_modes_switch_the_work_area(page, mode):
    """Image 4: the three modes each present their own Step 1 work area."""
    choose_workflow(page, OPTIMIZE)
    expect(page.get_by_role("heading", name="Optimize AI Prompt or Workflow")).to_be_visible()
    page.get_by_role("radio", name=re.compile("^" + re.escape(mode))).check()

    if mode.startswith("Optimize a prompt"):
        expect(page.get_by_role("heading", name="Provide the prompt")).to_be_visible()
        for source in ("Paste a prompt", "Add context or files", "Use a prompt example"):
            expect(page.get_by_role("button", name=source, exact=True)).to_be_visible()
        expect(page.get_by_label(re.compile("^User prompt"))).to_be_visible()
    else:
        expect(page.get_by_role("heading", name="Provide an existing AI workflow")).to_be_visible()
        expect(page.get_by_label(re.compile("^User prompt"))).to_have_count(0)
        expect(page.get_by_role("button", name="Use a measured example", exact=True)).to_be_visible()


def test_prompt_example_completes_all_seven_phases(page, browser_servers):
    """Image 4's prompt path, driven to a verified proof with no model spend."""
    choose_workflow(page, OPTIMIZE)
    page.get_by_role("radio", name=re.compile("^Optimize a prompt before you run it")).check()
    page.get_by_role("button", name="Use a prompt example", exact=True).click()

    examples = page.request.get(
        f"{browser_servers['api']}/api/optimization/prompt-examples"
    ).json()["examples"]
    lookup = next(item for item in examples if item["id"] == "repeated_policy_lookup")
    page.get_by_role("radio", name=re.compile("^" + re.escape(lookup["title"]))).check()

    with page.expect_response(
        lambda response: response.url == browser_servers["api"] + "/api/runs"
        and response.request.method == "POST"
    ) as created:
        page.get_by_role("button", name="Build prompt optimization plan", exact=True).click()
    run_id = created.value.json()["runId"]

    page.get_by_role("button", name="Authorize protected prompt run", exact=True).click()
    expect(page.locator(".optimization-hero")).to_be_visible(timeout=30000)

    proof = page.request.get(f"{browser_servers['api']}/api/runs/{run_id}/proof").json()
    assert proof["verification"]["passed"] is True
    assert proof["cost"]["modelCalls"] == 0
    assert proof["baseline"]["eligible"] is False
    expect(page.get_by_role("heading", name="Comparison not run", exact=True)).to_be_visible()


def test_measured_workflow_example_completes_all_seven_phases(page, browser_servers):
    """Image 4's measured path, driven to a verified proof with no model spend."""
    choose_workflow(page, OPTIMIZE)
    page.get_by_role("radio", name=re.compile("^Measure an optimized workflow")).check()
    page.get_by_role("button", name="Use a measured example", exact=True).click()

    with page.expect_response(
        lambda response: response.url == browser_servers["api"] + "/api/runs"
        and response.request.method == "POST"
    ) as created:
        page.get_by_role(
            "button", name="Analyze workflow and build an optimization plan", exact=True
        ).click()
    run_id = created.value.json()["runId"]

    page.get_by_role("button", name="Authorize protected run", exact=True).click()
    expect(page.locator(".optimization-hero")).to_be_visible(timeout=30000)

    proof = page.request.get(f"{browser_servers['api']}/api/runs/{run_id}/proof").json()
    assert proof["verification"]["passed"] is True
    assert proof["cost"]["modelCalls"] == 0
    assert "Measured sample run" in proof["badges"]
    expect(page.get_by_role("heading", name="Verified saving", exact=True)).to_have_count(0)


# ------------------------------------------------------------- cross-cutting


@pytest.mark.parametrize("title", LEGACY_WORKFLOWS)
def test_finished_run_reports_no_console_errors(page, browser_servers, title):
    """A first-time user must not hit a broken screen on any entry path."""
    errors = []
    page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
    page.on("pageerror", lambda error: errors.append(str(error)))

    run_sample_workflow(page, browser_servers, title)
    for phase in PHASES[1:]:
        open_phase(page, phase)

    ignorable = re.compile("favicon|ERR_INTERNET_DISCONNECTED", re.I)
    real = [message for message in errors if not ignorable.search(message)]
    assert not real, f"{title} produced console errors: {real}"


@pytest.mark.parametrize("width", [1440, 1024, 768])
def test_prove_layout_holds_at_supported_widths(page, browser_servers, width):
    """The redesigned hero must not clip or overflow at any supported width."""
    run_sample_workflow(page, browser_servers, DEADLINE)
    page.set_viewport_size({"width": width, "height": 1100})

    metrics = page.evaluate(
        """() => ({ scrollWidth: document.documentElement.scrollWidth,
                    clientWidth: document.documentElement.clientWidth })"""
    )
    assert metrics["scrollWidth"] <= metrics["clientWidth"] + 1, f"{width}px overflow: {metrics}"

    rows = page.evaluate(
        """() => {
            const groups = {};
            for (const card of document.querySelectorAll('.prove-cards .comparison-card')) {
                const row = Math.round(card.getBoundingClientRect().top);
                const value = Math.round(card.querySelector('.comparison-value').getBoundingClientRect().top);
                (groups[row] = groups[row] || []).push(value);
            }
            return Object.values(groups);
        }"""
    )
    for tops in rows:
        # Sub-pixel rounding at fractional grid widths can differ by 1px; anything
        # larger is a genuine misalignment a user would notice.
        assert max(tops) - min(tops) <= 1, f"Hero values misaligned at {width}px: {tops}"
