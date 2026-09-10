# TokenOS Reporting — Design and Build Plan

**Status:** proposal, not yet built
**Audience:** whoever implements the reporting surface
**Related:** [ENGINE-DEEP-DIVE.md](./ENGINE-DEEP-DIVE.md) · [TOKENOS-BENEFITS.md](./TOKENOS-BENEFITS.md) · [OPTIMIZATION-API.md](./services/tokenos-api/OPTIMIZATION-API.md)

---

## 1. What this is

A plan for a reporting screen that adopts the *visual language* of a modern AI-consumption dashboard — dark theme, KPI card row, panel grid, sparklines, impact-tagged recommendation cards — while showing only numbers TokenOS can actually stand behind.

The reference design was supplied as a style target. Its navigation taxonomy and several of its panels do not fit this product, so they are deliberately dropped. Section 3 lists exactly what is dropped and why.

---

## 2. The one adaptation that is not negotiable

The reference dashboard puts these four tiles in a single row, at identical visual weight:

| Tile | Claim strength |
|---|---|
| Total tokens | counted |
| Estimated cost | **guessed** |
| Avg tokens/request | counted |
| Est. optimization savings | **guessed** |

TokenOS exists because that row is misleading. The entire product thesis is that a measured cost, a projected cost, and a verified saving are different kinds of statement, and that blending them is how AI spend gets out of control in the first place.

**So: evidence tier becomes the primary visual organising principle of this screen, not an afterthought badge.**

Every number on the screen carries exactly one tier, rendered through the existing shared `EvidenceTier` primitive (which already takes the tier as a *required* argument — good, keep it that way):

| Tier | Meaning | Visual treatment |
|---|---|---|
| **Estimated** | Modelled, no run behind it | Muted text, dashed card border, no fill |
| **Measured — current** | Real usage from the ungoverned path | Solid card, neutral accent |
| **Measured — governed** | Real usage through TokenOS | Solid card, brand accent |
| **Projected at volume** | Measured unit cost × user-stated volume | Dashed border, prints its assumption string inline |
| **Verified saving** | Governed + paired baseline, identical contract, baseline cost more | Solid, `--tos-good`, the only tile allowed to read as money saved |

A tile with no data shows the tier and an em-dash. It does **not** fall back to an estimate. "We haven't measured this yet" is a legitimate and useful thing for the screen to say.

---

## 3. Navigation: what we drop

The reference sidebar carries ten destinations. TokenOS can honestly populate three of them. Building the other seven means inventing panels with nothing behind them — which is the exact failure this product is arguing against.

| Reference nav item | Decision | Reason |
|---|---|---|
| Overview | **Keep** | Becomes the main reporting screen |
| Usage / Costs | **Merge into Overview** | One product, one workload type — they aren't separate screens yet |
| Reports | **Merge into Overview** | Same data, no second view needed |
| Optimizations | **Keep, renamed** | Real, but must be tier-badged (see §6.4) |
| Sources | Drop | No multi-SaaS connector model. Input source is a *filter*, not a screen |
| Users & Teams | Drop | No multi-user model. There is a tenant, not a team roster |
| Models | Drop | Route tier is a panel on Overview, not a destination |
| Forecasting | Drop as a screen | No time-series forecast engine. Projection-at-volume is a panel |
| Alerts | Drop as a screen | Reuse as the governance-events feed panel |
| "Ask TokenLens" assistant | Drop | No such feature; adding a fake CTA is worse than omitting it |

**Resulting shell.** The app today is a single seven-phase journey plus a `HistoryDrawer` overlay ([App.tsx](./apps/web/src/App.tsx)). Reporting introduces the first real need for top-level navigation, so keep it minimal:

```
Workflow   Reports
```

Two items. The history drawer stays where it is and gains a "See all in Reports" link. A ten-item sidebar for a two-destination product is precisely the mismatch flagged in the brief.

---

## 4. Screen layout

Borrowed wholesale from the reference. This part works and should be copied closely.

```
┌────────────────────────────────────────────────────────────────────────┐
│ Reports                          [target ▾] [date range ▾] [Export ▾]  │
│ Measured governance across N runs · price table v2026-01-01            │
├────────────────────────────────────────────────────────────────────────┤
│ ┌────────┐┌────────┐┌────────┐┌────────┐┌────────┐┌ ─ ─ ─ ─┐          │
│ │Verified││Governed││Cost per││ Model  ││Quality ││Projected│  KPI row │
│ │ saving ││ spend  ││outcome ││ calls  ││  pass  ││at volume│  (6)     │
│ │ ▁▃▅▇   ││ ▇▅▃▁   ││ ▃▃▂▁   ││avoided ││ ▇▇▇▇   ││ dashed  │          │
│ └────────┘└────────┘└────────┘└────────┘└────────┘└ ─ ─ ─ ─┘          │
├────────────────────────────────────────────────────────────────────────┤
│ ┌──────────────────┐┌──────────────────┐┌──────────────────┐          │
│ │ Governed vs      ││ Where the work   ││ Projection at    │  3-col    │
│ │ baseline spend   ││ went (donut)     ││ volume           │  panels   │
│ │ (line, over time)││ local/reuse/     ││ (bar + assumption)│          │
│ │                  ││ efficient/adv    ││                  │          │
│ └──────────────────┘└──────────────────┘└──────────────────┘          │
├────────────────────────────────────────────────────────────────────────┤
│ ┌──────────────────────────────┐┌────────────┐┌────────────┐          │
│ │ Recent runs (table +         ││ Spend by   ││ Governance │          │
│ │ inline sparkline)            ││ route tier ││ events     │          │
│ └──────────────────────────────┘└────────────┘└────────────┘          │
├────────────────────────────────────────────────────────────────────────┤
│ ┌────────────┐┌────────────┐┌────────────┐                            │
│ │Opportunity ││Opportunity ││Opportunity │  all badged ESTIMATED       │
│ └────────────┘└────────────┘└────────────┘                            │
└────────────────────────────────────────────────────────────────────────┘
```

**Style notes carried over from the reference:** dark surface with elevated cards, one accent hue per series, generous card padding, small-caps muted labels above large numerals, delta chips (`▲ 12%` / `▼ 4%`) against the previous period, sparkline in every KPI card, `View all →` affordance on each panel header.

**Style notes deliberately *not* carried over:** the reference's uniform card treatment. TokenOS cards are visually differentiated by tier (§2) — dashed borders for anything not measured. This is the main visual departure and it is the point.

---

## 5. Existing assets

Most of the styling already exists.

`tokens.css` is already dark-first (`color-scheme: dark`, `--tos-bg: #0c1220`, `--tos-surface: #151d2e`) with a per-series accent set that maps directly onto the reference's multi-hue charts:

| Token | Value | Chart use |
|---|---|---|
| `--tos-brand` | `#8094ff` | Governed spend |
| `--tos-good` | `#5edba5` | Verified saving, quality pass |
| `--tos-warn` | `#ffc46b` | Escalation, advanced-tier calls |
| `--tos-risk` | `#ff8d87` | Baseline spend, quality failures |
| `--tos-muted` | `#aeb9ca` | Estimated / projected series |

No re-theme required. There is also a light palette under `[data-theme="light"]` that must keep working — every chart colour must come from a token, never a literal hex.

**Charting:** use inline SVG, no charting dependency. The app currently ships no chart library and the required shapes (sparkline, line, donut, horizontal bars) are ~30–60 lines each. This keeps the bundle small and matches the existing dependency-light style. Reassess only if a stacked time-series with brushing is later required.

---

## 6. Panel specification

Every panel below names the field that feeds it. Where a field does not exist yet, it is flagged **[needs backend]** and appears in §7.

### 6.1 KPI row (6 cards)

| # | Card | Source | Tier |
|---|---|---|---|
| 1 | Verified saving | `groups.measured.verifiedSavingsUsd` | Verified saving |
| 2 | Governed model spend | `groups.measured.governedModelSpendUsd` | Measured — governed |
| 3 | Cost per accepted outcome | Σ`modelSpendUsd` ÷ Σ`acceptedOutcomes` **[needs backend]** | Measured — governed |
| 4 | Model calls avoided | `metrics.modelCallsAvoided`, `localOperationRate` | Measured — governed |
| 5 | Quality pass rate | `groups.*.qualityPassRate` ÷ `runCount` **[needs backend]** | Measured — governed |
| 6 | Projected at volume | `groups.projected.valueUsd` | Projected |

Card 1 reads `$0.00` and stays neutral-coloured until at least one baseline-eligible pair exists — it must never imply a saving that has not been earned. Card 6 is dashed-bordered and prints the projection's `assumption` string beneath the value.

Cards 4 and 5 sit deliberately adjacent: *calls avoided* is the saving mechanism and *quality pass* is its guardrail. A cheaper wrong answer is not a saving, and the layout should make that pairing obvious.

### 6.2 Governed vs baseline spend (line, over time)

Two series over daily buckets: governed spend (`--tos-brand`, solid) and baseline spend (`--tos-risk`, dashed). The gap between them *is* the verified saving, shown as a filled band.

Baseline only exists for runs where a paired all-AI baseline was explicitly triggered, so the dashed line is sparse by design. Render gaps as gaps — do not interpolate across days with no baseline. **[needs backend: time bucketing]**

### 6.3 Where the work went (donut)

The reference's "usage by source" donut, repurposed to the routing ladder — which is the more interesting story anyway:

| Segment | Source | Colour |
|---|---|---|
| Handled locally | `cost.localOperations` | `--tos-good` |
| Served from reuse/cache | `cost.reuseOperations` | `--tos-brand` |
| Efficient-tier model | `cost.efficientCalls` | `--tos-warn` |
| Advanced-tier model | `cost.advancedCalls` | `--tos-risk` |

Legend shows percentage and absolute count per segment, matching the reference. This panel answers "did we need a model at all", which is the core claim of the product.

### 6.4 Projection at volume

Replaces the reference's forecasting chart. TokenOS has no time-series forecast engine and inventing one would be dishonest.

What it *does* have is `cost.projection`, which exists only when `recurringVolume` was supplied **and** a per-outcome cost is known. Render as a simple bar (per run/period) with the projection's own `label`, `badge` and `assumption` printed verbatim. Dashed border throughout.

Empty state: "No projection — supply a recurring volume on a run to see cost at scale." Do not substitute an estimate.

### 6.5 Recent runs (table)

Promotes the history drawer's content to a full table. Columns: run ID · workflow · optimization target · proof type · governed spend · cost per outcome · quality · verified saving · inline sparkline. Row click opens the existing proof view.

Filterable by the header's `optimizationTarget` control, which the endpoint already supports.

### 6.6 Spend by route tier (horizontal bars)

`efficientCalls` / `advancedCalls` crossed with the pinned price table. Shows both call count and dollar share — the point being that a small number of advanced-tier calls can dominate spend at the ~16.7× tier multiplier in the shipped price table.

Footer prints the price table version so the numbers are reproducible.

### 6.7 Governance events

The reference's alerts feed, populated from the real event stream already written at [store.py:83](./services/tokenos-api/tokenos_api/optimization/store.py:83). Severity icon + relative timestamp, exactly as the reference.

Event types worth surfacing: budget ceiling reached, escalation to advanced tier, quality gate failed, baseline not eligible (with reason), price table mismatch.

These are genuine governance signals, not synthetic alerts.

### 6.8 Optimization opportunities (cards)

The reference's recommendation cards with HIGH/MEDIUM/LOW impact badges. Keep the format — it is a good format — with one hard rule:

> **Every opportunity card is badged `Estimated` and shows the measured evidence it was derived from.**

Cards are only emitted where measured data supports them, e.g.:

- *"Cache eligibility measured at 40%, actual cached-token rate 5% — enabling reuse could avoid ~N calls."* Derived from `cacheEligibility` vs `measuredCachedTokenRate`.
- *"18% of spend went to advanced tier on runs that passed quality at efficient tier."* Derived from `efficientCalls` / `advancedCalls` / `qualityPassRate`.

The reference's "$127.50 potential per month" donut is **dropped**. A potential-savings donut with no tier marking is the single most misleading element in the source design.

---

## 7. Backend work required

Four gaps, one of which is a live bug.

### 7.1 Bug: rate metrics are summed, never averaged

At [engine.py:1143–1146](./services/tokenos-api/tokenos_api/optimization/engine.py:1143):

```python
for key in ("contextMinimizationRate", "measuredCachedTokenRate",
            "measuredInputTokenReduction", "costPerAcceptedOutcomeUsd",
            "qualityPassRate", "escalationRate"):
    value = metrics.get(key)
    if isinstance(value, (int, float)):
        group[key] += float(value)
```

These accumulate and are never divided by `runCount`. Over 10 runs, `qualityPassRate` returns ~10.0. Rendered as a percentage that is 1000%.

**Fix:** return `{sum, count, mean}` per metric rather than dividing in place, so callers can re-aggregate correctly and the wire format stays explicit.

**Separately, `costPerAcceptedOutcomeUsd` must not be a mean of means.** The correct aggregate is Σ`modelSpendUsd` ÷ Σ`acceptedOutcomes`. Averaging per-run averages weights a 1-outcome run equally with a 500-outcome run and will misstate unit economics.

### 7.2 No time dimension

`reports()` returns `run["proof"]` rows only ([engine.py:1117](./services/tokenos-api/tokenos_api/optimization/engine.py:1117)), which drops the run's `createdAt`. Every sparkline, trend line and period-over-period delta needs it.

The timestamp does exist — `createdAt` is set at run creation and persisted as its own SQLite column ([store.py:63](./services/tokenos-api/tokenos_api/optimization/store.py:63)) — so this is plumbing, not new capture.

**Add:** `from` / `to` / `bucket=day|week` params; attach `createdAt` to each row; return a `series` array of per-bucket aggregates.

### 7.3 No period-over-period comparison

The reference's delta chips need a previous-period aggregate. Once §7.2 lands, compute the immediately preceding window of equal length and return it as `previous` alongside `groups`.

### 7.4 No export

The header Export control needs CSV and JSON. Per-proof raw JSON already exists; this is the aggregate equivalent. Small.

---

## 8. Build phases

Sequenced so it can stop after any phase and still be shippable.

**Phase 1 — Truthful foundation.** Fix §7.1. Add time bucketing (§7.2). Add the shell nav and the Reports route. Build `StatCard`, `Sparkline`, `Panel` and wire the KPI row. *Stops here = a correct, honest six-tile summary.*

**Phase 2 — The panel grid.** Trend line, routing donut, projection panel, recent-runs table, route-tier bars, governance events. Adds §7.3 deltas and §7.4 export. *Stops here = the reference layout, fully populated.*

**Phase 3 — Opportunities.** The §6.8 cards and their derivation rules. Deliberately last: it is the highest-risk surface for overclaiming and benefits from the measured panels existing first.

---

## 9. Test plan

Matching the project's existing harnesses.

| Layer | Coverage | Harness |
|---|---|---|
| Unit | Aggregation maths — especially the §7.1 mean-vs-sum fix and Σ/Σ cost-per-outcome; bucket boundaries; empty-set behaviour | service `.venv`, `pytest` |
| API | New params (`from`/`to`/`bucket`), existing filters still honoured, `previous` window correctness, export shapes | `pytest` |
| Visual regression | Full Reports screen, dark **and** light themes, empty state, single-run state | system Python, `pytest -c pytest-browser.ini` |
| Accessibility | Charts have text alternatives; tier is conveyed by label not colour alone; `:focus-visible` intact across new controls | browser harness |

**A dedicated tier test.** Assert that no tile renders a value without a tier, and that `verifiedSavingsUsd` renders as `$0.00`/neutral when no baseline-eligible pair exists. This is the invariant most likely to regress and it is the one that matters most.

**Colour-blind safety.** The reference leans hard on hue to distinguish series. Segments must also differ by pattern or direct label — the routing donut in particular.

---

## 10. Open questions

1. **Placement.** Reports as a top-level peer of the workflow journey (assumed above), or a section within Prove? Top-level assumed because reporting spans runs and Prove is per-run.
2. **Default range.** The reference defaults to 7 days. With a low run count, 7 days may render mostly empty — "all time" may be the better default until volume justifies otherwise.
3. **Scope of the recent-runs table** vs the existing history drawer — full replacement, or does the drawer stay as the quick-access affordance? Assumed: drawer stays, table is the fuller view.
4. **Multi-tenant.** Everything above is single-tenant. If a tenant selector is ever needed the header has room, but no work is planned for it here.
