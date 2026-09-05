# TokenOS Prompt and Workflow Optimization Implementation Plan

## Purpose

Extend the `workflow_optimization` experience so TokenOS can optimize either:

1. a single prompt before it is sent to a model; or
2. a recurring AI workflow using representative inputs, run telemetry, and measured execution.

This gives TokenOS an intuitive prompt-level entry point while preserving its differentiator: it does more than rewrite a prompt. TokenOS controls context, model eligibility, data handling, quality gates, spend authorization, actual usage measurement, and verified savings.

## User-facing framing

### Replace the current mode heading

Do not use `What are you optimizing?`.

Use:

> ## Optimize AI Prompt or Workflow
>
> Start with a prompt or workflow. TokenOS reduces AI waste while preserving required quality and outcomes.

This language is inclusive of prompt work and workflow work, avoids implementation jargon, and is clear for a first-time user.

### Mode cards

Display the following three cards directly beneath the heading.

| Mode ID | Card title | Supporting text | Default |
| --- | --- | --- | --- |
| `analyze_current_workflow` | Analyze current workflow | Inspect current usage and identify opportunities. Recommendations are not measured improvements. | No |
| `optimize_single_prompt` | Optimize a prompt before you run it | Improve one prompt, its context, and its model route before any model spend occurs. | Yes |
| `measure_optimized_workflow` | Measure an optimized workflow | Replay representative work and measure the governed route before comparing it. | No |

The mode selection controls the rest of Step 1. Do not show workflow-telemetry controls when prompt mode is selected, and do not require a pasted prompt when a user is optimizing a recurring workflow.

## Product principles

- A prompt optimization is a pre-execution recommendation until the user runs it. Estimated input tokens, cost, cache eligibility, and expected reduction must be visibly marked **Estimated**.
- A workflow optimization becomes **Measured** only after TokenOS executes the governed route and captures actual provider usage.
- A value is a **Verified saving** only after a user explicitly starts a matched all-AI baseline, both paths pass identical quality gates, and measured baseline model cost exceeds measured governed model cost.
- TokenOS remains the governing layer. Models are bounded executors behind policy, budget, data, and quality decisions.
- A local deterministic route may be described as **zero model tokens**. It must not be presented as zero total cost.
- Never expose Foundry or provider secrets, raw credentials, or unredacted sensitive artifacts to the browser.

## UI information architecture

### Parent workflow card

Keep the Step 1 workflow card:

> **Optimize an existing AI workflow**  
> Connect an AI application or prior run. TokenOS finds the lowest-cost route that still meets the required quality.

The prompt path is a focused entry path inside this card, because a prompt is one form of AI work and is often the smallest executable unit of an existing workflow.

### Step 1 layout

```text
Selected workflow: Optimize an existing AI workflow

What do you want to improve?
  [Analyze current workflow] [Optimize a prompt before you run it] [Measure an optimized workflow]

Dynamic work area for selected mode

Required outcome and quality requirements
Optimization goal and optional expected volume
Advanced execution limits

[Analyze / build plan]
```

### Shared fields for every mode

These fields appear after the mode-specific work area:

1. **What should the result accomplish?** (required)
   - Plain-language task outcome.
   - Examples: `Produce a grounded customer response using the applicable policy.` or `Return valid JSON with the correct product classification.`

2. **What must remain true?** (at least one required)
   - Same decision or answer quality
   - Required citations or grounded evidence
   - Structured output remains valid
   - Required test suite passes
   - Response meets a latency target
   - Human approval remains required for selected outcomes

3. **Optimization goal** (single-select, required)
   - Lower cost per accepted outcome
   - Reduce unnecessary model calls
   - Reduce repeated context and token waste
   - Reduce latency while preserving quality
   - Compare efficient and advanced model routes

4. **Expected recurring volume** (optional)
   - Number plus period: day, week, month, year.
   - This supports a separate **Projected at volume** calculation only. It cannot produce a saving claim.

5. **Execution limits** (collapsed advanced section)
   - Maximum authorized model spend
   - Maximum allowed input/context tokens
   - Maximum output tokens
   - Latency target
   - Whether advanced escalation is allowed
   - Maximum advanced calls per run

## Step 1: Describe

### Goal

Collect enough representative work and constraints for TokenOS to build a safe, explainable optimization plan.

### A. Prompt mode: `optimize_single_prompt`

#### Screen heading

> ## Provide the prompt
>
> Paste the request you plan to send. TokenOS will identify unnecessary context, reusable content, eligible model routes, and quality requirements before any model spend occurs.

#### Input source controls

Do not show generic workflow upload cards as the primary prompt input. Instead use these three options:

| Source ID | Display title | Description |
| --- | --- | --- |
| `paste_prompt` | Paste a prompt | Paste the user prompt and optional system instructions directly. |
| `attach_context` | Add context or files | Add the documents, code, history, or policies the prompt currently sends to the model. |
| `prompt_example` | Use a prompt example | Load a reproducible prompt with repeated context and a measurable optimized route. |

The user may paste a prompt and attach context in the same run. `Use a prompt example` loads both a prompt and a bundled context set.

#### Required prompt fields

| Field | UI control | Validation | Notes |
| --- | --- | --- | --- |
| User prompt | Large text area | Required, 1 to configured maximum characters | Placeholder should show an intentionally verbose business request. |
| Desired outcome | Shared short text field | Required | Outcome is used to define the output contract and quality gates. |
| Current model | Dropdown | Required | Options: `Let TokenOS recommend`, `Efficient model`, `Advanced model`, `Existing application model`. |
| Output format | Dropdown | Required | Free text, Markdown, JSON, table, code patch, or application-defined schema. |
| System instructions | Collapsible text area | Optional | Count separately in prompt composition. |
| Conversation history | Collapsible text area or uploaded file | Optional | Show token estimate and propose compression/windowing. |
| Context artifacts | File picker/attachment list | Optional | Display file name, role, size, hash, content type, estimated token count. |

#### Prompt input copy

Prompt placeholder:

> Analyze everything below, review every policy and prior interaction, explain all possible options in detail, and produce the best possible response.

Current model helper:

> TokenOS uses this only as the starting route. It may recommend an efficient model if the required quality can still be verified.

Output-format helper:

> A specific format can reduce unnecessary output tokens and makes verification more reliable.

Context helper:

> Add only the material the current prompt would send. TokenOS will show what was kept, minimized, reused, or blocked before execution.

#### Prompt-specific Describe validation

Enable `Build prompt optimization plan` only when:

- user prompt is non-empty;
- desired outcome is defined;
- current model is selected or `Let TokenOS recommend` is selected;
- output format is selected;
- at least one quality requirement is selected;
- optimization goal is selected;
- all attached context artifacts have completed local validation.

### B. Current-workflow mode: `analyze_current_workflow`

#### Screen heading

> ## Provide an existing AI workflow
>
> Bring recent usage or representative runs. TokenOS will identify where context, model calls, retries, and routing may be creating avoidable cost.

#### Input sources

| Source ID | Display title | Description |
| --- | --- | --- |
| `telemetry_upload` | Upload workflow data | Upload an AI run export, request logs, or representative prompts and results. |
| `connected_application` | Connect an AI application | Select a registered application so TokenOS can read approved run telemetry. |
| `workflow_example` | Use a measured example | Explore a reproducible workflow with clearly labelled sample economics. |

Required telemetry fields where available: request ID, application/workflow, timestamp, model/deployment, prompt or hash, input/output/cached/reasoning tokens, latency, retries, outcome status, quality result, and attribution.

Analysis-only mode does not call a model by default. It produces recommendations and can mark current historical cost as measured only when actual provider usage and a pinned price table are available.

### C. Measured-workflow mode: `measure_optimized_workflow`

#### Screen heading

> ## Provide a representative AI workflow
>
> Give TokenOS repeatable inputs and the quality result to preserve. It will measure a governed route before you choose whether to run a matched comparison.

#### Input sources

| Source ID | Display title | Description |
| --- | --- | --- |
| `workflow_upload` | Upload workflow data | Upload representative inputs, optional telemetry, and required supporting artifacts. |
| `connected_application` | Connect an AI application | Select a registered application and approved test scope. |
| `workflow_example` | Use a measured example | Run a bundled fixture through the real local engine. |

Require either 3 to 20 representative requests or a workflow-specific input package. Require a testable acceptance condition.

### Connected application explanation

Always show below any connected-application control:

> A connected application is a TokenOS-registered application and approved data scope. It does not automatically connect to an Azure subscription. Provider credentials never reach the browser.

## Step 2: Plan

### Goal

Turn user inputs into a transparent map of current work and eligible lower-cost alternatives. Planning is local by default.

### Prompt mode plan view

Show a **Prompt composition** panel with distinct rows:

| Prompt component | Current amount | Candidate treatment | Reason |
| --- | ---: | --- | --- |
| System instructions | Estimated tokens | Keep / compact | Stable operating rules |
| User request | Estimated tokens | Clarify / preserve | Task intent |
| Conversation history | Estimated tokens | Window / summarize / remove | Older turns may be irrelevant |
| Retrieved or attached context | Estimated tokens | Keep selected excerpts only | Relevance and evidence requirement |
| Tool definitions | Estimated tokens | Limit to allowed tools | Avoid repeated prompt overhead |

Show a **Potential improvements** list:

- remove repeated or conflicting instructions;
- replace open-ended response request with output contract;
- minimize attached context to relevant evidence;
- preserve a stable prefix for provider cache eligibility;
- use local rules/retrieval when an answer can be verified without a model;
- route bounded interpretation to an efficient model;
- reserve advanced reasoning for failed quality verification.

All effect values in Plan are `Estimated`. Do not display the word `saving`.

### Workflow mode plan view

Show current model distribution, calls per outcome, retries, context size, latency, current cost when measured, and data completeness. Then show planned operations with current and candidate route.

### Plan controls

- `Approve optimization plan`
- `Edit inputs`
- `View assumptions`

## Step 3: Optimize

### Goal

Produce the proposed governed route and explain every change.

### Prompt mode optimized package

Show a side-by-side comparison, with copyable but not automatically applied content:

| Current prompt package | TokenOS governed prompt package |
| --- | --- |
| Original prompt and all submitted context | Concise task instructions plus only eligible context |
| Current/default model | Recommended route and escalation condition |
| Unbounded prose request | Required output schema/format and output limit |
| Repeated stable content | Stable cache-eligible prefix when applicable |

Under the comparison, show **What TokenOS changed and why**:

| Change | Reason | Evidence state |
| --- | --- | --- |
| Removed repeated instruction | Same task meaning appears multiple times | Estimated token reduction |
| Excluded irrelevant context | Not needed for outcome or citations | Data-minimization decision |
| Kept selected policy excerpts | Required for grounded result | Required evidence |
| Added JSON schema | Reduces verbosity and enables validation | Quality requirement |
| Recommended efficient model | Bounded task can be verified | Requires real execution |
| Reserved advanced model | Used only after failed verification | Policy condition |

Action buttons:

- `Copy governed prompt`
- `Continue to safeguards`

Do not present `Apply optimized prompt` as a completed optimization. The user must approve safeguards and run it for measured results.

### Workflow mode candidate plan

Show operations resolved locally, cache/reuse opportunity, model selection, budget, data decision, quality gates, and escalation path. Retain the same plan mechanics already defined for workflow optimization.

## Step 4: Protect

### Goal

Create the explicit authorization contract before any paid model work occurs.

### Shared checks

- pinned input manifest and hashes;
- data policy for every context artifact: allow, redact, minimize, require approval, block;
- allowed application and environment scope;
- allowed model aliases;
- maximum authorized model spend;
- maximum input and output tokens;
- required output contract;
- required quality gates;
- advanced escalation policy and ceiling;
- pinned price-table version.

### Prompt-specific safeguards UI

Show plain-language decisions:

- `Only 4 of 18 attached sections may reach the model`
- `History older than 6 turns will be summarized locally`
- `Maximum output: 400 tokens in valid JSON`
- `Efficient model is authorized first`
- `Advanced model is permitted only if the quality check fails`
- `Maximum model spend for this prompt: $0.05`

Primary action: `Authorize protected prompt run`.

### Data protection rule

Do not claim automatic PII stripping unless implemented and tested. Record the explicit data-policy outcome in proof. Secrets must be blocked or redacted before adapter invocation.

## Step 5: Run

### Goal

Execute the approved route and provide live, understandable progress.

### Event delivery

Use Server-Sent Events at `GET /api/runs/{runId}/events`. Polling is fallback only.

Required event categories:

```ts
type RunEvent =
  | { type: "phase_started"; phase: number; label: string }
  | { type: "prompt_analyzed"; currentEstimatedTokens: number; candidateEstimatedTokens: number }
  | { type: "context_decided"; kept: number; minimized: number; blocked: number }
  | { type: "operation_started"; operationId: string; route: string }
  | { type: "model_authorized"; modelAlias: string; reservedMicrodollars: number }
  | { type: "model_usage_reconciled"; usage: NormalizedUsage; cost: CostProof }
  | { type: "quality_gate_completed"; gate: QualityGate }
  | { type: "run_completed"; runId: string }
  | { type: "run_failed"; runId: string; safeMessage: string };
```

### Prompt-mode progress copy

```text
1. Checked prompt, context, and quality requirements
2. Removed or minimized ineligible context
3. Authorized the least-cost eligible model route
4. Ran the governed prompt and recorded actual usage
```

### Foundry adapter

- Foundry calls are server-side only.
- Use aliases: `tokenos-efficient`, `tokenos-advanced`, `tokenos-baseline`.
- Capture provider request ID, deployment alias/version, latency, input/output/cached/reasoning tokens, and raw provider usage as protected technical evidence.
- Normalize usage before cost calculation.
- Calculate displayed money from normalized provider usage and a pinned versioned price table.
- When Foundry is unavailable, safely stop with an `Unavailable` state. Do not return simulated model usage or cost.

## Step 6: Verify

### Goal

Prove the run achieved the user-defined outcome before presenting economics as a success.

### Prompt-specific verification

Apply the selected gates:

- citation references resolve to permitted sources;
- JSON or structured output validates against schema;
- required answer fields are present;
- content passes deterministic factual/amount constraints where possible;
- response remains inside output and latency limits;
- evaluator or acceptance test reaches threshold where configured;
- human approval requirement is preserved.

### UI

Show:

> **Outcome verification: Passed**

Then list requirements checked, failed checks, exceptions requiring human review, and a collapsed link to evidence. If verification fails, retain cost measurement but forbid savings claims and provide `Inspect failed checks`, `Adjust plan`, and `Escalate with approval`.

## Step 7: Prove

### Goal

Make the economic result clear without overstating what has been measured.

### Prompt mode first viewport

Hero before comparison:

> **Verified prompt outcome. Less unnecessary context. Measured cost proof.**

Hero after eligible baseline:

> **Same verified outcome. Lower measured model cost.**

Four required cards:

| Card | Value | Supporting copy |
| --- | --- | --- |
| Prompt size | Before and governed estimated input tokens | `Estimated before execution`; after-run actual usage shown separately |
| Model spend | Measured USD after a run | Provider usage plus pinned price table |
| Context decision | Kept, minimized, reused, blocked sections | Zero model tokens only for local work |
| Outcome verification | Passed / failed | Quality checks and evidence result |

### Prompt-mode route explanation

Show a concise visual:

`Prompt + approved context -> Local minimization/reuse -> Efficient model if needed -> Verification -> Advanced escalation only if required`

### What changed panel

Retain the Step 3 explanation, now with measured outcomes where possible:

- actual input/output/cached/reasoning tokens;
- final allowed context artifacts;
- model alias used;
- model calls issued;
- actual latency and measured cost;
- quality-gate status.

### Comparison and saving claim

Show an explicit CTA only after the governed prompt passes verification:

> **Run comparison with current route**  
> This invokes the matched baseline route and may incur model cost. TokenOS reports a verified saving only if both routes pass the same checks.

Controls:

- acknowledgement: `I understand this comparison invokes a model and may incur model cost.`
- button: `Run matched comparison`

Endpoint:

`POST /api/runs/{governedRunId}/baseline`

The baseline must use the same input manifest, output contract, maximum output length, quality-gate versions, and price-table version. If no original/current route was supplied, use a documented versioned `all_ai_v1` baseline and label it clearly.

Only show **Verified saving** when both completed paths pass equal-quality checks and baseline measured cost is greater. Otherwise use `Comparison not run`, `No valid comparison`, or `No cost saving verified`.

### Evidence hierarchy

Keep closed by default:

- Outcome evidence: response, citations, schema checks, acceptance criteria
- Technical evidence and run proof: input manifest hash, policy decisions, operations, usage, price table, and raw JSON download

## Backend contract changes

### Request model

```ts
type OptimizationTarget = "current_workflow" | "single_prompt" | "measured_workflow";

type CreateOptimizationRunRequest = {
  workflow: "workflow_optimization";
  optimizationTarget: OptimizationTarget;
  inputSource: string;
  inputs: {
    workflowDescription?: string;
    userPrompt?: string;
    systemInstructions?: string;
    conversationHistory?: string;
    contextFileIds?: string[];
    telemetryExportIds?: string[];
    representativeInputIds?: string[];
    currentModel?: string;
    outputFormat?: "text" | "markdown" | "json" | "table" | "code_patch" | "custom";
    desiredOutcome: string;
    recurringVolume?: { value: number; period: "day" | "week" | "month" | "year" };
  };
  requirements: {
    qualityRequirements: string[];
    optimizationGoal: string;
    maxModelSpendUsd?: number;
    maxInputTokens?: number;
    maxOutputTokens?: number;
    latencyTargetMs?: number;
    allowAdvancedEscalation?: boolean;
  };
};
```

### Prompt plan response

```ts
type PromptOptimizationPlan = {
  current: {
    estimatedInputTokens: number;
    components: PromptComponent[];
    currentModel?: string;
  };
  candidate: {
    governedPrompt: string;
    eligibleContextIds: string[];
    minimizedContextIds: string[];
    blockedContextIds: string[];
    estimatedInputTokens: number;
    cacheEligibility: "eligible" | "not_eligible" | "unknown";
    recommendedModelAlias: "tokenos-efficient" | "tokenos-advanced" | "local";
    outputContract: OutputContract;
  };
  changes: OptimizationChange[];
  evidenceStatus: "estimated";
};
```

### Run proof additions

```ts
type PromptProof = {
  originalPromptHash: string;
  governedPromptHash: string;
  promptComponents: PromptComponent[];
  contextDecisions: ContextDecision[];
  estimatedBefore?: TokenEstimate;
  measuredUsage?: NormalizedUsage;
  measuredCost?: CostProof;
  qualityGates: QualityGate[];
  baseline?: BaselineComparison;
};
```

No browser endpoint may return unredacted model secrets, credentials, or a context artifact blocked by policy.

## Storage and reporting

Store the optimization target and proof state with every run:

- `optimizationTarget`: current workflow, single prompt, or measured workflow;
- prompt/context size before and after, estimated and measured separately;
- context decisions;
- cache eligibility and provider-reported cached token use;
- model aliases and call counts;
- measured cost and price table version;
- quality results and acceptance state;
- baseline validity and verified saving state;
- application, owner/cost center, environment, and input source.

Enterprise reporting must filter **Measured**, **Projected**, and **Sample** separately. Include prompt-level measures:

- measured input-token reduction after governed prompt execution;
- cached-token rate;
- context-minimization rate;
- average model cost per accepted prompt outcome;
- efficient-to-advanced escalation rate;
- verified savings from valid paired comparisons only.

## Acceptance criteria

### User experience

- The shared heading reads exactly `What do you want to improve?` with the approved description.
- The three mode cards use the approved titles and supporting text.
- Selecting each mode changes the work area and validates only fields relevant to that mode.
- Prompt mode is understandable without knowledge of TokenOS, Foundry, routing, or token economics.
- The existing workflow optimization card remains the parent selection in the main four-card grid.

### Prompt capability

- A user can paste a prompt, attach context, choose outcome and quality requirements, and obtain a local plan before any model call.
- The plan shows prompt composition, context decisions, output contract, cache eligibility, candidate model, and all changes with reasons.
- The user can copy the governed prompt without triggering model spend.
- A governed run is explicit, protected, measured, and verified.
- Prompt comparison never calls an estimated reduction a saving.

### Truthful measurement

- All estimated values are labelled `Estimated`.
- All measured costs originate from actual normalized provider usage plus pinned price table.
- The baseline is explicit and requires cost acknowledgement.
- A verified saving requires all matching/quality conditions, including greater baseline cost.
- All visible counts derive from one run-proof aggregation, never static UI constants.

### Security and resilience

- Context policy blocks/redacts/minimizes data before any provider call.
- Provider credentials stay server-side.
- Foundry failure creates a safe unavailable state and no fabricated economics.
- Raw technical evidence is collapsed and available only to an authorized user.

### Tests

- Unit tests for prompt component token estimation, context-policy decisions, cache eligibility, route selection, and cost calculation.
- API tests for target-specific validation, protected prompt authorization, baseline equivalence, and credential non-disclosure.
- End-to-end tests for all three modes, each quality gate state, Foundry unavailable, baseline success/failure/no-saving, and copy consistency.
- Visual regression test for dynamic fields, card wrapping, and the Step 1 mode switch.

## Delivery order

1. Add mode schema, copy dictionary, routing state, and test fixtures.
2. Implement the Step 1 mode switch and prompt-mode form with local validation.
3. Implement prompt composition parser, local optimization heuristics, context decision engine, and plan view.
4. Implement optimized prompt package, copy action, output contract, and Protect safeguards.
5. Integrate server-side Foundry invocation, event stream, usage normalization, and measured cost.
6. Add prompt-specific verification and Prove visual states.
7. Implement explicit matched comparison and savings eligibility.
8. Add reporting dimensions, enterprise aggregation, security tests, end-to-end tests, evaluator sample, and updated demo script.

## Definition of done

The feature is complete when a user can begin with either one prompt or a recurring workflow, understand exactly what TokenOS will improve, see a safe and explainable plan before spend, run an authorized route, verify the required outcome, and distinguish recommendation, estimate, measured cost, and verified saving without leaving the UI.
