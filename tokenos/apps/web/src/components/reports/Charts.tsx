import { useId } from "react";
import type { ReportRouteTier, ReportSeriesBucket } from "../../api/types";
import { MetricValue, formatInteger, formatPercent, formatUsd } from "./reportValue";

type Tone = "brand" | "good" | "warn" | "risk" | "muted";

function point(value: number, index: number, values: number[], width: number, height: number): string {
  const max = Math.max(...values);
  const min = Math.min(...values);
  const x = values.length === 1 ? width / 2 : (index / (values.length - 1)) * width;
  const y = max === min ? height / 2 : height - ((value - min) / (max - min)) * height;
  return `${x.toFixed(2)},${y.toFixed(2)}`;
}

function linePath(
  raw: Array<number | null>,
  allValues: number[],
  width: number,
  height: number
): string {
  let path = "";
  let drawing = false;
  raw.forEach((value, index) => {
    if (value === null) {
      drawing = false;
      return;
    }
    const coordinates = point(value, index, allValues, width, height);
    path += `${drawing ? "L" : "M"} ${coordinates} `;
    drawing = true;
  });
  return path.trim();
}

function bandPaths(
  lower: Array<number | null>,
  upper: Array<number | null>,
  allValues: number[],
  width: number,
  height: number
): string[] {
  const paths: string[] = [];
  let lowerPoints: string[] = [];
  let upperPoints: string[] = [];

  lower.forEach((low, index) => {
    const high = upper[index];
    if (low === null || high === null) {
      if (lowerPoints.length > 1) {
        paths.push(`M ${lowerPoints.join(" L ")} L ${upperPoints.reverse().join(" L ")} Z`);
      }
      lowerPoints = [];
      upperPoints = [];
      return;
    }
    lowerPoints.push(point(low, index, allValues, width, height));
    upperPoints.push(point(high, index, allValues, width, height));
  });

  if (lowerPoints.length > 1) {
    paths.push(`M ${lowerPoints.join(" L ")} L ${upperPoints.reverse().join(" L ")} Z`);
  }

  return paths;
}

export function Sparkline({
  title,
  values,
  tone = "brand"
}: {
  title: string;
  values: Array<number | null>;
  tone?: Tone;
}) {
  const id = useId();
  const numeric = values.filter((value): value is number => value !== null);
  const path = numeric.length ? linePath(values, numeric, 120, 34) : "";

  return (
    <svg className={`sparkline is-${tone}`} viewBox="0 0 120 34" role="img" aria-labelledby={id}>
      <title id={id}>{numeric.length ? title : `${title}: no measured values yet`}</title>
      <line className="sparkline-base" x1="0" x2="120" y1="27" y2="27" />
      {path ? <path className="sparkline-line" d={path} /> : null}
    </svg>
  );
}

export function SpendTrendChart({ series }: { series: ReportSeriesBucket[] }) {
  const id = useId();
  const governed = series.map((bucket) => bucket.measured.governedModelSpendUsd);
  const baseline = series.map((bucket) =>
    bucket.measured.baselineModelSpendUsd > 0 || bucket.measured.verifiedSavingsUsd > 0
      ? bucket.measured.baselineModelSpendUsd
      : null
  );
  const allValues = [...governed, ...baseline].filter((value): value is number => value !== null);
  const values = allValues.length ? allValues : [0];
  const governedPath = linePath(governed, values, 420, 180);
  const baselinePath = linePath(baseline, values, 420, 180);
  const bands = bandPaths(governed, baseline, values, 420, 180);

  return (
    <div className="chart">
      <svg viewBox="0 0 420 180" role="img" aria-labelledby={id}>
        <title id={id}>
          Governed spend is shown as a solid line; measured baseline spend is dashed; shaded
          bands mark verified savings where both exist.
        </title>
        <line className="axis" x1="0" x2="420" y1="170" y2="170" />
        {bands.map((path) => (
          <path key={path} className="saving-band" d={path} />
        ))}
        {governedPath ? <path className="line governed" d={governedPath} /> : null}
        {baselinePath ? <path className="line baseline" d={baselinePath} /> : null}
      </svg>
      <div className="legend">
        <span><i className="key governed" />Governed spend</span>
        <span><i className="key baseline" />Measured baseline</span>
        <span><i className="key saving" />Verified gap</span>
      </div>
    </div>
  );
}

export function RouteTierShare({ tiers }: { tiers: ReportRouteTier[] }) {
  const id = useId();
  const patternId = useId().replace(/:/g, "");
  const total = tiers.reduce((sum, tier) => sum + tier.operations + tier.calls, 0);
  let offset = 0;

  return (
    <div className="route-chart">
      <svg viewBox="0 0 420 42" role="img" aria-labelledby={id}>
        <title id={id}>
          Route-tier distribution by counted operations and model calls with each segment labelled
          in the legend below.
        </title>
        <defs>
          <pattern id={`${patternId}-advanced`} width="8" height="8" patternUnits="userSpaceOnUse">
            <path className="pattern-stroke" d="M0 8 L8 0" />
          </pattern>
          <pattern id={`${patternId}-efficient`} width="7" height="7" patternUnits="userSpaceOnUse">
            <path className="pattern-stroke" d="M0 3.5 H7" />
          </pattern>
        </defs>
        <rect className="stack-shell" x="0" y="8" width="420" height="26" rx="13" />
        {total > 0
          ? tiers.map((tier) => {
              const amount = tier.operations + tier.calls;
              const width = (amount / total) * 420;
              const x = offset;
              offset += width;
              return (
                <g key={tier.tier}>
                  <rect
                    className={`segment is-${tier.tier}`}
                    x={x}
                    y="8"
                    width={width}
                    height="26"
                    rx="8"
                  />
                  {tier.tier === "advanced" || tier.tier === "efficient" ? (
                    <rect
                      className="pattern-fill"
                      fill={`url(#${patternId}-${tier.tier})`}
                      x={x}
                      y="8"
                      width={width}
                      height="26"
                      rx="8"
                    />
                  ) : null}
                </g>
              );
            })
          : null}
      </svg>
      <div className="route-list">
        {tiers.map((tier) => {
          const amount = tier.operations + tier.calls;
          const share = total > 0 ? amount / total : 0;
          return (
            <div className="route-item" key={tier.tier}>
              <span><i className={`key is-${tier.tier}`} />{tier.label}</span>
              <MetricValue value={share} tier="measured-governed" formatter={formatPercent} subtleTier />
              <MetricValue value={amount} tier="measured-governed" formatter={formatInteger} subtleTier />
              <MetricValue value={tier.spendUsd} tier="measured-governed" formatter={formatUsd} subtleTier />
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function ProjectionBars({ entries }: { entries: Array<[string, number]> }) {
  const id = useId();
  const max = Math.max(...entries.map((entry) => entry[1]), 0);

  if (!entries.length || max <= 0) {
    return (
      <p className="empty-copy">
        No projection — supply a recurring volume on a run to see cost at scale.
      </p>
    );
  }

  return (
    <div className="projection-chart">
      <svg viewBox="0 0 420 160" role="img" aria-labelledby={id}>
        <title id={id}>
          Projection at volume by period and source. Bars use labels beside the chart and measured
          values below.
        </title>
        <line className="axis" x1="0" x2="420" y1="146" y2="146" />
        {entries.map(([label, value], index) => {
          const width = 420 / entries.length;
          const barWidth = Math.max(18, width * 0.42);
          const height = (value / max) * 120;
          const x = index * width + (width - barWidth) / 2;
          const y = 146 - height;
          return (
            <rect
              key={label}
              className="projection-bar"
              x={x}
              y={y}
              width={barWidth}
              height={height}
              rx="8"
            />
          );
        })}
      </svg>
      <div className="projection-list">
        {entries.map(([label, value]) => (
          <div className="projection-item" key={label}>
            <span>{label}</span>
            <MetricValue value={value} tier="projected" formatter={formatUsd} subtleTier />
          </div>
        ))}
      </div>
    </div>
  );
}
