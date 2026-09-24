# TokenOS: AI Work and Workflow Optimizer

> **Demo video:** [Watch the TokenOS walkthrough on YouTube](https://youtube.com/shorts/PWWNHfphZfk)

TokenOS explores a practical question: **what is the least-expensive eligible route
that still produces a verified outcome?**

It uses local software, retrieval, and validated reuse before requesting model
reasoning. When AI is needed, TokenOS controls the allowed route, context, budget,
and quality checks, then records actual usage and cost. A cheaper-looking estimate
is never treated as a verified saving.

**The runnable application lives in [`tokenos/`](tokenos/).** This root README is
the starting point for setup, evaluation, and navigation. The
[application README](tokenos/README.md) contains additional workflow background.

> **Hosted demonstration:**
> <https://tokenos-hack26.yellowwater-54592620.eastus.azurecontainerapps.io>
>
> Public, no sign-in. AI calls there are **simulated** so the walkthrough costs
> nothing in model spend, and the hosted build says so on every screen. Local
> runs are unaffected and still use real models when Foundry is configured. See
> [`aca/README.md`](aca/README.md) for what is real, what is simulated, and the
> known limitations.

![TokenOS AI Work Optimizer overview. A seven-phase band reads Describe, Plan, Optimize, Protect, Run, Verify, Prove. Beneath it a routing diagram shows a prompt or workflow entering local rules, retrieval and reuse, then an efficient Foundry model only if needed, with a branch that escalates only if required, ending in quality verification and measured cost and outcome proof.](imgs/TokenOS-main-slide.png)

The seven phases run left to right. The routing diagram below them carries the
actual design: local rules, retrieval, and reuse resolve what they can, an
efficient model is called only if unresolved work remains, and the escalation
branch is taken only when the efficient route fails verification. Every path ends
in quality verification and measured proof.

## Contents

- [Quick start](#quick-start)
- [What you can do](#what-you-can-do)
- [Seven-phase user journey](#seven-phase-user-journey)
- [Try the examples](#try-the-examples)
- [How the application works](#how-the-application-works)
- [Economics and claim strength](#economics-and-claim-strength)
- [Hosted judge demonstration](#hosted-judge-demonstration)
- [Optional Azure deployment](#optional-azure-deployment)
- [Optional Microsoft Foundry configuration](#optional-microsoft-foundry-configuration)
- [Configuration and local storage](#configuration-and-local-storage)
- [Build and test](#build-and-test)
- [Repository map](#repository-map)
- [Documentation guide](#documentation-guide)
- [Troubleshooting](#troubleshooting)
- [Scope and limitations](#scope-and-limitations)

## Quick start

### Prerequisites

- **Python 3.13**, the version used for the recorded local validation.
- A supported **Node.js** release with **npm**; Node.js 22 or newer is recommended.
- **PowerShell** for the Windows commands below.
- **Microsoft Edge** for the default Windows browser-test configuration.
- Azure access, the Azure CLI, and the Azure Developer CLI (`azd`) are
  **optional**. They are needed only for Azure deployment or real Foundry
  inference, not for the local examples.

Unless a block says otherwise, start it from this repository's root directory.
There is no root Node.js package: use the web application's package directory.

### 1. Install application dependencies

```powershell
# Create the application's environment on first setup.
py -3.13 -m venv .\tokenos\services\tokenos-api\.venv

.\tokenos\services\tokenos-api\.venv\Scripts\python.exe -m pip install `
  -r .\tokenos\services\tokenos-api\requirements.txt

npm --prefix .\tokenos\apps\web ci
```

The application uses its own Python environment under
[`tokenos/services/tokenos-api/`](tokenos/services/tokenos-api/). A separate
environment at the repository root is not assumed.

Dependency definitions:
[runtime requirements](tokenos/services/tokenos-api/requirements.txt),
[test requirements](tokenos/services/tokenos-api/requirements-dev.txt),
and [web package](tokenos/apps/web/package.json).

### 2. Start the API

In a terminal opened at the repository root:

```powershell
Set-Location .\tokenos\services\tokenos-api
$env:TOKENOS_MODEL_MODE = "local"
.\.venv\Scripts\python.exe -m uvicorn tokenos_api.app:app `
  --host 127.0.0.1 --port 8000
```

Explicit local mode prevents this process from invoking Foundry. Local work runs
for real; a route that needs a model reports a configuration block or unavailable
state rather than inventing an answer.

### 3. Start the web UI

In a **second terminal**, opened at the repository root:

```powershell
npm --prefix .\tokenos\apps\web run dev
```

| Service | Default address |
| --- | --- |
| Web application | <http://localhost:5173> |
| API health | <http://127.0.0.1:8000/health> |
| Interactive API documentation | <http://127.0.0.1:8000/docs> |

You can check API readiness from another terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Stop each foreground server with **Ctrl+C** in its terminal. After dependencies
are installed, [`tokenos/start.ps1`](tokenos/start.ps1) is an alternative helper
that launches both services. It does not replace dependency installation or a
health check. Review the [startup guide](tokenos/STARTUP.md) before using process
helpers; on a shared machine, do not stop unrelated processes occupying a port.

## What you can do

The four primary workflows are:

| Workflow | Typical input | What TokenOS does |
| --- | --- | --- |
| **Review documents against rules** | Records, invoices, policies, and a review focus | Extracts and checks what local software can establish, preserving evidence for unresolved interpretation. |
| **Test a code change** | A change or project package, supporting specifications, and the requested outcome | Performs supported static and allowlisted test checks before bounded model investigation. |
| **Process records by a deadline** | A dataset, processing instruction, and due time | Processes routine records locally and identifies exceptions and deadline constraints. |
| **Optimize an existing AI workflow** | One prompt, representative requests, or run telemetry | Builds an explainable plan, authorizes eligible work, measures execution, and optionally compares a matched baseline. |

Existing internal identifiers remain `document_review`, `software_validation`,
`deadline_processing`, and `workflow_optimization`. The legacy `false_savings`
economics API is retained for compatibility but is not a primary selection.

### Three modes inside the fourth workflow

The section heading is **Optimize AI Prompt or Workflow**. Under
**What do you want to improve?**, choose:

| Mode | Intended use | Important distinction |
| --- | --- | --- |
| **Analyze current workflow** | Examine exported telemetry or bundled representative work | Recommendations are not measured improvements. Current cost needs usable provider-usage evidence and prices. |
| **Optimize a prompt before you run it** | Prepare one prompt, its context, model route, output format, and quality requirements | The default mode. Building or copying a plan does not invoke a model. |
| **Measure an optimized workflow** | Replay representative inputs through the governed route | The resulting proof records executed work. A baseline is a separate, explicitly acknowledged action. |

Prompt inputs can include system instructions, conversation history, and context
files. Workflow inputs can be uploaded, supplied by a registered application, or
loaded from a bundled example. A registered application is an approved server-side
adapter and scope, **not automatic access to an Azure subscription**.

For measurement, the workflow path normally uses **3-20 representative requests**.
Supported optimization exports include JSON, JSONL, CSV, and ZIP; representative
inputs and prompt context also support text and Markdown. The server validates
file types, sizes, archive contents, and artifact roles.

## Seven-phase user journey

| Phase | Purpose |
| --- | --- |
| **Describe** | Provide the work, desired outcome, quality requirements, optimization goal, and execution limits. |
| **Plan** | Understand current work and candidate operations. Prompt mode also shows component-level estimated token usage. |
| **Optimize** | Explain context decisions, reuse/cache eligibility, proposed routes, and why each change is suggested. |
| **Protect** | Check the pinned manifest, data policy, scope, model readiness, budget, output contract, and quality gates; require explicit authorization. |
| **Run** | Execute the authorized work and stream server-generated progress through SSE, with polling as fallback. |
| **Verify** | Check actual outputs against the required gates; expose failures and required human actions. |
| **Prove** | Lead with outcome quality, route decisions, and measured economics. Keep detailed technical proof collapsed and downloadable. |

For the optimization workflow, navigating to Plan or Optimize does not grant
execution permission. A protected run and a paid baseline have separate
authorization steps.

## Try the examples

### Fastest local prompt demonstration

1. Select **Optimize an existing AI workflow**.
2. Keep **Optimize a prompt before you run it** selected.
3. Choose **Use a prompt example**, then
   **Repeated policy lookup with irrelevant excerpts**.
4. Review the populated prompt, instructions, history, expected result, quality
   requirements, volume, and execution limits.
5. Select **Build prompt optimization plan** and follow the phases.

That example has a provable keyed policy answer and can complete locally without
model calls. **Verbose support reply with stale history** also supplies complete
defaults, but its interpretation work can require Foundry. An unavailable model
is an honest block, not an instruction to fabricate a sample response.

### Workflow examples

In either workflow mode, **Use a measured example** automatically selects and
populates a fixture. All required fields are filled, so planning is enabled
without typing a description or outcome. Selecting another fixture replaces
the complete defaults rather than retaining an unrelated prompt's values.

| Fixture | What to examine |
| --- | --- |
| Repeated customer-assistance prompts with reusable context | Exact retrieval, repeated inputs, and validated reuse. |
| Policy document review with one genuine interpretation exception | Routine local decisions versus a genuine approval exception. |
| Code-change validation with a failed test requiring bounded diagnosis | A real failing check must not become a pass merely because it was explained. |
| High-volume classification with a small ambiguous subset | Explicit classification rules versus unresolved mixed-category work. |

In Analyze mode, these fixtures provide representative requests, **not historical
provider telemetry**. TokenOS builds recommendations locally and leaves current
model usage/cost unavailable. Choose Measure for an authorized replay.

Example outputs carry a **Measured sample run** badge. This identifies sample
provenance; it does not turn an estimate into provider-measured economics.

Further reading:

- [Application workflow guide](tokenos/README.md)
- [Optimization API and configuration](tokenos/services/tokenos-api/OPTIMIZATION-API.md)
- [Prompt/workflow implementation report](tokenos/PROMPT-OPTIMIZATION-REPORT.md)

## How the application works

```text
React + TypeScript browser UI
          |
          | HTTP requests and server-sent events
          v
TokenOS FastAPI service
  - Input validation and artifact manifests
  - Local planning, routing, data policy, and budget authorization
  - Deterministic execution and outcome verification
  - Usage reconciliation, proof, and reporting
          |
          +--> Local software / retrieval / validated reuse
          |
          +--> Server-side Foundry adapter, when authorized and required
          |
          +--> Local SQLite proof, event, and artifact storage
```

TokenOS remains the **policy, routing, and measurement layer**. Foundry is a
bounded inference provider behind that layer, not a replacement for it.

![TokenOS engine deep dive. The request path runs from the React web client through the FastAPI application to a dispatching runs endpoint and server-owned run state. Panels detail the API surface, two independent engines behind one API, the Foundry spend boundary, a durable SQLite proof gate, the conditions under which two runs are comparable, and the comparison rule that yields a verified saving.](imgs/TokenOS-Engine-Deep-Dive.png)

Three properties of that layer are worth calling out:

- **Two engines, one API.** The classic engine runs the three fixed workflows;
  the optimization engine runs the describe-to-execute sequence. Both follow a
  server-authorized state machine (`described → planned → optimized →
  authorized`, then `running → completed | failed`). The server owns that state
  and returns `409` naming the required and current status, so a client cannot
  skip a phase or authorize spend out of order.
- **One spend boundary.** `_call_model()` is the only path that can spend. It
  validates contract, tenant, scope, and authorization, reserves the worst-case
  cost before calling Foundry, allows a single strict attempt, and records
  tokens, request ID, latency, and an exact `Decimal` cost.
  [`modeladapter.py`](tokenos/services/tokenos-api/tokenos_api/modeladapter.py)
  is the only module that imports the provider SDK, and credentials stay
  server-side.
- **A durable proof gate.** Runs, events, files, and claims persist to SQLite
  with a gap-free sequence that drives both live SSE and replay. Two runs are
  comparable only when they share a contract and price hash, both pass their
  quality gates, usage is complete, outcomes are equal, and provider request IDs
  are present.

The behaviour is **fail closed**: incomplete evidence never becomes zero cost,
and a cheaper rejected answer never becomes a saving.

| Code area | Responsibility |
| --- | --- |
| [Web source](tokenos/apps/web/src/) | Application shell, shared components, existing phases, and run state. |
| [Optimization UI](tokenos/apps/web/src/optimization/) | Mode-specific forms, example defaults, staged actions, SSE handling, and proof views. |
| [FastAPI application](tokenos/services/tokenos-api/tokenos_api/app.py) | Shared API entry point and routing between existing and optimization runs. |
| [Optimization backend](tokenos/services/tokenos-api/tokenos_api/optimization/) | Schemas, fixtures, imports, prompt analysis, authorization, execution, verification, and durable state. |
| [Foundry adapter](tokenos/services/tokenos-api/tokenos_api/modeladapter.py) | Server-side inference and normalized provider usage. |
| [Existing workflow handlers](tokenos/services/tokenos-api/tokenos_api/workflows/) | The original workflow implementations and registry. |
| [Storage layer](tokenos/services/tokenos-api/tokenos_api/storage/) | Existing run state, uploads, and reporting ledger. |

### Key optimization endpoints

| Endpoint | Purpose |
| --- | --- |
| `GET /api/workflows` | Primary workflow definitions. |
| `GET /api/optimization/samples` | Workflow examples with complete defaults. |
| `GET /api/optimization/prompt-examples` | Prompt examples, input content, and complete defaults. |
| `POST /api/optimization/uploads` | Telemetry and representative-input uploads. |
| `POST /api/optimization/context` | Prompt-context uploads. |
| `POST /api/runs` | Create a draft for the selected optimization target. |
| `POST /api/runs/{id}/analyze` | Build the local plan. |
| `POST /api/runs/{id}/optimize` | Approve the plan and compile candidate safeguards. |
| `POST /api/runs/{id}/authorize` | Authorize the protected run. |
| `POST /api/runs/{id}/execute` | Start the authorized work. |
| `GET /api/runs/{id}/events` | SSE progress and replay. |
| `GET /api/runs/{id}/proof` | Final proof. |
| `POST /api/runs/{id}/baseline` | Separately acknowledged matched comparison. |
| `GET /api/optimization/reports` | Filtered reports with separate evidence categories. |

See the [optimization API guide](tokenos/services/tokenos-api/OPTIMIZATION-API.md)
for request shapes, target-specific validation, state transitions, and baseline
rules. The [general API guide](tokenos/services/tokenos-api/API.md) documents
the existing workflow contracts.

## Economics and claim strength

| Label | Evidence it represents |
| --- | --- |
| **Estimated** | A locally computed pre-execution estimate or proposed effect. |
| **Measured current cost** | Imported provider usage priced against the configured table, when sufficient evidence exists. |
| **Measured governed cost** | Executed governed work and actual provider-reported usage, reconciled with the pinned price table. |
| **Projected cost at volume** | A separately labelled extrapolation, not a saving. |
| **Verified saving** | A valid completed comparison whose baseline passed the same requirements and cost more. |

A verified saving requires both routes to complete and pass with identical pinned
inputs, output contract, maximum output length, quality-gate versions, and
price-table version. The baseline must be explicitly requested with model-cost
acknowledgement, and its measured model cost must exceed the governed cost.

Until then, the UI uses states such as **Comparison not run**,
**No valid comparison**, or **No cost saving verified**.

**Zero model tokens is not zero total cost.** Local execution still consumes
compute, storage, and operational effort. Cache eligibility is not a measured
cache hit; only provider-reported cached tokens establish cache usage.

### A worked example

![TokenOS benefits. A measured sample walkthrough reports a verified saving of $0.0065 per run, with a matched all-AI baseline bar at about $0.0067 against a much shorter TokenOS governed route bar at $0.0002, alongside figures of about 97 percent lower measured model spend, 7 of 8 operations using zero model tokens, and 1 Foundry model call. A second column explains how the benefit is created, and a footer row summarises the value to finance, engineering, governance, and product and users.](imgs/TokenOS-Benefits.png)

This is one measured sample run in which both routes completed the same work and
passed the same quality checks. The matched all-AI baseline cost about
**$0.0067**, the governed route cost **$0.0002**, and the difference of
**$0.0065 per run** qualifies as a verified saving only because the baseline
actually ran, matched on every requirement above, and cost more. Seven of eight
operations used zero model tokens; one Foundry call was authorized.

Two caveats printed on the figure apply to every number in it: these are
**sample figures, not a customer claim**, and **zero model tokens does not mean
zero total operating cost**.

## Hosted judge demonstration

<https://tokenos-hack26.yellowwater-54592620.eastus.azurecontainerapps.io>

A public build that walks the complete journey **without calling any model
provider**, so evaluating it costs nothing in model spend. It runs the same
application in a third model mode, `simulated`, selected by
`TOKENOS_MODEL_MODE`. Local and Foundry behaviour is unchanged.

Everything except the model response is genuine. Uploads, parsing, hashing,
duplicate detection, policy lookups, arithmetic, schema validation, secret
scanning, test execution, routing decisions, budget authorisation, and the
quality gates all run for real. Only the model reply is authored, and it is
derived from the caller's own input so the real verification does real work
against it.

Three independent things would have to change before the hosted build could
spend money: the mode, the Foundry endpoint variables (removed), and the
presence of the provider SDK, which is **deliberately absent from the image**,
so a client cannot be constructed even by mistake. The app identity holds
`AcrPull` only.

Simulated runs are marked in the data as well as on screen. Proofs carry
`origin=simulated`, `sim-` prefixed identifiers, and a simulated measurement
label, so a downloaded artifact states its own provenance. They classify as
sample rather than measured evidence, so they can never aggregate as production
spend.

Deliverables live in [`aca/`](aca/): the image, infrastructure, deploy and
rollback scripts, a browser verification script, and a judge walkthrough with
the **known limitations**, most importantly that saved runs do not survive
container replacement. The simulator itself is part of the application at
[`simulator.py`](tokenos/services/tokenos-api/tokenos_api/simulator.py), with
tests in
[`test_simulated_mode.py`](tokenos/services/tokenos-api/tests/test_simulated_mode.py).

## Optional Azure deployment

The Azure Developer CLI project configuration is
[`infra/azure.yaml`](infra/azure.yaml). It deploys the application from
[`tokenos/`](tokenos/) using the root application
[`Dockerfile`](tokenos/Dockerfile), while the Bicep entry point and parameters
remain together under [`infra/`](infra/).

To provision and deploy from the repository root:

```powershell
Set-Location .\infra
azd auth login
azd up
```

The Bicep deployment creates the resource group and application resources,
including the container environment, registry, identity, and Container App.
Foundry integration is optional. When an existing Foundry account is supplied,
the deployment can grant the application identity access and pass the configured
endpoint and deployment aliases to the service. It does not create model
deployments.

Review [`infra/main.parameters.json`](infra/main.parameters.json) before
deployment. Values such as `TOKENOS_FOUNDRY_ACCOUNT_NAME`,
`TOKENOS_FOUNDRY_RESOURCE_GROUP_NAME`, `TOKENOS_FOUNDRY_BASE_URL`, and the model
deployment names are supplied through the selected `azd` environment.

### Redeploying a code change

Once the application is provisioned, shipping a code change does not need
`azd up`. Re-running provisioning against live infrastructure is a much larger
action than a code change warrants, and it can disturb environment variables,
identity, ingress and CORS that are already correct on the running app.
[`infra/redeploy.ps1`](infra/redeploy.ps1) rebuilds the image and repoints the
existing Container App at it, changing nothing else:

```powershell
Set-Location .\infra
.\redeploy.ps1
```

Use `azd up` instead for first-time provisioning, or when the Bicep itself
changes.

The script:

- refuses to run with a dirty working tree, because it tags the image with the
  current commit SHA and tagging modified content with a clean commit's SHA
  would make the image misrepresent what it contains (override with
  `-AllowDirty` and an explicit `-Tag`);
- builds in Azure Container Registry rather than locally, so no Docker daemon is
  required and the build host has the network access the local Docker build
  lacks (see [`tokenos/vendor-wheels/README.md`](tokenos/vendor-wheels/README.md));
- deploys by image **digest** rather than tag, so the revision records exactly
  what shipped: a tag can later be moved, a digest cannot;
- waits for the new revision to reach a running state and then verifies
  `/health`;
- finishes by running the read-only post-deploy check in
  `tokenos/services/tokenos-api/tests/browser/smoke_deployed.py`, which confirms
  the shipped bundle renders and lays out correctly without starting a workflow.
  That last point matters: a deployed app in `foundry` mode spends real tokens
  on every run, so verification must not trigger one.

Targets default to the existing deployment and can be overridden with
`-ResourceGroup`, `-ContainerApp`, `-Registry` and `-Repository`. Run
`Get-Help .\redeploy.ps1 -Full` for the complete parameter list.

One rough edge worth knowing: on Windows the `az acr build` log stream can die
with a `UnicodeEncodeError` because the web build prints a character the Azure
CLI's console writer cannot encode. The remote build is unaffected. The script
therefore ignores the CLI exit code and polls the ACR run record for the real
result.

## Optional Microsoft Foundry configuration

Skip this section for local-only evaluation. It assumes existing model deployments;
the application does not automatically create Foundry model deployments.

The Foundry SDK packages are optional and commented out in the runtime requirements.
Install them into the API environment when enabling inference:

```powershell
.\tokenos\services\tokenos-api\.venv\Scripts\python.exe -m pip install `
  "openai>=1.54" "azure-identity>=1.19"
```

In the terminal that will start the API:

```powershell
az login

$env:TOKENOS_MODEL_MODE = "foundry"
$env:TOKENOS_FOUNDRY_BASE_URL = "https://<resource>.openai.azure.com/openai/v1/"
$env:TOKENOS_FOUNDRY_AUTH_MODE = "entra"
$env:TOKENOS_FOUNDRY_EFFICIENT_DEPLOYMENT = "<efficient-deployment>"
$env:TOKENOS_FOUNDRY_ADVANCED_DEPLOYMENT = "<advanced-deployment>"
$env:TOKENOS_FOUNDRY_BASELINE_DEPLOYMENT = "<baseline-deployment>"

Set-Location .\tokenos\services\tokenos-api
.\.venv\Scripts\python.exe -m uvicorn tokenos_api.app:app `
  --host 127.0.0.1 --port 8000
```

The server identity needs an appropriate inference role, such as **Cognitive
Services OpenAI User**, on the configured resource. Browser-facing model aliases
are `tokenos-efficient`, `tokenos-advanced`, and `tokenos-baseline`.

Configure actual deployment pricing in
[`price_table.json`](tokenos/services/tokenos-api/price_table.json), using the
[unpriced example](tokenos/services/tokenos-api/optimization-price-table.example.json)
as a format reference. Preserve entries needed by existing workflows, supply a
version, and use your actual input/output/cached-input rates rather than assuming
sample values match your account.

Model cost is based on normalized provider usage:

```text
((inputTokens - cachedInputTokens) * inputRate
 + cachedInputTokens * cachedInputRate
 + outputTokens * outputRate) / 1,000,000
```

Reasoning tokens already included in output usage are not charged twice.
The optimization run pins the table and its version/content hash.

Keep credentials **server-side**. Do not place keys in source files, screenshots,
sample fixtures, or `VITE_` environment variables. A health configuration flag
alone does not prove that a paid inference request will succeed.

See [the full configuration guide](tokenos/services/tokenos-api/OPTIMIZATION-API.md)
for authentication, pricing, safeguard refresh, and unavailable states.

## Configuration and local storage

| Setting | Purpose |
| --- | --- |
| `TOKENOS_MODEL_MODE` | Select `local`, configured `foundry` execution, or `simulated` for a cost-free demonstration. An unrecognised value stops startup rather than being guessed at. |
| `VITE_TOKENOS_API_BASE` | UI API URL; defaults to `http://localhost:8000`. Not a place for secrets. |
| `TOKENOS_CORS_ORIGINS` | Comma-separated allowed browser origins; defaults cover localhost/127.0.0.1 on port 5173. |
| `TOKENOS_STORAGE_ROOT` | Local runtime storage directory; defaults to `.tokenos\runtime` under the user's home directory. |
| `TOKENOS_TENANT_ID` | Trusted server-side tenant identifier for the local optimization service. |
| `TOKENOS_PHASE_PACING_MS`, `TOKENOS_OPERATION_PACING_MS`, `TOKENOS_STEP_PACING_MS` | Presentation pacing used by existing execution paths; set to zero for automated checks. |
| `TOKENOS_STREAM_ATTACH_TIMEOUT_SECONDS` | Stream-attachment wait used by existing execution paths. |

See [configuration code](tokenos/services/tokenos-api/tokenos_api/config.py) for
additional limits. Defaults include 10 MB per file and 25 MB combined, with
endpoint-specific checks.

The optimization subsystem persists runs, files, events, and execution claims in
`optimization.sqlite3` under the configured storage root. Tables are created
automatically; no external database service is needed for the local demonstration.
This storage is separate from the existing workflow ledger.

Changing server configuration or prices does not silently rewrite an authorized
contract. Use **Refresh safeguards** for an unauthorized optimized draft; create
a new authorized version for already-protected work.

## Build and test

### Web typecheck and build

From the repository root:

```powershell
npm --prefix .\tokenos\apps\web run typecheck
npm --prefix .\tokenos\apps\web run build
```

Build output goes to `tokenos\apps\web\dist`. The package also provides
`npm run preview` for previewing built assets; the API must still be running,
and its CORS configuration must allow the preview server's actual origin.

### Python and browser test dependencies

```powershell
.\tokenos\services\tokenos-api\.venv\Scripts\python.exe -m pip install `
  -r .\tokenos\services\tokenos-api\requirements-dev.txt
```

### Unit and API tests

```powershell
Push-Location .\tokenos\services\tokenos-api

$env:TOKENOS_MODEL_MODE = "local"
$env:TOKENOS_PHASE_PACING_MS = "0"
$env:TOKENOS_OPERATION_PACING_MS = "0"
$env:TOKENOS_STEP_PACING_MS = "0"
$env:TOKENOS_STREAM_ATTACH_TIMEOUT_SECONDS = "0"

.\.venv\Scripts\python.exe -m compileall -q tokenos_api
.\.venv\Scripts\python.exe -m pytest -q

Pop-Location
```

### End-to-end and visual tests

```powershell
Push-Location .\tokenos\services\tokenos-api

$env:TOKENOS_BROWSER_CHANNEL = "msedge"
.\.venv\Scripts\python.exe -m pytest -c pytest-browser.ini -q

Pop-Location
```

The [browser test configuration](tokenos/services/tokenos-api/pytest-browser.ini)
is separate from the [unit/API configuration](tokenos/services/tokenos-api/pytest.ini).
Browser tests start isolated API and Vite servers on random loopback ports,
use temporary storage, and shut down the processes they started.

If Edge is not available, install Playwright Chromium and set
`TOKENOS_BROWSER_CHANNEL` to an empty string before the browser run:

```powershell
.\tokenos\services\tokenos-api\.venv\Scripts\python.exe -m playwright install chromium
$env:TOKENOS_BROWSER_CHANNEL = ""
```

Set `TOKENOS_SCREENSHOT_DIR` to an absolute output directory when you want captures.
The visual checks validate layout geometry, wrapping, clipping, and dynamic fields;
they are not pixel-baseline comparisons.

Coverage includes explicit authorization, example defaults, mode switching,
uploads, SSE/fallback behavior, quality failures, pricing, baseline eligibility,
and compatibility with the original workflows. Automated provider-positive cases
use isolated test doubles rather than the `simulated` mode: that mode exists for
the hosted demonstration, and a test that proved something about the simulator
would not prove anything about a real provider call.

For **recorded results**, see the
[prompt/workflow implementation report](tokenos/PROMPT-OPTIMIZATION-REPORT.md).
Results there are snapshots of executed validation, not promises about a future run.

## Repository map

```text
.
|-- README.md                       This entry point
|-- aca/                            Hosted judge demonstration (simulated AI)
|   |-- Dockerfile                  Judge image; omits the provider SDK on purpose
|   |-- .dockerignore               Build-context allowlist
|   |-- main.bicep                  Declarative form of the deployed configuration
|   |-- deploy.ps1                  Build, roll out, verify
|   |-- rollback.ps1                Restore the real-model image
|   |-- verify_deployed.py          Browser verification of the judge journey
|   `-- README.md                   Judge walkthrough and limitations
|-- docs/                           Product and implementation specifications
|-- imgs/                           Diagrams referenced by this README
|-- infra/                          Azure Developer CLI and Bicep deployment
|   |-- azure.yaml                  azd project and service configuration
|   |-- main.bicep                  Subscription-scope deployment entry point
|   |-- main.parameters.json        azd environment parameter mapping
|   |-- resources.bicep             Application infrastructure
|   |-- foundry-access.bicep        Optional access to an existing Foundry account
|   `-- redeploy.ps1                Rebuild and roll out a code change (no reprovision)
`-- tokenos/                        Runnable application
    |-- apps/web/                   React, TypeScript, and Vite
    |-- services/tokenos-api/       FastAPI, execution, verification, and tests
    |-- README.md                   Application-level documentation
    |-- AGENTS.md                   Working agreements for code changes
    |-- STARTUP.md                  Additional startup/process guidance
    |-- WORKINGS.md                 Architecture background
    |-- start.ps1                   Convenience launcher
    `-- stop.ps1                    Port-based process helper; review before use
```

Useful directories: [application](tokenos/), [web](tokenos/apps/web/),
[API](tokenos/services/tokenos-api/), [tests](tokenos/services/tokenos-api/tests/),
[infrastructure](infra/), and [specifications](docs/).

Local editor settings, helper scripts, private notes, demo assets, backups, and
supplementary data are intentionally not part of the tracked repository.

## Documentation guide

| Read this | For |
| --- | --- |
| [Application README](tokenos/README.md) | Workflow background and application-level guidance. |
| [Optimization API and configuration](tokenos/services/tokenos-api/OPTIMIZATION-API.md) | Current prompt/workflow contracts, safeguards, usage, storage, and Foundry setup. |
| [General API guide](tokenos/services/tokenos-api/API.md) | Existing workflow APIs and compatibility context. |
| [Azure deployment configuration](infra/azure.yaml) | The `azd` project definition for the Bicep infrastructure and TokenOS service. |
| [Azure deployment entry point](infra/main.bicep) | Resource-group creation, application resources, and optional Foundry access wiring. |
| [Architecture background](tokenos/WORKINGS.md) | TokenOS's local-first control flow and governance model. |
| [Prompt/workflow implementation report](tokenos/PROMPT-OPTIMIZATION-REPORT.md) | Delivered work, follow-up fixes, validation results, and limitations. |
| [Earlier implementation report](tokenos/IMPLEMENTATION-REPORT.md) | Historical workflow-optimization delivery notes. |
| [Working agreements](tokenos/AGENTS.md) | Validation expectations and engineering conventions. |

### Product specifications

The files under [`docs/`](docs/) record successive iterations:

- [Interactive UI specification](docs/1-TOKENOS-INTERACTIVE-UI-IMPLEMENTATION-SPEC.md)
- [Phase snapshot guide](docs/1-TOKENOS-UI-PHASE-SNAPSHOT-REPLICATION-GUIDE.md)
- [Real-input and local-API implementation](docs/2-TOKENOS-REAL-INPUT-AND-LOCAL-API-IMPLEMENTATION.md)
- [Real-input UI update](docs/2-TOKENOS-UI-REAL-INPUT-IMPLEMENTATION-UPDATE.md)
- [Verified-savings plan](<docs/3-TOKENOS-VERIFIED-SAVINGS-IMPLEMENTATION-PLAN(1).md>)
- [Verified-savings report](docs/3-TOKENOS-VERIFIED-SAVINGS-IMPLEMENTATION-REPORT.md)
- [Existing workflow optimization](docs/4-TOKENOS-EXISTING-WORKFLOW-OPTIMIZATION-IMPLEMENTATION.md)
- [Prompt and workflow optimization](docs/5-TOKENOS-PROMPT-AND-WORKFLOW-OPTIMIZATION-IMPLEMENTATION.md)

Older specifications and reports describe earlier states. Use the current API
guide and the latest report follow-ups for implemented behavior and documented
deviations.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| UI says the API is unavailable | Start the API, check `/health`, and confirm `VITE_TOKENOS_API_BASE`. |
| A new endpoint returns 404 or example defaults are missing | Restart the API process to load changed Python code, then reload the browser to fetch the current catalogs. Restart Vite if it was launched from a different checkout or is serving stale assets. |
| Planning is disabled with your own inputs | Check the selected mode's required fields, validated artifacts, desired outcome, quality requirements, and goal. Prompt answer-quality checks also need an expected result. |
| An example has empty required fields | Re-enter the example source after refreshing the current catalog. Examples should populate automatically; no manual field entry is required for planning. |
| Protect blocks a model route | Read the failed safeguard. Check deployment configuration, prices, context limits, budget, supported quality gates, and required approvals. |
| No saving is displayed | A plan or governed run alone is insufficient. The separately acknowledged baseline must finish, pass the identical gates, and cost more. |
| Vite chooses a different port | Resolve the conflict or use that port intentionally; configure the API to allow its exact browser origin. |
| Browser tests cannot find a browser | Use the installed Edge channel or install Playwright Chromium as described above. |

## Scope and limitations

- This is a **local, single-tenant prototype**, not a production-hardened
  multi-user deployment. Add a suitable authentication and hosting boundary before
  exposing the API to other users.
- Prompt token estimates are not provider measurements. A strict output contract
  can make a short prompt longer; that is not reported as a saving.
- Deterministic prompt routing is intentionally narrow: a locally provable keyed
  source can be retrieved; other interpretation may require a model.
- Open-ended answer quality is not magically verified. Expected outcomes or a
  supported evaluator are required. Unsupported gates block rather than auto-pass.
- The optimization code-validation fixture uses an allowlisted arithmetic adapter;
  a diagnosis does not repair a failing test or authorize arbitrary code execution.
- Sample inputs are reproducible examples, not evidence of customer spending.
  Historical provider telemetry, actual governed usage, and projections remain distinct.
- The bundled application connection is sample-scoped. Real integrations require
  registered server-side adapters and explicit scopes.
- No live paid Foundry run is implied by the recorded test results. Paid execution
  needs your configuration and authorization.
