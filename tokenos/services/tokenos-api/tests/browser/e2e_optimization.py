"""Run explicitly: python -m pytest -c pytest-browser.ini -v.

These tests use real HTTP, SSE, uploads, persistence, and local execution. They
never install a fake provider in the application or spend live model tokens.
"""

from __future__ import annotations

import os
import hashlib
import json
from pathlib import Path
import re
import time

import pytest
from playwright.sync_api import expect

TITLE = "Optimize an existing AI workflow"
DESCRIPTION = (
    "Connect an AI application or prior run. TokenOS finds the lowest-cost route "
    "that still meets the required quality."
)


MODE_ANALYZE = "Analyze current workflow"
MODE_PROMPT = "Optimize a prompt before you run it"
MODE_MEASURE = "Measure an optimized workflow"


def choose_mode(page, title):
    """Prompt mode is the default, so workflow tests select their mode explicitly."""
    radio = page.get_by_role("radio", name=re.compile("^" + re.escape(title)))
    expect(radio).to_be_visible()
    radio.check()


def choose_optimization(page, mode=MODE_MEASURE):
    card = page.get_by_role("button", name=re.compile("^" + TITLE))
    expect(card).to_be_visible()
    card.click()
    if mode:
        choose_mode(page, mode)


def screenshot(page, name):
    directory = os.getenv("TOKENOS_SCREENSHOT_DIR")
    if directory:
        destination = Path(directory)
        destination.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(destination / f"{name}.png"), full_page=True)


def wait_for_proof(page, api_url, run_id):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        response = page.request.get(f"{api_url}/api/runs/{run_id}/proof")
        body = response.json()
        if response.status == 200 and ("workflow_id" in body or "workflow" in body):
            return body
        time.sleep(0.1)
    raise AssertionError(f"No completed proof for {run_id}: {body}")


def test_approved_copy_and_accessibility(page):
    expect(page.get_by_role("heading", name="What do you want TokenOS to optimize?")).to_be_visible()
    expect(page.get_by_text(
        "Choose a workflow, provide the real work, and TokenOS will find the "
        "least-expensive safe route and prove the result.", exact=True
    )).to_be_visible()
    for title in (
        "Review documents against rules", "Test a code change",
        "Process records by a deadline", TITLE,
    ):
        expect(page.get_by_role("button", name=re.compile("^" + title))).to_be_visible()
    expect(page.get_by_role("button", name=re.compile("^Compare AI options and prove value"))).to_have_count(0)
    card = page.get_by_role("button", name=re.compile("^" + TITLE))
    card.click()
    expect(page.get_by_role("heading", name="Optimize AI Prompt or Workflow", exact=True)).to_be_visible()
    expect(page.get_by_text(
        "Start with a prompt or workflow. TokenOS reduces AI waste while "
        "preserving required quality and outcomes.", exact=True
    )).to_be_visible()
    modes = page.get_by_role("radiogroup", name="What do you want to improve?", exact=True)
    expect(modes).to_be_visible()
    for title in (MODE_ANALYZE, MODE_PROMPT, MODE_MEASURE):
        expect(page.get_by_role("radio", name=re.compile("^" + re.escape(title)))).to_be_visible()
    expect(page.get_by_role("radio", name=re.compile("^" + re.escape(MODE_PROMPT)))).to_be_checked()
    expect(page.get_by_role("heading", name="Provide the prompt", exact=True)).to_be_visible()
    choose_mode(page, MODE_MEASURE)
    expect(page.get_by_text(DESCRIPTION, exact=True).first).to_be_visible()
    expect(page.get_by_role("heading", name="Provide an existing AI workflow")).to_be_visible()
    screenshot(page, "01-describe")


def test_input_paths_and_required_description(page):
    choose_optimization(page)
    for title in ("Upload workflow data", "Connect an AI application", "Use a measured example"):
        expect(page.get_by_role("button", name=re.compile("^" + title))).to_be_visible()
    expect(page.get_by_text(
        "A connected application is a TokenOS-registered application and approved data scope. "
        "It does not automatically connect to an Azure subscription. "
        "Provider credentials never reach the browser.", exact=True
    )).to_be_visible()
    # Desired outcome is a shared required field for every mode, so a complete
    # form enables the action and clearing the description alone disables it.
    quality_and_goal(page)
    page.get_by_role("button", name=re.compile("^Use a measured example")).click()
    page.get_by_role("radio", name=re.compile("^Repeated customer-assistance prompts")).check()
    action = page.get_by_role(
        "button", name="Analyze workflow and build an optimization plan", exact=True
    )
    expect(action).to_be_enabled()
    description = page.get_by_label(re.compile("^Current workflow description"))
    description.fill("")
    expect(action).to_be_disabled()


def test_connected_path_has_scoped_selection(page):
    choose_optimization(page)
    page.get_by_role("button", name=re.compile("^Connect an AI application")).click()
    expect(page.get_by_label("Registered application", exact=True)).to_be_visible()
    expect(page.get_by_label("Time range", exact=True)).to_be_visible()
    expect(page.get_by_text(re.compile("does not automatically connect to an Azure subscription"))).to_be_visible()
    screenshot(page, "01-connected")


def test_four_measured_fixtures_are_available(page):
    choose_optimization(page)
    page.get_by_role("button", name=re.compile("^Use a measured example")).click()
    for title in (
        "Repeated customer-assistance prompts with reusable context",
        "Policy document review with one genuine interpretation exception",
        "Code-change validation with a failed test requiring bounded diagnosis",
        "High-volume classification with a small ambiguous subset",
    ):
        expect(page.get_by_role("radio", name=re.compile("^" + title))).to_be_visible()


def quality_and_goal(page):
    for label in ("Same decision or answer quality", "Required citations or grounded evidence",
                  "Structured output remains valid"):
        page.get_by_role("checkbox", name=label, exact=True).check()
    page.get_by_label("Optimization goal (required)", exact=True).select_option("cost_per_accepted_outcome")
    # Shared required field across all three modes.
    page.get_by_label(re.compile("^Desired outcome")).fill(
        "Produce the required decision with grounded evidence and valid structured output."
    )


def build_plan(page, api_url):
    with page.expect_response(lambda response: response.url == api_url + "/api/runs"
                              and response.request.method == "POST") as created:
        page.get_by_role("button", name="Analyze workflow and build an optimization plan", exact=True).click()
    response = created.value
    assert response.status == 200, response.text()
    # Plan and Optimize compile locally and spend nothing, so the journey runs
    # straight through to the authorization gate. Both stay open for inspection.
    expect(page.get_by_role("heading", name="Execution safeguards", exact=True)).to_be_visible()
    return response.json()["runId"]


def open_optimization_phase(page, name):
    """Navigates the optimization stepper the way a user inspects a phase."""
    stepper = page.get_by_role("navigation", name="Optimization workflow progress")
    button = stepper.get_by_role("button", name=re.compile(f"^{name}"))
    expect(button).to_be_enabled(timeout=30000)
    button.click()


def approve_to_protect(page, capture=False):
    """Visits the auto-compiled Plan and Optimize phases, then returns to Protect."""
    open_optimization_phase(page, "Plan")
    expect(page.get_by_role("heading", name="Current workflow map", exact=True)).to_be_visible()
    if capture:
        screenshot(page, "02-plan")
    open_optimization_phase(page, "Optimize")
    expect(page.get_by_role("heading", name="Optimization levers", exact=True)).to_be_visible()
    if capture:
        screenshot(page, "03-optimize")
    open_optimization_phase(page, "Protect")
    expect(page.get_by_role("heading", name="Execution safeguards", exact=True)).to_be_visible()
    if capture:
        screenshot(page, "04-protect")


def execute_to_prove(page, api_url, run_id, capture=False, authorize="Authorize protected run"):
    """Authorizing is the single deliberate decision; execution follows from it."""
    page.get_by_role("button", name=authorize, exact=True).click()
    # The journey lands on Prove by itself once the run finishes.
    expect(page.get_by_role("button", name="Download the full proof", exact=True).or_(
        page.locator(".optimization-hero")
    ).first).to_be_visible(timeout=30000)
    proof = wait_for_proof(page, api_url, run_id)
    if capture:
        screenshot(page, "05-run")
        open_optimization_phase(page, "Verify")
        expect(page.get_by_role("heading", name="Verified outcome", exact=True)).to_be_visible()
        screenshot(page, "06-verify")
        open_optimization_phase(page, "Prove")
    return proof


def sample_plan(page, api_url, title="Repeated customer-assistance prompts with reusable context"):
    choose_optimization(page)
    page.get_by_role("radio", name=re.compile("^" + title)).check()
    quality_and_goal(page)
    return build_plan(page, api_url)


def test_seven_phases_sse_proof_baseline_and_history(page, browser_servers):
    requests = []
    page.on("request", lambda request: requests.append((request.url, request.resource_type)))
    choose_optimization(page)
    page.get_by_role("radio", name=re.compile("^Repeated customer-assistance prompts")).check()
    quality_and_goal(page)
    page.get_by_label("Expected recurring volume (optional)", exact=True).fill("10000")
    run_id = build_plan(page, browser_servers["api"])
    approve_to_protect(page, capture=True)
    page.get_by_role("button", name="Refresh safeguards", exact=True).click()
    expect(page.get_by_role("button", name="Authorize protected run", exact=True)).to_be_enabled()
    proof = execute_to_prove(page, browser_servers["api"], run_id, capture=True)
    expect(page.get_by_role("heading", name="Verified outcome. Minimal AI use. Measured cost proof.", exact=True)).to_be_visible()
    assert proof["verification"]["passed"] is True
    assert proof["verification"]["processed"] == proof["verification"]["total"] == 4
    assert proof["cost"]["modelCalls"] == 0
    assert proof["cost"]["modelSpendUsd"] == 0
    assert proof["cost"]["localOperations"] == 2
    assert proof["cost"]["reuseOperations"] == 2
    assert proof["baseline"]["eligible"] is False
    assert any(url.endswith(f"/api/runs/{run_id}/events?last_event_id=0") or
               f"/api/runs/{run_id}/events?" in url or
               url.endswith(f"/api/runs/{run_id}/events")
               for url, kind in requests if kind == "eventsource")
    expect(page.get_by_role("heading", name="Comparison not run", exact=True)).to_be_visible()
    expect(page.get_by_role("heading", name="Verified saving", exact=True)).to_have_count(0)
    expect(page.get_by_role("heading", name="Projected cost at volume", exact=True)).to_be_visible()
    for summary in ("Outcome evidence: why quality passed", "Technical evidence and run proof"):
        details = page.locator("details").filter(has=page.locator("summary", has_text=summary))
        expect(details).not_to_have_attribute("open", "")
    # The Prove hero now uses the same before/after cards as the other workflows.
    assert page.locator(".prove-cards .comparison-card").count() == 4
    expect(page.locator(".work-avoided")).to_be_visible()
    expect(page.get_by_text("Measured sample run", exact=True).first).to_be_visible()
    screenshot(page, "07-prove")
    comparison = page.get_by_role("button", name="Run all-AI comparison", exact=True)
    expect(comparison).to_be_disabled()
    page.get_by_role("checkbox", name="I understand this comparison invokes a model and may incur model cost.", exact=True).check()
    with page.expect_response(lambda response: response.url.endswith(f"/api/runs/{run_id}/baseline")) as compared:
        comparison.click()
    assert compared.value.status in (200, 409, 503), compared.value.text()
    expect(page.get_by_role("heading", name="Verified saving", exact=True)).to_have_count(0)
    state = page.request.get(f"{browser_servers['api']}/api/runs/{run_id}").json()
    assert state["proof"]["cost"]["modelCalls"] == 0
    page.get_by_role("button", name="History", exact=True).click()
    history = page.get_by_role("dialog", name="Run history", exact=True)
    entry = history.get_by_role("button", name=f"Open {TITLE} proof {run_id}", exact=True)
    expect(entry).to_be_visible()
    screenshot(page, "08-history")
    entry.click()
    page.reload(wait_until="networkidle")
    expect(page.get_by_text(TITLE, exact=True).first).to_be_visible()
    expect(page.get_by_role("heading", name="Verified outcome. Minimal AI use. Measured cost proof.", exact=True)).to_be_visible()


@pytest.mark.parametrize("title", [
    "Policy document review with one genuine interpretation exception",
    "Code-change validation with a failed test requiring bounded diagnosis",
    "High-volume classification with a small ambiguous subset",
])
def test_real_ambiguities_block_without_foundry(page, browser_servers, title):
    run_id = sample_plan(page, browser_servers["api"], title)
    approve_to_protect(page)
    expect(page.get_by_role("button", name="Authorize protected run", exact=True)).to_be_disabled()
    expect(page.get_by_text("Foundry is unavailable. Configure server-side deployments and credentials.", exact=True)).to_be_visible()
    state = page.request.get(f"{browser_servers['api']}/api/runs/{run_id}").json()
    assert state["status"] == "optimized"
    assert state["proof"] is None
    assert not state.get("modelUsage")


def representative_fixture(wrong=False):
    return [{
        "id": f"uploaded-{index}", "taskType": "lookup", "input": "return window",
        "context": [{"id": "returns#window", "key": "return window",
                     "text": "Returns are accepted within 30 days.",
                     "output": {"decision": "30 days", "citations": ["returns#window"]}}],
        "expectedOutput": {"decision": "wrong" if wrong else "30 days", "citations": ["returns#window"]},
    } for index in range(3)]


def test_upload_manifest_and_real_measured_execution(page, browser_servers):
    choose_optimization(page)
    page.get_by_role("button", name=re.compile("^Upload workflow data")).click()
    content = (Path(__file__).resolve().parents[4] / "samples" / "optimization-requests.json").read_bytes()
    page.get_by_label(re.compile("^Representative test inputs")).set_input_files({
        "name": "representative.json", "mimeType": "application/json", "buffer": content,
    })
    expect(page.get_by_text(hashlib.sha256(content).hexdigest(), exact=True)).to_be_visible()
    page.get_by_label("Current workflow description (required)", exact=True).fill("An existing FAQ assistant reprocesses stable policy sources.")
    quality_and_goal(page)
    run_id = build_plan(page, browser_servers["api"])
    approve_to_protect(page)
    proof = execute_to_prove(page, browser_servers["api"], run_id)
    assert proof["verification"]["passed"]
    assert proof["cost"]["modelCalls"] == 0
    assert "Measured sample run" not in proof["badges"]
    expect(page.get_by_text("Measured sample run", exact=True)).to_have_count(0)


def test_upload_rejects_unsupported_and_oversized_files(page):
    choose_optimization(page)
    page.get_by_role("button", name=re.compile("^Upload workflow data")).click()
    upload = page.get_by_label("AI workflow export", exact=True)
    for name, content in (("invalid.exe", b"not supported"), ("oversized.json", b" " * (10 * 1024 * 1024 + 1))):
        upload.set_input_files({"name": name, "mimeType": "application/octet-stream", "buffer": content})
        expect(page.get_by_text("Choose a supported, nonempty file up to 10 MB. Larger workloads should use a representative input package.", exact=True)).to_be_visible()


def test_failed_output_never_offers_baseline(page, browser_servers):
    choose_optimization(page)
    page.get_by_role("button", name=re.compile("^Upload workflow data")).click()
    page.get_by_label("Or paste 3 to 20 representative requests", exact=True).fill(json.dumps(representative_fixture(wrong=True)))
    page.get_by_label("Current workflow description (required)", exact=True).fill("Validate real outputs against deliberately failing acceptance references.")
    quality_and_goal(page)
    run_id = build_plan(page, browser_servers["api"])
    approve_to_protect(page)
    proof = execute_to_prove(page, browser_servers["api"], run_id)
    assert proof["verification"]["passed"] is False
    expect(page.get_by_role("button", name="Run all-AI comparison", exact=True)).to_have_count(0)
    expect(page.get_by_role("heading", name="Verified saving", exact=True)).to_have_count(0)
    page.get_by_role("navigation", name="Optimization workflow progress").get_by_role("button", name=re.compile("^Verify")).click()
    for name in ("Inspect failed checks", "Adjust plan", "Escalate with approval"):
        expect(page.get_by_role("button", name=name, exact=True)).to_be_visible()
    page.get_by_role("button", name="Inspect failed checks", exact=True).click()
    expect(page.locator("details").filter(has=page.locator("summary", has_text="Outcome evidence"))).to_have_attribute("open", "")


def test_analyze_mode_remains_telemetry_not_verified_execution(page, browser_servers):
    choose_optimization(page, MODE_ANALYZE)
    page.get_by_role("button", name=re.compile("^Upload workflow data")).click()
    telemetry = json.dumps({"records": [{
        "requestId": f"prior-{index}", "providerRequestId": f"provider-{index}",
        "deployment": "unknown-imported-deployment", "inputTokens": 100,
        "outputTokens": 10, "cachedInputTokens": 0, "reasoningTokens": 0,
        "latencyMs": 12, "outcomeStatus": "accepted", "retryCount": 0,
    } for index in range(3)]}).encode()
    page.get_by_label("AI workflow export (required for analysis)", exact=True).set_input_files({
        "name": "telemetry.json", "mimeType": "application/json", "buffer": telemetry,
    })
    expect(page.get_by_text(hashlib.sha256(telemetry).hexdigest(), exact=True)).to_be_visible()
    page.get_by_label("Current workflow description (required)", exact=True).fill("Inspect historical usage; no replay requested.")
    quality_and_goal(page)
    run_id = build_plan(page, browser_servers["api"])
    approve_to_protect(page)
    proof = execute_to_prove(page, browser_servers["api"], run_id)
    assert proof["mode"] == "analyze"
    assert proof["verification"]["passed"] is False
    assert proof["modelUsage"] == []
    assert proof["cost"]["modelSpendUsd"] is None
    expect(page.get_by_text("Telemetry analysis is not an executed optimized route. Candidate improvements are recommendations only.", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="Run all-AI comparison", exact=True)).to_have_count(0)
    screenshot(page, "07-analyze")


def test_connected_sample_scopes_and_human_approval(page, browser_servers):
    choose_optimization(page)
    page.get_by_role("button", name=re.compile("^Connect an AI application")).click()
    page.get_by_label("Registered application", exact=True).select_option("support-archive")
    page.get_by_label("Workflow or trace (optional)", exact=True).select_option("support-september")
    page.get_by_label("Current workflow description (required)", exact=True).fill("Use only the registered approved support scope.")
    quality_and_goal(page)
    page.get_by_role("checkbox", name="Human approval remains required for selected outcomes", exact=True).check()
    run_id = build_plan(page, browser_servers["api"])
    approve_to_protect(page)
    expect(page.get_by_role("button", name="Authorize protected run", exact=True)).to_be_disabled()
    page.get_by_role("checkbox", name="I have reviewed the selected outcomes and grant the required human approval for this run.", exact=True).check()
    proof = execute_to_prove(page, browser_servers["api"], run_id)
    assert proof["verification"]["passed"] is True
    assert proof["dimensions"]["application"] == "support-archive"
    assert proof["dimensions"]["proofType"] == "sample"
    assert "Measured sample run" in proof["badges"]


def test_sse_failure_uses_authoritative_polling(page, browser_servers):
    run_id = sample_plan(page, browser_servers["api"])
    approve_to_protect(page)
    requests = []
    page.on("request", lambda request: requests.append(request.url))
    page.route(f"**/api/runs/{run_id}/events*", lambda route: route.abort("connectionfailed"))
    proof = execute_to_prove(page, browser_servers["api"], run_id)
    assert proof["verification"]["passed"] is True
    assert proof["cost"]["modelCalls"] == 0
    assert any(url.endswith(f"/api/runs/{run_id}") for url in requests)


@pytest.mark.parametrize("title,workflow_id", [
    ("Review documents against rules", "document_review"),
    ("Test a code change", "software_validation"),
    ("Process records by a deadline", "deadline_processing"),
])
def test_original_workflows_keep_real_execution(page, browser_servers, title, workflow_id):
    page.get_by_role("button", name=re.compile("^" + title)).click()
    page.get_by_role("button", name="Load sample data", exact=True).click()
    action = page.get_by_role("button", name="Analyze with TokenOS", exact=True)
    expect(action).to_be_enabled()
    with page.expect_response(
        lambda response: response.url == browser_servers["api"] + "/api/runs"
        and response.request.method == "POST"
    ) as started:
        action.click()
    response = started.value
    assert response.ok, response.text()
    run_id = response.json()["run_id"]
    proof = wait_for_proof(page, browser_servers["api"], run_id)
    assert proof.get("workflow_id") == workflow_id, proof
    assert proof["status"].startswith("completed")
    assert proof["usage"]["model_calls"] == 0
    assert proof["measurement_label"] == "Measured sample run"
