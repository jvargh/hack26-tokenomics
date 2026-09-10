import { useState } from "react";
import { AppHeader } from "./components/AppHeader";
import { PhaseStepper } from "./components/PhaseStepper";
import { HistoryDrawer } from "./components/HistoryDrawer";
import { FoundryConfigModal } from "./components/FoundryConfigModal";
import { DescribePhase } from "./phases/DescribePhase";
import { PlanPhase } from "./phases/PlanPhase";
import { OptimizePhase } from "./phases/OptimizePhase";
import { ProtectPhase } from "./phases/ProtectPhase";
import { RunPhase } from "./phases/RunPhase";
import { VerifyPhase } from "./phases/VerifyPhase";
import { ProvePhase } from "./phases/ProvePhase";
import { ReportsScreen } from "./components/reports/ReportsScreen";
import { RunProvider } from "./state/RunProvider";
import { useRun } from "./state/runContext";
import { ACTIVE_OPTIMIZATION_KEY, OptimizationJourney } from "./optimization/OptimizationJourney";

function ActivePhase({ onSelectOptimization, initialWorkflowId }: {
  onSelectOptimization: () => void; initialWorkflowId: string;
}) {
  const { state } = useRun();
  switch (state.active.viewingPhase) {
    case "plan":
      return <PlanPhase />;
    case "optimize":
      return <OptimizePhase />;
    case "protect":
      return <ProtectPhase />;
    case "run":
      return <RunPhase />;
    case "verify":
      return <VerifyPhase />;
    case "prove":
      return <ProvePhase />;
    default:
      return <DescribePhase onSelectOptimization={onSelectOptimization} initialWorkflowId={initialWorkflowId} />;
  }
}

function Announcer() {
  const { state } = useRun();
  return (
    <p className="sr-only" aria-live="polite">
      {state.active.announcement}
    </p>
  );
}

function Shell() {
  const { reset, loadRun } = useRun();
  const [historyOpen, setHistoryOpen] = useState(false);
  const [foundryModalOpen, setFoundryModalOpen] = useState(false);
  const [optimizationRunId, setOptimizationRunId] = useState<string | undefined>(() => {
    try { return sessionStorage.getItem(ACTIVE_OPTIMIZATION_KEY) ?? undefined; } catch { return undefined; }
  });
  const [optimizationMode, setOptimizationMode] = useState(Boolean(optimizationRunId));
  const [initialWorkflowId, setInitialWorkflowId] = useState("");
  const [journeyKey, setJourneyKey] = useState(0);
  const [historyError, setHistoryError] = useState("");
  const [destination, setDestination] = useState<"workflow" | "reports">("workflow");
  const startNew = () => {
    try { sessionStorage.removeItem(ACTIVE_OPTIMIZATION_KEY); } catch { /* Optional persistence. */ }
    reset(); setOptimizationRunId(undefined); setOptimizationMode(false); setJourneyKey((key) => key + 1);
  };
  const openRun = (id: string, workflowId?: string) => {
    setDestination("workflow");
    setHistoryError("");
    if (!workflowId || workflowId === "workflow_optimization") {
      setFoundryModalOpen(false); setOptimizationRunId(id); setOptimizationMode(true);
      setJourneyKey((key) => key + 1);
    } else {
      startNew();
      void loadRun(id).catch((error: unknown) => setHistoryError(error instanceof Error ? error.message : "Could not open the proof."));
    }
  };

  return (
    <div className="app">
      <AppHeader
        onOpenHistory={() => setHistoryOpen(true)}
        onOpenFoundryConfig={() => setFoundryModalOpen(true)}
        onNewRun={startNew}
      />
      <nav className="top-nav" aria-label="Primary">
        <button
          type="button"
          className="nav-item"
          data-testid="workflow-nav"
          aria-current={destination === "workflow" ? "page" : undefined}
          onClick={() => setDestination("workflow")}
        >
          Workflow
        </button>
        <span aria-hidden="true">|</span>
        <button
          type="button"
          className="nav-item"
          data-testid="reports-nav"
          aria-current={destination === "reports" ? "page" : undefined}
          onClick={() => setDestination("reports")}
        >
          Reports
        </button>
      </nav>
      {historyError && <p role="alert" className="error-text">{historyError}</p>}
      {destination === "reports" ? <ReportsScreen onOpenRun={openRun} /> : optimizationMode ? <OptimizationJourney key={journeyKey} initialRunId={optimizationRunId}
        onSelectWorkflow={(id) => { startNew(); setInitialWorkflowId(id); }} /> : <>
        <PhaseStepper />
        <Announcer />
        <main><ActivePhase initialWorkflowId={initialWorkflowId} onSelectOptimization={() => {
          setFoundryModalOpen(false); setOptimizationMode(true); setOptimizationRunId(undefined);
        }} /></main>
      </>}
      {historyOpen ? <HistoryDrawer onClose={() => setHistoryOpen(false)} onOpenRun={(id, workflowId) => {
        setHistoryOpen(false); setHistoryError("");
        openRun(id, workflowId);
      }} /> : null}
      {/* Mounted in every mode so the header's Foundry Config button always works. */}
      <FoundryConfigModal
        isOpen={foundryModalOpen}
        onClose={() => setFoundryModalOpen(false)}
      />
    </div>
  );
}

export default function App() {
  return (
    <RunProvider>
      <Shell />
    </RunProvider>
  );
}
