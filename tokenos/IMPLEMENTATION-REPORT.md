# TokenOS existing workflow optimization implementation report

Status: core implementation validated; final registered-archive adapter validation pending.

Source of truth: [the attached specification](../4-TOKENOS-EXISTING-WORKFLOW-OPTIMIZATION-IMPLEMENTATION.md).

## Compatibility decision

The checked-in application uses `document_review`, `software_validation`, and
`deadline_processing` for its first three workflows. These IDs are retained to
preserve existing API, storage, and UI behavior. The specification refers to
`validate_software` and `meet_deadline`; these do not replace existing persisted IDs.
The new primary workflow is `workflow_optimization`. Legacy `false_savings`
economics and endpoints are retained rather than relabelled as new measured runs.

## Completed implementation

- Exact approved Step 1 heading/subheading, four card titles/supporting strings,
  selected workflow identity, accessible names, history, and revised screenshots.
- Explicit Describe, Plan, Optimize, Protect, Run, Verify, and Prove transitions.
  Analysis, protected execution, and paid comparison are separate actions.
- Telemetry/native JSON, JSONL, CSV and ZIP imports; representative file uploads and
  3-20 pasted requests; manifest hashes, roles, detected types and size checks.
- Four real local-engine fixtures. Sample metrics are badged; no runtime provider
  simulation or precomputed successful execution is installed.
- Local planning/current-route analysis, independent optimization levers, safe
  exact reuse, and conditional efficient/advanced routing.
- Immutable Protect contracts, human approval, artifact handling, scope checks,
  bounded per-call reservations, output contracts and pinned prices.
- Server-only Foundry calls with strict provider-usage normalization, request
  identity/version, latency, reconciliation, output verification, and safe failure.
- SSE progress/replay with authoritative polling only as fallback.
- Outcome-first verification/proof, distinct operations versus model calls,
  collapsed evidence/download, and separate volume projections.
- Explicit all-AI acknowledgement, duplicate-run protection, matched-contract
  validation, and a strict quality/completion/cost gate for saving claims.
- Additive SQLite run/file/event/claim tables and separate measured/sample/projected
  reporting. Existing legacy ledger and APIs remain supported.
- Failed verification offers **Inspect failed checks**, **Adjust plan**, and
  **Escalate with approval**, without weakening quality or bypassing Protect.

## Validation results

These are executed results, not estimates:

| Check | Result |
| --- | --- |
| Frontend `npm run typecheck` | Passed |
| Frontend `npm run build` | Passed; 58 modules, production JavaScript 286.04 kB |
| Full existing/new unit and API suite | 128 passed before the final registered-archive extension |
| Browser acceptance suite | 17 passed in 34.20 seconds, no warnings |
| VS Code diagnostics | No errors |

Browser tests use real Edge, Vite, FastAPI, uploads, SQLite records, SSE and local
execution. The successful measured sample produced **4 accepted outcomes**, **2
local operations**, **2 validated reuses**, **0 model calls**, and **$0 model spend**.
That is not a savings claim: its paid baseline was not executed.

The browser suite covers all seven phases, exact copy/accessibility, all four
fixture selections, the three unchanged workflows, uploaded manifest integrity,
invalid/oversized uploads, pasted inputs, deliberately failed quality, missing
Foundry blocks, sample provenance, telemetry-only analysis, explicit human approval,
baseline consent/unavailability, persistence/reopening, collapsed evidence,
separate projections, and SSE failure recovery.

Unit/API tests cover measured pricing (including cached/reasoning usage), actual
output acceptance, failed/equal/cheaper baseline cases, positive eligible
comparisons, all pinned-field mismatch cases, scope isolation, configuration
refresh, concurrency, unsafe reuse, invalid/nonfinite inputs, and provider errors.
Positive provider/baseline tests use explicit isolated test doubles. No live
Foundry invocation or live customer saving is claimed.

Validation issues found and fixed:

- Browser proof readiness initially treated an asynchronous predicate as complete;
  it now waits for an actual final server proof.
- A browser `conftest` name collided with existing legacy test imports. Browser
  fixtures are now in an explicit harness, preserving default unit discovery.
- A separate browser pytest configuration avoids an unrelated system-environment
  asyncio-plugin warning without changing the original unit/API configuration.
- Bundled Chromium was absent; the already-installed Edge channel worked.
  No browser download or dependency installation was performed during this task.

## Run the application

From this `tokenos` directory, in separate terminals:

```powershell
# API: install requirements only if the environment is not already prepared.
Set-Location services\tokenos-api
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt
$env:TOKENOS_MODEL_MODE = "local"
.\.venv\Scripts\python.exe -m uvicorn tokenos_api.app:app --host 127.0.0.1 --port 8000
```

```powershell
# UI
Set-Location apps\web
npm ci
npm run dev
```

Open `http://localhost:5173`; API docs are at `http://127.0.0.1:8000/docs`.
Do not stop unrelated processes if a port is occupied; use another loopback port,
set `VITE_TOKENOS_API_BASE`, and allow that UI origin with `TOKENOS_CORS_ORIGINS`.

## Run validation

```powershell
# From apps\web
npm run typecheck
npm run build
```

```powershell
# From services\tokenos-api
$env:TOKENOS_MODEL_MODE = "local"
$env:TOKENOS_PHASE_PACING_MS = "0"
$env:TOKENOS_OPERATION_PACING_MS = "0"
$env:TOKENOS_STEP_PACING_MS = "0"
$env:TOKENOS_STREAM_ATTACH_TIMEOUT_SECONDS = "0"
.\.venv\Scripts\python.exe -m compileall -q tokenos_api
.\.venv\Scripts\python.exe -m pytest -q
$env:TOKENOS_BROWSER_CHANNEL = "msedge"
.\.venv\Scripts\python.exe -m pytest -c pytest-browser.ini -q
```

The actual browser run in this environment used the existing interpreter
`C:\Users\varghesejoji\AppData\Local\Programs\Python\Python313\python.exe`, which
already had Playwright, rather than installing it into the project virtualenv.
The unit/API run used `services\tokenos-api\.venv\Scripts\python.exe`.
Installing `requirements-dev.txt` into one virtualenv supports both commands above.
On non-Windows systems, use installed Chromium and the corresponding Playwright
browser setup instead of the Edge channel.

To regenerate captures, set `TOKENOS_SCREENSHOT_DIR` to
`tokenos\samples\screenshots\optimization` before running the browser suite. Test
servers use temporary storage and random ports, and are terminated by the harness.

## Foundry configuration

See [the local API/configuration guide](services/tokenos-api/OPTIMIZATION-API.md)
for the exact staged API and setup instructions. In brief:

1. Use existing Foundry/OpenAI deployments and sign in locally with `az login`.
2. Set server-only `TOKENOS_MODEL_MODE=foundry`, `TOKENOS_FOUNDRY_BASE_URL`,
   `TOKENOS_FOUNDRY_AUTH_MODE=entra`, and efficient/advanced/baseline deployment
   environment variables.
3. Give the server identity the necessary inference role on the resource.
4. Merge actual deployment rates into the server's `price_table.json`, using the
   [unpriced example](services/tokenos-api/optimization-price-table.example.json);
   supply a version and actual cached/input/output rates, not assumed list prices.
5. Refresh an unauthorized draft's safeguards, explicitly authorize, and execute.
6. Separately acknowledge any all-AI comparison cost.

Credentials never belong in `VITE_` variables, browser fields for this workflow, or
committed data. Missing credentials/pricing or unavailable inference cannot yield
simulated usage, successful verification, or a saving.

## Files changed

### Frontend

- `apps/web/src/App.tsx`
- `apps/web/src/api/client.ts`
- `apps/web/src/components/ApiHealthIndicator.tsx`
- `apps/web/src/components/AppHeader.tsx`
- `apps/web/src/components/HistoryDrawer.tsx`
- `apps/web/src/components/WorkflowChoices.tsx`
- `apps/web/src/phases/DescribePhase.tsx`
- `apps/web/src/state/runContext.ts`
- `apps/web/src/state/RunProvider.tsx`
- `apps/web/src/state/runStore.ts`
- `apps/web/src/optimization/client.ts`
- `apps/web/src/optimization/types.ts`
- `apps/web/src/optimization/OptimizationDescribe.tsx`
- `apps/web/src/optimization/OptimizationJourney.tsx`
- `apps/web/src/optimization/OptimizationViews.tsx`
- `apps/web/src/optimization/optimization.css`
- `apps/web/dist/` regenerated by the production build.

### Backend, schema and tests

- `services/tokenos-api/tokenos_api/app.py`
- `services/tokenos-api/tokenos_api/modeladapter.py`
- `services/tokenos-api/tokenos_api/workflows/__init__.py`
- `services/tokenos-api/tokenos_api/workflows/workflow_optimization.py`
- `services/tokenos-api/tokenos_api/optimization/__init__.py`
- `services/tokenos-api/tokenos_api/optimization/engine.py`
- `services/tokenos-api/tokenos_api/optimization/fixtures.py`
- `services/tokenos-api/tokenos_api/optimization/imports.py`
- `services/tokenos-api/tokenos_api/optimization/quality.py`
- `services/tokenos-api/tokenos_api/optimization/router.py`
- `services/tokenos-api/tokenos_api/optimization/schemas.py`
- `services/tokenos-api/tokenos_api/optimization/store.py`
- `services/tokenos-api/optimization-price-table.example.json`
- `services/tokenos-api/requirements-dev.txt`
- `services/tokenos-api/pytest-browser.ini`
- `services/tokenos-api/tests/test_workflow_labels.py`
- `services/tokenos-api/tests/test_optimization_api.py`
- `services/tokenos-api/tests/test_optimization_unit.py`
- `services/tokenos-api/tests/browser/harness.py`
- `services/tokenos-api/tests/browser/e2e_optimization.py`

### Documentation, fixtures and captures

- `README.md`, `WORKINGS.md`, `IMPLEMENTATION-REPORT.md`
- `services/tokenos-api/API.md`, `services/tokenos-api/OPTIMIZATION-API.md`
- `samples/README.md`, `samples/OPTIMIZATION-WALKTHROUGH.md`
- `samples/optimization-requests.json`
- `samples/normalized-telemetry-template.csv`
- `samples/screenshots/optimization/01-describe.png`
- `samples/screenshots/optimization/01-connected.png`
- `samples/screenshots/optimization/02-plan.png`
- `samples/screenshots/optimization/03-optimize.png`
- `samples/screenshots/optimization/04-protect.png`
- `samples/screenshots/optimization/05-run.png`
- `samples/screenshots/optimization/06-verify.png`
- `samples/screenshots/optimization/07-prove.png`
- `samples/screenshots/optimization/07-analyze.png`
- `samples/screenshots/optimization/08-history.png`

## Explicit limitations and intentional boundaries

- **Live paid Foundry/baseline execution was not tested.** Tests validate the adapter
  and claims contract without spending user model tokens. No Azure resources or
  model deployments were created.
- The service is **local and single-tenant**, with trusted tenant identity supplied
  by server configuration. Production multi-user authentication and hosting are
  not introduced by this feature.
- Open-ended answer quality needs independent expected outputs or a registered
  verifier. Unsupported schema constructs, missing citation evidence, and
  unsupported test requirements block Protect; they are not marked successful.
- The new code-validation fixture uses a safe finite arithmetic test adapter, not
  arbitrary uploaded code execution. The first three workflows retain their
  existing handlers.
- Reuse is conservatively exact and validated for matching context, access scope,
  freshness and contract. Approximate semantic similarity is not enough.
- Batch handling is an eligibility recommendation, as specified, not a new Azure
  batch-submission service.
- Baseline reruns require a new authorized run version; a previously claimed run
  cannot silently spend again. Interrupted work is not automatically replayed.
- The full approved post-baseline hero is shown only when fewer model calls are
  actually proved. If quality and cost improve without fewer calls, the headline
  omits the unsupported “Fewer AI calls” statement.

## Evaluator materials

- [Seven-phase walkthrough](samples/OPTIMIZATION-WALKTHROUGH.md)
- [Upload fixtures and screenshots](samples/README.md)
- [Measured local Prove capture](samples/screenshots/optimization/07-prove.png)
