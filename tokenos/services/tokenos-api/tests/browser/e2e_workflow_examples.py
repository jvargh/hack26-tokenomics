"""Complete workflow-example forms in both modes, including immediate source entry."""

import re

import pytest
from playwright.sync_api import expect

from e2e_optimization import (
    MODE_ANALYZE, MODE_MEASURE, MODE_PROMPT, approve_to_protect, build_plan,
    choose_mode, choose_optimization, execute_to_prove, screenshot,
)


def sample_catalog(page, api_url):
    return page.request.get(f"{api_url}/api/optimization/samples").json()["samples"]


def assert_workflow_defaults(page, sample):
    expect(page.get_by_role("radio", name=re.compile("^" + re.escape(sample["title"])))).to_be_checked()
    expect(page.get_by_label("Current workflow description (required)", exact=True)).to_have_value(sample["description"])
    expect(page.get_by_label("Desired outcome (required)", exact=True)).to_have_value(sample["desiredOutcome"])
    expect(page.get_by_label("Expected recurring volume (optional)", exact=True)).to_have_value(str(sample["recurringVolume"]["value"]))
    expect(page.get_by_label("Volume period", exact=True)).to_have_value(sample["recurringVolume"]["period"])
    requirements = sample["requirements"]
    for label, key in (
        ("Optimization goal (required)", "optimizationGoal"),
        ("Maximum authorized model spend (USD)", "maxModelSpendUsd"),
        ("Maximum allowed input/context tokens", "maxInputTokens"),
        ("Maximum output tokens", "maxOutputTokens"),
        ("Maximum advanced calls per run", "maxAdvancedCalls"),
        ("Required latency target (milliseconds)", "latencyTargetMs"),
    ):
        expect(page.get_by_label(label, exact=True)).to_have_value(str(requirements[key]))
    for key, label in (
        ("same_answer_quality", "Same decision or answer quality"),
        ("grounded_citations", "Required citations or grounded evidence"),
        ("structured_output", "Structured output remains valid"),
        ("required_tests", "Required test suite passes"),
        ("latency_target", "Response meets a latency target"),
        ("human_approval", "Human approval remains required for selected outcomes"),
    ):
        expect(page.get_by_role("checkbox", name=label, exact=True)).to_be_checked(
            checked=key in requirements["qualityRequirements"]
        )
    expect(page.get_by_role("button", name="Analyze workflow and build an optimization plan", exact=True)).to_be_enabled()
    expect(page.get_by_label("User prompt (required)", exact=True)).to_have_count(0)


@pytest.mark.parametrize("mode", [MODE_ANALYZE, MODE_MEASURE])
@pytest.mark.parametrize("sample_id", ["customer_assistance", "policy_review", "code_validation", "classification"])
def test_every_workflow_example_fills_and_submits_without_edits(page, browser_servers, mode, sample_id):
    choose_optimization(page, mode)
    page.get_by_role("button", name="Use a measured example", exact=True).click()
    samples = sample_catalog(page, browser_servers["api"])
    # Entering the source alone must initialize the first example, not show placeholders.
    assert_workflow_defaults(page, samples[0])
    sample = next(item for item in samples if item["id"] == sample_id)
    page.get_by_role("radio", name=re.compile("^" + re.escape(sample["title"]))).check()
    assert_workflow_defaults(page, sample)
    if sample_id == "customer_assistance":
        screenshot(page, "workflow-defaults-analyze" if mode == MODE_ANALYZE else "workflow-defaults-measure")
    if mode == MODE_ANALYZE:
        expect(page.get_by_text(sample["analysisNotice"], exact=False)).to_be_visible()
    with page.expect_response(
        lambda response: response.url == browser_servers["api"] + "/api/runs"
        and response.request.method == "POST"
    ) as created:
        run_id = build_plan(page, browser_servers["api"], spends=mode != MODE_ANALYZE)
    submitted = created.value.request.post_data_json
    assert submitted["inputs"]["workflowDescription"] == sample["description"]
    assert submitted["inputs"]["desiredOutcome"] == sample["desiredOutcome"]
    assert submitted["inputs"]["sampleId"] == sample_id
    assert "userPrompt" not in submitted["inputs"]
    for key, value in sample["requirements"].items():
        assert submitted["requirements"][key] == value
    state = page.request.get(f"{browser_servers['api']}/api/runs/{run_id}").json()
    if mode == MODE_ANALYZE:
        # Analyze cannot invoke a model, so it needs no authorization and runs on.
        assert state["status"] == "completed" and state["proof"] is not None
        assert state["proof"]["modelUsage"] == []
    else:
        # Plan and Optimize compile automatically; nothing has executed yet.
        assert state["status"] == "optimized" and state["proof"] is None
    assert state["currentRoute"]["modelSpendUsd"] is None
    assert state["badges"] == ["Measured sample run"]


def test_mode_and_source_switches_never_reuse_unrelated_prompt_values(page, browser_servers):
    choose_optimization(page, MODE_PROMPT)
    page.get_by_role("button", name="Use a prompt example", exact=True).click()
    # Prompt source entry is also immediately initialized, without selecting another radio.
    expect(page.get_by_role("button", name="Build prompt optimization plan", exact=True)).to_be_enabled()
    prompt_outcome = page.get_by_label("Desired outcome (required)", exact=True).input_value()
    samples = sample_catalog(page, browser_servers["api"])
    choose_mode(page, MODE_MEASURE)
    assert_workflow_defaults(page, samples[0])
    assert samples[0]["desiredOutcome"] != prompt_outcome
    for sample in samples[1:]:
        page.get_by_label("Current workflow description (required)", exact=True).fill("")
        page.get_by_label("Desired outcome (required)", exact=True).fill("Previous prompt outcome")
        page.get_by_role("checkbox", name="Required test suite passes", exact=True).check()
        page.get_by_role("radio", name=re.compile("^" + re.escape(sample["title"]))).check()
        assert_workflow_defaults(page, sample)
    choose_mode(page, MODE_ANALYZE)
    assert_workflow_defaults(page, samples[-1])
    page.get_by_role("button", name="Upload workflow data", exact=True).click()
    page.get_by_label("Desired outcome (required)", exact=True).fill("Unrelated uploaded outcome")
    page.get_by_role("button", name="Use a measured example", exact=True).click()
    assert_workflow_defaults(page, samples[-1])


def test_sample_catalog_arriving_later_initializes_defaults_once(page, browser_servers):
    pending = []
    endpoint = browser_servers["api"] + "/api/optimization/samples"
    page.route(endpoint, lambda route: pending.append(route))
    choose_optimization(page, MODE_MEASURE)
    action = page.get_by_role("button", name="Analyze workflow and build an optimization plan", exact=True)
    expect(action).to_be_disabled()
    expect(page.get_by_text("Measured examples are unavailable. Retry the connection or provide your own inputs.", exact=True)).to_be_visible()
    assert pending
    # Delay delivery of the real catalog, not a substitute execution result.
    response = page.request.get(endpoint)
    first = response.json()["samples"][0]
    for route in pending:
        route.fulfill(response=response)
    assert_workflow_defaults(page, first)
    page.get_by_label("Current workflow description (required)", exact=True).fill("My edited workflow description")
    page.get_by_label("Desired outcome (required)", exact=True).fill("My edited required outcome")
    expect(page.get_by_label("Current workflow description (required)", exact=True)).to_have_value("My edited workflow description")
    expect(page.get_by_label("Desired outcome (required)", exact=True)).to_have_value("My edited required outcome")
    expect(action).to_be_enabled()


@pytest.mark.parametrize("mode", [MODE_ANALYZE, MODE_MEASURE])
def test_default_example_reaches_proof_without_manual_input(page, browser_servers, mode):
    analyzing = mode == MODE_ANALYZE
    choose_optimization(page, mode)
    page.get_by_role("button", name="Use a measured example", exact=True).click()
    run_id = build_plan(page, browser_servers["api"], spends=not analyzing)
    if not analyzing:
        approve_to_protect(page)
    proof = execute_to_prove(page, browser_servers["api"], run_id,
                             authorize=None if analyzing else "Authorize protected run")
    assert proof["modelUsage"] == []
    assert proof["badges"] == ["Measured sample run"]
    assert proof["baseline"]["eligible"] is False
    assert proof["verification"]["passed"] is (mode == MODE_MEASURE)
    if analyzing:
        assert proof["cost"]["modelSpendUsd"] is None
        expect(page.get_by_role("button", name="Run all-AI comparison", exact=True)).to_have_count(0)
        # Nothing was spent, so nothing was authorized.
        expect(page.get_by_role("button", name="Authorize protected run", exact=True)).to_have_count(0)
    else:
        assert proof["verification"]["processed"] == proof["verification"]["total"] == 4
