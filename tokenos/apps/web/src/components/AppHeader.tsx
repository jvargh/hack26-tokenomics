import { useRun } from "../state/runContext";
import { ApiHealthIndicator } from "./ApiHealthIndicator";
import { ThemeToggle } from "./ThemeToggle";

export function AppHeader({
  onOpenHistory,
  onOpenFoundryConfig,
  onNewRun
}: {
  onOpenHistory: () => void;
  onOpenFoundryConfig: () => void;
  onNewRun?: () => void;
}) {
  const { state, reset } = useRun();
  const { history } = state;

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
        <ApiHealthIndicator onConfigure={onOpenFoundryConfig} />
        {/* App chrome, so it stays identical whichever workflow is selected. */}
        <div className="header-actions">
          <ThemeToggle />
          <button
            type="button"
            className="btn btn-small btn-secondary"
            onClick={onOpenFoundryConfig}
            title="Configure Azure AI Foundry endpoint, deployments, and price table"
          >
            ⚙ Foundry Config
          </button>
          <button type="button" className="btn btn-small" onClick={onOpenHistory}>
            History{history.length ? ` (${history.length})` : ""}
          </button>
          <button type="button" className="btn btn-small" onClick={onNewRun ?? reset}>
            New run
          </button>
        </div>
      </div>
    </header>
  );
}
