import { useRun } from "../state/runContext";
import { PhaseIntro, PhaseSummaryFacts, SectionHead } from "../components/shared/PhaseIntro";
import { StatusBadge } from "../components/shared/Badges";

export function VerifyPhase() {
  const { state } = useRun();
  const { active } = state;
  const verification = active.verification;

  return (
    <div className="phase">
      <PhaseIntro
        heading="Verifying the completed outcome"
        supporting="TokenOS confirms the outcome with workflow-specific deterministic checks before reporting any result."
        focusKey="verify"
      />

      <section className="panel">
        <SectionHead
          title={
            !verification
              ? "Running the workflow verification checks"
              : verification.qualityPassed
                ? "All verification checks passed"
                : "Verification found issues"
          }
          supporting={
            verification
              ? `Quality ${verification.qualityScore?.toFixed(2)} against the required ${(
                  active.plan?.protection_checks
                    .find((check) => check.check_id === "quality")
                    ?.evidence.find((item) => item.label === "Required score")?.value ?? "0.92"
                )}`
              : undefined
          }
        />

        {verification ? (
          <PhaseSummaryFacts
            facts={verification.facts.map((fact) => ({
              value: fact.value,
              label: fact.label,
              state: "passed" as const
            }))}
          />
        ) : null}

        <ul className="check-list">
          {(verification?.checks ?? []).map((check) => (
            <li key={check.name} className="check">
              <div className="check-head">
                <span className="check-name">{check.name}</span>
                <StatusBadge tone={check.passed ? "good" : "risk"}>
                  {check.passed ? "Passed" : "Failed"}
                </StatusBadge>
              </div>
              <p className="muted" style={{ margin: "8px 0 0" }}>
                {check.result}
              </p>
              <p className="muted" style={{ margin: "4px 0 0", fontSize: 12 }}>
                Pass rule: {check.rule}
              </p>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
