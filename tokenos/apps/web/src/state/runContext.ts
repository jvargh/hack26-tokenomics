import { createContext, useContext } from "react";
import type { HealthState, PlanResponse, WorkflowDefinition } from "../api/types";
import type { AppState, PhaseId } from "./runStore";

export interface RunContextValue {
  state: AppState;
  health: HealthState;
  workflows: WorkflowDefinition[];
  refreshHealth: () => Promise<void>;
  analyze: (payload: unknown) => Promise<PlanResponse>;
  startRun: (planId: string) => Promise<void>;
  loadRun: (runId: string) => Promise<void>;
  approve: (decision: "approved" | "rejected") => Promise<void>;
  stopSafely: () => Promise<void>;
  reset: () => void;
  viewPhase: (phase: PhaseId) => void;
}

export const RunContext = createContext<RunContextValue | null>(null);

export function useRun(): RunContextValue {
  const context = useContext(RunContext);
  if (!context) throw new Error("useRun must be used inside RunProvider");
  return context;
}
