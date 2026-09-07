import { useRef, useState, type ReactNode } from "react";
import { PhaseIntro, SectionHead } from "../components/shared/PhaseIntro";
import { ComparisonCard, WorkAvoidedBanner } from "../components/shared/Comparison";
import type { OptimizationComparison, OptimizationGate, OptimizationRecord, OptimizationUsage, PromptPlan } from "./types";

export function numberValue(value?: number): string {
  return typeof value === "number" && Number.isFinite(value) ? value.toLocaleString() : "Unavailable";
}

export function dollars(value?: number): string {
  return typeof value === "number" && Number.isFinite(value)
    ? value.toLocaleString("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 6 })
    : "Unavailable";
}

export function aliasName(value: string): string {
  if (!value || value === "unknown") return "Not observed";
  if (/^imported-model-\d+$/.test(value)) return `Imported model ${value.split("-").pop()}`;
  if (["tokenos-efficient", "tokenos-advanced", "tokenos-baseline"].includes(value)) return value;
  if (/efficient/i.test(value)) return "tokenos-efficient";
  if (/advanced/i.test(value)) return "tokenos-advanced";
  if (/baseline/i.test(value)) return "tokenos-baseline";
  if (/reuse|cache/i.test(value)) return "Validated reuse";
  if (/local|software|deterministic|retrieval|rule|test/i.test(value)) return "Local software";
  if (/model|ai/i.test(value)) return "Model route";
  return "Imported route";
}

export function SampleBadge({ sample }: { sample: boolean }) {
  return sample ? <span className="optimization-badge">Measured sample run</span> : null;
}

export function GateList({ checks }: { checks: OptimizationGate[] }) {
  return <ul className="optimization-checks">
    {checks.length === 0 && <li className="muted">No checks recorded yet.</li>}
    {checks.map((check) => <li key={check.id} className={`optimization-check ${check.passed === true ? "passed" : ""}`}>
      <span aria-hidden="true">{check.passed === true ? "✓" : check.passed === false ? "!" : "–"}</span>
      <div><strong>{check.name}</strong>
        <span className={`optimization-badge ${check.passed === true ? "good" : "warn"}`} style={{ marginLeft: 8 }}>
          {check.passed === true ? "Passed" : check.passed === false ? "Failed" : "Not checked"}
        </span>
        <p>{check.detail}</p>{check.passed !== true && check.action && <p><strong>Next step:</strong> {check.action}</p>}
      </div>
    </li>)}
  </ul>;
}

function Metric({ title, value, note, sample }: { title: string; value: ReactNode; note: string; sample: boolean }) {
  return <div className="optimization-metric"><span>{title}</span><strong>{value}</strong><small>{note}</small><SampleBadge sample={sample} /></div>;
}

function Facts({ facts }: { facts: Array<[string, ReactNode]> }) {
  return <dl className="optimization-facts">{facts.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>;
}

function outputContractSummary(value: unknown): string {
  if (!value || typeof value !== "object" || Array.isArray(value)) return "Unavailable";
  const contract = value as Record<string, unknown>;
  const required = Array.isArray(contract.required) ? contract.required.filter((item): item is string => typeof item === "string") : [];
  return `Structured ${typeof contract.type === "string" ? contract.type : "output"}${required.length ? ` · required: ${required.join(", ")}` : ""}`;
}

function idList(values: string[]): ReactNode {
  return values.length ? <ul className="optimization-compact-list">{values.map((value) => <li key={value}>{value}</li>)}</ul> : "Unavailable";
}

function PromptPlanView({ plan }: { plan: PromptPlan }) {
  return <>
    <section className="panel"><SectionHead title="Prompt composition" supporting="Every amount in this plan is Estimated until the governed prompt runs and provider usage is recorded." />
      <div className="optimization-table-wrap"><table className="optimization-table">
        <thead><tr><th>Prompt component</th><th>Current estimated amount</th><th>Candidate treatment</th><th>Reason</th></tr></thead>
        <tbody>{plan.current.components.map((component) => <tr key={component.id || component.label}>
          <td>{component.label || component.id}</td>
          <td>{component.estimatedTokens !== undefined ? `Estimated ${numberValue(component.estimatedTokens)} tokens` : "Estimated unavailable"}</td>
          <td>{component.candidateTreatment || "Awaiting treatment"}</td><td>{component.reason || "No reason recorded"}</td>
        </tr>)}</tbody>
      </table></div>
      {!plan.current.components.length && <p className="muted">Prompt components have not been returned by the server.</p>}
      <Facts facts={[
        ["Current estimated input", plan.current.estimatedInputTokens !== undefined ? `Estimated ${numberValue(plan.current.estimatedInputTokens)} tokens` : "Estimated unavailable"],
        ["Candidate estimated input", plan.candidate.estimatedInputTokens !== undefined ? `Estimated ${numberValue(plan.candidate.estimatedInputTokens)} tokens` : "Estimated unavailable"],
        ["Estimated reduction", plan.candidate.estimatedReductionTokens !== undefined ? `Estimated ${numberValue(plan.candidate.estimatedReductionTokens)} tokens` : "Estimated unavailable"],
        ["Cache eligibility", plan.candidate.cacheEligibility.replace(/_/g, " ") || "unknown"],
        ["Recommended route", aliasName(plan.candidate.recommendedModelAlias || "unknown")],
        ["Output contract", outputContractSummary(plan.candidate.outputContract)]
      ]} />
      {plan.candidate.cacheReason && <p className="muted">{plan.candidate.cacheReason}</p>}
      {plan.candidate.routeReason && <p className="muted">{plan.candidate.routeReason}</p>}
    </section>
    <section className="panel"><SectionHead title="Potential improvements" supporting="These are candidate changes that still require safeguards and execution before any measured economics exist." />
      <ul>{(plan.improvements.length ? plan.improvements : [
        "Remove repeated or conflicting instructions.",
        "Replace open-ended response request with an output contract.",
        "Minimize attached context to relevant evidence.",
        "Preserve a stable prefix for provider cache eligibility.",
        "Use local rules or retrieval when an answer can be verified without a model.",
        "Route bounded interpretation to an efficient model.",
        "Reserve advanced reasoning for failed quality verification."
      ]).map((improvement) => <li key={improvement}>{improvement}</li>)}</ul>
      {!!plan.contextDecisions.length && <details><summary>Context decisions</summary>
        <div className="optimization-table-wrap"><table className="optimization-table">
          <thead><tr><th>Context</th><th>Decision</th><th>Estimated amount</th><th>Reason</th></tr></thead>
          <tbody>{plan.contextDecisions.map((decision) => <tr key={decision.id || decision.sourceId}>
            <td>{decision.label || decision.sourceId}</td><td>{decision.decision.replace(/_/g, " ")}</td>
            <td>{decision.estimatedTokens !== undefined ? `Estimated ${numberValue(decision.estimatedTokens)} tokens` : "Estimated unavailable"}</td>
            <td>{decision.reason || "No reason recorded"}</td>
          </tr>)}</tbody>
        </table></div>
      </details>}
    </section>
  </>;
}

function OperationTable({ record }: { record: OptimizationRecord }) {
  return <div className="optimization-table-wrap"><table className="optimization-table">
    <thead><tr><th>Operation</th><th>Current route</th><th>Candidate route</th><th>Reason</th><th>Cost/evidence status</th></tr></thead>
    <tbody>{record.operations.map((operation) => <tr key={operation.id}>
      <td>{operation.label}</td><td>{aliasName(operation.currentRoute)}</td><td>{aliasName(operation.route)}</td>
      <td>{operation.reason}</td><td>{operation.evidenceStatus || "Estimated until execution"}</td>
    </tr>)}</tbody>
  </table></div>;
}

export function PlanView({ record, busy, onApprove, onEdit }: {
  record: OptimizationRecord; busy: boolean; onApprove: () => void; onEdit: () => void;
}) {
  const current = record.current;
  if (record.optimizationTarget === "single_prompt" && record.promptPlan) {
    return <>
      <PhaseIntro heading="Understand the prompt before changing the route"
        supporting="This plan is built locally and deterministically. No model has been invoked." focusKey="optimization-plan" />
      <PromptPlanView plan={record.promptPlan} />
      <section className="panel"><SectionHead title="Plan controls" supporting="Approving this plan only moves to the proposed governed package. It does not run a model." />
        <details><summary>View assumptions</summary>
          {record.assumptions.length ? <ul>{record.assumptions.map((assumption, index) => <li key={index}>{assumption}</li>)}</ul>
            : <p className="muted">Prompt plan values are Estimated until a protected run records provider usage. Missing server fields remain unavailable, not zero.</p>}
        </details>
        <div className="btn-row btn-row-end">
          <button type="button" className="btn" onClick={onEdit} disabled={busy}>Edit inputs</button>
          <button type="button" className="btn btn-primary" onClick={onApprove} disabled={busy}>Approve optimization plan</button>
        </div>
      </section>
    </>;
  }
  return <>
    <PhaseIntro heading="Understand the work before changing the route"
      supporting="This plan is built locally and deterministically. No model has been invoked." focusKey="optimization-plan" />
    <section className="panel"><SectionHead title="Current workflow map" supporting="Observed source telemetry is kept separate from candidate-route estimates." />
      <Facts facts={[
        ["Representative requests", numberValue(current.requests)],
        ["Accepted outcomes", numberValue(current.accepted)],
        ["Model calls per accepted outcome", numberValue(current.callsPerAccepted)],
        ["Input / output tokens", `${numberValue(current.inputTokens)} / ${numberValue(current.outputTokens)}`],
        ["Cached / reasoning tokens", `${numberValue(current.cachedTokens)} / ${numberValue(current.reasoningTokens)}`],
        ["Measured current cost per accepted outcome", dollars(current.costPerAcceptedUsd)],
        ["Retries / failures", `${numberValue(current.retries)} / ${numberValue(current.failures)}`],
        ["Human corrections", numberValue(current.corrections)],
        ["Observed latency", current.latencyMs !== undefined ? `${numberValue(current.latencyMs)} ms`
          : current.latencySamples?.length ? `${current.latencySamples.map((value) => numberValue(value)).join(", ")} ms` : "Unavailable"],
        ["Imported-data completeness", record.completeness],
        ["Current model distribution", current.modelDistribution.length
          ? current.modelDistribution.map((model) => `${aliasName(model.alias)}: ${numberValue(model.calls)} calls`).join(" · ") : "Not present in source telemetry"]
      ]} />
      <SampleBadge sample={record.sample} />
    </section>
    <section className="panel"><SectionHead title="Planned operations" supporting="Software and retrieval first; model use remains conditional on quality needs and authorization." />
      <OperationTable record={record} />
      <details><summary>View data assumptions</summary>
        {record.assumptions.length ? <ul>{record.assumptions.map((assumption, index) => <li key={index}>{assumption}</li>)}</ul>
          : <p className="muted">Missing telemetry remains unavailable. Candidate effects are estimates until measured execution.</p>}
        <p className="muted">Current model routes are represented by safe aliases. Planning never grants permission to execute a model.</p>
      </details>
      <div className="btn-row btn-row-end">
        <button type="button" className="btn" onClick={onEdit} disabled={busy}>Edit requirements</button>
        <button type="button" className="btn btn-primary" onClick={onApprove} disabled={busy}>Approve optimization plan</button>
      </div>
    </section>
  </>;
}

export function OptimizeView({ record, busy, onProtect }: { record: OptimizationRecord; busy: boolean; onProtect: () => void }) {
  const [copyStatus, setCopyStatus] = useState("");
  if (record.optimizationTarget === "single_prompt") {
    const plan = record.promptPlan;
    const governedPrompt = plan?.candidate.governedPrompt || record.promptProof?.governedPrompt || "";
    const copyGovernedPrompt = async () => {
      if (!governedPrompt) return;
      try {
        await navigator.clipboard.writeText(governedPrompt);
        setCopyStatus("Governed prompt copied. No model spend was triggered.");
      } catch {
        setCopyStatus("Copy unavailable in this browser. Select the governed prompt text to copy it.");
      }
    };
    return <>
      <PhaseIntro heading="Review the governed prompt package"
        supporting="This is a proposed package only. It is not a completed optimization until safeguards are authorized, the governed prompt runs, and results are measured." focusKey="optimization-optimize" />
      <section className="panel"><SectionHead title="Current prompt package vs TokenOS governed prompt package"
        supporting="Copying the governed prompt does not invoke a model or authorize spend." />
        <div className="optimization-side-by-side">
          <article className="optimization-package">
            <h4>Current prompt package</h4>
            <ul>
              <li>Original prompt and all submitted context</li>
              <li>{plan?.current.currentModel || "Current/default model"}</li>
              <li>Unbounded prose request</li>
              <li>Repeated stable content</li>
            </ul>
            <p className="muted">Original prompt content remains in the server proof. Blocked content is not exposed here.</p>
          </article>
          <article className="optimization-package">
            <h4>TokenOS governed prompt package</h4>
            <ul>
              <li>Concise task instructions plus only eligible context</li>
              <li>{aliasName(plan?.candidate.recommendedModelAlias || "unknown")} with escalation condition</li>
              <li>{outputContractSummary(plan?.candidate.outputContract)} and output limit</li>
              <li>{plan?.candidate.cacheEligibility ? `Cache eligibility: ${plan.candidate.cacheEligibility.replace(/_/g, " ")}` : "Stable cache-eligible prefix when applicable"}</li>
            </ul>
            <label className="field-label" htmlFor="governed-prompt-copy">Governed prompt</label>
            <textarea id="governed-prompt-copy" readOnly value={governedPrompt || "Governed prompt unavailable until the server returns a candidate package."} />
          </article>
        </div>
      </section>
      <section className="panel"><SectionHead title="What TokenOS changed and why" supporting="Evidence is Estimated or policy-state until a protected run records actual usage." />
        <div className="optimization-table-wrap"><table className="optimization-table">
          <thead><tr><th>Change</th><th>Reason</th><th>Evidence state</th></tr></thead>
          <tbody>{(plan?.changes ?? []).map((change) => <tr key={change.id || change.change}>
            <td>{change.change}</td><td>{change.reason}</td><td>{change.evidenceState}</td>
          </tr>)}</tbody>
        </table></div>
        {!(plan?.changes.length) && <p className="muted">No prompt changes have been returned by the server.</p>}
        <div className="btn-row btn-row-end">
          <button type="button" className="btn" onClick={() => void copyGovernedPrompt()} disabled={!governedPrompt || busy}>Copy governed prompt</button>
          <button type="button" className="btn btn-primary" disabled={busy} onClick={onProtect}>Continue to safeguards</button>
        </div>
        {copyStatus && <p className="muted" role="status">{copyStatus}</p>}
      </section>
    </>;
  }
  return <>
    <PhaseIntro heading="Use the least-expensive eligible route"
      supporting="Each lever is evaluated independently. Required quality checks are never traded away." focusKey="optimization-optimize" />
    <section className="panel"><SectionHead title="Optimization levers" supporting="Applicability is not a measured improvement. Provider caching is measured only after a real response." />
      <div className="optimization-levers">{record.levers.map((lever) => <article key={lever.id} className="optimization-lever">
        <div className="row-between"><h4>{lever.name}</h4><span className="optimization-badge">{lever.status}</span></div>
        <p>{lever.action}</p><p><strong>Evidence:</strong> {lever.evidence}</p>
      </article>)}</div>
      {!record.levers.length && <p className="muted">Lever evaluation has not been returned by the server.</p>}
    </section>
    <section className="panel"><SectionHead title="Candidate execution route" supporting="Expected effects remain estimated until execution. No model can run before Protect authorization." />
      <Facts facts={[
        ["Maximum model spend", dollars(record.maxSpendUsd)],
        ["Output contract", record.outputContract || "Not pinned yet"],
        ["Quality protections", "Citations, tests, structured output and human approval stay required when selected."]
      ]} />
      <div className="optimization-table-wrap"><table className="optimization-table">
        <thead><tr><th>Operation</th><th>Allowed route</th><th>Data handling</th><th>Required quality checks</th></tr></thead>
        <tbody>{record.operations.map((operation) => <tr key={operation.id}>
          <td>{operation.label}</td><td>{aliasName(operation.route)}</td>
          <td>{operation.dataDecision || "Awaiting safeguard decision"}</td>
          <td>{operation.qualityChecks.join(", ") || "Required workflow acceptance checks"}</td>
        </tr>)}</tbody>
      </table></div>
      <div className="btn-row btn-row-end"><button type="button" className="btn btn-primary" disabled={busy} onClick={onProtect}>
        {busy ? "Checking safeguards…" : "Review execution safeguards"}
      </button></div>
    </section>
  </>;
}

export function ProtectView({ record, busy, onAuthorize, onRefresh, onEdit, humanApproved, onHumanApproved }: {
  record: OptimizationRecord; busy: boolean; onAuthorize: () => void; onRefresh: () => void; onEdit: () => void;
  humanApproved: boolean; onHumanApproved: (approved: boolean) => void;
}) {
  const humanRequired = record.safeguards.some((check) =>
    check.passed === false && (check.id.includes(":human_approval:") || check.id.includes(":data_policy:") && record.dataDecision === "approval_required"));
  const eligible = record.canAuthorize || record.safeguards.length > 0 && record.safeguards.every((check) =>
    check.passed || check.id.includes(":model_cost_acknowledgement:") || humanApproved &&
      (check.id.includes(":human_approval:") || check.id.includes(":data_policy:") && record.dataDecision === "approval_required"));
  const isPrompt = record.optimizationTarget === "single_prompt";
  const plan = record.promptPlan;
  const historyTreatment = plan?.current.components.find((component) => /history/i.test(component.id || component.label))?.candidateTreatment;
  return <>
    <PhaseIntro heading="Protect the outcome. Authorize the work."
      supporting="Review the pinned execution contract before any model can be invoked." focusKey="optimization-protect" />
    <section className="panel"><SectionHead title="Execution safeguards" supporting="A failed check blocks execution. Fix its stated requirement; TokenOS will never substitute simulated results." />
      <GateList checks={record.safeguards} />
      {isPrompt && <section className="optimization-safeguards" aria-label="Plain-language prompt safeguards">
        <h4>Plain-language prompt safeguards</h4>
        <Facts facts={[
          ["Context sections allowed", plan ? idList(plan.candidate.eligibleContextIds) : "Unavailable"],
          ["History handling", historyTreatment || "Unavailable"],
          ["Maximum output", record.maxOutputTokens !== undefined ? `${numberValue(record.maxOutputTokens)} tokens` : "Unavailable"],
          ["Model authorization", aliasName(plan?.candidate.recommendedModelAlias || "unknown")],
          ["Escalation condition", record.maxAdvancedCalls !== undefined ? `Advanced model only after failed verification; maximum ${numberValue(record.maxAdvancedCalls)} calls` : "Advanced model only after failed verification when authorized"],
          ["Maximum spend", dollars(record.maxSpendUsd)]
        ]} />
      </section>}
      <Facts facts={[
        ["Maximum model spend", dollars(record.maxSpendUsd)],
        ["Conservative total reservation", dollars(record.perCallLimitUsd)],
        ["Maximum advanced calls", numberValue(record.maxAdvancedCalls)],
        ["Output contract", record.outputContract || "Unavailable"],
        ["Maximum output length", record.maxOutputTokens !== undefined ? `${numberValue(record.maxOutputTokens)} tokens` : "Unavailable"],
        ["Pinned price-table version", record.priceTableVersion || "Unavailable"]
      ]} />
      <details><summary>Input manifest and artifact decisions</summary>
        <p className="muted">Manifest SHA-256</p><code className="optimization-hash">{record.manifestHash || "Not pinned"}</code>
        <ul>{record.manifest.map((artifact) => <li key={artifact.upload_id}>
          <strong>{artifact.name}</strong> · {artifact.role} · {artifact.media_type} · Data handling: {record.dataDecision || "Unavailable"}<br />
          <code className="optimization-hash">{artifact.sha256}</code>
        </li>)}</ul>
        <p className="muted">Only approved, minimized evidence can reach an allowed model alias. Raw inputs remain behind this evidence view.</p>
      </details>
      {humanRequired && <label className="checkbox-row"><input type="checkbox" checked={humanApproved}
        onChange={(event) => onHumanApproved(event.target.checked)} disabled={busy} />
        I have reviewed the selected outcomes and grant the required human approval for this run.
      </label>}
      {!eligible && <p className="error-text" role="alert">Execution is blocked. Resolve the failed checks above, then refresh draft safeguards if deployment configuration or pricing changed. Edit requirements to change the inputs or budget. Configuration stays server-side.</p>}
      {!record.authorized && <p className="muted">Refreshing safeguards re-pins this draft's server configuration and prices without invoking a model. You must still explicitly authorize the protected run.</p>}
      <div className="btn-row btn-row-end">
        <button type="button" className="btn" onClick={onEdit} disabled={busy}>Edit requirements</button>
        <button type="button" className="btn" onClick={onRefresh} disabled={busy || record.status !== "optimized" || record.authorized}>Refresh safeguards</button>
        <button type="button" className="btn btn-primary" onClick={onAuthorize}
          disabled={busy || !eligible || record.authorized}>
          {busy ? "Authorizing…" : record.authorized ? "Run authorized" : isPrompt ? "Authorize protected prompt run" : "Authorize protected run"}
        </button>
      </div>
    </section>
  </>;
}

export function VerifyView({ record, onProve, onEdit, onEscalate }: {
  record: OptimizationRecord; onProve: () => void; onEdit: () => void; onEscalate: () => void;
}) {
  const passed = record.qualityPassed === true;
  const evidenceRef = useRef<HTMLDetailsElement>(null);
  const inspectFailures = () => {
    if (evidenceRef.current) {
      evidenceRef.current.open = true;
      evidenceRef.current.focus();
      evidenceRef.current.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  };
  return <>
    <PhaseIntro heading={passed ? "The required outcome passed verification" : "Review the outcome before the economics"}
      supporting="These results come from the same quality gates pinned before execution." focusKey="optimization-verify" />
    <section className="panel"><div className="row-between"><h3>Verified outcome</h3>
      <span className={`optimization-badge ${passed ? "good" : "warn"}`}>{passed ? "Passed" : record.qualityPassed === false ? "Failed" : "Not verified"}</span>
    </div>
      {record.optimizationTarget === "single_prompt" && <p className="optimization-route-line">Prompt + approved context -&gt; Local minimization/reuse -&gt; Efficient model if needed -&gt; Verification -&gt; Advanced escalation only if required</p>}
      <p>{record.outcome || (passed ? "The required acceptance checks passed." : "No passing outcome has been recorded.")}</p>
      <SampleBadge sample={record.sample} />
      {record.processed !== undefined && record.total !== undefined && <p><strong>{numberValue(record.processed)} of {numberValue(record.total)} records processed</strong></p>}
      <GateList checks={record.qualityGates} />
      {record.outcomes.length > 0 && <div className="optimization-table-wrap"><table className="optimization-table">
        <caption>Actual produced outcomes</caption>
        <thead><tr><th>Request</th><th>Produced decision / answer</th><th>Grounded sources</th><th>Acceptance</th></tr></thead>
        <tbody>{record.outcomes.map((outcome) => <tr key={outcome.requestId}>
          <td>{outcome.requestId}</td><td>{outcome.decision}{outcome.diagnosis && <small>{outcome.diagnosis}</small>}</td>
          <td>{outcome.citations.join(", ") || "No citations produced"}</td><td>{outcome.passed ? "Passed" : "Failed"}</td>
        </tr>)}</tbody>
      </table></div>}
      {!!record.exceptions.length && <div className="notice"><h4>Exceptions and required human actions</h4><ul>{record.exceptions.map((exception, index) => <li key={index}>{exception}</li>)}</ul></div>}
      <details ref={evidenceRef} tabIndex={-1}><summary>Outcome evidence: why quality {passed ? "passed" : "did not pass"}</summary><GateList checks={record.qualityGates} /></details>
      {!passed && <div className="notice"><strong>No cost saving verified</strong><p>The work remains measured, but failed or unavailable quality checks cannot support a successful comparison.</p></div>}
      {!passed && <p className="muted">Escalation prepares a new draft with advanced reasoning allowed only after failed efficient-model verification. Quality requirements remain unchanged and Protect must authorize the new run.</p>}
      <div className="btn-row btn-row-end">
        {!passed && <>
          <button type="button" className="btn" onClick={inspectFailures}>Inspect failed checks</button>
          <button type="button" className="btn" onClick={onEdit}>Adjust plan</button>
          <button type="button" className="btn" onClick={onEscalate}>Escalate with approval</button>
        </>}
        <button type="button" className="btn btn-primary" onClick={onProve}>Review measured cost proof</button>
      </div>
    </section>
  </>;
}

export function isEligibleComparison(comparison?: OptimizationComparison): boolean {
  return Boolean(comparison?.eligible && comparison.matched && comparison.governedPassed && comparison.baselinePassed
    && typeof comparison.baselineCostUsd === "number" && typeof comparison.governedCostUsd === "number"
    && comparison.baselineCostUsd > comparison.governedCostUsd
    && typeof comparison.savingUsd === "number" && comparison.savingUsd > 0);
}

function CallEvidence({ calls, sample }: { calls: OptimizationUsage[]; sample: boolean }) {
  return <>{calls.map((call, index) => <article className="optimization-call" key={call.id || index}>
    <div className="row-between"><h4>{call.purpose || "Model-assisted operation"}</h4><span className="optimization-badge">{aliasName(call.alias)}</span></div>
    {call.optionalPresentation && <p className="muted"><strong>Optional presentation work.</strong> This call produced a readable summary; it did not resolve ambiguity.</p>}
    <Facts facts={[
      ["Why software could not finish this step", call.alias === "tokenos-baseline"
        ? "Explicitly authorized all-AI comparator: local work is intentionally not used on this matched route."
        : call.whyAI || "No rationale recorded; inspect technical evidence."],
      ["Minimal evidence sent", call.minimalEvidence || "Not recorded"],
      ["Input / output tokens", `${numberValue(call.inputTokens)} / ${numberValue(call.outputTokens)}`],
      ["Cached / reasoning tokens", `${numberValue(call.cachedInputTokens)} / ${numberValue(call.reasoningTokens)}`],
      ["Total tokens", numberValue(call.totalTokens)],
      ["Measured model cost", dollars(call.costUsd)],
      ["Quality-gate result", `${call.qualityPassed === true ? "Passed" : call.qualityPassed === false ? "Failed" : "Not checked"}${call.qualityDetail ? ` · ${call.qualityDetail}` : ""}`],
      ["Escalation decision", call.escalation || "No escalation recorded"]
    ]} /><SampleBadge sample={sample} />
  </article>)}</>;
}

export function ProveView({ record, acknowledged, setAcknowledged, comparing, onBaseline }: {
  record: OptimizationRecord; acknowledged: boolean; setAcknowledged: (value: boolean) => void;
  comparing: boolean; onBaseline: () => void;
}) {
  const comparison = record.comparison;
  const isPrompt = record.optimizationTarget === "single_prompt";
  const promptPlan = record.promptPlan;
  const promptProof = record.promptProof;
  const eligible = record.qualityPassed === true && isEligibleComparison(comparison);
  const completed = record.operations.filter((operation) => ["complete", "completed", "passed"].includes(operation.status));
  const local = completed.filter((operation) => /local|software|reuse|cache|retrieval|rule|test/i.test(operation.route));
  const efficient = record.usage.filter((call) => call.alias === "tokenos-efficient");
  const advanced = record.usage.filter((call) => call.alias === "tokenos-advanced");
  const modelOperations = completed.filter((operation) => !local.includes(operation));
  const fewerCalls = comparison?.baselineCalls !== undefined && comparison?.governedCalls !== undefined
    && comparison.baselineCalls > comparison.governedCalls;
  const promptContextState = promptPlan ? "Kept, minimized, reused, or blocked sections recorded" : "";
  const heading = isPrompt && eligible ? "Same verified outcome. Lower measured model cost."
    : isPrompt && record.qualityPassed === true ? "Verified prompt outcome. Less unnecessary context. Measured cost proof."
    : record.mode === "analyze" ? "Measured current cost. A locally built optimization plan."
    : eligible && fewerCalls ? "Same verified outcome. Fewer AI calls. Lower measured model cost."
    : eligible ? "Same verified outcome. Lower measured model cost."
    : record.qualityPassed === true ? "Verified outcome. Minimal AI use. Measured cost proof."
    : "Measured execution. Outcome not verified.";
  const baselineStarted = Boolean(comparison && !["not_requested", "not_run"].includes(comparison.status));
  const beforeTokens = promptProof?.estimatedBefore?.inputTokens !== undefined
    ? numberValue(promptProof.estimatedBefore.inputTokens)
    : promptPlan?.current.estimatedInputTokens !== undefined
      ? numberValue(promptPlan.current.estimatedInputTokens) : "Unavailable";
  const afterTokens = promptProof?.estimatedAfter?.inputTokens !== undefined
    ? numberValue(promptProof.estimatedAfter.inputTokens)
    : promptPlan?.candidate.estimatedInputTokens !== undefined
      ? numberValue(promptPlan.candidate.estimatedInputTokens) : "Unavailable";
  const comparisonLabel = !baselineStarted ? "Comparison not run"
    : ["running", "queued"].includes(comparison?.status ?? "") || comparing ? "All-AI comparison running"
    : comparison?.label === "No valid comparison" || ["unavailable", "baseline_failed", "invalid_comparison", "failed"].includes(comparison?.status ?? "") ? "No valid comparison"
    : "No cost saving verified";
  function downloadProof() {
    const url = URL.createObjectURL(new Blob([JSON.stringify(record.raw, null, 2)], { type: "application/json" }));
    const link = document.createElement("a");
    link.href = url; link.download = `tokenos-${record.runId}-proof.json`; link.click();
    URL.revokeObjectURL(url);
  }
  return <>
    <section className={`panel optimization-hero ${record.qualityPassed !== true ? "is-unverified" : ""}`}>
      <div className="optimization-eyebrow"><span>OPTIMIZE AN EXISTING AI WORKFLOW / PROOF</span><SampleBadge sample={record.sample} /></div>
      <h2 tabIndex={-1}>{heading}</h2>
      <p className="muted">{record.outcome || "Actual outcomes and model usage, without inferred improvements."}</p>
      {record.mode === "analyze" && <p className="muted">Telemetry analysis is not an executed optimized route. Candidate improvements are recommendations only.</p>}
      {record.mode === "measure" && record.qualityPassed === true && completed.length > 0 ? (
        <WorkAvoidedBanner
          localOperations={local.length}
          totalOperations={completed.length}
          detail={record.modelCalls === 0
            ? "Ordinary software and validated reuse settled every step. No model was needed."
            : `Only ${modelOperations.length} ${modelOperations.length === 1 ? "step" : "steps"} genuinely needed a model.`}
        />
      ) : null}
      {isPrompt ? <div className="cards prove-cards">
        <ComparisonCard
          title="What this run cost"
          comparison={eligible && comparison ? <span>The all-AI version: <strong>{dollars(comparison.baselineCostUsd)}</strong></span> : undefined}
          value={dollars(promptProof?.measuredCost?.costUsd ?? promptProof?.measuredCost?.modelSpendUsd ?? record.modelSpendUsd)}
          chip={eligible ? "Verified saving" : undefined}
          tier={eligible ? "proven" : "none"}
          note="Measured provider usage priced against the pinned price table."
        />
        <ComparisonCard
          title="How big the prompt was"
          comparison={<span>Before TokenOS: <strong>{beforeTokens}</strong> tokens</span>}
          value={afterTokens}
          unit="tokens"
          chip="Estimate"
          tier="estimate"
          note="Estimated from prompt composition. Actual usage is recorded separately."
        />
        <ComparisonCard
          title="What happened to the context"
          value={promptContextState || "Recorded"}
          chip="No AI tokens used"
          tier="none"
          note="No AI tokens does not mean free — normal computing and review time still apply."
        />
        <ComparisonCard
          title="Is the answer still correct?"
          value={record.qualityPassed === true ? "Yes" : record.qualityPassed === false ? "No" : "Not run"}
          valueTone={record.qualityPassed === true ? "good" : undefined}
          chip={record.qualityPassed === true ? "Quality checks passed" : undefined}
          tier="proven"
          note="Quality checks and evidence result."
        />
      </div> : <div className="cards prove-cards">
        <ComparisonCard
          title={record.mode === "analyze" ? "What the current route costs" : "What this run cost"}
          comparison={eligible && comparison ? <span>The all-AI version: <strong>{dollars(comparison.baselineCostUsd)}</strong></span> : undefined}
          value={dollars(record.mode === "analyze" ? record.current.costUsd : record.modelSpendUsd)}
          chip={eligible ? "Verified saving" : undefined}
          tier={eligible ? "proven" : "none"}
          note={record.mode === "analyze"
            ? "Imported measured usage, where the source telemetry supports it."
            : "Measured provider usage priced against the pinned price table."}
        />
        <ComparisonCard
          title="How often AI was needed"
          comparison={eligible && comparison?.baselineCalls !== undefined
            ? <span>The all-AI version: <strong>{numberValue(comparison.baselineCalls)} times</strong></span> : undefined}
          value={record.mode === "analyze" ? numberValue(record.current.calls) : numberValue(record.modelCalls)}
          unit={record.modelCalls === 1 ? "time" : "times"}
          chip={eligible && comparison?.baselineCalls !== undefined && record.modelCalls !== undefined
            && comparison.baselineCalls > record.modelCalls
            ? `${comparison.baselineCalls - record.modelCalls} AI calls avoided · proven` : undefined}
          tier={eligible ? "proven" : "none"}
          note={record.mode === "analyze"
            ? "Observed on the current route. This is not a governed run."
            : `${modelOperations.length} model operations · ${efficient.length} efficient / ${advanced.length} advanced calls.`}
        />
        <ComparisonCard
          title="Work done by ordinary software"
          value={local.length}
          unit={`of ${completed.length} steps`}
          chip="No AI tokens used"
          tier="none"
          note="No AI tokens does not mean free — normal computing and review time still apply."
        />
        <ComparisonCard
          title="Is the answer still correct?"
          value={record.qualityPassed === true ? "Yes" : record.qualityPassed === false ? "No" : "Not run"}
          valueTone={record.qualityPassed === true ? "good" : undefined}
          chip={record.qualityPassed === true ? "Required checks passed" : undefined}
          tier="proven"
          note="Required quality checks and evidence status."
        />
      </div>}
      <p className="muted">Local software still consumes compute, storage and operating effort. Model spend is not total workflow cost.</p>
      {record.mode === "measure" && record.modelCalls !== undefined && record.modelCalls > record.usage.length &&
        <p className="muted">Some attempted calls have no usable provider-usage record. Their cost is unavailable, not zero; no improvement can be claimed from incomplete measurement.</p>}
    </section>
    {isPrompt && <section className="panel">
      <SectionHead title="Prompt route" supporting="The baseline is separate and only runs after explicit acknowledgement." />
      <p className="optimization-route-line">Prompt + approved context -&gt; Local minimization/reuse -&gt; Efficient model if needed -&gt; Verification -&gt; Advanced escalation only if required</p>
    </section>}
    {!isPrompt && record.mode === "measure" && <section className="panel">
      <SectionHead title="Why this route" supporting="Counts come from completed operation records and actual model-call records, not the planned route." />
      <div className="optimization-route">
        <div><strong>{local.length}</strong><span>Local and reuse operations</span></div><span aria-hidden="true">→</span>
        <div><strong>{efficient.length}</strong><span>Efficient model calls</span></div><span aria-hidden="true">→</span>
        <div><strong>{advanced.length}</strong><span>Advanced escalations</span></div>
      </div>
      <SampleBadge sample={record.sample} />
      <p className="muted">Operations and model calls are different units. One model call may support more than one operation.</p>
    </section>}
    {record.usage.length > 0 && <section className="panel"><SectionHead title="Why AI was used" supporting="One record per actual call. Only minimized evidence summaries are shown here, not raw prompts." />
      <CallEvidence calls={record.usage} sample={record.sample} />
    </section>}
    {isPrompt && <section className="panel">
      <SectionHead title="What changed" supporting="Estimated, measured, projected, and verified saving states are shown separately." />
      <div className="optimization-table-wrap"><table className="optimization-table">
        <thead><tr><th>Change</th><th>Reason</th><th>Evidence state</th></tr></thead>
        <tbody>{(promptPlan?.changes ?? []).map((change) => <tr key={change.id || change.change}>
          <td>{change.change}</td><td>{change.reason}</td><td>{change.evidenceState}</td>
        </tr>)}</tbody>
      </table></div>
      {!(promptPlan?.changes.length) && <p className="muted">No prompt change explanations are available in the proof.</p>}
      <Facts facts={[
        ["Actual input / output tokens", `${numberValue(promptProof?.measuredUsage?.inputTokens)} / ${numberValue(promptProof?.measuredUsage?.outputTokens)}`],
        ["Actual cached / reasoning tokens", `${numberValue(promptProof?.measuredUsage?.cachedInputTokens)} / ${numberValue(promptProof?.measuredUsage?.reasoningTokens)}`],
        ["Final allowed context artifacts", promptPlan ? idList(promptPlan.candidate.eligibleContextIds) : "Unavailable"],
        ["Model alias used", aliasName(promptProof?.measuredUsage?.alias || record.usage[0]?.alias || "unknown")],
        ["Model calls issued", numberValue(record.modelCalls)],
        ["Actual latency", promptProof?.measuredUsage?.durationMs !== undefined ? `${numberValue(promptProof.measuredUsage.durationMs)} ms` : "Unavailable"],
        ["Measured cost", dollars(promptProof?.measuredCost?.costUsd ?? promptProof?.measuredCost?.modelSpendUsd ?? record.modelSpendUsd)],
        ["Quality-gate status", record.qualityPassed === true ? "Passed" : record.qualityPassed === false ? "Failed" : "Not verified"]
      ]} />
    </section>}
    <section className="panel">
      <div className="row-between"><h3>{eligible ? "Verified saving" : comparisonLabel}</h3><SampleBadge sample={record.sample} /></div>
      {eligible && comparison ? <>
        <div className="optimization-metrics">
          <Metric title="All-AI cost" value={dollars(comparison.baselineCostUsd)} note="Measured baseline model spend" sample={record.sample} />
          <Metric title="TokenOS governed cost" value={dollars(comparison.governedCostUsd)} note="Measured governed model spend" sample={record.sample} />
          <Metric title="Verified saving" value={dollars(comparison.savingUsd)} note={comparison.savingPercent !== undefined ? `${numberValue(comparison.savingPercent)}% lower measured model cost` : "Measured dollar difference"} sample={record.sample} />
          <Metric title="Quality" value="Both passed" note="Matched acceptance requirements" sample={record.sample} />
        </div>
        <p className="muted">Both paths used the same inputs, output contract, quality checks, and price-table version.</p>
      </> : <>
        <p className="muted">{comparison?.reason || "Only an eligible, matched comparison can establish a cost improvement. Volume projections do not qualify."}</p>
        {record.qualityPassed === true && record.mode === "measure" && !baselineStarted && <>
          <h4>{isPrompt ? "Run comparison with current route" : "Run the all-AI comparison"}</h4>
          <p className="muted">{isPrompt
            ? "This invokes the matched baseline route and may incur model cost. TokenOS reports a verified saving only if both routes pass the same checks."
            : "This re-runs the same inputs through the baseline route and consumes model tokens. TokenOS shows a verified saving only if both routes meet the same quality checks."}</p>
          <label className="checkbox-row"><input type="checkbox" checked={acknowledged} disabled={comparing}
            onChange={(event) => setAcknowledged(event.target.checked)} />
            I understand this comparison invokes a model and may incur model cost.
          </label>
          <div className="btn-row"><button type="button" className="btn btn-primary" disabled={!acknowledged || comparing} onClick={onBaseline}>
            {comparing ? "Starting matched comparison…" : isPrompt ? "Run matched comparison" : "Run all-AI comparison"}
          </button></div>
        </>}
        {record.qualityPassed !== true && <p className="muted">A matched all-AI comparison requires a completed governed run with passing quality checks.</p>}
        {baselineStarted && <p role="status" className="muted">{comparing ? "Receiving live all-AI comparison events…" : "This comparison attempt is recorded. A rerun requires a separately authorized version."}</p>}
      </>}
    </section>
    {!!comparison?.usage?.length && <section className="panel">
      <SectionHead title="Why AI was used in the matched comparison" supporting="Baseline call records are separate from governed spend and governed operations." />
      <CallEvidence calls={comparison.usage} sample={record.sample} />
    </section>}
    {record.projection && <section className="panel optimization-projection">
      <div className="row-between"><h3>Projected cost at volume</h3><span className="optimization-badge warn">Projected</span></div>
      <p><strong>{dollars(record.projection.costUsd)}</strong> for {numberValue(record.projection.volume)} requests per {record.projection.period}</p>
      <p className="muted">{record.projection.basis} This scaling estimate is separate from measured spend and is not a verified improvement.</p>
      <SampleBadge sample={record.sample} />
    </section>}
    <details><summary>Outcome evidence: why quality {record.qualityPassed === true ? "passed" : "did not pass"}</summary>
      <GateList checks={record.qualityGates} />{!!record.exceptions.length && <ul>{record.exceptions.map((item, index) => <li key={index}>{item}</li>)}</ul>}
    </details>
    <details><summary>Technical evidence and run proof</summary>
      <Facts facts={[["Run ID", record.runId], ["Price-table version", record.priceTableVersion || "Unavailable"], ["Input manifest", <code className="optimization-hash">{record.manifestHash || "Unavailable"}</code>]]} />
      <p className="muted">Includes artifact hashes, policy decisions, routes, normalized provider usage and quality checks. Provider credentials are never part of the proof.</p>
      <button type="button" className="btn btn-small" onClick={downloadProof}>Download raw JSON proof</button>
      <details style={{ marginTop: 12 }}><summary>Inspect recorded proof JSON</summary><pre className="optimization-json">{JSON.stringify(record.raw, null, 2)}</pre></details>
    </details>
  </>;
}
