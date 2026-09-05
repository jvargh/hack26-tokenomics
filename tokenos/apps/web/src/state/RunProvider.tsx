import React, { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import { api, openRunStream } from "../api/client";
import { ApiError, type HealthState, type PlanResponse, type WorkflowDefinition } from "../api/types";
import { appReducer, initialAppState, type PhaseId } from "./runStore";
import { RunContext, type RunContextValue } from "./runContext";

/**
 * Owns the connection to the local TokenOS API.
 *
 * There is no client-side simulation: phases, operations, metrics, and the
 * final proof all arrive from the server event stream.
 */
export function RunProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(appReducer, initialAppState);
  const [health, setHealth] = useState<HealthState>({ state: "checking" });
  const [workflows, setWorkflows] = useState<WorkflowDefinition[]>([]);
  const streamRef = useRef<EventSource | null>(null);
  const runIdRef = useRef<string | null>(null);
  const lastSequenceRef = useRef(0);

  const closeStream = useCallback(() => {
    streamRef.current?.close();
    streamRef.current = null;
  }, []);

  useEffect(() => closeStream, [closeStream]);

  const refreshHealth = useCallback(async () => {
    setHealth({ state: "checking" });
    try {
      const result = await api.health();
      setHealth({ state: "ready", health: result });
      const definitions = await api.workflows();
      setWorkflows(definitions.workflows);
    } catch (error) {
      setHealth({
        state: "offline",
        message:
          error instanceof ApiError && error.status !== 0
            ? error.message
            : "Start the TokenOS API on http://localhost:8000. The UI does not generate substitute results."
      });
    }
  }, []);

  useEffect(() => {
    void refreshHealth();
  }, [refreshHealth]);

  const attachStream = useCallback(
    (runId: string) => {
      closeStream();
      streamRef.current = openRunStream(
        runId,
        (event) => {
          lastSequenceRef.current = Math.max(lastSequenceRef.current, event.sequence ?? 0);
          dispatch({ type: "event", event });
          if (
            event.type === "run.completed" ||
            event.type === "run.failed" ||
            event.type === "run.blocked" ||
            event.type === "run.stopped"
          ) {
            closeStream();
            dispatch({ type: "streamState", value: "closed" });
          }
        },
        () => {
          // The browser retries automatically; fall back to authoritative state.
          dispatch({ type: "streamState", value: "reconnecting" });
          void api
            .runState(runId)
            .then((serverState) => dispatch({ type: "syncState", state: serverState }))
            .catch(() => undefined);
        },
        lastSequenceRef.current
      );
      dispatch({ type: "streamState", value: "open" });
    },
    [closeStream]
  );

  const analyze = useCallback(async (payload: unknown): Promise<PlanResponse> => {
    const plan = await api.analyze(payload);
    dispatch({ type: "planCompiled", plan });
    return plan;
  }, []);

  const startRun = useCallback(
    async (planId: string) => {
      lastSequenceRef.current = 0;
      const idempotencyKey = crypto.randomUUID();
      const started = await api.startRun(planId, idempotencyKey);
      runIdRef.current = started.run_id;
      dispatch({ type: "runStarted", runId: started.run_id });
      attachStream(started.run_id);
    },
    [attachStream]
  );

  const loadRun = useCallback(async (runId: string) => {
    closeStream();
    const serverState = await api.runState(runId);
    runIdRef.current = runId;
    lastSequenceRef.current = serverState.last_sequence;
    dispatch({ type: "syncState", state: serverState });
    if (serverState.proof) dispatch({ type: "viewPhase", phase: "prove" });
    else if (serverState.status === "running") attachStream(runId);
  }, [attachStream, closeStream]);

  const approve = useCallback(async (decision: "approved" | "rejected") => {
    if (!runIdRef.current) return;
    await api.approve(runIdRef.current, decision);
  }, []);

  const stopSafely = useCallback(async () => {
    if (!runIdRef.current) return;
    await api.stop(runIdRef.current);
  }, []);

  const reset = useCallback(() => {
    closeStream();
    runIdRef.current = null;
    lastSequenceRef.current = 0;
    dispatch({ type: "reset" });
  }, [closeStream]);

  const viewPhase = useCallback((phase: PhaseId) => dispatch({ type: "viewPhase", phase }), []);

  const value = useMemo<RunContextValue>(
    () => ({
      state,
      health,
      workflows,
      refreshHealth,
      analyze,
      startRun,
      loadRun,
      approve,
      stopSafely,
      reset,
      viewPhase
    }),
    [state, health, workflows, refreshHealth, analyze, startRun, loadRun, approve, stopSafely, reset, viewPhase]
  );

  return <RunContext.Provider value={value}>{children}</RunContext.Provider>;
}
