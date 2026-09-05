import type { ReactNode } from "react";
import { GENERATIVE_ROUTES, routeLabel } from "./format";

/** Colour is never the only signal: every badge also carries text. */
export function RouteBadge({ route }: { route: string }) {
  const tone =
    route === "advanced_ai"
      ? "badge-warn"
      : GENERATIVE_ROUTES.has(route) || route === "batch"
        ? "badge-brand"
        : route === "blocked"
          ? "badge-risk"
          : "badge-good";
  return <span className={`badge ${tone}`}>{routeLabel(route)}</span>;
}

export function StatusBadge({
  tone,
  children
}: {
  tone: "good" | "warn" | "risk" | "brand" | "neutral";
  children: ReactNode;
}) {
  return <span className={tone === "neutral" ? "badge" : `badge badge-${tone}`}>{children}</span>;
}

export function MeasurementBadge({ label }: { label: string }) {
  return (
    <span className="badge" title="How this value was produced">
      {label}
    </span>
  );
}
