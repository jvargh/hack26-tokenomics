# Evaluator walkthrough: optimize an existing AI workflow

## What this demonstration proves

TokenOS is the policy, routing, and measurement layer. It first attempts local
software and eligible reuse, authorizes bounded model work only in Protect, and
checks actual outputs before presenting economics as success.

The local-only walkthrough does not need an Azure subscription or model credentials.
An ambiguous request is not magically resolved in local-only mode: model-required
runs are blocked or unavailable with actionable configuration information.

## 1. Describe

1. Start the API and web app using the [application instructions](../README.md).
2. Under **What do you want TokenOS to optimize?**, select
   **Optimize an existing AI workflow**.
3. Choose **Analyze current workflow** for local analysis, or
   **Measure an optimized workflow** for execution.
4. Choose an input path:
   - **Upload workflow data**: provide a normalized/native export and/or
     representative requests. Inspect each artifact's name, size, SHA-256,
     content type, and role. Measurement requires 3-20 representative requests.
   - **Connect an AI application**: choose a server-registered application,
     authorized trace/workflow, and time range. Inspect the displayed read scope.
     This is not automatic Azure subscription access.
   - **Use a measured example**: automatically selects the first available fixture
     and fills all required fields. Select any of the four fixtures below to replace
     the complete set of defaults.
5. For your own input, supply the current workflow description, desired outcome,
   quality requirements, and optimization goal. Examples fill these plus recurring
   volume, latency, and execution limits; the planning button is enabled immediately.
   Optional recurring volume affects projections only.
6. Select **Analyze workflow and build an optimization plan**.

| Fixture | What to inspect |
| --- | --- |
| Repeated customer-assistance prompts with reusable context | Local retrieval and validation; repeated context and eligible reuse |
| Policy document review with one genuine interpretation exception | An exception must not become a fabricated deterministic answer |
| Code-change validation with a failed test requiring bounded diagnosis | A failed check must not become a passing outcome merely because a model explained it |
| High-volume classification with a small ambiguous subset | Ordinary records can be local; unresolved cases still need verified interpretation |

Every sample result is labelled **Measured sample run**. In Analyze mode these
fixtures provide representative requests, not historical provider telemetry:
planning is local, and current model usage/cost remain unavailable. Measure mode
replays the requests after authorization. No historical usage is fabricated.

Switching from a prompt to a workflow starts a mode-appropriate form instead of
carrying over the prompt's desired outcome. Entering the sample source also selects
and fills an example when its catalog arrives after the click.

## 2. Plan

Inspect the **Current workflow map** and **Planned operations**. Missing usage is
unknown, not zero. Current measured model cost requires valid provider-usage fields
and a matching price entry. Completeness, retries, corrections, and latency remain
visible where supplied.

Open **View data assumptions**. The default planner is local; merely entering this
phase must not send anything to Foundry. Select **Approve optimization plan**.

## 3. Optimize

Review context minimization, prompt caching, semantic reuse, efficient routing,
advanced escalation, deterministic execution, and batch eligibility independently.
Proposals are estimates until supported by actual execution evidence.

In particular:

- Cache eligibility is not a cache hit. Only provider-reported cached tokens prove
  a measured cache rate.
- Reuse is not allowed solely because two prompts look similar.
- Local work consumes zero model tokens, not zero total infrastructure or human cost.
- A required quality gate cannot be removed to make a cheaper route look successful.

## 4. Protect

Review **Execution safeguards**, including manifest integrity, artifact handling,
application scope, output contract/limit, quality gates, alias readiness, budget,
escalation policy, and pinned price-table version.

Select **Authorize protected run** only after the safeguards pass. Missing model
configuration or invalid requirements must produce an actionable block, not a
simulated run. Editing requirements means returning to a new plan and authorization.
If only server deployment configuration or pricing changed, use **Refresh safeguards**
on the unauthorized draft, then authorize explicitly. A refresh is not authorization.

## 5. Run

Observe live server-sent events. Expand operation details only if needed. The stream
contains actual local completion, data-policy decisions, model authorization,
budget reservations, provider usage, reconciled costs, quality results, and failures.
The explicit **Run authorized workflow** action starts execution. When it finishes,
select **Inspect verified outcome**, then **Review measured cost proof** after
checking verification.

Polling is recovery for an unavailable SSE connection, not the normal progress source.
The browser must never generate cost, token, quality, or savings values from timers.

## 6. Verify

Inspect **Verified outcome**: checked requirements, coverage, failed checks,
exceptions, and required human actions. A measured failed run remains a failed run;
it cannot authorize a savings claim.

Use **Inspect failed checks**, **Adjust plan**, or **Escalate with approval** as
appropriate. Model-generated explanations are not substitutes for passing tests,
citations, output validation, acceptance checks, or required human review.

## 7. Prove

For a passing governed run, the initial headline is:

> Verified outcome. Minimal AI use. Measured cost proof.

Inspect model spend, model calls versus operations, local work, outcome verification,
and the route decision chain. Each actual model call has its own purpose, reason,
minimal evidence, alias, measured usage/cost, verification, and escalation evidence.

Before a baseline, expect **Comparison not run**, not a saving. Recurring-volume
figures are separately labelled **Projected cost at volume** and **Projected**.
Outcome evidence and technical proof are collapsed by default.

### Optional paid comparison

With server-side Foundry and valid pricing configured:

1. Review **Run the all-AI comparison**.
2. Check **I understand this comparison invokes a model and may incur model cost.**
3. Select **Run all-AI comparison**.
4. Observe baseline progress through SSE.

Only a completed, quality-passing pair with identical manifest, output contract,
maximum output length, quality gates, and price-table version is comparable.
Only when its measured baseline cost is greater may TokenOS show **Verified saving**.

Equal/lower baseline cost means **No cost saving verified**. A mismatched or failed
pair means **No valid comparison**. No Foundry configuration means **Unavailable**,
never invented tokens or savings.

## Reproducible acceptance checks

From `services\tokenos-api`, run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest -c pytest-browser.ini -v
```

Browser tests require the development dependencies. They launch their own local API
and Vite server with isolated storage and random loopback ports, leaving existing
servers untouched. They use installed Edge on Windows. Set `TOKENOS_BROWSER_CHANNEL`
to another installed Playwright channel, or install Chromium with
`python -m playwright install chromium` on non-Windows systems.

The separate browser pytest configuration selects the synchronous browser suite
without changing the existing unit/API discovery rules.

Set `TOKENOS_SCREENSHOT_DIR` to a chosen local directory to capture the walkthrough
screenshots while running the browser tests. Test fixtures do not spend live model
tokens. Positive paid-comparison cases in the API suite use explicit test doubles,
not a simulated production execution mode.

For server-side Foundry, pricing, supported verifiers, and the complete endpoint
contract, see [the optimization API guide](../services/tokenos-api/OPTIMIZATION-API.md).
Updated [phase screenshots and upload fixtures](README.md) accompany this walkthrough.
