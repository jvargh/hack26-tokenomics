# TokenOS engine deep dive

An engineer's guide to how TokenOS actually works: control flow, data structures, invariants,
and the reasoning behind the unusual parts. Written for someone who has to maintain or extend
the system, not for someone evaluating the product.

Companion documents, so you know when to read something else instead:

| Document | Answers |
| --- | --- |
| [`README.md`](./README.md) | What the product is, how to run it |
| [`WORKINGS.md`](./WORKINGS.md) | Product-level architecture narrative |
| [`services/tokenos-api/API.md`](./services/tokenos-api/API.md) | Classic endpoint reference |
| [`services/tokenos-api/OPTIMIZATION-API.md`](./services/tokenos-api/OPTIMIZATION-API.md) | Optimization endpoint reference |
| **This document** | *Why* the code is shaped the way it is, and where every rule lives |

Line numbers are accurate as of commit `7ed07ac`. They drift; the function names do not.

---

## Contents

1. [The single idea that shapes the codebase](#1-the-single-idea-that-shapes-the-codebase)
2. [Module topology](#2-module-topology)
3. [Two engines, one API](#3-two-engines-one-api)
4. [The run state machine](#4-the-run-state-machine)
5. [Phase by phase through the engine](#5-phase-by-phase-through-the-engine)
6. [The routing ladder](#6-the-routing-ladder)
7. [`_call_model`: the only code that spends money](#7-_call_model-the-only-code-that-spends-money)
8. [Cost, prices, and pinning](#8-cost-prices-and-pinning)
9. [The verification model](#9-the-verification-model)
10. [The proof object](#10-the-proof-object)
11. [The baseline and the savings gate](#11-the-baseline-and-the-savings-gate)
12. [Prompt mode](#12-prompt-mode)
13. [Ingestion and the trust boundary](#13-ingestion-and-the-trust-boundary)
14. [Storage, events, and SSE](#14-storage-events-and-sse)
15. [Frontend architecture](#15-frontend-architecture)
16. [Configuration reference](#16-configuration-reference)
17. [Test topology](#17-test-topology)
18. [Invariants that must not regress](#18-invariants-that-must-not-regress)
19. [Extension recipes](#19-extension-recipes)
20. [Sharp edges and known limits](#20-sharp-edges-and-known-limits)

---

## 1. The single idea that shapes the codebase

TokenOS claims it saves money on AI. That claim is trivially easy to fake, and almost every
unusual design decision in this repository is a defence against one specific way of faking it.

If you understand the table below, most of the code stops looking paranoid and starts looking
necessary.

| A plausible way to lie | Where the code stops it |
| --- | --- |
| Claim a saving without ever running the alternative | The baseline must actually execute; `comparable` requires `governed["completed"] and baseline["completed"]` — [`engine.py:1068`](./services/tokenos-api/tokenos_api/optimization/engine.py) |
| Be cheaper by doing less, or worse | Both sides must pass every quality gate, and produce the same number of outcomes — [`engine.py:1068-1072`](./services/tokenos-api/tokenos_api/optimization/engine.py) |
| Compare against a deliberately dumb baseline | Both sides must share a byte-identical contract: `governed["contract"] == baseline["contract"]` — [`engine.py:1070`](./services/tokenos-api/tokenos_api/optimization/engine.py) |
| Present an estimate as a measurement | Separate fields, separate `evidenceStatus`, separate UI tiers — `EvidenceTier` in [`Comparison.tsx`](./apps/web/src/components/shared/Comparison.tsx) |
| Invent token counts when the provider is vague | `strict_usage=True` rejects incomplete usage; every usage row must carry a `providerRequestId` — [`engine.py:1072`](./services/tokenos-api/tokenos_api/optimization/engine.py) |
| Let price changes make old runs look good | The price table is deep-copied and pinned per run, hashed into the contract, and re-checked — [`engine.py:50-61`](./services/tokenos-api/tokenos_api/optimization/engine.py) |
| Quietly feed different inputs to each side | `inputManifestHash` and `_sourceHash` are recomputed and compared at Protect — [`engine.py:503-506`](./services/tokenos-api/tokenos_api/optimization/engine.py) |
| Retry until something passes, bill once | `single_attempt=True`, and escalation is capped by `maxAdvancedCalls` — [`engine.py:828-831`](./services/tokenos-api/tokenos_api/optimization/engine.py) |
| Show the model the expected answer | Expected outputs live under `_`-prefixed keys, are stripped from provider payloads, and are recorded as `expectedOutputsSent: False` — [`engine.py:761`](./services/tokenos-api/tokenos_api/optimization/engine.py) |
| Report `$0.00` when a call failed mid-flight | The `interrupted` category explicitly says *do not infer a zero charge* — [`engine.py:867`](./services/tokenos-api/tokenos_api/optimization/engine.py) |

Two consequences worth internalising before you change anything:

- **The system fails closed.** Every ambiguous condition resolves to "no claim", never to an
  optimistic default. If you add a code path that returns a number, ask what it returns when
  the evidence is missing. The answer must not be `0`.
- **A cheaper wrong answer is not a saving.** Quality is a precondition of cost comparison, not
  a separate report. This is why verification and cost live in the same eligibility expression.

---

## 2. Module topology

```
tokenos/
├── apps/web/                          React 18 + Vite + TypeScript, no UI framework
│   └── src/
│       ├── App.tsx                    Shell, phase dispatch
│       ├── api/          client.ts    Classic API + SSE helper
│       │                 types.ts     Shared server-shape types
│       ├── optimization/              The 4th workflow, self-contained
│       │   ├── OptimizationJourney.tsx    Orchestrator, owns phase state + SSE
│       │   ├── OptimizationDescribe.tsx   Step 1 form, mode/source branching
│       │   ├── OptimizationViews.tsx      Plan/Optimize/Protect/Run/Verify/Prove views
│       │   └── client.ts                  Anti-corruption layer (see §15)
│       ├── phases/                    Classic workflow phase screens
│       ├── state/        runStore.ts  Reducer for classic runs
│       └── components/shared/         Claim-strength primitives
│
└── services/tokenos-api/
    └── tokenos_api/
        ├── app.py                     FastAPI assembly + classic routes
        ├── config.py                  All settings, all env vars
        ├── modeladapter.py            The ONLY code that talks to Foundry
        ├── pricing.py                 Price table load/save
        ├── runner.py                  Classic execution engine
        ├── baseline.py, comparison.py Classic baseline
        ├── connectors.py              Classic connected-app stubs
        ├── samples.py                 Classic sample data
        └── optimization/              The 4th workflow's engine
            ├── engine.py     (75 KB)  Lifecycle, routing, execution, proof, baseline
            ├── imports.py    (27 KB)  Ingestion, registry, validation, hashing
            ├── prompts.py    (29 KB)  Prompt compilation pipeline
            ├── quality.py    (15 KB)  Verifiers, gates, local adapters
            ├── fixtures.py            Bundled reproducible examples
            ├── router.py              Optimization HTTP routes
            ├── schemas.py             Pydantic request contracts
            └── store.py               SQLite persistence + events
```

**Import direction is strictly one-way**: `router → engine → {imports, prompts, quality, store}`.
Nothing under `optimization/` imports from `runner.py` or `baseline.py`, and nothing in the
classic engine imports from `optimization/`. `app.py` is the only place both meet.

---

## 3. Two engines, one API

This is the first thing that confuses people, so it is worth being blunt: **there are two
independent execution engines in this repository, and both are live.**

| | Classic engine | Optimization engine |
| --- | --- | --- |
| Entry | [`runner.execute_run()`](./services/tokenos-api/tokenos_api/runner.py) | [`engine.describe()`](./services/tokenos-api/tokenos_api/optimization/engine.py) → … |
| Workflows | `document_review`, `software_validation`, `deadline_processing` | `workflow_optimization` |
| Storage | classic run store | `optimization.sqlite3` |
| Baseline | [`baseline.py`](./services/tokenos-api/tokenos_api/baseline.py) + [`comparison.py`](./services/tokenos-api/tokenos_api/comparison.py) | `engine.comparison()` |
| Frontend | `phases/*` + `state/runStore.ts` | `optimization/*` |

The fork happens in `POST /api/runs` at [`app.py:335`](./services/tokenos-api/tokenos_api/app.py):
if `workflow == "workflow_optimization"` the request is delegated to the optimization engine,
otherwise it runs the classic path. `GET /api/runs/{id}`, the SSE endpoint, and the history and
delete endpoints all check the optimization store first and fall back to the classic store.

**Why two engines?** The classic engine executes a *fixed, known* workflow the product ships.
The optimization engine executes *user-supplied* work under a contract that must be provable
after the fact. The second problem needs pinning, hashing, reservations and a matched baseline;
forcing that machinery onto the first would have made three simple workflows much harder to read.

When extending, pick a side deliberately. Cross-engine helpers are the main way this codebase
could rot.

---

## 4. The run state machine

Two orthogonal concepts, easy to conflate:

- **`status`** — what the run is *allowed to do next*. Enforced by `_require_status()`.
- **`phase`** — what the UI *shows*. Emitted as events, never used for authorization.

```
                    ┌──────────────────────────────────────────────┐
                    │                                              │
  describe()        │  analyze()       optimize()     authorize()  │  execute()
      │             │      │               │              │        │      │
      ▼             │      ▼               ▼              ▼        │      ▼
 ┌──────────┐       │ ┌─────────┐    ┌───────────┐   ┌──────────┐  │ ┌─────────┐
 │ described│───────┴▶│ planned │───▶│ optimized │──▶│authorized│──┴▶│ running │
 └──────────┘         └─────────┘    └───────────┘   └──────────┘    └─────────┘
                                          ▲                               │
                                          │ refresh_safeguards()          │
                                          └───────────────────────────┐   ▼
                                                              ┌───────────────────┐
                                                              │completed / failed │
                                                              └───────────────────┘
                                                                        │
                                                          start_baseline() (explicit)
                                                                        ▼
                                                              baseline: running → completed
```

| Status | Set at | Gate to leave it |
| --- | --- | --- |
| `described` | [`engine.py:207`](./services/tokenos-api/tokenos_api/optimization/engine.py) | `analyze()` requires exactly this |
| `planned` | [`engine.py:384`](./services/tokenos-api/tokenos_api/optimization/engine.py), `:423` | `optimize()` requires exactly this |
| `optimized` | [`engine.py:594`](./services/tokenos-api/tokenos_api/optimization/engine.py) | `authorize()` requires exactly this |
| `authorized` | [`engine.py:669`](./services/tokenos-api/tokenos_api/optimization/engine.py) | `execute()` requires exactly this |
| `running` | [`engine.py:696`](./services/tokenos-api/tokenos_api/optimization/engine.py) | terminal transition inside `_execute()` |
| `completed` / `failed` | [`engine.py:1026`](./services/tokenos-api/tokenos_api/optimization/engine.py) (analyze), [`:1038`](./services/tokenos-api/tokenos_api/optimization/engine.py) (measure) | only `start_baseline()` accepts `completed` |

`_require_status()` ([`engine.py:45-47`](./services/tokenos-api/tokenos_api/optimization/engine.py))
raises `409` with both the required and the current status. This is a deliberate design choice:
the frontend uses the 409 as a *navigation signal* rather than tracking server state itself
(see §15).

Note the asymmetry at the end: analyze runs always reach `completed` because they cannot fail a
gate they never ran, while measure runs become `completed` only when
`result["qualityPassed"]` — a run that executed cleanly but failed verification is `failed`,
not a `completed` run with a bad score.

Phases are `describe → plan → optimize → protect → run → verify → prove`. `_phase()` sets
`run["phase"]` and emits `phase.started`; `_completed_phase()` emits `phase.completed`.
Note that `optimize()` emits phase `optimize` but `analyze()` emits phase `plan` — status names
and phase names deliberately do not line up one-to-one.

### Single-execution claims

`store.claim(run_id, kind)` inserts into `optimization_claims` with a composite primary key.
A duplicate insert raises `IntegrityError`, converted to a `409` reading *"A {kind} is already
active or was already executed. Create a new versioned run."*
([`store.py:95-101`](./services/tokenos-api/tokenos_api/optimization/store.py)).

This is what stops a run being executed or baselined twice — for example by a double-click, or
by a retried request. It is a database constraint rather than an in-memory flag because the
API is expected to survive a restart mid-run.

---

## 5. Phase by phase through the engine

### Describe — `describe()` [`engine.py:207`](./services/tokenos-api/tokenos_api/optimization/engine.py)

Validates the request through `DescribeRequest`, materialises inputs, computes
`inputManifest` + `inputManifestHash`, and persists a run at status `described`.

The interesting logic is in the schema, not the engine.
`DescribeRequest.derive_mode_and_target` ([`schemas.py:124-145`](./services/tokenos-api/tokenos_api/optimization/schemas.py))
resolves the `mode`/`optimizationTarget` pair:

| `optimizationTarget` | `mode` | UI card |
| --- | --- | --- |
| `current_workflow` | `analyze` | Analyze current workflow |
| `single_prompt` | `measure` | Optimize a prompt before you run it |
| `measured_workflow` | `measure` | Measure an optimized workflow |

Either may be omitted and is derived from the other; supplying both with a mismatch raises
`optimizationTarget and mode do not agree.` Omitting both defaults to
`measured_workflow`/`measure`.

`validate_target_inputs` then enforces that the two families never mix: a `single_prompt` run
rejects telemetry and representative workflow requests, and a workflow run rejects
`userPrompt`, `systemInstructions`, `conversationHistory`, `contextFileIds` and
`promptExampleId`. This is what keeps prompt mode genuinely inside the fourth workflow rather
than being a fourth-and-a-half workflow with shared, ambiguous state.

### Plan — `analyze()` [`engine.py:394`](./services/tokenos-api/tokenos_api/optimization/engine.py)

Prompt runs divert immediately to `_analyze_prompt()` (§12). For workflow runs:

1. Deep-copy and pin the price table; derive `priceTableVersion`. An unusable table is a `422`.
2. `_current_route()` builds the "before" picture from uploaded telemetry.
3. For each representative request, **speculatively run the local adapter**:

```python
try:
    output, evidence = local_result(item)
except (ValueError, TypeError, SyntaxError, ArithmeticError):
    output, evidence = None, {"reason": "The allowlisted local adapter rejected this input.", "inputError": True}
```

The resulting operation records `route: "local" if output is not None else "tokenos-efficient"`
and `evidenceStatus: "Zero model tokens"` or `"Estimated until execution"`.

This is a **dry run that spends nothing**. The output is discarded — only the *decision* is
kept. `local_result` runs again for real during execution. Doing the work twice is intentional:
the plan must be honest about what will happen before anyone authorizes spending, and the
execution must not trust a stale plan.

`_current_route()` labels the current cost `"Measured current cost"` only when every telemetry
row is fully priced; otherwise `"Current cost unavailable"`. It never interpolates a missing price.

### Optimize — `optimize()` [`engine.py:556`](./services/tokenos-api/tokenos_api/optimization/engine.py)

Does **not** re-decide routes. It reads the decisions `analyze()` made and produces:

- **`levers`** — seven named optimization levers, each with a status of `applicable`,
  `estimated` or `not_applicable`. These are explanatory, not executable. Note
  `batch_eligibility` is forced to `not_applicable` when a `latency_target` gate is present,
  and its detail states that no batch price is claimed without an executed provider batch.
- **`protectionChecks`** — via `_checks()`, the safeguard list rendered on Protect.
- **`candidateRoute`** — allowed deployment aliases, spend ceiling, and the maximum reservation.

### Protect — `_checks()` [`engine.py:486`](./services/tokenos-api/tokenos_api/optimization/engine.py)

Ten safeguards. Every one must pass before money can be spent.

| Check | Fails when |
| --- | --- |
| `manifest` | Inputs changed since planning (`_sourceHash` or `inputManifestHash` moved) |
| `quality` | `gate_blockers()` returned anything (see §9) |
| `local_adapters` | A local adapter rejected an input |
| `data_policy` | `dataHandling == "block"`, or `approval_required` without approval |
| `human_approval` | The `human_approval` gate was requested but not granted |
| `scope` | Registered application missing, wrong tenant, or lacking the needed scope |
| `input_tokens` | *(prompt only)* estimated governed input exceeds `maxInputTokens` |
| `provider` | Model operations exist but Foundry is unavailable |
| `prices_context` | A reservation could not be computed from the pinned table |
| `budget` | Total conservative reservation exceeds `maxModelSpendUsd` |
| `price_version` | The administrator changed prices since planning |

The budget check is deliberately pessimistic: it reserves every planned efficient call **plus**
the `maxAdvancedCalls` most expensive possible escalations
([`engine.py:539-543`](./services/tokenos-api/tokenos_api/optimization/engine.py)). A run that
could conceivably exceed the ceiling is refused, not started and aborted midway.

`_checks()` also writes `run["_maximumReservationUsd"]` as a side effect — worth knowing
before you refactor it into something pure.

### Authorize — `authorize()` [`engine.py:643`](./services/tokenos-api/tokenos_api/optimization/engine.py)

```python
checks = _checks(run, human_approved=payload.humanApprovalGranted)
if any(not check["passed"] for check in checks):
    raise HTTPException(409, {"message": "Protect blocked the run...", "protectionChecks": checks})
```

Records `_authorization`: `authorizeModelCost`, `humanApprovalGranted`, `authorizedAt`,
`tenant`, `contractHash`. The 409 body carries the failed checks so the UI can render exactly
what blocked the run.

`authorizeModelCost` must be truthful. Analyze-mode runs pass `false` because they *cannot*
invoke a model at all, and `_call_model` refuses to proceed without it
([`engine.py:713-714`](./services/tokenos-api/tokenos_api/optimization/engine.py)). Do not
"simplify" this to always-true to make a flow smoother; it is the record of what a human agreed to.

`_contract()` ([`engine.py:629`](./services/tokenos-api/tokenos_api/optimization/engine.py))
freezes what both the governed run and any future baseline must match: input manifest hash,
source hash, output contract, max output tokens and characters, quality requirements,
verifier version, price table version and hash.

### Run / Verify / Prove — `_execute()` [`engine.py:986`](./services/tokenos-api/tokenos_api/optimization/engine.py)

```
_phase("run")
  ├─ mode == "analyze" → no model replay at all; proof is built from analysis only
  └─ mode == "measure" → _route() actually executes
_phase("verify")   aggregate gate results
_phase("prove")    _proof()
status = completed | failed
```

Analyze mode short-circuits because it has nothing to execute — it inspects existing telemetry
and recommends. Its proof carries a *projection*, clearly labelled, and never a measured cost.

---

## 6. The routing ladder

Four rungs, cheapest first. The decision is made per request in `_route()`
([`engine.py:805-820`](./services/tokenos-api/tokenos_api/optimization/engine.py)).

```
1. reuse              ── an identical, still-fresh request already succeeded in this run
2. local              ── a deterministic rule proves the answer; zero tokens
3. tokenos-efficient  ── bounded model call
4. tokenos-advanced   ── only after efficient FAILED VERIFICATION, and only if authorized
```

Plus `tokenos-baseline`, which is not a rung — it is the comparison path, used only by the
explicitly triggered all-AI baseline.

### Reuse

`_reuse_key()` ([`engine.py:702`](./services/tokenos-api/tokenos_api/optimization/engine.py))
hashes tenant, application, scope, freshness version, normalized input, task type, context,
expected output **and the execution contract**. A cache hit therefore cannot survive a contract
change, a tenant change, or a freshness bump. Reuse is also recorded only after the original
passed verification (`if passed and key and not baseline`), so a failed answer is never reused.

Reuse is skipped entirely for prompt-mode requests unless the task is a `lookup`.

### Local

`local_result()` ([`quality.py:106`](./services/tokenos-api/tokenos_api/optimization/quality.py))
handles four task types and refuses anything ambiguous:

- `lookup` — exactly one context source whose `key` matches case-insensitively.
- `classification` — exactly one source with a matching `terms` entry. **Zero or several
  matches deliberately fall through to a model**: `"Zero or multiple labels match; interpretation is required."`
- `policy` — registered freight rules, matched against exact policy text.
- `code_validation` — allowlisted arithmetic only.

`run_arithmetic_tests()` ([`quality.py:62`](./services/tokenos-api/tokenos_api/optimization/quality.py))
deserves attention because it is the one place user input is *evaluated*. It parses with
`ast.parse(mode="eval")` and then walks the tree with an explicit allowlist of `Add, Sub, Mult,
Div, FloorDiv, Mod` plus unary `+`/`-`. Calls, attributes and names outside the supplied args
raise. It bounds expression length (1000 chars), AST node count (100), test count (1–30), and
every intermediate value (finite, `abs ≤ 1e15`). There is no `eval()` anywhere in the path.

### Escalation

```python
if not passed and not baseline and operation["route"] == "tokenos-efficient":
    eligible = (run["requirements"]["allowAdvancedEscalation"]
                and advanced_calls < run["requirements"]["maxAdvancedCalls"])
```

Three properties worth preserving:

1. **Escalation is a response to failed verification, never a prediction.** The efficient call
   happens first and is measured; only a real gate failure triggers the advanced attempt.
2. **The baseline never escalates** (`not baseline`). The baseline is a fixed profile, so it
   cannot quietly acquire extra attempts the governed side did not get.
3. **The decision is recorded either way** — `approved_after_failed_verification` or
   `not_authorized_or_limit_reached`, then `advanced_verification_passed`/`_failed` — and
   emitted as an `escalation.decision` event.

---

## 7. `_call_model`: the only code that spends money

[`engine.py:712-783`](./services/tokenos-api/tokenos_api/optimization/engine.py). Every model
call in the optimization engine passes through here. Read it before changing anything nearby.

Guards **before** the call:

```python
_validate_contract(run)                              # 403 if contract/tenant/scope moved
if not baseline and not run["_authorization"]["authorizeModelCost"]:
    raise HTTPException(403, "Protect did not authorize model cost.")
if baseline and not run.get("_baselineAuthorization"):
    raise HTTPException(403, "The paired baseline has no explicit model-cost acknowledgement.")
if run.get("_application"):                          # 403 unless model_execution scope granted
    ...
if not model_available():
    raise ModelUnavailable("Foundry is unavailable.")
...
if measured + reservation > Decimal(str(run["requirements"]["maxModelSpendUsd"])):
    raise ValueError("The per-call reservation exceeds the remaining authorized budget.")
```

Then a `budget.reserved` event is emitted, `usageComplete` is set **false**, and the run is
saved — so a crash mid-call leaves visible evidence of an unreconciled call rather than a
silent gap.

The call itself always sets `strict_usage=True, single_attempt=True, json_response=True,
temperature=0`.

Guards **after** the call:

| Check | Failure meaning |
| --- | --- |
| All four token counts are non-negative `int`, and `reasoning ≤ output` | Provider usage is malformed → no measured cost |
| `measured + cost > maxModelSpendUsd` or `cost > reservation` | Actual exceeded authorization → further calls blocked |
| `output_tokens > maxOutputTokens` | Provider ignored the pinned bound |
| `not provider.request_id` | No provider identity → evidence insufficient for comparison |

Note the ordering: the usage row is appended and the `model.usage` and `budget.reconciled`
events are emitted **before** the ceiling check raises. Money that was genuinely spent is always
recorded, even on the call that trips the limit. This is the difference between an honest
overspend report and a missing one.

Finally:

```python
# Always parse the actual response. Do not trust an adapter's independent parsed field.
return json.loads(provider.content, parse_constant=... raise ...)
```

`parse_constant` rejects `NaN`/`Infinity`, which would otherwise survive into JSON output and
break both the schema check and the durable store (`json.dumps(..., allow_nan=False)`).

The recorded `minimalEvidence` block asserts `expectedOutputsSent: False` and hashes the exact
payload (`inputHash`, `inputCharacters`) so the claim is checkable rather than aspirational.

### The adapter

[`modeladapter.py`](./services/tokenos-api/tokenos_api/modeladapter.py) is the only module that
imports `openai`. Credentials come from either `AZURE_INFERENCE_CREDENTIAL` (api-key mode) or
`DefaultAzureCredential` + `get_bearer_token_provider` (entra mode, the default). Both are
server-side. `GET /api/foundry/config` returns `has_api_key: bool(...)` — a boolean, never the
key.

- `single_attempt=True` → `client.with_options(max_retries=0)` and a single pass. Retries would
  multiply cost invisibly and break the reservation model.
- `strict_usage=True` → missing or malformed `prompt_tokens`/`completion_tokens` raises
  `ModelUnavailable` instead of returning a result with guessed usage.

---

## 8. Cost, prices, and pinning

`cost_for_usage()` [`engine.py:95`](./services/tokenos-api/tokenos_api/optimization/engine.py)
works entirely in `Decimal`:

```
((input_tokens - cached_tokens) * input_rate
 + cached_tokens * cached_rate
 + output_tokens * output_rate) / 1_000_000
```

Rules it enforces:

- Rates must be finite and non-negative; a missing deployment raises.
- `cached_tokens > input_tokens` raises.
- **Cached tokens reported without a configured `cached_input_per_1m_usd` raises.** It does not
  silently price them at the full input rate — that would understate or overstate a number the
  product specifically advertises.

`float` appears only at the API boundary; `costUsdExact` carries the `Decimal` as a string, and
the savings comparison sums `Decimal(usage["costUsdExact"])`, never the floats.

### Pinning

`_price_version()` returns `"{version}:{digest(table)[:20]}"` — a declared version *and* a
content hash, so an edit that forgets to bump the version still changes the identity. The table
is deep-copied into `run["_priceTable"]` at plan time, `priceTableHash` goes into the contract,
and `_prices_unchanged()` re-checks it at Protect. A price edit mid-run invalidates the run
rather than silently re-pricing it.

Two price surfaces exist, which is a genuine wart:
[`pricing.py`](./services/tokenos-api/tokenos_api/pricing.py) (`calculate_cost_usd`, used by the
classic engine, returns `(0.0, False)` for unknown deployments and rounds to 6 dp) and
`cost_for_usage` in the optimization engine (raises instead). The optimization engine never
calls `calculate_cost_usd`. Do not unify them without deciding which failure mode you want.

---

## 9. The verification model

All in [`quality.py`](./services/tokenos-api/tokenos_api/optimization/quality.py).
`VERIFIER_VERSION = "optimization-verifier-v1"` is stamped into every check and into the
contract, so results from different verifier versions can never be compared.

Six supported gates: `same_answer_quality`, `grounded_citations`, `structured_output`,
`required_tests`, `latency_target`, `human_approval`.

### Two-stage design

**`gate_blockers()` — before execution** ([`quality.py:159`](./services/tokenos-api/tokenos_api/optimization/quality.py)).
Refuses to start a run whose gates could never be evaluated: unsupported criteria, unsupported
schema constructs, missing `expectedOutput`, an `expectedOutput` that violates the contract or
exceeds the length bound, `required_tests` on a prompt, citations required with no context.

The newest blocker prevents an entire class of waste: an `expectedResult` that is free prose
appearing nowhere in approved context can never be exact-matched, so the run is refused rather
than paid for.

```python
if any(item.get("_expectedResult") and not expected_result_is_verifiable(item) for item in requests):
    blockers.append("inputs.expectedResult is free prose that no model can be expected to "
                    "reproduce word for word, ...")
```

`expected_result_is_verifiable()` accepts a short decision value (≤ 6 words, ≤ 64 chars, single
line) **or** any string that appears verbatim in the approved context — the two cases where a
model can actually produce the value.

**`verify_output()` — after execution** ([`quality.py:198`](./services/tokenos-api/tokenos_api/optimization/quality.py)).
Always adds `output_contract` and `output_length`, then `outcome_acceptance`, then one check per
requested gate. Acceptance is exact equality:

```python
if item.get("promptMode"):
    accepted = (... isinstance(output, dict)
                and (output.get("decision") == expected_result or output.get("response") == expected_result))
else:
    accepted = isinstance(output, dict) and bool(expected) and all(
        key in output and output[key] == value for key, value in (expected or {}).items())
```

There is deliberately **no fuzzy matching and no LLM judge**. A model grading a model would make
the savings claim unfalsifiable, which is the one thing this product cannot afford. The cost of
that choice is that gradeable outcomes must be discrete — which is why a prompt carrying an
`expectedResult` gets a `decision` field added to its output contract
([`prompts.py:89`](./services/tokenos-api/tokenos_api/optimization/prompts.py), `require_decision`),
letting prose stay prose in `response` while the graded value stays checkable.

`schema_supported()` restricts the contract to a small JSON-Schema subset
(`type, required, properties, additionalProperties, items, enum, maxLength`). Anything richer is
rejected up front rather than half-enforced.

---

## 10. The proof object

`_proof()` [`engine.py:891`](./services/tokenos-api/tokenos_api/optimization/engine.py) builds
the durable evidence record. Top level:

`runId`, `workflow`, `mode`, `inputManifestHash`, `inputManifest`, `telemetryCompleteness`,
`currentRoute`, `candidateRoute`, `operations`, `qualityGates`, `modelUsage`,
`priceTableVersion`, `executionContract`, `priceTable`, `verification`, `outcomes`, `cost`,
`baseline`, `badges`, `dimensions`, `metrics`, `error`, and `prompt` for prompt runs.

Blocks worth knowing:

- **`cost`** — `modelSpendUsd`, `knownModelSpendUsd`, `modelSpendUsdExact`, `modelCalls`,
  `localOperations`, `reuseOperations`, `efficientCalls`, `advancedCalls`, `acceptedOutcomes`,
  `costPerAcceptedOutcomeUsd`, `projection`, `nonModelCostsIncluded`.
  `costPerAcceptedOutcomeUsd` is the headline metric: it cannot be gamed by producing cheap
  rejected answers.
- **`verification`** — `passed`, `requirementsChecked`, `exceptions`, `processed`, `total`,
  `accepted`, `verifierVersion`.
- **`metrics`** — `localOperationRate`, `qualityPassRate`, `escalationRate`,
  `measuredCachedTokenRate`, `cacheEligibility`, `correctedOutcomeRate`, `modelCallsAvoided`.
- **`dimensions`** — `_dimensions()` [`engine.py:881`](./services/tokenos-api/tokenos_api/optimization/engine.py)
  tags every run for reporting: application, environment, `inputSource`, `optimizationTarget`,
  `promptRun`, `proofType` (`"sample"` vs `"measured"`), owner, cost centre, price table version.
- **`cost.projection`** — only present when `recurringVolume` was supplied *and* a per-outcome
  cost is known. It carries its own `label`, `badge` and `assumption` string so a projection can
  never be rendered as a measurement by accident.

Aggregation is over **every** model call, not the first:

```python
"measuredUsage": {... sum over all calls ...},
"modelCalls": len(usage_rows),
"deploymentAliases": [...],
"providerRequestIds": [...],
```

(An earlier version reported only `modelUsage[0]`, which under-reported any escalated run.
`test_escalated_prompt_reports_every_call_not_just_the_first` in
[`test_prompt_api.py`](./services/tokenos-api/tests/test_prompt_api.py) locks this down.)

---

## 11. The baseline and the savings gate

The most important 20 lines in the repository.

### Starting a baseline — `start_baseline()` [`engine.py:1046`](./services/tokenos-api/tokenos_api/optimization/engine.py)

Preconditions, all mandatory:

1. `status == "completed"`.
2. `mode == "measure"` **and** the governed verification passed. A failed run cannot be
   compared — *"Only a completed, verified governed outcome can authorize a matched baseline."*
3. `_validate_contract()` still holds.
4. `_checks(run, baseline=True)` all pass.
5. `store.claim(run_id, "baseline")` succeeds — one baseline per run, ever.

It is never automatic. The user explicitly asks for it, because it costs real money.

### The gate — `comparison()` [`engine.py:1067`](./services/tokenos-api/tokenos_api/optimization/engine.py)

```python
comparable = (governed["completed"] and baseline["completed"] and governed["qualityPassed"]
              and baseline["qualityPassed"] and governed["usageComplete"] and baseline["usageComplete"]
              and governed["contract"] == baseline["contract"] and bool(baseline["modelUsage"])
              and len(baseline["outcomes"]) == len(governed["outcomes"])
              and all(usage.get("providerRequestId") for usage in baseline["modelUsage"] + governed["modelUsage"]))

eligible = comparable and baseline_cost > governed_cost
```

Nine conditions, then a strict cost inequality. Read them as a list of the ways a comparison
could be dishonest:

| Condition | Prevents |
| --- | --- |
| both `completed` | Claiming against a run that crashed |
| both `qualityPassed` | Winning by being worse |
| both `usageComplete` | Costing a run with partial usage evidence |
| identical `contract` | Comparing different tasks, bounds, gates, verifiers or prices |
| baseline has `modelUsage` | An "all-AI" baseline that never called AI |
| equal outcome counts | Winning by answering fewer requests |
| every usage has `providerRequestId` | Unattributable, unverifiable calls |
| `baseline_cost > governed_cost` | Reporting a negative saving as a saving |

Three resulting labels, and only one is a claim:

- `"Verified saving"` — eligible.
- `"No cost saving verified"` — comparable, but governed was not cheaper. **The honest loss.**
- `"No valid comparison"` — not comparable at all.

`verifiedSavingUsd` and `verifiedSavingPercent` are `None` unless eligible. There is no code
path that populates them otherwise.

`_baseline()` additionally records `measuredInputTokenReduction` for prompt runs — but only when
both sides have complete usage.

---

## 12. Prompt mode

`optimizationTarget: "single_prompt"`. The pipeline lives in
[`prompts.py`](./services/tokenos-api/tokenos_api/optimization/prompts.py) and produces a
compiled plan consumed by the same engine as workflow runs.

`build_prompt_plan(inputs, requirements, artifacts)` → `{plan, request, baselinePackage, proofPrompt}`

```
raw prompt + system + history + artifacts
        │
        ├── estimate_tokens()      deterministic; docstring literally says ESTIMATE
        ├── decide_context()       per artifact: allow | minimize | redact
        ├── output_contract()      +decision field when an expectedResult is graded
        ├── governed_system_prompt()  treats all user/context text as untrusted DATA
        ├── cache_eligibility()    "eligible" only describes a stable prefix, never a saving
        ├── route_alias()          tokenos-efficient | tokenos-advanced
        └── lookup_candidate()     can this be answered with NO model at all?
```

Points that matter when modifying it:

- **`decide_context()` uses light deterministic stemming.** The comment at
  [`prompts.py:272`](./services/tokenos-api/tokenos_api/optimization/prompts.py) explains why:
  raw bag-of-words overlap treated *"return window"* and *"Returns are accepted within 30 days."*
  as unrelated and minimized away the excerpt the answer depended on. Both sides are stemmed
  identically, so unrelated excerpts gain no overlap.
- **`lookup_candidate()` requires exactly one keyed match** and returns an explicit reason
  otherwise (`"Multiple keyed context sources match... deterministic lookup is not safe."`).
  This is how a prompt run reaches zero model calls.
- **Two contract call sites must stay in sync** — `build_prompt_plan` ([`prompts.py:408`](./services/tokenos-api/tokenos_api/optimization/prompts.py))
  and `provider_payload_for_prompt` ([`prompts.py:528`](./services/tokenos-api/tokenos_api/optimization/prompts.py))
  both derive the contract with the same `require_decision` flag. If they diverge, the model is
  instructed under one contract and graded under another.
- **The baseline package is built at plan time**, capturing the *original* prompt with full
  history and all policy-clean context. That is what `all_ai_v1` replays, so the comparison is
  against the user's real starting point.
- **`_`-prefixed request keys never leave the server**: `_expectedResult`, `_outputFormat`,
  `_governedSystemPrompt`. See §14 for the mechanism.

---

## 13. Ingestion and the trust boundary

[`imports.py`](./services/tokenos-api/tokenos_api/optimization/imports.py). Treat every input as
hostile.

### `parse_export()` [`imports.py:40`](./services/tokenos-api/tokenos_api/optimization/imports.py)

Accepts JSON, JSONL, CSV, ZIP for both roles, plus TXT/MD for representative inputs.
ZIP handling is the hardened part — each member is rejected if it is absolute, contains `..`, has
a drive letter or NUL, is encrypted, is a symlink, is itself a `.zip`, or is oversized. Expanded
totals are bounded before extraction, so a zip bomb fails on inspection.

### `normalize_requests()` [`imports.py:104`](./services/tokenos-api/tokenos_api/optimization/imports.py)

3–20 requests, unique IDs ≤ 120 chars, task type from a fixed set, context sources requiring
string `id` and `text` with unique IDs per request. The comment at
[`imports.py:136`](./services/tokenos-api/tokenos_api/optimization/imports.py) states the
guarantee: *expected outputs are evaluator-only and are never included in a provider prompt.*

### Registered applications — two different things

This trips people up:

| | Classic connectors | Optimization registry |
| --- | --- | --- |
| Code | [`connectors.py`](./services/tokenos-api/tokenos_api/connectors.py) | `imports.py:194-439` |
| Examples | `claims-assistant`, `vendor-desk` | `support-archive` (bundled) + operator-registered |
| Real? | **No — local stubs**, `adapter="local_stub"`, header says so | Bundled one is sample data; operator entries read real approved local archives |
| Used by | Classic workflows | `workflow_optimization` |

The optimization registry is configured by `TOKENOS_OPTIMIZATION_APPLICATIONS_FILE`, which must
be an absolute local path — no URLs, no UNC, no traversal, no symlinks. The JSON must be
`{version: 1, applications: [...]}` with unknown fields rejected, IDs matching
`^[A-Za-z0-9][A-Za-z0-9_.-]{0,119}$`, and only the `normalized_archive` adapter permitted.

Scopes are `telemetry`, `test_inputs`, `model_execution`, and they are separate on purpose:
the bundled `support-archive` grants the first two and explicitly **not** the third
(*"Approved synthetic requests only; model execution is not permitted."*). Scope and revocation
are re-checked on every archive read and again inside `_call_model`, not just at describe time.

### Redaction

Secret detection lives in two places. `engine.py:26-27` holds the patterns
(`api_key|password|access_token|secret|authorization`) and `prompts.py` implements
`has_secret`, `redact_text`, `redact_value`. Redacted excerpts are excluded from the baseline
package, and a `secret-redaction` entry is added to `promptPlan.changes` so the user can see
that something was withheld.

### `digest()`

SHA-256 over canonical JSON (`sort_keys=True`, compact separators, `allow_nan=False`). Used for
`inputManifestHash`, `_sourceHash`, `contractHash`, reuse keys, price table hash and prompt
hashes. Canonical serialization is what makes those hashes stable across processes.

---

## 14. Storage, events, and SSE

SQLite at `settings.storage_root / "optimization.sqlite3"`, four tables:
`optimization_runs`, `optimization_events`, `optimization_files`, `optimization_claims`
([`store.py:36-49`](./services/tokenos-api/tokenos_api/optimization/store.py)). Schema is created
idempotently on every connection, so there are no migrations to run.

### The `_` convention — the actual trust boundary

```python
def public_state(run: dict) -> dict:
    return {key: value for key, value in run.items() if not key.startswith("_")}
```

Every engine entry point returns `public_state(run)`. Any key prefixed with `_` is server-only:
`_requests` (which contain `expectedOutput` and `_expectedResult`), `_priceTable`, `_contract`,
`_authorization`, `_execution`, `_tenant`, `_application`, `_deployments`,
`_promptBaselinePackage`, `_sourceHash`.

This one-line filter is what keeps evaluator answers out of the browser. **If you add server-only
state to a run dict, prefix it with `_`.** Forgetting is a data leak, not a style issue.

### Events

`store.event()` allocates a sequence number under `BEGIN IMMEDIATE`, giving a gap-free
monotonic ordering per run even with concurrent writers. Each event is `{sequence, runId, at,
type, ...data}`. Events are the only source of live UI truth.

### SSE

`router.events()` [`router.py:132`](./services/tokenos-api/tokenos_api/optimization/router.py)
reads a cursor from the `Last-Event-ID` header or `last_event_id` query parameter (a non-digit
cursor is a `422`), replays everything after it, then tails. Frames are standard
`id: / event: / data:`, with `: keep-alive` comments between polls and
`Cache-Control: no-cache`, `X-Accel-Buffering: no` so proxies do not buffer the stream.

Because the cursor is honoured, a dropped connection reconnects without losing or duplicating
events — which is what makes the polling fallback in §15 a genuine fallback rather than the
primary mechanism.

### Deletion

`store.delete()` removes the run, its events and its claims, then garbage-collects files no
other run still references. `store.clear()` does the same tenant-wide. Both were written against
tests that caught orphaned ledger rows.

---

## 15. Frontend architecture

React 18 + Vite + TypeScript. No component library, no state library, no router — phase state
is local and deliberate.

### The four cards

[`WorkflowChoices.tsx`](./apps/web/src/components/WorkflowChoices.tsx) is the single source of
truth for card copy:

| Internal ID | Title |
| --- | --- |
| `document_review` | Review documents against rules |
| `software_validation` | Test a code change |
| `deadline_processing` | Process records by a deadline |
| `workflow_optimization` | Optimize an existing AI workflow |

The ID list is built so `workflow_optimization` is always last and `false_savings` (a test
fixture workflow) never renders.

### `optimization/client.ts` — the anti-corruption layer

The most important frontend file. It converts loose server JSON into strict view models so no
component ever indexes into a raw response. Five primitives —`object()`, `array()`, `text()`,
`number()`, `strings()` — mean a missing or malformed field degrades to a safe default in one
place instead of throwing somewhere deep in a view.

`normalizeRecord()` is where server shape becomes `OptimizationRecord`. If the API adds a field,
this is the only file that needs to learn about it.

### Journey orchestration

`OptimizationJourney.buildPlan()` chains
`create → analyze → optimize → authorize → execute` in one user action, then attaches the SSE
stream, which drives phases through to `prove` without further clicks.

Authorization is *not* a separate click. It is bound to the Describe button, whose label states
what is about to happen ("Authorize and run the governed workflow") and which renders the exact
spend ceiling beside it. If `authorize()` rejects, the catch navigates to Protect and rethrows,
so the failed safeguards render where they belong:

```ts
catch (reason) { navigate("protect"); throw reason; }
```

The frontend deliberately does not parse the 409 status — it treats *any* authorize failure as
"go to Protect and show why", and Protect renders `protectionChecks` from the error body.

### Live progress

`optimizationStream()` opens an `EventSource` against
`/api/runs/{id}/events?last_event_id={lastSequence}` with an event-type allowlist. `onopen`
marks the stream live and cancels any fallback; `onerror` starts
`setInterval(() => sync(false), 2000)`. On terminal events the client re-fetches authoritative
state rather than trusting the last event. Polling never runs while SSE is healthy.

### Claim strength in the UI

[`Comparison.tsx`](./apps/web/src/components/shared/Comparison.tsx) defines
`EvidenceTier = "estimate" | "proven" | "none"` and its header states the rule:

> The tier is passed in explicitly rather than inferred here, so a caller can never accidentally
> render an estimate with measured styling.

`ComparisonCard`, `ClaimStrengthBar` and `RouteComparison` all take `tier` as a required prop,
and `EVIDENCE_WORD` centralises the vocabulary so the two Prove surfaces cannot drift apart.
The `none` tier renders no benefit at all rather than a zero.

---

## 16. Configuration reference

All in [`config.py`](./services/tokenos-api/tokenos_api/config.py). An optional `.env` beside the
service root is loaded at import.

| Variable | Default | Controls |
| --- | --- | --- |
| `TOKENOS_MODEL_MODE` | `local` | `local` or `foundry`. **`local` cannot spend money.** |
| `TOKENOS_FOUNDRY_BASE_URL` | `""` | Foundry endpoint |
| `TOKENOS_FOUNDRY_EFFICIENT_DEPLOYMENT` | `tokenos-efficient` | Efficient alias target |
| `TOKENOS_FOUNDRY_ADVANCED_DEPLOYMENT` | `tokenos-advanced` | Advanced alias target |
| `TOKENOS_FOUNDRY_BASELINE_DEPLOYMENT` | advanced deployment | Baseline alias target |
| `TOKENOS_FOUNDRY_AUTH_MODE` | `entra` | `entra` or `api_key` |
| `AZURE_INFERENCE_CREDENTIAL` | — | Required when auth mode is `api_key` |
| `TOKENOS_FOUNDRY_TOKEN_SCOPE` | `https://cognitiveservices.azure.com/.default` | Entra token scope |
| `TOKENOS_MODEL_TIMEOUT_SECONDS` | `20.0` | Provider timeout |
| `TOKENOS_MODEL_MAX_RETRIES` | `1` | Overridden to 0 by `single_attempt` |
| `TOKENOS_MAX_OUTPUT_TOKENS` | `500` | Hard output bound |
| `TOKENOS_MAX_MODEL_INPUT_CHARACTERS` | `12000` | Hard input bound |
| `TOKENOS_MAX_FILES_PER_RUN` | `10` | Upload/ZIP member count |
| `TOKENOS_MAX_FILE_BYTES` | `10 MiB` | Per-file cap |
| `TOKENOS_MAX_TOTAL_BYTES` | `25 MiB` | Aggregate cap |
| `TOKENOS_AMBIGUOUS_SAMPLE_LIMIT` | `20` | Ambiguous sample cap |
| `TOKENOS_TEST_TIMEOUT_SECONDS` | `10.0` | Local test adapter timeout |
| `TOKENOS_PHASE_PACING_MS` | `500` | **Presentation only** |
| `TOKENOS_OPERATION_PACING_MS` | `240` | **Presentation only** |
| `TOKENOS_STEP_PACING_MS` | `90` | **Presentation only** |
| `TOKENOS_STREAM_ATTACH_TIMEOUT_SECONDS` | `3.0` | SSE attach grace |
| `TOKENOS_CORS_ORIGINS` | `localhost:5173,127.0.0.1:5173` | CORS allowlist |
| `TOKENOS_STORAGE_ROOT` | `~/.tokenos/runtime` | SQLite + artifact root |
| `TOKENOS_WEB_DIST_ROOT` | `{service}/static` | Static SPA mount, if present |
| `TOKENOS_TENANT_ID` | `local` | Tenant identity — **server-side only, never a header** |
| `TOKENOS_OPTIMIZATION_APPLICATIONS_FILE` | — | Registered application registry |

Pacing is presentation only and is subtracted from measured work time. Set all three to `0` for
tests. `foundry_configured` requires mode `foundry`, a base URL, and (in api-key mode) the
credential — anything less and `model_available()` is false, which makes the `provider`
safeguard fail rather than letting a run proceed toward a call that cannot happen.

---

## 17. Test topology

Two runners, deliberately separate.

**Unit + API** — `pytest.ini`, the service `.venv`, ~180 tests, ~2m10s.

| File | Covers |
| --- | --- |
| `test_optimization_api.py` (35 KB) | Optimization lifecycle end to end |
| `test_prompt_api.py` | Prompt mode over HTTP |
| `test_full_matrix.py` (20 KB) | Workflow × source × mode matrix |
| `test_optimization_unit.py`, `test_prompt_unit.py` | Pure functions: contracts, gates, context |
| `test_savings_eligibility.py` | The §11 gate |
| `test_pricing_unit.py`, `test_ledger_unit.py`, `test_route_counts.py` | Cost, ledger, routing counts |
| `test_history_delete.py`, `test_comparison_endpoint.py`, `test_workflow_labels.py` | Endpoints and copy |
| `test_foundry_unavailable.py` | Failure path |

**Browser** — `pytest-browser.ini`, system Python + Playwright, 118 tests, ~3m30s.
`e2e_optimization.py` holds the shared helpers (`build_plan`, `build_plan_to_protect`,
`execute_to_prove`, `sample_file`) that the other suites import; change it carefully.
`capture_history.py`, `demo_recording.py` and `capture_prove.py` are capture scripts, not tests,
and are excluded by the ini.

```powershell
# unit + API
cd tokenos\services\tokenos-api; .\.venv\Scripts\python.exe -m pytest -q

# browser
cd tokenos\services\tokenos-api
& "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe" -m pytest -c pytest-browser.ini -q

# frontend typecheck + build
cd tokenos\apps\web; npm run build
```

### The test trap that has bitten twice

**Fakes that return the expected answer verbatim hide real bugs.** The prompt provider fake once
returned `expectedResult` exactly, so no test noticed that the shipped sample could never pass
exact-match verification against a real model. It now returns freely-worded prose with the graded
value in `decision`.

Similarly, local mode never escalates, so a bug in multi-call cost aggregation survived every
test until it appeared in a screenshot.

When you write a fake, make it behave like a *plausible* provider, not a *cooperative* one.

---

## 18. Invariants that must not regress

From [`AGENTS.md`](./AGENTS.md) and enforced throughout:

1. **No browser timer produces a phase, cost, token, quality or savings value.** Every one comes
   from a server event.
2. **Pacing is presentation only** and is subtracted from measured work time.
3. **Never show a number the server did not produce.** If something is unavailable, say so.
4. **Avoided cost appears only with a valid measured baseline.**
5. **No model call before explicit authorization.** `_call_model` enforces it server-side; the UI
   affordance is a convenience, not the control.
6. **Expected outputs never reach a provider.** Guarded by the `_` convention, the payload
   builders, and asserted in the fakes.
7. **Credentials never reach the browser.** Config endpoints return booleans.
8. **Measured cost requires complete provider usage** — `strict_usage`, non-negative integer
   counts, and a `providerRequestId`.
9. **The price table is pinned per run** and a change invalidates rather than re-prices.
10. **Quality is a precondition of cost comparison**, never a parallel report.

---

## 19. Extension recipes

### Add a quality gate

1. Add the ID to `SUPPORTED_GATES` ([`quality.py:11`](./services/tokenos-api/tokenos_api/optimization/quality.py)).
2. Add a pre-flight rule to `gate_blockers()` — what makes it *unevaluable*? Refuse there rather
   than failing after spending.
3. Add the check branch to `verify_output()`. It must be deterministic.
4. Add the label to `QUALITY_OPTIONS` in [`OptimizationDescribe.tsx`](./apps/web/src/optimization/OptimizationDescribe.tsx).
5. Consider bumping `VERIFIER_VERSION` — it is in the contract, so bumping it correctly
   invalidates cross-version comparisons.

### Add a local adapter (avoid a model call)

Extend `local_result()` with a new `taskType` branch. It must return `(output, evidence)` and
**return `None` when ambiguous** — follow the `classification` branch, which refuses on zero or
multiple matches. Add the type to the allowlist in `normalize_requests()`
([`imports.py:120`](./services/tokenos-api/tokenos_api/optimization/imports.py)). Never execute
user-supplied code; follow the arithmetic AST allowlist pattern.

### Add a model route

Add the alias to `_deployments()` ([`engine.py:63`](./services/tokenos-api/tokenos_api/optimization/engine.py)),
add prices for the deployment, extend the route selection in `_route()`/`route_alias()`, and
extend `_checks()` reservation accounting so the budget check still bounds the worst case.
Routes not in `{tokenos-efficient, tokenos-advanced}` are coerced to efficient at
[`engine.py:819`](./services/tokenos-api/tokenos_api/optimization/engine.py) — update that too.

### Add a proof field

Add it in `_proof()`, surface it through `normalizeRecord()` in
[`optimization/client.ts`](./apps/web/src/optimization/client.ts), then render it. State its
evidence tier explicitly. If it is derived rather than measured, name it so
(`estimated…`, `projected…`) and give it a tier of `estimate`.

### Add an input source

Add the value to the `InputSource` literal and `_SOURCE_FAMILIES` in
[`schemas.py`](./services/tokenos-api/tokenos_api/optimization/schemas.py), extend
`validate_target_inputs`, add parsing in `imports.py` with explicit limits, and add the card to
the relevant `*_SOURCES` array in `OptimizationDescribe.tsx`.

---

## 20. Sharp edges and known limits

Things that will surprise you, stated plainly.

**Architectural**

- **Two engines** (§3). Easy to patch the wrong one. `workflow_optimization` → `optimization/`;
  everything else → `runner.py`.
- **Two cost functions.** `pricing.calculate_cost_usd` returns `(0.0, False)` on an unknown
  deployment; `engine.cost_for_usage` raises. The optimization engine only uses the latter.
- **Single tenant.** `tenant_id()` reads `TOKENOS_TENANT_ID`, defaulting to `local`, and
  explicitly never a request header. Multi-tenancy would need real work in `store.py`.
- **`_checks()` mutates** `run["_maximumReservationUsd"]` as a side effect.

**Functional**

- **Verification is exact-match only** (§9). Deliberate — a fuzzy or model-judged gate would make
  the savings claim unfalsifiable — but it means gradeable outcomes must be discrete values, not
  prose. Prompts with an `expectedResult` therefore get a `decision` field in their contract.
- **Analyze mode cannot invoke a model at all.** Its proof carries a projection, never a measured
  cost, and `authorizeModelCost` is `false`.
- **Classic connectors are local stubs.** `claims-assistant` and `vendor-desk` are labelled
  `adapter="local_stub"`. Only the optimization registry reads real archives, and only from
  operator-approved absolute local paths.
- **The bundled `support-archive` has no `model_execution` scope**, so it can never trigger a
  real call — by design.
- **`latency_target` disables batch eligibility** unconditionally.
- **Reuse is intra-run only.** `_route()` builds a fresh `reuse = {}` per execution; there is no
  cross-run cache.

**Operational**

- **Restart both servers after changes.** A stale API or Vite process has repeatedly produced
  false "it's broken" reports.
- **A dev API in `foundry` mode spends real money.** Use an isolated harness for experiments.
- **PowerShell has no heredoc.** Use a here-string piped to `python -`, or a temp file for commit
  messages.
- **Sample fixtures are synthetic *inputs*, not synthetic *execution*.** `fixtures.py` header:
  *"Synthetic inputs, not synthetic execution, token usage, or prices."* A sample run performs
  real local work and, in foundry mode, real calls. Runs are tagged `proofType: "sample"` and
  badged `Measured sample run`.

---

## Appendix: where to look first

| Question | File |
| --- | --- |
| Why did this run cost that? | `_proof()` → `cost` block, then `modelUsage` rows |
| Why did it not claim a saving? | `comparison()` — walk the nine `comparable` conditions |
| Why was Protect blocked? | `_checks()` — the failed check's `detail` is the reason |
| Why did it call a model here? | `_route()` — reuse, then `local_result()`, then the fallthrough |
| Why did it escalate? | The `quality.result` event before the `escalation.decision` event |
| Why is this field not in the UI? | It probably starts with `_` and never left the server |
| Why did the request 422? | `schemas.py` validators, then `imports.py` limits |
| Why is the UI stuck on a phase? | Check SSE in devtools; then whether the run is `failed` |
