# Tokenomics: The Zero-Waste AI Challenge

*Microsoft Global Hackathon 2026 — Executive Challenge*

## Goal

Today, AI is mostly measured by usage, tokens, and consumption. When cost becomes the story, the instinct is to clamp down, and every cap quietly taxes the innovation we exist to deliver.

There is a better way. Customers have moved past experimenting; they want outcomes and the ROI behind them, and they want them faster than ever.

As part of the Global Hackathon, this Executive Challenge invites you to rethink how AI value is measured and delivered. The goal: move from reactive cost controls to intelligent, cost-aware AI that scales value, not just spend.

This is what a services renaissance looks like in practice, and SP&D should lead it. Come hack it, mentor it, or judge it.

## Sponsors
### Executive Sponsor 
Karina Radulescu - CVP, Services Portfolio & Delivery

Aparna Gupta - VP, Global Center for Innovation and Delivery

Sapna Grover - Consulting Practice Leader, Global Center for Innovation and Delivery

## Leadership ask

We're sponsoring an Executive Challenge at this year's Microsoft Global Hackathon: **Tokenomics: The Zero-Waste AI Challenge**. I know how passionate this team is about AI and innovation, and I'd love to see us take on the challenge!

- **The challenge:** AI is increasingly measured by usage, tokens and consumption. When cost becomes the main story, the instinct is to clamp down and every cap quietly taxes the innovation we exist to deliver.
- **The goal:** move from reactive cost controls to proactive, cost-aware AI, so enterprises scale sustainably while maximizing ROI. Directions include cost-aware prompt optimization, lightweight model-selection heuristics, budget-guided orchestration, and feedback loops that keep improving efficiency.

You don't need to be an engineer. A business process idea, a telemetry idea, or one that changes our customer conversations all count. Come hack it, mentor it, or judge it.

## Go deeper on Tokenomics

- [Prompt caching](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/prompt-caching)
- [Model router](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/model-router?tabs=foundry-responses)
- [AI gateway in Azure API Management](https://learn.microsoft.com/en-us/azure/api-management/genai-gateway-capabilities)
- [Evaluation and observability](https://learn.microsoft.com/en-us/azure/foundry/concepts/observability)

### What each link actually says about tokens and cost

_Pulled directly from the four pages above on 2026-08-31. Mechanics, not prices — verify current rates and model availability before quoting anything to a customer._

**Prompt caching** ([source](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/prompt-caching))

- Reduces latency and **cost** for prompts that repeat identical content at the start. It reuses processed input-token computations instead of recomputing them on every call. It never changes the output content, only latency and cost.
- **Eligibility:** the request needs at least 1,024 tokens, and the first 1,024 tokens of the prompt must be identical to a previous request. Any change to that leading block invalidates the match.
- **Billing:** cache reads are billed at a **discount on input-token pricing** for Standard deployments, and **up to a 100% discount** on Provisioned Throughput (PTU) deployments. Models before the GPT-5.6 family never charge extra to *write* to the cache; GPT-5.6 and later can charge for cache writes in addition to discounted cache reads — so prompt structure (keeping the reused block byte-identical) directly controls whether you pay to write the cache or only benefit from reading it.
- **Cache lifetime:** the default in-memory cache is cleared after 5–10 minutes of inactivity and always removed within 1 hour. An **extended retention** option (available on newer models such as `gpt-5.5`, `gpt-5.4`, `gpt-4.1`) can keep a cached prefix alive for up to **24 hours** by offloading it to storage. Caches are never shared across Azure subscriptions.
- **Cache hit/write visibility:** hits appear as `cached_tokens` under `prompt_tokens_details` in the response; GPT-5.6+ models also report `cache_write_tokens` separately, so cache economics can be measured per call, not assumed.
- On GPT-5.6+ models, a `prompt_cache_key` and explicit **cache breakpoints** let you mark exactly which prefix is reusable, up to 4 new cache writes per request, and Azure considers up to the last 50 breakpoints in a conversation for cache reads.

**Model router** ([source](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/model-router?tabs=foundry-responses))

- A single deployable Foundry model that **picks which underlying LLM answers each request in real time**, across a large supported set (OpenAI, Anthropic, xAI, DeepSeek, and Meta models as of the `2025-11-18` router version).
- **Three routing modes**, selectable per deployment: **Balanced** (default — "optimizes cost while maintaining quality"), **Quality** ("critical tasks like legal review, medical summaries, or complex reasoning"), and **Cost** ("high-volume, budget-sensitive workloads like content classification or simple Q&A"). Mode and model-subset changes take up to five minutes to propagate.
- You can restrict routing to a **custom subset of models** for tighter control over cost, compliance, and performance — new models are excluded by default until explicitly added to that subset.
- Model router is a **single deployment**: you don't need to separately deploy every candidate model (Claude models are the one exception — they must be deployed first for the router to be able to select them).
- **Tokenomics implication directly relevant to this challenge:** because the router can select a reasoning-capable model, and reasoning tokens bill as output even though you never see them, a workload's real cost under the router depends on *which* model it actually picked for a given request, not just which mode you configured — worth measuring per request, not assuming from the mode label.

**AI gateway in Azure API Management** ([source](https://learn.microsoft.com/en-us/azure/api-management/genai-gateway-capabilities))

- Positioned to solve exactly the problem of **one app consuming an entire shared token quota** and starving other consumers: it manages "token usage and quotas across multiple applications," not just a single deployment's limit.
- **Token rate limiting and quotas:** the `llm-token-limit` policy enforces a tokens-per-minute limit or a token quota over an hourly/daily/weekly/monthly/yearly window, keyed on any counter (subscription key, IP address, or a custom policy expression) — so multiple apps or teams can share one backend without one of them exhausting it. The policy can also **precalculate prompt tokens at the gateway** to reject an over-limit request before it ever reaches the AI backend.
- **Semantic caching:** using Azure Managed Redis (or another RediSearch-compatible cache), the `llm-semantic-cache-store` / `llm-semantic-cache-lookup` policies reuse a previous completion when a new prompt is *semantically* similar, not just textually identical — this is a different, complementary mechanism to prompt caching, and Microsoft's own docs note it "can help reduce costs" without promising a specific number.
- **Observability built for cost, specifically:** the `llm-emit-token-metric` policy emits token-usage metrics into Azure Monitor with custom dimensions (for example client IP, API ID, or a user-ID header), so spend can be broken out per consumer. API Management can also log prompts/completions to Azure Monitor and expose a built-in monitoring dashboard.
- **Resiliency features that also protect cost:** backend load balancing (round-robin, weighted, priority) and a **circuit breaker** that respects the backend's own `Retry-After` header, so a struggling or throttled backend doesn't silently keep absorbing (and billing) retried calls.
- Managed identity authentication to AI services means you can avoid distributing API keys to every consuming application.

**Evaluation and observability** ([source](https://learn.microsoft.com/en-us/azure/foundry/concepts/observability))

- Three core capabilities work together: **evaluation** (built-in quality/safety/RAG/agent-specific metrics you run against a dataset), **monitoring** (real-time dashboards for token consumption, latency, error rates, and quality scores, integrated with Application Insights), and **tracing** (OpenTelemetry-based distributed traces across LLM calls, tool invocations, and agent decisions).
- The explicit reason this matters for tokenomics: evaluation exists so a cost optimization can be checked against quality **before and after** it ships — "continuous evaluation" samples production traffic on an ongoing basis, and "scheduled evaluation" re-runs a fixed test dataset over time to catch quality drift that a cost dashboard alone would never surface.
- Three lifecycle stages: **base model selection** (compare quality/cost/safety across candidate models before committing to one), **pre-production evaluation** (validate task adherence, groundedness, relevance, and safety before deployment), and **post-production monitoring** (operational metrics, continuous and scheduled evaluation, scheduled red-teaming, and Azure Monitor alerts when outputs fail a quality threshold).
- The practical takeaway for a "zero-waste" pitch: none of the other three levers (caching, routing, gateway quotas) can tell you whether a cost reduction broke quality. That join has to come from this fourth pillar — which is exactly the gap most "levers" projects in this challenge leave unaddressed (see the competitive analysis appended to `projects_detailed.md`).

---

# How token billing actually works

This is the reference the show keeps pointing back to. It is deliberately vendor-neutral and deliberately free of specific list prices, because prices move and the mechanics do not. Use it to build accurate customer language, then check current rates before you quote anything.

## 1. Tokenization

Language models do not read characters or words. They read tokens: sub-word fragments produced by a tokenizer. A common English word is usually one token. A rare word, a long identifier, or a piece of punctuation-heavy syntax gets split into several.

Useful rules of thumb for English prose:

- One token is roughly four characters.
- 1,000 tokens is roughly 750 words.
- A single-spaced page is very roughly 500 to 700 tokens.

Those rules break down fast outside English prose. Code, JSON, XML, base64, GUIDs, and non-Latin scripts all tokenize far less efficiently, sometimes by a factor of two or more. This is why a payload that looks small can bill like a large one.

> **Why it matters in the field:** never estimate cost from document count or page count. Estimate from the tokenized payload, and measure the real thing before you commit to a number in front of a customer.

## 2. The cost formula

Almost every model API bills on the same shape:

```text
Cost = (input tokens x input rate) + (output tokens x output rate)
```

Three things follow from that:

- **Output is the expensive half.** Output rates are typically several times higher than input rates. Verbosity is a direct cost.
- **Reasoning models add a hidden line.** Models that "think" before answering emit internal reasoning tokens that bill as output even though the user never sees them. A short visible answer can carry a long invisible bill.
- **Rates vary enormously by model.** The spread between a small model and a frontier model is often one to two orders of magnitude. Model choice is usually a bigger lever than prompt tuning.

> **Why it matters in the field:** "make the response shorter" and "use a smaller model for this step" are engineering decisions with a line-item impact. Treat them that way.

## 3. Context is charged every turn

Models are stateless. There is no memory between calls. Whatever the model needs to know has to be sent again on every single request: the system prompt, the retrieved documents, the tool definitions, and the entire conversation so far.

That has an unpleasant consequence. If a chat naively appends every turn to the history, turn 20 pays for turns 1 through 19 all over again. Total spend across a conversation grows quadratically, not linearly, even though the feature looks linear to the user.

Mitigations: summarize older turns, use a sliding window, extract durable facts into a compact memory, or cache the stable prefix.

> **Why it matters in the field:** when a customer says "our AI bill exploded and we did not change anything," this is usually the answer. Usage did not change. Session length did.

## 4. Context window is a ceiling, not a target

A large context window tells you what the model can accept. It does not tell you what you should send. Filling a large window is expensive on every call and often makes output worse, not better: relevant facts get diluted among irrelevant ones, and models are measurably weaker at retrieving information buried in the middle of very long inputs.

The engineering discipline here has a name in the show: context is expensive. Send the smallest set of tokens that reliably produces the right answer.

> **Why it matters in the field:** "we have a million-token window so we will just put everything in the prompt" is one of the most costly architectural decisions a customer can make, and it usually degrades quality at the same time.

## 5. The optimization levers, and what each one costs you

**Prompt caching**
Reuse a stable prompt prefix across many calls so it is not reprocessed every time. Providers typically discount cached input reads heavily.
*Tradeoff:* only works when the prefix is genuinely identical and recent. Any change to the front of the prompt invalidates the cache, so prompt ordering becomes an architectural decision.

**Model routing**
Classify the request, then send it to the cheapest model that can handle it. Escalate only when needed.
*Tradeoff:* you now own a classifier and an escalation path, and a bad routing decision costs more than it saves through retries and rework.

**Retrieval instead of stuffing**
Index the corpus, retrieve the few relevant chunks, and send only those.
*Tradeoff:* you pay for embedding, storage, and retrieval infrastructure, and retrieval quality becomes the ceiling on answer quality.

**Batch processing**
Submit non-urgent work asynchronously. Providers commonly discount batch throughput substantially versus real-time.
*Tradeoff:* latency, measured in minutes to hours. Only viable for work nobody is waiting on.

**Provisioned throughput**
Reserve capacity for predictable, high-volume, latency-sensitive workloads instead of paying per call.
*Tradeoff:* you pay for the reservation whether you use it or not. Only wins above a real utilization threshold.

**Output constraints**
Cap max tokens, request structured output, and stop asking for preamble and restatement.
*Tradeoff:* almost none, which is why it should usually be the first thing you do.

**Small and fine-tuned models**
A smaller model tuned for one narrow task can beat a frontier model on cost by a wide margin.
*Tradeoff:* tuning cost, evaluation burden, model sprawl, and a maintenance commitment.

**Context compression**
Summarize history, prune tool definitions, and compact agent memory.
*Tradeoff:* summarization is lossy. Compress the wrong thing and the agent forgets something it needed.

## 6. Agents multiply everything

An agent is a loop, not a call. A single user request becomes: plan, call a tool, read the result, re-evaluate, call another tool, maybe retry, then answer. Every one of those steps is a fresh model call that re-sends the accumulated context.

The practical effects:

- One user request can quietly become ten to fifty model calls.
- Tool definitions are part of the prompt. Twenty tools is twenty tools of overhead on every step.
- Failed tool calls and retries are billed exactly like successful ones.
- Multi-agent designs multiply again, and agents talking to agents can re-summarize the same context repeatedly.

> **Why it matters in the field:** the per-token price is not the risk in agentic systems. The loop count is. Instrument before you scale.

## 7. Cost per outcome is the only metric that survives

Cost per token is an accounting figure. It tells you nothing about whether the money bought anything. The metric that holds up in front of a CFO is:

**Cost per successfully completed task**

Building that number means defining success, then counting everything: the calls that worked, the calls that failed, the retries, the escalations to a bigger model, and the human time spent cleaning up afterwards.

Once you have the denominator, a lot of arguments resolve themselves. A model that is five times cheaper per token but fails a third of the time and needs a person to fix it is not cheaper. A reasoning model that costs more per call but removes a review step may be dramatically cheaper per outcome.

> **Why it matters in the field:** this is the single most useful reframe you can offer a customer who is anxious about AI spend. Move the conversation from the numerator to the denominator.

## 8. Governance: what good looks like in the first 30 days

- **Attribution.** Every call is tagged to a team, application, and environment. If you cannot attribute it, you cannot govern it.
- **Observability.** Token consumption is tracked like CPU and storage: dashboards, trends, and anomaly detection, not a monthly surprise.
- **Budgets and alerts.** Soft alerts before hard caps. Hard caps exist and someone has tested them.
- **Showback before chargeback.** Show teams what they consume before you bill them for it. Chargeback without a period of showback creates resentment and shadow usage.
- **An evaluation baseline.** You cannot safely optimize cost without a quality baseline to protect. Evaluation is the missing link in most cost programs.
- **A gateway.** A single policy enforcement point for routing, quotas, logging, and data boundaries beats per-application governance every time.

The failure mode to avoid: governance introduced as a blocker. Token economics should accelerate adoption by making it defensible, not slow it down by making it frightening.

## Glossary

| Term | Definition |
| --- | --- |
| **Token** | The unit a model reads and writes, and the unit it bills. Roughly four characters of English text. |
| **Input / prompt tokens** | Everything sent to the model: system prompt, tool definitions, retrieved context, and conversation history. |
| **Output / completion tokens** | Everything the model generates. Typically priced several times higher than input. |
| **Reasoning tokens** | Internal thinking tokens produced by reasoning models. Billed as output, invisible to the user. |
| **Context window** | The maximum number of tokens a model can consider in one call. A ceiling, not a target. |
| **Prompt caching** | Reusing a previously processed prompt prefix at a reduced rate. |
| **Model routing** | Directing each request to the cheapest model capable of handling it. |
| **RAG** | Retrieval-Augmented Generation. Fetch relevant content and include only that, instead of sending the whole corpus. |
| **Batch inference** | Asynchronous processing at a reduced rate, in exchange for latency. |
| **Provisioned throughput** | Reserved model capacity billed on a commitment rather than per call. |
| **Showback** | Reporting consumption back to the team that caused it, without billing them. |
| **Chargeback** | Actually billing consumption back to the consuming team or cost centre. |
| **Cost per outcome** | Total cost of producing one successfully completed task, including failures, retries, and human cleanup. |
| **AI gateway** | A central proxy that enforces routing, quotas, logging, and data boundaries across all model traffic. |

> Rates, discounts, and model capabilities change frequently. Treat this page as the mechanics, not the price list, and verify current numbers before quoting anything to a customer.

