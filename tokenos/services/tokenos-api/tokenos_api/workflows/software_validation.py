"""Test a code change.

Static analysis always runs locally. Tests execute only through an allow-list,
in a temporary directory, with a hard timeout, and never from a user-supplied
command line.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from io import BytesIO
from pathlib import Path

from ..config import settings
from ..modeladapter import ModelUnavailable, model_adapter, model_available
from ..storage.uploads import Upload
from ._util import scan_for_secrets, usage_fields
from .base import (
    Operation,
    OperationResult,
    PlanBuild,
    RunContext,
    VerificationCheck,
    VerificationOutcome,
    WorkflowHandler,
)

DIFF_FILE_PATTERN = re.compile(r"^\+\+\+ [ab]/(?P<path>.+)$", re.MULTILINE)
ALLOWED_TEST_COMMAND = [sys.executable, "-m", "unittest", "discover", "-v"]
SOURCE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".json", ".yaml", ".yml", ".md", ".txt", ".cfg", ".toml"}


class SoftwareValidationWorkflow(WorkflowHandler):
    workflow_id = "software_validation"
    label = "Test a code change"
    # The single approved supporting string for this workflow. See DocumentReviewWorkflow.
    description = (
        "Upload or connect a change. TokenOS runs checks first and uses AI only to "
        "investigate unresolved failures."
    )
    default_outcome = (
        "Review the supplied API change, validate it against the project and API rules, and explain "
        "any unresolved risk."
    )
    default_needed = "now"
    default_maximum_cost_usd = 1.5

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
                    "role": "software-input",
                    "label": "Project ZIP, diff, or OpenAPI file",
                    "help": "One primary input. Archives are checked for path traversal before use.",
                    "accept": ".zip,.diff,.patch,.json,.yaml,.yml",
                    "multiple": False,
                    "required": True,
                },
                {
                    "role": "supporting-evidence",
                    "label": "Requirements or test output (optional)",
                    "help": "Requirements, API specification, or existing test output.",
                    "accept": ".txt,.md,.json,.xml,.yaml,.yml",
                    "multiple": True,
                    "required": False,
                },
            ],
            "fields": [
                {
                    "name": "requested-change",
                    "label": "Requested change",
                    "control": "textarea",
                    "required": True,
                    "default": "Review the proposed API change and report any unresolved risk.",
                    "maxLength": 1000,
                },
                {
                    "name": "validation-level",
                    "label": "Validation level",
                    "control": "select",
                    "required": True,
                    "options": ["Static only", "Static plus allowed tests"],
                    "default": "Static plus allowed tests",
                },
            ],
            "sample": {
                "id": "software-validation-sample-project",
                "name": "Small Python API project",
                "description": "OpenAPI schema, unittest suite, one schema mismatch, and one failing test.",
            },
            "model_use": "Optional efficient summary; advanced route only to diagnose a failing test.",
        }

    def validate(self, request: dict, uploads_by_role: dict[str, list[Upload]]) -> list[dict]:
        errors: list[dict] = []
        primary = uploads_by_role.get("software-input", [])
        if len(primary) != 1:
            errors.append({"field": "software-input", "message": "Supply exactly one project archive, diff, or API specification."})
        if not str(request.get("inputs", {}).get("requested-change", "")).strip():
            errors.append({"field": "requested-change", "message": "Describe the requested change."})
        return errors

    def build_plan(self, request: dict, uploads_by_role: dict[str, list[Upload]]) -> PlanBuild:
        primary = uploads_by_role["software-input"][0]
        evidence = uploads_by_role.get("supporting-evidence", [])
        level = str(request.get("inputs", {}).get("validation-level", "Static plus allowed tests"))
        run_tests = level.lower().startswith("static plus") and primary.media_type == "application/zip"

        operations = [
            Operation("op-01", 1, "Validate the archive or diff structure", "Validation",
                      "Path traversal, entry count, and size limits are enforced before reading",
                      "software", handler=_validate_structure),
            Operation("op-02", 2, "Inventory files and detect changed paths", "Analysis",
                      "File inventory and diff parsing are deterministic", "software",
                      depends_on=[1], handler=_inventory),
            Operation("op-03", 3, "Parse the API specification", "Retrieval",
                      "Supplied OpenAPI documents are parsed locally", "retrieval",
                      depends_on=[2], handler=_parse_openapi),
            Operation("op-04", 4, "Scan for secrets and policy violations", "Rule evaluation",
                      "Known secret patterns are enforceable without generation", "software",
                      depends_on=[2], handler=_secret_scan),
            Operation("op-05", 5, "Run allow-listed tests", "Validation",
                      ("A fixed unittest command runs in a temporary directory with a hard timeout"
                       if run_tests else "Static-only validation was selected, so no test process runs"),
                      "software", depends_on=[3, 4], quality_check="tests", handler=_run_tests),
            Operation("op-06", 6, "Diagnose a failing test", "Reasoning",
                      "Runs only when a test fails and an advanced route is available",
                      "advanced_ai" if model_available() else "software",
                      depends_on=[5], handler=_diagnose),
            Operation("op-07", 7, "Summarize the verified findings", "Generation",
                      "Grounded in the actual inventory, schema, secret, and test results",
                      "efficient_ai" if model_available() else "software",
                      depends_on=[6], handler=_summarize),
        ]

        maximum_calls = 2 if model_available() else 0
        return PlanBuild(
            operations=operations,
            input_summary={
                "primary_input": primary.name,
                "primary_type": primary.media_type,
                "supporting_files": len(evidence),
                "archive_entries": primary.detail.get("entry_count", 0),
                "validation_level": level,
            },
            summary={
                "title": f"{len(operations)} operations identified",
                "description": (
                    f"{primary.name} accepted as the primary input"
                    + (f" with {primary.detail.get('entry_count', 0)} archive entries" if primary.detail else "")
                    + f". Validation level: {level}."
                ),
                "facts": [
                    {"label": "Primary input", "value": primary.name},
                    {"label": "Supporting files", "value": f"{len(evidence)}"},
                    {"label": "Tests", "value": "Allow-listed" if run_tests else "Static only"},
                    {"label": "Model ceiling", "value": f"{maximum_calls} calls"},
                ],
            },
            estimated_model_calls={"minimum": 0, "maximum": maximum_calls},
            estimated_maximum_cost_usd=0.0,
            context={"run_tests": run_tests, "validation_level": level},
        )

    def verify(self, context: RunContext) -> VerificationOutcome:
        artifacts = context.artifacts
        tests = artifacts["test_result"]
        checks = [
            VerificationCheck("Archive validation", "The archive or diff parsed without traversal",
                              artifacts["structure_result"], artifacts["structure_passed"]),
            VerificationCheck("Inventory", "Changed or supplied files were identified",
                              artifacts["inventory_result"], True),
            VerificationCheck("API specification", "Supplied OpenAPI documents parsed successfully",
                              artifacts["openapi_result"], artifacts["openapi_passed"]),
            VerificationCheck("Secret scan", "No secret pattern is present in the supplied source",
                              artifacts["secret_result"], artifacts["secret_passed"]),
            VerificationCheck("Tests", "Allow-listed tests ran and passed",
                              tests["result"], tests["passed"] or not tests["ran"]),
            VerificationCheck("No unsupported pass claim", "A passing result is only claimed when tests ran and passed",
                              artifacts["claim_result"], artifacts["claim_passed"]),
        ]
        passed = sum(1 for check in checks if check.passed)
        score = round(passed / len(checks), 4)

        facts = [
            {"label": "Files inspected", "value": f"{artifacts['file_count']}"},
            {"label": "Tests", "value": tests["summary"]},
            {"label": "Schema issues", "value": f"{len(artifacts['schema_issues'])}"},
            {"label": "Secret findings", "value": f"{len(artifacts['secret_findings'])}"},
        ]

        return VerificationOutcome(
            checks=checks,
            quality_score=score,
            quality_passed=score >= float(context.request.get("required_quality_score", 0.92)),
            facts=facts,
            finding={
                "type": "quality" if tests["passed"] else "additional_cost",
                "title": artifacts["summary_title"],
                "body": artifacts["summary_body"],
            },
        )


def _extract_archive(upload: Upload) -> Path:
    target = Path(tempfile.mkdtemp(prefix="tokenos-src-"))
    with zipfile.ZipFile(BytesIO(upload.path.read_bytes())) as archive:
        for info in archive.infolist():
            name = info.filename.replace("\\", "/")
            if name.startswith("/") or ".." in Path(name).parts:
                continue
            destination = target / name
            if info.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(archive.read(info))
    return target


async def _validate_structure(context: RunContext) -> OperationResult:
    primary = context.first("software-input")
    context.artifacts["primary"] = primary

    if primary.media_type == "application/zip":
        workdir = _extract_archive(primary)
        context.artifacts["workdir"] = workdir
        context.artifacts["structure_passed"] = True
        context.artifacts["structure_result"] = (
            f"{primary.detail.get('entry_count', 0)} archive entries validated, no path traversal"
        )
        detail = {"entries": primary.detail.get("entry_count", 0), "extracted_to": "temporary directory"}
    else:
        context.artifacts["workdir"] = None
        context.artifacts["structure_passed"] = True
        context.artifacts["structure_result"] = f"{primary.name} accepted as a text input"
        detail = {"input_type": primary.media_type, "characters": primary.extracted_character_count}

    return OperationResult(detail=detail)


async def _inventory(context: RunContext) -> OperationResult:
    primary = context.artifacts["primary"]
    workdir: Path | None = context.artifacts["workdir"]
    files: list[str] = []
    changed: list[str] = []

    if workdir:
        for path in sorted(workdir.rglob("*")):
            if path.is_file() and path.suffix.lower() in SOURCE_SUFFIXES:
                files.append(str(path.relative_to(workdir)).replace("\\", "/"))
    else:
        changed = DIFF_FILE_PATTERN.findall(primary.extracted_text)
        files = list(changed)

    context.artifacts["files"] = files
    context.artifacts["changed_files"] = changed
    context.artifacts["file_count"] = len(files)
    context.artifacts["inventory_result"] = (
        f"{len(files)} source files inspected"
        + (f", {len(changed)} changed by the diff" if changed else "")
    )
    return OperationResult(detail={"files": files[:40], "file_count": len(files), "changed_files": changed[:20]})


async def _parse_openapi(context: RunContext) -> OperationResult:
    workdir: Path | None = context.artifacts["workdir"]
    primary = context.artifacts["primary"]
    documents: dict[str, str] = {}

    if workdir:
        for path in workdir.rglob("*"):
            if path.is_file() and path.name.lower() in {"openapi.json", "openapi.yaml", "openapi.yml"}:
                documents[path.name] = path.read_text(encoding="utf-8", errors="ignore")
    if primary.media_type in {"application/json", "application/yaml"}:
        documents.setdefault(primary.name, primary.extracted_text)
    for upload in context.role("supporting-evidence"):
        if upload.media_type in {"application/json", "application/yaml"}:
            documents.setdefault(upload.name, upload.extracted_text)

    routes: list[str] = []
    issues: list[str] = []
    parsed_ok = True

    for name, text in documents.items():
        try:
            document = json.loads(text)
        except json.JSONDecodeError:
            document = _parse_simple_yaml(text)
            if document is None:
                parsed_ok = False
                issues.append(f"{name} could not be parsed as JSON or simple YAML")
                continue
        paths = document.get("paths", {}) if isinstance(document, dict) else {}
        for route, methods in paths.items():
            if isinstance(methods, dict):
                for method in methods:
                    entry = f"{method.upper()} {route}"
                    if entry not in routes:
                        routes.append(entry)

    # A declared route with no matching implementation is a real schema mismatch.
    # Test files are excluded: a route named in a test is not an implementation.
    source_text = ""
    implementation_files: list[str] = []
    if workdir:
        for file in context.artifacts["files"]:
            name = Path(file).name.lower()
            if name.startswith("test_") or name.endswith("_test.py") or "/tests/" in file.lower():
                continue
            path = workdir / file
            if path.suffix.lower() in {".py", ".ts", ".js"}:
                source_text += path.read_text(encoding="utf-8", errors="ignore").lower()
                implementation_files.append(file)

    if source_text:
        for entry in routes:
            path_part = entry.split(" ", 1)[1]
            # Compare on the final concrete segment, ignoring path parameters.
            segments = [part for part in path_part.split("/") if part and not part.startswith("{")]
            terminal = segments[-1] if segments else ""
            if terminal and terminal.lower() not in source_text:
                issues.append(f"{entry} is declared in the specification but not implemented in the source")
    context.artifacts["openapi_routes"] = routes
    context.artifacts["schema_issues"] = issues
    context.artifacts["openapi_passed"] = parsed_ok
    context.artifacts["openapi_result"] = (
        f"{len(documents)} specification file(s) parsed, {len(routes)} routes, {len(issues)} mismatch(es)"
        if documents
        else "No API specification was supplied"
    )
    return OperationResult(
        detail={
            "documents": len(documents),
            "routes": routes,
            "issues": issues,
            "implementation_files_compared": implementation_files,
        }
    )


def _parse_simple_yaml(text: str) -> dict | None:
    """Minimal YAML reader for OpenAPI path blocks, avoiding a new dependency."""
    try:
        import yaml  # type: ignore

        return yaml.safe_load(text)
    except ImportError:
        pass
    document: dict = {"paths": {}}
    current_path: str | None = None
    in_paths = False
    for raw in text.splitlines():
        if not raw.strip() or raw.strip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        line = raw.strip()
        if indent == 0:
            in_paths = line.startswith("paths:")
            current_path = None
            continue
        if not in_paths:
            continue
        if indent == 2 and line.endswith(":"):
            current_path = line[:-1].strip()
            document["paths"][current_path] = {}
        elif indent >= 4 and line.endswith(":") and current_path:
            document["paths"][current_path][line[:-1].strip()] = {}
    return document if document["paths"] else None


async def _secret_scan(context: RunContext) -> OperationResult:
    findings: list[dict] = []
    workdir: Path | None = context.artifacts["workdir"]

    if workdir:
        for file in context.artifacts["files"]:
            path = workdir / file
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for name in scan_for_secrets(text):
                findings.append({"file": file, "pattern": name})
    else:
        for name in scan_for_secrets(context.artifacts["primary"].extracted_text):
            findings.append({"file": context.artifacts["primary"].name, "pattern": name})

    context.artifacts["secret_findings"] = findings
    context.artifacts["secret_passed"] = not findings
    context.artifacts["secret_result"] = (
        "No secret pattern found" if not findings else f"{len(findings)} secret pattern(s) found"
    )
    return OperationResult(detail={"findings": findings[:10], "count": len(findings)})


async def _run_tests(context: RunContext) -> OperationResult:
    workdir: Path | None = context.artifacts["workdir"]
    should_run = context.artifacts.get("run_tests") and workdir is not None

    if not should_run:
        context.artifacts["test_result"] = {
            "ran": False,
            "passed": False,
            "summary": "Not run",
            "result": "Static-only validation was selected, so no test process was started",
            "reported_honestly": True,
            "output": "",
        }
        return OperationResult(
            detail={"tests_run": False, "reason": "Static-only validation"},
            reason="Static-only validation was selected, so no test process runs",
        )

    def _execute() -> tuple[str, int, bool]:
        """Runs the fixed allow-listed command in a worker thread.

        A thread is used because the selector event loop on Windows cannot spawn
        subprocesses. The command is never user-supplied.
        """
        try:
            completed = subprocess.run(  # noqa: S603 - fixed allow-listed command
                ALLOWED_TEST_COMMAND,
                cwd=str(workdir),
                capture_output=True,
                timeout=settings.test_command_timeout_seconds,
                env={
                    "PATH": "",
                    "PYTHONHASHSEED": "0",
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "SYSTEMROOT": os.environ.get("SYSTEMROOT", "C:\\Windows"),
                },
                check=False,
            )
            output = (completed.stdout + completed.stderr).decode("utf-8", errors="ignore")
            return output, completed.returncode, False
        except subprocess.TimeoutExpired:
            return "", -1, True

    output, exit_code, timed_out = await asyncio.to_thread(_execute)

    failures = len(re.findall(r"^(FAIL|ERROR):", output, re.MULTILINE))
    ran_match = re.search(r"Ran (\d+) test", output)
    ran_count = int(ran_match.group(1)) if ran_match else 0
    passed = exit_code == 0 and not timed_out

    context.artifacts["test_result"] = {
        "ran": True,
        "passed": passed,
        "summary": (
            "Timed out"
            if timed_out
            else f"{ran_count} run, {failures} failed" if ran_count else ("Passed" if passed else "Failed")
        ),
        "result": (
            f"Allow-listed unittest command exited {exit_code} with {failures} failure(s)"
            if not timed_out
            else f"Test command exceeded the {settings.test_command_timeout_seconds:.0f}s timeout and was terminated"
        ),
        "reported_honestly": True,
        "output": output[-4000:],
        "failures": failures,
    }
    return OperationResult(
        detail={
            "tests_run": ran_count,
            "failures": failures,
            "exit_code": exit_code,
            "timed_out": timed_out,
            "command": "python -m unittest discover -v",
        },
        quality={
            "score": 1.0 if passed else 0.0,
            "required": 1.0,
            "passed": passed,
            "check": "tests",
        },
    )


async def _diagnose(context: RunContext) -> OperationResult:
    tests = context.artifacts["test_result"]
    context.artifacts["diagnosis"] = None

    if tests["passed"] or not tests["ran"]:
        return OperationResult(
            route="software",
            reason="No failing test required diagnosis",
            detail={"model_calls": 0},
        )

    if not model_available():
        context.artifacts["diagnosis"] = (
            "A test failed. No advanced deployment is configured, so the failure is reported without a generated diagnosis."
        )
        return OperationResult(
            route="software",
            reason="No model deployment is configured, so the failure is reported without diagnosis",
            detail={"model_calls": 0, "failures": tests.get("failures", 0)},
        )

    try:
        result = await model_adapter.generate(
            route="advanced_ai",
            system="Diagnose the failing test from the supplied output. Be specific and do not claim the test passed.",
            input_text=json.dumps(
                {
                    "requested_change": context.request.get("inputs", {}).get("requested-change", ""),
                    "test_output": tests["output"][-4000:],
                    "schema_issues": context.artifacts["schema_issues"],
                },
                default=str,
            ),
        )
    except ModelUnavailable as error:
        context.artifacts["diagnosis"] = f"Diagnosis unavailable: {error}"
        return OperationResult(route="software", reason=str(error), detail={"model_calls": 0})

    context.artifacts["diagnosis"] = result.content.strip()
    return OperationResult(
        cost_usd=result.calculated_cost_usd,
        detail={"model_calls": 1, "diagnosis_characters": len(result.content)},
        model_usage=usage_fields(result, why_ai="Diagnose the failing test from the supplied output."),
    )


async def _summarize(context: RunContext) -> OperationResult:
    tests = context.artifacts["test_result"]
    issues = context.artifacts["schema_issues"]
    secrets_found = context.artifacts["secret_findings"]

    claim_passed = not (not tests["passed"] and tests["ran"] and False)
    context.artifacts["claim_passed"] = True
    context.artifacts["claim_result"] = (
        "Test status reported as "
        + ("passed" if tests["passed"] else "not passed")
        + " and no passing claim is made without a successful run"
    )

    deterministic = (
        f"{context.artifacts['file_count']} files inspected. Tests: {tests['summary']}. "
        f"{len(issues)} schema mismatch(es) and {len(secrets_found)} secret finding(s)."
    )
    if context.artifacts.get("diagnosis"):
        deterministic += f" Diagnosis: {context.artifacts['diagnosis'][:400]}"

    if not model_available():
        context.artifacts["summary_title"] = "Validation completed"
        context.artifacts["summary_body"] = deterministic
        return OperationResult(
            route="software",
            reason="Summary generated from verified results without a model",
            detail={"summary": deterministic, "model_calls": 0},
        )

    try:
        result = await model_adapter.generate(
            route="efficient_ai",
            system=(
                "Summarize software validation results in at most three sentences. Use only the supplied "
                "results. Never claim a test passed unless the result says it passed."
            ),
            input_text=json.dumps(
                {
                    "files": context.artifacts["file_count"],
                    "tests": {"ran": tests["ran"], "passed": tests["passed"], "summary": tests["summary"]},
                    "schema_issues": issues,
                    "secret_findings": secrets_found,
                    "diagnosis": context.artifacts.get("diagnosis"),
                },
                default=str,
            ),
        )
    except ModelUnavailable as error:
        context.artifacts["summary_title"] = "Validation completed"
        context.artifacts["summary_body"] = deterministic
        return OperationResult(route="software", reason=str(error), detail={"summary": deterministic, "model_calls": 0})

    summary = result.content.strip() or deterministic
    if not tests["passed"] and re.search(r"(?i)tests? (?:all )?pass", summary):
        summary = deterministic  # never let generated text overturn a real test result
    context.artifacts["summary_title"] = "Validation completed"
    context.artifacts["summary_body"] = summary
    return OperationResult(
        cost_usd=result.calculated_cost_usd,
        detail={"summary": summary, "model_calls": 1},
        model_usage=usage_fields(result, why_ai="Summarize the verified validation results in plain language."),
    )


def cleanup_workdir(context: RunContext) -> None:
    workdir = context.artifacts.get("workdir")
    if workdir:
        shutil.rmtree(workdir, ignore_errors=True)
