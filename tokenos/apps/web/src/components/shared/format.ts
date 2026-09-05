/** Primary UI shows dollars; model costs can be small, so allow four decimals. */
export function formatUsd(value: number, precise = false): string {
  if (!Number.isFinite(value)) return "$0.00";
  if (value === 0) return "$0.00";
  if (precise || Math.abs(value) < 0.01) return `$${value.toFixed(4)}`;
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }).format(value);
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatCount(value: number): string {
  return value.toLocaleString("en-US");
}

export function formatDuration(ms: number): string {
  if (ms <= 0) return "<1 ms";
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}

/** Only these labels appear in the primary UI. */
export const ROUTE_LABEL: Record<string, string> = {
  software: "Regular software",
  retrieval: "Approved retrieval",
  reuse: "Approved reuse",
  efficient_ai: "Efficient AI",
  advanced_ai: "Advanced AI",
  batch: "Scheduled capacity",
  reserved_capacity: "Reserved capacity",
  human_approval: "Human approval",
  blocked: "Blocked safely"
};

export const GENERATIVE_ROUTES = new Set(["efficient_ai", "advanced_ai"]);

export function routeLabel(route: string): string {
  return ROUTE_LABEL[route] ?? route;
}
