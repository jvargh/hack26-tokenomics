"""Workflow registry."""

from __future__ import annotations

from .base import WorkflowHandler
from .deadline_processing import DeadlineProcessingWorkflow
from .document_review import DocumentReviewWorkflow
from .false_savings import FalseSavingsWorkflow
from .software_validation import SoftwareValidationWorkflow
from .workflow_optimization import WorkflowOptimizationWorkflow

_WORKFLOWS: dict[str, WorkflowHandler] = {
    handler.workflow_id: handler
    for handler in (
        DocumentReviewWorkflow(),
        SoftwareValidationWorkflow(),
        DeadlineProcessingWorkflow(),
        FalseSavingsWorkflow(),
        WorkflowOptimizationWorkflow(),
    )
}


def normalize_workflow_id(workflow_id: str) -> str:
    key = (workflow_id or "").strip().replace("-", "_").lower()
    return {"validate_software": "software_validation", "meet_deadline": "deadline_processing"}.get(key, key)


def get_workflow(workflow_id: str) -> WorkflowHandler:
    handler = _WORKFLOWS.get(normalize_workflow_id(workflow_id))
    if handler is None:
        raise KeyError(f"Unknown workflow '{workflow_id}'")
    return handler


def all_workflows() -> list[WorkflowHandler]:
    return [handler for handler in _WORKFLOWS.values() if handler.workflow_id != "false_savings"]
