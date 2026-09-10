import { useEffect, useMemo, useState } from "react";
import { api } from "../../api/client";
import type {
  ReportOptimizationTarget,
  ReportResponse,
  ReportRun,
  ReportingQuery
} from "../../api/types";
import { KpiCard, Panel } from "./Cards";
import { ProjectionBars, RouteTierShare, Sparkline, SpendTrendChart } from "./Charts";
import { reportingFixture } from "./reportingFixture";
import {
  MetricValue,
  TierChip,
  formatInteger,
  formatPercent,
  formatUnitUsd,
  formatUsd,
  targetLabel
} from "./reportValue";
import type { ReportTier } from "./reportValue";

type RangePreset = "last7" | "last30" | "all";
type ExportFormat = "json" | "csv";

const dayMs = 24 * 60 * 60 * 1000;

function queryFor(range: RangePreset, target: ReportOptimizationTarget | ""): ReportingQuery {
  const query: ReportingQuery = { bucket: "day", limit: 200 };
  if (target) query.optimizationTarget = target;
  if (range !== "all") {
    const days = range === "last7" ? 7 : 30;
    const to = new Date();
    const from = new Date(to.getTime() - days * dayMs);
    query.from = from.toISOString();
    query.to = to.toISOString();
  }
  return query;
}

function numberOrNull(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function delta(current: number | null, previous: number | null): string | null {
  if (current === null || previous === null) return null;
  if (previous === 0) {
    if (current === 0) return "No change vs prior";
    return "New vs prior";
  }
  const change = (current - previous) / Math.abs(previous);
  const marker = change >= 0 ? "▲" : "▼";
  return `${marker} ${formatPercent(Math.abs(change))} vs prior`;
}

function fixtureBlob(format: ExportFormat): Blob {
  if (format === "json") {
    return new Blob([JSON.stringify(reportingFixture, null, 2)], { type: "application/json" });
  }
  const columns = [
    "runId",
    "createdAt",
    "application",
    "environment",
    "optimizationTarget",
    "proofType",
    "priceTableVersion",
    "governedModelSpendUsd",
    "baselineModelSpendUsd",
    "verifiedSavingUsd",
    "acceptedOutcomes",
    "costPerAcceptedOutcomeUsd",
    "modelCalls",
    "localOperations",
    "reuseOperations",
    "qualityPassRate",
    "escalationRate"
  ] as const;
  const escape = (value: unknown) => {
    if (value === null || value === undefined) return "";
    const text = String(value);
    return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  };
  const rows = reportingFixture.runs.map((run) => columns.map((column) => escape(run[column])));
  const csv = [columns.join(","), ...rows.map((row) => row.join(","))].join("\n");
  return new Blob([csv], { type: "text/csv" });
}

function downloadBlob(blob: Blob, format: ExportFormat) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `tokenos-report.${format}`;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

/**
 * Flattens a report row into the fields the table renders.
 *
 * The endpoint nests measures under `dimensions`, `cost`, `baseline` and
 * `metrics`, and the two run sources disagree on where counters live:
 * optimization runs put them on `cost`, workflow runs on `metrics`. Reading a
 * flat key straight off the row silently yields `undefined` and falls through
 * to a default, which is how a sample run could previously render as
 * "measured". Everything unresolved stays `null` so the caller renders an
 * em-dash rather than inventing a value.
 */
function runView(run: ReportRun) {
  const record = run as Record<string, unknown>;
  const nested = (key: string): Record<string, unknown> => {
    const value = record[key];
    return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
  };
  const dimensions = nested("dimensions");
  const cost = nested("cost");
  const baseline = nested("baseline");
  const metrics = nested("metrics");

  const pick = (...candidates: unknown[]): unknown =>
    candidates.find((candidate) => candidate !== undefined && candidate !== null);

  const text = (value: unknown): string | null =>
    typeof value === "string" && value.trim() !== "" ? value : null;

  const counter = (key: string): number | null =>
    numberOrNull(pick(cost[key], metrics[key]));

  const savingEligible = baseline.eligible === true;

  return {
    workflow: text(pick(dimensions.workflow, dimensions.workflowId, dimensions.application, record.workflow)),
    workflowId: text(pick(dimensions.workflowId, record.workflowId, record.workflow_id)),
    source: text(dimensions.source),
    optimizationTarget: text(pick(dimensions.optimizationTarget, record.optimizationTarget)),
    proofType: text(pick(dimensions.proofType, record.proofType)),
    governedModelSpendUsd: numberOrNull(pick(cost.modelSpendUsd, record.governedModelSpendUsd)),
    baselineModelSpendUsd: numberOrNull(pick(baseline.baselineModelSpendUsd, record.baselineModelSpendUsd)),
    // A saving is shown only when the server marked the baseline eligible.
    // Without that flag the run has no verified saving to report.
    verifiedSavingUsd: savingEligible ? numberOrNull(baseline.verifiedSavingUsd) : null,
    costPerAcceptedOutcomeUsd: numberOrNull(pick(cost.costPerAcceptedOutcomeUsd, record.costPerAcceptedOutcomeUsd)),
    qualityPassRate: numberOrNull(pick(metrics.qualityPassRate, record.qualityPassRate)),
    acceptedOutcomes: counter("acceptedOutcomes"),
    modelCalls: counter("modelCalls")
  };
}

function runWorkflow(run: ReportRun): string {
  const view = runView(run);
  return view.workflow ?? "Unattributed run";
}

function runWorkflowId(run: ReportRun): string | undefined {
  const workflowId = runView(run).workflowId;
  return typeof workflowId === "string" ? workflowId : undefined;
}

function relativeTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const seconds = Math.round((date.getTime() - Date.now()) / 1000);
  const abs = Math.abs(seconds);
  const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  if (abs < 60) return formatter.format(seconds, "second");
  if (abs < 3600) return formatter.format(Math.round(seconds / 60), "minute");
  if (abs < 86400) return formatter.format(Math.round(seconds / 3600), "hour");
  return formatter.format(Math.round(seconds / 86400), "day");
}

export function ReportsScreen({
  onOpenRun
}: {
  onOpenRun: (runId: string, workflowId?: string) => void;
}) {
  const [range, setRange] = useState<RangePreset>("last30");
  const [target, setTarget] = useState<ReportOptimizationTarget | "">("");
  const [report, setReport] = useState<ReportResponse | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);

  const query = useMemo(() => queryFor(range, target), [range, target]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    api
      .reports(query)
      .then((response) => {
        if (!cancelled) setReport(response);
      })
      .catch((caught: unknown) => {
        if (cancelled) return;
        if (import.meta.env.DEV) {
          setReport(reportingFixture);
          setError("Using the local development reporting fixture until the API is available.");
        } else {
          setReport(null);
          setError(caught instanceof Error ? caught.message : "Could not load reports.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [query]);

  /**
   * Which evidence the headline figures are drawn from.
   *
   * Measured and sample runs are never summed: with five measured and three
   * sample runs, one combined total would overstate production spend. But
   * reading only `measured` meant a screen full of zeros whenever the only runs
   * so far were over bundled fixtures, which reads as "reporting is broken"
   * rather than "these runs were samples". So the basis falls back to sample
   * when there is no measured evidence, and every card is tiered accordingly.
   */
  const measuredGroup = report?.groups.measured;
  const sampleGroup = report?.groups.sample;
  const basis: "measured" | "sample" =
    (measuredGroup?.runCount ?? 0) > 0 || (sampleGroup?.runCount ?? 0) === 0
      ? "measured"
      : "sample";
  const measured = basis === "measured" ? measuredGroup : sampleGroup;
  const basisTier: ReportTier = basis === "measured" ? "measured-governed" : "measured-sample";
  const previous = report?.previous;
  const previousBasis = previous ? previous[basis] : null;
  const seriesBasis = report?.series.map((bucket) => bucket[basis]) ?? [];
  const runs = report?.runs ?? [];
  const hasRuns = runs.length > 0;
  const projectionEntries = useMemo(
    () => Object.entries(report?.groups.projected.byPeriodAndSource ?? {}),
    [report]
  );
  const priceVersions = report?.priceTableVersions.length ? report.priceTableVersions.join(", ") : "";
  const priceLabel = priceVersions ? `price table v${priceVersions}` : "price table not reported";

  const handleExport = async (format: ExportFormat) => {
    setExporting(true);
    setError("");
    try {
      const blob = await api.exportReport(query, format);
      downloadBlob(blob, format);
    } catch (caught) {
      if (import.meta.env.DEV) {
        downloadBlob(fixtureBlob(format), format);
        setError("Exported the local development fixture because the API is unavailable.");
      } else {
        setError(caught instanceof Error ? caught.message : "Could not export the report.");
      }
    } finally {
      setExporting(false);
    }
  };

  return (
    <main className="reports" data-testid="reports-screen">
      <section className="hero">
        <div>
          <p className="eyebrow">Reports</p>
          <h1>Evidence-weighted AI spend</h1>
          <p className="subtitle">
            Measured governance across selected runs · {priceLabel}
          </p>
          {report ? (
            <div className="summary-strip">
              <MetricValue value={report.groups.measured.runCount} tier="measured-governed" formatter={formatInteger} subtleTier />
              <MetricValue value={report.groups.sample.runCount} tier="measured-sample" formatter={formatInteger} subtleTier />
              <MetricValue value={report.groups.projected.projectionCount} tier="projected" formatter={formatInteger} subtleTier />
            </div>
          ) : null}
        </div>
        <div className="toolbar" aria-label="Report controls">
          <label>
            <span>Target</span>
            <select
              data-testid="report-target"
              value={target}
              onChange={(event) => setTarget(event.target.value as ReportOptimizationTarget | "")}
            >
              <option value="">All targets</option>
              <option value="current_workflow">Current workflow</option>
              <option value="single_prompt">Single prompt</option>
              <option value="measured_workflow">Measured workflow</option>
            </select>
          </label>
          <label>
            <span>Date range</span>
            <select
              data-testid="report-range"
              value={range}
              onChange={(event) => setRange(event.target.value as RangePreset)}
            >
              <option value="last7">Last 7 days</option>
              <option value="last30">Last 30 days</option>
              <option value="all">All measured time</option>
            </select>
          </label>
          <label>
            <span>Export</span>
            <select
              data-testid="report-export"
              value=""
              disabled={exporting}
              onChange={(event) => {
                const format = event.target.value as ExportFormat;
                if (format) void handleExport(format);
              }}
            >
              <option value="">{exporting ? "Exporting…" : "Choose format"}</option>
              <option value="json">JSON</option>
              <option value="csv">CSV</option>
            </select>
          </label>
        </div>
      </section>

      {error ? <p role="alert" className="notice notice-warn">{error}</p> : null}
      {loading ? <p className="panel">Loading reporting evidence…</p> : null}

      {report && !loading && !hasRuns ? (
        <section className="panel empty-state" data-testid="reports-empty">
          <h2>No runs in this range yet</h2>
          <p>
            TokenOS will not substitute estimates for missing measurements. Complete any
            workflow or widen the range to see measured spend, quality, and savings.
          </p>
        </section>
      ) : null}

      {report && measured && !loading && hasRuns ? (
        <>
          {basis === "sample" ? (
            <p className="notice notice-brand" data-testid="reports-sample-basis">
              These figures come from runs over bundled sample input. The usage was
              measured, but the input is reproducible fixture data, so treat it as a
              demonstration rather than production spend.
            </p>
          ) : null}
          <section className="kpi-grid" aria-label="Key reporting metrics">
            <KpiCard
              testId="kpi-verified-saving"
              label="Verified saving"
              value={measured.verifiedSavingsUsd}
              tier={measured.verifiedSavingsUsd > 0 ? "verified-saving" : "neutral"}
              formatter={formatUsd}
              delta={previousBasis ? delta(measured.verifiedSavingsUsd, previousBasis.verifiedSavingsUsd) : null}
              sparkline={seriesBasis.map((bucket) => bucket.verifiedSavingsUsd)}
              tone={measured.verifiedSavingsUsd > 0 ? "good" : "muted"}
            />
            <KpiCard
              testId="kpi-governed-spend"
              label="Governed spend"
              value={measured.governedModelSpendUsd}
              tier={basisTier}
              formatter={formatUsd}
              delta={previousBasis ? delta(measured.governedModelSpendUsd, previousBasis.governedModelSpendUsd) : null}
              sparkline={seriesBasis.map((bucket) => bucket.governedModelSpendUsd)}
              tone="brand"
            />
            <KpiCard
              testId="kpi-cost-per-outcome"
              label="Cost per accepted outcome"
              value={measured.costPerAcceptedOutcomeUsd}
              tier={basisTier}
              formatter={formatUnitUsd}
              delta={previousBasis ? delta(measured.costPerAcceptedOutcomeUsd, previousBasis.costPerAcceptedOutcomeUsd) : null}
              sparkline={seriesBasis.map((bucket) => bucket.costPerAcceptedOutcomeUsd)}
              tone="brand"
            />
            <KpiCard
              testId="kpi-calls-avoided"
              label="Model calls avoided"
              value={measured.modelCallsAvoided}
              tier={basisTier}
              formatter={formatInteger}
              delta={previousBasis ? delta(measured.modelCallsAvoided, previousBasis.modelCallsAvoided) : null}
              sparkline={seriesBasis.map((bucket) => bucket.modelCallsAvoided)}
              tone="brand"
              note="Counted only against a paired baseline run."
            />
            <KpiCard
              testId="kpi-quality-pass"
              label="Quality pass rate"
              value={measured.rates.qualityPassRate.mean}
              tier={basisTier}
              formatter={formatPercent}
              delta={previousBasis ? delta(measured.rates.qualityPassRate.mean, previousBasis.rates.qualityPassRate.mean) : null}
              sparkline={seriesBasis.map((bucket) => bucket.rates.qualityPassRate.mean)}
              tone="good"
            />
            <KpiCard
              testId="kpi-projected"
              label="Projected at volume"
              value={report.groups.projected.valueUsd}
              tier="projected"
              formatter={formatUsd}
              delta={previous ? delta(report.groups.projected.valueUsd, previous.projected.valueUsd) : null}
              sparkline={report.series.map((bucket) => bucket.projected.valueUsd)}
              tone="warn"
              note="Only when recurring volume was supplied."
            />
          </section>

          <section className="panel-grid" aria-label="Reporting panels">
            <Panel
              title="Governed vs baseline spend"
              eyebrow="Measured over time"
              testId="panel-spend-trend"
            >
              <SpendTrendChart series={report.series} basis={basis} />
            </Panel>

            <Panel
              title="Where the work went"
              eyebrow="Route-tier distribution"
              testId="panel-route-tiers"
            >
              <RouteTierShare tiers={report.routeTiers} />
              <p className="panel-foot">{priceLabel}</p>
            </Panel>

            <Panel
              title="Projection at volume"
              eyebrow="Projected, not measured"
              testId="panel-projection"
              projected
            >
              <div className="projection-total">
                <MetricValue value={report.groups.projected.valueUsd} tier="projected" formatter={formatUsd} />
              </div>
              <ProjectionBars entries={projectionEntries} />
            </Panel>

            <Panel title="Recent runs" eyebrow={targetLabel(target)} testId="panel-recent-runs">
              <div className="table-wrap">
                <table>
                  <caption>Each row is a server-reported proof object from the report endpoint.</caption>
                  <thead>
                    <tr>
                      <th>Run ID</th>
                      <th>Workflow</th>
                      <th>Target</th>
                      <th>Proof</th>
                      <th className="numeric">Governed spend</th>
                      <th className="numeric">Cost per outcome</th>
                      <th className="numeric">Quality</th>
                      <th className="numeric">Verified saving</th>
                      <th>Sparkline</th>
                    </tr>
                  </thead>
                  <tbody>
                    {runs.map((run) => {
                      const view = runView(run);
                      const saving = view.verifiedSavingUsd;
                      // Tier each figure by the evidence the run itself carries.
                      // A fixture run's usage was measured, but it is not
                      // production spend and must not be styled as if it were.
                      const spendTier: ReportTier =
                        view.proofType === "sample" ? "measured-sample" : "measured-governed";
                      return (
                        <tr
                          key={run.runId}
                          className="click-row"
                          tabIndex={0}
                          role="button"
                          onClick={() => onOpenRun(run.runId, runWorkflowId(run))}
                          onKeyDown={(event) => {
                            if (event.key === "Enter" || event.key === " ") {
                              event.preventDefault();
                              onOpenRun(run.runId, runWorkflowId(run));
                            }
                          }}
                        >
                          <td>{run.runId}</td>
                          <td>{runWorkflow(run)}</td>
                          <td>{view.optimizationTarget ? targetLabel(view.optimizationTarget) : "—"}</td>
                          <td>{view.proofType ?? "—"}</td>
                          <td className="numeric">
                            <MetricValue value={view.governedModelSpendUsd} tier={spendTier} formatter={formatUsd} subtleTier />
                          </td>
                          <td className="numeric">
                            <MetricValue value={view.costPerAcceptedOutcomeUsd} tier={spendTier} formatter={formatUnitUsd} subtleTier />
                          </td>
                          <td className="numeric">
                            <MetricValue value={view.qualityPassRate} tier={spendTier} formatter={formatPercent} subtleTier />
                          </td>
                          <td className="numeric">
                            <MetricValue
                              value={saving}
                              tier={saving !== null && saving > 0 ? "verified-saving" : "neutral"}
                              formatter={formatUsd}
                              subtleTier
                            />
                          </td>
                          <td>
                            <Sparkline
                              title={`Spend evidence for ${run.runId}`}
                              values={[
                                view.governedModelSpendUsd,
                                view.baselineModelSpendUsd,
                                saving
                              ]}
                              tone={saving !== null && saving > 0 ? "good" : "muted"}
                            />
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </Panel>

            <Panel title="Governance events" eyebrow="Newest first" testId="panel-events">
              {report.events.length ? (
                <ol className="event-list">
                  {report.events.map((event) => (
                    <li className={`event is-${event.severity}`} key={`${event.runId}-${event.at}-${event.type}`}>
                      <span className="event-icon" aria-hidden="true">
                        {event.severity === "risk" ? "!" : event.severity === "warning" ? "△" : "i"}
                      </span>
                      <div>
                        <strong>{event.message}</strong>
                        <span>{event.type} · {relativeTime(event.at)} · {event.runId}</span>
                      </div>
                    </li>
                  ))}
                </ol>
              ) : (
                <p className="empty-copy">No governance events in this range.</p>
              )}
            </Panel>
          </section>

          <section className="opportunities" aria-labelledby="opportunity-heading">
            <div className="section-head">
              <p className="eyebrow">Opportunities</p>
              <h2 id="opportunity-heading">Measured evidence, estimated opportunity</h2>
            </div>
            {report.opportunities.length ? (
              <div className="opportunity-grid">
                {report.opportunities.map((opportunity) => (
                  <article className="opportunity-card" data-testid="opportunity-card" key={opportunity.id}>
                    <div className="opportunity-head">
                      <span className={`impact is-${opportunity.impact}`}>{opportunity.impact}</span>
                      <TierChip tier="estimated" />
                    </div>
                    <h3>{opportunity.title}</h3>
                    <p>{opportunity.evidence}</p>
                    <MetricValue
                      value={opportunity.estimatedSavingUsd}
                      tier="estimated"
                      formatter={formatUsd}
                    />
                    <small>Derived from {opportunity.derivedFrom.join(", ")}</small>
                  </article>
                ))}
              </div>
            ) : (
              <div className="panel empty-state">
                <h3>No estimated opportunities yet</h3>
                <p>
                  The API only emits opportunities when measured runs support a derivation. There is
                  nothing honest to recommend for this range.
                </p>
              </div>
            )}
          </section>
        </>
      ) : null}
    </main>
  );
}
