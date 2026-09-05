import { API_BASE } from "../api/client";
import type { ConnectedApplication, UploadRecord } from "../api/types";
import type { ExampleDefaults, OptimizationDraft, OptimizationSample, PromptExample } from "./OptimizationDescribe";
import { representativeRequests } from "./OptimizationDescribe";
import type { OptimizationGate, OptimizationRecord, OptimizationUsage, PromptChange, PromptComponent, PromptContextDecision, PromptPlan, PromptProof } from "./types";

type ObjectValue = Record<string, unknown>;
const object = (value: unknown): ObjectValue => value !== null && typeof value === "object" && !Array.isArray(value) ? value as ObjectValue : {};
const array = (value: unknown): unknown[] => Array.isArray(value) ? value : [];
const text = (value: unknown, fallback = ""): string => typeof value === "string" ? value : fallback;
const number = (value: unknown): number | undefined => typeof value === "number" && Number.isFinite(value) ? value : undefined;
const strings = (value: unknown): string[] => array(value).filter((entry): entry is string => typeof entry === "string");

const exampleDefaultsError = () => new OptimizationApiError(
  "Example defaults are incomplete. Restart or update the TokenOS API, then reload workflow sources.", 502
);

function exampleText(value: unknown): string {
  if (typeof value !== "string" || !value.trim()) throw exampleDefaultsError();
  return value;
}

function exampleNumber(value: unknown): number {
  const result = number(value);
  if (result === undefined || result < 0) throw exampleDefaultsError();
  return result;
}

function exampleChoice<T extends string>(value: unknown, choices: readonly T[]): T {
  const choice = choices.find((item) => item === value);
  if (choice === undefined) throw exampleDefaultsError();
  return choice;
}

function exampleDefaults(example: ObjectValue): ExampleDefaults {
  const requirements = object(example.requirements);
  const volume = object(example.recurringVolume);
  const quality = strings(requirements.qualityRequirements);
  if (!quality.length || typeof requirements.allowAdvancedEscalation !== "boolean") throw exampleDefaultsError();
  return {
    desiredOutcome: exampleText(example.desiredOutcome),
    recurringVolume: {
      value: exampleNumber(volume.value),
      period: exampleChoice(volume.period, ["day", "week", "month", "year"])
    },
    requirements: {
      qualityRequirements: quality,
      optimizationGoal: exampleText(requirements.optimizationGoal),
      maxModelSpendUsd: exampleNumber(requirements.maxModelSpendUsd),
      maxInputTokens: exampleNumber(requirements.maxInputTokens),
      maxOutputTokens: exampleNumber(requirements.maxOutputTokens),
      latencyTargetMs: exampleNumber(requirements.latencyTargetMs),
      allowAdvancedEscalation: requirements.allowAdvancedEscalation,
      maxAdvancedCalls: exampleNumber(requirements.maxAdvancedCalls)
    }
  };
}

export class OptimizationApiError extends Error {
  constructor(message: string, readonly status: number, readonly checks: OptimizationGate[] = []) { super(message); }
}

async function request(path: string, init?: RequestInit): Promise<ObjectValue> {
  let response: Response;
  try { response = await fetch(`${API_BASE}${path}`, init); }
  catch { throw new OptimizationApiError("The TokenOS API is unavailable. No substitute results were generated.", 0); }
  const data = await response.json().catch(() => ({})) as unknown;
  const body = object(data);
  if (!response.ok) {
    const detail = object(body.detail);
    const validation = array(body.detail).map((item) => text(object(item).msg)).filter(Boolean).join(" ");
    throw new OptimizationApiError(text(detail.message) || text(body.detail) || validation || `Request failed (${response.status}).`,
      response.status, gates(detail.protectionChecks));
  }
  return body;
}

const post = (path: string, body?: unknown) => request(path, {
  method: "POST", ...(body === undefined ? {} : { headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
});

const GATE_LABELS: Record<string, string> = {
  output_contract: "Output contract", outcome_acceptance: "Required outcome accepted",
  same_answer_quality: "Same decision or answer quality", grounded_citations: "Grounded citations",
  structured_output: "Valid structured output", required_tests: "Required tests",
  latency_target: "Latency target", human_approval: "Required human approval"
};

const CHECK_ACTIONS: Record<string, string> = {
  manifest: "Rebuild the plan from unchanged artifacts.",
  quality: "Edit representative requests to include expectedOutput and any required source context or tests.",
  local_adapters: "Use a supported input shape for the allowlisted local adapter.",
  data_policy: "Approve the required human action, or revise blocked artifact data handling.",
  human_approval: "Review the selected outcomes and record explicit human approval below.",
  scope: "Choose a registered application with the required approved scopes.",
  provider: "Ask the server administrator to configure the required deployment aliases and authentication.",
  prices_context: "Configure versioned prices server-side and supply bounded source evidence.",
  budget: "Reduce model work or edit requirements to authorize an appropriate spend ceiling.",
  price_version: "Refresh draft safeguards to pin the administrator's current price table before authorization.",
  configuration: "Refresh draft safeguards after the server deployment configuration change.",
  model_cost_acknowledgement: "Authorize the protected run to explicitly permit the displayed model budget."
};

function gates(value: unknown): OptimizationGate[] {
  return array(value).map((entry, index) => {
    const gate = object(entry);
    const id = text(gate.id);
    return {
      id: `${text(gate.requestId)}:${id}:${index}`,
      name: `${text(gate.requestId) ? `${text(gate.requestId)} · ` : ""}${text(gate.name) || GATE_LABELS[id] || id.replace(/_/g, " ")}`,
      passed: typeof gate.passed === "boolean" ? gate.passed : null,
      detail: text(gate.detail),
      action: text(gate.userAction) || CHECK_ACTIONS[id]
    };
  });
}

function uploadRecord(value: unknown): UploadRecord {
  const file = object(value);
  return {
    upload_id: text(file.fileId) || text(file.sha256), name: text(file.filename),
    role: text(file.role), workflow_id: "workflow_optimization", media_type: text(file.contentType),
    size_bytes: number(file.size) ?? 0, sha256: text(file.sha256), status: "ready",
    data_classification: "internal", extracted_character_count: 0, detail: file, origin: "upload"
  };
}

function promptComponent(value: unknown): PromptComponent {
  const component = object(value);
  return {
    id: text(component.id),
    label: text(component.label),
    estimatedTokens: number(component.estimatedTokens),
    candidateTreatment: text(component.candidateTreatment),
    reason: text(component.reason)
  };
}

function promptContextDecision(value: unknown): PromptContextDecision {
  const decision = object(value);
  return {
    id: text(decision.id),
    label: text(decision.label),
    decision: text(decision.decision),
    reason: text(decision.reason),
    estimatedTokens: number(decision.estimatedTokens),
    sourceId: text(decision.sourceId)
  };
}

function promptChange(value: unknown): PromptChange {
  const change = object(value);
  return {
    id: text(change.id),
    change: text(change.change),
    reason: text(change.reason),
    evidenceState: text(change.evidenceState)
  };
}

function outputContractLabel(value: unknown): string {
  const contract = object(value);
  return Object.keys(contract).length
    ? `Structured ${text(contract.type, "output")} · required: ${strings(contract.required).join(", ")}`
    : "";
}

function normalizePromptPlan(value: unknown): PromptPlan | null {
  const plan = object(value);
  if (!Object.keys(plan).length) return null;
  const current = object(plan.current);
  const candidate = object(plan.candidate);
  const cacheEligibility = text(candidate.cacheEligibility, "unknown");
  return {
    current: {
      estimatedInputTokens: number(current.estimatedInputTokens),
      currentModel: text(current.currentModel),
      components: array(current.components).map(promptComponent)
    },
    candidate: {
      governedPrompt: text(candidate.governedPrompt),
      governedSystemPrompt: text(candidate.governedSystemPrompt),
      eligibleContextIds: strings(candidate.eligibleContextIds),
      minimizedContextIds: strings(candidate.minimizedContextIds),
      blockedContextIds: strings(candidate.blockedContextIds),
      estimatedInputTokens: number(candidate.estimatedInputTokens),
      estimatedReductionTokens: number(candidate.estimatedReductionTokens),
      estimatedReductionPercent: number(candidate.estimatedReductionPercent),
      cacheEligibility: cacheEligibility === "eligible" || cacheEligibility === "not_eligible" ? cacheEligibility : "unknown",
      cacheReason: text(candidate.cacheReason),
      recommendedModelAlias: text(candidate.recommendedModelAlias),
      routeReason: text(candidate.routeReason),
      outputContract: candidate.outputContract ?? null
    },
    contextDecisions: array(plan.contextDecisions).map(promptContextDecision),
    changes: array(plan.changes).map(promptChange),
    improvements: strings(plan.improvements),
    evidenceStatus: text(plan.evidenceStatus, "estimated")
  };
}

function normalizePromptProof(value: unknown): PromptProof | null {
  const proof = object(value);
  if (!Object.keys(proof).length) return null;
  const estimatedBefore = object(proof.estimatedBefore);
  const estimatedAfter = object(proof.estimatedAfter);
  const cost = object(proof.measuredCost);
  return {
    originalPromptHash: text(proof.originalPromptHash),
    governedPromptHash: text(proof.governedPromptHash),
    promptComponents: array(proof.promptComponents).map(promptComponent),
    contextDecisions: array(proof.contextDecisions).map(promptContextDecision),
    estimatedBefore: Object.keys(estimatedBefore).length ? { inputTokens: number(estimatedBefore.inputTokens) } : undefined,
    estimatedAfter: Object.keys(estimatedAfter).length ? { inputTokens: number(estimatedAfter.inputTokens) } : undefined,
    measuredUsage: Object.keys(object(proof.measuredUsage)).length ? normalizedUsage([proof.measuredUsage])[0] ?? null : null,
    measuredCost: Object.keys(cost).length ? { ...cost, costUsd: number(cost.costUsd), modelSpendUsd: number(cost.modelSpendUsd) } : null,
    measuredInputTokenReduction: proof.measuredInputTokenReduction === null ? null : number(proof.measuredInputTokenReduction),
    outputFormat: text(proof.outputFormat),
    governedPrompt: text(proof.governedPrompt)
  };
}

function safeAlias(value: string): string {
  return ["tokenos-efficient", "tokenos-advanced", "tokenos-baseline", "local", "reuse", "model", "unknown"].includes(value) || /^imported-model-\d+$/.test(value)
    ? value : "Imported model route";
}

function normalizedUsage(value: unknown): OptimizationUsage[] {
  return array(value).map((entry) => {
    const call = object(entry);
    const evidence = object(call.minimalEvidence);
    return {
      id: text(call.callId), purpose: text(call.purpose), whyAI: text(call.whyNotLocal),
      minimalEvidence: text(call.minimalEvidence) || [
        strings(evidence.sourceIds).length ? `Source excerpts: ${strings(evidence.sourceIds).join(", ")}` : "",
        number(evidence.inputCharacters) !== undefined ? `${number(evidence.inputCharacters)} input characters` : "",
        evidence.expectedOutputsSent === false ? "Expected answers were not sent" : ""
      ].filter(Boolean).join(" · "),
      alias: safeAlias(text(call.deploymentAlias)), inputTokens: number(call.inputTokens), outputTokens: number(call.outputTokens),
      cachedInputTokens: number(call.cachedInputTokens), reasoningTokens: number(call.reasoningTokens),
      totalTokens: number(call.totalTokens), costUsd: number(call.costUsd), durationMs: number(call.latencyMs),
      requestId: text(call.providerRequestId), qualityPassed: typeof call.qualityPassed === "boolean" ? call.qualityPassed : null,
      qualityDetail: text(call.qualityDetail), escalation: text(call.escalationDecision).replace(/_/g, " "),
      optionalPresentation: call.optionalPresentation === true
    };
  });
}

export function normalizeRecord(value: unknown): OptimizationRecord {
  const state = object(value);
  const proof = object(state.proof);
  const run = { ...state, ...proof };
  const current = object(run.currentRoute);
  const candidate = object(run.candidateRoute);
  const requirements = object(state.requirements);
  const contract = object(run.executionContract);
  const cost = object(run.cost);
  const verification = object(run.verification);
  const baseline = object(run.baseline);
  const projection = object(cost.projection);
  const safeguards = gates(state.protectionChecks);
  const operations = array(run.operations);
  const error = object(run.error);
  const distribution = object(current.modelDistribution);
  const promptPlan = normalizePromptPlan(run.promptPlan ?? state.promptPlan);
  const promptProof = normalizePromptProof(object(run.prompt));
  const optimizationTarget = text(run.optimizationTarget, text(state.optimizationTarget,
    promptPlan || promptProof ? "single_prompt" : run.mode === "analyze" ? "current_workflow" : "measured_workflow"));
  const raw: ObjectValue = { ...run, currentRoute: { ...current, modelDistribution: Object.fromEntries(
    Object.entries(distribution).map(([alias, count], index) => [safeAlias(alias) === "Imported model route" ? `Imported model route ${index + 1}` : alias, count])
  ) } };
  delete raw.proof;
  const qualityPassed = typeof verification.passed === "boolean" ? verification.passed : null;
  const modelCalls = number(cost.modelCalls);
  return {
    runId: text(run.runId), status: text(state.status, text(run.status)), phase: text(state.phase),
    mode: run.mode === "analyze" ? "analyze" : "measure",
    optimizationTarget: optimizationTarget === "single_prompt" || optimizationTarget === "current_workflow" ? optimizationTarget : "measured_workflow",
    sample: strings(run.badges).includes("Measured sample run"),
    inputSource: text(run.inputSource), manifestHash: text(run.inputManifestHash),
    manifest: array(run.inputManifest).map(uploadRecord), completeness: text(run.telemetryCompleteness, "unknown"),
    assumptions: strings(run.dataAssumptions ?? current.assumptions),
    current: {
      requests: number(current.representativeRequests), accepted: number(current.acceptedOutcomes),
      calls: number(current.observedModelCalls), callsPerAccepted: number(current.callsPerAcceptedOutcome),
      modelDistribution: Object.entries(distribution).map(([alias, calls]) => ({ alias: safeAlias(alias), calls: number(calls) ?? 0 })),
      inputTokens: number(current.inputTokens), outputTokens: number(current.outputTokens),
      cachedTokens: number(current.cachedInputTokens), reasoningTokens: number(current.reasoningTokens),
      costUsd: number(current.modelSpendUsd), costPerAcceptedUsd: number(current.costPerAcceptedOutcomeUsd),
      retries: number(current.retries), failures: number(current.failures), corrections: number(current.humanCorrections),
      latencyMs: number(current.latencyMs), latencySamples: array(current.latencyMs).filter((item): item is number => typeof item === "number")
    },
    operations: operations.map((entry) => {
      const operation = object(entry);
      return {
        id: text(operation.operationId), label: text(operation.label), currentRoute: safeAlias(text(operation.currentRoute)),
        route: safeAlias(text(operation.route)), reason: text(operation.reason), status: text(operation.status),
        evidenceStatus: text(operation.evidenceStatus), qualityChecks: strings(operation.qualityGateIds),
        dataDecision: text(operation.dataDecision) || text(candidate.dataDecision)
      };
    }),
    levers: array(state.levers).map((entry) => {
      const lever = object(entry);
      return { id: text(lever.id), name: text(lever.label), status: text(lever.status).replace(/_/g, " "),
        action: text(lever.detail), evidence: text(lever.evidence, text(lever.detail)) };
    }),
    safeguards, qualityGates: gates(run.qualityGates),
    maxSpendUsd: number(candidate.maximumModelSpendUsd) ?? number(requirements.maxModelSpendUsd),
    maxOutputTokens: number(contract.maxOutputTokens) ?? number(requirements.maxOutputTokens),
    maxAdvancedCalls: number(requirements.maxAdvancedCalls),
    perCallLimitUsd: number(candidate.maximumReservationUsd),
    outputContract: outputContractLabel(contract.outputContract ?? requirements.outputContract),
    dataDecision: text(candidate.dataDecision) || text(requirements.dataHandling),
    priceTableVersion: text(run.priceTableVersion), authorized: ["authorized", "running", "completed", "failed"].includes(text(state.status)),
    canAuthorize: safeguards.length > 0 && safeguards.every((check) => check.passed),
    qualityPassed, outcome: text(verification.headline) || text(verification.summary),
    processed: number(verification.processed), total: number(verification.total), exceptions: strings(verification.exceptions),
    outcomes: array(run.outcomes).map((entry) => {
      const outcome = object(entry); const output = object(outcome.output);
      return { requestId: text(outcome.requestId), decision: text(output.decision, "No decision produced"),
        citations: strings(output.citations), diagnosis: text(output.diagnosis), passed: outcome.passed === true };
    }),
    modelCalls,
    usage: normalizedUsage(run.modelUsage),
    modelSpendUsd: number(cost.modelSpendUsd),
    projection: Object.keys(projection).length ? { costUsd: number(projection.valueUsd), volume: number(projection.volume) ?? 0,
      period: text(projection.period), basis: text(projection.assumption, "Observed current cost per accepted request is assumed constant.") } : undefined,
    comparison: Object.keys(baseline).length ? {
      status: text(baseline.status), label: text(baseline.label), eligible: baseline.eligible === true, matched: baseline.sameContract === true,
      governedPassed: qualityPassed === true, baselinePassed: baseline.qualityPassed === true,
      governedCostUsd: number(baseline.governedModelSpendUsd), baselineCostUsd: number(baseline.baselineModelSpendUsd),
      savingUsd: number(baseline.verifiedSavingUsd), savingPercent: number(baseline.verifiedSavingPercent),
      governedCalls: modelCalls, baselineCalls: Array.isArray(baseline.modelUsage) ? baseline.modelUsage.length : undefined,
      reason: text(object(baseline.error).message) || text(baseline.evidence),
      usage: normalizedUsage(baseline.modelUsage)
    } : undefined,
    promptPlan,
    promptProof,
    error: text(error.message) || undefined, raw
  };
}

export interface OptimizationEvent {
  type: string; sequence: number; at: string; phase?: string; operationId?: string;
  route?: string; label?: string; baseline?: boolean; passed?: boolean; decision?: string;
  message?: string; deploymentAlias?: string; [key: string]: unknown;
}

export const optimizationApi = {
  async samples(): Promise<OptimizationSample[]> {
    const body = await request("/api/optimization/samples");
    return array(body.samples).map((entry) => {
      const sample = object(entry);
      return {
        ...exampleDefaults(sample),
        id: text(sample.id), title: text(sample.title), description: exampleText(sample.description),
        requestCount: exampleNumber(sample.requestCount), analysisNotice: exampleText(sample.analysisNotice)
      };
    });
  },
  async promptExamples(): Promise<PromptExample[]> {
    const body = await request("/api/optimization/prompt-examples");
    return array(body.examples).map((entry) => {
      const example = object(entry);
      return {
        ...exampleDefaults(example),
        id: text(example.id),
        title: text(example.title),
        description: text(example.description),
        badge: text(example.badge),
        promptCharacters: number(example.promptCharacters),
        contextArtifacts: number(example.contextArtifacts),
        prompt: exampleText(example.prompt),
        systemInstructions: exampleText(example.systemInstructions),
        conversationHistory: exampleText(example.conversationHistory),
        expectedResult: exampleText(example.expectedResult),
        currentModel: exampleChoice(example.currentModel, ["recommend", "efficient", "advanced", "application"]),
        outputFormat: exampleChoice(example.outputFormat, ["text", "markdown", "json", "table", "code_patch", "custom"]),
        contextFilenames: strings(example.contextFilenames)
      };
    });
  },
  async applications(): Promise<ConnectedApplication[]> {
    const body = await request("/api/optimization/applications");
    return array(body.applications).map((entry) => {
      const app = object(entry);
      return { application_id: text(app.id), name: text(app.name), scope: text(app.scopeSummary),
        permitted_actions: strings(app.scopes), available_references: strings(app.references),
        workflow_id: "workflow_optimization", adapter: "registered", reference_label: "Workflow or trace",
        reference_example: "", connection_kind: app.sample === true ? "local_stub" : "live" };
    });
  },
  async upload(role: string, files: File[]): Promise<UploadRecord[]> {
    const form = new FormData();
    form.append("role", role); files.forEach((file) => form.append("files", file));
    const body = await request("/api/optimization/uploads", { method: "POST", body: form });
    return array(body.files).map(uploadRecord);
  },
  async uploadContext(files: File[]): Promise<UploadRecord[]> {
    const form = new FormData();
    files.forEach((file) => form.append("files", file));
    const body = await request("/api/optimization/context", { method: "POST", body: form });
    return array(body.files).map(uploadRecord);
  },
  async create(draft: OptimizationDraft): Promise<OptimizationRecord> {
    let requests: unknown[] = representativeRequests(draft.requests);
    try {
      const parsed: unknown = JSON.parse(draft.requests);
      if (Array.isArray(parsed)) requests = parsed;
    } catch { /* Plain text remains plain text; the server validates acceptance evidence. */ }
    const target = draft.optimizationTarget;
    const isPrompt = target === "single_prompt";
    const isUpload = ["upload", "telemetry_upload", "workflow_upload"].includes(draft.source);
    const isConnected = ["connected", "connected_application"].includes(draft.source);
    const recurringVolume = draft.volume ? { recurringVolume: { value: Number(draft.volume), period: draft.period } } : {};
    const representativeInputIds = draft.testInputs.map((file) => file.upload_id);
    const body = await post("/api/runs", {
      workflow: "workflow_optimization", optimizationTarget: target, mode: draft.mode, inputSource: draft.source,
      inputs: {
        desiredOutcome: draft.desiredOutcome,
        ...(isPrompt ? {
          userPrompt: draft.userPrompt,
          systemInstructions: draft.systemInstructions || undefined,
          conversationHistory: draft.conversationHistory || undefined,
          contextFileIds: draft.contextFiles.map((file) => file.upload_id),
          currentModel: draft.currentModel,
          outputFormat: draft.outputFormat,
          expectedResult: draft.expectedResult || undefined,
          promptExampleId: draft.promptExampleId || undefined
        } : { workflowDescription: draft.description }),
        ...(isUpload ? {
          telemetryExportIds: draft.telemetry.map((file) => file.upload_id),
          testInputIds: representativeInputIds,
          representativeInputIds,
          representativeRequests: requests
        } : {}),
        ...(["sample", "workflow_example"].includes(draft.source) ? { sampleId: draft.fixture } : {}),
        ...(isConnected ? {
          applicationId: draft.application,
          filters: { reference: draft.reference, timeRange: draft.timeRange, ...(draft.timeRange === "custom" ? {
            start: new Date(draft.start).toISOString(), end: new Date(draft.end).toISOString()
          } : {}) }, owner: draft.owner
        } : {}),
        ...recurringVolume
      },
      requirements: {
        qualityRequirements: draft.quality, optimizationGoal: draft.goal,
        maxModelSpendUsd: Number(draft.maxSpend), allowAdvancedEscalation: draft.allowAdvanced,
        ...(draft.maxInputTokens.trim() ? { maxInputTokens: Number(draft.maxInputTokens) } : {}),
        ...(draft.maxOutputTokens.trim() ? { maxOutputTokens: Number(draft.maxOutputTokens) } : {}),
        ...(draft.maxAdvancedCalls.trim() ? { maxAdvancedCalls: Number(draft.maxAdvancedCalls) } : {}),
        ...(draft.quality.includes("latency_target") ? { latencyTargetMs: Number(draft.latency) } : {})
      }
    });
    return normalizeRecord(body);
  },
  async analyze(id: string) { return normalizeRecord(await post(`/api/runs/${encodeURIComponent(id)}/analyze`)); },
  async optimize(id: string) { return normalizeRecord(await post(`/api/runs/${encodeURIComponent(id)}/optimize`, { approvePlan: true })); },
  async refreshSafeguards(id: string) { return normalizeRecord(await post(`/api/runs/${encodeURIComponent(id)}/refresh-safeguards`, {})); },
  async authorize(id: string, humanApprovalGranted: boolean) {
    return normalizeRecord(await post(`/api/runs/${encodeURIComponent(id)}/authorize`, { authorizeModelCost: true, humanApprovalGranted }));
  },
  async execute(id: string) { return normalizeRecord(await post(`/api/runs/${encodeURIComponent(id)}/execute`)); },
  async state(id: string) { return normalizeRecord(await request(`/api/runs/${encodeURIComponent(id)}`)); },
  async baseline(id: string) {
    return normalizeRecord(await post(`/api/runs/${encodeURIComponent(id)}/baseline`, { acknowledgeModelCost: true, baselineProfile: "all_ai_v1" }));
  },
  async importTemplate() { return request("/api/optimization/import-template"); }
};

export function optimizationStream(id: string, onEvent: (event: OptimizationEvent) => void,
  onError: () => void, onOpen: () => void, lastSequence = 0): EventSource {
  const source = new EventSource(`${API_BASE}/api/runs/${encodeURIComponent(id)}/events?last_event_id=${lastSequence}`);
  const eventTypes = ["phase.started", "phase.completed", "safeguards.refreshed", "data.policy", "model.authorized", "budget.reserved",
    "prompt.analyzed", "context.decided", "model.usage", "budget.reconciled", "operation.started", "operation.completed", "quality.result",
    "escalation.decision", "execution.failed", "run.completed", "run.failed", "baseline.started", "baseline.completed"];
  for (const type of eventTypes) source.addEventListener(type, (event) => {
    try { onEvent({ ...JSON.parse((event as MessageEvent<string>).data), type } as OptimizationEvent); }
    catch { /* An invalid transport frame is not evidence. */ }
  });
  source.onerror = onError;
  source.onopen = onOpen;
  return source;
}
