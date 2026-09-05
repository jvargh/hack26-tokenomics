# TokenOS Verified Savings — Implementation Report

Implements `TOKENOS-VERIFIED-SAVINGS-IMPLEMENTATION-PLAN(1).md` end to end against the
existing TokenOS codebase (`tokenos/`). This report lists what was completed, what was
already in place before this pass, known gaps, how to configure Foundry locally, and the
exact commands to run the demo and the test suite.

Scope note: most of the plan's core architecture — the four workflows with real input
forms, hybrid Foundry routing with efficient→advanced escalation, a versioned price
table, tiktoken-based *projected* (never *measured*) comparator, SSE streaming, and
protection checks — already existed from prior sessions. This pass focused on closing the
remaining truthfulness and completeness gaps called out in the plan, rather than
rewriting working code.

## 1. What was completed this pass

### Truthfulness fix (the most important change)

- **`baseline.evaluate_saving()`** (`tokenos_api/baseline.py`) — extracted the previous
  inline if/elif eligibility chain into a pure, unit-tested function, and **fixed a real
  bug**: previously an equal-quality comparison was labelled a saving even when the
  baseline cost the same as or less than the governed run. Now `saving <= 0` correctly
  returns `no_saving` (a valid comparison, just no saving), distinct from
  `invalid_comparison` (the comparison itself can't be trusted — a quality gate failed,
  the governed decision was incomplete, the contract didn't match, or no price table is
  configured). See the status table in [API.md](tokenos/services/tokenos-api/API.md#post-apirunsrun_idbaseline).

### Cost-acknowledgement gate

- `POST /api/runs/{id}/baseline` now requires `{"acknowledged": true}` in the request
  body and returns `400` otherwise — enforced server-side, not just a UI checkbox, so no
  client can trigger real model spend silently.
- The Prove screen (`ProvePhase.tsx`) has a required checkbox ("I understand this
  comparison invokes a model and may incur model cost.") gating the baseline button, with
  copy stating the expected maximum spend before the click.

### Dedicated read-only comparison endpoint

- `GET /api/runs/{id}/comparison` — returns the cached baseline result, or
  `{"status": "not_requested"}` before one has run. Never itself executes a model call, so
  the UI (or a report) can poll/refresh the comparison state without risking spend.

### Durable persistence (the plan's "database/schema" deliverable)

- New `tokenos_api/storage/ledger.py` — a SQLite-backed ledger (`run_proofs`,
  `run_baselines` tables), independent from the existing in-memory `storage/runs.py` used
  for live SSE state. Every completed proof and baseline computation is written once, so
  route counts, model calls, and costs can be audited after a process restart, not just
  observed live in the browser.
- Wired into `runner.py` (on run completion) and the `/baseline` handler.
- New `GET /api/reports/runs` endpoint — an enterprise reporting view reading only from
  this ledger; its `summary.verified_savings_count`/`total_verified_saving_usd` only ever
  count rows whose baseline status is `eligible_saving`, so a `no_saving` or
  `invalid_comparison` baseline can never inflate a reported total.

### Real provider usage fields, not just tiktoken estimates

- `ModelResult` (`modeladapter.py`) now captures `cached_input_tokens` and
  `reasoning_tokens` from the Azure OpenAI response's `usage.prompt_tokens_details` /
  `usage.completion_tokens_details` when the provider includes them — never estimated,
  defaults to `0` when absent.
- Deduplicated the three workflows' inline usage-record dicts into one shared
  `workflows/_util.py::usage_fields()` helper so every workflow reports usage the same way.

### Automated test suite (the plan's biggest missing deliverable)

36 new `pytest` tests across 6 files, all running in-process against a real `TestClient`
driving actual workflow execution — no live server, no credentials, no network:

| File | Covers |
| --- | --- |
| `test_pricing_unit.py` | Price lookup, cost calculation, "not configured" handling |
| `test_savings_eligibility.py` | Every branch of `evaluate_saving`: eligible saving, no-saving at equal/lower cost, and each invalid-comparison reason, in priority order |
| `test_ledger_unit.py` | Ledger persistence, idempotency, proof↔baseline join, summary aggregation |
| `test_comparison_endpoint.py` | Acknowledgement gate (400/200), comparison cache round-trip, 404s |
| `test_route_counts.py` | Route/model-call/cost counts reconcile across `routing`, `usage`, and per-operation `detail` for all 4 workflows; regression guard that `document_review`'s summary step never silently routes to a model |
| `test_foundry_unavailable.py` | Health/workflows report unavailable correctly; `document_review` still completes with unresolved items instead of inventing an answer; baseline refuses to spend |

`tests/conftest.py` forces `TOKENOS_MODEL_MODE=local` and a scratch `TOKENOS_STORAGE_ROOT`
**before** `tokenos_api` is imported, so the suite is deterministic even though the
project's own `.env` configures real Foundry credentials for manual/demo use.

Added `pytest.ini` (scopes discovery to `tests/`) and `requirements-dev.txt`
(`pytest`, `pytest-asyncio`, `httpx`, `requests`).

**Result: 36/36 passing, ~82s.**

### Documentation

- New [API.md](tokenos/services/tokenos-api/API.md) — every endpoint with real captured
  request/response examples, including the acknowledgement gate, the comparison status
  enum, and the ledger report shape.
- Updated the main [README.md](tokenos/README.md) — API table now lists `/comparison` and
  `/reports/runs`, the baseline description now states the acknowledgement requirement,
  the Tests section documents the automated `pytest` suite vs. the manual live scripts,
  and the "Turning the projection into a proof" section reflects the acknowledgement gate
  and `evaluate_saving` behavior.

## 2. What already existed and was verified, not rebuilt

- All 4 workflows (`document_review`, `software_validation`, `deadline_processing`,
  `false_savings`) with dynamic, schema-driven input forms.
- Server-side Foundry adapter (`modeladapter.py`) with `tokenos-efficient` /
  `tokenos-advanced` deployments, Entra ID auth, and efficient→advanced escalation only
  when a deterministic quality check fails.
- `price_table.json` — versioned by deployment, model, model version, region, and
  effective date; reports "not configured" rather than a made-up cost when unpriced.
- tiktoken-based comparator labelled a **projection**, never presented as measured spend.
- SSE event stream (`phase.started`, `operation.completed`, `run.completed`, etc.) with
  `Last-Event-ID` replay.
- Protection checks (budget ceiling, human approval gating, data classification).
- Registered connector stubs (`connectors.py`) for the "connected application" input path.

## 3. Known gaps / deliberate non-changes

- **`false_savings.py` uses zero model calls.** Every operation in this workflow routes to
  `software`. This is arguably thematically correct (a workflow that *finds* false AI-
  savings claims via deterministic rules doesn't need AI itself to do that), but it means
  this workflow alone cannot demonstrate hybrid routing or a paired baseline. Not changed
  in this pass — flagged here as a decision point, not fixed, per the instruction to focus
  on truthfulness/completeness of the existing architecture rather than expanding
  domain-specific features.
- **SSE event names use dot notation** (`phase.started`, `operation.completed`) rather
  than the plan's illustrative underscore examples (`phase_started`). This is a pre-
  existing, working convention; renaming it was judged cosmetic/low-value and risked
  breaking the already-working frontend event handlers, so it was left as-is.
- **Legacy manual/live test scripts** (`tests/test_workflows_e2e.py`,
  `tests/test_workflows_live.py`, `tests/test_full_matrix.py`,
  `tests/check_prove_numbers.py`) were left in place rather than folded into the pytest
  suite. They expose no `def test_*` functions (only `if __name__ == "__main__":` entry
  points), need a running server (and, for the last one, a real Foundry deployment) to be
  useful, and pytest safely collects zero test items from them. They remain the
  recommended path for live-Foundry smoke verification; the new pytest suite is the
  recommended path for CI/automated verification.
- **`cached_input_tokens`/`reasoning_tokens` capture is structurally verified only** — the
  extraction code was reviewed against the Azure OpenAI response shape and exercised via
  local-mode tests (where these fields are always `0`, since no model call occurs), but
  has not yet been exercised against a live Foundry response with these fields actually
  populated. Recommend a manual check with `tests/check_prove_numbers.py` against a real
  deployment before judging.
- **No `POST /baseline` rate limit or per-run cap.** The acknowledgement gate prevents
  *silent* spend, but nothing currently stops an operator from POSTing `/baseline`
  repeatedly for the same run. Given the plan's explicit "only run a paired baseline
  during the judge demo or explicit Proof mode" framing, this is left as an operational
  discipline (the UI only exposes one baseline button per proof) rather than an enforced
  server-side limit.

## 4. Configuring Foundry locally

The local API is always the control plane; Foundry only supplies reasoning when
deterministic rules and the efficient model can't resolve something. To exercise the
hybrid path for real:

```powershell
Set-Location tokenos\services\tokenos-api
az login
python -m pip install openai azure-identity
.\start-foundry.ps1
```

Or set the environment variables directly:

```powershell
$env:TOKENOS_MODEL_MODE = "foundry"
$env:TOKENOS_FOUNDRY_BASE_URL = "https://<resource>.openai.azure.com/openai/v1/"
$env:TOKENOS_FOUNDRY_EFFICIENT_DEPLOYMENT = "<efficient deployment>"
$env:TOKENOS_FOUNDRY_ADVANCED_DEPLOYMENT = "<advanced deployment>"
$env:TOKENOS_FOUNDRY_AUTH_MODE = "entra"
```

The signed-in principal needs the **Cognitive Services OpenAI User** role on the account:

```powershell
az role assignment create --assignee <upn-or-object-id> `
  --role "Cognitive Services OpenAI User" `
  --scope "/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<account>"
```

Confirm with `GET /health` — expect `"foundryAvailable": true` and both deployment names
populated. Populate `price_table.json` with your real per-deployment prices before
treating any cost figure as your actual spend; until then the UI reports *Measured usage,
price table not configured* instead of a fabricated number.

This repo's own `.env` (not committed — see `.gitignore`) is already configured this way
for the demo account; the automated test suite deliberately overrides it back to local
mode (see `tests/conftest.py`) so tests never depend on it being present or valid.

There is also an in-app Foundry configuration panel (`GET`/`POST /api/foundry/config`,
`POST /api/foundry/test`) so an operator can enter these values without editing `.env` —
it never accepts or displays a credential in the browser; Entra ID auth is resolved
server-side.

## 5. Commands

### Run the demo

```powershell
# Terminal 1 — API (local mode; add Foundry env vars first for the hybrid demo)
Set-Location tokenos\services\tokenos-api
.\.venv\Scripts\Activate.ps1
python -m uvicorn tokenos_api.main:app --host 127.0.0.1 --port 8000

# Terminal 2 — UI
Set-Location tokenos\apps\web
npm run dev            # http://localhost:5173
```

### Run the automated test suite

```powershell
Set-Location tokenos\services\tokenos-api
python -m pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -v          # 36 tests, ~82s, no server/credentials needed
```

### Run the manual/live verification scripts (need a running server)

```powershell
Set-Location tokenos\services\tokenos-api
python tests\test_workflows_live.py   # smoke: all four workflows complete
python tests\test_full_matrix.py      # full matrix: 74 hand-derived assertions
python tests\check_prove_numbers.py   # inspect a real governed run + baseline (needs Foundry)
```

### Frontend checks

```powershell
Set-Location tokenos\apps\web
npx tsc --noEmit
npm run build
```

## 6. Verification performed for this report

- Full new `pytest` suite: **36 passed**, 0 failed (one real bug found and fixed along the
  way — `software_validation`'s real subprocess/archive work needs a longer poll window
  than the original 5s test timeout; fixed in `tests/conftest.py`'s `run_workflow()`).
- Live smoke test against a running local-mode server confirmed: `POST /baseline` returns
  `400` without acknowledgement and `200` with it; `GET /comparison` correctly reports
  `not_requested` before a baseline runs and returns the cached `unavailable` result after;
  `GET /reports/runs` aggregates real ledger rows with correct `summary` totals.
  All example payloads in `API.md` were captured from these real runs, not hand-written.
- `npx tsc --noEmit` and `npm run build` both pass cleanly on the frontend after all
  changes.
- `pytest tests --collect-only` confirms the legacy manual scripts contribute zero test
  items and cause no collection errors or accidental network calls.
