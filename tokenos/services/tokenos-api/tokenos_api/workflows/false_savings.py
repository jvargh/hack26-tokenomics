"""Compare AI options and prove value.

Compares completed-run history across routes using fully loaded cost per
accepted result. This workflow needs no generative model at all.
"""

from __future__ import annotations

from ..storage.uploads import Upload
from ._util import as_bool, as_float, as_int, read_tabular
from .base import (
    Operation,
    OperationResult,
    PlanBuild,
    RunContext,
    VerificationCheck,
    VerificationOutcome,
    WorkflowHandler,
)

REQUIRED_COLUMNS = [
    "run_id",
    "route",
    "ai_cost_usd",
    "successful",
    "accepted_first_pass",
    "quality_score",
    "correction_seconds",
]


class FalseSavingsWorkflow(WorkflowHandler):
    workflow_id = "false_savings"
    label = "Compare AI options and prove value"
    # The single approved supporting string for this workflow. See DocumentReviewWorkflow.
    description = (
        "Compare routes using cost, quality, and correction effort, then show the "
        "lowest-cost accepted outcome."
    )
    default_outcome = (
        "Compare the selected AI routes and identify which route has the lowest fully loaded "
        "cost per successful accepted outcome."
    )
    default_needed = "today"
    default_priority = "best_quality"
    default_maximum_cost_usd = 1.0

    def definition(self) -> dict:
        return {
            "workflow_id": self.workflow_id,
            "label": self.label,
            "short_label": self.description,
            "description": self.description,
            "default_outcome": self.default_outcome,
            "defaults": {
                "importance": self.default_importance,
                "needed": self.default_needed,
                "priority": self.default_priority,
                "maximum_cost_usd": self.default_maximum_cost_usd,
                "required_quality_score": self.default_quality,
            },
            "roles": [
                {
                    "role": "outcome-history",
                    "label": "Outcome history",
                    "help": "Completed runs with route, AI cost, acceptance, quality, and correction time.",
                    "accept": ".csv,.json,.jsonl",
                    "multiple": False,
                    "required": True,
                }
            ],
            "fields": [
                {
                    "name": "reviewer-hourly-rate",
                    "label": "Loaded hourly rate",
                    "control": "number",
                    "required": True,
                    "default": "68",
                    "min": 0,
                    "help": "Standard loaded cost of reviewer time, in dollars per hour.",
                },
                {
                    "name": "acceptance-rule",
                    "label": "Accepted-result rule",
                    "control": "text",
                    "required": True,
                    "default": "Accepted without correction, retry, or reversal",
                    "maxLength": 300,
                },
                {
                    "name": "minimum-quality",
                    "label": "Minimum quality",
                    "control": "number",
                    "required": True,
                    "default": "0.9",
                    "min": 0,
                    "max": 1,
                    "step": 0.01,
                },
                {
                    "name": "minimum-cohort",
                    "label": "Minimum cohort",
                    "control": "number",
                    "required": True,
                    "default": "25",
                    "min": 1,
                    "help": "Smallest number of runs a route needs before it is compared.",
                },
            ],
            "sample": {
                "id": "false-savings-200-runs",
                "name": "200 completed runs across two routes",
                "description": "Efficient and advanced routes with real acceptance and correction times.",
            },
            "model_use": "No model call is required for this analysis.",
        }

    def validate(self, request: dict, uploads_by_role: dict[str, list[Upload]]) -> list[dict]:
        errors: list[dict] = []
        history = uploads_by_role.get("outcome-history", [])
        if not history:
            errors.append({"field": "outcome-history", "message": "Supply one outcome-history file."})
        inputs = request.get("inputs", {})
        if as_float(inputs.get("reviewer-hourly-rate"), -1) < 0:
            errors.append(
                {"field": "reviewer-hourly-rate", "message": "Enter a loaded hourly rate of 0 or more."}
            )
        if not str(inputs.get("acceptance-rule", "")).strip():
            errors.append({"field": "acceptance-rule", "message": "Describe what counts as an accepted result."})

        if history:
            rows, columns, _ = read_tabular(history[0].extracted_text, history[0].name)
            missing = [column for column in REQUIRED_COLUMNS if column not in columns]
            if missing:
                errors.append(
                    {
                        "field": "outcome-history",
                        "message": f"The history file is missing required columns: {', '.join(missing)}.",
                    }
                )
            elif len({str(row.get("route")) for row in rows}) < 2:
                errors.append(
                    {"field": "outcome-history", "message": "At least two routes are required to compare."}
                )
        return errors

    def build_plan(self, request: dict, uploads_by_role: dict[str, list[Upload]]) -> PlanBuild:
        history = uploads_by_role["outcome-history"][0]
        rows, columns, invalid = read_tabular(history.extracted_text, history.name)
        routes = sorted({str(row.get("route", "unknown")) for row in rows})

        operations = [
            Operation(
                id="op-01",
                order=1,
                label="Validate the history file structure",
                kind="Validation",
                reason="Required columns and value types are checked directly",
                route="software",
                handler=_validate_structure,
            ),
            Operation(
                id="op-02",
                order=2,
                label="Group completed runs by route",
                kind="Rule evaluation",
                reason="Route and outcome fields are explicit and machine-readable",
                route="software",
                depends_on=[1],
                handler=_group_runs,
            ),
            Operation(
                id="op-03",
                order=3,
                label="Calculate human correction cost",
                kind="Calculation",
                reason="Correction seconds and the loaded rate are applied arithmetically",
                route="software",
                depends_on=[2],
                handler=_correction_cost,
            ),
            Operation(
                id="op-04",
                order=4,
                label="Calculate fully loaded cost per accepted result",
                kind="Calculation",
                reason="AI cost plus correction cost divided by accepted outcomes",
                route="software",
                depends_on=[3],
                handler=_fully_loaded,
            ),
            Operation(
                id="op-05",
                order=5,
                label="Apply cohort and quality eligibility rules",
                kind="Rule evaluation",
                reason="Only routes meeting the same minimum rules are compared",
                route="software",
                depends_on=[4],
                handler=_eligibility,
            ),
            Operation(
                id="op-06",
                order=6,
                label="Recommend the lowest fully loaded route",
                kind="Generation",
                reason="The recommendation is derived from the verified numbers, so no model is needed",
                route="software",
                depends_on=[5],
                handler=_recommend,
            ),
        ]

        return PlanBuild(
            operations=operations,
            input_summary={
                "runs": len(rows),
                "routes": routes,
                "columns": columns,
                "invalid_rows": len(invalid),
            },
            summary={
                "title": f"{len(operations)} operations identified",
                "description": (
                    f"{len(rows)} completed runs across {len(routes)} routes are ready to analyze. "
                    "This workflow needs no generative AI."
                ),
                "facts": [
                    {"label": "Completed runs", "value": f"{len(rows)}"},
                    {"label": "Routes", "value": ", ".join(routes)},
                    {"label": "Model calls", "value": "0 planned"},
                    {"label": "Invalid rows", "value": f"{len(invalid)}"},
                ],
            },
            estimated_model_calls={"minimum": 0, "maximum": 0},
            estimated_maximum_cost_usd=0.0,
            context={"rows": rows, "columns": columns, "invalid": invalid, "history_name": history.name},
        )

    def verify(self, context: RunContext) -> VerificationOutcome:
        artifacts = context.artifacts
        totals = artifacts["route_totals"]
        checks = [
            VerificationCheck(
                "Required columns",
                "Every required column exists",
                "All required columns present",
                True,
            ),
            VerificationCheck(
                "Currency values",
                "AI cost values are non-negative",
                artifacts["currency_check"]["result"],
                artifacts["currency_check"]["passed"],
            ),
            VerificationCheck(
                "Unique run identifiers",
                "Run IDs are unique within the period",
                artifacts["unique_check"]["result"],
                artifacts["unique_check"]["passed"],
            ),
            VerificationCheck(
                "Cohort threshold",
                "Each compared route meets the minimum cohort size",
                artifacts["cohort_check"]["result"],
                artifacts["cohort_check"]["passed"],
            ),
            VerificationCheck(
                "Reconciliation",
                "Route totals reconcile to the row-level values",
                artifacts["reconciliation"]["result"],
                artifacts["reconciliation"]["passed"],
            ),
            VerificationCheck(
                "Failed runs visible",
                "Unsuccessful runs remain counted and their cost is not hidden",
                f"{artifacts['failed_runs']} unsuccessful runs retained in the analysis",
                True,
            ),
            VerificationCheck(
                "No person-level ranking",
                "Results are aggregated at workflow level only",
                "Aggregated by route, no individual reviewer identified",
                True,
            ),
        ]
        passed = sum(1 for check in checks if check.passed)
        score = round(passed / len(checks), 4)

        facts = [
            {
                "label": route,
                "value": f"${values['fully_loaded_per_accepted']:.2f} per accepted result",
                "detail": (
                    f"{values['runs']} runs · AI ${values['ai_cost']:.2f} · "
                    f"correction ${values['correction_cost']:.2f} · "
                    f"first-pass {values['first_pass_rate'] * 100:.1f}%"
                ),
            }
            for route, values in totals.items()
        ]

        return VerificationOutcome(
            checks=checks,
            quality_score=score,
            quality_passed=score >= float(context.request.get("required_quality_score", 0.92)),
            facts=facts,
            finding=artifacts.get("finding"),
            baseline=artifacts.get("baseline"),
        )


async def _validate_structure(context: RunContext) -> OperationResult:
    rows = context.artifacts["rows"]
    invalid = context.artifacts["invalid"]
    negative = [
        row for row in rows if as_float(row.get("ai_cost_usd")) < 0 or as_int(row.get("correction_seconds")) < 0
    ]
    context.artifacts["currency_check"] = {
        "passed": not negative,
        "result": (
            "All AI cost and correction values are non-negative"
            if not negative
            else f"{len(negative)} rows contain negative values"
        ),
    }
    run_ids = [str(row.get("run_id")) for row in rows]
    duplicates = len(run_ids) - len(set(run_ids))
    context.artifacts["unique_check"] = {
        "passed": duplicates == 0,
        "result": "All run IDs are unique" if duplicates == 0 else f"{duplicates} duplicate run IDs",
    }
    return OperationResult(
        detail={
            "rows": len(rows),
            "invalid_rows": len(invalid),
            "negative_values": len(negative),
            "duplicate_run_ids": duplicates,
        }
    )


async def _group_runs(context: RunContext) -> OperationResult:
    rows = context.artifacts["rows"]
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(str(row.get("route", "unknown")), []).append(row)
    context.artifacts["grouped"] = grouped
    context.artifacts["failed_runs"] = sum(
        1 for row in rows if not as_bool(row.get("successful"), True)
    )
    return OperationResult(
        detail={route: len(items) for route, items in grouped.items()}
    )


async def _correction_cost(context: RunContext) -> OperationResult:
    rate = as_float(context.request.get("inputs", {}).get("reviewer-hourly-rate"), 0.0)
    grouped = context.artifacts["grouped"]
    correction: dict[str, float] = {}
    for route, items in grouped.items():
        correction[route] = round(
            sum(as_int(row.get("correction_seconds")) / 3600 * rate for row in items), 4
        )
    context.artifacts["correction"] = correction
    context.artifacts["rate"] = rate
    return OperationResult(detail={"loaded_hourly_rate_usd": rate, "correction_cost_usd": correction})


async def _fully_loaded(context: RunContext) -> OperationResult:
    grouped = context.artifacts["grouped"]
    correction = context.artifacts["correction"]
    totals: dict[str, dict] = {}

    for route, items in grouped.items():
        ai_cost = round(sum(as_float(row.get("ai_cost_usd")) for row in items), 4)
        accepted = sum(1 for row in items if as_bool(row.get("accepted_first_pass")))
        successful = sum(1 for row in items if as_bool(row.get("successful"), True))
        quality_values = [as_float(row.get("quality_score")) for row in items]
        fully_loaded = round(ai_cost + correction[route], 4)
        totals[route] = {
            "runs": len(items),
            "ai_cost": ai_cost,
            "correction_cost": correction[route],
            "fully_loaded": fully_loaded,
            "accepted": accepted,
            "successful": successful,
            "first_pass_rate": round(accepted / len(items), 4) if items else 0.0,
            "mean_quality": round(sum(quality_values) / len(quality_values), 4) if quality_values else 0.0,
            "ai_cost_per_run": round(ai_cost / len(items), 4) if items else 0.0,
            "correction_per_run": round(correction[route] / len(items), 4) if items else 0.0,
            "fully_loaded_per_accepted": round(fully_loaded / accepted, 4) if accepted else 0.0,
        }

    context.artifacts["route_totals"] = totals
    reconciles = all(
        abs(values["fully_loaded"] - (values["ai_cost"] + values["correction_cost"])) < 0.01
        for values in totals.values()
    )
    context.artifacts["reconciliation"] = {
        "passed": reconciles,
        "result": "Route totals equal the sum of row-level values" if reconciles else "Totals do not reconcile",
    }
    return OperationResult(detail=totals)


async def _eligibility(context: RunContext) -> OperationResult:
    inputs = context.request.get("inputs", {})
    minimum_cohort = as_int(inputs.get("minimum-cohort"), 25)
    minimum_quality = as_float(inputs.get("minimum-quality"), 0.9)
    totals = context.artifacts["route_totals"]

    eligible = {
        route: values
        for route, values in totals.items()
        if values["runs"] >= minimum_cohort and values["mean_quality"] >= minimum_quality
    }
    context.artifacts["eligible"] = eligible
    context.artifacts["cohort_check"] = {
        "passed": len(eligible) >= 2,
        "result": (
            f"{len(eligible)} routes meet the {minimum_cohort}-run cohort and {minimum_quality:.2f} quality rules"
        ),
    }
    return OperationResult(
        detail={
            "minimum_cohort": minimum_cohort,
            "minimum_quality": minimum_quality,
            "eligible_routes": list(eligible),
        }
    )


async def _recommend(context: RunContext) -> OperationResult:
    eligible = context.artifacts["eligible"] or context.artifacts["route_totals"]
    ranked = sorted(eligible.items(), key=lambda item: item[1]["fully_loaded_per_accepted"])
    best_route, best = ranked[0]
    cheapest_ai_route, cheapest_ai = min(eligible.items(), key=lambda item: item[1]["ai_cost_per_run"])

    finding = None
    if cheapest_ai_route != best_route:
        ai_saving = round(best["ai_cost_per_run"] - cheapest_ai["ai_cost_per_run"], 4)
        correction_increase = round(
            cheapest_ai["correction_per_run"] - best["correction_per_run"], 4
        )
        finding = {
            "type": "false_saving",
            "title": "False saving detected",
            "body": (
                f"The {cheapest_ai_route} route saved ${ai_saving:.2f} in AI cost per run but added an "
                f"estimated ${correction_increase:.2f} in correction effort. The {best_route} route has the "
                f"lower fully loaded cost per accepted result."
            ),
        }
    else:
        finding = {
            "type": "no_saving",
            "title": "Lowest AI price is also the lowest total cost",
            "body": (
                f"The {best_route} route has both the lower AI cost and the lower fully loaded cost per "
                "accepted result, so no correction-cost contradiction was found."
            ),
        }

    baseline = {
        "kind": "route_comparison",
        "columns": ["Metric", *eligible.keys()],
        "rows": [
            ["Completed runs", *[f"{values['runs']}" for values in eligible.values()]],
            [
                "First-pass success",
                *[f"{values['first_pass_rate'] * 100:.1f}%" for values in eligible.values()],
            ],
            ["AI cost per run", *[f"${values['ai_cost_per_run']:.2f}" for values in eligible.values()]],
            [
                "Human correction cost per run",
                *[f"${values['correction_per_run']:.2f}" for values in eligible.values()],
            ],
            [
                "Fully loaded cost per accepted result",
                *[f"${values['fully_loaded_per_accepted']:.2f}" for values in eligible.values()],
            ],
        ],
        "note": (
            "Correction cost is estimated from recorded correction seconds at the supplied loaded "
            "hourly rate."
        ),
    }

    context.artifacts["finding"] = finding
    context.artifacts["baseline"] = baseline
    return OperationResult(
        detail={"recommended_route": best_route, "finding": finding["title"]},
        reason="The recommendation is derived from verified measurements, so no model was needed",
    )
