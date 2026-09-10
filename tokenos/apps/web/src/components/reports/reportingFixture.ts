import type { ReportAggregate, ReportRate, ReportResponse } from "../../api/types";

const rate = (sum: number, count: number): ReportRate => ({
  sum,
  count,
  mean: count === 0 ? null : sum / count
});

const aggregate = (overrides: Partial<ReportAggregate> = {}): ReportAggregate => {
  const base: ReportAggregate = {
    runCount: 6,
    modelSpendUsd: 0.026,
    governedModelSpendUsd: 0.009,
    baselineModelSpendUsd: 0.017,
    verifiedSavingsUsd: 0.008,
    acceptedOutcomes: 150,
    modelCalls: 18,
    localOperations: 42,
    reuseOperations: 13,
    efficientCalls: 15,
    advancedCalls: 3,
    modelCallsAvoided: 22,
    costPerAcceptedOutcomeUsd: 0.009 / 150,
    rates: {
      contextMinimizationRate: rate(3.9, 6),
      measuredCachedTokenRate: rate(1.4, 6),
      measuredInputTokenReduction: rate(0.72, 6),
      qualityPassRate: rate(5.6, 6),
      escalationRate: rate(0.5, 6),
      localOperationRate: rate(4.4, 6)
    }
  };
  const merged = { ...base, ...overrides };
  return {
    ...merged,
    costPerAcceptedOutcomeUsd:
      merged.acceptedOutcomes === 0
        ? null
        : merged.governedModelSpendUsd / merged.acceptedOutcomes
  };
};

export const reportingFixture: ReportResponse = {
  range: {
    from: "2026-01-01T00:00:00+00:00",
    to: "2026-01-08T00:00:00+00:00",
    bucket: "day"
  },
  priceTableVersions: ["2026-01-01"],
  groups: {
    measured: aggregate(),
    sample: aggregate({
      runCount: 2,
      modelSpendUsd: 0.004,
      governedModelSpendUsd: 0.004,
      baselineModelSpendUsd: 0,
      verifiedSavingsUsd: 0,
      acceptedOutcomes: 40,
      modelCalls: 8,
      localOperations: 10,
      reuseOperations: 4,
      efficientCalls: 7,
      advancedCalls: 1,
      modelCallsAvoided: 4,
      rates: {
        contextMinimizationRate: rate(1.1, 2),
        measuredCachedTokenRate: rate(0.3, 2),
        measuredInputTokenReduction: rate(0.22, 2),
        qualityPassRate: rate(1.8, 2),
        escalationRate: rate(0.2, 2),
        localOperationRate: rate(1.2, 2)
      }
    }),
    projected: {
      valueUsd: 42.5,
      projectionCount: 2,
      byPeriodAndSource: {
        "measured:week": 9.8,
        "measured:month": 42.5
      }
    }
  },
  previous: {
    measured: aggregate({
      runCount: 4,
      modelSpendUsd: 0.029,
      governedModelSpendUsd: 0.012,
      baselineModelSpendUsd: 0.017,
      verifiedSavingsUsd: 0.005,
      acceptedOutcomes: 90,
      modelCalls: 16,
      localOperations: 24,
      reuseOperations: 7,
      efficientCalls: 13,
      advancedCalls: 3,
      modelCallsAvoided: 12,
      rates: {
        contextMinimizationRate: rate(2, 4),
        measuredCachedTokenRate: rate(0.6, 4),
        measuredInputTokenReduction: rate(0.34, 4),
        qualityPassRate: rate(3.4, 4),
        escalationRate: rate(0.7, 4),
        localOperationRate: rate(2.7, 4)
      }
    }),
    sample: aggregate({
      runCount: 1,
      modelSpendUsd: 0.003,
      governedModelSpendUsd: 0.003,
      baselineModelSpendUsd: 0,
      verifiedSavingsUsd: 0,
      acceptedOutcomes: 25,
      rates: {
        contextMinimizationRate: rate(0.5, 1),
        measuredCachedTokenRate: rate(0.1, 1),
        measuredInputTokenReduction: rate(0.1, 1),
        qualityPassRate: rate(0.9, 1),
        escalationRate: rate(0.1, 1),
        localOperationRate: rate(0.6, 1)
      }
    }),
    projected: {
      valueUsd: 25,
      projectionCount: 1,
      byPeriodAndSource: { "measured:month": 25 }
    }
  },
  series: [
    {
      bucket: "2026-01-01",
      measured: aggregate({
        runCount: 1,
        governedModelSpendUsd: 0.0015,
        baselineModelSpendUsd: 0.0024,
        verifiedSavingsUsd: 0.0009,
        acceptedOutcomes: 24
      }),
      sample: aggregate({ runCount: 0, governedModelSpendUsd: 0, acceptedOutcomes: 0 }),
      projected: { valueUsd: 0, projectionCount: 0, byPeriodAndSource: {} }
    },
    {
      bucket: "2026-01-02",
      measured: aggregate({
        runCount: 1,
        governedModelSpendUsd: 0.0012,
        baselineModelSpendUsd: 0,
        verifiedSavingsUsd: 0,
        acceptedOutcomes: 20
      }),
      sample: aggregate({ runCount: 0, governedModelSpendUsd: 0, acceptedOutcomes: 0 }),
      projected: { valueUsd: 0, projectionCount: 0, byPeriodAndSource: {} }
    },
    {
      bucket: "2026-01-03",
      measured: aggregate({
        runCount: 1,
        governedModelSpendUsd: 0.0019,
        baselineModelSpendUsd: 0.0031,
        verifiedSavingsUsd: 0.0012,
        acceptedOutcomes: 30
      }),
      sample: aggregate({ runCount: 1, governedModelSpendUsd: 0.0011, acceptedOutcomes: 12 }),
      projected: { valueUsd: 9.8, projectionCount: 1, byPeriodAndSource: { "measured:week": 9.8 } }
    },
    {
      bucket: "2026-01-04",
      measured: aggregate({
        runCount: 1,
        governedModelSpendUsd: 0.0014,
        baselineModelSpendUsd: 0.0021,
        verifiedSavingsUsd: 0.0007,
        acceptedOutcomes: 22
      }),
      sample: aggregate({ runCount: 0, governedModelSpendUsd: 0, acceptedOutcomes: 0 }),
      projected: { valueUsd: 0, projectionCount: 0, byPeriodAndSource: {} }
    },
    {
      bucket: "2026-01-05",
      measured: aggregate({
        runCount: 1,
        governedModelSpendUsd: 0.0018,
        baselineModelSpendUsd: 0.003,
        verifiedSavingsUsd: 0.0012,
        acceptedOutcomes: 28
      }),
      sample: aggregate({ runCount: 0, governedModelSpendUsd: 0, acceptedOutcomes: 0 }),
      projected: { valueUsd: 0, projectionCount: 0, byPeriodAndSource: {} }
    },
    {
      bucket: "2026-01-06",
      measured: aggregate({
        runCount: 1,
        governedModelSpendUsd: 0.0017,
        baselineModelSpendUsd: 0.0028,
        verifiedSavingsUsd: 0.0011,
        acceptedOutcomes: 26
      }),
      sample: aggregate({ runCount: 1, governedModelSpendUsd: 0.0029, acceptedOutcomes: 28 }),
      projected: { valueUsd: 42.5, projectionCount: 1, byPeriodAndSource: { "measured:month": 42.5 } }
    }
  ],
  routeTiers: [
    { tier: "local", label: "Handled locally", operations: 42, calls: 0, spendUsd: 0 },
    { tier: "reuse", label: "Served from reuse", operations: 13, calls: 0, spendUsd: 0 },
    { tier: "efficient", label: "Efficient model", operations: 0, calls: 15, spendUsd: 0.003 },
    { tier: "advanced", label: "Advanced model", operations: 0, calls: 3, spendUsd: 0.006 }
  ],
  events: [
    {
      runId: "run_fixture_006",
      at: "2026-01-06T14:40:00+00:00",
      type: "quality.result",
      severity: "risk",
      message: "Quality gate failed on one advanced escalation."
    },
    {
      runId: "run_fixture_005",
      at: "2026-01-05T17:10:00+00:00",
      type: "route.selected",
      severity: "warning",
      message: "Advanced tier selected after efficient answer missed citation density."
    },
    {
      runId: "run_fixture_004",
      at: "2026-01-04T08:20:00+00:00",
      type: "baseline.completed",
      severity: "info",
      message: "Baseline comparison completed with equal quality."
    }
  ],
  opportunities: [
    {
      id: "cache-gap",
      title: "Reuse is eligible but not being used",
      impact: "medium",
      tier: "estimated",
      evidence: "Cache eligibility measured at 40%, actual cached-token rate 23%.",
      derivedFrom: ["metrics.cacheEligibility", "metrics.measuredCachedTokenRate"],
      estimatedSavingUsd: 0.0012
    },
    {
      id: "advanced-tier-share",
      title: "Advanced tier is carrying avoidable spend",
      impact: "medium",
      tier: "estimated",
      evidence: "Advanced calls are present while measured quality pass rate is above 90%.",
      derivedFrom: ["cost.advancedCalls", "rates.qualityPassRate"],
      estimatedSavingUsd: 0.002
    }
  ],
  runs: [
    {
      runId: "run_fixture_006",
      createdAt: "2026-01-06T14:40:00+00:00",
      application: "Claims review",
      environment: "dev",
      workflowId: "workflow_optimization",
      workflow: "Claims review workflow",
      optimizationTarget: "measured_workflow",
      proofType: "measured",
      priceTableVersion: "2026-01-01",
      governedModelSpendUsd: 0.0017,
      baselineModelSpendUsd: 0.0028,
      verifiedSavingUsd: 0.0011,
      acceptedOutcomes: 26,
      costPerAcceptedOutcomeUsd: 0.0017 / 26,
      modelCalls: 4,
      localOperations: 7,
      reuseOperations: 2,
      qualityPassRate: 0.91,
      escalationRate: 0.08
    },
    {
      runId: "run_fixture_005",
      createdAt: "2026-01-05T17:10:00+00:00",
      application: "Claims review",
      environment: "dev",
      workflowId: "workflow_optimization",
      workflow: "Claims review workflow",
      optimizationTarget: "single_prompt",
      proofType: "measured",
      priceTableVersion: "2026-01-01",
      governedModelSpendUsd: 0.0018,
      baselineModelSpendUsd: 0.003,
      verifiedSavingUsd: 0.0012,
      acceptedOutcomes: 28,
      costPerAcceptedOutcomeUsd: 0.0018 / 28,
      modelCalls: 3,
      localOperations: 8,
      reuseOperations: 3,
      qualityPassRate: 1,
      escalationRate: 0.04
    }
  ]
};
