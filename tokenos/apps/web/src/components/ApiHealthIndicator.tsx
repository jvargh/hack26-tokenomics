import { API_BASE } from "../api/client";
import { useRun } from "../state/runContext";

/** Replaces the old run-source selector with real API status. */
export function ApiHealthIndicator({ onConfigure }: { onConfigure?: () => void }) {
  const { health, refreshHealth } = useRun();
  const endpointLabel = API_BASE || "Same origin";
  const simulated = health.state === "ready" && health.health.modelMode === "simulated";

  const label =
    health.state === "checking"
      ? "Checking TokenOS API"
      : health.state === "offline"
        ? "TokenOS API offline"
        : simulated
          ? "TokenOS API ready · Simulated AI"
          : health.health.foundryAvailable
            ? "TokenOS API ready · Foundry connected"
            : "TokenOS API ready · Foundry not configured";

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
          {endpointLabel} · v{health.health.version} ·{" "}
          {/* Same line in every workflow. Deployment bindings are a server
              concern, and the UI refers to models by alias, not by raw name. */}
          {simulated ? (
            // No Foundry configuration link here: offering one would invite a
            // judge to try to connect a provider the hosted build cannot use.
            <span>Model routes are answered by the built-in simulator.</span>
          ) : health.health.foundryAvailable ? (
            <span>Model aliases and pricing are configured on the server.</span>
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
