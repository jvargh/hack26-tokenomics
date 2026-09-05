import { API_BASE } from "../api/client";
import { useRun } from "../state/runContext";

/** Replaces the old run-source selector with real local API status. */
export function ApiHealthIndicator({ onConfigure, serverManaged = false }: {
  onConfigure?: () => void; serverManaged?: boolean;
}) {
  const { health, refreshHealth } = useRun();

  const label =
    health.state === "checking"
      ? "Checking local TokenOS API"
      : health.state === "offline"
        ? "Local API offline"
        : health.health.foundryAvailable
          ? "Local API ready · Foundry connected"
          : "Local TokenOS API ready · Foundry not configured";

  const tone =
    health.state === "checking" ? "is-checking" : health.state === "offline" ? "is-offline" : "is-ready";

  return (
    <div className={`api-health ${tone}`}>
      <div className="api-health-row">
        <span className="api-dot" aria-hidden="true" />
        <span className="api-health-label">{label}</span>
      </div>
      {health.state === "ready" ? (
        <p className="muted api-health-detail">
          {API_BASE} · v{health.health.version} ·{" "}
          {serverManaged ? (
            <span>Model aliases and pricing are configured on the server.</span>
          ) : health.health.foundryAvailable ? (
            <span>
              {health.health.efficientDeployment} / {health.health.advancedDeployment}
            </span>
          ) : (
            <span
              onClick={onConfigure}
              style={{ cursor: "pointer", textDecoration: "underline" }}
              title="Click to configure Foundry endpoint"
            >
              Configure Foundry models →
            </span>
          )}
        </p>
      ) : (
        <p className="muted api-health-detail">
          {health.state === "offline"
            ? "Start the TokenOS API on http://localhost:8000. The UI does not generate substitute results."
            : "Contacting the local service…"}
        </p>
      )}
      {health.state === "offline" ? (
        <button type="button" className="btn btn-small" onClick={() => void refreshHealth()}>
          Retry
        </button>
      ) : null}
    </div>
  );
}
