import { useRun } from "../state/runContext";
import { PHASE_LABEL, PHASE_ORDER, type PhaseId } from "../state/runStore";

export function PhaseStepper() {
  const { state, viewPhase } = useRun();
  const { active } = state;
  const currentIndex = PHASE_ORDER.indexOf(active.currentPhase);
  const maxIndex = PHASE_ORDER.indexOf(active.maxPhaseReached);

  const stateFor = (phase: PhaseId, index: number) => {
    if (active.status === "blocked" && index === currentIndex) return "is-failed";
    if (active.status === "waiting" && index === currentIndex) return "is-paused";
    if (phase === active.currentPhase) return "is-current";
    if (index <= maxIndex) return "is-complete";
    return "is-future";
  };

  return (
    <nav className="stepper" aria-label="Run progress">
      <ol>
        {PHASE_ORDER.map((phase, index) => {
          const status = stateFor(phase, index);
          const reachable = index <= maxIndex;
          const isViewing = phase === active.viewingPhase;
          return (
            <li key={phase} className={`step ${status} ${isViewing ? "is-viewing" : ""}`}>
              <button
                type="button"
                disabled={!reachable}
                aria-current={phase === active.currentPhase ? "step" : undefined}
                aria-pressed={isViewing}
                onClick={() => viewPhase(phase)}
              >
                <span className="step-circle" aria-hidden="true">
                  {index + 1}
                </span>
                <span className="step-label">{PHASE_LABEL[phase]}</span>
                <span className="sr-only">
                  {`Step ${index + 1} of 7: ${PHASE_LABEL[phase]}. ${
                    status === "is-complete"
                      ? "Completed, available to inspect."
                      : status === "is-current"
                        ? "Current phase."
                        : status === "is-paused"
                          ? "Paused, awaiting a decision."
                          : status === "is-failed"
                            ? "Stopped by a control."
                            : "Not yet available."
                  }${isViewing ? " Now showing." : ""}`}
                </span>
              </button>
            </li>
          );
        })}
      </ol>
      <p className="step-mobile">
        {`Step ${currentIndex + 1} of 7: ${PHASE_LABEL[active.currentPhase]}`}
      </p>
    </nav>
  );
}
