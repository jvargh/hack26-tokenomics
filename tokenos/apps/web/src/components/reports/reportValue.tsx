import { EvidenceTier } from "../shared/Comparison";
import type { EvidenceTier as SharedEvidenceTier } from "../shared/Comparison";

export type ReportTier =
  | "estimated"
  | "measured-current"
  | "measured-governed"
  | "measured-sample"
  | "projected"
  | "verified-saving"
  | "neutral";

const tierText: Record<ReportTier, string> = {
  estimated: "Estimated",
  "measured-current": "Measured — current",
  "measured-governed": "Measured — governed",
  // The usage behind this figure was genuinely measured, but the input was a
  // bundled fixture. Saying both stops a reproducible demo run from being read
  // as production spend.
  "measured-sample": "Measured — sample run",
  projected: "Projected at volume",
  "verified-saving": "Verified saving",
  neutral: "Verified saving"
};

const sharedTier: Record<ReportTier, SharedEvidenceTier> = {
  estimated: "estimate",
  "measured-current": "proven",
  "measured-governed": "proven",
  // The number is a real measurement, not a guess, so calling it an estimate
  // would be inaccurate in the other direction. The wording carries the caveat.
  "measured-sample": "proven",
  projected: "estimate",
  "verified-saving": "proven",
  neutral: "none"
};

export function TierChip({
  tier,
  testId,
  subtle = false
}: {
  tier: ReportTier;
  testId?: string;
  subtle?: boolean;
}) {
  return (
    <EvidenceTier
      tier={sharedTier[tier]}
      className={`tier is-${tier}${subtle ? " is-subtle" : ""}`}
      testId={testId}
    >
      {tierText[tier]}
    </EvidenceTier>
  );
}

export function MetricValue({
  value,
  tier,
  formatter = formatNumber,
  className,
  valueTestId,
  tierTestId,
  subtleTier = false
}: {
  value: number | null;
  tier: ReportTier;
  formatter?: (value: number) => string;
  className?: string;
  valueTestId?: string;
  tierTestId?: string;
  subtleTier?: boolean;
}) {
  return (
    <span className={`metric ${className ?? ""}`.trim()}>
      <span className="metric-number" data-testid={valueTestId}>
        {value === null ? "—" : formatter(value)}
      </span>
      <TierChip tier={tier} testId={tierTestId} subtle={subtleTier} />
    </span>
  );
}

export function formatNumber(value: number): string {
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(value);
}

export function formatInteger(value: number): string {
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 }).format(value);
}

export function formatUsd(value: number): string {
  const fractionDigits = Math.abs(value) > 0 && Math.abs(value) < 0.01 ? 4 : 2;
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits
  }).format(value);
}

export function formatUnitUsd(value: number): string {
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 6,
    maximumFractionDigits: 6
  }).format(value);
}

export function formatPercent(value: number): string {
  return new Intl.NumberFormat(undefined, {
    style: "percent",
    minimumFractionDigits: 0,
    maximumFractionDigits: 1
  }).format(value);
}

export function targetLabel(value: string | null | undefined): string {
  switch (value) {
    case "current_workflow":
      return "Current workflow";
    case "single_prompt":
      return "Single prompt";
    case "measured_workflow":
      return "Measured workflow";
    default:
      return "All targets";
  }
}
