import type {
  ApprovalRequest,
  LiveOperation,
  PlanResponse,
  Proof,
  ProtectionCheck,
  RunMetrics,
  RunState,
  ServerEvent,
  VerificationCheckResult
} from "../api/types";

export type PhaseId = "describe" | "plan" | "optimize" | "protect" | "run" | "verify" | "prove";

export const PHASE_ORDER: PhaseId[] = [
  "describe",
  "plan",
  "optimize",
  "protect",
  "run",
  "verify",
  "prove"
];

export const PHASE_LABEL: Record<PhaseId, string> = {
  describe: "Describe",
  plan: "Plan",
  optimize: "Optimize",
  protect: "Protect",
  run: "Run",
  verify: "Verify",
  prove: "Prove"
};

export interface BlockedInfo {
  check: string;
  reason: string;
  operationLabel: string;
  userAction: string;
  prevented: string;
}

export interface ActiveRun {
  runId: string | null;
  status: string;
  currentPhase: PhaseId;
  maxPhaseReached: PhaseId;
  viewingPhase: PhaseId;
  plan: PlanResponse | null;
  operations: LiveOperation[];
  routesSelected: number;
  passedChecks: string[];
  metrics: RunMetrics | null;
  approval: ApprovalRequest | null;
  blocked: BlockedInfo | null;
  verification: {
    checks: VerificationCheckResult[];
    qualityScore: number | null;
    qualityPassed: boolean | null;
    deadlineMet: boolean | null;
    facts: Array<{ label: string; value: string; detail?: string }>;
  } | null;
  proof: Proof | null;
  error: { message: string; type: string } | null;
  events: ServerEvent[];
  announcement: string;
  streamState: "idle" | "open" | "reconnecting" | "closed";
}

export interface AppState {
  active: ActiveRun;
  history: Array<{ runId: string; workflowId: string; status: string; proof: Proof | null }>;
}

export const emptyRun: ActiveRun = {
  runId: null,
  status: "draft",
  currentPhase: "describe",
  maxPhaseReached: "describe",
  viewingPhase: "describe",
  plan: null,
  operations: [],
  routesSelected: 0,
  passedChecks: [],
  metrics: null,
  approval: null,
  blocked: null,
  verification: null,
  proof: null,
  error: null,
  events: [],
  announcement: "",
  streamState: "idle"
};

export const initialAppState: AppState = { active: emptyRun, history: [] };

export type AppAction =
  | { type: "planCompiled"; plan: PlanResponse }
  | { type: "runStarted"; runId: string }
  | { type: "event"; event: ServerEvent }
  | { type: "syncState"; state: RunState }
  | { type: "streamState"; value: ActiveRun["streamState"] }
  | { type: "viewPhase"; phase: PhaseId }
  | { type: "reset" };

function phaseIndex(phase: PhaseId): number {
  return PHASE_ORDER.indexOf(phase);
}

function advance(run: ActiveRun, phase: PhaseId): ActiveRun {
  const follow = run.viewingPhase === run.currentPhase;
  const maxPhaseReached =
    phaseIndex(phase) > phaseIndex(run.maxPhaseReached) ? phase : run.maxPhaseReached;
  return {
    ...run,
    currentPhase: phase,
    maxPhaseReached,
    viewingPhase: follow ? phase : run.viewingPhase,
    announcement: `Step ${phaseIndex(phase) + 1} of 7: ${PHASE_LABEL[phase]}`
  };
}

function patchOperation(
  operations: LiveOperation[],
  operationId: string,
  patch: Partial<LiveOperation>
): LiveOperation[] {
  return operations.map((operation) =>
    operation.operation_id === operationId ? { ...operation, ...patch } : operation
  );
}

function reduceEvent(run: ActiveRun, event: ServerEvent): ActiveRun {
  const next = { ...run, events: [...run.events, event] };

  switch (event.type) {
    case "phase.started": {
      const phase = String(event.phase) as PhaseId;
      return PHASE_ORDER.includes(phase) ? advance(next, phase) : next;
    }

    case "plan.compiled":
      return {
        ...next,
        operations: (event.operations as LiveOperation[]).map((operation) => ({
          ...operation,
          status: "pending"
        })),
        announcement: `${event.operation_count} operations identified.`
      };

    case "route.selected":
      return { ...next, routesSelected: next.routesSelected + 1 };

    case "check.passed":
      return { ...next, passedChecks: [...next.passedChecks, String(event.check_id)] };

    case "approval.required":
      return {
        ...next,
        status: "waiting",
        approval: {
          action: String(event.action),
          reason: String(event.reason),
          maximum_cost_usd: Number(event.maximum_cost_usd ?? 0),
          rollback: String(event.rollback),
          decision: "pending"
        },
        announcement: "Approval required before execution."
      };

    case "approval.recorded":
      return {
        ...next,
        status: event.decision === "approved" ? "running" : "blocked",
        approval: next.approval
          ? { ...next.approval, decision: event.decision as "approved" | "rejected" }
          : null
      };

    case "run.blocked":
      return {
        ...next,
        status: "blocked",
        blocked: {
          check: String(event.check ?? "Protection"),
          reason: String(event.reason ?? ""),
          operationLabel: String(event.operation_label ?? ""),
          userAction: String(event.user_action ?? ""),
          prevented: String(event.prevented ?? "")
        },
        announcement: `Run blocked safely. ${event.reason ?? ""}`
      };

    case "run.started":
      return { ...next, status: "running" };

    case "operation.started":
      return {
        ...next,
        operations: patchOperation(next.operations, String(event.operation_id), {
          status: "running"
        })
      };

    case "operation.completed": {
      const operation = next.operations.find(
        (item) => item.operation_id === String(event.operation_id)
      );
      return {
        ...next,
        operations: patchOperation(next.operations, String(event.operation_id), {
          status: "complete",
          route: String(event.route ?? operation?.route ?? "software"),
          reason: String(event.reason ?? operation?.reason ?? ""),
          actual_cost_usd: Number(event.actual_cost_usd ?? 0),
          duration_ms: Number(event.duration_ms ?? 0),
          detail: event.detail as Record<string, unknown>
        }),
        announcement: `${operation?.label ?? "Operation"} completed.`
      };
    }

    case "run.metrics":
      return { ...next, metrics: event as unknown as RunMetrics };

    case "verification.completed":
      return {
        ...next,
        verification: {
          checks: event.checks as VerificationCheckResult[],
          qualityScore: Number(event.quality_score ?? 0),
          qualityPassed: Boolean(event.quality_passed),
          deadlineMet: (event.deadline_met ?? null) as boolean | null,
          facts: (event.facts ?? []) as Array<{ label: string; value: string; detail?: string }>
        },
        announcement: event.quality_passed ? "Verification passed." : "Verification found issues."
      };

    case "run.stopped":
      return {
        ...next,
        status: "stopped",
        operations: next.operations.map((operation) =>
          operation.status === "pending" || operation.status === "running"
            ? { ...operation, status: "blocked" as const }
            : operation
        ),
        announcement: "Run stopped safely."
      };

    case "run.failed":
      return {
        ...next,
        status: "failed",
        error: {
          message: String(event.message ?? "The run failed."),
          type: String(event.error_type ?? "RunFailed")
        },
        announcement: "The run failed."
      };

    case "run.completed": {
      const proof = event.proof as Proof;
      return advance(
        {
          ...next,
          status: proof.status,
          proof,
          streamState: "closed",
          announcement: "Run completed. The server proof is ready."
        },
        "prove"
      );
    }

    default:
      return next;
  }
}

export function appReducer(state: AppState, action: AppAction): AppState {
  switch (action.type) {
    case "planCompiled":
      return {
        ...state,
        active: {
          ...emptyRun,
          plan: action.plan,
          status: "analyzed",
          operations: action.plan.operations.map((operation) => ({
            ...operation,
            status: "pending" as const
          })),
          announcement: action.plan.plan_summary.title
        }
      };

    case "runStarted":
      return {
        ...state,
        active: { ...state.active, runId: action.runId, status: "running", streamState: "open" }
      };

    case "event": {
      const active = reduceEvent(state.active, action.event);
      if (action.event.type !== "run.completed") return { ...state, active };
      const proof = action.event.proof as Proof;
      return {
        active,
        history: [
          { runId: proof.run_id, workflowId: proof.workflow_id, status: proof.status, proof },
          ...state.history.filter((item) => item.runId !== proof.run_id)
        ]
      };
    }

    /** Authoritative recovery after a dropped stream. */
    case "syncState": {
      const serverState = action.state;
      const phase = (serverState.phase as PhaseId) ?? state.active.currentPhase;
      return {
        ...state,
        active: {
          ...state.active,
          runId: serverState.run_id,
          status: serverState.status,
          operations: serverState.operations,
          metrics: serverState.metrics,
          approval: serverState.approval,
          proof: serverState.proof,
          error: serverState.error,
          currentPhase: PHASE_ORDER.includes(phase) ? phase : state.active.currentPhase,
          maxPhaseReached:
            phaseIndex(phase) > phaseIndex(state.active.maxPhaseReached)
              ? phase
              : state.active.maxPhaseReached,
          viewingPhase:
            state.active.viewingPhase === state.active.currentPhase
              ? phase
              : state.active.viewingPhase
        }
      };
    }

    case "streamState":
      return { ...state, active: { ...state.active, streamState: action.value } };

    case "viewPhase":
      if (phaseIndex(action.phase) > phaseIndex(state.active.maxPhaseReached)) return state;
      return { ...state, active: { ...state.active, viewingPhase: action.phase } };

    case "reset":
      return { ...state, active: { ...emptyRun } };

    default:
      return state;
  }
}

export function protectionChecks(run: ActiveRun): ProtectionCheck[] {
  return run.plan?.protection_checks ?? [];
}
