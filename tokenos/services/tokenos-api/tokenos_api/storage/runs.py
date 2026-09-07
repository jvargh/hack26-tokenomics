"""Run state and the ordered event stream the UI consumes.

Every event carries an increasing sequence number so a browser that drops its
connection can resume with Last-Event-ID instead of restarting the run.
"""

from __future__ import annotations

import asyncio
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RunEvent:
    sequence: int
    run_id: str
    type: str
    at: str
    data: dict[str, Any]

    def payload(self) -> dict:
        return {"sequence": self.sequence, "run_id": self.run_id, "at": self.at, **self.data}


@dataclass
class Run:
    run_id: str
    plan_id: str
    workflow_id: str
    status: str = "created"
    phase: str = "plan"
    created_at: str = field(default_factory=_now)
    events: list[RunEvent] = field(default_factory=list)
    operations: list[dict] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    proof: dict | None = None
    error: dict | None = None
    approval: dict | None = None
    stop_requested: bool = False
    _sequence: int = 0
    _subscribers: list[asyncio.Queue] = field(default_factory=list)
    _approval_gate: asyncio.Event = field(default_factory=asyncio.Event)
    _subscriber_attached: asyncio.Event = field(default_factory=asyncio.Event)

    def emit(self, event_type: str, data: dict | None = None) -> RunEvent:
        self._sequence += 1
        event = RunEvent(
            sequence=self._sequence,
            run_id=self.run_id,
            type=event_type,
            at=_now(),
            data=data or {},
        )
        self.events.append(event)
        for queue in list(self._subscribers):
            queue.put_nowait(event)
        return event

    def subscribe(self, after_sequence: int = 0) -> tuple[asyncio.Queue, list[RunEvent]]:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.append(queue)
        self._subscriber_attached.set()
        replay = [event for event in self.events if event.sequence > after_sequence]
        return queue, replay

    async def wait_for_subscriber(self, timeout: float) -> bool:
        """Holds execution until a client is listening, so no phase is missed."""
        try:
            await asyncio.wait_for(self._subscriber_attached.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        if queue in self._subscribers:
            self._subscribers.remove(queue)

    @property
    def finished(self) -> bool:
        return self.status in {"completed", "failed", "stopped", "blocked"}

    @property
    def active(self) -> bool:
        """True while the run is still in flight, whatever outcome it reaches.

        `finished` is deliberately not reused here: it drives stream keep-alives
        and does not count `completed_with_findings` as a terminal state, which
        would wrongly protect a finished run from deletion.
        """
        return self.status in {"created", "running", "waiting"}

    def state(self) -> dict:
        return {
            "run_id": self.run_id,
            "plan_id": self.plan_id,
            "workflow_id": self.workflow_id,
            "status": self.status,
            "phase": self.phase,
            "created_at": self.created_at,
            "operations": self.operations,
            "metrics": self.metrics,
            "approval": self.approval,
            "proof": self.proof,
            "error": self.error,
            "last_sequence": self._sequence,
        }


@dataclass
class Plan:
    plan_id: str
    workflow_id: str
    request: dict
    input_summary: dict
    operations: list[dict]
    estimated_model_calls: dict
    estimated_maximum_cost_usd: float
    requires_approval: bool
    summary: dict
    context: dict = field(default_factory=dict)
    created_at: str = field(default_factory=_now)

    def public(self) -> dict:
        return {
            "plan_id": self.plan_id,
            "workflow_id": self.workflow_id,
            "input_summary": self.input_summary,
            "operation_count": len(self.operations),
            "operations": self.operations,
            "estimated_model_calls": self.estimated_model_calls,
            "estimated_maximum_cost_usd": self.estimated_maximum_cost_usd,
            "requires_approval": self.requires_approval,
            "plan_summary": self.summary,
        }


class RunStore:
    def __init__(self) -> None:
        self._plans: dict[str, Plan] = {}
        self._runs: dict[str, Run] = {}
        self._idempotency: dict[str, str] = {}

    def add_plan(self, plan: Plan) -> Plan:
        self._plans[plan.plan_id] = plan
        return plan

    def plan(self, plan_id: str) -> Plan | None:
        return self._plans.get(plan_id)

    def create_run(self, plan: Plan, idempotency_key: str | None) -> tuple[Run, bool]:
        if idempotency_key and idempotency_key in self._idempotency:
            return self._runs[self._idempotency[idempotency_key]], False
        run = Run(run_id=f"run-{secrets.token_hex(5)}", plan_id=plan.plan_id, workflow_id=plan.workflow_id)
        self._runs[run.run_id] = run
        if idempotency_key:
            self._idempotency[idempotency_key] = run.run_id
        return run, True

    def run(self, run_id: str) -> Run | None:
        return self._runs.get(run_id)

    def delete(self, run_id: str) -> bool:
        """Removes one run and any idempotency key that pointed at it."""
        if run_id not in self._runs:
            return False
        del self._runs[run_id]
        for key, target in list(self._idempotency.items()):
            if target == run_id:
                del self._idempotency[key]
        return True

    def clear(self) -> int:
        """Removes every recorded run. Plans are left alone: they hold no proof
        and an in-flight plan may still be waiting to start."""
        removed = len(self._runs)
        self._runs.clear()
        self._idempotency.clear()
        return removed

    def history(self) -> list[dict]:
        return [
            {
                "run_id": run.run_id,
                "workflow_id": run.workflow_id,
                "status": run.status,
                "created_at": run.created_at,
                "proof": run.proof,
            }
            for run in sorted(self._runs.values(), key=lambda item: item.created_at, reverse=True)
        ]


run_store = RunStore()


def new_plan_id() -> str:
    return f"plan-{secrets.token_hex(5)}"
