# TokenOS Workflow Architecture & Workings Specification

This document details the architectural workings, decision routing, and execution lifecycle of **TokenOS** — confirming alignment with the hybrid model governance framework.

---

## 1. Executive Summary & Core Principle

> **"Foundry provides intelligence. TokenOS decides whether intelligence is worth paying for."**

TokenOS operates as a **local governance and cost-control control plane** for AI workflows. Rather than treating Large Language Models (LLMs) as default processors, TokenOS enforces a deterministic-first architecture:
1. Enterprise tasks are decomposed into discrete, verifiable operations.
2. Regular software (regex, SHA-256 deduplication, table parsing, static analysis, unit tests, schema validators) executes first at **zero token cost**.
3. Microsoft Azure AI Foundry models are invoked **only** when unstructured text, messy context, or policy ambiguity cannot be resolved deterministically.
4. TokenOS post-validates all model outputs (citations, numbers, policy clauses) and escalates to advanced reasoning tiers only when quality thresholds fail.

---

## 2. End-to-End Execution Flowchart

The TokenOS execution engine follows the hybrid decision flow depicted below:

```
                  ┌─────────────────────────────────────┐
                  │    User Selects Workflow Type       │
                  │    and Data / Input Source          │
                  └──────────────────┬──────────────────┘
                                     │
                                     ▼
                  ┌─────────────────────────────────────┐
                  │       Local TokenOS API             │
                  │ Validates files, schema, rules,     │
                  │ budget ceiling, and quality target  │
                  └──────────────────┬──────────────────┘
                                     │
                                     ▼
                     /───────────────────────────────\
                    <   Can regular software complete >
                    <       and verify this step?     >
                     \───────────────────────────────/
                                     │
                     ┌───────────────┴───────────────┐
                 Yes │                               │ No
                     ▼                               ▼
     ┌───────────────────────────────┐   ┌───────────────────────────────┐
     │  Execute Locally with         │   │ Call Foundry Efficient        │
     │  Deterministic Software       │   │ Deployment (e.g. gpt-4.1-nano)│
     │  (Zero Model Tokens)          │   └───────────────┬───────────────┘
     └───────────────┬───────────────┘                   │
                     │                                   ▼
                     │                   /───────────────────────────────\
                     │                  <   Quality & Citation checks   >
                     │                  <             pass?             >
                     │                   \───────────────────────────────/
                     │                                   │
                     │                   ┌───────────────┴───────────────┐
                     │               Yes │                               │ No, ambiguity remains
                     │                   ▼                               ▼
                     │   ┌───────────────────────────────┐   ┌───────────────────────────────┐
                     │   │ Accept Measured Result        │   │ Call Foundry Advanced         │
                     │   │ (Usage recorded from API)     │   │ Deployment (e.g. gpt-4o)      │
                     │   └───────────────┬───────────────┘   └───────────────┬───────────────┘
                     │                   │                                   │
                     │                   │                                   ▼
                     │                   │                   ┌───────────────────────────────┐
                     │                   │                   │ Validate Result Locally       │
                     │                   │                   │ (citations, amounts, bounds)  │
                     │                   │                   └───────────────┬───────────────┘
                     │                   │                                   │
                     └───────────────────┼───────────────────────────────────┘
                                         ▼
                         ┌───────────────────────────────┐
                         │   Produce Measured Run Proof  │
                         │   & Paired Baseline Compare   │
                         └───────────────────────────────┘
```

---

## 3. Workflow Capabilities Matrix

| Workflow Selection | 1. Local TokenOS Handles First (Zero Tokens) | 2. Foundry Efficient Model (Bounded / Only if Needed) | 3. Foundry Advanced Model (Escalation Only) |
| :--- | :--- | :--- | :--- |
| **Review documents against rules** | File format validation, SHA-256 duplicate detection, line item extraction, explicit policy rules, mathematical checks, citation matching. | Extract ambiguous clauses from unstructured text or summarize grounded evidence. | Resolve a contested policy exception when efficient model output fails verification. |
| **Test a code change** | Diff parsing, schema validation, AST/static checks, allow-listed test runs (`python -m unittest`), secret scanning. | Propose a bounded code patch or explain a specific failed test. | Diagnose complex multi-file architectural tradeoffs or unresolved system failures. |
| **Process records by a deadline** | Parse all records, validate JSON/CSV schema, estimate processing throughput, calculate deadline feasibility equations. | Classify only ambiguous records in a capped sample or micro-batch. | Rarely needed. Reserved for materially uncertain or high-risk records. |
| **Optimize an existing AI workflow** | Normalize approved telemetry and representative inputs, compile a local plan, validate rules and reuse eligibility, pin the execution contract. | Resolve bounded work only after Protect authorization and budget reservation. | Escalate only after failed efficient verification and within explicit authorization. |

The legacy false-savings calculator remains available internally. It is not a primary
workflow. An optimization saving requires an explicitly requested, completed all-AI
baseline with identical input manifest, output contract, output limit, quality gates,
and price-table version; both routes must pass and the baseline must cost more.

---

## 4. Input Sources & Ingestion Modes

| Input Source | Processing Path | Governance & Context Handling |
| :--- | :--- | :--- |
| **Upload My Data** | User files (PDF/MD/CSV/JSON/ZIP) stream directly to the local TokenOS API. | Data is processed locally. Sensitive tokens/PII are stripped before any external API call. |
| **Connected Application** | TokenOS connects to external systems via registered adapters (OpenAPI, database, file shares). | Retrieves only approved context adhering to pre-configured RBAC and rate limits. |
| **Use Sample Data** | High-fidelity test sets bundled within TokenOS. | Enables deterministic benchmarking, reproducible demonstrations, and automated regression testing. |

---

## 5. The 9-Step Live Execution Timeline (Document Review Example)

When executing the **Document Review** workflow on supplier invoices against procurement policies, TokenOS executes the following visible timeline:

```
[1. Ingest & Read]       Read invoice and policy files locally (Markdown/PDF/JSON).
         │
[2. Deduplicate]         Detect duplicate charges locally using line hashing (Zero tokens).
         │
[3. Match Rules]         Evaluate explicit policy constraints (e.g., meal caps, travel rates).
         │
[4. Isolate Ambiguity]   Identify contested line items (e.g., weekend rework surcharge) that rules cannot settle.
         │
[5. Reserve Budget]      Reserve cost ceiling for an efficient Foundry call ($0.0005 max).
         │
[6. Targeted AI Call]    Call Foundry Efficient (e.g. gpt-4.1-nano) passing ONLY the relevant policy section and charge line.
         │
[7. Local Verification]  Verify returned policy citation (e.g., Section 4.2) and calculated dollar amounts locally.
         │
[8. Escalation (Opt)]    If confidence < threshold or citation check fails, escalate to Advanced Model (e.g. gpt-4o) once.
         │
[9. Economic Proof]      Compile token counts, measured duration, calculate cost from versioned price table, and generate run proof.
```

---

## 6. Tokenomics Measurement & Governance Proof

### 6.1 Real Measurement vs. Estimation
- **Measured Run Spend:** Uses `response.usage.prompt_tokens` and `response.usage.completion_tokens` directly from the Microsoft Foundry / Azure OpenAI API response. TokenOS **never** relies on approximate tokenizers (`tiktoken`) for verified billing.
- **Estimated Comparator:** Pre-flight projection used only to illustrate expected cost prior to execution.
- **Paired Baseline (`POST /api/baseline`):** Runs the identical task using an unconstrained all-AI pipeline under identical prompts, test sets, and quality gates to prove genuine avoided spend.

### 6.2 The "Why AI?" Governance Audit Record
For every paid AI invocation, TokenOS produces an immutable governance rationale:

```json
{
  "operation": "resolve_ambiguous_line_item",
  "tier": "efficient",
  "deployment": "tokenos-gpt41-nano",
  "reason": "Deterministic rule could not settle Section 4.2 overtime exception.",
  "tokens": { "prompt": 1766, "completion": 211, "total": 1977 },
  "measured_cost_usd": 0.000261,
  "quality_verification": "Passed: Section 4.2 citation verified with exact line match."
}
```

---

### 6.3 Counting Rules Enforced by the Prove Screen

Every number on the Prove screen is derived from one executed run record, never from
separately rendered constants. Three quantities are deliberately kept distinct:

| Quantity | Source field | Meaning |
| --- | --- | --- |
| Operations | `routing.operations` | Steps the plan contained and the runner executed. |
| Operations without generative AI | `routing.completed_without_generative_ai` | Steps whose executed route was software, retrieval, or reuse. |
| Model calls | `usage.model_calls` | Foundry requests actually issued, one governance record each. |

The invariants are:

```
completed_without_generative_ai + efficient_ai + advanced_ai == operations
len(why_ai) == usage.model_calls
sum(row.model_calls for row in tokenomics.routing.rows) == usage.model_calls
```

A model-assisted operation is not the same as a model call: one call may serve more
than one step, so the headline states both figures rather than merging them. The
screen therefore reads *"8 operations. 7 completed without generative AI. 1 operation
used 1 Foundry call."* rather than a single blended count.

Two claim-strength rules apply to the wording:

- **Before a paired baseline runs**, the heading is *"Verified review decision. Minimal AI use. Measured cost proof."* and the volume figure is labelled *"Projected spend at the current measured run rate … Not a verified saving."*
- **Only after `POST /api/runs/{id}/baseline` completes with `equal_quality`** does the heading become *"Same verified decision. Fewer AI calls. Lower measured cost."* and the volume figure become a *Verified saving*.

The paid call must also be materially useful. `Resolve contested policy interpretation`
is the only operation permitted to reach a model; `Create decision summary` is rendered
from verified findings by a deterministic template at zero token cost. This is asserted
by `tests/check_prove_numbers.py`, which fails if a summary step is ever routed to a model.

---

### 7.1 Dynamic Foundry Configuration
TokenOS exposes runtime configuration endpoints:
- `GET /api/foundry/config` — Retrieves current connection, auth mode, and price tables.
- `POST /api/foundry/config` — Updates parameters and hot-reloads the adapter without restarting the server.
- `POST /api/foundry/test` — Performs real-time diagnostic latency and token pings for both Efficient and Advanced deployments.

### 7.2 Price Table Versioning
Costs are calculated deterministically from `price_table.json`, versioned by:
- `deployment`: Azure deployment identifier
- `model`: Model architecture (e.g., `gpt-4.1-nano`, `gpt-4o`)
- `model_version`: Specific release timestamp
- `region`: Azure datacenter region (e.g., `eastus`)
- `effective_date`: Valid pricing schedule timestamp

---
*TokenOS Architecture Specification — Microsoft AI Tour & Hackathon Edition*
