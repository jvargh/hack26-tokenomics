import { useState } from "react";
import { api } from "../api/client";
import type { BaselineRun } from "../api/types";
import { useRun } from "../state/runContext";
import { PhaseIntro } from "../components/shared/PhaseIntro";
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
    ? "Same verified decision. Fewer AI calls. Lower measured cost."
    : !passed
      ? "Completed with findings"
      : decisionComplete
        ? "Verified review decision. Minimal AI use. Measured cost proof."
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

  return (
    <div className="phase">
      <PhaseIntro heading={heading} supporting={summary} focusKey="prove" />

      {/* 1. ECONOMICS PROOF */}
      <div className="cards prove-cards">
        <div className="card">
          <div className="card-label">Model spend</div>
          <div className="card-value">{formatUsd(cost, true)}</div>
          <div className="card-note">
            {modelCalls > 0
              ? `${formatCount(totalTokens)} tokens on ${
                  proof.usage.deployments.join(", ") || "Foundry"
                }`
              : "Zero model spend · every operation completed locally"}
          </div>
          <div className="proof-status is-measured">
            {modelCalls > 0 ? "Measured · model response usage" : "Measured · no model spend"}
          </div>
        </div>

        <div className="card">
          <div className="card-label">Model calls</div>
          <div className="card-value">
            {modelCalls}{" "}
            <span className="card-value-sub">
              {modelCalls === 1 ? "model call" : "model calls"} across {totalOps} operations
            </span>
          </div>
          <div className="card-note">
            {modelCalls > 0
              ? `${modelAssistedOps} model-assisted ${
                  modelAssistedOps === 1 ? "operation" : "operations"
                } · ${advancedOps} advanced ${advancedOps === 1 ? "escalation" : "escalations"}`
              : "0 calls needed · every rule resolved locally"}
          </div>
          <div className="proof-status is-measured">
            {modelCalls === 0
              ? "No model call authorized"
              : `${plural(modelCalls, "model call")} authorized`}
          </div>
        </div>

        <div className="card">
          <div className="card-label">Non-AI operations</div>
          <div className="card-value">
            {localOps} <span className="card-value-sub">of {totalOps} completed locally</span>
          </div>
          <div className="card-note">
            Deterministic rules, duplicate hashing, approved retrieval, and the decision summary
          </div>
          <div className="proof-status is-measured">Zero tokens spent</div>
        </div>

        <div className="card">
          <div className="card-label">Outcome verification</div>
          <div className={`card-value ${passed && decisionComplete ? "text-good" : ""}`}>
            {passed && decisionComplete ? "Passed" : passed ? "Incomplete" : "Failed"}
          </div>
          <div className="card-note">
            {passed && decisionComplete
              ? "Citations, amounts and limits verified against source text"
              : passed
                ? `Deterministic checks passed · ${unresolvedItems} item(s) unresolved`
                : "Verification checks failed"}
          </div>
          <div
            className={`proof-status ${passed && decisionComplete ? "is-measured" : "is-incomplete"}`}
          >
            {decisionComplete ? "Outcome verified" : "Decision incomplete"}
          </div>
        </div>
      </div>

      {/* Volume rate projection — never described as a saving before a paired run */}
      <div className="volume-projection-box">
        <div className="volume-projection-main">
          {hasVerifiedBaseline && baseline?.baseline ? (
            <span>
              <strong>Verified saving at 10,000 equivalent runs:</strong>{" "}
              <strong className="text-good">
                ${((baseline.baseline.cost_usd - cost) * 10000).toFixed(2)}
              </strong>{" "}
              (${costPer10k} TokenOS governed against $
              {(baseline.baseline.cost_usd * 10000).toFixed(2)} measured all-AI baseline, both paths
              passing the same checks).
            </span>
          ) : (
            <span>
              <strong>Projected spend at the current measured run rate:</strong> ${costPer10k} per
              10,000 equivalent runs.{" "}
              <span className="volume-projection-disclaimer">Not a verified saving.</span>
            </span>
          )}
        </div>
      </div>

      {/* 2. ROUTE FLOW AND THE REASON A MODEL WAS REACHED */}
      <section className="panel route-flow-panel">
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
                "Deterministic policy checks could not settle a contested charge, so the efficient model was reached."}{" "}
              TokenOS sent only the contested charge and the relevant policy excerpt, then verified
              the returned citation and amount against the extracted source text.
              {deterministicSummary
                ? " The decision summary was then formatted deterministically with zero model tokens."
                : ""}
            </p>
          ) : (
            <p>
              Every charge line was settled deterministically by software rules against the policy
              thresholds. No contested interpretation remained, so no generative tokens were spent.
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
              {plural(totalOps, "review operation")} ran. {localOps} completed without generative AI
              and {routeSentence.charAt(0).toLowerCase() + routeSentence.slice(1)} Only charges
              requiring subjective policy interpretation were allowed to reach a model.
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
      <section className="panel baseline-comparison-section">
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
          {tok ? (
            <div className="economics-basis-box">
              <strong>How this is calculated.</strong> {tok.basis}. Input tokens are counted from the
              text each operation actually read, and output tokens from the result it actually
              produced. Only the routing of the comparator is hypothetical — the token counts are
              measured.
              {tok.price_effective_date
                ? ` Price effective ${tok.price_effective_date}${
                    tok.price_source ? ` · ${tok.price_source}` : ""
                  }.`
                : ""}
            </div>
          ) : null}

          {proof.comparison_contract ? (
            <div className="contract-block">
              <strong>Comparison contract — what makes this comparison valid</strong>
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
              <p className="muted" style={{ margin: "6px 0 0", fontSize: 12 }}>
                {proof.comparison_contract.note}
              </p>
            </div>
          ) : null}

          <dl
            className="evidence-list"
            style={{ gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))" }}
          >
            <div>
              <dt>Run ID</dt>
              <dd>{proof.run_id}</dd>
            </div>
            <div>
              <dt>Workflow</dt>
              <dd>{proof.workflow_id}</dd>
            </div>
            <div>
              <dt>Input evidence</dt>
              <dd>
                {proof.input_evidence} · {proof.inputs.length} file(s)
              </dd>
            </div>
            <div>
              <dt>Model mode</dt>
              <dd>
                {proof.usage.model_mode}
                {proof.usage.deployments.length
                  ? ` · ${proof.usage.deployments.join(", ")}`
                  : " · no model route used"}
              </dd>
            </div>
            <div>
              <dt>Measurement</dt>
              <dd>{proof.measurement_label}</dd>
            </div>
            <div>
              <dt>Measured usage</dt>
              <dd>
                {formatCount(proof.usage.input_tokens)} in · {formatCount(proof.usage.output_tokens)}{" "}
                out · {formatDuration(proof.usage.duration_ms)}
              </dd>
            </div>
          </dl>

          <div className="table-wrap">
            <table>
              <caption>Inputs read by the server</caption>
              <thead>
                <tr>
                  <th>File</th>
                  <th>Role</th>
                  <th>SHA-256</th>
                  <th className="numeric">Characters</th>
                </tr>
              </thead>
              <tbody>
                {proof.inputs.map((input) => (
                  <tr key={input.upload_id}>
                    <td>{input.name}</td>
                    <td>{input.role}</td>
                    <td>{input.sha256.slice(0, 16)}…</td>
                    <td className="numeric">{formatCount(input.extracted_character_count)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="table-wrap">
            <table>
              <caption>Operations, routes, and measured cost</caption>
              <thead>
                <tr>
                  <th>Operation</th>
                  <th>Route</th>
                  <th className="numeric">Duration</th>
                  <th className="numeric">Cost</th>
                </tr>
              </thead>
              <tbody>
                {proof.operations.map((operation) => (
                  <tr key={operation.operation_id}>
                    <td>{operation.label}</td>
                    <td>{routeLabel(operation.route)}</td>
                    <td className="numeric">{formatDuration(operation.duration_ms ?? 0)}</td>
                    <td className="numeric">{formatUsd(operation.actual_cost_usd ?? 0, true)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

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
