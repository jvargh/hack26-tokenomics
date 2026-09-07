import { useEffect, useRef, useState } from "react";
import { useRun } from "../state/runContext";
import { api } from "../api/client";
import { formatCount, formatDuration, formatUsd } from "./shared/format";
import { StatusBadge } from "./shared/Badges";
import { workflowTitle } from "./WorkflowChoices";
import { normalizeRecord } from "../optimization/client";
import { dollars, SampleBadge } from "../optimization/OptimizationViews";

/** "2 min ago" reads faster than a clock time when scanning for the latest run. */
function relativeTime(value: string): string {
  const at = new Date(value);
  if (!value || Number.isNaN(at.getTime())) return "";
  const seconds = Math.max(0, Math.round((Date.now() - at.getTime()) / 1000));
  if (seconds < 60) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} hr ago`;
  return `${Math.round(hours / 24)} d ago`;
}

export function HistoryDrawer({ onClose, onOpenRun }: {
  onClose: () => void; onOpenRun: (runId: string, workflowId: string) => void;
}) {
  const { state } = useRun();
  const closeRef = useRef<HTMLButtonElement>(null);
  const [entries, setEntries] = useState<Awaited<ReturnType<typeof api.history>>["runs"]>(
    state.history.map((entry) => ({ run_id: entry.runId, workflow_id: entry.workflowId, status: entry.status, proof: entry.proof, created_at: "" }))
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  /** Deleting a proof is not undoable, so every delete is confirmed in place. */
  const [confirming, setConfirming] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState("");

  useEffect(() => {
    let active = true;
    api.history().then((result) => { if (active) setEntries(result.runs); })
      .catch(() => { if (active) setError("Server history is unavailable. Showing recorded proofs from this browser session."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function removeOne(runId: string) {
    setBusy(runId);
    setError("");
    try {
      await api.deleteRun(runId);
      setEntries((current) => current.filter((entry) => entry.run_id !== runId));
      setNotice("Run deleted.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "That run could not be deleted.");
    } finally {
      setBusy(null);
      setConfirming(null);
    }
  }

  async function removeAll() {
    setBusy("all");
    setError("");
    try {
      const result = await api.deleteAllRuns();
      const remaining = await api.history();
      setEntries(remaining.runs);
      setNotice(result.kept_running > 0
        ? `Deleted ${result.deleted} run(s). ${result.kept_running} still running and were kept.`
        : `Deleted ${result.deleted} run(s).`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "History could not be cleared.");
    } finally {
      setBusy(null);
      setConfirming(null);
    }
  }

  return (
    <div
      className="drawer-backdrop"
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <aside className="drawer" role="dialog" aria-modal="true" aria-label="Run history">
        <div className="drawer-head">
          <h2>History</h2>
          <div className="drawer-head-actions">
            {entries.length > 0 && (
              confirming === "all" ? (
                <>
                  <span className="history-confirm-text">Delete all {entries.length}?</span>
                  <button type="button" className="btn btn-small btn-danger" disabled={busy !== null}
                    onClick={removeAll}>
                    {busy === "all" ? "Deleting…" : "Delete all"}
                  </button>
                  <button type="button" className="btn btn-small" onClick={() => setConfirming(null)}>Keep</button>
                </>
              ) : (
                <button type="button" className="btn btn-small" onClick={() => { setNotice(""); setConfirming("all"); }}>
                  Clear all
                </button>
              )
            )}
            <button ref={closeRef} type="button" className="btn btn-small" onClick={onClose}>
              Close
            </button>
          </div>
        </div>

        <p className="muted">
          Recorded server runs and proofs. Open a completed run to inspect its outcome and cost proof.
          Starting another run never deletes a recorded proof — only you can, with the delete buttons below.
        </p>

        {loading && <p className="muted" role="status">Loading recorded runs…</p>}
        {error && <p className="muted" role="status">{error}</p>}
        {notice && !error && <p className="muted" role="status">{notice}</p>}
        {!loading && entries.length === 0 ? (
          <p className="muted">No completed runs yet.</p>
        ) : (
          <ul className="check-list">
            {entries.map((entry) => (
              <li key={entry.run_id} className="check history-row">
                <button type="button" className="optimization-history-button"
                  onClick={() => onOpenRun(entry.run_id, entry.workflow_id)}
                  aria-label={`Open ${workflowTitle(entry.workflow_id)} ${entry.proof ? "proof" : "run"} ${entry.run_id}`}>
                <div className="check-head">
                  <span className="check-name">{workflowTitle(entry.workflow_id)}</span>
                  {/* The list is newest first; the time makes that obvious. */}
                  {relativeTime(entry.created_at) ? (
                    <time className="history-time" dateTime={entry.created_at}
                      title={new Date(entry.created_at).toLocaleString()}>
                      {relativeTime(entry.created_at)}
                    </time>
                  ) : null}
                  <StatusBadge tone={entry.status === "completed" ? "good" : "warn"}>
                    {entry.status === "completed" ? "Completed" : entry.status.replace(/_/g, " ")}
                  </StatusBadge>
                </div>
                {entry.workflow_id === "workflow_optimization" ? (() => {
                  const record = normalizeRecord(entry.optimization ?? entry.proof);
                  return <div className="muted" style={{ marginTop: 6, fontSize: 12.5 }}>
                    {entry.run_id} · {record.mode === "analyze" ? "Measured current cost" : "Measured governed cost"} ·{" "}
                    {dollars(record.mode === "analyze" ? record.current.costUsd : record.modelSpendUsd)}{" "}
                    <SampleBadge sample={record.sample} />
                  </div>;
                })() : entry.proof ? (
                  <p className="muted" style={{ margin: "6px 0 0", fontSize: 12.5 }}>
                    {entry.run_id} · {entry.proof.measurement_label} ·{" "}
                    {formatUsd(entry.proof.economics.total_calculated_cost_usd, true)} ·{" "}
                    {formatCount(entry.proof.usage.model_calls)} model call(s) ·{" "}
                    {formatDuration(entry.proof.usage.duration_ms)}
                  </p>
                ) : null}
                </button>
                {confirming === entry.run_id ? (
                  <span className="history-row-actions">
                    <button type="button" className="btn btn-small btn-danger" disabled={busy !== null}
                      aria-label={`Confirm delete run ${entry.run_id}`}
                      onClick={() => removeOne(entry.run_id)}>
                      {busy === entry.run_id ? "Deleting…" : "Delete"}
                    </button>
                    <button type="button" className="btn btn-small"
                      aria-label={`Keep run ${entry.run_id}`}
                      onClick={() => setConfirming(null)}>Keep</button>
                  </span>
                ) : (
                  <span className="history-row-actions">
                    <button type="button" className="history-delete"
                      aria-label={`Delete run ${entry.run_id}`}
                      onClick={() => { setNotice(""); setConfirming(entry.run_id); }}>
                      Delete
                    </button>
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </aside>
    </div>
  );
}
