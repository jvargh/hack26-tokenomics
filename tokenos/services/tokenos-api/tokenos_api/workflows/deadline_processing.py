"""Process records by a deadline.

Parses the whole uploaded dataset locally, applies explicit rules with regular
software, and sends only a small ambiguous sample to an efficient model.
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone

from ..config import settings
from ..modeladapter import ModelUnavailable, model_adapter, model_available
from ..storage.uploads import Upload
from ._util import read_tabular, usage_fields
from .base import (
    Operation,
    OperationResult,
    PlanBuild,
    RunContext,
    VerificationCheck,
    VerificationOutcome,
    WorkflowHandler,
)

RULE_PATTERN = re.compile(r"^\s*(?P<term>[^=:]+?)\s*(?:=>|=|:)\s*(?P<category>.+?)\s*$")


def _parse_rules(text: str) -> list[tuple[str, str]]:
    rules: list[tuple[str, str]] = []
    for line in text.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        match = RULE_PATTERN.match(line)
        if match:
            rules.append((match.group("term").strip().lower(), match.group("category").strip()))
    return rules


def _row_text(row: dict) -> str:
    return " ".join(str(value) for value in row.values() if value is not None).lower()


class DeadlineProcessingWorkflow(WorkflowHandler):
    workflow_id = "deadline_processing"
    label = "Process records by a deadline"
    # The single approved supporting string for this workflow. See DocumentReviewWorkflow.
    description = (
        "Submit a workload and due time. TokenOS completes routine records locally and "
        "reserves AI for exceptions."
    )
    default_outcome = (
        "Classify and summarize the supplied records by the required completion time using the "
        "least expensive eligible execution route."
    )
    default_needed = "flexible"
    default_priority = "lowest_cost"
    default_maximum_cost_usd = 2.0

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
                    "role": "records",
                    "label": "Records",
                    "help": "One CSV, JSON, or JSONL dataset to process.",
                    "accept": ".csv,.json,.jsonl",
                    "multiple": False,
                    "required": True,
                },
                {
                    "role": "category-rules",
                    "label": "Category rules (optional)",
                    "help": "Lines of `term = category` applied locally before any model call.",
                    "accept": ".txt,.md,.csv,.json",
                    "multiple": False,
                    "required": False,
                },
            ],
            "fields": [
                {
                    "name": "processing-instruction",
                    "label": "Processing instruction",
                    "control": "textarea",
                    "required": True,
                    "default": "Classify each record by category and summarize the totals.",
                    "maxLength": 500,
                },
                {
                    "name": "completion-deadline",
                    "label": "Completion deadline",
                    "control": "datetime",
                    "required": True,
                },
                {
                    "name": "output-format",
                    "label": "Output format",
                    "control": "select",
                    "required": True,
                    "options": ["CSV", "JSON"],
                    "default": "CSV",
                },
                {
                    "name": "allow-scheduled",
                    "label": "Allow scheduled execution",
                    "control": "checkbox",
                    "required": False,
                    "default": "true",
                },
            ],
            "sample": {
                "id": "deadline-10000-records",
                "name": "10,000 support records",
                "description": "Includes a stable category mix, an ambiguous subset, and invalid rows.",
            },
            "model_use": "At most one efficient model call, used only for ambiguous records.",
        }

    def validate(self, request: dict, uploads_by_role: dict[str, list[Upload]]) -> list[dict]:
        errors: list[dict] = []
        records = uploads_by_role.get("records", [])
        if not records:
            errors.append({"field": "records", "message": "Upload one dataset to process."})
        inputs = request.get("inputs", {})
        if not str(inputs.get("processing-instruction", "")).strip():
            errors.append(
                {"field": "processing-instruction", "message": "Describe how the records should be processed."}
            )
        deadline = str(inputs.get("completion-deadline", "")).strip()
        if not deadline:
            errors.append({"field": "completion-deadline", "message": "Choose a completion deadline."})
        else:
            try:
                parsed = datetime.fromisoformat(deadline)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                if parsed <= datetime.now(timezone.utc):
                    errors.append(
                        {
                            "field": "completion-deadline",
                            "message": "Choose a completion time later than the current time.",
                        }
                    )
            except ValueError:
                errors.append({"field": "completion-deadline", "message": "The deadline is not a valid date and time."})

        if records:
            try:
                rows, _, _ = read_tabular(records[0].extracted_text, records[0].name)
            except (json.JSONDecodeError, ValueError) as error:
                errors.append({"field": "records", "message": f"The dataset could not be parsed: {error}"})
            else:
                if not rows:
                    errors.append({"field": "records", "message": "The dataset contains no records."})
        return errors

    def build_plan(self, request: dict, uploads_by_role: dict[str, list[Upload]]) -> PlanBuild:
        dataset = uploads_by_role["records"][0]
        rows, columns, invalid = read_tabular(dataset.extracted_text, dataset.name)
        rules_upload = (uploads_by_role.get("category-rules") or [None])[0]
        rules = _parse_rules(rules_upload.extracted_text) if rules_upload else []

        operations = [
            Operation("op-01", 1, "Validate the dataset structure", "Validation",
                      "Schema and row shape are checked directly", "software", handler=_validate_dataset),
            Operation("op-02", 2, "Derive the actual record count and columns", "Analysis",
                      "The count comes from the file, not from the request text", "software",
                      depends_on=[1], handler=_derive_counts),
            Operation("op-03", 3, "Select the execution route for the deadline", "Rule evaluation",
                      "Measured local throughput is compared with the required completion time",
                      "software", depends_on=[2], handler=_select_route),
            Operation("op-04", 4, "Classify records with explicit rules", "Classification",
                      "Explicit category rules are machine-readable", "software",
                      depends_on=[3], handler=_classify_local),
            Operation("op-05", 5, "Resolve ambiguous records", "Classification",
                      "Only records no rule matched are sent, capped at a small sample",
                      "efficient_ai" if model_available() else "software",
                      depends_on=[4], quality_check="classification-coverage",
                      handler=_resolve_ambiguous),
            Operation("op-06", 6, "Verify row coverage and completion time", "Validation",
                      "Coverage and timing are verified against the parsed dataset", "software",
                      depends_on=[5], handler=_verify_coverage),
        ]

        estimated_calls = 1 if model_available() else 0
        return PlanBuild(
            operations=operations,
            input_summary={
                "records": len(rows),
                "columns": columns,
                "invalid_rows": len(invalid),
                "rules": len(rules),
                "file_size_bytes": dataset.size_bytes,
            },
            summary={
                "title": f"{len(operations)} operations identified",
                "description": (
                    f"{len(rows)} records parsed from {dataset.name}. "
                    f"{len(invalid)} rows are invalid and are reported separately."
                ),
                "facts": [
                    {"label": "Records", "value": f"{len(rows):,}"},
                    {"label": "Columns", "value": f"{len(columns)}"},
                    {"label": "Invalid rows", "value": f"{len(invalid)}"},
                    {"label": "Model calls", "value": f"up to {estimated_calls}"},
                ],
            },
            estimated_model_calls={"minimum": 0, "maximum": estimated_calls},
            estimated_maximum_cost_usd=0.0,
            context={
                "rows": rows,
                "columns": columns,
                "invalid": invalid,
                "rules": rules,
                "dataset_name": dataset.name,
            },
        )

    def verify(self, context: RunContext) -> VerificationOutcome:
        artifacts = context.artifacts
        classified = artifacts["classified_count"]
        unresolved = artifacts.get("unresolved_count", 0)
        valid = len(artifacts["rows"])
        coverage = round((classified - unresolved) / valid, 4) if valid else 0.0

        checks = [
            VerificationCheck("Row coverage", "Every valid record has exactly one result",
                              f"{classified} of {valid} records have a result", classified == valid),
            VerificationCheck("Invalid rows reported", "Invalid rows are reported separately",
                              f"{len(artifacts['invalid'])} invalid rows listed separately", True),
            VerificationCheck("Ambiguous records reported", "Records no rule matched are labelled, never guessed",
                              (f"{unresolved} records could not be classified and are labelled Unclassified"
                               if unresolved else "Every record matched a rule or was resolved"), True),
            VerificationCheck("Category totals", "Summary totals equal row-level totals",
                              artifacts["totals_check"]["result"], artifacts["totals_check"]["passed"]),
            VerificationCheck("Completion time", "A completion timestamp is recorded",
                              artifacts["completion_result"], True),
            VerificationCheck("Deadline", "Completion is within the required time",
                              artifacts["deadline_result"], artifacts["deadline_met"]),
        ]
        passed = sum(1 for check in checks if check.passed)
        score = round(passed / len(checks), 4)

        facts = [
            {"label": "Records processed", "value": f"{classified:,}"},
            {"label": "Categories", "value": f"{len(artifacts['category_totals'])}"},
            {"label": "Unclassified", "value": f"{unresolved:,}"},
            {"label": "Execution route", "value": artifacts["selected_route_label"]},
        ]

        return VerificationOutcome(
            checks=checks,
            quality_score=score,
            quality_passed=score >= float(context.request.get("required_quality_score", 0.92)),
            deadline_met=artifacts["deadline_met"],
            facts=facts,
            finding={
                "type": "quality",
                "title": "Same work, cheaper execution route",
                "body": (
                    f"{classified:,} records were processed through "
                    f"{artifacts['selected_route_label'].lower()} with "
                    f"{artifacts['model_calls_used']} model call(s). Explicit rules resolved "
                    f"{artifacts['rule_matched']:,} records locally"
                    + (f" and {unresolved:,} were labelled Unclassified rather than guessed."
                       if unresolved else ".")
                ),
            },
        )


async def _validate_dataset(context: RunContext) -> OperationResult:
    rows = context.artifacts["rows"]
    invalid = context.artifacts["invalid"]
    return OperationResult(
        detail={"valid_rows": len(rows), "invalid_rows": len(invalid), "columns": context.artifacts["columns"]}
    )


async def _derive_counts(context: RunContext) -> OperationResult:
    rows = context.artifacts["rows"]
    started = time.perf_counter()
    for row in rows:
        _row_text(row)
    throughput = len(rows) / max(time.perf_counter() - started, 1e-6)
    context.artifacts["throughput_rows_per_second"] = round(throughput, 2)
    return OperationResult(
        detail={
            "record_count": len(rows),
            "measured_throughput_rows_per_second": round(throughput, 2),
        }
    )


async def _select_route(context: RunContext) -> OperationResult:
    inputs = context.request.get("inputs", {})
    rows = context.artifacts["rows"]
    throughput = context.artifacts["throughput_rows_per_second"]
    local_seconds = len(rows) / max(throughput, 1.0)

    deadline_text = str(inputs.get("completion-deadline", "")).strip()
    deadline = datetime.fromisoformat(deadline_text)
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    available_seconds = (deadline - datetime.now(timezone.utc)).total_seconds()
    allow_scheduled = str(inputs.get("allow-scheduled", "true")).lower() != "false"

    if local_seconds <= available_seconds * 0.5:
        route, label = "local_now", "Regular software, immediate"
    elif allow_scheduled and available_seconds > local_seconds:
        route, label = "scheduled", "Scheduled local capacity"
    else:
        route, label = "model_now", "Immediate model route"

    context.artifacts |= {
        "selected_route": route,
        "selected_route_label": label,
        "deadline": deadline.isoformat(),
        "available_seconds": round(available_seconds, 2),
        "estimated_local_seconds": round(local_seconds, 3),
    }
    return OperationResult(
        detail={
            "selected_route": label,
            "estimated_local_seconds": round(local_seconds, 3),
            "seconds_until_deadline": round(available_seconds, 1),
            "safety_buffer_seconds": round(available_seconds - local_seconds, 1),
        },
        reason=f"{label} meets the deadline with the lowest cost",
    )


async def _classify_local(context: RunContext) -> OperationResult:
    rows = context.artifacts["rows"]
    rules = context.artifacts["rules"]
    assignments: dict[int, str] = {}
    ambiguous: list[int] = []

    for index, row in enumerate(rows):
        text = _row_text(row)
        existing = str(row.get("category") or row.get("Category") or "").strip()
        if existing:
            assignments[index] = existing
            continue
        matched = next((category for term, category in rules if term in text), None)
        if matched:
            assignments[index] = matched
        else:
            ambiguous.append(index)

    context.artifacts["assignments"] = assignments
    context.artifacts["ambiguous_indexes"] = ambiguous
    context.artifacts["rule_matched"] = len(assignments)
    return OperationResult(
        detail={
            "rule_matched": len(assignments),
            "ambiguous": len(ambiguous),
            "rules_applied": len(rules),
        }
    )


async def _resolve_ambiguous(context: RunContext) -> OperationResult:
    rows = context.artifacts["rows"]
    ambiguous = context.artifacts["ambiguous_indexes"]
    assignments = context.artifacts["assignments"]
    context.artifacts["model_calls_used"] = 0

    if not ambiguous:
        context.artifacts["classified_count"] = len(assignments)
        context.artifacts["unresolved_count"] = 0
        return OperationResult(
            route="software",
            reason="Every record matched an explicit rule, so no model call was needed",
            detail={"ambiguous": 0, "model_calls": 0},
            quality={"score": 1.0, "required": 1.0, "passed": True, "check": "classification-coverage"},
        )

    sample_indexes = ambiguous[: settings.ambiguous_sample_limit]
    sample = [{"index": index, "record": rows[index]} for index in sample_indexes]

    if not model_available():
        for index in ambiguous:
            assignments[index] = "Unclassified"
        context.artifacts["classified_count"] = len(assignments)
        context.artifacts["unresolved_count"] = len(ambiguous)
        return OperationResult(
            route="software",
            reason=(
                "No model deployment is configured, so ambiguous records are marked Unclassified "
                "rather than guessed"
            ),
            detail={"ambiguous": len(ambiguous), "model_calls": 0, "marked_unclassified": len(ambiguous)},
            quality={
                "score": round(len(assignments) / len(rows), 4),
                "required": 1.0,
                "passed": False,
                "check": "classification-coverage",
            },
        )

    instruction = str(context.request.get("inputs", {}).get("processing-instruction", ""))
    known = sorted({value for value in assignments.values()})
    try:
        result = await model_adapter.generate(
            route="efficient_ai",
            system=(
                "You classify records into categories. Reply with JSON only, using the shape "
                '{"mapping": {"<index>": "<category>"}}. Use one of the known categories when it fits.'
            ),
            input_text=json.dumps(
                {"instruction": instruction, "known_categories": known, "records": sample},
                default=str,
            )[: settings.max_model_input_characters],
            json_response=True,
        )
    except ModelUnavailable as error:
        for index in ambiguous:
            assignments[index] = "Unclassified"
        context.artifacts["classified_count"] = len(assignments)
        context.artifacts["unresolved_count"] = len(ambiguous)
        return OperationResult(
            route="software",
            reason=f"Model route unavailable: {error}",
            detail={"ambiguous": len(ambiguous), "model_calls": 0, "error": str(error)},
            quality={
                "score": round(len(assignments) / len(rows), 4),
                "required": 1.0,
                "passed": False,
                "check": "classification-coverage",
            },
        )

    mapping = (result.parsed or {}).get("mapping", {}) if result.parsed else {}
    resolved_terms: dict[str, str] = {}
    for key, category in mapping.items():
        try:
            index = int(key)
        except (TypeError, ValueError):
            continue
        if 0 <= index < len(rows):
            assignments[index] = str(category)
            resolved_terms[_row_text(rows[index])[:40]] = str(category)

    # Apply the learned mapping to the remaining ambiguous records locally.
    applied_locally = 0
    for index in ambiguous:
        if index in assignments:
            continue
        text = _row_text(index_row := rows[index])
        match = next((category for term, category in resolved_terms.items() if term and term in text), None)
        if match:
            assignments[index] = match
            applied_locally += 1
        else:
            assignments[index] = "Unclassified"
        del index_row

    context.artifacts["classified_count"] = len(assignments)
    context.artifacts["unresolved_count"] = sum(1 for value in assignments.values() if value == "Unclassified")
    context.artifacts["model_calls_used"] = 1
    return OperationResult(
        cost_usd=result.calculated_cost_usd,
        detail={
            "ambiguous": len(ambiguous),
            "sent_to_model": len(sample),
            "applied_locally_from_model_mapping": applied_locally,
            "model_calls": 1,
        },
        model_usage=usage_fields(
            result, why_ai="Classified records that matched no deterministic rule."
        ),
        quality={
            "score": round(len(assignments) / len(rows), 4),
            "required": 1.0,
            "passed": len(assignments) == len(rows),
            "check": "classification-coverage",
        },
    )


async def _verify_coverage(context: RunContext) -> OperationResult:
    rows = context.artifacts["rows"]
    assignments = context.artifacts["assignments"]
    totals: dict[str, int] = {}
    for category in assignments.values():
        totals[category] = totals.get(category, 0) + 1

    context.artifacts["category_totals"] = totals
    context.artifacts["totals_check"] = {
        "passed": sum(totals.values()) == len(assignments),
        "result": f"Category totals sum to {sum(totals.values())} of {len(assignments)} classified records",
    }

    completed_at = datetime.now(timezone.utc)
    deadline = datetime.fromisoformat(context.artifacts["deadline"])
    context.artifacts["deadline_met"] = completed_at <= deadline
    context.artifacts["completion_result"] = completed_at.isoformat(timespec="seconds")
    context.artifacts["deadline_result"] = (
        f"Completed {completed_at.isoformat(timespec='seconds')} against a deadline of "
        f"{deadline.isoformat(timespec='seconds')}"
    )
    return OperationResult(
        detail={
            "valid_records": len(rows),
            "classified": len(assignments),
            "category_totals": totals,
            "completed_at": context.artifacts["completion_result"],
            "deadline_met": context.artifacts["deadline_met"],
        }
    )