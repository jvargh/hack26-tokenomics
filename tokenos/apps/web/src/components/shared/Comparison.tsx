/**
 * Shared before/after comparison primitives for the Prove screens.
 *
 * Claim strength is the whole point of this file. A value is either:
 *   - "estimate"  — locally computed, nothing extra was spent
 *   - "proven"    — both routes actually ran and were measured
 *   - "none"      — no honest comparison exists, so no benefit is shown
 *
 * The tier is passed in explicitly rather than inferred here, so a caller can
 * never accidentally render an estimate with measured styling.
 */

import type { ReactNode } from "react";

export type EvidenceTier = "estimate" | "proven" | "none";

/** Wording used wherever a comparison value is labelled. Kept in one place so
 *  the two Prove surfaces cannot drift into separate vocabularies. */
export const EVIDENCE_WORD: Record<Exclude<EvidenceTier, "none">, string> = {
  estimate: "estimate",
  proven: "proven"
};

/** The headline benefit: how much of the work never needed a model at all. */
export function WorkAvoidedBanner({
  localOperations,
  totalOperations,
  detail,
  /** "used no AI at all" is the precise claim when a step was reserved for a
   *  model and deferred: it ran no tokens, but it did not complete either. */
  completed = true
}: {
  localOperations: number;
  totalOperations: number;
  detail: ReactNode;
  completed?: boolean;
}) {
  return (
    <div className="work-avoided">
      <div className="work-avoided-count">
        {localOperations}
        <span className="work-avoided-of"> of {totalOperations}</span>
      </div>
      <div className="work-avoided-text">
        {completed
          ? "steps were completed without using AI at all."
          : "steps used no AI at all."}
        <small>{detail}</small>
      </div>
    </div>
  );
}

/** One hero card. `comparison` is the "before" line; omit it only when no
 *  honest comparison exists, and the slot still reserves its height so the
 *  large values stay on a single baseline across the row. */
export function ComparisonCard({
  title,
  comparison,
  value,
  unit,
  chip,
  tier,
  note,
  valueTone
}: {
  title: string;
  comparison?: ReactNode;
  value: ReactNode;
  unit?: string;
  chip?: string;
  tier: EvidenceTier;
  note: ReactNode;
  valueTone?: "good";
}) {
  return (
    <div className="card comparison-card">
      <div className="comparison-card-title">{title}</div>
      <div className={`comparison-before${comparison ? "" : " is-blank"}`} aria-hidden={!comparison}>
        {comparison ?? "\u00a0"}
      </div>
      <div className={`comparison-value${valueTone === "good" ? " text-good" : ""}`}>
        {value}
        {unit ? <span className="comparison-value-unit"> {unit}</span> : null}
      </div>
      {chip ? <span className={`comparison-chip is-${tier}`}>{chip}</span> : null}
      <div className="comparison-note">{note}</div>
    </div>
  );
}

/** The single strength bar under the cards: says how strong the claim is and
 *  offers the one action that can strengthen it. */
export function ClaimStrengthBar({
  tier,
  badge,
  headline,
  detail,
  children
}: {
  tier: EvidenceTier;
  badge: string;
  headline: string;
  detail: ReactNode;
  children?: ReactNode;
}) {
  return (
    <div className={`claim-strength is-${tier}`}>
      <span className={`claim-strength-badge is-${tier}`}>{badge}</span>
      <div className="claim-strength-main">
        <span className="claim-strength-headline">{headline}</span>
        <span className="claim-strength-detail">{detail}</span>
      </div>
      {children ? <div className="claim-strength-action">{children}</div> : null}
    </div>
  );
}

/** Two-row route picture: the all-AI shape above, what actually ran below.
 *  Used by the optimization Prove surface; the legacy screen folds the same
 *  "before" row into its own richer route-flow panel. */
export function RouteComparison({
  beforeLabel,
  beforeSteps,
  beforeSuffix,
  afterLabel,
  afterSteps
}: {
  beforeLabel: string;
  beforeSteps: string[];
  beforeSuffix?: string;
  afterLabel: string;
  afterSteps: Array<{ text: string; tone?: "local" | "model" }>;
}) {
  return (
    <div className="route-comparison">
      <div className="route-comparison-row">
        <span className="route-comparison-label">{beforeLabel}</span>
        {beforeSteps.map((step, index) => (
          <span key={step}>
            {index > 0 ? <span className="route-comparison-arrow">→</span> : null}
            <span className="route-comparison-step is-ghosted">{step}</span>
          </span>
        ))}
        {beforeSuffix ? <span className="route-comparison-suffix">{beforeSuffix}</span> : null}
      </div>
      <div className="route-comparison-row">
        <span className="route-comparison-label">{afterLabel}</span>
        {afterSteps.map((step, index) => (
          <span key={step.text}>
            {index > 0 ? <span className="route-comparison-arrow">→</span> : null}
            <span className={`route-comparison-step${step.tone ? ` is-${step.tone}` : ""}`}>
              {step.text}
            </span>
          </span>
        ))}
      </div>
    </div>
  );
}
