# TokenOS: AI Work Optimizer

TokenOS is the operating system for AI work. It helps enterprises reduce avoidable AI spend while protecting the quality of the real business outcome.

The Tokenomics challenge asks us to move beyond reactive token caps and usage reports. Enterprises do not need AI usage to be restricted. They need AI work to be intentional, measurable, governed, and economically defensible. TokenOS addresses that gap by choosing the least-expensive safe route for every part of an AI task, then proving the outcome and its economics.

Repository: [github.com/jvargh/hack26-tokenomics](https://github.com/jvargh/hack26-tokenomics)

Link to test: [TokenOS ACA App](https://tokenos-hack26.yellowwater-54592620.eastus.azurecontainerapps.io/)

## The problem

Most AI applications treat a user request as a single model call. In practice, one request may contain routine validation, retrieval, duplicate detection, calculations, policy checks, code tests, formatting, retries, reasoning, and response generation.

When every step is sent to a model:

- Token spend rises even when software could complete the work.
- Full document sets, conversation history, and tool definitions are repeatedly sent as context.
- Advanced models are used before lower-cost routes are tested.
- Cost is measured after it is spent rather than authorized before execution.
- Teams can report tokens, but cannot prove that higher spend delivered a better outcome.
- A lower-cost route may look successful while creating quality failures, retries, rework, human review, or hidden escalation cost.

The measure that matters is not cost per token. It is **cost per successfully completed and verified outcome**.

## What TokenOS does

TokenOS accepts a prompt or workflow, then turns it into a governed execution plan. It uses local software, approved retrieval, reuse, context minimization, and efficient model routing before permitting a paid model call.

Azure AI Foundry provides model intelligence. TokenOS decides whether intelligence is needed, which route is eligible, what context may be sent, how much spend is authorized, and how the result must be verified.

TokenOS runs through seven visible phases:

![TokenOS AI Work Optimizer overview. A seven-phase band reads Describe, Plan, Optimize, Protect, Run, Verify, Prove. Below it a routing diagram shows a prompt or workflow entering local rules, retrieval and reuse, then an efficient Foundry model only if needed, with an escalation branch used only if required, ending in quality verification and measured cost and outcome proof.](TokenOS-main-slide.png)

**Figure 1 — The seven-phase journey and the routing model.** The upper band shows the phases in order. The diagram beneath it is the part that carries the argument: a prompt or workflow enters at the left, local rules, retrieval and reuse resolve everything they can, and an efficient Foundry model is called only if unresolved work remains. The orange branch, *escalate only if required*, is taken only when the efficient route fails verification, so an advanced model is never the starting point. Every path ends in quality verification and measured cost and outcome proof. The four cards name the shipped entry points, each with the condition under which AI is permitted at all. The closing principles state the rule the whole design follows: local work first, AI used with purpose, quality protected, and verified savings only after a matched baseline.

1. **Describe**: Capture the prompt or workflow, required outcome, quality requirements, budget, deadline, and allowed data scope.
2. **Plan**: Break the request into discrete operations so routine work is visible before a model is called.
3. **Optimize**: Select the least-expensive safe route for each operation: regular software, approved retrieval, validated reuse, efficient AI, or advanced AI only when necessary.
4. **Protect**: Apply enterprise safeguards before spend: data policy, context minimization, budget ceiling, output constraints, quality threshold, model eligibility, and escalation rules.
5. **Run**: Execute only the approved path and capture real provider usage, tokens, latency, model calls, and calculated model cost.
6. **Verify**: Check citations, facts, policy coverage, structured output, tests, amounts, deadlines, and workflow-specific acceptance criteria.
7. **Prove**: Show what completed without generative AI, why any AI call was allowed, measured model cost, quality outcome, and verified savings when a matched baseline qualifies.

## How routing works

```text
Prompt or workflow
        ↓
Local rules, retrieval, reuse, validation, tests, and calculations
        ↓
Efficient Azure AI Foundry model only if unresolved work remains
        ↓
Advanced model only if the efficient route fails required verification
        ↓
Independent quality verification
        ↓
Measured cost and outcome proof
```

AI is not treated as the default processor. It is treated as a bounded capability used where it adds real value.

Examples of work that can stay local include file validation, schema checks, SHA-256 duplicate detection, policy lookups, arithmetic, structured extraction, code analysis, allowlisted tests, citation checks, output validation, and deterministic decision summaries.

## Engine architecture

![TokenOS engine deep dive. A request path runs from the React web client through FastAPI to a dispatching runs endpoint and server-owned run state. Panels detail the API surface, two independent engines behind one API, the Foundry spend boundary, a durable SQLite proof gate, the conditions under which two runs are comparable, and the comparison rule that yields a verified saving.](TokenOS-Engine-Deep-Dive.png)

**Figure 2 — API, execution paths, and the proof contract.** One FastAPI surface dispatches both the fixed workflows and user-supplied optimization runs while preserving a single evidence model. Three things in this diagram matter most:

- **Two independent engines behind one API.** The classic engine runs the three fixed workflows; the optimization engine runs the describe-to-execute sequence. Both are driven by a server-authorized state machine (`described → planned → optimized → authorized`, then `running → completed | failed`). The server owns that state and returns `409` with the required and current state, so the browser cannot skip a phase or authorize spend out of order.
- **A single spend boundary.** `_call_model()` is the only path that can spend. It validates contract, tenant, scope and authorization, reserves the worst-case cost *before* calling Foundry, allows a single strict attempt, and records tokens, request ID, latency and an exact `Decimal` cost. `modeladapter.py` alone imports the provider SDK, and credentials never leave the server.
- **A durable proof gate.** Runs, events, files and claims persist to SQLite with a gap-free sequence that drives both live SSE and replay. Two runs are comparable only when they share a contract and price hash, both pass their quality gates, usage is complete, outcomes are equal, and provider request IDs are present. Only then does `comparison()` compare costs, and only a costlier baseline yields a verified saving.

The footer states the operating rule: **fail closed**. Incomplete evidence never becomes zero cost, and a cheaper rejected answer never becomes a saving.

## Practical use cases

### Review documents against rules

TokenOS checks submitted records against policies, evidence, amounts, duplicate items, and explicit rules locally. It sends only genuinely unclear policy interpretation to an efficient model, then verifies the returned citation and facts.

### Test a code change

TokenOS runs static checks, schema validation, secret scanning, and approved tests before invoking a model. AI is reserved for unresolved test failures, bounded diagnosis, or a constrained patch proposal.

### Process records by a deadline

TokenOS validates complete input coverage, plans throughput, and processes routine records locally. It reserves AI capacity for the ambiguous exception set rather than multiplying model cost across every record.

### Optimize an existing AI workflow

A user can start with a single prompt or a recurring AI workflow. TokenOS identifies repeated context, unnecessary tool definitions, cache-eligible prefixes, model-routing opportunities, retries, and quality risks. It can compare the current route with a governed route that preserves the required outcome.

## Core Tokenomics capabilities

- **Cost-aware prompt optimization:** Identifies repeated instructions, irrelevant context, oversized history, output verbosity, and structured-output opportunities before a prompt is run.
- **Context minimization and reuse:** Sends only the approved evidence needed for the task and preserves stable context where caching or reuse is eligible.
- **Lightweight model selection:** Starts with the lowest-cost eligible route and reserves advanced reasoning for quality failures or policy-required escalation.
- **Budget-guided orchestration:** Authorizes model spend before execution, reconciles actual provider usage after execution, and records the reason for every paid call.
- **Quality-aware optimization:** Checks that a lower-cost route still meets the same evidence, safety, accuracy, structure, latency, and acceptance requirements.
- **Measured economics:** Calculates model cost from actual provider usage and a pinned, versioned price table.
- **Outcome-aware reporting:** Tracks model spend, model calls avoided, local completion rate, cost per accepted outcome, quality pass rate, escalation rate, and verified savings.
- **Feedback loops:** Preserves execution evidence so teams can improve routing, prompts, policies, and model choices over time.

## Honest savings proof

TokenOS distinguishes clearly between:

- **Estimated**: A pre-run prediction such as expected input-token reduction.
- **Measured**: Actual usage and calculated cost from a completed provider call.
- **Projected**: A scale forecast based on a measured run rate.
- **Verified saving**: A claim permitted only after a governed route and a matched all-AI baseline use the same inputs, output contract, quality checks, and price table, both pass, and the all-AI baseline costs more.

This prevents a common failure mode in AI cost optimization: presenting an untested projection as a real saving.

![TokenOS benefits. A measured sample walkthrough shows a verified saving of $0.0065 per run, with a matched all-AI baseline bar at about $0.0067 against a much shorter TokenOS governed route bar at $0.0002, plus figures of about 97 percent lower measured model spend, 7 of 8 operations using zero model tokens, and 1 Foundry model call. A second column explains how the benefit is created, and a footer row summarises the value to finance, engineering, governance, and product and users.](TokenOS-Benefits.png)

**Figure 3 — A worked example of the claim rules above.** The left panel is a single measured sample run in which both routes completed the same work and passed the same quality checks. The matched all-AI baseline cost about **$0.0067**; the TokenOS governed route cost **$0.0002**; the difference, **$0.0065 per run**, is reported as a verified saving precisely because the baseline ran, matched, and cost more. Seven of eight operations used zero model tokens and one Foundry call was authorized.

The right column explains where that result comes from: eliminating unnecessary model spend through local rules, approved retrieval and reuse; controlling every paid call through a hard spend ceiling, minimal context and efficient-first routing enforced before execution; and proving the saving without lowering quality through provider-measured usage, pinned prices and a quality-matched baseline. The bottom row states what each audience gets — defensible cost per accepted outcome for finance, a reason and cost record for every route for engineering, budget control before spend and audit after for governance, and lower cost without accepting worse results for product and users.

Two caveats are printed on the figure itself and are repeated here deliberately: this is **sample evidence, not a customer claim**, and **zero model tokens does not mean zero total operating cost**. Local execution still consumes compute and engineering time.

## Enterprise readiness

TokenOS is a governance and measurement framework, not just a prompt optimizer or token dashboard. It supports registered application connections with approved server-side scopes; data decisions of allow, redact, minimize, require approval, or block; budget and model authorization controls; quality, safety, and evidence gates; application, team, environment, and cost-center attribution; real-time execution visibility; and audit-ready run proof.

Enterprise reporting separates measured, projected, and sample values so forecasts cannot be mistaken for spend or verified savings.

## Why TokenOS matters

The challenge is not to make enterprises afraid of AI spend. It is to make AI adoption sustainable because the business can see what value it receives for that spend.

**Local work first. AI used with purpose. Quality protected. Savings verified only after a matched baseline.**

TokenOS helps enterprises use AI where it improves the result, not where it merely spends tokens.