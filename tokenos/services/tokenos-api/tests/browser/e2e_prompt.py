"""Prompt-mode acceptance tests.

Run explicitly: python -m pytest -c pytest-browser.ini -v

Real HTTP, SSE, uploads, persistence and local execution. No fake provider is
installed in the application and no live model tokens are spent.
"""

from __future__ import annotations

import hashlib
import json
import re
import time

import pytest
from playwright.sync_api import expect

from e2e_optimization import (
    MODE_ANALYZE,
    MODE_MEASURE,
    MODE_PROMPT,
    TITLE,
    choose_mode,
    screenshot,
    wait_for_proof,
)

SECTION_HEADING = "Optimize AI Prompt or Workflow"
SECTION_DESCRIPTION = (
    "Start with a prompt or workflow. TokenOS reduces AI waste while "
    "preserving required quality and outcomes."
)
PROMPT_PLACEHOLDER = (
    "Analyze everything below, review every policy and prior interaction, "
    "explain all possible options in detail, and produce the best possible response."
)
VERBOSE_PROMPT = (
    "Please review absolutely everything attached, consider every prior conversation "
    "turn, evaluate every policy in full detail, and then explain at length all the "
    "possible options before giving me the best possible answer about the return window."
)

# A keyed context artifact the deterministic retriever can actually prove.
GROUNDED_CONTEXT = [
    {
        "id": "returns#window",
        "key": "return window",
        "text": "Returns are accepted within 30 days.",
        "output": {"decision": "30 days", "citations": ["returns#window"]},
    },
    {"id": "shipping#standard", "text": "Standard shipping takes 3 business days."},
    {"id": "billing#invoices", "text": "Invoices are issued monthly in arrears."},
]


def open_prompt_mode(page):
    page.get_by_role("button", name=re.compile("^" + TITLE)).click()
    choose_mode(page, MODE_PROMPT)
    expect(page.get_by_role("heading", name="Provide the prompt", exact=True)).to_be_visible()


def fill_shared_requirements(page, quality=("Structured output remains valid",),
                             goal="cost_per_accepted_outcome"):
    for label in quality:
        page.get_by_role("checkbox", name=label, exact=True).check()
    page.get_by_label(re.compile("^Optimization goal")).select_option(goal)


def build_plan(page, api_url):
    action = page.get_by_role("button", name="Build prompt optimization plan", exact=True)
    expect(action).to_be_enabled()
    with page.expect_response(
        lambda response: response.url == api_url + "/api/runs"
        and response.request.method == "POST"
    ) as created:
        action.click()
    response = created.value
    assert response.status == 200, response.text()
    body = response.json()
    assert body["optimizationTarget"] == "single_prompt"
    expect(page.get_by_role("heading", name="Prompt composition", exact=True)).to_be_visible()
    return body["runId"]


def paste_grounded_prompt(page, prompt=VERBOSE_PROMPT):
    page.get_by_role("button", name=re.compile("^Paste a prompt")).click()
    page.get_by_label(re.compile("^User prompt")).fill(prompt)
    page.get_by_label(re.compile("^Desired outcome")).fill(
        "Return the applicable return window with a citation to the governing policy."
    )
    page.get_by_label(re.compile("^Current model")).select_option("advanced")
    page.get_by_label(re.compile("^Output format")).select_option("json")


def attach_context(page, records=GROUNDED_CONTEXT, name="policy-context.json"):
    page.get_by_role("button", name=re.compile("^Add context or files")).click()
    content = json.dumps(records).encode()
    page.get_by_label("Context artifacts", exact=True).set_input_files(
        {"name": name, "mimeType": "application/json", "buffer": content}
    )
    expect(page.get_by_text(hashlib.sha256(content).hexdigest(), exact=True)).to_be_visible()
    return content


# --------------------------------------------------------------------------- copy


def test_mode_section_copy_is_exact(page):
    page.get_by_role("button", name=re.compile("^" + TITLE)).click()
    expect(page.get_by_role("heading", name=SECTION_HEADING, exact=True)).to_be_visible()
    expect(page.get_by_text(SECTION_DESCRIPTION, exact=True)).to_be_visible()
    expect(page.get_by_role("radiogroup", name="What do you want to improve?", exact=True)).to_be_visible()
    for title, supporting in (
        (MODE_ANALYZE,
         "Inspect current usage and identify opportunities. Recommendations are not measured improvements."),
        (MODE_PROMPT,
         "Improve one prompt, its context, and its model route before any model spend occurs."),
        (MODE_MEASURE,
         "Replay representative work and measure the governed route before comparing it."),
    ):
        expect(page.get_by_role("radio", name=re.compile("^" + re.escape(title)))).to_be_visible()
        expect(page.get_by_text(supporting, exact=True)).to_be_visible()
    # The parent workflow card itself is unchanged and still the primary selection.
    expect(page.get_by_role("button", name=re.compile("^" + TITLE))).to_be_visible()


def test_prompt_mode_is_the_default_and_shows_prompt_copy(page):
    page.get_by_role("button", name=re.compile("^" + TITLE)).click()
    expect(page.get_by_role("radio", name=re.compile("^" + re.escape(MODE_PROMPT)))).to_be_checked()
    expect(page.get_by_role("heading", name="Provide the prompt", exact=True)).to_be_visible()
    expect(page.get_by_text(
        "Paste the request you plan to send. TokenOS will identify unnecessary context, "
        "reusable content, eligible model routes, and quality requirements before any "
        "model spend occurs.", exact=True
    )).to_be_visible()
    for title in ("Paste a prompt", "Add context or files", "Use a prompt example"):
        expect(page.get_by_role("button", name=re.compile("^" + title))).to_be_visible()
    page.get_by_role("button", name=re.compile("^Paste a prompt")).click()
    expect(page.get_by_label(re.compile("^User prompt"))).to_have_attribute(
        "placeholder", PROMPT_PLACEHOLDER
    )
    screenshot(page, "p01-describe-prompt")


# ------------------------------------------------------------------- mode switching


def test_mode_switch_shows_only_relevant_controls(page):
    page.get_by_role("button", name=re.compile("^" + TITLE)).click()

    choose_mode(page, MODE_PROMPT)
    expect(page.get_by_role("heading", name="Provide the prompt", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name=re.compile("^Upload workflow data"))).to_have_count(0)
    expect(page.get_by_label(re.compile("^Current workflow description"))).to_have_count(0)

    choose_mode(page, MODE_MEASURE)
    expect(page.get_by_role("heading", name="Provide an existing AI workflow", exact=True)).to_be_visible()
    expect(page.get_by_label(re.compile("^User prompt"))).to_have_count(0)
    expect(page.get_by_role("button", name=re.compile("^Upload workflow data"))).to_be_visible()

    choose_mode(page, MODE_ANALYZE)
    expect(page.get_by_label(re.compile("^User prompt"))).to_have_count(0)
    expect(page.get_by_role("button", name=re.compile("^Upload workflow data"))).to_be_visible()


def test_prompt_validation_gates_the_plan_button(page):
    open_prompt_mode(page)
    page.get_by_role("button", name=re.compile("^Paste a prompt")).click()
    action = page.get_by_role("button", name="Build prompt optimization plan", exact=True)
    expect(action).to_be_disabled()

    page.get_by_label(re.compile("^User prompt")).fill(VERBOSE_PROMPT)
    expect(action).to_be_disabled()
    page.get_by_label(re.compile("^Desired outcome")).fill("Return the applicable return window.")
    expect(action).to_be_disabled()
    page.get_by_label(re.compile("^Current model")).select_option("recommend")
    page.get_by_label(re.compile("^Output format")).select_option("json")
    expect(action).to_be_disabled()
    fill_shared_requirements(page)
    expect(action).to_be_enabled()


def test_same_answer_quality_requires_an_expected_result(page):
    open_prompt_mode(page)
    paste_grounded_prompt(page)
    page.get_by_role("checkbox", name="Same decision or answer quality", exact=True).check()
    expected = page.get_by_label(re.compile("^Expected result"))
    expect(expected).to_be_visible()
    page.get_by_label(re.compile("^Optimization goal")).select_option("cost_per_accepted_outcome")
    expect(page.get_by_role("button", name="Build prompt optimization plan", exact=True)).to_be_disabled()
    expected.fill("30 days")
    expect(page.get_by_role("button", name="Build prompt optimization plan", exact=True)).to_be_enabled()


# ------------------------------------------------------------------------ plan


def test_plan_is_local_estimated_and_never_says_saving(page, browser_servers):
    open_prompt_mode(page)
    paste_grounded_prompt(page)
    attach_context(page)
    fill_shared_requirements(page)
    run_id = build_plan(page, browser_servers["api"])

    expect(page.get_by_role("heading", name="Potential improvements", exact=True)).to_be_visible()
    for component in ("System instructions", "User request", "Conversation history",
                      "Retrieved or attached context"):
        expect(page.get_by_text(component, exact=True).first).to_be_attached()
    expect(page.get_by_text("Estimated", exact=False).first).to_be_visible()

    plan_text = page.locator("main").inner_text()
    assert not re.search(r"\bsaving", plan_text, re.I), "Plan must not use savings language."

    # Planning is local only: no model usage and no proof yet.
    state = page.request.get(f"{browser_servers['api']}/api/runs/{run_id}").json()
    assert state["status"] == "planned"
    assert state["proof"] is None
    assert state["promptPlan"]["evidenceStatus"] == "estimated"
    assert not state.get("modelUsage")
    screenshot(page, "p02-plan-prompt")


def test_optimize_shows_governed_package_and_copy_does_not_spend(page, browser_servers):
    open_prompt_mode(page)
    paste_grounded_prompt(page)
    attach_context(page)
    fill_shared_requirements(page)
    run_id = build_plan(page, browser_servers["api"])
    page.get_by_role("button", name="Approve optimization plan", exact=True).click()

    expect(page.get_by_role("heading", name="Current prompt package", exact=True)).to_be_visible()
    expect(page.get_by_role("heading", name="TokenOS governed prompt package", exact=True)).to_be_visible()
    expect(page.get_by_role("heading", name="What TokenOS changed and why", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="Apply optimized prompt", exact=True)).to_have_count(0)
    screenshot(page, "p03-optimize-prompt")

    page.context.grant_permissions(["clipboard-read", "clipboard-write"])
    calls_before = page.request.get(f"{browser_servers['api']}/api/runs/{run_id}").json()
    page.get_by_role("button", name="Copy governed prompt", exact=True).click()
    calls_after = page.request.get(f"{browser_servers['api']}/api/runs/{run_id}").json()
    assert calls_after["status"] == calls_before["status"] == "optimized"
    assert calls_after["proof"] is None
    assert not calls_after.get("modelUsage")


# ------------------------------------------------------------- protect and execution


def test_no_model_call_before_explicit_authorization(page, browser_servers):
    open_prompt_mode(page)
    paste_grounded_prompt(page)
    attach_context(page)
    fill_shared_requirements(page)
    run_id = build_plan(page, browser_servers["api"])
    page.get_by_role("button", name="Approve optimization plan", exact=True).click()
    page.get_by_role("button", name="Continue to safeguards", exact=True).click()
    expect(page.get_by_role("heading", name="Execution safeguards", exact=True)).to_be_visible()
    screenshot(page, "p04-protect-prompt")

    api = browser_servers["api"]
    assert page.request.post(f"{api}/api/runs/{run_id}/execute", data="{}",
                             headers={"content-type": "application/json"}).status == 409
    state = page.request.get(f"{api}/api/runs/{run_id}").json()
    assert state["authorized"] is False if "authorized" in state else state["status"] == "optimized"
    assert not state.get("modelUsage")


def test_grounded_prompt_runs_locally_through_all_seven_phases(page, browser_servers):
    """The retrievable prompt is provable without a model, so the whole governed
    journey completes with zero model tokens even with no Foundry configured."""
    open_prompt_mode(page)
    paste_grounded_prompt(page)
    attach_context(page)
    fill_shared_requirements(page, quality=("Structured output remains valid",
                                            "Required citations or grounded evidence"))
    page.get_by_label(re.compile("^Expected recurring volume")).fill("5000")
    run_id = build_plan(page, browser_servers["api"])
    page.get_by_role("button", name="Approve optimization plan", exact=True).click()
    page.get_by_role("button", name="Continue to safeguards", exact=True).click()
    page.get_by_role("button", name="Authorize protected prompt run", exact=True).click()
    page.get_by_role("button", name="Run governed prompt", exact=True).click()

    expect(page.get_by_role("button", name="Inspect verified outcome", exact=True)).to_be_enabled(timeout=20000)
    screenshot(page, "p05-run-prompt")
    page.get_by_role("button", name="Inspect verified outcome", exact=True).click()
    expect(page.get_by_role("heading", name="Verified outcome", exact=True)).to_be_visible()
    screenshot(page, "p06-verify-prompt")
    page.get_by_role("button", name="Review measured cost proof", exact=True).click()

    proof = wait_for_proof(page, browser_servers["api"], run_id)
    assert proof["mode"] == "measure"
    assert proof["verification"]["passed"] is True
    assert proof["cost"]["modelCalls"] == 0
    assert proof["cost"]["modelSpendUsd"] == 0
    assert proof["prompt"]["originalPromptHash"] != proof["prompt"]["governedPromptHash"]
    # A short prompt with tiny context can legitimately grow once a strict output
    # contract is added. The contract must never report that as a reduction.
    assert proof["prompt"]["estimatedBefore"]["inputTokens"] > 0
    assert proof["prompt"]["estimatedAfter"]["inputTokens"] > 0
    assert proof["baseline"]["eligible"] is False

    # Claim strength before any baseline.
    expect(page.get_by_role("heading", name="Comparison not run", exact=True)).to_be_visible()
    expect(page.get_by_role("heading", name="Verified saving", exact=True)).to_have_count(0)
    expect(page.get_by_role("heading", name="Projected cost at volume", exact=True)).to_be_visible()
    for summary in ("Technical evidence and run proof",):
        details = page.locator("details").filter(has=page.locator("summary", has_text=summary))
        expect(details).not_to_have_attribute("open", "")
    screenshot(page, "p07-prove-prompt")


def test_interpretation_prompt_blocks_safely_without_foundry(page, browser_servers):
    """A prompt with no provable local answer must block, never invent a result."""
    open_prompt_mode(page)
    paste_grounded_prompt(page, prompt="Draft a persuasive apology explaining our delay policy.")
    fill_shared_requirements(page)
    run_id = build_plan(page, browser_servers["api"])
    page.get_by_role("button", name="Approve optimization plan", exact=True).click()
    page.get_by_role("button", name="Continue to safeguards", exact=True).click()

    expect(page.get_by_role("button", name="Authorize protected prompt run", exact=True)).to_be_disabled()
    expect(page.get_by_text(
        "Foundry is unavailable. Configure server-side deployments and credentials.", exact=True
    )).to_be_visible()
    state = page.request.get(f"{browser_servers['api']}/api/runs/{run_id}").json()
    assert state["status"] == "optimized"
    assert state["proof"] is None
    assert not state.get("modelUsage")


def test_required_tests_gate_is_blocked_for_a_prompt(page, browser_servers):
    open_prompt_mode(page)
    paste_grounded_prompt(page)
    attach_context(page)
    fill_shared_requirements(page, quality=("Required test suite passes",))
    run_id = build_plan(page, browser_servers["api"])
    page.get_by_role("button", name="Approve optimization plan", exact=True).click()
    page.get_by_role("button", name="Continue to safeguards", exact=True).click()
    expect(page.get_by_role("button", name="Authorize protected prompt run", exact=True)).to_be_disabled()
    state = page.request.get(f"{browser_servers['api']}/api/runs/{run_id}").json()
    blocked = [check for check in state["protectionChecks"] if check["passed"] is False]
    assert blocked, "An unsupported verifier must block Protect."
    assert state["proof"] is None


# --------------------------------------------------------------------- fixtures


def assert_example_defaults(page, example):
    for label, key in (
        ("User prompt (required)", "prompt"),
        ("System instructions", "systemInstructions"),
        ("Conversation history", "conversationHistory"),
        ("Desired outcome (required)", "desiredOutcome"),
        ("Expected result (required)", "expectedResult"),
        ("Current model (required)", "currentModel"),
        ("Output format (required)", "outputFormat"),
    ):
        expect(page.get_by_label(label, exact=True)).to_have_value(example[key])
    requirements = example["requirements"]
    for label, key in (
        ("Maximum authorized model spend (USD)", "maxModelSpendUsd"),
        ("Maximum allowed input/context tokens", "maxInputTokens"),
        ("Maximum output tokens", "maxOutputTokens"),
        ("Maximum advanced calls per run", "maxAdvancedCalls"),
        ("Required latency target (milliseconds)", "latencyTargetMs"),
        ("Optimization goal (required)", "optimizationGoal"),
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
    expect(page.get_by_label("Allow advanced escalation only after failed efficient-model verification", exact=True)).to_be_checked(
        checked=requirements["allowAdvancedEscalation"]
    )
    expect(page.get_by_label("Expected recurring volume (optional)", exact=True)).to_have_value(str(example["recurringVolume"]["value"]))
    expect(page.get_by_label("Volume period", exact=True)).to_have_value(example["recurringVolume"]["period"])
    for filename in example["contextFilenames"]:
        expect(page.get_by_text(filename, exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="Build prompt optimization plan", exact=True)).to_be_enabled()


def test_prompt_example_loads_a_reproducible_prompt(page, browser_servers):
    open_prompt_mode(page)
    page.get_by_role("button", name=re.compile("^Use a prompt example")).click()
    examples = page.request.get(f"{browser_servers['api']}/api/optimization/prompt-examples").json()
    by_id = {item["id"]: item for item in examples["examples"]}
    assert {"verbose_support_reply", "repeated_policy_lookup"} <= set(by_id)

    # Choosing the example path must actually supply a prompt, not report that
    # examples are unavailable and leave the user to write one.
    expect(page.get_by_text(re.compile("Prompt examples are unavailable"))).to_have_count(0)
    lookup = by_id["repeated_policy_lookup"]
    assert lookup["prompt"].strip(), "The catalog must return real example prompt text."
    assert lookup["desiredOutcome"].strip()

    page.get_by_role("radio", name=re.compile("^" + re.escape(lookup["title"]))).check()
    prompt_field = page.get_by_label(re.compile("^User prompt"))
    expect(prompt_field).to_have_value(lookup["prompt"])
    expect(page.get_by_label(re.compile("^Desired outcome"))).to_have_value(lookup["desiredOutcome"])

    assert_example_defaults(page, lookup)
    run_id = build_plan(page, browser_servers["api"])
    state = page.request.get(f"{browser_servers['api']}/api/runs/{run_id}").json()
    assert "Measured sample run" in state["badges"]
    # The bundled prompt really is the one that was planned.
    assert state["promptPlan"]["candidate"]["governedPrompt"].strip()
    expect(page.get_by_text("Measured sample run", exact=True).first).to_be_visible()
    screenshot(page, "p08-prompt-example")


@pytest.mark.parametrize("example_id", ["verbose_support_reply", "repeated_policy_lookup"])
def test_every_prompt_example_supplies_usable_prompt_content(page, browser_servers, example_id):
    """Each example enables planning on a fresh form, with no manual form edits."""
    open_prompt_mode(page)
    page.get_by_role("button", name=re.compile("^Use a prompt example")).click()
    examples = page.request.get(f"{browser_servers['api']}/api/optimization/prompt-examples").json()["examples"]
    assert len(examples) >= 2
    example = next(item for item in examples if item["id"] == example_id)
    calls = []
    page.on("request", lambda request: calls.append(request.url))
    page.get_by_role("radio", name=re.compile("^" + re.escape(example["title"]))).check()
    assert_example_defaults(page, example)
    for title in ("System instructions", "Conversation history", "Execution limits"):
        page.locator("summary").filter(has_text=re.compile("^" + title + "$")).click()
    screenshot(page, f"example-defaults-{example_id}")
    with page.expect_response(
        lambda response: response.url == browser_servers["api"] + "/api/runs"
        and response.request.method == "POST"
    ) as described:
        run_id = build_plan(page, browser_servers["api"])
    submitted = described.value.request.post_data_json
    for key in ("systemInstructions", "conversationHistory", "desiredOutcome", "expectedResult", "currentModel", "outputFormat", "recurringVolume"):
        assert submitted["inputs"][key] == example[key]
    for key, value in example["requirements"].items():
        assert submitted["requirements"][key] == value
    state = page.request.get(f"{browser_servers['api']}/api/runs/{run_id}").json()
    assert state["status"] == "planned"
    assert state["proof"] is None
    assert not any(url.endswith(("/authorize", "/execute", "/baseline")) for url in calls)


def test_switching_prompt_examples_replaces_all_edited_defaults(page, browser_servers):
    open_prompt_mode(page)
    page.get_by_role("button", name=re.compile("^Use a prompt example")).click()
    examples = {item["id"]: item for item in page.request.get(
        f"{browser_servers['api']}/api/optimization/prompt-examples"
    ).json()["examples"]}
    for example_id in ("verbose_support_reply", "repeated_policy_lookup", "verbose_support_reply"):
        example = examples[example_id]
        page.get_by_role("radio", name=re.compile("^" + re.escape(example["title"]))).check()
        assert_example_defaults(page, example)
        page.get_by_label("Expected result (required)", exact=True).fill("")
        page.get_by_label("Desired outcome (required)", exact=True).fill("")
        page.get_by_label("User prompt (required)", exact=True).fill("Previous user edit")
        page.get_by_label("Current model (required)", exact=True).select_option("advanced")
        page.get_by_label("Output format (required)", exact=True).select_option("code_patch")
        page.get_by_label("Expected recurring volume (optional)", exact=True).fill("999")
        page.get_by_role("checkbox", name="Required test suite passes", exact=True).check()
        page.get_by_role("checkbox", name="Human approval remains required for selected outcomes", exact=True).check()
        expect(page.get_by_role("button", name="Build prompt optimization plan", exact=True)).to_be_disabled()


def test_prompt_example_runs_end_to_end_with_its_supplied_prompt(page, browser_servers):
    """The example path supplies a prompt and that prompt completes the governed run."""
    open_prompt_mode(page)
    page.get_by_role("button", name=re.compile("^Use a prompt example")).click()
    examples = page.request.get(f"{browser_servers['api']}/api/optimization/prompt-examples").json()
    lookup = next(item for item in examples["examples"] if item["id"] == "repeated_policy_lookup")

    page.get_by_role("radio", name=re.compile("^" + re.escape(lookup["title"]))).check()
    expect(page.get_by_label(re.compile("^User prompt"))).to_have_value(lookup["prompt"])
    assert_example_defaults(page, lookup)

    run_id = build_plan(page, browser_servers["api"])
    page.get_by_role("button", name="Approve optimization plan", exact=True).click()
    page.get_by_role("button", name="Continue to safeguards", exact=True).click()
    page.get_by_role("button", name="Authorize protected prompt run", exact=True).click()
    page.get_by_role("button", name="Run governed prompt", exact=True).click()
    expect(page.get_by_role("button", name="Inspect verified outcome", exact=True)).to_be_enabled(timeout=20000)

    proof = wait_for_proof(page, browser_servers["api"], run_id)
    assert proof["verification"]["passed"] is True
    assert proof["cost"]["modelCalls"] == 0
    assert "Measured sample run" in proof["badges"]
    assert proof["prompt"]["governedPrompt"].strip()
    assert proof["baseline"]["eligible"] is False


def test_verbose_context_produces_a_real_estimated_reduction(page, browser_servers):
    """With a genuinely wasteful package, minimization must cut estimated input tokens."""
    open_prompt_mode(page)
    paste_grounded_prompt(page)
    padding = "This paragraph documents an unrelated internal procedure. " * 60
    bulky = GROUNDED_CONTEXT + [
        {"id": f"unrelated#{index}", "text": padding} for index in range(4)
    ]
    attach_context(page, records=bulky, name="bulky-context.json")
    fill_shared_requirements(page, quality=("Structured output remains valid",
                                            "Required citations or grounded evidence"))
    run_id = build_plan(page, browser_servers["api"])
    state = page.request.get(f"{browser_servers['api']}/api/runs/{run_id}").json()
    candidate = state["promptPlan"]["candidate"]
    current = state["promptPlan"]["current"]

    assert candidate["estimatedInputTokens"] < current["estimatedInputTokens"]
    assert candidate["estimatedReductionTokens"] > 0
    assert 0 < candidate["estimatedReductionPercent"] <= 100
    assert candidate["minimizedContextIds"], "Irrelevant artifacts must be minimized."
    assert candidate["eligibleContextIds"], "Required grounding must survive minimization."
    assert state["promptPlan"]["evidenceStatus"] == "estimated"


def test_context_artifacts_show_a_real_manifest(page, browser_servers):
    open_prompt_mode(page)
    paste_grounded_prompt(page)
    content = attach_context(page)
    expect(page.get_by_text(str(len(content)), exact=False).first).to_be_attached()
    fill_shared_requirements(page)
    run_id = build_plan(page, browser_servers["api"])
    state = page.request.get(f"{browser_servers['api']}/api/runs/{run_id}").json()
    assert state["manifestHash"] if "manifestHash" in state else state["inputManifestHash"]
    decisions = state["promptPlan"]["contextDecisions"]
    assert decisions, "Context decisions must be recorded."
    assert {decision["decision"] for decision in decisions} <= {
        "allow", "minimize", "redact", "approval_required", "block"
    }


def test_no_credentials_or_raw_deployments_reach_the_browser(page, browser_servers):
    open_prompt_mode(page)
    paste_grounded_prompt(page)
    attach_context(page)
    fill_shared_requirements(page)
    run_id = build_plan(page, browser_servers["api"])
    body = page.request.get(f"{browser_servers['api']}/api/runs/{run_id}").text().lower()
    for secret in ("azure_inference_credential", "api-key", "apikey", "authorization",
                   "openai.azure.com", "bearer "):
        assert secret not in body, f"{secret} must never reach the browser."
