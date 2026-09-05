# TokenOS API

Local FastAPI service for TokenOS: uploads, plan compilation, governed execution, live
events, measured proof, the paired all-AI baseline, and the durable reporting ledger.

Base URL (local dev): `http://127.0.0.1:8000`. Interactive OpenAPI docs are always
available at `http://127.0.0.1:8000/docs`. Every route below except `/health` is prefixed
with `/api`.

For the new `workflow_optimization` request, staged authorization, normalized inputs,
SSE/proof schema, storage, reporting, and server-only Foundry configuration, see
[OPTIMIZATION-API.md](OPTIMIZATION-API.md). The examples below retain the legacy
snake_case contract used by the first three workflows.

Legacy examples in this document are captured responses from a local-mode run (no
Foundry deployment configured — `TOKENOS_MODEL_MODE=local`), trimmed for length where
noted. Field names and shapes are exact; only long arrays are abbreviated with `…`.

## Conventions

- All costs are USD, all timestamps are ISO-8601 with timezone offset.
- Nothing in this API is simulated. A field is either a real measurement (token counts
  from a provider's `usage` object, wall-clock durations, calculated cost from the pinned
  price table) or explicitly labelled as a projection/estimate in its own `*_status` or
  `*_label` field (e.g. `"comparator_status": "Projection, not measured spend"`).
- Governed execution may spend model tokens only after authorization. A paired baseline
  requires a separate, explicit cost acknowledgement. Read-only state, proof, reporting,
  and comparison endpoints never initiate model calls.

---

## `GET /health`

Service status, model mode, and Foundry availability. No auth, safe to poll.

**Response 200**
```json
{
  "status": "ready",
  "version": "0.1.0",
  "modelMode": "local",
  "foundryAvailable": false,
  "efficientDeployment": null,
  "advancedDeployment": null,
  "workflows": [
    "document_review",
    "software_validation",
    "deadline_processing",
    "workflow_optimization"
  ]
}
```

When Foundry is configured and reachable, `modelMode` is `"foundry"`, `foundryAvailable`
is `true`, and both deployment names are populated.

---

## `GET /api/workflows`

Returns every workflow's input schema (upload roles, form fields, defaults, validation
constraints) so the UI can render forms without hard-coding them.

**Response 200 (abbreviated)**
```json
{
  "workflows": [
    {
      "workflow_id": "document_review",
      "label": "Review documents against rules",
      "short_label": "Upload records and policies. TokenOS checks what software can verify before using AI for unclear cases.",
      "description": "Upload records and policies. TokenOS checks what software can verify before using AI for unclear cases.",
      "uploads": [
        { "role": "review-input", "required": true, "…": "…" },
        { "role": "governing-rules", "required": true, "…": "…" }
      ],
      "fields": [
        {
          "name": "review-focus",
          "label": "What should be checked?",
          "control": "textarea",
          "required": true,
          "default": "Unsupported charges and missing approvals",
          "maxLength": 500
        }
      ]
    }
  ]
}
```

`label` is the card title and `short_label` is the supporting text rendered beneath it.
`description` carries the same approved supporting string, because the selected-workflow
panel ("Provide the work") renders it — keeping the two fields identical is what stops the
card and the panel drifting into separate wordings. `tests/test_workflow_labels.py`
asserts all of this verbatim.

The first three `workflow_id` values (`document_review`, `software_validation`,
`deadline_processing`) remain stable. `workflow_optimization` replaces the fourth
selection. The legacy `false_savings` API remains supported, but is not returned as a
primary workflow. The specification's `validate_software` and `meet_deadline` names do
not rename the existing persisted IDs.

| `workflow_id` | Card title | Supporting text |
| --- | --- | --- |
| `document_review` | Review documents against rules | Upload records and policies. TokenOS checks what software can verify before using AI for unclear cases. |
| `software_validation` | Test a code change | Upload or connect a change. TokenOS runs checks first and uses AI only to investigate unresolved failures. |
| `deadline_processing` | Process records by a deadline | Submit a workload and due time. TokenOS completes routine records locally and reserves AI for exceptions. |
| `workflow_optimization` | Optimize an existing AI workflow | Connect an AI application or prior run. TokenOS finds the lowest-cost route that still meets the required quality. |

---

## `POST /api/uploads`

Uploads and validates real files (`multipart/form-data`). Returns server-issued
`upload_id`s — the browser never uses a filename as a path, and archives are checked for
path traversal.

**Request** — `multipart/form-data` with fields `workflow_id`, `role`, and one or more
`files`.

**Response 200**
```json
{
  "uploads": [
    {
      "upload_id": "upl-563d81618f49",
      "name": "openapi.json",
      "role": "supporting-evidence",
      "workflow_id": "software_validation",
      "media_type": "application/json",
      "size_bytes": 373,
      "status": "ready",
      "data_classification": "internal",
      "extracted_character_count": 373,
      "detail": {},
      "origin": "upload"
    }
  ]
}
```

---

## `POST /api/uploads/sample`

Materializes the bundled sample input for a workflow through the **same** upload and
extraction pipeline as a real upload — so a sample run is labelled `Measured sample run`,
never `Simulated`.

**Request**
```json
{ "workflow_id": "document_review" }
```

**Response 200 (abbreviated)** — one entry per upload role:
```json
{
  "uploads": {
    "review-input": [
      { "upload_id": "upl-...", "name": "freight-invoice.txt", "role": "review-input", "…": "…" }
    ],
    "governing-rules": [
      { "upload_id": "upl-...", "name": "freight-policy.txt", "role": "governing-rules", "…": "…" }
    ]
  }
}
```

---

## `GET /api/connections?workflow_id=`

Registered connected applications (local stubs today — see the main
[README](../../README.md#registered-applications)) available for a workflow.

---

## `DELETE /api/uploads/{upload_id}`

Removes an unused upload. `200 { "removed": true }` or `404` if unknown.

---

## `POST /api/runs/analyze`

Validates the supplied inputs/uploads against the workflow schema and compiles a real
execution plan (route decisions, operation list, protection checks) **before** anything
runs.

**Request**
```json
{
  "workflow_id": "document_review",
  "input_source": "sample",
  "uploads": {
    "review-input": ["upl-..."],
    "governing-rules": ["upl-..."]
  },
  "inputs": { "review-focus": "Unsupported charges and missing approvals" },
  "desired_outcome": "",
  "requirements": {
    "maximum_cost_usd": 1.0,
    "required_quality_score": 0.9,
    "allowed_routes": ["software", "retrieval", "reuse", "efficient_ai", "advanced_ai"]
  }
}
```

**Response 200 (abbreviated)**
```json
{
  "plan_id": "plan-a2e6e62519",
  "workflow_id": "document_review",
  "operation_count": 8,
  "operations": [
    {
      "operation_id": "op-01",
      "order": 1,
      "label": "Extract text from every uploaded document",
      "route": "software",
      "intended_route": "software",
      "reason": "Text extraction is deterministic"
    }
  ]
}
```

**Errors** — `400` with a field-level validation payload when a required input is
missing:
```json
{ "detail": { "errors": [ { "field": "review-focus", "message": "Describe what should be checked." } ] } }
```

---

## `POST /api/runs`

Starts an approved run. Idempotency key honoured — POSTing the same `idempotency_key`
twice returns the same `run_id` rather than starting a second run.

**Request**
```json
{ "plan_id": "plan-a2e6e62519", "idempotency_key": null }
```

**Response 200**
```json
{ "run_id": "run-476a0e362c", "status": "created", "created": true }
```

---

## `GET /api/runs/{run_id}/events`

Server-Sent Events stream of the run's seven-phase execution, with `Last-Event-ID`
replay support so a dropped connection can resume without missing or duplicating events.
`Content-Type: text/event-stream`.

Event names follow the phase/operation lifecycle (`phase.started`, `operation.completed`,
`run.completed`, etc.) — see `runner.py`'s `build_proof`/event emission for the exact set.
A run will wait briefly (`TOKENOS_STREAM_ATTACH_TIMEOUT_SECONDS`, default `3.0`) for the
browser to attach before phases begin, so the UI never misses phase 1.

---

## `GET /api/runs/{run_id}`

Authoritative run state — status, current phase, operations executed so far — for
recovery after a dropped SSE connection, or for polling in tests.

**Response 200 (abbreviated)**
```json
{
  "run_id": "run-476a0e362c",
  "plan_id": "plan-a2e6e62519",
  "workflow_id": "document_review",
  "status": "completed",
  "phase": "prove",
  "operations": [ "…" ],
  "metrics": {
    "operations_total": 8,
    "completed": 8,
    "without_generative_ai": 8,
    "model_calls": 0,
    "quality_state": "passed"
  }
}
```

`404` for an unknown `run_id`.

---

## `POST /api/runs/{run_id}/approve`

Records a human approval decision for a run gated on `human_approval_required`.

**Request** `{ "decision": "approved" }` (or `"rejected"`)

---

## `POST /api/runs/{run_id}/stop`

Stops new work safely — in-flight operations are allowed to finish, no new ones start.

---

## `GET /api/runs/{run_id}/proof`

The final measured proof. `409` until the run reaches a terminal state
(`GET /api/runs/{id}` will show `status` still `"running"`); `404` for an unknown run.

**Response 200 (real captured example, abbreviated — long arrays truncated)**
```json
{
  "run_id": "run-476a0e362c",
  "plan_id": "plan-a2e6e62519",
  "workflow_id": "document_review",
  "status": "completed",
  "created_at": "2026-09-04T17:50:17.350392-04:00",
  "finished_at": "2026-09-04T17:50:20.354053-04:00",
  "measurement": "measured_sample_run",
  "measurement_label": "Measured sample run",
  "outcome": {
    "successful": true,
    "quality_passed": true,
    "quality_score": 1.0,
    "required_quality_score": 0.9,
    "decision_complete": false,
    "unresolved_items": 1,
    "quality_label": "Deterministic checks passed. Final decision incomplete.",
    "headline": "Known findings resolved locally. 1 material ambiguity requires AI or human review."
  },
  "usage": {
    "model_calls": 0,
    "input_tokens": 0,
    "output_tokens": 0,
    "duration_ms": 3001,
    "deployments": [],
    "model_mode": "local"
  },
  "economics": {
    "calculated_model_cost_usd": 0.0,
    "tool_cost_usd": 0.0,
    "total_calculated_cost_usd": 0.0,
    "authorized_model_cost_usd": 1.0,
    "price_configured": false,
    "actual_cost_status": "No model spend — all work completed locally",
    "comparator_status": "Projection, not measured spend",
    "difference_status": "Projected, not a verified saving",
    "verified_saving_status": "Requires a paired all-AI run with an equal-quality outcome",
    "token_source": "no model call was made"
  },
  "routing": {
    "operations": 8,
    "completed_without_generative_ai": 8,
    "efficient_ai": 0,
    "advanced_ai": 0
  },
  "verification": [ "…" ],
  "facts": [ "…" ],
  "findings": [ "…" ],
  "reviewed_items": [ "…" ],
  "tokenomics": { "…": "the projected-comparator block described in the README" }
}
```

Notes on truthfulness invariants visible in this shape:

- `outcome.quality_passed` can be `true` while `outcome.decision_complete` is `false` —
  every *known* rule passed, but a genuinely ambiguous item is still unresolved (no model
  configured in this example). The headline reflects exactly that, never "Same review
  decision" language, until a baseline actually proves it.
- `routing.operations` (not `operations_total`) is the field name read by both the ledger
  and the UI. `routing.completed_without_generative_ai + routing.efficient_ai +
  routing.advanced_ai` always equals `routing.operations`.
- `usage.model_calls` and `economics.calculated_model_cost_usd` are `0` here because no
  model call occurred — never a fabricated non-zero number.

---

## `POST /api/runs/{run_id}/baseline`

Executes the all-AI comparison path against the **same** inputs and quality gates as the
governed run, then verifies it the same way. This is the only endpoint that can spend real
model tokens, so it requires explicit cost acknowledgement in the request body.

**Request**
```json
{ "acknowledged": true }
```

**Response 400** — missing or `false` acknowledgement (no model call is made):
```json
{ "detail": "The baseline invokes a real model call and may incur cost. Send {\"acknowledged\": true} to run it." }
```

**Response 200 — no Foundry deployment configured (real captured example)**
```json
{
  "available": false,
  "status": "unavailable",
  "reason": "A paired baseline needs a model deployment. Set TOKENOS_MODEL_MODE=foundry and the deployment variables, then run the comparison to turn the projection into a verified saving.",
  "saving_claimable": false,
  "governed": {
    "cost_usd": 0.0,
    "quality_passed": true,
    "findings": 4,
    "model_calls": 0,
    "tokens": 0
  },
  "baseline": null
}
```

**Response 200 — baseline ran against a real Foundry deployment (shape)**
```json
{
  "available": true,
  "status": "eligible_saving",
  "reason": null,
  "saving_claimable": true,
  "saving_usd": 0.0058,
  "governed": { "cost_usd": 0.0001, "quality_passed": true, "findings": 4, "model_calls": 1, "tokens": 620 },
  "baseline": {
    "cost_usd": 0.0059,
    "quality_passed": true,
    "model_calls": 8,
    "input_tokens": 5400,
    "output_tokens": 1527,
    "cached_input_tokens": 0,
    "reasoning_tokens": 0
  },
  "equal_quality": true
}
```

`status` is one of the values in `tokenos_api/comparison.py`:

| `status` | Meaning |
| --- | --- |
| `not_requested` | No baseline has been run yet for this proof |
| `unavailable` | No model deployment is configured — cannot run a baseline at all |
| `baseline_failed` | The baseline call itself errored (network, auth, provider error) |
| `eligible_saving` | Both paths passed the same quality checks and the baseline cost more — **the only status where a saving may be shown** |
| `no_saving` | Both paths passed, but the baseline did not cost more than the governed run (equal or cheaper) — a *valid* comparison, just no saving |
| `invalid_comparison` | The comparison itself cannot be trusted (a quality gate failed on either path, the governed decision was incomplete, the contract/inputs didn't match, or the price table wasn't configured) |

`404` for an unknown `run_id`; `409` if the run has not produced a proof yet.

---

## `GET /api/runs/{run_id}/comparison`

Read-only fetch of whatever comparison has already been computed for this run. **Never**
executes a model call — safe to poll from the UI. Returns the same shape as
`POST /baseline`'s response, cached.

**Response 200 — before a baseline has ever been requested**
```json
{ "available": false, "status": "not_requested", "reason": "The measured all-AI comparison has not been run for this proof." }
```

**Response 200 — after `POST /baseline` has run** — identical to the cached result
returned by that call (see above).

`404` for an unknown `run_id`.

---

## `GET /api/runs`

Run history (in-memory, current process only).

```json
{ "runs": [ { "run_id": "run-476a0e362c", "workflow_id": "document_review", "status": "completed", "…": "…" } ] }
```

---

## `GET /api/reports/runs?limit=200`

Enterprise reporting view read from the **durable** SQLite ledger
(`tokenos_api/storage/ledger.py`), not the in-memory run store — so it survives a process
restart and is the source of truth for audit. Every row was written once, when its run's
proof (or later, its baseline) actually completed; nothing here is recalculated.

**Response 200 (real captured example, trimmed to 1 row)**
```json
{
  "summary": {
    "total_runs": 4,
    "total_model_calls": 0,
    "total_operations": 23,
    "total_without_generative_ai": 31,
    "total_measured_cost_usd": 0.0,
    "verified_savings_count": 0,
    "total_verified_saving_usd": 0.0
  },
  "runs": [
    {
      "run_id": "run-476a0e362c",
      "workflow_id": "document_review",
      "status": "completed",
      "measurement_label": "Measured sample run",
      "quality_passed": 1,
      "model_calls": 0,
      "operations_total": 8,
      "without_generative_ai": 8,
      "input_tokens": 0,
      "output_tokens": 0,
      "calculated_cost_usd": 0.0,
      "created_at": "2026-09-04T17:50:20.355343-04:00",
      "baseline_status": "unavailable",
      "saving_claimable": 0,
      "saving_usd": null,
      "equal_quality": 0
    }
  ]
}
```

`verified_savings_count`/`total_verified_saving_usd` in `summary` only ever count rows
whose `baseline_status` is `eligible_saving` — the same enum used by
`POST /baseline` and `GET /comparison`, so a "no saving" or "invalid comparison" baseline
can never inflate the reported saving total.

---

## `GET /api/foundry/config`

Reports the current model-mode configuration (never the credential itself).

```json
{
  "model_mode": "local",
  "foundry_base_url": "",
  "foundry_auth_mode": "entra",
  "efficient_deployment": null,
  "advanced_deployment": null,
  "configured": false
}
```

## `POST /api/foundry/config`

Updates the model-mode configuration for the running process (used by the in-app Foundry
config panel). Accepts `model_mode`, `foundry_base_url`, `foundry_auth_mode`,
`foundry_token_scope`, `efficient_deployment`, `advanced_deployment`. **Never accepts or
stores an API key from the browser** — Entra ID auth is resolved server-side via
`azure-identity`; an API-key auth mode (if enabled) still requires the key to be set as a
server-side environment variable, never sent in this request body.

## `POST /api/foundry/test`

Issues a minimal real call against the configured deployment to confirm connectivity
before relying on it, without running a full workflow.

---

## Error shape

Every error response is a standard FastAPI `HTTPException` body:
```json
{ "detail": "<human-readable message>" }
```
or, for request validation errors, FastAPI's field-level `{"detail": [...]}` array, or the
workflow-specific `{"detail": {"errors": [...]}}` shape shown under `/runs/analyze` above.

---

## What is never exposed here

- No provider API key or Entra credential is ever present in a response body.
- No endpoint accepts a client-supplied cost, token count, or quality score as truth — all
  of those are computed server-side from real execution, real provider `usage` fields, and
  the pinned `price_table.json`.
- `POST /api/runs/{run_id}/baseline` is the **only** endpoint capable of spending model
  tokens, and only when `acknowledged: true` is explicitly sent.
