import type { ReactNode } from "react";
import { Sparkline } from "./Charts";
import { MetricValue, TierChip, type ReportTier } from "./reportValue";

export function Panel({
  title,
  eyebrow,
  action = "View all →",
  children,
  testId,
  projected = false
}: {
  title: string;
  eyebrow?: string;
  action?: ReactNode;
  children: ReactNode;
  testId?: string;
  projected?: boolean;
}) {
  return (
    <section className={`panel panel-card${projected ? " is-projected" : ""}`} data-testid={testId}>
      <div className="panel-head">
        <div>
          {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
          <h3>{title}</h3>
        </div>
        {action ? <span className="panel-action">{action}</span> : null}
      </div>
      {children}
    </section>
  );
}

export function KpiCard({
  testId,
  label,
  value,
  tier,
  formatter,
  delta,
  sparkline,
  tone = "brand",
  note
}: {
  testId: string;
  label: string;
  value: number | null;
  tier: ReportTier;
  formatter: (value: number) => string;
  delta?: string | null;
  sparkline: Array<number | null>;
  tone?: "brand" | "good" | "warn" | "risk" | "muted";
  note?: ReactNode;
}) {
  return (
    <article className={`kpi-card is-${tier}`} data-testid={testId}>
      <div className="kpi-label">{label}</div>
      <MetricValue
        value={value}
        tier={tier}
        formatter={formatter}
        className="kpi-value"
        valueTestId={`${testId}-value`}
        tierTestId={`${testId}-tier`}
      />
      {delta ? (
        <div className="delta">
          <span>{delta}</span>
          <TierChip tier={tier} subtle />
        </div>
      ) : null}
      {note ? <div className="kpi-note">{note}</div> : null}
      <Sparkline
        title={`${label} trend across selected buckets`}
        values={sparkline}
        tone={tone}
      />
    </article>
  );
}
