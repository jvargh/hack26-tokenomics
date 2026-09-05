import { useCallback, useEffect, useRef, useState } from "react";
import type { ConnectedApplication } from "../api/types";
import { PhaseIntro } from "../components/shared/PhaseIntro";
import { WorkflowChoices, workflowTitle } from "../components/WorkflowChoices";
import { useRun } from "../state/runContext";
import { PHASE_LABEL, PHASE_ORDER, type PhaseId } from "../state/runStore";
import { EMPTY_DRAFT, OptimizationDescribe, type OptimizationDraft, type OptimizationSample, type PromptExample } from "./OptimizationDescribe";
import { OptimizationApiError, optimizationApi, optimizationStream, type OptimizationEvent } from "./client";
import { OptimizeView, PlanView, ProtectView, ProveView, SampleBadge, VerifyView } from "./OptimizationViews";
import type { OptimizationRecord } from "./types";
import "./optimization.css";

export const ACTIVE_OPTIMIZATION_KEY = "tokenos.optimization.activeRun";
const terminal = (record: OptimizationRecord) => ["completed", "failed", "blocked", "unavailable"].includes(record.status);

function eventDescription(event: OptimizationEvent): string {
  switch (event.type) {
    case "phase.started": return `${PHASE_LABEL[event.phase as PhaseId] ?? "Workflow"} started`;
    case "phase.completed": return `${PHASE_LABEL[event.phase as PhaseId] ?? "Workflow"} completed`;
    case "prompt.analyzed": return "Prompt composition analyzed";
    case "context.decided": return "Prompt context decisions recorded";
    case "operation.started": return `${event.label ?? "Operation"} started`;
    case "operation.completed": return `${event.operationId ?? "Operation"} completed`;
    case "data.policy": return `Artifact data decision: ${event.decision ?? "recorded"}`;
    case "safeguards.refreshed": return "Draft safeguards refreshed without invoking a model";
    case "model.authorized": return "Protected model authorization recorded";
    case "budget.reserved": return `Model budget reserved for ${event.deploymentAlias ?? "an allowed alias"}`;
    case "model.usage": return "Provider usage received and measured";
    case "budget.reconciled": return "Model cost reconciled against the pinned price table";
    case "quality.result": return `Quality check ${event.passed === true ? "passed" : "failed"}`;
    case "escalation.decision": return `Escalation: ${(event.decision ?? "recorded").replace(/_/g, " ")}`;
    case "execution.failed": return event.message ?? "Execution unavailable; inspect the recorded safe failure.";
    case "baseline.started": return "Matched all-AI comparison started";
    case "baseline.completed": return "Matched all-AI comparison completed";
    case "run.failed": return "Run ended without a verified outcome";
    case "run.completed": return "Governed run completed";
    default: return "Server event recorded";
  }
}

function EventDetails({ events }: { events: OptimizationEvent[] }) {
  return <details><summary>Operation-level events ({events.length})</summary>
    <ul className="optimization-events">{events.map((event) => <li key={`${event.sequence}-${event.type}`}>
      <time dateTime={event.at}>{new Date(event.at).toLocaleTimeString()}</time>{eventDescription(event)}
      {event.baseline && <span className="optimization-badge" style={{ marginLeft: 8 }}>All-AI comparison</span>}
    </li>)}</ul>
    {!events.length && <p className="muted">Waiting for the first server event.</p>}
  </details>;
}

export function OptimizationJourney({ initialRunId, onSelectWorkflow }: {
  initialRunId?: string; onSelectWorkflow: (workflowId: string) => void;
}) {
  const { workflows, health } = useRun();
  const [draft, setDraft] = useState<OptimizationDraft>({ ...EMPTY_DRAFT });
  const [samples, setSamples] = useState<OptimizationSample[]>([]);
  const [promptExamples, setPromptExamples] = useState<PromptExample[]>([]);
  const [applications, setApplications] = useState<ConnectedApplication[]>([]);
  const [record, setRecord] = useState<OptimizationRecord | null>(null);
  const [phase, setPhase] = useState<PhaseId>("describe");
  const [reached, setReached] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [events, setEvents] = useState<OptimizationEvent[]>([]);
  const [streamStatus, setStreamStatus] = useState<"idle" | "connecting" | "live" | "fallback" | "complete">("idle");
  const [acknowledged, setAcknowledged] = useState(false);
  const [humanApproved, setHumanApproved] = useState(false);
  const [comparing, setComparing] = useState(false);
  const [announcement, setAnnouncement] = useState("");
  const [sourceReload, setSourceReload] = useState(0);
  const streamRef = useRef<EventSource | null>(null);
  const fallbackRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const lastSequence = useRef(0);
  const liveGeneration = useRef(0);
  const alive = useRef(true);

  const clearFallback = useCallback(() => {
    if (fallbackRef.current) clearInterval(fallbackRef.current);
    fallbackRef.current = null;
  }, []);
  const closeStream = useCallback(() => {
    streamRef.current?.close();
    streamRef.current = null;
    clearFallback();
    liveGeneration.current += 1;
  }, [clearFallback]);
  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; closeStream(); };
  }, [closeStream]);

  const remember = useCallback((next: OptimizationRecord) => {
    setRecord(next);
    try { sessionStorage.setItem(ACTIVE_OPTIMIZATION_KEY, next.runId); } catch { /* Persistence is optional in private browsing. */ }
  }, []);
  const navigate = (next: PhaseId) => {
    setPhase(next);
    setReached((value) => Math.max(value, PHASE_ORDER.indexOf(next)));
    setAnnouncement(`${PHASE_LABEL[next]}: ${workflowTitle("workflow_optimization")}`);
  };

  useEffect(() => {
    let active = true;
    Promise.allSettled([optimizationApi.samples(), optimizationApi.promptExamples(), optimizationApi.applications()])
      .then(([loadedSamples, loadedPromptExamples, loadedApps]) => {
        if (!active) return;
        if (loadedSamples.status === "fulfilled") setSamples(loadedSamples.value);
        if (loadedPromptExamples.status === "fulfilled") setPromptExamples(loadedPromptExamples.value);
        if (loadedApps.status === "fulfilled") setApplications(loadedApps.value);
        const failed = [loadedSamples, loadedApps].find((result) => result.status === "rejected");
        if (failed?.status === "rejected") setError(failed.reason instanceof Error ? failed.reason.message : "Workflow sources unavailable.");
      });
    return () => { active = false; };
  }, [sourceReload]);

  const attachStream = useCallback((id: string, baseline = false) => {
    closeStream();
    const generation = liveGeneration.current;
    let refreshing = false;
    let finishing = false;
    const valid = () => alive.current && generation === liveGeneration.current;
    setStreamStatus("connecting");
    const sync = async (finish: boolean) => {
      if (refreshing || !valid()) return;
      refreshing = true;
      try {
        const next = await optimizationApi.state(id);
        if (!valid()) return;
        remember(next);
        const done = baseline ? Boolean(next.comparison && next.comparison.status !== "running") : terminal(next);
        if (finish || done) {
          closeStream();
          setStreamStatus("complete");
          if (baseline) setComparing(false);
          setAnnouncement(baseline ? "All-AI comparison result recorded." : "Execution finished. Review verification before cost proof.");
        }
      } catch (reason) {
        if (valid()) {
          setError(reason instanceof Error ? reason.message : "Could not retrieve the authoritative run state.");
          if (finish && !fallbackRef.current) {
            setStreamStatus("fallback");
            fallbackRef.current = setInterval(() => void sync(false), 2000);
          }
        }
      } finally {
        refreshing = false;
        // A terminal frame can arrive while a fallback read is already in flight.
        if (finishing && valid() && !fallbackRef.current) {
          setStreamStatus("fallback");
          fallbackRef.current = setInterval(() => void sync(false), 2000);
        }
      }
    };
    const source = optimizationStream(id, (event) => {
      if (!valid() || event.sequence <= lastSequence.current) return;
      lastSequence.current = event.sequence;
      setEvents((current) => [...current, event]);
      setAnnouncement(eventDescription(event));
      const done = baseline ? event.type === "baseline.completed" : event.type === "run.completed" || event.type === "run.failed";
      if (done && !finishing) { finishing = true; void sync(true); }
    }, () => {
      if (!valid() || finishing) return;
      setStreamStatus("fallback");
      void sync(false);
      if (!fallbackRef.current) fallbackRef.current = setInterval(() => void sync(false), 2000);
    }, () => {
      if (!valid()) return;
      clearFallback();
      setStreamStatus("live");
    }, lastSequence.current);
    streamRef.current = source;
  }, [clearFallback, closeStream, remember]);

  useEffect(() => {
    if (!initialRunId) return;
    let active = true;
    setBusy(true);
    optimizationApi.state(initialRunId).then((next) => {
      if (!active) return;
      remember(next);
      const restoredPhase: PhaseId = terminal(next) ? "prove"
        : next.status === "running" ? "run" : next.status === "authorized" ? "run"
        : next.status === "optimized" ? "protect" : next.status === "planned" ? "plan" : "describe";
      setPhase(restoredPhase); setReached(PHASE_ORDER.indexOf(restoredPhase));
      if (next.status === "running") attachStream(next.runId);
      else if (next.comparison?.status === "running") { setComparing(true); attachStream(next.runId, true); }
    }).catch((reason: unknown) => {
      if (active) setError(reason instanceof Error ? reason.message : "Could not open this proof.");
    }).finally(() => { if (active) setBusy(false); });
    return () => { active = false; };
  }, [initialRunId, remember, attachStream]);

  async function action(callback: () => Promise<void>) {
    if (busy) return;
    setBusy(true); setError("");
    try { await callback(); }
    catch (reason) {
      if (!alive.current) return;
      setError(reason instanceof Error ? reason.message : "The requested action could not be completed.");
      if (reason instanceof OptimizationApiError && reason.checks.length) {
        setRecord((current) => current ? { ...current, safeguards: reason.checks, canAuthorize: false } : current);
      }
    } finally { if (alive.current) setBusy(false); }
  }

  function editDraft() {
    closeStream(); setRecord(null); setEvents([]); setReached(0); setPhase("describe");
    setAcknowledged(false); setHumanApproved(false); lastSequence.current = 0;
    try { sessionStorage.removeItem(ACTIVE_OPTIMIZATION_KEY); } catch { /* Optional persistence. */ }
  }
  const buildPlan = () => void action(async () => {
    const described = await optimizationApi.create(draft);
    remember(described);
    const planned = await optimizationApi.analyze(described.runId);
    remember(planned); navigate("plan");
  });
  const approvePlan = () => record && void action(async () => {
    const optimized = await optimizationApi.optimize(record.runId);
    remember(optimized); navigate("optimize");
  });
  const authorize = () => record && void action(async () => {
    const authorized = await optimizationApi.authorize(record.runId, humanApproved);
    remember(authorized); navigate("run");
  });
  const execute = () => record && void action(async () => {
    const started = await optimizationApi.execute(record.runId);
    remember(started); attachStream(started.runId);
  });
  const baseline = () => {
    if (!record || !acknowledged || comparing) return;
    setComparing(true);
    void action(async () => {
      try {
        const next = await optimizationApi.baseline(record.runId);
        remember(next); attachStream(next.runId, true);
      } catch (reason) { setComparing(false); throw reason; }
    });
  };
  const workEvents = events.filter((event) => !event.baseline);
  const done = record ? terminal(record) : false;
  const localDone = workEvents.some((event) => event.type === "operation.completed" && ["local", "reuse"].includes(event.route ?? ""));
  const modelCalled = workEvents.some((event) => event.type === "model.usage") || Boolean(record?.usage.length);
  const noModelNeeded = done && record?.modelCalls === 0;
  const isPromptRun = record?.optimizationTarget === "single_prompt";
  const showRun = () => record && <>
    <PhaseIntro heading={done ? "Execution finished. Inspect the outcome." : record.status === "authorized" ? "Protected and ready to run" : "Only the necessary work, in real time"}
      supporting="Progress and measurements come from server events. The browser does not generate execution results." focusKey="optimization-run" />
    <section className="panel"><div className="row-between"><h3>Governed execution</h3>
      <span className="optimization-badge">{streamStatus === "live" ? "Live · SSE" : streamStatus === "fallback" ? "Reconnecting · state fallback" : streamStatus === "complete" ? "Recorded" : streamStatus === "connecting" ? "Connecting to event stream" : "Awaiting your action"}</span>
    </div>
      <SampleBadge sample={record.sample} />
      <ol className="optimization-progress">
        <li className={record.authorized ? "is-done" : ""}>{isPromptRun ? "Checked prompt, context, and quality requirements" : "Checked input and quality requirements"}</li>
        <li className={localDone || done ? "is-done" : ""}>{isPromptRun ? "Removed or minimized ineligible context" : "Completed local validation and reuse opportunities"}</li>
        <li className={modelCalled || noModelNeeded ? "is-done" : ""}>
          {isPromptRun ? "Authorized the least-cost eligible model route" : noModelNeeded ? "No model call was needed for this route" : "Sent only necessary context to the efficient model"}
          {!modelCalled && !done && <small>Conditional: only if deterministic work cannot finish the outcome.</small>}
        </li>
        <li className={record.qualityPassed === true ? "is-done" : ""}>
          {isPromptRun ? "Ran the governed prompt and recorded actual usage" : done && record.qualityPassed !== true ? "Recorded execution; required outcome was not verified" : "Verified result and reconciled measured model cost"}
        </li>
      </ol>
      {record.error && <p className="error-text" role="alert">{record.error}</p>}
      <EventDetails events={events} />
      <div className="btn-row btn-row-end">
        {record.status === "authorized" && <button type="button" className="btn btn-primary" onClick={execute} disabled={busy}>{isPromptRun ? "Run governed prompt" : "Run authorized workflow"}</button>}
        {done && <button type="button" className="btn btn-primary" onClick={() => navigate("verify")}>Inspect verified outcome</button>}
      </div>
    </section>
  </>;

  return <>
    <nav className="stepper" aria-label="Optimization workflow progress"><ol>
      {PHASE_ORDER.map((step, index) => <li key={step} className={`step ${step === phase ? "is-current is-viewing" : index <= reached ? "is-complete" : "is-future"}`}>
        <button type="button" disabled={index > reached || busy || comparing || record?.status === "running" && step !== "run"}
          aria-current={step === phase ? "step" : undefined} aria-pressed={step === phase}
          onClick={() => { setPhase(step); setAnnouncement(`Viewing ${PHASE_LABEL[step]}`); }}>
          <span className="step-circle" aria-hidden="true">{index + 1}</span><span className="step-label">{PHASE_LABEL[step]}</span>
          <span className="sr-only">Step {index + 1} of 7: {PHASE_LABEL[step]}</span>
        </button>
      </li>)}
    </ol><p className="step-mobile">Step {PHASE_ORDER.indexOf(phase) + 1} of 7: {PHASE_LABEL[phase]}</p></nav>
    <p className="sr-only" aria-live="polite">{announcement}</p>
    <main><div className="phase">
      {phase !== "describe" && <div className="optimization-eyebrow"><span>{workflowTitle("workflow_optimization")}</span>
        <span className="optimization-badge">{record?.optimizationTarget === "single_prompt" ? "Optimize a prompt before you run it" : record?.mode === "analyze" ? "Analyze current workflow" : "Measure an optimized workflow"}</span>
        <SampleBadge sample={record?.sample ?? false} />
      </div>}
      {error && <div className="notice" role="alert"><strong>Action needed</strong><p>{error}</p>
        {phase === "describe" && (!samples.length || !applications.length) && <button type="button" className="btn btn-small"
          onClick={() => { setError(""); setSourceReload((value) => value + 1); }}>Retry workflow sources</button>}
      </div>}
      {busy && !record && <p role="status">Loading the authoritative workflow record…</p>}
      {phase === "describe" && <>
        <WorkflowChoices workflows={workflows} selected="workflow_optimization" onSelect={(id) => {
          if (id !== "workflow_optimization") onSelectWorkflow(id);
        }} />
        <OptimizationDescribe draft={draft} onChange={(next) => { if (record) editDraft(); setDraft(next); }}
          samples={samples} promptExamples={promptExamples} applications={applications} ready={health.state === "ready"} busy={busy} onSubmit={buildPlan} />
      </>}
      {phase === "plan" && record && <PlanView record={record} busy={busy || record.status !== "planned"} onApprove={approvePlan} onEdit={editDraft} />}
      {phase === "optimize" && record && <OptimizeView record={record} busy={busy} onProtect={() => navigate("protect")} />}
      {phase === "protect" && record && <ProtectView record={record} busy={busy} onAuthorize={authorize}
        onRefresh={() => void action(async () => { remember(await optimizationApi.refreshSafeguards(record.runId)); })}
        onEdit={editDraft} humanApproved={humanApproved} onHumanApproved={setHumanApproved} />}
      {phase === "run" && showRun()}
      {phase === "verify" && record && <VerifyView record={record} onProve={() => navigate("prove")} onEdit={editDraft}
        onEscalate={() => { editDraft(); setDraft((current) => ({ ...current, allowAdvanced: true })); }} />}
      {phase === "prove" && record && <>
        <ProveView record={record} acknowledged={acknowledged} setAcknowledged={setAcknowledged} comparing={comparing} onBaseline={baseline} />
        {comparing && <section className="panel"><h3>Live all-AI comparison</h3><p role="status" className="muted">
          {streamStatus === "fallback" ? "Reconnecting; retrieving authoritative comparison state." : "Receiving server-sent comparison events."}
        </p><EventDetails events={events.filter((event) => event.baseline || event.type.startsWith("baseline."))} /></section>}
      </>}
    </div></main>
  </>;
}
