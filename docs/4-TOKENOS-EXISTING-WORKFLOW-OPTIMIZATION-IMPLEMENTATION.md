# TokenOS Existing Workflow Optimization Implementation Plan

## Objective

Add a fourth primary TokenOS workflow that lets a user bring an existing AI application, representative requests, or run telemetry to TokenOS and receive a measured optimization plan.

The workflow demonstrates the core Tokenomics challenge outcome:

> Find the lowest-cost route that still produces an accepted, verified outcome.

This is not a generic cost dashboard and it is not a token cap. TokenOS must analyze a real or reproducible workload, identify avoidable AI work, test an eligible optimized route, protect quality, and only claim a saving after a valid matched comparison.

## Scope and copy migration

### Keep these internal workflow IDs unchanged

| Internal workflow ID | User-facing title | User-facing supporting text |
| --- | --- | --- |
| `document_review` | Review documents against rules | Upload records and policies. TokenOS checks what software can verify before using AI for unclear cases. |
| `validate_software` | Test a code change | Upload or connect a change. TokenOS runs checks first and uses AI only to investigate unresolved failures. |
| `meet_deadline` | Process records by a deadline | Submit a workload and due time. TokenOS completes routine records locally and reserves AI for exceptions. |
| `workflow_optimization` | Optimize an existing AI workflow | Connect an AI application or prior run. TokenOS finds the lowest-cost route that still meets the required quality. |

### Retire from primary workflow selection

Remove `Compare AI options and prove value` from the Step 1 card grid. Do not delete its economics logic. Reuse that capability inside the new `workflow_optimization` flow and in reporting.

### Global UI text

Change the Step 1 heading from:

> What should your AI workflow accomplish?

to:

> What do you want TokenOS to optimize?

Subheading:

> Choose a workflow, provide the real work, and TokenOS will find the least-expensive safe route and prove the result.

Update titles, descriptions, accessibility labels, run history display values, tooltips, sample-data descriptions, walkthrough text, screenshots, and visible test assertions. Do not change API values, database IDs, existing workflow routes, or analytics identifiers for the first three workflows.

## Product behavior

### Two operating modes

The new workflow has two clear modes. The UI must not mix their claim strength.

| Mode | Purpose | What can be claimed |
| --- | --- | --- |
| Analyze current workflow | Analyze run telemetry or exported traces and recommend candidate improvements. | Measured current cost if provider usage exists; recommendations; projections clearly labelled. |
| Measure an optimized workflow | Replay representative inputs through a TokenOS-governed route and, optionally, a matched all-AI baseline. | Measured governed cost; verified saving only after both comparable routes pass. |

### Required evidence for a verified saving

A **Verified saving** is allowed only if all conditions hold:

1. The governed optimized run completed successfully.
2. The paired all-AI baseline completed successfully after explicit user acknowledgement of model cost.
3. Both use the same pinned input manifest.
4. Both use the same output contract, maximum output length, and quality gates.
5. Both use the same pinned price-table version.
6. Both pass the required quality gates.
7. Measured baseline model cost is greater than governed model cost.

Before that point, use only these labels: `Measured current cost`, `Measured governed cost`, `Projected cost at volume`, `Comparison not run`, `No valid comparison`, or `No cost saving verified`.

## Step 1: Describe

### Goal

Collect a representative existing AI workflow, state the outcome that must be preserved, and establish the user-authorized optimization target.

### Screen layout

#### Workflow card

Selected card:

> **Optimize an existing AI workflow**  
> Connect an AI application or prior run. TokenOS finds the lowest-cost route that still meets the required quality.

#### Provide the work panel

Heading:

> **Provide an existing AI workflow**

Supporting text:

> Bring a representative workflow, its recent usage, and the quality result TokenOS must preserve. TokenOS will identify avoidable context, model calls, and routing cost before testing an eligible alternative.

### Input source cards

| Source | Card title | Copy | Behavior |
| --- | --- | --- | --- |
| Upload | Upload workflow data | Upload an AI run export, request logs, or representative prompts and results. | Accept a permitted export plus representative test inputs. |
| Connected application | Connect an AI application | Select a registered application so TokenOS can read approved run telemetry and test a scoped workflow. | Read only from pre-registered, server-side adapters. |
| Sample | Use a measured example | Explore a reproducible workflow with real local execution and clearly labelled sample economics. | Runs a bundled fixture through the real local engine. |

Explain beneath the source cards:

> A connected application is a TokenOS-registered application and approved data scope. It is not an automatic connection to an Azure subscription. Provider credentials never reach the browser.

### Upload mode fields

1. **AI workflow export** (required for telemetry analysis)
   - Accepted types: `.json`, `.jsonl`, `.csv`, `.zip`.
   - Expected values where available: request ID, timestamp, workflow/application, prompt or prompt hash, model/deployment, input tokens, output tokens, cached tokens, reasoning tokens, latency, outcome status, retry count, and user/team attribution.
   - Do not require a specific provider schema. Implement adapters for TokenOS native export and a documented normalized import template.

2. **Representative test inputs** (required to run an optimized route)
   - Upload files or paste 3 to 20 representative requests.
   - Accept text, JSON, JSONL, CSV, Markdown, and workflow-specific input packages.
   - Show a manifest: filename, size, hash, detected content type, and intended role.

3. **Current workflow description** (required)
   - Placeholder: `Our support assistant sends every request, full conversation history, and policy library to an advanced model.`

4. **What must remain true?** (required multi-select)
   - Same decision or answer quality
   - Required citations or grounded evidence
   - Structured output remains valid
   - Required test suite passes
   - Response meets a latency target
   - Human approval remains required for selected outcomes

5. **Optimization goal** (required single-select)
   - Lower cost per accepted outcome
   - Reduce unnecessary model calls
   - Reduce repeated context and token waste
   - Reduce latency while preserving quality
   - Compare efficient and advanced model routes

6. **Expected recurring volume** (optional)
   - Numeric requests per day/month.
   - Use only for a separately labelled projection. It must not create a saving claim.

### Connected-application mode fields

- Registered application selector (required)
- Workflow or trace selector (optional, with search)
- Time range: 24 hours, 7 days, 30 days, custom
- Read scope summary: telemetry only, approved test inputs, or model execution authorization
- Optimization goal and required quality criteria
- Optional cost center/application owner assignment

The server must enforce the registered adapter's scopes. The browser sends only application selection and filter parameters.

### Sample-data mode

Provide four fixtures:

- Repeated customer-assistance prompts with reusable context
- Policy document review with one genuine interpretation exception
- Code-change validation with a failed test requiring bounded diagnosis
- High-volume classification with a small ambiguous subset

Every resulting metric must carry the `Measured sample run` badge. Any scaling number carries the `Projected` badge.

### Describe validation

Disable `Analyze workflow and build an optimization plan` until:

- an input source is selected;
- workflow description is present;
- at least one quality requirement is selected;
- optimization goal is selected;
- upload mode has a valid export or representative inputs;
- connected mode has application and authorized scope;
- sample mode has fixture selected.

## Step 2: Plan

### Goal

Make the current workflow understandable before suggesting a change.

### Required UI

Show a compact **Current workflow map** with:

- number of representative requests;
- current model/deployment distribution;
- observed model calls per accepted outcome;
- input, output, cached, and reasoning tokens when available;
- current measured cost per accepted outcome when source telemetry supports it;
- retries, failures, human correction, and latency where available;
- confidence level for imported data completeness.

Show a **Planned operations** table:

| Operation | Current route | Candidate route | Reason | Cost/evidence status |
| --- | --- | --- | --- | --- |
| Validate input shape | Model | Local software | Schema is explicit | Zero model tokens |
| Trim repeated context | Full prompt | Minimized relevant context | Stable history is redundant | Estimated reduction until run |
| Reuse stable prefix | Reprocess every call | Prompt cache where eligible | Prefix is unchanged | Measured only after provider response |
| Resolve ambiguity | Advanced model | Efficient model | Bounded interpretation task | Requires quality verification |
| Escalate if needed | Always advanced | Advanced only after failed check | Quality ceiling is protected | Conditional |

### Plan controls

- `Approve optimization plan`
- `Edit requirements`
- `View data assumptions`

Do not invoke a model in this phase unless the user has explicitly chosen a model-assisted workload-discovery feature and approved the cost. Default planning is local and deterministic.

## Step 3: Optimize

### Goal

Construct the lowest-cost eligible execution route without weakening quality requirements.

### Required optimization levers

Evaluate each lever independently and show whether it is applicable, not applicable, estimated, or measured:

| Lever | TokenOS action | Evidence required |
| --- | --- | --- |
| Context minimization | Remove irrelevant history, tool definitions, and retrieved content | Input manifest and prompt composition |
| Prompt caching | Preserve a stable, identical request prefix when provider/model supports it | Cached-token fields from provider response |
| Semantic reuse | Reuse a prior validated result only when scope, access, freshness, and quality rules match | Reuse record and validation result |
| Efficient-model routing | Route bounded work to `tokenos-efficient` | Quality gate result |
| Advanced escalation | Reserve `tokenos-advanced` for failed verification or policy-required cases | Escalation rationale |
| Local deterministic execution | Use rules, parsers, calculators, validators, tests, and retrieval first | Operation completion record |
| Batch eligibility | Mark non-urgent asynchronous work eligible for batch route | Deadline/latency constraint |

### Candidate plan output

Show:

- operations resolved locally;
- model operations and allowed deployment alias;
- maximum model spend; 
- proposed data minimization decision: allow, redact, minimize, approval required, or block;
- quality-gate mapping for every model-assisted operation;
- expected effect, clearly marked as estimated before execution.

### Guardrails

- No route may bypass required citations, tests, structured-output validation, policy rules, or human approval.
- No model credentials, deployment secrets, or provider API keys appear in UI state.
- The optimizer may propose a route but cannot call Foundry until Step 4 authorization completes.

## Step 4: Protect

### Goal

Turn the candidate plan into an authorized, safe, reproducible execution contract.

### Required checks

- Input manifest hash and artifact roles
- Data-handling decision for every artifact: allow, redact, minimize, require approval, block
- Registered application scope and tenant authorization
- Model alias and deployment configuration readiness
- Budget ceiling and per-call reservation limits
- Required output contract and maximum output length
- Quality thresholds and required citations/tests
- Escalation policy and maximum number of advanced calls
- Price table version pinned for the run

### UI

Show an **Execution safeguards** panel with pass/fail items, not legalistic terminology. Examples:

- `Only minimized policy excerpts may reach the model`
- `Maximum model spend: $0.05`
- `Advanced reasoning: allowed only after failed efficient-model verification`
- `Required quality checks: citations + structured output + acceptance rule`

Primary action: `Authorize protected run`.

If any required check fails, show an actionable block with the exact missing configuration or user approval. Do not silently fall back to simulated results.

## Step 5: Run

### Goal

Execute the governed route and show real-time, simple progress.

### Event source

Use Server-Sent Events from `GET /api/runs/{runId}/events`; polling is fallback only.

Events must include:

- phase started/completed;
- operation started/completed;
- data-policy decision;
- model authorization and budget reservation;
- normalized provider usage and reconciled cost;
- quality-gate result;
- escalation decision;
- safe failure reason.

### UI

Keep the visible progress concise:

```text
1. Checked input and quality requirements
2. Completed local validation and reuse opportunities
3. Sent only necessary context to the efficient model
4. Verified result and reconciled measured model cost
```

Expandable detail can show operation-level records. Do not display raw prompts, secrets, or verbose diagnostic logs by default.

### Foundry integration

- TokenOS calls Foundry through a server-side adapter only.
- Use aliases, not raw deployment names in the user UI: `tokenos-efficient`, `tokenos-advanced`, `tokenos-baseline`.
- Capture provider request ID, normalized usage, latency, deployment alias/version, and error category.
- Normalize `inputTokens`, `outputTokens`, `cachedInputTokens`, `reasoningTokens`, and `totalTokens`.
- Calculate cost from measured provider usage and the pinned versioned price table.
- If Foundry is unavailable, return `Unavailable` with a clear message. Do not fabricate cost, model usage, or savings.

## Step 6: Verify

### Goal

Confirm the optimized run reached the required outcome before presenting economics as success.

### Verification rules

Apply the same workflow-specific quality gates specified in Describe and pinned in Protect.

Examples:

| Requirement | Verification |
| --- | --- |
| Same decision/answer quality | Comparison evaluator or deterministic acceptance test passes |
| Required citations | Citation references supplied source and allowed section |
| Structured output | Schema validation passes |
| Code change | Required allowlisted tests pass |
| Deadline | All required records processed before deadline or exceptions are explicitly reported |
| Latency | Measured completion time is within stated limit |

### UI

Show a **Verified outcome** card with:

- pass/fail status;
- requirements checked;
- exceptions and required human actions;
- data coverage, such as `10,000 of 10,000 records processed`;
- link to collapsed supporting evidence.

If verification fails, the run is still measured but no savings language is allowed. Offer: `Inspect failed checks`, `Adjust plan`, or `Escalate with approval`.

## Step 7: Prove

### Goal

Show a clear economic result while keeping claim strength truthful.

### First viewport

Hero state before baseline:

> **Verified outcome. Minimal AI use. Measured cost proof.**

Hero state after an eligible baseline:

> **Same verified outcome. Fewer AI calls. Lower measured model cost.**

Show four cards derived from the executed run record:

| Card | Value | Supporting text |
| --- | --- | --- |
| Model spend | Actual displayed USD cost | Measured provider usage and pinned price table |
| Model calls | Calls and operations separately | Efficient and advanced call count |
| Local work | Operations completed locally | Zero model tokens, not zero total cost |
| Outcome verification | Passed / failed | Required quality checks and evidence status |

### Explain route choices

Show:

`Local and reuse operations -> Efficient model calls -> Advanced escalations`

Use counts derived from operation records. Never embed static count text. Clearly distinguish operations from model calls because one call can support more than one operation.

### Why AI was used

Each model call has one visible record:

- business/technical purpose;
- why deterministic software could not complete the step;
- minimal evidence sent;
- deployment alias;
- actual token usage and measured cost;
- quality-gate result;
- escalation decision.

If a model only produced a readable summary, label it as optional presentation work. Do not claim it resolved ambiguity.

### Matched baseline comparison

Show this CTA when governed run verification passes:

> **Run the all-AI comparison**  
> This re-runs the same inputs through the baseline route and consumes model tokens. TokenOS shows a verified saving only if both routes meet the same quality checks.

Controls:

- acknowledgement checkbox: `I understand this comparison invokes a model and may incur model cost.`
- primary action: `Run all-AI comparison`
- status updates via SSE;
- one active baseline per governed run unless authorized versioned rerun.

Endpoint:

`POST /api/runs/{governedRunId}/baseline`

Request:

```json
{
  "acknowledgeModelCost": true,
  "baselineProfile": "all_ai_v1"
}
```

Baseline validation requires identical input manifest, output contract, quality gate versions, maximum output length, and price table version. It must use the same outcome verifier.

### Valid comparison result

When eligible, show:

| All-AI cost | TokenOS governed cost | Verified saving | Quality |
| ---: | ---: | ---: | --- |
| Measured | Measured | Measured dollar and percent delta | Both passed |

Below the grid:

> Both paths used the same inputs, output contract, quality checks, and price-table version.

### Evidence hierarchy

Keep these collapsed by default:

- Outcome evidence: why quality passed
- Technical evidence and run proof: manifest hashes, policies, routes, provider usage, price table, and raw JSON download

## Data model and APIs

### New workflow request

`POST /api/runs`

```json
{
  "workflow": "workflow_optimization",
  "inputSource": "upload",
  "inputs": {
    "telemetryExportIds": ["file_001"],
    "testInputIds": ["file_002"],
    "workflowDescription": "Support assistant sends full context to an advanced model.",
    "recurringVolume": { "value": 10000, "period": "month" }
  },
  "requirements": {
    "qualityRequirements": ["same_answer_quality", "grounded_citations"],
    "optimizationGoal": "cost_per_accepted_outcome",
    "maxModelSpendUsd": 0.05,
    "allowAdvancedEscalation": true
  }
}
```

### Required run-proof properties

```ts
type OptimizationRunProof = {
  runId: string;
  workflow: "workflow_optimization";
  mode: "analyze" | "measure";
  inputManifestHash: string;
  telemetryCompleteness: "complete" | "partial" | "unknown";
  currentRoute?: RouteSummary;
  candidateRoute: RouteSummary;
  operations: OperationRecord[];
  qualityGates: QualityGate[];
  modelUsage: NormalizedUsage[];
  cost: CostProof;
  baseline?: BaselineComparison;
  priceTableVersion: string;
};
```

### Reporting

Tag all runs with application, environment, workflow, input source, proof type, owner/cost center, and price-table version. Enterprise reporting must separately filter and total `measured`, `projected`, and `sample` values.

Key measures:

- measured model spend;
- verified savings only;
- model calls avoided on valid paired runs;
- local/non-AI operation rate;
- cost per accepted outcome;
- quality pass rate;
- escalation rate;
- cache eligibility and measured cached-token rate;
- corrected/reworked outcome rate.

## Acceptance tests

### Copy and UI

- The fourth card reads exactly `Optimize an existing AI workflow` and the approved supporting text.
- `Compare AI options and prove value` is not shown as a primary Step 1 card.
- Step 1 heading reads `What do you want TokenOS to optimize?`.
- All selected-workflow, run history, and accessibility labels show the same user-facing title.

### Functional

- Upload mode accepts a normalized export and representative test inputs, shows manifest, and rejects unsupported/oversized files.
- Connected mode limits results to registered adapter scopes and clearly states it is not automatic subscription access.
- Sample mode is replayed by the real local engine and every result carries a sample badge.
- Plan routes software/retrieval/model work separately and shows model use is conditional.
- Foundry calls occur only after Protect authorizes them.
- Provider usage and price-table version produce the measured cost value.
- Foundry unavailability never generates simulated usage, savings, or successful verification.

### Claim strength

- Before baseline: no visible use of `Verified saving`, `saved`, or comparable success language.
- Baseline endpoint rejects missing cost acknowledgement, changed input manifest, changed quality gates, changed output contract, or changed price table.
- Equal-quality baseline with greater cost results in a verified saving.
- Failed quality, lower/equal baseline cost, or invalid comparison results in the correct no-saving label.
- Projection at user-entered volume is visibly separate from measured cost.

## Delivery sequence

1. Add `workflow_optimization` to the workflow registry, copy dictionary, route schema, test fixtures, and UI selection grid.
2. Implement Step 1 forms, validation, normalized upload parser, registered-application selector, and sample fixtures.
3. Build Plan view and local analysis of telemetry/context/model/routing opportunities.
4. Implement candidate-route compiler, policy/budget checks, price-table pinning, and Protect contract.
5. Implement server-side Foundry adapter, SSE events, real governed execution, usage normalization, and measurement.
6. Implement quality verification and the Prove screen using only aggregated run-proof data.
7. Implement the explicit matched baseline flow and saving eligibility gate.
8. Add reporting dimensions, alerts, unit/API/end-to-end tests, evaluator sample walkthrough, and updated screenshots.

## Definition of done

The feature is done when a first-time user can select the new workflow, provide a real or reproducible AI workload, understand what TokenOS will optimize, see its execution progress, verify the outcome, and distinguish measured cost, projected cost, and a genuinely verified saving without using a CLI or reading raw JSON.
