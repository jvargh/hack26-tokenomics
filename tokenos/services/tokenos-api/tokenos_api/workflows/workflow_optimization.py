from .base import WorkflowHandler


class WorkflowOptimizationWorkflow(WorkflowHandler):
    workflow_id = "workflow_optimization"
    label = "Optimize an existing AI workflow"
    description = "Connect an AI application or prior run. TokenOS finds the lowest-cost route that still meets the required quality."
    default_outcome = "Preserve accepted outcomes while measuring the least-expensive eligible route."

    def definition(self) -> dict:
        return {
            "workflow_id": self.workflow_id, "label": self.label, "short_label": self.description,
            "description": self.description, "default_outcome": self.default_outcome,
            "defaults": {"importance": "important", "needed": "today", "priority": "balanced",
                         "maximum_cost_usd": 0.05, "required_quality_score": 1.0},
            "roles": [], "fields": [], "staged_api": True,
        }
