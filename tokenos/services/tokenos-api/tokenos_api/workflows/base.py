"""Workflow framework shared by the four TokenOS workflows."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from ..storage.uploads import Upload


@dataclass
class OperationResult:
    detail: dict = field(default_factory=dict)
    route: str | None = None
    reason: str | None = None
    cost_usd: float = 0.0
    quality: dict | None = None
    model_usage: dict | None = None
    # Set when one operation made more than one model call, such as an efficient
    # attempt followed by a single advanced escalation. Each entry carries its own
    # `why_ai` reason so every paid call can be justified individually.
    model_usages: list = field(default_factory=list)

    def all_model_usages(self) -> list:
        if self.model_usages:
            return list(self.model_usages)
        return [self.model_usage] if self.model_usage else []


@dataclass
class Operation:
    id: str
    order: int
    label: str
    kind: str
    reason: str
    route: str
    depends_on: list[int] = field(default_factory=list)
    side_effect: bool = False
    quality_check: str | None = None
    # The route this operation would take if every route were available. Kept so the
    # governance decision stays visible when a model deployment is not configured.
    intended_route: str | None = None
    handler: Callable[["RunContext"], Awaitable[OperationResult]] | None = None

    def public(self) -> dict:
        return {
            "operation_id": self.id,
            "order": self.order,
            "label": self.label,
            "kind": self.kind,
            "reason": self.reason,
            "route": self.route,
            "intended_route": self.intended_route or self.route,
            "depends_on": self.depends_on,
            "side_effect": self.side_effect,
            "quality_check": self.quality_check,
        }


@dataclass
class PlanBuild:
    operations: list[Operation]
    input_summary: dict
    summary: dict
    estimated_model_calls: dict
    estimated_maximum_cost_usd: float
    requires_approval: bool = False
    context: dict = field(default_factory=dict)
    protection: dict = field(default_factory=dict)


@dataclass
class RunContext:
    workflow_id: str
    request: dict
    uploads_by_role: dict[str, list[Upload]]
    artifacts: dict[str, Any] = field(default_factory=dict)
    model_calls: list[dict] = field(default_factory=list)

    @property
    def uploads(self) -> list[Upload]:
        return [upload for group in self.uploads_by_role.values() for upload in group]

    def role(self, role: str) -> list[Upload]:
        return self.uploads_by_role.get(role, [])

    def first(self, role: str) -> Upload | None:
        group = self.role(role)
        return group[0] if group else None


@dataclass
class VerificationCheck:
    name: str
    rule: str
    result: str
    passed: bool

    def public(self) -> dict:
        return {"name": self.name, "rule": self.rule, "result": self.result, "passed": self.passed}


@dataclass
class VerificationOutcome:
    checks: list[VerificationCheck]
    quality_score: float
    quality_passed: bool
    deadline_met: bool | None = None
    facts: list[dict] = field(default_factory=list)
    finding: dict | None = None
    baseline: dict | None = None


class WorkflowHandler:
    """Base class every workflow implements."""

    workflow_id: str = ""
    label: str = ""
    description: str = ""
    default_outcome: str = ""
    default_importance: str = "important"
    default_needed: str = "today"
    default_priority: str = "balanced"
    default_maximum_cost_usd: float = 1.0
    default_quality: float = 0.92

    def definition(self) -> dict:
        raise NotImplementedError

    def validate(self, request: dict, uploads_by_role: dict[str, list[Upload]]) -> list[dict]:
        raise NotImplementedError

    def build_plan(self, request: dict, uploads_by_role: dict[str, list[Upload]]) -> PlanBuild:
        raise NotImplementedError

    def verify(self, context: RunContext) -> VerificationOutcome:
        raise NotImplementedError
