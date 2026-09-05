import { useRun } from "../state/runContext";
import { PhaseIntro } from "../components/shared/PhaseIntro";
import { RouteBadge, StatusBadge } from "../components/shared/Badges";
import { formatCount, formatDuration, formatUsd } from "../components/shared/format";
import type { LiveOperation } from "../api/types";

function marker(operation: LiveOperation): string {
  switch (operation.status) {
    case "complete":
      return "✓";
    case "running":
      return "•";
    case "blocked":
      return "■";
    case "failed":
      return "!";
    default:
      return String(operation.order);
  }
}

function detailSummary(operation: LiveOperation): string {
  const detail = operation.detail;
  if (!detail || typeof detail !== "object") return "";
  return Object.entries(detail)
    .filter(([, value]) => typeof value !== "object" || value === null)
    .slice(0, 4)
    .map(([key, value]) => `${key.replace(/_/g, " ")}: ${String(value)}`)
    .join(" · ");
}

export function RunPhase() {
  const { state, stopSafely } = useRun();
  const { active } = state;
  const metrics = active.metrics;
  const operations = active.operations;
  const total = metrics?.operations_total ?? operations.length;
  const completed = operations.filter((operation) => operation.status === "complete").length;
  const withoutGenerative = metrics?.without_generative_ai ?? 0;
  const percent = total ? Math.round((withoutGenerative / total) * 100) : 0;
  const running = active.status === "running" || active.status === "waiting";

  return (
    <div className="phase">
      <PhaseIntro
        heading={active.status === "stopped" ? "Stopped safely" : "Running approved operations"}
        supporting={
          completed === 0
            ? `TokenOS is executing ${total} approved operations and reporting each result as it happens.`
            : `${completed} of ${total} operations complete. ${withoutGenerative} did not require generative AI.`
        }
        focusKey="run"
      />

      {active.streamState === "reconnecting" ? (
        <div className="notice notice-warn">
          <h3>Reconnecting to run…</h3>
          <p>The event stream dropped. TokenOS is recovering from authoritative run state.</p>
        </div>
      ) : null}

      {active.error ? (
        <div className="notice notice-risk">
          <h3>The run failed</h3>
          <p>{active.error.message}</p>
        </div>
      ) : null}

      <section className="panel">
        <div className="run-layout">
          <ul className="timeline">
            {operations.map((operation) => (
              <li key={operation.operation_id} className={`op is-${operation.status}`}>
                <span className="op-marker" aria-hidden="true">
                  {marker(operation)}
                </span>
                <div>
                  <div className="op-name">{operation.label}</div>
                  <div className="op-reason">{operation.reason}</div>
                  {operation.status === "complete" && detailSummary(operation) ? (
                    <div className="op-reason" style={{ opacity: 0.85 }}>
                      {detailSummary(operation)}
                    </div>
                  ) : null}
                  <div className="op-meta">
                    <RouteBadge route={operation.route} />
                    {operation.duration_ms !== undefined ? (
                      <StatusBadge tone="neutral">{formatDuration(operation.duration_ms)}</StatusBadge>
                    ) : null}
                    <span className="sr-only">{`Status: ${operation.status}`}</span>
                  </div>
                </div>
                <div className="op-cost">
                  {operation.status === "complete"
                    ? formatUsd(operation.actual_cost_usd ?? 0, true)
                    : "—"}
                </div>
              </li>
            ))}
          </ul>

          <aside className="economics" aria-label="Live measurements">
            <div>
              <div className="row-between">
                <span className="field-label" style={{ marginBottom: 0 }}>
                  Generative AI avoided
                </span>
                <span className="muted">{`${withoutGenerative} of ${total}`}</span>
              </div>
              <div
                className="meter"
                role="progressbar"
                aria-label="Generative AI avoided"
                aria-valuenow={percent}
                aria-valuemin={0}
                aria-valuemax={100}
              >
                <div className="meter-fill" style={{ width: `${percent}%` }} />
              </div>
            </div>

            <div>
              <div className="field-label">Authorized model cost</div>
              <div className="metric-value">
                {formatUsd(metrics?.authorized_model_cost_usd ?? 0)}
              </div>
            </div>

            <div>
              <div className="field-label">Cost so far</div>
              <div className="metric-value">
                {formatUsd(metrics?.calculated_model_cost_usd ?? 0, true)}
              </div>
              <p className="muted" style={{ margin: "4px 0 0", fontSize: 12 }}>
                Measured usage, calculated cost
              </p>
            </div>

            <div>
              <div className="field-label">Model usage</div>
              <p className="muted" style={{ margin: 0, fontSize: 13 }}>
                {formatCount(metrics?.model_calls ?? 0)} call(s) ·{" "}
                {formatCount(metrics?.input_tokens ?? 0)} in ·{" "}
                {formatCount(metrics?.output_tokens ?? 0)} out
              </p>
            </div>

            <div>
              <div className="field-label">Quality</div>
              <div>
                {completed === total && total > 0 ? (
                  <StatusBadge tone="good">Checked by the server</StatusBadge>
                ) : (
                  <StatusBadge tone="neutral">Checking</StatusBadge>
                )}
              </div>
            </div>

            {running ? (
              <button type="button" className="btn btn-risk" onClick={() => void stopSafely()}>
                Stop safely
              </button>
            ) : null}
          </aside>
        </div>
      </section>
    </div>
  );
}
