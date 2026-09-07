import { useEffect, useState } from "react";
import { optimizationApi } from "./client";
import type { ConnectedApplication, UploadRecord } from "../api/types";
import { SectionHead } from "../components/shared/PhaseIntro";
import { formatBytes } from "../components/shared/format";

export const QUALITY_OPTIONS = [
  ["same_answer_quality", "Same decision or answer quality"],
  ["grounded_citations", "Required citations or grounded evidence"],
  ["structured_output", "Structured output remains valid"],
  ["required_tests", "Required test suite passes"],
  ["latency_target", "Response meets a latency target"],
  ["human_approval", "Human approval remains required for selected outcomes"]
] as const;

export const GOAL_OPTIONS = [
  ["cost_per_accepted_outcome", "Lower cost per accepted outcome"],
  ["reduce_model_calls", "Reduce unnecessary model calls"],
  ["reduce_context", "Reduce repeated context and token waste"],
  ["reduce_latency", "Reduce latency while preserving quality"],
  ["compare_models", "Compare efficient and advanced model routes"]
] as const;

const MODE_CARDS = [
  ["analyze_current_workflow", "current_workflow", "analyze", "Analyze current workflow", "Inspect current usage and identify opportunities. Recommendations are not measured improvements."],
  ["optimize_single_prompt", "single_prompt", "measure", "Optimize a prompt before you run it", "Improve one prompt, its context, and its model route before any model spend occurs."],
  ["measure_optimized_workflow", "measured_workflow", "measure", "Measure an optimized workflow", "Replay representative work and measure the governed route before comparing it."]
] as const;

const PROMPT_SOURCES = [
  ["paste_prompt", "Paste a prompt", "Paste the user prompt and optional system instructions directly."],
  ["attach_context", "Add context or files", "Add the documents, code, history, or policies the prompt currently sends to the model."],
  ["prompt_example", "Use a prompt example", "Load a reproducible prompt with repeated context and a measurable optimized route."]
] as const;

const CURRENT_WORKFLOW_SOURCES = [
  ["telemetry_upload", "Upload workflow data", "Upload an AI run export, request logs, or representative prompts and results."],
  ["connected_application", "Connect an AI application", "Select a registered application so TokenOS can read approved run telemetry."],
  ["workflow_example", "Use a measured example", "Explore a reproducible workflow with clearly labelled sample economics."]
] as const;

const MEASURED_WORKFLOW_SOURCES = [
  ["workflow_upload", "Upload workflow data", "Upload representative inputs, optional telemetry, and required supporting artifacts."],
  ["connected_application", "Connect an AI application", "Select a registered application and approved test scope."],
  ["workflow_example", "Use a measured example", "Run a bundled fixture through the real local engine."]
] as const;

const CURRENT_MODEL_OPTIONS = [
  ["recommend", "Let TokenOS recommend"],
  ["efficient", "Efficient model"],
  ["advanced", "Advanced model"],
  ["application", "Existing application model"]
] as const;

const OUTPUT_FORMAT_OPTIONS = [
  ["text", "Free text"],
  ["markdown", "Markdown"],
  ["json", "JSON"],
  ["table", "Table"],
  ["code_patch", "Code patch"],
  ["custom", "Application-defined schema"]
] as const;

type OptimizationTarget = "current_workflow" | "single_prompt" | "measured_workflow";
export type OptimizationSource = "paste_prompt" | "attach_context" | "prompt_example" |
  "upload" | "connected" | "sample" | "telemetry_upload" | "workflow_upload" | "connected_application" | "workflow_example";

export interface OptimizationDraft {
  optimizationTarget: OptimizationTarget;
  mode: "analyze" | "measure";
  source: OptimizationSource;
  description: string;
  desiredOutcome: string;
  quality: string[];
  goal: string;
  fixture: string;
  telemetry: UploadRecord[];
  testInputs: UploadRecord[];
  requests: string;
  application: string;
  reference: string;
  search: string;
  timeRange: string;
  start: string;
  end: string;
  owner: string;
  volume: string;
  period: "day" | "week" | "month" | "year";
  maxSpend: string;
  maxInputTokens: string;
  maxOutputTokens: string;
  maxAdvancedCalls: string;
  latency: string;
  allowAdvanced: boolean;
  userPrompt: string;
  systemInstructions: string;
  conversationHistory: string;
  contextFiles: UploadRecord[];
  currentModel: "recommend" | "efficient" | "advanced" | "application";
  outputFormat: "text" | "markdown" | "json" | "table" | "code_patch" | "custom";
  expectedResult: string;
  promptExampleId: string;
}

export interface ExampleDefaults {
  desiredOutcome: string;
  recurringVolume: { value: number; period: OptimizationDraft["period"] };
  requirements: {
    qualityRequirements: string[];
    optimizationGoal: string;
    maxModelSpendUsd: number;
    maxInputTokens: number;
    maxOutputTokens: number;
    latencyTargetMs: number;
    allowAdvancedEscalation: boolean;
    maxAdvancedCalls: number;
  };
}

export interface OptimizationSample extends ExampleDefaults {
  id: string;
  title: string;
  description: string;
  requestCount: number;
  analysisNotice: string;
}

export interface PromptExample extends ExampleDefaults {
  id: string;
  title: string;
  description: string;
  badge?: string;
  promptCharacters?: number;
  contextArtifacts?: number;
  prompt: string;
  systemInstructions: string;
  conversationHistory: string;
  expectedResult: string;
  currentModel: OptimizationDraft["currentModel"];
  outputFormat: OptimizationDraft["outputFormat"];
  contextFilenames: string[];
}

export const EMPTY_DRAFT: OptimizationDraft = {
  optimizationTarget: "single_prompt", mode: "measure", source: "paste_prompt", description: "", desiredOutcome: "",
  quality: [], goal: "", fixture: "", telemetry: [], testInputs: [], requests: "", application: "",
  reference: "", search: "", timeRange: "7d", start: "", end: "", owner: "", volume: "", period: "month",
  maxSpend: "0.05", maxInputTokens: "", maxOutputTokens: "", maxAdvancedCalls: "", latency: "30000",
  allowAdvanced: true, userPrompt: "", systemInstructions: "", conversationHistory: "", contextFiles: [],
  currentModel: "recommend", outputFormat: "text", expectedResult: "", promptExampleId: ""
};

export function representativeRequests(value: string): string[] {
  if (!value.trim()) return [];
  try {
    const parsed: unknown = JSON.parse(value);
    if (Array.isArray(parsed)) return parsed.map((item) => typeof item === "string" ? item : JSON.stringify(item));
  } catch { /* Text requests are separated by blank lines. */ }
  return value.split(/\n\s*\n/).map((item) => item.trim()).filter(Boolean);
}

function finiteNumber(value: string, min: number, max: number, integer = false): boolean {
  if (!value.trim()) return true;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= min && parsed <= max && (!integer || Number.isInteger(parsed));
}

function detailNumber(record: UploadRecord, key: string): number | undefined {
  const value = record.detail[key];
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function sourceFamily(source: OptimizationSource): "prompt" | "prompt_sample" | "upload" | "connected" | "sample" {
  if (source === "paste_prompt" || source === "attach_context") return "prompt";
  if (source === "prompt_example") return "prompt_sample";
  if (source === "connected" || source === "connected_application") return "connected";
  if (source === "sample" || source === "workflow_example") return "sample";
  return "upload";
}

function exampleDraftDefaults(example: ExampleDefaults) {
  return {
    desiredOutcome: example.desiredOutcome,
    quality: [...example.requirements.qualityRequirements],
    goal: example.requirements.optimizationGoal,
    volume: String(example.recurringVolume.value),
    period: example.recurringVolume.period,
    maxSpend: String(example.requirements.maxModelSpendUsd),
    maxInputTokens: String(example.requirements.maxInputTokens),
    maxOutputTokens: String(example.requirements.maxOutputTokens),
    maxAdvancedCalls: String(example.requirements.maxAdvancedCalls),
    latency: String(example.requirements.latencyTargetMs),
    allowAdvanced: example.requirements.allowAdvancedEscalation
  };
}

function workflowExampleDraft(draft: OptimizationDraft, sample: OptimizationSample): OptimizationDraft {
  return {
    ...EMPTY_DRAFT, ...exampleDraftDefaults(sample),
    optimizationTarget: draft.optimizationTarget, mode: draft.mode,
    source: "workflow_example", fixture: sample.id, description: sample.description
  };
}

function promptExampleDraft(example: PromptExample): OptimizationDraft {
  return {
    ...EMPTY_DRAFT, ...exampleDraftDefaults(example),
    source: "prompt_example", promptExampleId: example.id,
    userPrompt: example.prompt, systemInstructions: example.systemInstructions,
    conversationHistory: example.conversationHistory, expectedResult: example.expectedResult,
    currentModel: example.currentModel, outputFormat: example.outputFormat
  };
}

export function OptimizationDescribe({
  draft, onChange, samples, promptExamples, applications, ready, busy, onSubmit
}: {
  draft: OptimizationDraft;
  onChange: (draft: OptimizationDraft) => void;
  samples: OptimizationSample[];
  promptExamples: PromptExample[];
  applications: ConnectedApplication[];
  ready: boolean;
  busy: boolean;
  onSubmit: () => void;
}) {
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const update = <K extends keyof OptimizationDraft>(key: K, value: OptimizationDraft[K]) =>
    onChange({ ...draft, [key]: value });
  const selectedApp = applications.find((app) => app.application_id === draft.application);
  const selectedExample = draft.source === "prompt_example"
    ? promptExamples.find((example) => example.id === draft.promptExampleId) : undefined;
  const selectedSample = samples.find((sample) => sample.id === draft.fixture);
  const requests = representativeRequests(draft.requests);
  const validRequests = requests.length >= 3 && requests.length <= 20;
  const isPrompt = draft.optimizationTarget === "single_prompt";
  const currentWorkflow = draft.optimizationTarget === "current_workflow";
  const promptInputReady = Boolean(draft.userPrompt.trim()) && draft.contextFiles.every((file) => file.status === "ready");
  const workflowSource = sourceFamily(draft.source);
  const workflowInputReady = workflowSource === "sample" ? Boolean(draft.fixture)
    : workflowSource === "connected" ? Boolean(selectedApp?.scope && selectedApp.permitted_actions.includes(draft.mode === "analyze" ? "telemetry" : "test_inputs"))
      && (draft.timeRange !== "custom" || Boolean(draft.start && draft.end && draft.start < draft.end))
    : draft.mode === "analyze" ? draft.telemetry.length > 0
    : (draft.testInputs.length > 0 || validRequests) && (!draft.requests.trim() || validRequests);
  const inputReady = isPrompt ? promptInputReady : Boolean(draft.description.trim()) && workflowInputReady;
  const budgetReady = draft.maxSpend.trim() !== "" && Number.isFinite(Number(draft.maxSpend)) && Number(draft.maxSpend) >= 0 && Number(draft.maxSpend) <= 100;
  const volumeReady = draft.volume === "" || Number.isInteger(Number(draft.volume)) && Number(draft.volume) > 0 && Number(draft.volume) <= 1_000_000_000;
  const limitsReady = finiteNumber(draft.maxInputTokens, 1, 200_000, true) && finiteNumber(draft.maxOutputTokens, 1, 200_000, true)
    && finiteNumber(draft.maxAdvancedCalls, 0, 1000, true);
  const requirementsReady = Boolean(draft.desiredOutcome.trim() && draft.quality.length && draft.goal)
    && budgetReady && volumeReady && limitsReady
    && (!draft.quality.includes("latency_target") || Number(draft.latency) > 0 && Number(draft.latency) <= 3_600_000)
    && (!isPrompt || !draft.quality.includes("same_answer_quality") || Boolean(draft.expectedResult.trim()));

  // Catalogs may arrive after the user selects the sample source. Initialize once,
  // not after later edits to the selected example.
  useEffect(() => {
    if (workflowSource === "sample" && !draft.fixture && samples.length) {
      onChange(workflowExampleDraft(draft, samples[0]));
    } else if (workflowSource === "prompt_sample" && !draft.promptExampleId && promptExamples.length) {
      onChange(promptExampleDraft(promptExamples[0]));
    }
  }, [draft, workflowSource, samples, promptExamples, onChange]);

  function chooseTarget(target: OptimizationTarget) {
    const selected = MODE_CARDS.find(([, cardTarget]) => cardTarget === target);
    if (!selected) return;
    const nextSource: OptimizationSource = target === "single_prompt" ? "paste_prompt"
      : workflowSource === "sample" || target === "measured_workflow" ? "workflow_example" : "telemetry_upload";
    const next: OptimizationDraft = { ...EMPTY_DRAFT, optimizationTarget: target, mode: selected[2], source: nextSource };
    const sample = selectedSample ?? samples[0];
    setUploadError("");
    onChange(nextSource === "workflow_example" && sample ? workflowExampleDraft(next, sample) : next);
  }

  function chooseSource(source: OptimizationSource) {
    setUploadError("");
    const sample = selectedSample ?? samples[0];
    if (sourceFamily(source) === "sample" && sample) {
      onChange(workflowExampleDraft(draft, sample));
      return;
    }
    const example = selectedExample ?? promptExamples[0];
    if (source === "prompt_example" && example) {
      onChange(promptExampleDraft(example));
      return;
    }
    onChange({ ...draft, source });
  }

  function chooseExample(example: PromptExample) {
    setUploadError("");
    onChange(promptExampleDraft(example));
  }

  async function upload(role: "telemetry" | "testInputs", files: FileList | null) {
    if (!files?.length) return;
    const selected = Array.from(files);
    const permitted = role === "telemetry" ? /\.(json|jsonl|csv|zip)$/i : /\.(txt|json|jsonl|csv|md|zip)$/i;
    if (selected.some((file) => !permitted.test(file.name) || file.size > 10 * 1024 * 1024 || !file.size)) {
      setUploadError("Choose a supported, nonempty file up to 10 MB. Larger workloads should use a representative input package.");
      return;
    }
    setUploadError("");
    setUploading(true);
    try {
      const records = await optimizationApi.upload(role === "telemetry" ? "telemetry" : "test_inputs", selected);
      onChange({ ...draft, [role]: [...draft[role], ...records] });
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : "Upload unavailable.");
    } finally { setUploading(false); }
  }

  async function uploadContext(files: FileList | null) {
    if (!files?.length) return;
    const selected = Array.from(files);
    if (selected.some((file) => !/\.(txt|md|json|jsonl|csv|zip)$/i.test(file.name) || file.size > 10 * 1024 * 1024 || !file.size)) {
      setUploadError("Choose supported context files up to 10 MB: TXT, Markdown, JSON, JSONL, CSV, or ZIP.");
      return;
    }
    setUploadError("");
    setUploading(true);
    try {
      const records = await optimizationApi.uploadContext(selected);
      onChange({ ...draft, contextFiles: [...draft.contextFiles, ...records], source: draft.source === "prompt_example" ? draft.source : "attach_context" });
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : "Context upload unavailable.");
    } finally { setUploading(false); }
  }

  function remove(role: "telemetry" | "testInputs" | "contextFiles", record: UploadRecord) {
    onChange({ ...draft, [role]: draft[role].filter((item) => item.upload_id !== record.upload_id) });
  }

  async function downloadTemplate() {
    try {
      const template = await optimizationApi.importTemplate();
      const url = URL.createObjectURL(new Blob([JSON.stringify(template, null, 2)], { type: "application/json" }));
      const link = document.createElement("a");
      link.href = url; link.download = "tokenos-normalized-import-template.json"; link.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : "Import template unavailable.");
    }
  }

  // Analysis reads recorded telemetry and can never invoke a model, so it has no
  // spend to authorize. Prompt and measure runs can, so this button is the single
  // explicit authorization: the journey runs end to end from here, and the exact
  // ceiling being permitted is stated next to it.
  const spends = !currentWorkflow || isPrompt;
  const buttonCopy = !spends ? "Analyze workflow and build an optimization plan"
    : isPrompt ? "Authorize and run the governed prompt"
    : "Authorize and run the governed workflow";
  const workflowSources = currentWorkflow ? CURRENT_WORKFLOW_SOURCES : MEASURED_WORKFLOW_SOURCES;

  return (
    <fieldset disabled={busy || uploading} className="optimization-form">
      <legend className="sr-only">Existing AI workflow requirements</legend>
      <section className="panel">
        <SectionHead title="Optimize AI Prompt or Workflow"
          supporting="Start with a prompt or workflow. TokenOS reduces AI waste while preserving required quality and outcomes." />
        <fieldset className="optimization-modes optimization-modes-three" role="radiogroup" aria-labelledby="optimization-mode-legend">
          <legend id="optimization-mode-legend" className="field-label">What do you want to improve?</legend>
          {MODE_CARDS.map(([id, target, , title, copy]) => (
            <label className={`optimization-mode ${draft.optimizationTarget === target ? "is-selected" : ""}`} key={id}>
              <input type="radio" name="optimization-mode" value={id} checked={draft.optimizationTarget === target}
                onChange={() => chooseTarget(target)} />
              <span><strong>{title}</strong><small>{copy}</small></span>
            </label>
          ))}
        </fieldset>
      </section>

      {isPrompt ? <section className="panel">
        <SectionHead title="Provide the prompt"
          supporting="Paste the request you plan to send. TokenOS will identify unnecessary context, reusable content, eligible model routes, and quality requirements before any model spend occurs." />
        <div className="source-choices" role="group" aria-label="Prompt input source">
          {PROMPT_SOURCES.map(([source, title, copy]) => (
            <button key={source} type="button" aria-pressed={draft.source === source}
              aria-label={title}
              className={`source-choice ${draft.source === source ? "is-selected" : ""}`}
              onClick={() => chooseSource(source)}>
              <span className="template-name">{title}</span><span className="template-support">{copy}</span>
            </button>
          ))}
        </div>

        {draft.source === "prompt_example" && <fieldset className="optimization-samples">
          <legend className="field-label">Select a prompt example</legend>
          {promptExamples.length === 0 && <p className="muted">Prompt examples are unavailable. Paste a prompt or add context instead.</p>}
          {promptExamples.map((example) => (
            <label className={`optimization-sample ${draft.promptExampleId === example.id ? "is-selected" : ""}`} key={example.id}>
              <input type="radio" name="prompt-example" checked={draft.promptExampleId === example.id}
                onChange={() => chooseExample(example)} />
              <span><strong>{example.title}</strong><small>{example.description}</small>
                {(example.badge || example.promptCharacters !== undefined || example.contextArtifacts !== undefined) && <small>
                  {[example.badge, example.promptCharacters !== undefined ? `${example.promptCharacters.toLocaleString()} prompt characters` : "",
                    example.contextArtifacts !== undefined ? `${example.contextArtifacts.toLocaleString()} context artifacts` : ""].filter(Boolean).join(" · ")}
                </small>}
              </span>
            </label>
          ))}
        </fieldset>}

        <label className="field-label" htmlFor="optimization-user-prompt">User prompt (required)</label>
        <textarea id="optimization-user-prompt" value={draft.userPrompt} maxLength={20000}
          placeholder="Analyze everything below, review every policy and prior interaction, explain all possible options in detail, and produce the best possible response."
          onChange={(event) => update("userPrompt", event.target.value)} />

        <div className="advanced-grid">
          <div><label className="field-label" htmlFor="optimization-current-model">Current model (required)</label>
            <select id="optimization-current-model" value={draft.currentModel} onChange={(event) => update("currentModel", event.target.value as OptimizationDraft["currentModel"])}>
              {CURRENT_MODEL_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
            <p className="muted">TokenOS uses this only as the starting route. It may recommend an efficient model if the required quality can still be verified.</p>
          </div>
          <div><label className="field-label" htmlFor="optimization-output-format">Output format (required)</label>
            <select id="optimization-output-format" value={draft.outputFormat} onChange={(event) => update("outputFormat", event.target.value as OptimizationDraft["outputFormat"])}>
              {OUTPUT_FORMAT_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
            <p className="muted">A specific format can reduce unnecessary output tokens and makes verification more reliable.</p>
          </div>
        </div>

        <details><summary>System instructions</summary>
          <label className="field-label" htmlFor="optimization-system-instructions">System instructions</label>
          <textarea id="optimization-system-instructions" value={draft.systemInstructions} maxLength={8000}
            placeholder="Stable operating rules, tone, policy boundaries, or application instructions."
            onChange={(event) => update("systemInstructions", event.target.value)} />
        </details>
        <details><summary>Conversation history</summary>
          <label className="field-label" htmlFor="optimization-conversation-history">Conversation history</label>
          <textarea id="optimization-conversation-history" value={draft.conversationHistory} maxLength={40000}
            placeholder="Paste only the previous turns the current prompt would send."
            onChange={(event) => update("conversationHistory", event.target.value)} />
        </details>

        <div className="input-role">
          <label className="field-label" htmlFor="optimization-context-files">Context artifacts</label>
          <p className="muted" id="context-help">Add only the material the current prompt would send. TokenOS will show what was kept, minimized, reused, or blocked before execution.</p>
          {selectedExample && <div className="notice">
            <strong>Bundled example context</strong>
            <ul>{selectedExample.contextFilenames.map((filename) => <li key={filename}>{filename}</li>)}</ul>
            <p className="muted">Included automatically from the server's fixture. No file upload is needed.</p>
          </div>}
          <input id="optimization-context-files" type="file" multiple accept=".txt,.md,.json,.jsonl,.csv,.zip"
            aria-describedby="context-help" onChange={(event) => { void uploadContext(event.target.files); event.target.value = ""; }} />
          {draft.contextFiles.length > 0 && <div className="optimization-table-wrap">
            <table className="optimization-table"><caption>Context attachment list</caption>
              <thead><tr><th>Name</th><th>Role</th><th>Size</th><th>Hash</th><th>Content type</th><th>Estimated tokens</th><th><span className="sr-only">Actions</span></th></tr></thead>
              <tbody>{draft.contextFiles.map((record) => <tr key={record.upload_id}>
                <td>{record.name}</td><td>{record.role || "context"}</td><td>{formatBytes(record.size_bytes)}</td>
                <td><code className="optimization-hash">{record.sha256}</code></td><td>{record.media_type}</td>
                <td>{detailNumber(record, "estimatedTokens") !== undefined ? `Estimated ${detailNumber(record, "estimatedTokens")?.toLocaleString()}` : "Estimated unavailable"}</td>
                <td><button type="button" className="btn btn-small" aria-label={`Remove ${record.name}`}
                  onClick={() => void remove("contextFiles", record)}>Remove</button></td>
              </tr>)}</tbody>
            </table>
          </div>}
        </div>
      </section> : <section className="panel">
        <SectionHead title="Provide an existing AI workflow"
          supporting={currentWorkflow
            ? "Bring recent usage or representative runs. TokenOS will identify where AI work, context, model calls, and cost may be avoidable."
            : "Give TokenOS repeatable inputs and the quality result to preserve. It will measure a governed route before you choose whether to run a matched comparison."} />
        <div className="source-choices" role="group" aria-label="Workflow input source">
          {workflowSources.map(([source, title, copy]) => (
            <button key={source} type="button" aria-pressed={draft.source === source}
              aria-label={title}
              className={`source-choice ${draft.source === source ? "is-selected" : ""}`}
              onClick={() => chooseSource(source)}>
              <span className="template-name">{title}</span><span className="template-support">{copy}</span>
            </button>
          ))}
        </div>
        <p className="muted optimization-scope-note">A connected application is a TokenOS-registered application and approved data scope. It does not automatically connect to an Azure subscription. Provider credentials never reach the browser.</p>

        <label className="field-label" htmlFor="optimization-description">Current workflow description (required)</label>
        <textarea id="optimization-description" value={draft.description} maxLength={8000}
          placeholder="Our support assistant sends every request, full conversation history, and policy library to an advanced model."
          onChange={(event) => update("description", event.target.value)} />

        {workflowSource === "sample" && <fieldset className="optimization-samples">
          <legend className="field-label">Select a reproducible workflow</legend>
          {samples.length === 0 && <p className="muted">Measured examples are unavailable. Retry the connection or provide your own inputs.</p>}
          {samples.map((sample) => (
            <label className={`optimization-sample ${draft.fixture === sample.id ? "is-selected" : ""}`} key={sample.id}>
              <input type="radio" name="fixture" checked={draft.fixture === sample.id}
                onChange={() => { setUploadError(""); onChange(workflowExampleDraft(draft, sample)); }} />
              <span><strong>{sample.title}</strong><small>{sample.description}</small></span>
            </label>
          ))}
          <p className="muted">{currentWorkflow && selectedSample
            ? selectedSample.analysisNotice : "Fixtures use real local execution."} Every result is labelled <strong>Measured sample run</strong>; no model usage is simulated.</p>
        </fieldset>}

        {workflowSource === "upload" && <>
          {(["telemetry", "testInputs"] as const).map((role) => <div key={role} className="input-role">
            <label className="field-label" htmlFor={`optimization-${role}`}>
              {role === "telemetry" ? "AI workflow export" : "Representative test inputs"}
              {draft.mode === "analyze" && role === "telemetry" ? " (required for analysis)" : ""}
              {draft.mode === "measure" && role === "testInputs" ? " (upload or paste below)" : ""}
            </label>
            <p className="muted">{role === "telemetry"
              ? "TokenOS native or normalized JSON, JSONL, CSV, ZIP. Include request ID, timestamp, tokens, latency and outcome where available; no provider-specific schema required."
              : "Text, JSON, JSONL, CSV, Markdown or ZIP input packages. Use 3 to 20 representative requests."} Maximum 10 MB per file.</p>
            <input id={`optimization-${role}`} type="file" multiple
              accept={role === "telemetry" ? ".json,.jsonl,.csv,.zip" : ".txt,.json,.jsonl,.csv,.md,.zip"}
              onChange={(event) => { void upload(role, event.target.files); event.target.value = ""; }} />
            {draft[role].length > 0 && <div className="optimization-table-wrap">
              <table className="optimization-table"><caption>Input manifest — {role === "telemetry" ? "telemetry" : "representative inputs"}</caption>
                <thead><tr><th>Filename / detected type</th><th>Size</th><th>SHA-256</th><th>Intended role</th><th><span className="sr-only">Actions</span></th></tr></thead>
                <tbody>{draft[role].map((record) => <tr key={record.upload_id}>
                  <td>{record.name}<small>{record.media_type}</small></td><td>{formatBytes(record.size_bytes)}</td>
                  <td><code className="optimization-hash">{record.sha256}</code></td><td>{record.role}</td>
                  <td><button type="button" className="btn btn-small" aria-label={`Remove ${record.name}`}
                    onClick={() => void remove(role, record)}>Remove</button></td>
                </tr>)}</tbody>
              </table>
            </div>}
          </div>)}
          <label className="field-label" htmlFor="optimization-requests">Or paste 3 to 20 representative requests</label>
          <textarea id="optimization-requests" value={draft.requests} maxLength={200000}
            placeholder={"First representative request\n\nSecond representative request\n\nThird representative request"}
            onChange={(event) => update("requests", event.target.value)} aria-describedby="requests-help" />
          <p id="requests-help" className="muted">Separate requests with a blank line, or paste a JSON array. {requests.length} supplied. For measured execution, include independently specified expectedOutput and any context citations for each request. Plain text can be planned but cannot pass Protect without acceptance evidence. The server pins the manifest hash.</p>
          {requests.length > 0 && !validRequests && <p className="error-text">Supply between 3 and 20 requests, or use a representative input file.</p>}
          <details><summary>Normalized telemetry import fields</summary>
            <p className="muted">Use one record per request with requestId, providerRequestId, timestamp, deployment, inputTokens, outputTokens, cachedInputTokens, reasoningTokens, latencyMs, outcomeStatus, retryCount, application and owner where known. Missing values remain unknown, not zero. The server also supports normalized snake_case and native TokenOS exports.</p>
            <button type="button" className="btn btn-small" onClick={() => void downloadTemplate()}>Download normalized import template</button>
          </details>
        </>}

        {workflowSource === "connected" && <div className="advanced-grid">
          <div><label className="field-label" htmlFor="optimization-app">Registered application</label>
            <select id="optimization-app" value={draft.application} onChange={(event) => onChange({ ...draft, application: event.target.value, reference: "" })}>
              <option value="">Select a registered application</option>
              {applications.map((app) => <option key={app.application_id} value={app.application_id}>{app.name}</option>)}
            </select>
          </div>
          <div><label className="field-label" htmlFor="optimization-search">Search workflows or traces</label>
            <input id="optimization-search" type="text" value={draft.search} placeholder="Filter approved references"
              onChange={(event) => update("search", event.target.value)} />
          </div>
          <div><label className="field-label" htmlFor="optimization-reference">Workflow or trace (optional)</label>
            <select id="optimization-reference" value={draft.reference} disabled={!selectedApp}
              onChange={(event) => update("reference", event.target.value)}>
              <option value="">All approved references</option>
              {(selectedApp?.available_references ?? []).filter((item) => item.toLowerCase().includes(draft.search.toLowerCase()))
                .map((item) => <option key={item}>{item}</option>)}
            </select>
          </div>
          <div><label className="field-label" htmlFor="optimization-range">Time range</label>
            <select id="optimization-range" value={draft.timeRange} onChange={(event) => update("timeRange", event.target.value)}>
              <option value="24h">24 hours</option><option value="7d">7 days</option><option value="30d">30 days</option><option value="custom">Custom</option>
            </select>
          </div>
          {draft.timeRange === "custom" && <>
            <div><label className="field-label" htmlFor="optimization-start">From</label><input id="optimization-start" type="datetime-local" value={draft.start} onChange={(event) => update("start", event.target.value)} /></div>
            <div><label className="field-label" htmlFor="optimization-end">To</label><input id="optimization-end" type="datetime-local" value={draft.end} min={draft.start} onChange={(event) => update("end", event.target.value)} /></div>
          </>}
          <div className="optimization-full">
            <label className="field-label" htmlFor="optimization-owner">Owner or cost center (optional)</label>
            <input id="optimization-owner" type="text" maxLength={120} value={draft.owner} onChange={(event) => update("owner", event.target.value)} />
          </div>
          <div className="connection-scope optimization-full">
            <strong>Read scope summary</strong><p>{selectedApp?.scope ?? "Select an application with an approved scope."}</p>
            {selectedApp && <p className="muted">Permitted actions: {selectedApp.permitted_actions.join(", ")}. Scopes are enforced by the server; this selection does not grant additional access.</p>}
            {selectedApp?.connection_kind === "local_stub" && <p className="muted">Local registered adapter — bundled inputs, not live subscription telemetry.</p>}
            {!applications.length && <p className="muted">No applications are registered. Choose an upload or measured example, or ask an administrator to register a server-side adapter.</p>}
          </div>
        </div>}
      </section>}

      <section className="panel">
        <label className="field-label" htmlFor="optimization-desired-outcome">Desired outcome (required)</label>
        <textarea id="optimization-desired-outcome" value={draft.desiredOutcome} maxLength={2000}
          placeholder="Produce a grounded customer response using the applicable policy."
          onChange={(event) => update("desiredOutcome", event.target.value)} />
        <fieldset>
          <legend className="field-label">What must remain true? (select at least one)</legend>
          <div className="advanced-grid">{QUALITY_OPTIONS.map(([value, label]) => <label key={value} className="checkbox-row">
            <input type="checkbox" checked={draft.quality.includes(value)} onChange={(event) =>
              update("quality", event.target.checked ? [...draft.quality, value] : draft.quality.filter((item) => item !== value))} />{label}
          </label>)}</div>
        </fieldset>
        {isPrompt && draft.quality.includes("same_answer_quality") && <div>
          <label className="field-label" htmlFor="optimization-expected-result">Expected result (required)</label>
          <textarea id="optimization-expected-result" value={draft.expectedResult} maxLength={2000}
            placeholder="Describe the decision, answer, or acceptance criteria TokenOS must preserve."
            onChange={(event) => update("expectedResult", event.target.value)} />
        </div>}
        {isPrompt && draft.quality.includes("required_tests") && <p className="error-text">Required test suites are not supported for a single prompt. Protect will block this requirement unless you choose a workflow mode.</p>}
        {draft.quality.includes("latency_target") && <div>
          <label className="field-label" htmlFor="optimization-latency">Required latency target (milliseconds)</label>
          <input id="optimization-latency" type="number" min={1} max={3600000} value={draft.latency} onChange={(event) => update("latency", event.target.value)} />
        </div>}
        <div><label className="field-label" htmlFor="optimization-goal">Optimization goal (required)</label>
          <select id="optimization-goal" value={draft.goal} onChange={(event) => update("goal", event.target.value)}>
            <option value="">Select a goal</option>{GOAL_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </div>
        <div className="advanced-grid">
          <div><label className="field-label" htmlFor="optimization-volume">Expected recurring volume (optional)</label>
            <input id="optimization-volume" type="number" min={1} max={1000000000} step={1} value={draft.volume} placeholder="Requests"
              onChange={(event) => update("volume", event.target.value)} />
          </div>
          <div><label className="field-label" htmlFor="optimization-period">Volume period</label>
            <select id="optimization-period" value={draft.period} onChange={(event) => update("period", event.target.value as OptimizationDraft["period"])}>
              <option value="day">Per day</option><option value="week">Per week</option><option value="month">Per month</option><option value="year">Per year</option>
            </select>
          </div>
        </div>
        <p className="muted">Volume is used only for a separately labelled projection. It is not a measured improvement.</p>
        <details><summary>Execution limits</summary>
          <div className="advanced-grid">
            <div><label className="field-label" htmlFor="optimization-budget">Maximum authorized model spend (USD)</label>
              <input id="optimization-budget" type="number" min={0} max={100} step={0.01} value={draft.maxSpend} onChange={(event) => update("maxSpend", event.target.value)} /></div>
            <div><label className="field-label" htmlFor="optimization-max-input-tokens">Maximum allowed input/context tokens</label>
              <input id="optimization-max-input-tokens" type="number" min={1} max={200000} step={1} value={draft.maxInputTokens}
                onChange={(event) => update("maxInputTokens", event.target.value)} /></div>
            <div><label className="field-label" htmlFor="optimization-max-output-tokens">Maximum output tokens</label>
              <input id="optimization-max-output-tokens" type="number" min={1} max={200000} step={1} value={draft.maxOutputTokens}
                onChange={(event) => update("maxOutputTokens", event.target.value)} /></div>
            <div><label className="field-label" htmlFor="optimization-max-advanced-calls">Maximum advanced calls per run</label>
              <input id="optimization-max-advanced-calls" type="number" min={0} max={1000} step={1} value={draft.maxAdvancedCalls}
                onChange={(event) => update("maxAdvancedCalls", event.target.value)} /></div>
          </div>
          <label className="checkbox-row"><input type="checkbox" checked={draft.allowAdvanced}
            onChange={(event) => update("allowAdvanced", event.target.checked)} />Allow advanced escalation only after failed efficient-model verification</label>
          <p className="muted">Credentials, deployment bindings, approved scopes and pricing are configured on the server. No model is invoked during planning.</p>
        </details>
        {uploading && <p role="status">Validating input and recording its manifest…</p>}
        {uploadError && <p className="error-text" role="alert">{uploadError}</p>}
        <ul className="readiness" aria-live="polite">
          <li className={inputReady ? "is-ready" : ""}>{inputReady ? "✓" : "•"} {isPrompt ? "Prompt source supplied" : "Required source supplied"}</li>
          <li className={requirementsReady ? "is-ready" : ""}>{requirementsReady ? "✓" : "•"} Outcome and quality requirements defined</li>
          <li className={ready ? "is-ready" : ""}>{ready ? "✓" : "•"} Local TokenOS API available</li>
        </ul>
        <div className="btn-row btn-row-end">
          {spends && <p className="muted optimization-authorize-note">
            Authorizes up to {`$${Number(draft.maxSpend || 0).toFixed(2)}`} of model spend on the route TokenOS selects. Plan, Optimize and Protect are checked first and stay open for inspection.
          </p>}
          <button className="btn btn-primary" type="button"
            disabled={!ready || !inputReady || !requirementsReady || uploading || busy} onClick={onSubmit}>
            {busy ? "Building the local plan…" : buttonCopy}
          </button>
        </div>
      </section>
    </fieldset>
  );
}
