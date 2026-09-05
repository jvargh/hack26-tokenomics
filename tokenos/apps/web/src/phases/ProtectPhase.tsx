import { useRun } from "../state/runContext";
import { PhaseIntro, SectionHead } from "../components/shared/PhaseIntro";
import { StatusBadge } from "../components/shared/Badges";
import { formatUsd } from "../components/shared/format";

export function ProtectPhase() {
  const { state, approve, viewPhase } = useRun();
  const { active } = state;
  const plan = active.plan;
  if (!plan) return null;

  const checks = plan.protection_checks;
  const blocked = active.blocked;
  const approval = active.approval;
  const awaitingApproval = approval?.decision === "pending";
  const allPassed = active.passedChecks.length >= checks.length;

  return (
    <div className="phase">
      <PhaseIntro
        heading={blocked ? "Stopped before any paid action" : "Checking enterprise safeguards"}
        supporting="TokenOS checks spending, quality, data, side effects, and time before any paid action begins."
        focusKey="protect"
      />

      <section className="panel">
        <SectionHead
          title={
            blocked
              ? `${blocked.check} check failed`
              : allPassed
                ? "The optimized plan is safe to execute"
                : "Checking spending, quality, data, actions, and time"
          }
        />

        {blocked ? (
          <div className="notice notice-risk">
            <h3>Run blocked safely</h3>
            <p>
              <strong>Failed check:</strong> {blocked.check}
            </p>
            <p>
              <strong>Reason:</strong> {blocked.reason}
            </p>
            <p>
              <strong>What you can change:</strong> {blocked.userAction}
            </p>
            <p>
              <strong>What TokenOS prevented:</strong> {blocked.prevented}
            </p>
            <div className="btn-row" style={{ marginTop: 12 }}>
              <button type="button" className="btn" onClick={() => viewPhase("describe")}>
                Return to task requirements
              </button>
            </div>
          </div>
        ) : null}

        {awaitingApproval && approval ? (
          <div className="notice notice-warn">
            <h3>Approval required before execution</h3>
            <p>{approval.reason}</p>
            <dl className="evidence-list" style={{ marginTop: 10 }}>
              <div>
                <dt>Action</dt>
                <dd>{approval.action}</dd>
              </div>
              <div>
                <dt>Maximum authorized model cost</dt>
                <dd>{formatUsd(approval.maximum_cost_usd)}</dd>
              </div>
              <div>
                <dt>Rollback</dt>
                <dd>{approval.rollback}</dd>
              </div>
            </dl>
            <div className="btn-row" style={{ marginTop: 12 }}>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => void approve("approved")}
              >
                Approve and continue
              </button>
              <button
                type="button"
                className="btn btn-risk"
                onClick={() => void approve("rejected")}
              >
                Reject and stop safely
              </button>
            </div>
          </div>
        ) : null}

        <ul className="check-list">
          {checks.map((check) => {
            const passed = active.passedChecks.includes(check.check_id);
            const failedHere = blocked?.check.toLowerCase() === check.check_id;
            return (
              <li key={check.check_id} className="check">
                <div className="check-head">
                  <span className="check-name">{check.name}</span>
                  {failedHere || !check.passed ? (
                    <StatusBadge tone="risk">Blocked safely</StatusBadge>
                  ) : passed ? (
                    <StatusBadge tone="good">Passed</StatusBadge>
                  ) : (
                    <StatusBadge tone="neutral">Checking</StatusBadge>
                  )}
                </div>
                <p className="muted" style={{ margin: "8px 0 0", fontSize: 13 }}>
                  {check.detail}
                </p>
                <details>
                  <summary>Evidence</summary>
                  <dl className="evidence-list">
                    {check.evidence.map((item) => (
                      <div key={item.label}>
                        <dt>{item.label}</dt>
                        <dd>{item.value}</dd>
                      </div>
                    ))}
                  </dl>
                </details>
              </li>
            );
          })}
        </ul>
      </section>
    </div>
  );
}
