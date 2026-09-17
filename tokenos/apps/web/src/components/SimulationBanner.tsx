import { useRun } from "../state/runContext";

/**
 * Standing notice for the hosted judging build.
 *
 * Driven by the mode the server reports at /health rather than a build-time
 * flag, so it cannot disagree with what the API is actually doing. If the
 * server is answering model routes from the simulator, this is visible; if it
 * is calling a provider, it is not.
 *
 * Rendered above everything and never dismissible: a reader who scrolls past it
 * must not be able to lose the context for the figures underneath.
 */
export function SimulationBanner() {
  const { health } = useRun();
  if (health.state !== "ready" || health.health.modelMode !== "simulated") return null;

  return (
    <aside className="simulation-banner" role="note" data-testid="simulation-banner">
      <span className="simulation-banner-title">JUDGE DEMO: SIMULATED AI</span>
      <span className="simulation-banner-body">
        AI calls are simulated for judging purposes. No requests are sent to model
        providers. Azure hosting costs still apply.
      </span>
    </aside>
  );
}
