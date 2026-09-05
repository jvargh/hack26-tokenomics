import { useRun } from "../state/runContext";
import { ApiHealthIndicator } from "./ApiHealthIndicator";

export function AppHeader({
  onOpenHistory,
  onOpenFoundryConfig,
  serverManaged = false,
  onNewRun
}: {
  onOpenHistory: () => void;
  onOpenFoundryConfig: () => void;
  serverManaged?: boolean;
  onNewRun?: () => void;
}) {
  const { state, reset } = useRun();
  const { active, history } = state;
  const started = active.runId !== null || active.plan !== null;

  return (
    <header className="header">
      <div className="identity">
        <div className="mark" aria-hidden="true">
          T
        </div>
        <div>
          <div className="product-name">TokenOS</div>
          <div className="product-descriptor">AI Workflow Optimizer</div>
        </div>
      </div>

      <div className="source">
        <ApiHealthIndicator onConfigure={serverManaged ? undefined : onOpenFoundryConfig} serverManaged={serverManaged} />
        <div className="header-actions">
          {!serverManaged ? <button
            type="button"
            className="btn btn-small btn-secondary"
            onClick={onOpenFoundryConfig}
            title="Configure Azure AI Foundry endpoint, deployments, and price table"
          >
            ⚙ Foundry Config
          </button> : null}
          <button type="button" className="btn btn-small" onClick={onOpenHistory}>
            History{history.length ? ` (${history.length})` : ""}
          </button>
          {started || serverManaged ? (
            <button type="button" className="btn btn-small" onClick={onNewRun ?? reset}>
              New run
            </button>
          ) : null}
        </div>
      </div>
    </header>
  );
}
