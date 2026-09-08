# Why TokenOS is essential to tokenomics

A benefits summary for stakeholders, evaluators, and decision-makers. For how it works, see
the [engine deep dive](ENGINE-DEEP-DIVE.md); for the product tour, see the [README](README.md).

Every number below comes from a file already in this repository — the shipped price table, a
real recorded governance event, or the bundled demo walkthrough. This document does not use a
figure TokenOS itself would refuse to show — that consistency is the point, and it is also the
entire financial argument: **a savings claim that can't survive this level of scrutiny is not a
savings claim.**

---

## The problem, stated as a cost problem

Generative AI has a simple, expensive default: **when in doubt, call the model — and call the
best one you have.** Teams that adopt AI quickly route everything through it, at whatever tier
is easiest to wire up, because writing deterministic software to answer correctly takes more
effort than writing one prompt. Two costs compound from that default:

1. **Volume cost** — routine, rule-based, or repeated work is billed at model prices when it
   didn't need a model at all.
2. **Tier cost** — work that does need a model is frequently sent straight to the most capable
   (and most expensive) deployment, instead of trying a cheaper tier first.

Both are avoidable, and both are quantifiable from the same price table any Azure AI Foundry
deployment already uses. TokenOS is built to avoid both, and to prove — in dollars, from
provider-measured usage — how much it avoided.

---

## Financial and cost-savings benefits

### 1. A real, price-table-quantified reason to route down a tier

TokenOS ships with `price_table.json`, containing public list prices for its efficient and
advanced deployment tiers:

| Tier | Input, per 1M tokens | Output, per 1M tokens |
| --- | ---: | ---: |
| `tokenos-efficient` (gpt-4o-mini class) | $0.15 | $0.60 |
| `tokenos-advanced` (gpt-4o class) | $2.50 | $10.00 |

**The advanced tier costs ~16.7× the efficient tier, on both input and output, at the prices
already configured in this repository.** Every operation TokenOS resolves at the efficient tier
instead of advanced avoids that multiplier outright. Every operation it resolves with zero model
tokens (hashing, table parsing, arithmetic, keyed lookup, exact rule matching) avoids 100% of
model spend on that operation. The routing ladder tries local software, then the efficient tier,
then the advanced tier — in that order, never the reverse — precisely because that ordering is
where the money is.

*(Confirm these figures against your own Azure agreement, region, and commitment tier before
treating them as your real cost — the price table file says so explicitly, and TokenOS enforces
the same rule: prices must be pinned and dated before any cost is calculated from them.)*

### 2. `costPerAcceptedOutcomeUsd` — the one metric that can't be gamed

The cheapest way to make an AI pipeline look financially efficient is to make it answer faster
and reject more. TokenOS's headline cost metric is not total spend, and not spend-per-call — it
is **cost per accepted outcome**: total measured model spend divided by requests that actually
passed verification. An answer that failed the quality gate is not in the denominator. This
means a cost figure cannot be improved by quietly answering worse, only by genuinely needing less
model help to answer correctly.

### 3. Hard spend ceilings enforced *before* the money is spent, not reconciled after

Every run carries an explicit, human-authorized budget ceiling checked at Protect, before any
model call is placed. From the bundled demonstration walkthrough (`document_review`, real local
run):

> *"The authorized budget was one dollar, but the measured call cost was two ten-thousandths of
> a dollar."* — **$1.00 ceiling, $0.0002 actual spend.**

That is not a rounding curiosity — it is the financial control model: a budget owner sets a hard
ceiling once, and every run under it is refused before overspend rather than flagged after. No
retries, no escalation, and no baseline comparison can spend a cent past that ceiling, because
the check runs before the first call, not after the last one.

### 4. A real, reproducible worked example of a verified saving

From the same bundled walkthrough, after the paired all-AI baseline was explicitly authorized and
executed:

| Figure | Value | Source |
| --- | ---: | --- |
| Measured governed cost | $0.0002 | Actual provider usage × pinned price table |
| Verified saving (per run) | $0.0065 | `POST /api/runs/{id}/baseline`, same inputs/contract/quality gates |
| Implied baseline cost | ≈ $0.0067 | Governed cost + verified saving |
| Cost multiplier avoided | ≈ 33× | Baseline cost ÷ governed cost |

This is a **sample walkthrough** — reproducible on demand, not evidence of any customer's real
spend — and it is labelled that way everywhere it appears (`proofType: "sample"`). What makes it
useful financially is that the *mechanism* generating a 33× figure here is the identical
mechanism that would generate a real customer's number: measured tokens, the pinned price table,
and a baseline that actually ran and actually cost more.

### 5. Projected cost at volume — a CFO-usable number that never masquerades as fact

Every workflow accepts a `recurringVolume` (for example, *10,000 requests / month*, or
*5,000 / day, week, month, year*). Once a per-outcome cost is measured, TokenOS multiplies it out
to a volume projection — the number a budget owner actually wants — but renders it with its own
label, badge, and assumption string, so it can never be mistaken for a measurement:

> **Projected cost at volume** — extrapolated from one measured per-outcome cost. *Not a saving,
> not a measurement of future spend.*

This is the same discipline applied in the other direction: TokenOS will hand you a monthly or
annual number, but it will not let that number borrow the credibility of "measured" or "verified."

### 6. Price-table pinning protects the financial claim itself, not just the run

The price table used by a run is hashed into that run's contract at planning time
(`priceTableVersion`, a version string *and* a content digest). If prices change mid-run, the
safeguard check fails the run rather than silently re-pricing it. This cuts both ways
financially: a verified saving from three months ago cannot be inflated by a since-lowered price,
and it cannot be quietly deflated by a since-raised one either. **The dollar figure a stakeholder
saw is the dollar figure that stays true**, regardless of what the price table says today.

### 7. Escalation is a cost event with a cause, not a default

The advanced tier — the expensive one — is only reached after the efficient tier's answer fails
independent verification, and only up to an explicit, pre-authorized call limit. Every escalation
is a recorded, causally-explained event (`why_ai`), not a standing default. Financially, this
means the ~16.7× tier multiplier from benefit 1 is paid only when evidence justified it, and the
audit trail proves that on a per-call basis.

### 8. Portfolio-level financial reporting, not just single-run numbers

`/api/optimization/reports` aggregates across runs and returns, among other fields:
`costPerAcceptedOutcomeUsd`, `verifiedSavingsUsd`, `measuredInputTokenReduction`,
`contextMinimizationRate`, `measuredCachedTokenRate`, and `escalationRate` — with measured,
projected, and sample runs kept in **separate columns**, never blended into one average that
would hide which figures are real. A finance stakeholder can ask "what did we actually verify we
saved this month?" and get an answer that excludes projections and sample runs by construction.

---

## Seven more benefits, each backed by an enforced mechanism

### 1. It removes AI spend that was never necessary

Most of the routing ladder resolves work at **zero model tokens**: SHA-256 duplicate detection,
Markdown-table charge parsing, exact dollar/percentage policy limits, allowlisted arithmetic
test validation, keyed document lookup. A model is invoked only for the residue — text that
genuinely requires interpretation.

**Measured evidence already in this repository** (local-mode runs, see [`README.md`](README.md)):

| Workflow | What ran | Model calls | Time |
| --- | --- | ---: | ---: |
| Review documents against rules | 2 findings: charges over their applicable limit | 0–2 | ~35 ms |
| Test a code change | 3 tests run, 1 failed, 1 schema mismatch, reported honestly | 0–2 | ~220 ms |
| Process records by a deadline | 9,989 valid records processed, 11 invalid reported, deadline met | 0–1 | ~110 ms |

Nearly ten thousand records processed with zero model calls, because the work was arithmetic
and schema validation — not interpretation. At any non-trivial price per record, that is the
largest lever in this document: work that never reaches the price table at all.

### 2. Every dollar it does spend is measured, not guessed

A model call is priced from **provider-reported usage**, not a token estimate.
`strict_usage=True` rejects any response with missing or malformed token counts rather than
inferring them, and every usage row carries a `providerRequestId` so the charge is traceable
back to the exact call that produced it. Estimated figures — used only before execution — are
labelled `Estimated` and are never substituted for a measured number once a call has actually run.

From a real recorded governance record:

```json
{
  "operation": "resolve_ambiguous_line_item",
  "tier": "efficient",
  "reason": "Deterministic rule could not settle Section 4.2 overtime exception.",
  "tokens": { "prompt": 1766, "completion": 211, "total": 1977 },
  "measured_cost_usd": 0.000261,
  "quality_verification": "Passed: Section 4.2 citation verified with exact line match."
}
```

### 3. It escalates spend only in response to a proven failure, never as a guess

The cheapest capable model route runs first. Only if the answer **fails independent
verification** — a missing citation, a wrong contract, a failed test — does TokenOS retry on a
more capable, more expensive route, and only up to an explicit, pre-authorized call limit. This
means the expensive path is a *reaction to evidence*, never a hedge purchased up front "just in
case." Escalation, its trigger, and its outcome are all recorded as separate audit events.

### 4. It never spends before a human explicitly authorizes it

No model call — efficient, advanced, or baseline — can occur until an explicit Protect
authorization records `authorizeModelCost: true` alongside a hard spend ceiling. Ten separate
safeguards (budget, data-handling policy, human approval, registered scope, price-table
freshness, and more) must all pass first; any failure blocks the run rather than letting it
proceed and fail expensively partway through.

### 5. It refuses to call a "cheaper wrong answer" a saving

This is the rule most cost-optimization tools skip, and it is the one enforced hardest here.
A saving is claimed **only** when all of the following hold simultaneously:

- the governed run **and** an explicitly-requested all-AI baseline both actually completed,
- both **passed every quality gate** — a faster wrong answer never counts,
- both answered the **same number of requests**, under a **byte-identical contract** (same
  inputs, output schema, maximum output length, verifier version, price table version),
- every usage row on both sides carries a real provider request ID,
- and the baseline **genuinely cost more**.

Fail any one of these and TokenOS reports `No valid comparison` or `No cost saving verified` —
never a number. This is a strict superset of "the governed run was cheap"; it is "the governed
run was cheap **and correct**, and the more expensive alternative was also correct **and** more
expensive."

### 6. It keeps every claim honestly labelled by evidence strength

Five distinct labels, never interchanged:

| Label | What it actually means |
| --- | --- |
| **Estimated** | Computed locally before execution. Nothing has been measured yet. |
| **Measured current cost** | Priced from imported provider usage against the pinned price table. |
| **Measured governed cost** | Priced from actual provider usage of the run that just executed. |
| **Projected cost at volume** | An extrapolation from a measured per-outcome cost. Explicitly *not* a saving. |
| **Verified saving** | Passed the full gate in benefit 5, above. |

The UI enforces this at the component level: a shared `EvidenceTier` primitive takes the tier as
a required argument, so no view can accidentally render an estimate with the visual weight of a
measurement.

### 7. It prices against a version-pinned table, so past claims can't be revised by future price changes

Covered in financial detail in benefit 6 above; restated here because it is also, simply, a
correctness guarantee: the price table used for a run is deep-copied and hashed into that run's
execution contract at plan time, so a verified saving from three months ago stays verified
against the prices that were actually in effect, not whatever is configured today.

---

## What this buys, concretely, in dollars and controls

| Stakeholder | What TokenOS gives them |
| --- | --- |
| **Finance / budget owner** | A per-run spend ceiling enforced *before* the call, a cost-per-accepted-outcome figure that can't be gamed by cheap failures, and a volume projection clearly separated from a verified number. |
| **Engineering** | A routing decision and its exact reason for every operation — never a black-box "the model handled it," and never an advanced-tier call without a documented failure that justified it. |
| **Compliance / audit** | An immutable record per model call: what was sent, what came back, what it cost, and whether it passed verification — reconcilable against the exact price table version in effect at the time. |
| **Product / decision-makers** | A savings number that can be re-derived from the same evidence a skeptic would ask for — because it's the same evidence TokenOS itself required before showing the number. |
| **End users** | The same or better answer quality, because cost reduction is gated on passing the same acceptance checks, not a separate concern. |

---

## Why this matters specifically for *tokenomics*

"Tokenomics" here means the economics of AI token consumption: what gets spent, on what, and
whether the spend was worth it. Three properties make TokenOS structural to that problem rather
than cosmetic:

1. **It changes the default.** The system asks "does this need a model at all, and if so, the
   cheap tier or the expensive one?" *before* it asks "which model?" — inverting the usual
   all-AI, best-tier-first default that drives runaway token spend.
2. **It makes savings falsifiable, in dollars.** A saving that cannot be independently re-run and
   priced is a marketing number. TokenOS's savings claim requires the harder, more expensive path
   to actually execute, actually get priced from the same table, and actually lose — which means
   the claim can be disproven if it's wrong, and therefore means something in a budget review
   when it isn't.
3. **It decouples cost reduction from quality risk.** The single easiest way to cut AI cost is to
   quietly accept worse answers. TokenOS makes that financially invisible to try, because the
   only cost figure it publishes — cost per *accepted* outcome — already excludes anything that
   failed the same quality bar the expensive path had to clear.

---

## What it is not claiming

Consistent with everything above, some limits are stated plainly rather than left implicit:

- This is a **local, single-tenant prototype**, not a production multi-tenant deployment.
- **Zero model tokens is not zero total cost.** Local execution still consumes compute and
  operational effort; TokenOS never claims otherwise.
- **The shipped price table is a public list-price example**, not a negotiated rate. Confirm your
  own agreement, region, and commitment tier before treating any figure in this document — the
  16.7× tier multiplier included — as your real cost.
- **Prompt token estimates are estimates**, not provider-exact tokenizer counts, and are always
  labelled as such.
- **Sample fixtures are reproducible examples**, not evidence of a customer's actual spend —
  they are tagged `proofType: "sample"` and badged accordingly everywhere they appear, including
  the $0.0065 walkthrough figure cited above.
- A verified saving describes **one governed run against one matched baseline run**, not a
  guaranteed result for every future run at every volume; recurring-volume figures are labelled
  `Projected`, explicitly not a saving, until they too are backed by repeated measurement.

---

## The one-sentence pitch

**TokenOS doesn't make AI cheaper by asking it to try harder — it makes AI cheaper by asking,
for every single step, whether AI needed to answer at all and which tier it actually needed, and
it will not tell you a dollar figure in savings unless it can show you the more expensive run
that actually happened, was priced from the same table, and actually lost.**
