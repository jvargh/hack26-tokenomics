/**
 * Client for the local TokenOS API.
 *
 * The browser never calculates authoritative results: it uploads real input,
 * asks the API to analyze and run, and renders what the server reports.
 */

import {
  ApiError,
  type BaselineRun,
  type ConnectedApplication,
  type FieldError,
  type FoundryConfig,
  type FoundryTestResult,
  type HealthResponse,
  type PlanResponse,
  type Proof,
  type RunState,
  type ServerEvent,
  type UploadRecord,
  type WorkflowDefinition
} from "./types";

export const API_BASE: string =
  (import.meta.env.VITE_TOKENOS_API_BASE as string | undefined) ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, init);
  } catch {
    throw new ApiError(`The local TokenOS API at ${API_BASE} could not be reached.`, 0);
  }

  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    let fieldErrors: FieldError[] = [];
    try {
      const body = await response.json();
      const detail = body?.detail;
      if (typeof detail === "string") {
        message = detail;
      } else if (detail && Array.isArray(detail.errors)) {
        fieldErrors = detail.errors as FieldError[];
        message = fieldErrors.map((item) => item.message).join(" ");
      } else if (Array.isArray(detail)) {
        message = detail.map((item: { msg?: string }) => item.msg ?? "Invalid input").join(" ");
      }
    } catch {
      /* keep the status text */
    }
    throw new ApiError(message, response.status, fieldErrors);
  }

  return (await response.json()) as T;
}

export const api = {
  health: () => request<HealthResponse>("/health"),

  workflows: () =>
    request<{ workflows: WorkflowDefinition[]; model_available: boolean }>("/api/workflows"),

  async upload(
    workflowId: string,
    role: string,
    files: File[],
    dataClassification: string
  ): Promise<UploadRecord[]> {
    const form = new FormData();
    form.append("workflow_id", workflowId);
    form.append("input_role", role);
    form.append("data_classification", dataClassification);
    files.forEach((file) => form.append("files", file));
    const body = await request<{ uploads: UploadRecord[] }>("/api/uploads", {
      method: "POST",
      body: form
    });
    return body.uploads;
  },

  sampleUploads: (workflowId: string) =>
    request<{ workflow_id: string; uploads: Record<string, UploadRecord[]> }>(
      "/api/uploads/sample",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ workflow_id: workflowId })
      }
    ),

  listConnections: async (workflowId: string) => {    const body = await request<{ applications: ConnectedApplication[] }>(
      `/api/connections?workflow_id=${encodeURIComponent(workflowId)}`
    );
    return body.applications;
  },

  compareBaseline: (runId: string, acknowledged: boolean) =>
    request<BaselineRun>(`/api/runs/${runId}/baseline`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ acknowledged })
    }),

  getComparison: (runId: string) =>
    request<BaselineRun>(`/api/runs/${runId}/comparison`),

  removeUpload: (uploadId: string) =>
    request<{ removed: string }>(`/api/uploads/${uploadId}`, { method: "DELETE" }),

  analyze: (payload: unknown) =>
    request<PlanResponse>("/api/runs/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }),

  startRun: (planId: string, idempotencyKey: string) =>
    request<{ run_id: string; status: string; created: boolean }>("/api/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ plan_id: planId, idempotency_key: idempotencyKey })
    }),

  runState: (runId: string) => request<RunState>(`/api/runs/${runId}`),

  proof: (runId: string) => request<Proof>(`/api/runs/${runId}/proof`),

  approve: (runId: string, decision: "approved" | "rejected") =>
    request<{ run_id: string; decision: string }>(`/api/runs/${runId}/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision })
    }),

  stop: (runId: string) =>
    request<{ run_id: string; stop_requested: boolean }>(`/api/runs/${runId}/stop`, {
      method: "POST"
    }),

  getFoundryConfig: () => request<FoundryConfig>("/api/foundry/config"),

  updateFoundryConfig: (payload: Partial<FoundryConfig> & { api_key?: string }) =>
    request<FoundryConfig>("/api/foundry/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }),

  testFoundry: (deploymentType: "efficient" | "advanced") =>
    request<FoundryTestResult>("/api/foundry/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ deployment_type: deploymentType })
    }),

  history: () =>
    request<{
      runs: Array<{
        run_id: string;
        workflow_id: string;
        status: string;
        created_at: string;
        proof: Proof | null;
        optimization?: unknown;
      }>;
    }>("/api/runs"),

  deleteRun: (runId: string) =>
    request<{ deleted: boolean; run_id: string }>(`/api/runs/${encodeURIComponent(runId)}`, {
      method: "DELETE"
    }),

  deleteAllRuns: () =>
    request<{ deleted: number; kept_running: number }>("/api/runs", { method: "DELETE" })
};

const RUN_EVENT_TYPES = [
  "run.created",
  "phase.started",
  "plan.compiled",
  "optimization.started",
  "route.selected",
  "optimization.completed",
  "protection.started",
  "check.passed",
  "cost.authorized",
  "approval.required",
  "approval.recorded",
  "protection.passed",
  "run.blocked",
  "run.started",
  "operation.started",
  "operation.completed",
  "model.invoked",
  "quality.checked",
  "run.metrics",
  "execution.completed",
  "verification.started",
  "verification.completed",
  "verification.passed",
  "verification.failed",
  "run.stopped",
  "run.completed",
  "run.failed"
] as const;

/** Subscribes to the ordered server event stream. */
export function openRunStream(
  runId: string,
  onEvent: (event: ServerEvent) => void,
  onError: (error: Event) => void,
  lastSequence = 0
): EventSource {
  const query = lastSequence > 0 ? `?last_event_id=${lastSequence}` : "";
  const source = new EventSource(`${API_BASE}/api/runs/${runId}/events${query}`);
  for (const type of RUN_EVENT_TYPES) {
    source.addEventListener(type, (event) => {
      const message = event as MessageEvent<string>;
      try {
        onEvent({ ...(JSON.parse(message.data) as object), type } as ServerEvent);
      } catch {
        /* ignore malformed frames */
      }
    });
  }
  source.onerror = onError;
  return source;
}
