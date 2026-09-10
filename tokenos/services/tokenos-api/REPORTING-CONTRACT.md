# Reporting API contract (frozen)

Both the backend and the frontend build to this document. If an implementation needs
to deviate, change this file first and say so in the final report.

Companion to [REPORTING-PLAN.md](../../REPORTING-PLAN.md). Endpoint lives alongside the
existing optimization routes in `tokenos_api/optimization/router.py`.

---

## 1. `GET /api/optimization/reports`

### Query parameters

| Param | Type | Default | Notes |
|---|---|---|---|
| `proofType` | `measured` \| `sample` \| `projected` | none | Existing. Filters the `runs` array only, never `groups` |
| `application` | string | none | Existing |
| `optimizationTarget` | `current_workflow` \| `single_prompt` \| `measured_workflow` | none | Existing. 422 on any other value |
| `limit` | int | 200 | Existing. Clamped 1–1000 |
| `from` | ISO 8601 datetime | none | **New.** Inclusive lower bound on run `createdAt` |
| `to` | ISO 8601 datetime | none | **New.** Exclusive upper bound |
| `bucket` | `day` \| `week` | `day` | **New.** 422 on any other value |

`from`/`to` must be timezone-qualified. A naive datetime is a 422 with a message naming
the parameter — consistent with how `imports.py` already rejects naive telemetry timestamps.

### Response

```jsonc
{
  "range": { "from": "2026-01-01T00:00:00+00:00", "to": "2026-01-08T00:00:00+00:00", "bucket": "day" },
  "priceTableVersions": ["2026-01-01"],

  "groups": {
    "measured":  { /* Aggregate, see §1.1 */ },
    "sample":    { /* Aggregate */ },
    "projected": {
      "valueUsd": 12.5,
      "projectionCount": 2,
      "byPeriodAndSource": { "measured:month": 12.5 }
    }
  },

  "previous": {
    "measured":  { /* Aggregate for the immediately preceding window of equal length */ },
    "sample":    { /* Aggregate */ },
    "projected": { "valueUsd": 0.0, "projectionCount": 0, "byPeriodAndSource": {} }
  },

  "series": [
    {
      "bucket": "2026-01-01",
      "measured":  { /* Aggregate */ },
      "sample":    { /* Aggregate */ },
      "projected": { "valueUsd": 0.0, "projectionCount": 0, "byPeriodAndSource": {} }
    }
  ],

  "routeTiers": [ /* §1.2 */ ],
  "events":     [ /* §1.3 */ ],
  "opportunities": [ /* §1.4 */ ],

  "runs": [ /* existing proof objects, each additionally carrying runId + createdAt */ ]
}
```

`previous` is `null` when neither `from` nor `to` was supplied (no window means no
preceding window). `series` is `[]` when there are no runs in range.

### 1.1 Aggregate object

Used identically in `groups.measured`, `groups.sample`, `previous.*`, and every `series[].*`.

```jsonc
{
  "runCount": 12,

  "modelSpendUsd": 0.0123,           // governed + baseline, matches existing behaviour
  "governedModelSpendUsd": 0.0061,
  "baselineModelSpendUsd": 0.0062,
  "verifiedSavingsUsd": 0.0065,      // only from baseline.eligible runs

  "acceptedOutcomes": 240,
  "modelCalls": 18,
  "localOperations": 42,
  "reuseOperations": 7,
  "efficientCalls": 15,
  "advancedCalls": 3,
  "modelCallsAvoided": 9,

  "costPerAcceptedOutcomeUsd": 0.0000254,   // TRUE RATIO, see below. null when acceptedOutcomes == 0

  "rates": {
    "contextMinimizationRate":    { "sum": 4.2, "count": 6, "mean": 0.7 },
    "measuredCachedTokenRate":    { "sum": 0.3, "count": 6, "mean": 0.05 },
    "measuredInputTokenReduction":{ "sum": 900, "count": 3, "mean": 300 },
    "qualityPassRate":            { "sum": 5.4, "count": 6, "mean": 0.9 },
    "escalationRate":             { "sum": 0.6, "count": 6, "mean": 0.1 },
    "localOperationRate":         { "sum": 4.8, "count": 6, "mean": 0.8 }
  }
}
```

**Two correctness rules that are the whole reason this endpoint is being changed:**

1. **`rates.*` returns `{sum, count, mean}`, never a bare running total.** The current code at
   `engine.py:1143` accumulates into a scalar and never divides, so `qualityPassRate` across
   10 runs returns ~10.0. `count` counts only runs where the metric was a real number —
   `None` and missing values are skipped and must not inflate the denominator. `mean` is
   `null` when `count` is 0.

2. **`costPerAcceptedOutcomeUsd` is `Σ modelSpendUsd ÷ Σ acceptedOutcomes`**, not the mean
   of per-run `costPerAcceptedOutcomeUsd`. A mean of means weights a 1-outcome run equally
   with a 500-outcome run and misstates unit economics. Use the governed spend numerator
   (`governedModelSpendUsd`), not the governed+baseline total.

### 1.2 `routeTiers`

Fixed four entries, always present in this order, zeros rather than omission:

```jsonc
[
  { "tier": "local",     "label": "Handled locally",    "operations": 42, "calls": 0,  "spendUsd": 0.0 },
  { "tier": "reuse",     "label": "Served from reuse",  "operations": 7,  "calls": 0,  "spendUsd": 0.0 },
  { "tier": "efficient", "label": "Efficient model",    "operations": 0,  "calls": 15, "spendUsd": 0.0021 },
  { "tier": "advanced",  "label": "Advanced model",     "operations": 0,  "calls": 3,  "spendUsd": 0.0040 }
]
```

`spendUsd` is `null` — not `0.0` — where per-tier attribution is not derivable from the
runs in range. A null means "not measured"; a zero means "measured as free".

### 1.3 `events`

Newest first, capped at 50. Sourced from the existing event stream.

```jsonc
{
  "runId": "run_...",
  "at": "2026-01-03T09:12:44+00:00",
  "type": "cost.authorized",
  "severity": "info" | "warning" | "risk",
  "message": "Authorized ceiling $1.00"
}
```

Only these types surface, mapped to severity:

| Type | Severity |
|---|---|
| `cost.authorized` | `info` |
| `baseline.completed` | `info` |
| `route.selected` (advanced tier) | `warning` |
| `quality.result` with `passed: false` | `risk` |
| `run.blocked`, `run.failed` | `risk` |

### 1.4 `opportunities`

Derived only from measured runs. Empty array when nothing is derivable — **never** a
placeholder or a guess.

```jsonc
{
  "id": "cache-gap",
  "title": "Reuse is eligible but not being used",
  "impact": "high" | "medium" | "low",
  "tier": "estimated",                        // ALWAYS "estimated". No other value is valid.
  "evidence": "Cache eligibility measured at 40%, actual cached-token rate 5%.",
  "derivedFrom": ["metrics.cacheEligibility", "metrics.measuredCachedTokenRate"],
  "estimatedSavingUsd": 0.0012                // nullable
}
```

Ship exactly these three rules:

| `id` | Fires when | Impact |
|---|---|---|
| `cache-gap` | `cacheEligibility` is eligible and `measuredCachedTokenRate.mean` < 0.25 | `high` if gap > 0.5, else `medium` |
| `advanced-tier-share` | `advancedCalls` > 0 and `rates.qualityPassRate.mean` >= 0.9 | `high` if advanced spend share > 0.5, else `medium` |
| `context-headroom` | `contextMinimizationRate.mean` < 0.3 and `runCount` >= 3 | `low` |

---

## 2. `GET /api/optimization/reports/export`

Same filters as §1 plus `format`.

| Param | Values | Default |
|---|---|---|
| `format` | `json` \| `csv` | `json` |

- `json` → the complete §1 body, `Content-Disposition: attachment`.
- `csv` → one row per run. Columns, in order:
  `runId, createdAt, application, environment, optimizationTarget, proofType, priceTableVersion,
   governedModelSpendUsd, baselineModelSpendUsd, verifiedSavingUsd, acceptedOutcomes,
   costPerAcceptedOutcomeUsd, modelCalls, localOperations, reuseOperations, qualityPassRate, escalationRate`

CSV values that are `None` render as an empty field, not the string `None`. Any value
containing a comma, quote or newline is quoted per RFC 4180 — use the `csv` module, not
manual string joining.

---

## 3. Frontend contract notes

- **Evidence tier is required on every rendered value.** Reuse the existing shared
  `EvidenceTier` primitive (it already takes tier as a required argument — keep it that way).
  Map: `groups.measured` → *Measured — governed*, `groups.sample` → *Estimated*,
  `groups.projected` → *Projected at volume*, `verifiedSavingsUsd` → *Verified saving*.
- **`verifiedSavingsUsd` of `0` renders neutral, never green, never as an achievement.**
  Green is reserved for a value earned by a baseline-eligible pair.
- **`null` renders as an em-dash plus the tier**, never as `0`, and never falls back to an
  estimate. "Not measured yet" is a legitimate thing for the screen to say.
- **All chart colours come from CSS custom properties**, never literal hex, so the existing
  `[data-theme="light"]` palette keeps working.
- Charts are **inline SVG**. Do not add a charting dependency; the app currently ships none
  and the required shapes are small.
