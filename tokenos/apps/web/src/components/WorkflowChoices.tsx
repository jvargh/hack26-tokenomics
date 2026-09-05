import type { WorkflowDefinition } from "../api/types";

export const WORKFLOW_COPY: Record<string, { title: string; supporting: string }> = {
  document_review: {
    title: "Review documents against rules",
    supporting: "Upload records and policies. TokenOS checks what software can verify before using AI for unclear cases."
  },
  software_validation: {
    title: "Test a code change",
    supporting: "Upload or connect a change. TokenOS runs checks first and uses AI only to investigate unresolved failures."
  },
  deadline_processing: {
    title: "Process records by a deadline",
    supporting: "Submit a workload and due time. TokenOS completes routine records locally and reserves AI for exceptions."
  },
  workflow_optimization: {
    title: "Optimize an existing AI workflow",
    supporting: "Connect an AI application or prior run. TokenOS finds the lowest-cost route that still meets the required quality."
  }
};

export const DESCRIBE_HEADING = "What do you want TokenOS to optimize?";
export const DESCRIBE_SUPPORTING = "Choose a workflow, provide the real work, and TokenOS will find the least-expensive safe route and prove the result.";

export function workflowTitle(id: string): string {
  return WORKFLOW_COPY[id]?.title ?? id.replace(/_/g, " ");
}

export function WorkflowChoices({
  workflows, selected, onSelect
}: {
  workflows: WorkflowDefinition[];
  selected: string;
  onSelect: (id: string) => void;
}) {
  const ids = [
    ...workflows.filter((item) => item.workflow_id !== "false_savings" && item.workflow_id !== "workflow_optimization")
      .map((item) => item.workflow_id),
    "workflow_optimization"
  ];
  return (
    <fieldset>
      <legend className="sr-only">Workflow</legend>
      <div className="template-grid">
        {ids.map((id) => {
          const definition = workflows.find((item) => item.workflow_id === id);
          return (
            <button key={id} type="button" className="template" aria-pressed={selected === id}
              onClick={() => onSelect(id)}>
              <span className="template-name">{WORKFLOW_COPY[id]?.title ?? definition?.label}</span>
              <span className="template-support">{WORKFLOW_COPY[id]?.supporting ?? definition?.short_label}</span>
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}
