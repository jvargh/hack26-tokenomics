import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import { ApiError, type ConnectedApplication, type UploadRecord, type WorkflowDefinition } from "../api/types";
import { useRun } from "../state/runContext";
import { PhaseIntro, SectionHead } from "../components/shared/PhaseIntro";
import { formatBytes } from "../components/shared/format";
import { DESCRIBE_HEADING, DESCRIBE_SUPPORTING, WORKFLOW_COPY, WorkflowChoices } from "../components/WorkflowChoices";

type InputSource = "upload" | "connected" | "sample";

const SOURCE_LABEL: Record<InputSource, string> = {
  upload: "Upload my data",
  connected: "Use a connected application",
  sample: "Use sample data"
};

const SOURCE_HELP: Record<InputSource, string> = {
  upload: "Your files are sent to the TokenOS API, validated, and analyzed there.",
  connected:
    "This connects to an application registered with TokenOS. It does not automatically connect to an Azure subscription.",
  sample: "Bundled input processed by the real engine. Results are labelled Measured sample run."
};

function localDateTime(hoursAhead: number): string {
  const date = new Date(Date.now() + hoursAhead * 3600 * 1000);
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(
    date.getHours()
  )}:${pad(date.getMinutes())}`;
}

function defaultFieldValues(workflow: WorkflowDefinition): Record<string, string> {
  const values: Record<string, string> = {};
  for (const field of workflow.fields) {
    values[field.name] =
      field.control === "datetime" ? localDateTime(8) : String(field.default ?? "");
  }
  return values;
}

export function DescribePhase({ onSelectOptimization, initialWorkflowId = "" }: {
  onSelectOptimization: () => void;
  initialWorkflowId?: string;
}) {
  const { workflows, health, analyze, startRun } = useRun();
  const [workflowId, setWorkflowId] = useState<string>("");
  const [source, setSource] = useState<InputSource>("sample");
  const [uploads, setUploads] = useState<Record<string, UploadRecord[]>>({});
  const [values, setValues] = useState<Record<string, string>>({});
  const [outcome, setOutcome] = useState("");
  const [importance, setImportance] = useState("important");
  const [needed, setNeeded] = useState("today");
  const [priority, setPriority] = useState("balanced");
  const [maximumCost, setMaximumCost] = useState(1);
  const [quality, setQuality] = useState(0.92);
  const [classification, setClassification] = useState("Internal");
  const [approvalRequired, setApprovalRequired] = useState(false);
  const [connection, setConnection] = useState({ application: "", reference: "" });
  const [applications, setApplications] = useState<ConnectedApplication[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [pageError, setPageError] = useState("");
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const fileInputs = useRef<Record<string, HTMLInputElement | null>>({});

  const workflow = useMemo(
    () => workflows.find((item) => item.workflow_id === workflowId) ?? workflows[0],
    [workflows, workflowId]
  );

  // Selecting a workflow resets every workflow-specific input, including files.
  const selectWorkflow = useCallback((definition: WorkflowDefinition) => {
    setWorkflowId(definition.workflow_id);
    setUploads({});
    setValues(defaultFieldValues(definition));
    setOutcome(definition.default_outcome);
    setImportance(definition.defaults.importance);
    setNeeded(definition.defaults.needed);
    setPriority(definition.defaults.priority);
    setMaximumCost(definition.defaults.maximum_cost_usd);
    setQuality(definition.defaults.required_quality_score);
    setConnection({ application: "", reference: "" });
    setErrors({});
    setPageError("");
  }, []);

  useEffect(() => {
    if (!workflowId && workflows.length) {
      selectWorkflow(workflows.find((item) => item.workflow_id === initialWorkflowId) ?? workflows[0]);
    }
  }, [workflows, workflowId, selectWorkflow, initialWorkflowId]);

  // Registered applications come from the server; the browser never invents one.
  useEffect(() => {
    if (!workflow) return;
    let active = true;
    api
      .listConnections(workflow.workflow_id)
      .then((items) => {
        if (active) setApplications(items);
      })
      .catch(() => {
        if (active) setApplications([]);
      });
    return () => {
      active = false;
    };
  }, [workflow]);

  const selectedApp = useMemo(
    () => applications.find((item) => item.application_id === connection.application) ?? null,
    [applications, connection.application]
  );

  const apiReady = health.state === "ready";
  const requiredRoles = workflow?.roles.filter((role) => role.required) ?? [];
  const hasRequiredInputs =
    source === "connected"
      ? Boolean(connection.application.trim() && connection.reference.trim())
      : requiredRoles.every((role) => (uploads[role.role]?.length ?? 0) > 0);
  const hasRequiredFields = (workflow?.fields ?? [])
    .filter((field) => field.required && field.control !== "checkbox")
    .every((field) => String(values[field.name] ?? "").trim().length > 0);
  const outcomeReady = outcome.trim().length > 0;
  const ready = apiReady && hasRequiredInputs && hasRequiredFields && outcomeReady && !busy;

  const uploadFiles = async (role: string, files: FileList | null) => {
    if (!files?.length || !workflow) return;
    setBusy(`Uploading to ${role}`);
    setErrors((current) => ({ ...current, [role]: "" }));
    try {
      const created = await api.upload(
        workflow.workflow_id,
        role,
        Array.from(files),
        classification.toLowerCase()
      );
      setUploads((current) => ({ ...current, [role]: [...(current[role] ?? []), ...created] }));
    } catch (error) {
      setErrors((current) => ({
        ...current,
        [role]: error instanceof Error ? error.message : "The upload failed."
      }));
    } finally {
      setBusy(null);
      const input = fileInputs.current[role];
      if (input) input.value = "";
    }
  };

  const removeUpload = async (role: string, uploadId: string) => {
    await api.removeUpload(uploadId).catch(() => undefined);
    setUploads((current) => ({
      ...current,
      [role]: (current[role] ?? []).filter((item) => item.upload_id !== uploadId)
    }));
  };

  const loadSample = async () => {
    if (!workflow) return;
    setBusy("Loading the bundled sample through the API");
    setPageError("");
    try {
      const result = await api.sampleUploads(workflow.workflow_id);
      setUploads(result.uploads);
    } catch (error) {
      setPageError(error instanceof Error ? error.message : "The sample could not be loaded.");
    } finally {
      setBusy(null);
    }
  };

  const submit = async () => {
    if (!workflow) return;
    setBusy("Analyzing with TokenOS");
    setErrors({});
    setPageError("");
    try {
      const plan = await analyze({
        workflow_id: workflow.workflow_id,
        input_source: source,
        uploads: Object.fromEntries(
          Object.entries(uploads).map(([role, items]) => [role, items.map((item) => item.upload_id)])
        ),
        inputs: values,
        connection: source === "connected" ? connection : null,
        desired_outcome: outcome,
        requirements: {
          importance,
          needed,
          priority,
          maximum_cost_usd: maximumCost,
          required_quality_score: quality,
          human_approval_required: approvalRequired,
          data_classification: classification.toLowerCase()
        }
      });
      await startRun(plan.plan_id);
    } catch (error) {
      if (error instanceof ApiError && error.fieldErrors.length) {
        setErrors(Object.fromEntries(error.fieldErrors.map((item) => [item.field, item.message])));
      } else {
        setPageError(error instanceof Error ? error.message : "The analysis request failed.");
      }
    } finally {
      setBusy(null);
    }
  };

  if (!workflow) {
    return (
      <div className="phase">
        <PhaseIntro
          heading={DESCRIBE_HEADING}
          supporting={
            health.state === "offline"
              ? "Start the TokenOS API on http://localhost:8000. The UI does not generate substitute results."
              : "Loading workflows from the TokenOS API..."
          }
          focusKey="describe"
        />
      </div>
    );
  }

  return (
    <div className="phase">
      <PhaseIntro
        heading={DESCRIBE_HEADING}
        supporting={DESCRIBE_SUPPORTING}
        focusKey="describe"
      />

      <WorkflowChoices workflows={workflows} selected={workflow.workflow_id} onSelect={(id) => {
        if (id === "workflow_optimization") onSelectOptimization();
        else {
          const selected = workflows.find((item) => item.workflow_id === id);
          if (selected) selectWorkflow(selected);
        }
      }} />

      <section className="panel">
        <SectionHead title="Provide the work" supporting={WORKFLOW_COPY[workflow.workflow_id]?.supporting ?? workflow.description} />

        <div className="source-choices" role="radiogroup" aria-label="Input source">
          {(Object.keys(SOURCE_LABEL) as InputSource[]).map((option) => (
            <button
              key={option}
              type="button"
              role="radio"
              aria-checked={source === option}
              className={`source-choice ${source === option ? "is-selected" : ""}`}
              onClick={() => {
                setSource(option);
                setUploads({});
                setPageError("");
              }}
            >
              <span className="template-name">{SOURCE_LABEL[option]}</span>
              <span className="template-support">{SOURCE_HELP[option]}</span>
            </button>
          ))}
        </div>

        {source === "sample" ? (
          <div className="notice notice-brand">
            <h3>{workflow.sample.name}</h3>
            <p>{workflow.sample.description}</p>
            <p className="muted" style={{ marginTop: 6 }}>
              The bundled files are submitted through the same upload, extraction, and analysis path
              as your own data. Results are labelled <strong>Measured sample run</strong>.
            </p>
            <div className="btn-row" style={{ marginTop: 10 }}>
              <button
                type="button"
                className="btn btn-small"
                onClick={() => void loadSample()}
                disabled={!apiReady || Boolean(busy)}
              >
                {Object.keys(uploads).length ? "Reload sample data" : "Load sample data"}
              </button>
            </div>
          </div>
        ) : null}

        {source === "connected" ? (
          <div className="advanced-grid">
            {applications.length === 0 ? (
              <div className="connection-empty" style={{ gridColumn: "1 / -1" }}>
                <strong>No applications are registered for this workflow.</strong>
                <p>
                  {workflow
                    ? `TokenOS has no connected application that is permitted to supply ${workflow.label.toLowerCase()} input.`
                    : ""}{" "}
                  Choose <em>Upload my data</em> or <em>Use sample data</em>, or register an
                  application on the server first.
                </p>
              </div>
            ) : null}
            <div>
              <label className="field-label" htmlFor="connected-application">
                Registered application
              </label>
              <select
                id="connected-application"
                value={connection.application}
                disabled={applications.length === 0}
                onChange={(event) =>
                  setConnection({ application: event.target.value, reference: "" })
                }
              >
                <option value="">
                  {applications.length ? "Select an application" : "None registered"}
                </option>
                {applications.map((app) => (
                  <option key={app.application_id} value={app.application_id}>
                    {app.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="field-label" htmlFor="connected-reference">
                {selectedApp?.reference_label ?? "Reference"}
              </label>
              <select
                id="connected-reference"
                value={connection.reference}
                disabled={!selectedApp}
                onChange={(event) =>
                  setConnection((current) => ({ ...current, reference: event.target.value }))
                }
              >
                <option value="">
                  {selectedApp ? "Select a reference" : "Select an application first"}
                </option>
                {(selectedApp?.available_references ?? []).map((reference) => (
                  <option key={reference} value={reference}>
                    {reference}
                  </option>
                ))}
              </select>
            </div>
            {selectedApp ? (
              <div className="connection-scope" style={{ gridColumn: "1 / -1" }}>
                <div>
                  <span>What this application may do</span>
                  <strong>{selectedApp.scope}</strong>
                </div>
                <div>
                  <span>Permitted actions</span>
                  <strong>{selectedApp.permitted_actions.join(", ")}</strong>
                </div>
                {selectedApp.connection_kind === "local_stub" ? (
                  <p className="connection-stub">
                    This is a local connector stub. It returns bundled records so the connected
                    path can be exercised without external credentials. Results are labelled
                    Measured run, local connector stub.
                  </p>
                ) : null}
              </div>
            ) : null}
            <p className="muted" style={{ gridColumn: "1 / -1", margin: 0 }}>
              {SOURCE_HELP.connected} The registration defines its adapter, credentials, and
              permitted actions on the server, so no provider credentials reach the browser.
            </p>
          </div>
        ) : null}

        {source !== "connected"
          ? workflow.roles.map((role) => (
              <div key={role.role} className="input-role">
                <div className="row-between">
                  <label className="field-label" htmlFor={`file-${role.role}`}>
                    {role.label}
                  </label>
                  <span className="muted" style={{ fontSize: 12 }}>
                    {role.accept}
                  </span>
                </div>
                <p className="muted" style={{ margin: "0 0 8px", fontSize: 12.5 }}>
                  {role.help}
                </p>
                {source === "upload" ? (
                  <input
                    id={`file-${role.role}`}
                    ref={(element) => {
                      fileInputs.current[role.role] = element;
                    }}
                    type="file"
                    accept={role.accept}
                    multiple={role.multiple}
                    disabled={!apiReady || Boolean(busy)}
                    onChange={(event) => void uploadFiles(role.role, event.target.files)}
                  />
                ) : null}
                {(uploads[role.role] ?? []).length ? (
                  <ul className="upload-list">
                    {(uploads[role.role] ?? []).map((item) => (
                      <li key={item.upload_id}>
                        <div>
                          <strong>{item.name}</strong>
                          <div className="muted" style={{ fontSize: 12 }}>
                            {item.media_type.split("/").pop()?.toUpperCase()} ·{" "}
                            {formatBytes(item.size_bytes)} ·{" "}
                            {item.extracted_character_count > 0
                              ? `${item.extracted_character_count.toLocaleString()} characters extracted`
                              : `${(item.detail as { entry_count?: number })?.entry_count ?? 0} archive entries`}{" "}
                            · {item.status === "ready" ? "Ready" : item.status}
                          </div>
                        </div>
                        {source === "upload" ? (
                          <button
                            type="button"
                            className="btn btn-small"
                            onClick={() => void removeUpload(role.role, item.upload_id)}
                          >
                            Remove
                          </button>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                ) : null}
                {errors[role.role] ? (
                  <p className="error-text" role="alert">
                    {errors[role.role]}
                  </p>
                ) : null}
              </div>
            ))
          : null}

        {workflow.fields.map((field) => (
          <div key={field.name}>
            {field.control === "checkbox" ? (
              <div className="checkbox-row">
                <input
                  id={`field-${field.name}`}
                  type="checkbox"
                  checked={String(values[field.name] ?? "") === "true"}
                  onChange={(event) =>
                    setValues((current) => ({
                      ...current,
                      [field.name]: String(event.target.checked)
                    }))
                  }
                />
                <label htmlFor={`field-${field.name}`}>{field.label}</label>
              </div>
            ) : (
              <>
                <label className="field-label" htmlFor={`field-${field.name}`}>
                  {field.label}
                </label>
                {field.control === "textarea" ? (
                  <textarea
                    id={`field-${field.name}`}
                    value={values[field.name] ?? ""}
                    maxLength={field.maxLength}
                    style={{ minHeight: 72 }}
                    onChange={(event) =>
                      setValues((current) => ({ ...current, [field.name]: event.target.value }))
                    }
                  />
                ) : field.control === "select" ? (
                  <select
                    id={`field-${field.name}`}
                    value={values[field.name] ?? ""}
                    onChange={(event) =>
                      setValues((current) => ({ ...current, [field.name]: event.target.value }))
                    }
                  >
                    {(field.options ?? []).map((option) => (
                      <option key={option}>{option}</option>
                    ))}
                  </select>
                ) : (
                  <input
                    id={`field-${field.name}`}
                    type={
                      field.control === "number"
                        ? "number"
                        : field.control === "datetime"
                          ? "datetime-local"
                          : "text"
                    }
                    value={values[field.name] ?? ""}
                    min={field.min}
                    max={field.max}
                    step={field.step}
                    maxLength={field.maxLength}
                    onChange={(event) =>
                      setValues((current) => ({ ...current, [field.name]: event.target.value }))
                    }
                  />
                )}
                {field.help ? (
                  <p className="muted" style={{ margin: "6px 0 0", fontSize: 12.5 }}>
                    {field.help}
                  </p>
                ) : null}
              </>
            )}
            {errors[field.name] ? (
              <p className="error-text" role="alert">
                {errors[field.name]}
              </p>
            ) : null}
          </div>
        ))}
      </section>

      <section className="panel">
        <SectionHead
          title="Desired outcome"
          supporting="This describes what to produce. It does not replace the supplied work."
        />
        <textarea id="outcome" value={outcome} onChange={(event) => setOutcome(event.target.value)} />

        <div className="priority-grid">
          <div>
            <label className="field-label is-caps" htmlFor="importance">
              Importance
            </label>
            <select
              id="importance"
              value={importance}
              onChange={(event) => setImportance(event.target.value)}
            >
              <option value="routine">Routine</option>
              <option value="important">Important</option>
              <option value="critical">Critical</option>
            </select>
          </div>
          <div>
            <label className="field-label is-caps" htmlFor="needed">
              Needed
            </label>
            <select id="needed" value={needed} onChange={(event) => setNeeded(event.target.value)}>
              <option value="now">Now</option>
              <option value="today">Today</option>
              <option value="flexible">Flexible</option>
            </select>
          </div>
          <div>
            <label className="field-label is-caps" htmlFor="priority">
              Priority
            </label>
            <select
              id="priority"
              value={priority}
              onChange={(event) => setPriority(event.target.value)}
            >
              <option value="lowest_cost">Lowest cost</option>
              <option value="balanced">Balanced</option>
              <option value="best_quality">Best quality</option>
            </select>
          </div>
        </div>

        <details
          open={advancedOpen}
          onToggle={(event) => setAdvancedOpen((event.target as HTMLDetailsElement).open)}
        >
          <summary>Advanced settings</summary>
          <div className="advanced-grid">
            <div>
              <label className="field-label" htmlFor="max-cost">
                Maximum authorized model cost (dollars)
              </label>
              <input
                id="max-cost"
                type="number"
                min={0}
                step={0.01}
                value={maximumCost}
                onChange={(event) => setMaximumCost(Number(event.target.value))}
              />
            </div>
            <div>
              <label className="field-label" htmlFor="quality">
                Quality requirement (0 to 1)
              </label>
              <input
                id="quality"
                type="number"
                min={0}
                max={1}
                step={0.01}
                value={quality}
                onChange={(event) => setQuality(Number(event.target.value))}
              />
            </div>
            <div>
              <label className="field-label" htmlFor="classification">
                Data classification
              </label>
              <select
                id="classification"
                value={classification}
                onChange={(event) => setClassification(event.target.value)}
              >
                <option>Public</option>
                <option>Internal</option>
                <option>Confidential</option>
              </select>
            </div>
            <div className="checkbox-row">
              <input
                id="approval"
                type="checkbox"
                checked={approvalRequired}
                onChange={(event) => setApprovalRequired(event.target.checked)}
              />
              <label htmlFor="approval">Require human approval before execution</label>
            </div>
            <p className="muted" style={{ gridColumn: "1 / -1", margin: 0, fontSize: 12.5 }}>
              {workflow.model_use}
            </p>
          </div>
        </details>

        <ul className="readiness" aria-live="polite">
          <li className={hasRequiredInputs ? "is-ready" : ""}>
            <span aria-hidden="true">{hasRequiredInputs ? "✓" : "•"}</span> Required input supplied
          </li>
          <li className={outcomeReady && hasRequiredFields ? "is-ready" : ""}>
            <span aria-hidden="true">{outcomeReady && hasRequiredFields ? "✓" : "•"}</span> Desired
            outcome and required fields defined
          </li>
          <li className={apiReady ? "is-ready" : ""}>
            <span aria-hidden="true">{apiReady ? "✓" : "•"}</span> TokenOS API available
          </li>
        </ul>

        {pageError ? (
          <p className="error-text" role="alert">
            {pageError}
          </p>
        ) : null}

        <div className="btn-row btn-row-end">
          <button
            type="button"
            className="btn btn-primary"
            disabled={!ready}
            onClick={() => void submit()}
          >
            {busy ?? "Analyze with TokenOS"}
          </button>
        </div>
      </section>
    </div>
  );
}
