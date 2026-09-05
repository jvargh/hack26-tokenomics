# Evaluator walkthrough: optimize a prompt or a workflow

This is the guided path for the fourth TokenOS workflow,
**Optimize an existing AI workflow**, which now covers both a single prompt and a
recurring workflow.

For the workflow-only journey, see
[the workflow walkthrough](OPTIMIZATION-WALKTHROUGH.md). This document focuses on
the prompt entry point and on what separates it from a prompt rewriter.

## What this demonstration proves

A prompt rewriter returns different words. TokenOS decides **whether the model is
needed at all**, what context is allowed to leave the machine, which route is
cheapest among those that can still be verified, what the run may cost, and
whether the result actually met the requirement.

So the honest claim ladder is visible throughout:

| Label | Means |
| --- | --- |
| `Estimated` | Local pre-execution arithmetic. No model was called. |
| `Measured` | Actual provider usage reconciled against a pinned price table. |
| `Projected` | Measured unit cost multiplied by a volume you entered. |
| `Verified saving` | A completed matched baseline that passed the same gates and cost more. |

Nothing in local-only mode fabricates the last three.

## Before you start

Run the app as described in [the README](../README.md). No Azure subscription or
model credential is needed for the local walkthrough. Prompts that genuinely
require a model will block with an actionable message instead of inventing output.

## Step 1: Describe

1. On **What do you want TokenOS to optimize?**, choose
   **Optimize an existing AI workflow**.
2. The section **Optimize AI Prompt or Workflow** appears with:
   > Start with a prompt or workflow. TokenOS reduces AI waste while preserving required quality and outcomes.
3. Under **What do you want to improve?** pick one of three modes:

| Mode | Use it for | Claim it can reach |
| --- | --- | --- |
| Analyze current workflow | Inspecting existing telemetry | Measured current cost only, plus recommendations |
| Optimize a prompt before you run it *(default)* | One prompt you are about to send | Estimated plan, then a measured governed run |
| Measure an optimized workflow | Recurring work with representative inputs | Measured governed run, then an optional baseline |

The work area changes with the mode. Prompt mode never asks for telemetry, and
the workflow modes never require a pasted prompt. Mode changes clear incompatible
input rather than carrying a prompt's desired outcome into a workflow form.

In either workflow mode, **Use a measured example** automatically selects and
populates the first fixture, including every required field, so planning is enabled
without edits. All four workflow options carry their own descriptions/outcomes.
Analysis of these representative examples does not fabricate historical telemetry
or model cost; choose Measure for an authorized replay.

### Prompt mode inputs

Choose **Paste a prompt**, **Add context or files**, or **Use a prompt example**.
You may paste a prompt and attach context in the same run.

| Field | Notes |
| --- | --- |
| User prompt | Required. The placeholder is a deliberately wasteful request. |
| Desired outcome | Required. Defines the output contract and the quality gates. |
| Current model | Required. Only a starting route; TokenOS may recommend a cheaper one. |
| Output format | Required. A specific format cuts output tokens and makes verification real. |
| System instructions | Optional, counted separately in prompt composition. |
| Conversation history | Optional. TokenOS proposes windowing or summarising it. |
| Context artifacts | Optional. Each shows name, role, size, SHA-256, type and estimated tokens. |
| Expected result | Appears and becomes required only if you select *Same decision or answer quality*. |

Then set the shared fields: what must remain true, the optimization goal,
optional recurring volume, and the collapsed execution limits.

**Try this:** select *Same decision or answer quality* and leave **Expected
result** empty. `Build prompt optimization plan` stays disabled. TokenOS will not
claim it preserved an answer it has no way to check.

### Two bundled prompt examples

Choose **Use a prompt example**, then select either example. It fills the entire
form: prompt, system instructions, conversation history, current model, output
format, desired outcome, expected result, quality criteria, optimization goal,
latency target, recurring volume and execution limits. The bundled context filenames
are shown and included server-side, so no upload is needed.

**Build prompt optimization plan** is immediately enabled with no manual field
edits. Switching examples replaces the previous example's values and any intervening
edits with the new example's complete defaults. These are editable planning defaults,
not authorization: no model is invoked until the later explicit Protect action.

If examples or their defaults are unavailable, verify that the API is running the
current build, then reload the page.

| Example | What it demonstrates |
| --- | --- |
| `repeated_policy_lookup` | The answer is provable by exact retrieval from a supplied policy artifact, so the governed route needs **zero model calls** and still passes verification. |
| `verbose_support_reply` | Genuinely needs interpretation, so with no Foundry configured it **blocks safely** instead of producing an invented answer. |

Both are labelled **Measured sample run**. They are sample *inputs* only; no
execution result, token count or cost is precomputed.

## Step 2: Plan (local, estimated)

**Prompt composition** breaks the request into system instructions, user request,
conversation history, attached context and tool definitions, with an estimated
token amount, a candidate treatment and a reason for each.

**Potential improvements** lists the eligible levers.

Check two things here:

- every effect is marked `Estimated`;
- the word *saving* does not appear anywhere on this screen.

Planning is deterministic and local. Entering this phase must not contact Foundry.

## Step 3: Optimize (still no spend)

A side-by-side **Current prompt package** and **TokenOS governed prompt package**,
then **What TokenOS changed and why** — each row carrying a reason and an evidence
state.

`Copy governed prompt` puts the governed prompt on your clipboard and spends
nothing. This is deliberate: you can take the improved prompt away without ever
running it. Note that the button is *not* called "Apply optimized prompt", because
nothing has been proved yet.

Choose `Continue to safeguards`.

## Step 4: Protect (the authorization gate)

Plain-language safeguards, for example how many attached sections may reach the
model, how history is handled, the maximum output, which alias is authorized
first, the escalation condition, and the maximum spend for this prompt.

`Authorize protected prompt run` is the only thing that permits paid work.

**Try this:** before authorizing, confirm the server refuses to execute. The
run stays `optimized`, holds no proof, and records no model usage.

## Step 5: Run

Live server-sent events drive the four progress lines. Polling is only a recovery
path if the stream drops; it is not the normal source of progress.

With `repeated_policy_lookup` or an equivalent grounded pasted prompt, the run
completes locally with zero model tokens. Zero model tokens is not zero total
cost, and the UI says so.

## Step 6: Verify

**Verified outcome** shows the produced answer, its citations, the schema result
and the acceptance state. A failed gate keeps the run measured but blocks every
form of success language.

## Step 7: Prove

Leads with outcome quality, the route decision, and measured economics:

`Prompt + approved context -> Local minimization/reuse -> Efficient model if needed -> Verification -> Advanced escalation only if required`

Before any baseline you should see **Comparison not run** — never a saving. If you
entered a recurring volume, **Projected cost at volume** is a separate, separately
badged panel.

Technical evidence stays collapsed and downloadable as raw JSON.

### The optional paid comparison

With server-side Foundry and real prices configured, **Run comparison with current
route** re-runs the *original* package — original system instructions, full
history, all relevance-minimised context, original verbose prompt — against the
same output contract, output limit, quality gates, verifier and price table.

Policy-blocked content (secrets, credentials) is excluded from **both** paths.
That composition difference is recorded in the comparison evidence, because the
whole point of the comparison is that the current route sends more.

Outcomes:

| Result | Shown as |
| --- | --- |
| Both passed, baseline costs more | **Verified saving** |
| Both passed, baseline costs the same or less | **No cost saving verified** |
| Either failed, or contracts differ | **No valid comparison** |
| No Foundry configured | **Unavailable** |

## Reproducible checks

From `services\tokenos-api`:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest -c pytest-browser.ini -q
```

The browser suites (`e2e_optimization.py`, `e2e_prompt.py`, `e2e_visual.py`) start
their own API and Vite servers on random loopback ports with temporary storage, so
they leave any running demo untouched. On Windows they use the installed Edge
channel; set `TOKENOS_BROWSER_CHANNEL` or install Chromium elsewhere.

`e2e_visual.py` is a layout-geometry regression suite rather than a pixel-diff:
it asserts wrapping, equal card heights, absence of clipping and overflow, and the
dynamic-field behaviour of the mode switch, so it stays valid across machines,
fonts and DPI.

Set `TOKENOS_SCREENSHOT_DIR` to capture the walkthrough screenshots while running
them. No test spends live model tokens; positive provider paths use explicit
in-test doubles, never a simulated production mode.
