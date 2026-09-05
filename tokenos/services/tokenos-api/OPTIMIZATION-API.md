# Existing workflow optimization API and local configuration

This is the camelCase API for `workflow_optimization`. Existing snake_case APIs for
the first three workflows and legacy `false_savings` remain supported.

## State transitions

| Method | Endpoint | Effect |
| --- | --- | --- |
| GET | `/api/optimization/samples` | Four reproducible fixtures with descriptions, desired outcomes, recurring volume, complete requirements, request counts, and an analysis provenance notice |
| GET | `/api/optimization/applications` | Only applications registered for the server's tenant |
| GET | `/api/optimization/import-template` | Normalized/native import documentation and examples |
| POST | `/api/optimization/uploads` | Multipart `role=telemetry` or `role=test_inputs`, `files`; returns `files[]` manifest metadata |
| POST | `/api/runs` | Describe a new optimization draft; never executes a model |
| POST | `/api/runs/{id}/analyze` | Local telemetry analysis and operation planning |
| POST | `/api/runs/{id}/optimize` | Requires `{"approvePlan":true}`; compiles levers, routes, and safeguards |
| POST | `/api/runs/{id}/refresh-safeguards` | Re-pins configuration/prices for an unauthorized optimized draft only |
| POST | `/api/runs/{id}/authorize` | Protect checks and explicit model/human authorization |
| POST | `/api/runs/{id}/execute` | Starts the already-authorized route asynchronously |
| GET | `/api/runs/{id}/events` | SSE, including replay through `Last-Event-ID` or `last_event_id` |
| GET | `/api/runs/{id}` | Authoritative durable state, also used for polling fallback |
| GET | `/api/runs/{id}/proof` | Final proof; 409 before the new workflow has a final proof |
| POST | `/api/runs/{id}/baseline` | Explicitly acknowledged asynchronous all-AI comparison |
| GET | `/api/runs/{id}/comparison` | Read-only recorded comparison |
| GET | `/api/runs` | History, including optimization records |
| GET | `/api/optimization/reports` | Measured/sample/projected groups, with `proofType`, `application`, and bounded `limit` filters |

The stage sequence is `described -> planned -> optimized -> authorized -> running
-> completed|failed`. UI navigation does not authorize execution. Refresh never
authorizes a run; protected contracts are immutable. A second execution or baseline
on the same version is rejected rather than spending again.

### Workflow-example defaults

Each sample record contains `description`, `desiredOutcome`, `recurringVolume`,
`requirements`, `requestCount`, and `analysisNotice`. Selecting the sample source
automatically initializes the first available example; selecting another fixture
replaces all example-specific defaults. Prompt and workflow forms share the default
mapping, while mode changes clear incompatible input from the previous mode.

`current_workflow` / `analyze` accepts the bundled representative examples even
without provider telemetry. This is local recommendation planning only: historical
model usage/cost remain unavailable, no provider call is made, and no outcome or
saving is verified. The notice is included in the form and plan assumptions.
Non-sample telemetry analysis still requires a valid telemetry export. The sample
exception does not bypass upload, connected-application, or execution safeguards.

## Describe request

```json
{
  "workflow": "workflow_optimization",
  "inputSource": "sample",
  "mode": "measure",
  "inputs": {
    "workflowDescription": "Our assistant sends full history and policy context for every request.",
    "sampleId": "customer_assistance",
    "recurringVolume": { "value": 10000, "period": "month" },
    "owner": "support",
    "costCenter": "customer-service",
    "environment": "local"
  },
  "requirements": {
    "qualityRequirements": [
      "same_answer_quality",
      "grounded_citations",
      "structured_output"
    ],
    "optimizationGoal": "cost_per_accepted_outcome",
    "maxModelSpendUsd": 0.05,
    "allowAdvancedEscalation": true,
    "maxAdvancedCalls": 1,
    "maxOutputTokens": 500,
    "maxOutputCharacters": 8000,
    "dataHandling": "minimize"
  }
}
```

`inputSource` is `upload`, `connected`, or `sample`; `mode` is `analyze` or `measure`.
Uploads use server-issued `telemetryExportIds` and `testInputIds`. Pasted inputs use
`representativeRequests`. Measurement requires 3-20 requests with independently
specified `expectedOutput`; missing acceptance evidence blocks Protect.

Connected requests send `applicationId` and `filters` only, never file paths, URLs,
tenant identity, credentials, or permission grants. Supported filters are `reference`,
`timeRange` (`24h`, `7d`, `30d`, `custom`), and timezone-qualified custom `start`/`end`.

Supported goal IDs: `cost_per_accepted_outcome`, `reduce_model_calls`,
`reduce_context`, `reduce_latency`, `compare_models`.

Supported quality IDs: `same_answer_quality`, `grounded_citations`,
`structured_output`, `required_tests`, `latency_target`, `human_approval`.
Latency requires `latencyTargetMs`. An unsupported evaluator or schema feature
blocks execution rather than silently dropping the requirement.

Representative request shape:

```json
{
  "id": "request-1",
  "taskType": "lookup",
  "input": "return window",
  "context": [{
    "id": "returns#window",
    "key": "return window",
    "text": "Returns are accepted within 30 days.",
    "output": { "decision": "30 days", "citations": ["returns#window"] }
  }],
  "expectedOutput": { "decision": "30 days", "citations": ["returns#window"] },
  "reuseScope": "approved-public-policy",
  "freshnessVersion": "2026-09"
}
```

Supported task adapters are `lookup`, `classification`, `policy`, `code_validation`,
and bounded `interpretation`. Expected outputs are evaluator-only and never appear
in provider prompts. Unknown plain-text requests can be planned but cannot pass
Protect without independent acceptance evidence.

## Protect and comparison acknowledgement

```json
{ "authorizeModelCost": true, "humanApprovalGranted": false }
```

`authorizeModelCost` is required for actual model work. A local-only route can
authorize with `false`. Human approval is checked separately whenever required.
Server safeguards validate the manifest, application scope, data handling, provider
configuration, conservative reservations, output contract, quality gates, and prices.

The comparison request is exactly:

```json
{ "acknowledgeModelCost": true, "baselineProfile": "all_ai_v1" }
```

Missing, false, string, or numeric acknowledgement is rejected. The baseline must
pass the same verifier and all pinned contract checks. Equal/lower baseline cost
produces **No cost saving verified**; failed or mismatched pairs produce
**No valid comparison**. Only a passing, complete, more-expensive baseline can
produce **Verified saving**. Volume projections never establish a saving.

## Events, proof, and durable storage

Named SSE events include `phase.started`, `phase.completed`, `operation.started`,
`operation.completed`, `data.policy`, `model.authorized`, `budget.reserved`,
`model.usage`, `budget.reconciled`, `quality.result`, `escalation.decision`,
`execution.failed`, `run.completed`, `run.failed`, `baseline.started`,
`baseline.completed`, and `safeguards.refreshed`.

Each has `sequence`, `runId`, `at`, `type`, and safe event-specific fields. A baseline
has its own status; it does not overwrite the governed run's completion status.

Proof contains manifest/contract hashes, current/candidate routes, completed
operations, actual produced outcomes, quality gates, provider usage, exact USD
cost strings, public alias-based prices, baseline comparison, dimensions, and badges.
Unknown cost is null, not a successful-looking zero. Zero model cost on a local run
does not claim zero compute, storage, or human cost.

Storage is additive: `TOKENOS_STORAGE_ROOT\optimization.sqlite3` contains
`optimization_runs`, `optimization_events`, `optimization_files`, and
`optimization_claims`. The claims table prevents duplicate paid execution/baselines.
Tables are created with `IF NOT EXISTS`; existing legacy ledger tables are untouched.
Completed proof and event replay survive a process restart.

The current service is a local, single-tenant deployment. `TOKENOS_TENANT_ID` supplies
the trusted server-side tenant identity; browser headers cannot override it. Place
an authenticated boundary in front of the API before exposing it to other users.
Do not deploy this development service publicly as a multi-tenant API.

## Foundry local configuration

No Azure provisioning is performed by this feature. Use existing deployments and
configure bindings only on the server. Browser-facing names are always
`tokenos-efficient`, `tokenos-advanced`, and `tokenos-baseline`.

From `services\tokenos-api`, after installing the existing runtime requirements:

```powershell
az login
$env:TOKENOS_MODEL_MODE = "foundry"
$env:TOKENOS_FOUNDRY_BASE_URL = "https://<resource>.openai.azure.com/openai/v1/"
$env:TOKENOS_FOUNDRY_AUTH_MODE = "entra"
$env:TOKENOS_FOUNDRY_EFFICIENT_DEPLOYMENT = "<efficient-deployment>"
$env:TOKENOS_FOUNDRY_ADVANCED_DEPLOYMENT = "<advanced-deployment>"
$env:TOKENOS_FOUNDRY_BASELINE_DEPLOYMENT = "<baseline-deployment>"
$env:TOKENOS_TENANT_ID = "local"
.\.venv\Scripts\python.exe -m uvicorn tokenos_api.app:app --host 127.0.0.1 --port 8000
```

The signed-in identity needs the appropriate data-plane role, such as **Cognitive
Services OpenAI User**, on the configured resource. Entra uses the
`https://cognitiveservices.azure.com/.default` audience by default. API-key
authentication, where allowed by the resource, uses `TOKENOS_FOUNDRY_AUTH_MODE=api_key`
and server-only `AZURE_INFERENCE_CREDENTIAL`; never put a key in a `VITE_` variable,
browser field, or committed fixture.

Before authorizing model calls:

1. Review [optimization-price-table.example.json](optimization-price-table.example.json).
2. Merge deployment-keyed entries into the server's existing `price_table.json`,
   preserving entries needed by the other workflows.
3. Replace every null rate with the actual agreed USD rate per million input,
   output, and cached-input tokens. Do not treat example numbers as account pricing.
4. Set an explicit top-level `version`; record model/model-version, region, effective
   date, and source as entry metadata where available.
5. Refresh an unauthorized draft's safeguards after changing configuration/prices.
   For already-authorized runs, create a new plan.

The run pins both the table snapshot and a version/content hash. Model cost is
calculated with Decimal arithmetic from provider-reported usage:

`((input - cached) * inputRate + cached * cachedRate + output * outputRate) / 1,000,000`

Reasoning tokens are included in output tokens, not charged twice. Missing cached
pricing when the provider reports cached tokens blocks a measured comparison.
Request identity, alias/version, latency, token categories, cost reconciliation,
and safe errors are recorded. No deployed model or unavailable Foundry means a
clear block/failure, never synthetic usage or a substitute successful outcome.

## Prompt-level optimization (`optimizationTarget: "single_prompt"`)

The fourth workflow covers a single prompt as well as a recurring workflow. The
three modes map to one request field:

| Mode card | `optimizationTarget` | derived `mode` |
| --- | --- | --- |
| `Analyze current workflow` | `current_workflow` | `analyze` |
| `Optimize a prompt before you run it` | `single_prompt` | `measure` |
| `Measure an optimized workflow` | `measured_workflow` | `measure` |

Omitting `optimizationTarget` derives it from `mode` (`analyze` ->
`current_workflow`, `measure` -> `measured_workflow`), so existing callers are
unaffected. Supplying both with conflicting values is a 422.

`inputSource` accepts the prompt sources `paste_prompt`, `attach_context`,
`prompt_example`, the workflow sources `telemetry_upload`, `workflow_upload`,
`connected_application`, `workflow_example`, and the legacy `upload`,
`connected`, `sample`. A prompt target rejects workflow sources and vice versa.

### Additional endpoints

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/api/optimization/context` | Upload context artifacts (role forced to `context`); returns hash, type, size, estimated tokens and excerpt count |
| `GET` | `/api/optimization/prompt-examples` | Complete example defaults: `prompt`, `systemInstructions`, `conversationHistory`, `desiredOutcome`, `expectedResult`, `currentModel`, `outputFormat`, `recurringVolume`, `requirements` and `contextFilenames` |

Each example's `requirements` includes quality criteria, optimization goal, spend
ceiling, input/output token limits, latency target, and bounded advanced escalation.
Selecting an example applies these defaults together and enables planning without
manual edits. The catalog contains no execution or human-approval grant. Context
files remain pinned server-side; `contextFilenames` displays what is bundled without
duplicating uploads.

### Describe request

```jsonc
{
  "workflow": "workflow_optimization",
  "optimizationTarget": "single_prompt",
  "inputSource": "attach_context",
  "inputs": {
    "userPrompt": "required, 1..20000 characters",
    "desiredOutcome": "required; defines the output contract and gates",
    "currentModel": "recommend|efficient|advanced|application",
    "outputFormat": "text|markdown|json|table|code_patch|custom",
    "systemInstructions": "optional",
    "conversationHistory": "optional",
    "contextFileIds": ["file_..."],
    "expectedResult": "required only when same_answer_quality is selected",
    "promptExampleId": "verbose_support_reply | repeated_policy_lookup",
    "recurringVolume": { "value": 5000, "period": "day|week|month|year" }
  },
  "requirements": {
    "qualityRequirements": ["structured_output", "grounded_citations"],
    "optimizationGoal": "cost_per_accepted_outcome",
    "maxInputTokens": 8000
  }
}
```

`workflowDescription` stays required for the workflow targets and is not required
for a prompt. `Desired outcome` is required for **all three** modes.

### `promptPlan` state

Returned by `/analyze` onward and pinned into `proof.prompt`:

- `current`: `estimatedInputTokens`, `currentModel`, and one `components` row per
  system / user / history / context / tools segment with its estimated tokens,
  candidate treatment and reason.
- `candidate`: `governedPrompt`, `governedSystemPrompt`, eligible / minimized /
  blocked context IDs, `estimatedInputTokens`, `estimatedReductionTokens`,
  `estimatedReductionPercent`, `cacheEligibility`, `recommendedModelAlias`,
  `routeReason` and `outputContract`.
- `contextDecisions`: per excerpt, one of `allow`, `minimize`, `redact`,
  `approval_required`, `block`, with a reason.
- `changes`, `improvements`, and `evidenceStatus: "estimated"`.

`estimatedReductionTokens` is floored at zero. A short prompt with little context
can legitimately grow once a strict output contract is added; the API reports that
as a zero reduction rather than inventing a gain. Both token estimates are always
returned so the direction of the change stays visible.

### Route classification

The governed prompt becomes exactly one internal request. It is classified as a
deterministic `lookup` only when the request text names the retrieval key of
exactly one eligible context excerpt that carries a decision plus citations
satisfying the output contract. That path runs locally with zero model tokens.
Everything else is `interpretation` and requires an authorized model call, so with
no Foundry configured it blocks at Protect instead of answering.

Context relevance uses stemmed term overlap, and an excerpt whose retrieval key is
named by the request is always retained — minimization must never strip the
grounding that required citations depend on.

### Prompt quality gates

Verifiable for a prompt: `structured_output`, `grounded_citations`,
`latency_target`, `human_approval`.

`same_answer_quality` requires `inputs.expectedResult`; without it Protect blocks.
`required_tests` is unsupported for a prompt and blocks. Neither is ever
auto-passed.

For `text`, `markdown`, `table` and `code_patch` the output contract requires a
JSON envelope with a `response` string (plus optional `citations`), and the
governed system prompt instructs the model to return exactly that, so schema
validation is real rather than decorative.

### Prompt baseline

The matched `all_ai_v1` baseline sends the **original** package: original system
instructions, full conversation history, all relevance-minimized context and the
original verbose prompt, against the same output contract, output limit, quality
gates, verifier and price table. Policy-blocked content (secrets, credentials) is
excluded from both paths, and that composition difference is recorded in the
comparison evidence.

### Additional events

Alongside the existing dotted events: `prompt.analyzed`
(`currentEstimatedTokens`, `candidateEstimatedTokens`) and `context.decided`
(`kept`, `minimized`, `blocked`).

The specification lists these names in snake_case (`phase_started`,
`prompt_analyzed`, ...). The shipped stream keeps the dotted names already used by
the UI and the existing tests; this naming difference is a deliberate deviation.

### Reporting

Run dimensions gain `optimizationTarget` and `promptRun`. `/api/optimization/reports`
accepts an `optimizationTarget` filter and reports `contextMinimizationRate`,
`measuredCachedTokenRate`, `measuredInputTokenReduction`,
`costPerAcceptedOutcomeUsd`, `qualityPassRate`, `escalationRate` and
`verifiedSavingsUsd`, with measured / projected / sample kept separate.

## Scope of the current verifiers
The new code-validation adapter executes a finite arithmetic AST test suite; it
does not execute arbitrary uploaded code. A model diagnosis does not convert a
failing test into a pass. The first three workflows retain their existing broader
workflow-specific behavior.

Batch eligibility is a recommendation, not a live batch-job submission. Semantic
reuse is conservative validated exact reuse within the same context/scope/freshness,
not approximate vector similarity. Quality is evaluated against explicit expected
outputs and allowed citations; unconstrained open-ended answer quality needs a
registered evaluator before it can support a claim.
