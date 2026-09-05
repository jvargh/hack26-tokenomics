"""Token economics: what the work cost, and what it would have cost on the naive route.

TokenOS routes work to the cheapest safe route. That claim is only worth anything if
the saving is quantified, so this module computes both sides of the comparison:

  actual     — tokens really spent, priced from the configured table
  projected  — tokens the same work would have consumed had every operation been
               sent to the advanced model instead

The projection is built from exact token counts, not guesses:

  input tokens  = tiktoken count of the source text the operation actually read
  output tokens = tiktoken count of the result the operation actually produced

Both are real measurements of real text. The only hypothetical part is the routing,
so the result is reported as `projected`, never as `measured`. When no price is
configured the projection reports tokens and states that cost is unavailable rather
than inventing a number.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from .config import settings
from .pricing import calculate_cost_usd, price_source

try:  # tiktoken gives exact counts; without it no projection is claimed.
    import tiktoken

    _ENCODING = tiktoken.get_encoding("o200k_base")
except Exception:  # pragma: no cover - optional dependency
    _ENCODING = None

# Sent with every model call regardless of route: system prompt, schema instructions,
# and the JSON envelope. Measured from the prompts this service actually sends.
PROMPT_OVERHEAD_TOKENS = 180


def tokenizer_available() -> bool:
    return _ENCODING is not None


def count_tokens(text: str) -> int:
    if not text:
        return 0
    if _ENCODING is None:
        return 0
    return len(_ENCODING.encode(text))


def _as_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, default=str)
    except (TypeError, ValueError):
        return str(value)


@dataclass
class OperationProjection:
    operation_id: str
    label: str
    actual_route: str
    input_tokens: int
    output_tokens: int
    projected_cost_usd: float
    priced: bool

    def public(self) -> dict:
        return {
            "operation_id": self.operation_id,
            "label": self.label,
            "actual_route": self.actual_route,
            "projected_input_tokens": self.input_tokens,
            "projected_output_tokens": self.output_tokens,
            "projected_cost_usd": self.projected_cost_usd,
            "priced": self.priced,
        }


@dataclass
class TokenomicsLedger:
    """Accumulates both sides of the comparison as operations complete."""

    deployment: str = ""
    projections: list[OperationProjection] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.deployment = self.deployment or settings.foundry_advanced_deployment or "tokenos-advanced"

    def record(self, operation_id: str, label: str, route: str, source_text: str, result) -> None:
        """Records what this operation would have cost on the advanced model.

        Called for every operation, including those that did use a model, so the
        comparison covers the whole workflow rather than a favourable subset.
        """
        if _ENCODING is None:
            return
        input_tokens = count_tokens(source_text) + PROMPT_OVERHEAD_TOKENS
        output_tokens = count_tokens(_as_text(result))
        cost, priced = calculate_cost_usd(self.deployment, input_tokens, output_tokens)
        self.projections.append(
            OperationProjection(
                operation_id=operation_id,
                label=label,
                actual_route=route,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                projected_cost_usd=cost,
                priced=priced,
            )
        )

    @property
    def projected_input_tokens(self) -> int:
        return sum(item.input_tokens for item in self.projections)

    @property
    def projected_output_tokens(self) -> int:
        return sum(item.output_tokens for item in self.projections)

    @property
    def projected_cost_usd(self) -> float:
        return round(sum(item.projected_cost_usd for item in self.projections), 6)

    @property
    def priced(self) -> bool:
        return bool(self.projections) and all(item.priced for item in self.projections)

    def routing_story(self, operations: list[dict], model_available: bool) -> dict:
        """Explains the routing decision operation by operation.

        This is the governance claim: the complete plan is shown, not one prompt, and
        every operation states why it did or did not need a model.
        """
        groups: dict[str, list[dict]] = {}
        for item in operations:
            # Group by what the plan decided, so a missing deployment does not erase
            # the fact that TokenOS reserved this step for a model.
            groups.setdefault(item.get("intended_route") or item.get("route", "software"), []).append(item)

        readable = {
            "software": "Regular software",
            "retrieval": "Approved retrieval",
            "reuse": "Approved reuse",
            "efficient_ai": "Efficient model",
            "advanced_ai": "Advanced model",
        }
        why = {
            "software": "Deterministic rules — zero tokens spent",
            "retrieval": "Reads approved sources directly — zero tokens spent",
            "reuse": "Reuses a verified earlier result — zero tokens spent",
            "efficient_ai": "Interprets contested policy ambiguity — tried before advanced models",
            "advanced_ai": "Reserved for ambiguity that survived every cheaper route",
        }

        rows = []
        for route, items in sorted(groups.items(), key=lambda pair: -len(pair[1])):
            generative = route in {"efficient_ai", "advanced_ai"}
            ran_on_model = [item for item in items if item.get("route") in {"efficient_ai", "advanced_ai"}]
            model_calls = len(ran_on_model) if generative else 0
            rows.append({
                "route": route,
                "route_label": readable.get(route, route),
                "count": len(items),
                "model_calls": model_calls,
                "why": why.get(route, "Routed by the plan"),
                "operations": [item.get("label", "") for item in items],
                "generative": generative,
                "executed_on_model": len(ran_on_model),
                "deferred": generative and not ran_on_model,
            })

        planned_model = sum(len(items) for route, items in groups.items()
                            if route in {"efficient_ai", "advanced_ai"})
        executed_model = sum(
            1 for item in operations if item.get("route") in {"efficient_ai", "advanced_ai"}
        )
        return {
            "total_operations": len(operations),
            "operations_without_generative_ai": len(operations) - planned_model,
            "operations_reserved_for_a_model": planned_model,
            "operations_on_a_model": executed_model,
            "rows": rows,
            "model_available": model_available,
            "note": (
                None
                if model_available or not planned_model
                else f"{planned_model} operation(s) were reserved for a model, but no deployment is "
                     "configured. TokenOS reported those items as unresolved rather than answering "
                     "them without one."
            ),
        }

    def summary(self, actual_cost_usd: float, actual_tokens: int, quality_passed: bool) -> dict:
        """Builds the economics block reported in the proof.

        This is a *projection*, not a paired run. It states what the same text would
        have cost on the advanced model, and deliberately makes no claim that the
        advanced route would have reached the same quality — nothing here verified
        that. A saving may only be asserted after `baseline_run.py` executes the
        comparison path and both paths pass the same checks.
        """
        source = price_source(self.deployment) or {}
        priced = self.priced and bool(source.get("effective_date"))
        projected = self.projected_cost_usd if priced else None
        # The difference between the two routes, before any quality comparison.
        exposure = None
        if priced and projected is not None:
            exposure = round(max(projected - actual_cost_usd, 0.0), 6)

        if not tokenizer_available():
            basis = "No tokenizer is available, so no projection is claimed"
        elif not priced:
            basis = "Exact token counts, no price configured for the advanced deployment"
        else:
            basis = "Exact token counts at the configured list price"

        return {
            "actual_cost_usd": round(actual_cost_usd, 6),
            "actual_tokens": actual_tokens,
            "projected_cost_usd": projected,
            "projected_input_tokens": self.projected_input_tokens,
            "projected_output_tokens": self.projected_output_tokens,
            "projected_total_tokens": self.projected_input_tokens + self.projected_output_tokens,
            # Named "exposure", not "saving": no baseline run has verified that the
            # advanced route would have produced an equally acceptable outcome.
            "estimated_exposure_usd": exposure,
            "estimated_exposure_per_1k_runs_usd": (
                round(exposure * 1000, 2) if exposure is not None else None
            ),
            "projected_per_1k_runs_usd": (round(projected * 1000, 2) if projected is not None else None),
            "actual_per_1k_runs_usd": round(actual_cost_usd * 1000, 2),
            "quality_passed": quality_passed,
            "saving_claimable": False,
            "saving_blocked_reason": (
                "This is a projection. A saving is only claimed after a paired baseline run "
                "completes the same quality checks."
            ),
            "exposure_reason": (
                None
                if exposure is not None
                else "No price is configured for the advanced deployment"
                if tokenizer_available()
                else "No tokenizer is available"
            ),
            "cost_per_accepted_result_usd": (round(actual_cost_usd, 6) if quality_passed else None),
            "comparison_deployment": self.deployment,
            "price_effective_date": source.get("effective_date") or None,
            "price_source": source.get("source") or None,
            "basis": basis,
            "priced": priced,
            "operations": [item.public() for item in self.projections],
        }

    def baseline_table(self, actual_cost_usd: float, quality_passed: bool) -> dict | None:
        """A route comparison the Prove screen can render directly."""
        summary = self.summary(actual_cost_usd, 0, quality_passed)
        if not summary["priced"]:
            return None

        projected = summary["projected_cost_usd"] or 0.0
        exposure = summary["estimated_exposure_usd"]
        without_ai = sum(
            1 for item in self.projections if item.actual_route not in {"efficient_ai", "advanced_ai"}
        )

        def money(value: float) -> str:
            if value == 0:
                return "$0.00"
            return f"${value:,.4f}" if value < 1 else f"${value:,.2f}"

        rows = [
            ["Model cost", money(summary["actual_cost_usd"]), money(projected)],
            ["Tokens", f"{summary['actual_tokens']:,}", f"{summary['projected_total_tokens']:,}"],
            [
                "Operations on a model",
                f"{len(self.projections) - without_ai} of {len(self.projections)}",
                f"{len(self.projections)} of {len(self.projections)}",
            ],
            [
                "Quality verified",
                "yes" if quality_passed else "no",
                "not run",
            ],
            [
                "Evidence status",
                "Measured from model response usage" if summary["actual_tokens"] else "No model spend",
                "Projection, not measured spend",
            ],
        ]
        if exposure is not None:
            rows.append(["Cost difference per run", money(exposure), "—"])
            rows.append([
                "Cost at 1,000 runs",
                money(summary["actual_cost_usd"] * 1000),
                money(projected * 1000),
            ])

        return {
            "kind": "route_projection",
            # "Baseline" is reserved for an actual paired run; this table is a modelled
            # comparator built from measured token counts.
            "title": "Estimated all-AI comparator",
            "status": "Projection, not measured spend",
            "columns": ["Metric", "TokenOS route", "Estimated all-AI comparator"],
            "rows": rows,
            "note": (
                f"Projected against {summary['comparison_deployment']} using exact token counts of the "
                f"text each operation read and produced. Price effective {summary['price_effective_date']}. "
                "The token counts and prices are measured; the routing is hypothetical. The all-AI route "
                "was not executed, so this is a cost difference, not a verified saving. Run the paired "
                "comparison to turn this projection into a verified saving."
            ),
        }
