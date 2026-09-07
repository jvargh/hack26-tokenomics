import { useState } from "react";
import { api } from "../api/client";
import type { BaselineRun } from "../api/types";
import { useRun } from "../state/runContext";
import { PhaseIntro } from "../components/shared/PhaseIntro";
import {
  ClaimStrengthBar,
  ComparisonCard,
  WorkAvoidedBanner,
  type EvidenceTier
} from "../components/shared/Comparison";
import {
  GENERATIVE_ROUTES,
  formatCount,
  formatDuration,
  formatUsd,
  routeLabel
} from "../components/shared/format";

const DECISION_LABEL: Record<string, string> = {
  approve: "Pay",
  request_evidence: "Needs approval",
  needs_interpretation: "Needs interpretation",
  reject: "Do not pay",
  unmatched: "No rule matched"
};

const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? "" : "s"}`;

/** Colour family for a route, so the same decision reads the same everywhere. */
function routeTone(route: string): "local" | "retrieval" | "efficient" | "advanced" {
  if (route === "advanced_ai") return "advanced";
  if (route === "efficient_ai") return "efficient";
  if (route === "retrieval" || route === "reuse") return "retrieval";
  return "local";
}

/** Every value on this screen comes from the server proof, never from the browser. */
export function ProvePhase() {
  const { state, reset } = useRun();
  const [baseline, setBaseline] = useState<BaselineRun | null>(null);
  const [baselineBusy, setBaselineBusy] = useState(false);
  const [baselineAcknowledged, setBaselineAcknowledged] = useState(false);
  const proof = state.active.proof;
  if (!proof) return null;

  const findings = proof.findings ?? [];
  const reviewed = proof.reviewed_items ?? [];
  const tok = proof.tokenomics ?? null;
  const whyAi = proof.why_ai ?? [];
  const passed = proof.outcome.quality_passed;
  const decisionComplete = proof.outcome.decision_complete !== false;
  const unresolvedItems = proof.outcome.unresolved_items ?? 0;
  const cost = proof.economics.total_calculated_cost_usd;

  // ---------------------------------------------------------------------------
  // One run record is the single source of every count on this screen.
  // `proof.routing` describes what actually executed; `proof.usage.model_calls`
  // counts the Foundry requests those operations produced. An operation can be
  // model-assisted without being a separate call, so the two are never conflated.
  // ---------------------------------------------------------------------------
  const totalOps = proof.routing.operations;
  const efficientOps = proof.routing.efficient_ai;
  const advancedOps = proof.routing.advanced_ai;
  const modelAssistedOps = efficientOps + advancedOps;
  const localOps = proof.routing.completed_without_generative_ai;
  const modelCalls = proof.usage.model_calls;
  const totalTokens = proof.usage.input_tokens + proof.usage.output_tokens;

  /** True only when a decision-summary step ran without a generative model. */
  const deterministicSummary = proof.operations.some(
    (operation) => /summary/i.test(operation.label) && !GENERATIVE_ROUTES.has(operation.route)
  );

  // ---------------------------------------------------------------------------
  // Technical-evidence derivations. These only summarise the operation records
  // already in the proof; nothing new is measured or inferred here.
  // ---------------------------------------------------------------------------
  const routeBreakdown = (
    [
      { key: "local", label: "regular software" },
      { key: "retrieval", label: "approved retrieval" },
      { key: "efficient", label: "efficient AI" },
      { key: "advanced", label: "advanced AI" }
    ] as const
  ).map((entry) => ({
    ...entry,
    count: proof.operations.filter((operation) => routeTone(operation.route) === entry.key).length
  }));

  /** Bars are relative, so a single slow step cannot flatten the rest to nothing. */
  const longestOperation = Math.max(
    1,
    ...proof.operations.map((operation) => operation.duration_ms ?? 0)
  );
  const largestInput = Math.max(
    1,
    ...proof.inputs.map((input) => input.extracted_character_count)
  );
  const totalCharacters = proof.inputs.reduce(
    (sum, input) => sum + input.extracted_character_count,
    0
  );
  // Long input lists are truncated here only; the JSON proof keeps every row.
  const INPUT_PREVIEW = 6;
  const visibleInputs = proof.inputs.slice(0, INPUT_PREVIEW);
  const hiddenInputCount = proof.inputs.length - visibleInputs.length;

  const downloadProof = () => {
    const blob = new Blob([JSON.stringify(proof, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${proof.run_id}-proof.json`;
    link.click();
    URL.revokeObjectURL(url);
  };

  // "Same decision" can only be claimed once a paired all-AI run passed the same
  // checks. Until then the headline states what was actually proved.
  const hasVerifiedBaseline = Boolean(
    baseline?.available && baseline.saving_claimable && baseline.equal_quality
  );
  const heading = hasVerifiedBaseline
    ? "Same correct answer. Far less AI. Now proven."
    : !passed
      ? "This run finished, but the answer did not pass its checks."
      : decisionComplete
        ? modelCalls === 0
          ? "Your work is done, and it never needed AI."
          : "Your work is done, and it barely used AI."
        : `Known findings resolved locally. ${
            unresolvedItems === 1
              ? "One material ambiguity requires"
              : `${unresolvedItems} material ambiguities require`
          } AI or human review.`;

  const routeSentence =
    modelCalls === 0
      ? `No Foundry call was required.`
      : modelAssistedOps === modelCalls
        ? `${plural(modelAssistedOps, "operation")} used ${plural(modelCalls, "Foundry call")}.`
        : `${plural(modelAssistedOps, "operation")} were model-assisted in ${plural(
            modelCalls,
            "Foundry call"
          )}.`;

  const summary = !passed
    ? `The workflow completed and verification reported issues. ${
        proof.verification.filter((check) => !check.passed).length
      } check(s) did not pass, so no saving is claimed.`
    : `${plural(totalOps, "operation")}. ${localOps} completed without generative AI. ${routeSentence}`;

  const costPer10k = (cost * 10000).toFixed(2);
  // The paired baseline replays the whole document set through the advanced model
  // in a single request, so the projected all-AI cost is the honest ceiling to show
  // before the user spends anything.
  const projectedBaselineCost = tok?.projected_cost_usd ?? null;

  // ---------------------------------------------------------------------------
  // Before/after claim strength.
  //
  //   "proven"   — the paired all-AI run completed and both routes passed.
  //   "estimate" — nothing extra was spent; the "before" is this run's own token
  //                counts repriced as if every step had used a model.
  //   "none"     — no honest comparison exists, so no benefit is shown.
  //
  // Two separate gates, because they protect against different lies:
  //   * The work-avoided banner needs only passing checks. Local work that really
  //     ran really did cost no tokens.
  //   * The cost comparison additionally needs a *complete* decision. An
  //     unfinished run is cheaper partly because it did less, so comparing it
  //     against a finished all-AI run would be exactly the false economy this
  //     product exists to expose.
  // ---------------------------------------------------------------------------
  const measuredBaseline = hasVerifiedBaseline ? (baseline?.baseline ?? null) : null;
  const workAvoidedShown = passed;
  const claimsAllowed = passed && decisionComplete;
  const evidence: EvidenceTier = !claimsAllowed
    ? "none"
    : measuredBaseline
      ? "proven"
      : "estimate";
  const showComparison = evidence !== "none";

  /** The all-AI cost to compare against: measured when a baseline ran, otherwise
   *  the local estimate. Null when neither is available (e.g. no price table). */
  const comparisonCost = measuredBaseline?.cost_usd ?? projectedBaselineCost;
  const comparisonCalls = measuredBaseline?.model_calls ?? totalOps;
  const evidenceWord = evidence === "proven" ? "proven" : "estimate";
  const beforeLead = measuredBaseline ? "The all-AI version:" : "If AI did every step:";

  /** Only claim a reduction when the comparison is actually cheaper. A governed
   *  run that costs the same or more must say so rather than hide it. */
  const isCheaper = comparisonCost !== null && comparisonCost > cost;
  const percentLower =
    isCheaper && comparisonCost ? Math.round(((comparisonCost - cost) / comparisonCost) * 100) : null;
  const callsAvoided = Math.max(0, comparisonCalls - modelCalls);

  const costChip =
    comparisonCost === null
      ? undefined
      : percentLower !== null
        ? `${percentLower}% lower · ${evidenceWord}`
        : "No reduction found";
  const costChipTier: EvidenceTier = percentLower === null ? "none" : evidence;

  const heroSummary = measuredBaseline
    ? `The all-AI version used a model for all ${comparisonCalls} and reached the same answer.`
    : !decisionComplete
      ? `Ordinary software settled everything the rules could decide. ${plural(
          unresolvedItems,
          "item"
        )} still needs AI or human review before this decision is final.`
      : `Ordinary software handled them — reading files, checking rules, matching amounts. ${
          modelCalls === 0
            ? "No step needed a model."
            : `Only ${plural(modelAssistedOps, "step")} genuinely needed a model.`
        }`;

  return (
    <div className="phase">
      <PhaseIntro heading={heading} supporting={summary} focusKey="prove" />

      {/* 1. THE WIN — how much work never needed a model at all */}
      {workAvoidedShown ? (
        <WorkAvoidedBanner
          localOperations={localOps}
          totalOperations={totalOps}
          completed={decisionComplete}
          detail={heroSummary}
        />
      ) : null}

      {/* 2. BEFORE / AFTER CARDS */}
      <div className="cards prove-cards">
        <ComparisonCard
          title="What this run cost"
          comparison={
            showComparison && comparisonCost !== null ? (
              <span>
                {beforeLead} <strong>{formatUsd(comparisonCost, true)}</strong>
              </span>
            ) : undefined
          }
          value={formatUsd(cost, true)}
          chip={showComparison ? costChip : undefined}
          tier={costChipTier}
          note={
            modelCalls > 0
              ? `${formatCount(totalTokens)} tokens on ${
                  proof.usage.deployments.join(", ") || "Foundry"
                }.`
              : "No model was used, so nothing was spent on tokens."
          }
        />

        <ComparisonCard
          title="How often AI was needed"
          comparison={
            showComparison ? (
              <span>
                {beforeLead} <strong>{plural(comparisonCalls, "time")}</strong>
              </span>
            ) : undefined
          }
          value={modelCalls}
          unit={modelCalls === 1 ? "time" : "times"}
          chip={
            showComparison && callsAvoided > 0
              ? `${plural(callsAvoided, "AI call")} avoided · ${evidenceWord}`
              : undefined
          }
          tier={evidence}
          note={
            modelCalls === 0
              ? "Every step was settled by ordinary software."
              : `Used only for the ${plural(modelAssistedOps, "step")} that needed judgement.`
          }
        />

        <ComparisonCard
          title={measuredBaseline ? "Cost per correct answer" : "Work done by ordinary software"}
          comparison={
            measuredBaseline ? (
              <span>
                {beforeLead} <strong>{formatUsd(measuredBaseline.cost_usd, true)}</strong>
              </span>
            ) : showComparison ? (
              <span>
                {beforeLead} <strong>0 steps</strong>
              </span>
            ) : undefined
          }
          value={measuredBaseline ? formatUsd(cost, true) : localOps}
          unit={measuredBaseline ? undefined : `of ${totalOps} steps`}
          chip={
            measuredBaseline ? "Verified saving" : showComparison ? "No AI tokens used" : undefined
          }
          tier={measuredBaseline ? "proven" : "none"}
          note={
            measuredBaseline
              ? "Counts only answers that passed every quality check."
              : "No AI tokens does not mean free — normal computing and review time still apply."
          }
        />

        <ComparisonCard
          title="Is the answer still correct?"
          comparison={
            measuredBaseline ? (
              <span>
                {beforeLead} <strong>also passed</strong>
              </span>
            ) : undefined
          }
          value={passed && decisionComplete ? "Yes" : passed ? "Incomplete" : "No"}
          valueTone={passed && decisionComplete ? "good" : undefined}
          chip={
            passed && decisionComplete
              ? measuredBaseline
                ? "Both versions passed"
                : `All ${proof.verification.length} checks passed`
              : undefined
          }
          tier="proven"
          note={
            passed && decisionComplete
              ? measuredBaseline
                ? "Both routes were given identical inputs and had to pass identical checks."
                : "Every required check passed against the supplied source material."
              : passed
                ? `Checks passed, but ${plural(unresolvedItems, "item")} still needs review.`
                : "Some quality checks did not pass."
          }
        />
      </div>

      {/* 3. CLAIM STRENGTH — says plainly how strong the comparison is */}
      {evidence === "none" ? (
        <ClaimStrengthBar
          tier="none"
          badge={passed ? "No comparison yet" : "No savings shown"}
          headline={
            passed
              ? "Cost comparisons are held back until the decision is finished."
              : "Cost comparisons are hidden because the answer was not verified."
          }
          detail={
            passed ? (
              <>
                {plural(unresolvedItems, "item")} still needs AI or human review. This run is
                cheaper partly because it has not finished, so comparing it against a completed
                all-AI run would overstate the benefit. Finish the review to see the comparison.
              </>
            ) : (
              <>
                {plural(
                  proof.verification.filter((check) => !check.passed).length,
                  "quality check"
                )}{" "}
                did not pass. You can still see exactly what this run spent, but TokenOS shows no
                saving and no comparison until the answer is correct. A cheaper wrong answer is not
                a saving.
              </>
            )
          }
        />
      ) : measuredBaseline ? (
        <ClaimStrengthBar
          tier="proven"
          badge="Proven saving"
          headline={`${formatUsd(
            measuredBaseline.cost_usd - cost,
            true
          )} cheaper on this run, with the same correct answer.`}
          detail={
            <>
              Both versions used the same documents, the same required answer format, the same
              quality checks and the same prices — and both passed. At 10,000 runs that is about{" "}
              <strong>${((measuredBaseline.cost_usd - cost) * 10000).toFixed(2)}</strong>, which is a
              forecast rather than a measurement.
            </>
          }
        />
      ) : (
        <ClaimStrengthBar
          tier="estimate"
          badge="Estimate"
          headline="These savings are an estimate, not yet proven."
          detail={
            <>
              We calculated it from this run&rsquo;s real token counts, assuming every step had used{" "}
              <strong>
                {tok?.comparison_deployment ||
                  proof.usage.deployments.join(", ") ||
                  "the comparison model"}
              </strong>
              . To prove it, TokenOS can run the same work the all-AI way and measure both.
              {cost > 0 ? ` Projected spend at the current rate: $${costPer10k} per 10,000 runs.` : ""}
            </>
          }
        >
          {/* Links to the acknowledgement gate rather than duplicating it: model
              spend must stay behind a single explicit consent control. */}
          <a className="btn btn-primary" href="#run-all-ai-comparison">
            Run the all-AI comparison
          </a>
        </ClaimStrengthBar>
      )}

      {/* 4. ROUTE PICTURE AND THE REASON A MODEL WAS REACHED.
          The hypothetical all-AI shape sits directly above what actually ran, so
          the contrast is visible without a second route diagram. */}
      <section className="panel route-flow-panel">
        {showComparison ? (
          <div className="route-flow-before">
            <span className="route-flow-before-label">
              {measuredBaseline ? "The all-AI version" : "If AI did every step"}
            </span>
            <span className="route-comparison-step is-ghosted">
              {plural(comparisonCalls, "AI call")}
            </span>
            <span className="route-comparison-arrow">→</span>
            <span className="route-comparison-step is-ghosted">0 steps by software</span>
            <span className="route-comparison-suffix">
              {measuredBaseline ? "measured" : "estimate"}
            </span>
          </div>
        ) : null}
        <div className="route-flow-row">
          <div className="route-flow-step step-local">
            <span className="route-flow-badge">{localOps} local operations</span>
            <span className="route-flow-sub">Software rules, retrieval and templates</span>
          </div>
          <span className="route-flow-arrow">→</span>
          <div className="route-flow-step step-efficient">
            <span className="route-flow-badge">
              {efficientOps} efficient model {efficientOps === 1 ? "operation" : "operations"}
            </span>
            <span className="route-flow-sub">
              {modelCalls > 0 ? `${plural(modelCalls, "Foundry call")} made` : "No call made"}
            </span>
          </div>
          <span className="route-flow-arrow">→</span>
          <div className="route-flow-step step-advanced">
            <span className="route-flow-badge">
              {advancedOps} advanced {advancedOps === 1 ? "escalation" : "escalations"}
            </span>
            <span className="route-flow-sub">Cost ceiling preserved</span>
          </div>
        </div>

        <div className="why-allowed-box">
          <h4>
            {modelCalls === 0
              ? "Why no model call was needed"
              : modelCalls === 1
                ? "Why one model call was allowed"
                : `Why ${modelCalls} model calls were allowed`}
          </h4>
          {modelCalls > 0 ? (
            <p>
              {whyAi[0]?.why_ai ??
                "Deterministic checks could not settle the work, so the efficient model was reached."}{" "}
              TokenOS sent only the unresolved item and the evidence it needed, then verified the
              returned answer against the extracted source text.
              {deterministicSummary
                ? " The decision summary was then formatted deterministically with zero model tokens."
                : ""}
            </p>
          ) : (
            <p>
              Every step was settled deterministically by software rules against the supplied
              evidence. No contested interpretation remained, so no generative tokens were spent.
              {tok?.routing?.note ? ` ${tok.routing.note}` : ""}
            </p>
          )}
        </div>
      </section>

      {/* 3. ROUTE BREAKDOWN */}
      {tok?.routing ? (
        <section className="panel routing-story">
          <div className="routing-heading">
            <div className="section-kicker">Governance</div>
            <h3>Route breakdown</h3>
            <p>
              {plural(totalOps, "operation")} ran. {localOps} completed without generative AI and{" "}
              {routeSentence.charAt(0).toLowerCase() + routeSentence.slice(1)} Only work that needed
              subjective interpretation was allowed to reach a model.
            </p>
          </div>
          <div className="table-wrap">
            <table className="routing-table">
              <thead>
                <tr>
                  <th>What TokenOS did</th>
                  <th className="numeric">Operations</th>
                  <th className="numeric">Model calls</th>
                  <th>Why it matters</th>
                </tr>
              </thead>
              <tbody>
                {tok.routing.rows.map((row) => (
                  <tr key={row.route}>
                    <td>
                      <span className={`route-tag ${row.generative ? "route-ai" : "route-free"}`}>
                        {row.route_label}
                      </span>
                      {row.deferred ? <span className="route-deferred">not run</span> : null}
                      <div className="route-ops">{row.operations.join(" · ")}</div>
                    </td>
                    <td className="numeric">{row.count}</td>
                    <td className="numeric">
                      {row.generative ? (row.model_calls ?? row.executed_on_model) : 0}
                    </td>
                    <td className="muted">{row.why}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="routing-note">
            Operations count the planned steps. Model calls count the Foundry requests those steps
            actually produced, so a single call covering more than one step is never counted twice.
            {tok.routing.note ? ` ${tok.routing.note}` : ""}
          </p>
        </section>
      ) : null}

      {/* 4. WHY EACH PAID CALL WAS AUTHORIZED */}
      {whyAi.length ? (
        <section className="panel why-ai">
          <div className="section-kicker">Audit trail</div>
          <h3>
            {whyAi.length === 1
              ? "Why this Foundry call was authorized"
              : "Why these Foundry calls were authorized"}
          </h3>
          <p className="muted" style={{ marginTop: 0 }}>
            One governance record per paid call. A model is only reached after regular software
            cannot complete and verify the work.
          </p>
          {whyAi.map((call, index) => (
            <div className="why-ai-card" key={`${call.deployment}-${index}`}>
              <div className="why-ai-head">
                <span
                  className={`route-tag ${call.route === "advanced_ai" ? "route-ai" : "route-free"}`}
                >
                  {routeLabel(call.route)} used
                </span>
                <span className="why-ai-cost">{formatUsd(call.calculated_cost_usd, true)}</span>
              </div>
              <p className="why-ai-reason">{call.why_ai}</p>
              <div className="why-ai-facts">
                <span>Deployment: {call.deployment}</span>
                <span>
                  {formatCount(call.input_tokens)} in · {formatCount(call.output_tokens)} out ·{" "}
                  {call.token_source}
                </span>
                {call.quality_check ? (
                  <span>
                    Quality check: {call.quality_check.passed ? "passed" : "failed"} —{" "}
                    {call.quality_check.reason}
                  </span>
                ) : null}
                <span>
                  Approved cost ceiling remaining: {formatUsd(call.ceiling_remaining_usd, true)}
                </span>
              </div>
            </div>
          ))}
        </section>
      ) : null}

      {/* 5. MEASURED ALL-AI COMPARISON */}
      <section className="panel baseline-comparison-section" id="run-all-ai-comparison">
        <div className="section-kicker">Baseline comparison</div>
        <h3>Run measured all-AI comparison</h3>
        <p className="muted" style={{ margin: "4px 0 14px" }}>
          Replays the identical workload through a standard all-AI pipeline using real model calls.
          TokenOS claims a saving only if both paths meet the same citation, amount, and quality
          checks.
        </p>

        {baseline ? (
          <div className={`baseline-result ${baseline.saving_claimable ? "is-verified" : ""}`}>
            {baseline.available && baseline.baseline ? (
              <>
                <div className="baseline-header-row">
                  <strong>
                    {baseline.saving_claimable
                      ? `Verified saving ${formatUsd(baseline.saving_usd ?? 0, true)} per run`
                      : "Both paths ran — no saving claimed"}
                  </strong>
                  <span className="proof-status is-measured">Measured paired run</span>
                </div>
                <div className="baseline-grid">
                  <div className="baseline-col">
                    <span>TokenOS governed route</span>
                    <div className="baseline-cost">
                      {formatUsd(baseline.governed.cost_usd, true)}
                    </div>
                    <div className="baseline-meta">
                      {formatCount(baseline.governed.tokens)} tokens ·{" "}
                      {plural(baseline.governed.model_calls, "model call")} ·{" "}
                      {baseline.governed.quality_passed ? "quality passed" : "quality failed"}
                    </div>
                  </div>
                  <div className="baseline-col">
                    <span>All-AI baseline (executed)</span>
                    <div className="baseline-cost">
                      {formatUsd(baseline.baseline.cost_usd, true)}
                    </div>
                    <div className="baseline-meta">
                      {formatCount(baseline.baseline.tokens)} tokens ·{" "}
                      {plural(baseline.baseline.model_calls, "model call")} ·{" "}
                      {baseline.baseline.quality_passed ? "quality passed" : "quality failed"}
                    </div>
                  </div>
                </div>
                {baseline.saving_blocked_reason ? (
                  <p className="baseline-warning">{baseline.saving_blocked_reason}</p>
                ) : null}
              </>
            ) : (
              <>
                <strong>Paired baseline not available</strong>
                <p className="muted">{baseline.reason}</p>
              </>
            )}
          </div>
        ) : (
          <div className="baseline-cta-panel">
            <div className="baseline-cta-meta">
              Uses up to 1 Foundry call over the full document set.{" "}
              {projectedBaselineCost !== null
                ? `Estimated maximum model spend: ${formatUsd(projectedBaselineCost, true)}.`
                : "Projected spend is calculated from the measured token volume at advanced-model rates."}{" "}
              The actual cost is measured from the model response.
            </div>
            <label className="baseline-ack-checkbox">
              <input
                type="checkbox"
                checked={baselineAcknowledged}
                onChange={(event) => setBaselineAcknowledged(event.target.checked)}
              />
              <span>I understand this comparison invokes a model and may incur model cost.</span>
            </label>
            <button
              type="button"
              className="btn btn-primary"
              disabled={baselineBusy || !baselineAcknowledged}
              onClick={async () => {
                setBaselineBusy(true);
                try {
                  setBaseline(await api.compareBaseline(proof.run_id, true));
                } catch (error) {
                  setBaseline({
                    available: false,
                    status: "baseline_failed",
                    saving_claimable: false,
                    reason: error instanceof Error ? error.message : "The comparison failed.",
                    governed: {
                      cost_usd: cost,
                      quality_passed: passed,
                      findings: findings.length,
                      model_calls: modelCalls,
                      tokens: totalTokens
                    },
                    baseline: null
                  });
                } finally {
                  setBaselineBusy(false);
                }
              }}
            >
              {baselineBusy ? "Executing all-AI baseline…" : "Run measured all-AI comparison"}
            </button>
          </div>
        )}
      </section>

      {/* 6. OUTCOME EVIDENCE (collapsed) */}
      {findings.length || reviewed.length ? (
        <details className="panel collapsible-evidence outcome-evidence-details">
          <summary className="evidence-summary-btn">
            <div>
              <div className="section-kicker">Workload verification</div>
              <h3 style={{ display: "inline", margin: 0 }}>
                Outcome evidence: why quality passed ({plural(findings.length, "finding")},{" "}
                {reviewed.length} charges reviewed)
              </h3>
            </div>
            <span className="summary-toggle-icon">▼</span>
          </summary>

          <div className="evidence-content" style={{ marginTop: 16 }}>
            <p className="muted" style={{ margin: "0 0 16px" }}>
              The supplier review is the controlled workload TokenOS ran against. These records
              exist to show the outcome was preserved while unnecessary AI calls were avoided.
            </p>

            {findings.length ? (
              <div className="finding-grid">
                {findings.map((item, index) => {
                  const rejected = item.recommendation === "reject";
                  return (
                    <article
                      className={`finding-card ${rejected ? "finding-reject" : "finding-evidence"}`}
                      key={`${item.document}-${item.line ?? index}-${item.finding}`}
                    >
                      <div className="finding-card-header">
                        <div>
                          <div className="finding-number">Finding {index + 1}</div>
                          <h4>
                            {rejected
                              ? "Do not pay"
                              : item.recommendation === "needs_interpretation"
                                ? "Needs interpretation"
                                : "Approval or evidence needed"}
                          </h4>
                        </div>
                        {item.amount_usd !== null ? (
                          <strong className="finding-amount">{formatUsd(item.amount_usd)}</strong>
                        ) : null}
                      </div>
                      <p className="finding-description">{item.finding}</p>
                      <div className="finding-action">
                        <span>Next step</span>
                        <strong>
                          {rejected
                            ? "Remove this charge from payment."
                            : item.recommendation === "needs_interpretation"
                              ? "Route to reviewer or model interpretation."
                              : "Provide required approval reference."}
                        </strong>
                      </div>
                      <div className="finding-meta">
                        <div>
                          <span>Invoice line</span>
                          <strong>{item.line ?? "Not supplied"}</strong>
                        </div>
                        <div>
                          <span>Policy rule</span>
                          <strong>{item.policy_citation}</strong>
                        </div>
                      </div>
                      <blockquote>
                        <span>Source evidence</span>
                        {item.source_excerpt}
                      </blockquote>
                    </article>
                  );
                })}
              </div>
            ) : null}

            {reviewed.length ? (
              <div className="reviewed-block" style={{ marginTop: 20 }}>
                <div className="reviewed-heading">
                  <h4>Every charge reviewed</h4>
                  <p className="muted" style={{ margin: "4px 0 12px" }}>
                    All {reviewed.length} charge{reviewed.length === 1 ? "" : "s"} evaluated against
                    policy rules.
                  </p>
                </div>
                <div className="table-wrap">
                  <table className="reviewed-table">
                    <thead>
                      <tr>
                        <th>Line</th>
                        <th>Charge</th>
                        <th className="numeric">Amount</th>
                        <th>Decision</th>
                        <th>Why</th>
                      </tr>
                    </thead>
                    <tbody>
                      {reviewed.map((item, index) => (
                        <tr key={`${item.document}-${item.line ?? index}-${item.label}`}>
                          <td>{item.line ?? "—"}</td>
                          <td>{item.label}</td>
                          <td className="numeric">{formatUsd(item.amount_usd)}</td>
                          <td>
                            <span className={`decision-tag decision-${item.outcome}`}>
                              {DECISION_LABEL[item.outcome] ?? item.outcome}
                            </span>
                          </td>
                          <td className="reviewed-why">
                            {item.reason}
                            {item.policy_citation ? (
                              <span className="muted">{item.policy_citation}</span>
                            ) : null}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : null}
          </div>
        </details>
      ) : null}

      {/* 7. TECHNICAL EVIDENCE (collapsed) */}
      <details className="panel collapsible-evidence technical-evidence-details">
        <summary className="evidence-summary-btn">
          <div>
            <div className="section-kicker">Audit and reproducible proof</div>
            <h3 style={{ display: "inline", margin: 0 }}>Technical evidence and run proof</h3>
          </div>
          <span className="summary-toggle-icon">▼</span>
        </summary>

        <div className="evidence-content stack" style={{ marginTop: 16 }}>
          {/* Identity as chips: a wrapping grid left ragged gaps whenever one
              workflow had longer values than another. */}
          <div className="evidence-identity">
            <span className="evidence-tag is-mono">
              <i>Run</i>
              <b>{proof.run_id}</b>
            </span>
            <span className="evidence-tag">
              <i>Workflow</i>
              <b>{proof.workflow_id}</b>
            </span>
            <span className="evidence-tag">
              <i>Inputs</i>
              <b>
                {proof.input_evidence} · {plural(proof.inputs.length, "file")}
              </b>
            </span>
            <span className="evidence-tag">
              <i>Tokens</i>
              <b>
                {formatCount(proof.usage.input_tokens)} in ·{" "}
                {formatCount(proof.usage.output_tokens)} out
              </b>
            </span>
            <span className="evidence-tag">
              <i>Wall time</i>
              <b>{formatDuration(proof.usage.duration_ms)}</b>
            </span>
            <span className="evidence-tag is-mono">
              <i>Model</i>
              <b>
                {proof.usage.deployments.length
                  ? proof.usage.deployments.join(", ")
                  : `${proof.usage.model_mode} · no model route used`}
              </b>
            </span>
            <span className="evidence-tag is-sample">
              <i>Measured</i>
              <b>{proof.measurement_label.replace(/^Measured\s+/i, "")}</b>
            </span>
          </div>

          {/* The routing decision is the point of the product, so show its shape
              before the per-row detail. Counts come from the operation records. */}
          <div className="route-ladder">
            <div className="route-ladder-head">
              <span className="route-ladder-title">
                How the {plural(totalOps, "operation")} {totalOps === 1 ? "was" : "were"} routed
              </span>
              <span className="route-ladder-sub">
                {modelCalls === 0
                  ? "No model call was needed"
                  : `${plural(modelCalls, "model call")} · ${formatUsd(cost, true)} measured`}
              </span>
            </div>
            <div className="route-ladder-bar">
              {routeBreakdown.map((entry) =>
                entry.count ? (
                  <span
                    key={entry.key}
                    className={`route-ladder-seg is-${entry.key}`}
                    style={{ width: `${(entry.count / totalOps) * 100}%` }}
                  />
                ) : null
              )}
            </div>
            <div className="route-ladder-legend">
              {routeBreakdown.map((entry) => (
                <span key={entry.key}>
                  <span className={`route-ladder-dot is-${entry.key}`} aria-hidden="true" />
                  <b>{entry.count}</b> {entry.label}
                </span>
              ))}
            </div>
          </div>

          <div className="evidence-section-head">
            <h4>Operations</h4>
            <span>
              {plural(totalOps, "step")} ·{" "}
              {modelCalls === 0 ? "none reached a model" : `${modelAssistedOps} reached a model`}
            </span>
          </div>
          <div className="table-wrap">
            <table className="evidence-table">
              <caption className="sr-only">Operations, routes, and measured cost</caption>
              <thead>
                <tr>
                  <th>Operation</th>
                  <th>Route</th>
                  <th className="numeric">Duration</th>
                  <th className="numeric">Cost</th>
                </tr>
              </thead>
              <tbody>
                {proof.operations.map((operation) => {
                  const spend = operation.actual_cost_usd ?? 0;
                  const duration = operation.duration_ms ?? 0;
                  const tone = routeTone(operation.route);
                  return (
                    <tr key={operation.operation_id} className={spend > 0 ? `is-paid is-${tone}` : ""}>
                      <td className="evidence-op">{operation.label}</td>
                      <td>
                        <span className={`route-pill is-${tone}`}>{routeLabel(operation.route)}</span>
                      </td>
                      <td>
                        <span className="evidence-meter">
                          <span
                            className={`evidence-meter-bar is-${tone}`}
                            style={{
                              width: `${Math.max(2, Math.round((duration / longestOperation) * 110))}px`
                            }}
                          />
                          <span className={`numeric${duration < 1 ? " muted" : ""}`}>
                            {formatDuration(duration)}
                          </span>
                        </span>
                      </td>
                      <td className={`numeric${spend > 0 ? ` evidence-cost is-${tone}` : " muted"}`}>
                        {spend > 0 ? formatUsd(spend, true) : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
              <tfoot>
                <tr>
                  <td>Total</td>
                  <td className="muted">
                    {localOps} of {totalOps} used no model
                  </td>
                  <td className="numeric">{formatDuration(proof.usage.duration_ms)}</td>
                  <td className={`numeric${cost > 0 ? " evidence-cost is-efficient" : " muted"}`}>
                    {cost > 0 ? formatUsd(cost, true) : "—"}
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>

          <div className="evidence-section-head">
            <h4>Inputs read by the server</h4>
            <span>
              {plural(proof.inputs.length, "file")} ·{" "}
              {formatCount(totalCharacters)} characters · SHA-256 pinned
            </span>
          </div>
          <div className="table-wrap">
            <table className="evidence-table">
              <caption className="sr-only">Inputs read by the server</caption>
              <thead>
                <tr>
                  <th>File</th>
                  <th>SHA-256</th>
                  <th className="numeric">Characters</th>
                </tr>
              </thead>
              <tbody>
                {visibleInputs.map((input) => (
                  <tr key={input.upload_id}>
                    <td>
                      <span className="evidence-file">{input.name}</span>
                      <span className="evidence-role">{input.role}</span>
                    </td>
                    <td>
                      <button
                        type="button"
                        className="evidence-hash"
                        title={`${input.sha256} — click to copy`}
                        onClick={() => void navigator.clipboard?.writeText(input.sha256)}
                      >
                        {input.sha256.slice(0, 16)}…
                      </button>
                    </td>
                    <td>
                      <span className="evidence-meter">
                        <span
                          className="evidence-meter-bar is-chars"
                          style={{
                            width: `${Math.max(
                              2,
                              Math.round(
                                (input.extracted_character_count / largestInput) * 110
                              )
                            )}px`
                          }}
                        />
                        <span className="numeric">
                          {formatCount(input.extracted_character_count)}
                        </span>
                      </span>
                    </td>
                  </tr>
                ))}
                {hiddenInputCount ? (
                  <tr>
                    <td colSpan={3} className="muted evidence-more">
                      …{plural(hiddenInputCount, "more file")}. The full list stays in the JSON run
                      proof.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>

          {/* The prose belongs to auditors, so it sits after the evidence rather
              than in front of it. */}
          <div className="evidence-section-head">
            <h4>How to check this yourself</h4>
            <span />
          </div>
          {tok ? (
            <details className="evidence-disclosure">
              <summary>How the cost was calculated</summary>
              <div className="evidence-disclosure-body">
                {tok.basis}. Input tokens are counted from the text each operation actually read, and
                output tokens from the result it actually produced. Only the routing of the
                comparator is hypothetical — the token counts are measured.
                {tok.price_effective_date
                  ? ` Price effective ${tok.price_effective_date}${
                      tok.price_source ? ` · ${tok.price_source}` : ""
                    }.`
                  : ""}
              </div>
            </details>
          ) : null}

          {proof.comparison_contract ? (
            <details className="evidence-disclosure">
              <summary>Comparison contract — what makes this comparison valid</summary>
              <div className="evidence-disclosure-body">
                <ul>
                  <li>Prompt version: {proof.comparison_contract.prompt_version}</li>
                  <li>Output schema: {proof.comparison_contract.output_schema_version}</li>
                  <li>
                    Maximum output length: {proof.comparison_contract.max_output_tokens} tokens, both
                    routes
                  </li>
                  <li>Citation requirement: {proof.comparison_contract.citation_requirement}</li>
                  <li>Quality checks: {proof.comparison_contract.quality_checks.join(", ")}</li>
                  <li>Test set: {proof.comparison_contract.test_set}</li>
                </ul>
                {proof.comparison_contract.note}
              </div>
            </details>
          ) : null}

          <div className="raw-proof-box">
            <p className="muted" style={{ margin: "0 0 8px", fontSize: 12.5 }}>
              The complete signed run record — every operation, route decision, token count, and
              price reference — is available as JSON for independent verification.
            </p>
            <button type="button" className="btn btn-sm" onClick={downloadProof}>
              Download JSON run proof
            </button>
          </div>
        </div>
      </details>

      {/* 8. ACTIONS */}
      <div className="btn-row" style={{ marginTop: 20 }}>
        <button type="button" className="btn btn-primary" onClick={reset}>
          Start another run
        </button>
        <button type="button" className="btn" onClick={downloadProof}>
          Download run proof
        </button>
      </div>
    </div>
  );
}
