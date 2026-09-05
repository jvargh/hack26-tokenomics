import type { UploadRecord } from "../api/types";

export interface PromptComponent {
  id: string;
  label: string;
  estimatedTokens?: number;
  candidateTreatment: string;
  reason: string;
}

export interface PromptContextDecision {
  id: string;
  label: string;
  decision: string;
  reason: string;
  estimatedTokens?: number;
  sourceId: string;
}

export interface PromptChange {
  id: string;
  change: string;
  reason: string;
  evidenceState: string;
}

export interface PromptPlan {
  current: {
    estimatedInputTokens?: number;
    currentModel: string;
    components: PromptComponent[];
  };
  candidate: {
    governedPrompt: string;
    governedSystemPrompt: string;
    eligibleContextIds: string[];
    minimizedContextIds: string[];
    blockedContextIds: string[];
    estimatedInputTokens?: number;
    estimatedReductionTokens?: number;
    estimatedReductionPercent?: number;
    cacheEligibility: "eligible" | "not_eligible" | "unknown";
    cacheReason: string;
    recommendedModelAlias: "tokenos-efficient" | "tokenos-advanced" | "local" | string;
    routeReason: string;
    outputContract: unknown;
  };
  contextDecisions: PromptContextDecision[];
  changes: PromptChange[];
  improvements: string[];
  evidenceStatus: "estimated" | string;
}

export interface OptimizationOperation {
  id: string;
  label: string;
  currentRoute: string;
  route: string;
  reason: string;
  evidenceStatus: string;
  status: string;
  qualityChecks: string[];
  dataDecision?: string;
}

export interface OptimizationGate {
  id: string;
  name: string;
  passed: boolean | null;
  detail: string;
  action?: string;
}

export interface OptimizationLever {
  id: string;
  name: string;
  status: string;
  action: string;
  evidence: string;
}

export interface OptimizationUsage {
  id: string;
  purpose: string;
  whyAI: string;
  minimalEvidence: string;
  alias: string;
  inputTokens?: number;
  outputTokens?: number;
  cachedInputTokens?: number;
  reasoningTokens?: number;
  totalTokens?: number;
  costUsd?: number;
  durationMs?: number;
  requestId?: string;
  qualityPassed: boolean | null;
  qualityDetail: string;
  escalation: string;
  optionalPresentation?: boolean;
}

export interface OptimizationComparison {
  status: string;
  label?: string;
  eligible: boolean;
  matched: boolean;
  governedPassed: boolean;
  baselinePassed: boolean;
  governedCostUsd?: number;
  baselineCostUsd?: number;
  savingUsd?: number;
  savingPercent?: number;
  governedCalls?: number;
  baselineCalls?: number;
  reason?: string;
  usage?: OptimizationUsage[];
}

export interface PromptProof {
  originalPromptHash: string;
  governedPromptHash: string;
  promptComponents: PromptComponent[];
  contextDecisions: PromptContextDecision[];
  estimatedBefore?: { inputTokens?: number };
  estimatedAfter?: { inputTokens?: number };
  measuredUsage: OptimizationUsage | null;
  measuredCost: { costUsd?: number; modelSpendUsd?: number; [key: string]: unknown } | null;
  measuredInputTokenReduction?: number | null;
  outputFormat: string;
  governedPrompt: string;
}

export interface OptimizationRecord {
  runId: string;
  status: string;
  phase: string;
  mode: "analyze" | "measure";
  optimizationTarget: "current_workflow" | "single_prompt" | "measured_workflow";
  sample: boolean;
  inputSource: string;
  manifestHash: string;
  manifest: UploadRecord[];
  completeness: string;
  assumptions: string[];
  current: {
    requests?: number;
    accepted?: number;
    calls?: number;
    callsPerAccepted?: number;
    modelDistribution: Array<{ alias: string; calls: number }>;
    inputTokens?: number;
    outputTokens?: number;
    cachedTokens?: number;
    reasoningTokens?: number;
    costUsd?: number;
    costPerAcceptedUsd?: number;
    retries?: number;
    failures?: number;
    corrections?: number;
    latencyMs?: number;
    latencySamples?: number[];
  };
  operations: OptimizationOperation[];
  levers: OptimizationLever[];
  safeguards: OptimizationGate[];
  qualityGates: OptimizationGate[];
  maxSpendUsd?: number;
  maxOutputTokens?: number;
  maxAdvancedCalls?: number;
  perCallLimitUsd?: number;
  outputContract: string;
  dataDecision: string;
  priceTableVersion: string;
  authorized: boolean;
  canAuthorize: boolean;
  qualityPassed: boolean | null;
  outcome: string;
  processed?: number;
  total?: number;
  exceptions: string[];
  outcomes: Array<{ requestId: string; decision: string; citations: string[]; diagnosis: string; passed: boolean }>;
  usage: OptimizationUsage[];
  modelSpendUsd?: number;
  modelCalls?: number;
  projection?: { costUsd?: number; volume: number; period: string; basis: string };
  comparison?: OptimizationComparison;
  promptPlan: PromptPlan | null;
  promptProof: PromptProof | null;
  error?: string;
  raw: unknown;
}
