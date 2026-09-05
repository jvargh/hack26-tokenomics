from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import re
import stat
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath

from fastapi import HTTPException

from ..config import settings
from .fixtures import sample_requests
from .store import tenant_id


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                                    allow_nan=False).encode()).hexdigest()


def file_metadata(filename: str, content: bytes, role: str) -> dict:
    filename = filename.replace("\\", "/").split("/")[-1]
    return {"filename": filename, "size": len(content), "sha256": hashlib.sha256(content).hexdigest(),
            "contentType": {".json": "application/json", ".jsonl": "application/x-ndjson",
                            ".csv": "text/csv", ".zip": "application/zip", ".md": "text/markdown",
                            ".txt": "text/plain"}.get(PurePosixPath(filename).suffix.lower(), "application/octet-stream"),
            "role": role}


def _decode_json(value: str) -> object:
    return json.loads(value, parse_constant=lambda constant: (_ for _ in ()).throw(ValueError("Non-finite JSON numbers are forbidden.")))


def parse_export(filename: str, content: bytes, role: str) -> list[dict | str]:
    suffix = PurePosixPath(filename.replace("\\", "/")).suffix.lower()
    allowed = {".json", ".jsonl", ".csv", ".zip"} | ({".txt", ".md"} if role == "test_inputs" else set())
    if role not in {"telemetry", "test_inputs"} or suffix not in allowed:
        raise ValueError("Use JSON, JSONL, CSV or ZIP exports; representative inputs also accept TXT and Markdown.")
    if not content or len(content) > settings.max_file_bytes:
        raise ValueError(f"File must be nonempty and at most {settings.max_file_bytes} bytes.")
    if suffix == ".zip":
        records: list = []
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            members = [member for member in archive.infolist() if not member.is_dir()]
            if not members or len(members) > settings.max_files_per_run:
                raise ValueError("ZIP contains an unsupported number of files.")
            if sum(member.file_size for member in members) > settings.max_total_bytes:
                raise ValueError("ZIP expanded contents exceed the upload limit.")
            for member in members:
                name = member.filename.replace("\\", "/")
                path = PurePosixPath(name)
                if (path.is_absolute() or ".." in path.parts or ":" in name or "\x00" in name
                        or member.flag_bits & 1 or stat.S_ISLNK(member.external_attr >> 16)
                        or path.suffix.lower() == ".zip" or member.file_size > settings.max_file_bytes):
                    raise ValueError("Unsafe, encrypted, nested, or oversized ZIP member.")
                records.extend(parse_export(name, archive.read(member), role))
                if len(records) > 100_000:
                    raise ValueError("Export contains too many records.")
        return records
    text = content.decode("utf-8-sig")
    if suffix == ".csv":
        records = []
        for row in csv.DictReader(io.StringIO(text)):
            if None in row:
                raise ValueError("CSV contains malformed columns.")
            for key, value in list(row.items()):
                if value and value.lstrip().startswith(("{", "[")):
                    row[key] = _decode_json(value)
            records.append(row)
    elif suffix == ".jsonl":
        records = [_decode_json(line) for line in text.splitlines() if line.strip()]
    elif suffix in {".txt", ".md"}:
        records = [paragraph.strip() for paragraph in text.split("\n\n") if paragraph.strip()]
    else:
        parsed = _decode_json(text)
        if isinstance(parsed, list):
            records = parsed
        elif isinstance(parsed, dict):
            # TokenOS native proof/export and the provider-neutral template.
            keys = ("requests", "representativeRequests", "inputs") if role == "test_inputs" else (
                "records", "telemetry", "modelUsage", "model_usage", "model_calls",
            )
            proof = parsed.get("proof", parsed)
            if not isinstance(proof, dict):
                raise ValueError("The native proof must be a JSON object.")
            records = next((proof[key] for key in keys if isinstance(proof.get(key), list)), None)
            if records is None:
                raise ValueError("JSON must contain an array of requests or normalized telemetry records.")
        else:
            raise ValueError("Export must contain an array of records.")
    if not records or len(records) > 100_000 or any(not isinstance(row, (dict, str)) for row in records):
        raise ValueError("Export must contain 1 to 100000 object records.")
    if role == "telemetry" and any(not isinstance(row, dict) for row in records):
        raise ValueError("Telemetry records must be objects.")
    return records


def normalize_requests(records: list) -> list[dict]:
    if not 3 <= len(records) <= 20:
        raise ValueError("Provide 3 to 20 representative requests.")
    result = []
    ids = set()
    for index, item in enumerate(records):
        row = dict(item) if isinstance(item, dict) else {"input": item}
        row["id"] = str(row.get("id", row.get("requestId", f"request-{index + 1}")))
        row["input"] = row.get("input", row.get("prompt", row.get("request")))
        if row["input"] is None or row["input"] == "":
            raise ValueError(f"Representative request {index + 1} has no input.")
        if row["id"] in ids or len(row["id"]) > 120:
            raise ValueError("Representative request IDs must be unique and at most 120 characters.")
        ids.add(row["id"])
        row["taskType"] = row.get("taskType", "interpretation")
        if row["taskType"] not in {"lookup", "classification", "policy", "code_validation", "interpretation"}:
            raise ValueError("Unsupported deterministic task type. Use interpretation for bounded model work.")
        if "expectedOutput" not in row and "expected_output" in row:
            row["expectedOutput"] = row["expected_output"]
        if isinstance(row.get("expectedOutput"), str):
            row["expectedOutput"] = {"decision": row["expectedOutput"]}
        if "expectedOutput" in row and not isinstance(row["expectedOutput"], dict):
            raise ValueError("expectedOutput must be an object or a decision string.")
        row["context"] = row.get("context", [])
        if not isinstance(row["context"], list) or any(not isinstance(source, dict) for source in row["context"]):
            raise ValueError("context must be an array of source objects with id and text.")
        if any(not isinstance(source.get("id"), str) or not isinstance(source.get("text"), str) for source in row["context"]):
            raise ValueError("Each source needs a string id and text.")
        if len({source["id"] for source in row["context"]}) != len(row["context"]):
            raise ValueError("Source identifiers must be unique within a request.")
        if len(json.dumps(row, ensure_ascii=False).encode()) > settings.max_file_bytes:
            raise ValueError("Representative request exceeds the artifact limit.")
        # Expected outputs are evaluator-only and are never included in a provider prompt.
        result.append(row)
    return result


_ALIASES = {
    "requestId": ("requestId", "request_id", "id"),
    "providerRequestId": ("providerRequestId", "provider_request_id", "request_id"),
    "timestamp": ("timestamp", "at", "created_at"),
    "deployment": ("deploymentAlias", "deployment", "model", "model_deployment"),
    "inputTokens": ("inputTokens", "input_tokens", "prompt_tokens"),
    "outputTokens": ("outputTokens", "output_tokens", "completion_tokens"),
    "cachedInputTokens": ("cachedInputTokens", "cached_input_tokens", "cached_tokens"),
    "reasoningTokens": ("reasoningTokens", "reasoning_tokens"),
    "latencyMs": ("latencyMs", "duration_ms", "latency_ms"),
    "status": ("outcomeStatus", "status", "outcome_status"),
    "retryCount": ("retryCount", "retry_count", "retries"),
    "humanCorrection": ("humanCorrection", "human_correction"),
    "application": ("application", "workflow", "workflow_id"),
    "owner": ("owner", "user", "team"),
    "promptHash": ("promptHash", "prompt_hash"),
}


def normalize_telemetry(records: list[dict]) -> list[dict]:
    normalized = []
    for source in records:
        row = {**source, **(source.get("usage", {}) if isinstance(source.get("usage"), dict) else {})}
        item = {target: next((row[key] for key in aliases if row.get(key) not in (None, "")), None)
                for target, aliases in _ALIASES.items()}
        for field in ("requestId", "providerRequestId", "deployment", "timestamp", "status"):
            if item[field] is not None:
                if not isinstance(item[field], (str, int)) or isinstance(item[field], bool):
                    raise ValueError(f"Telemetry {field} must be a textual identifier.")
                item[field] = str(item[field])
        for field in ("inputTokens", "outputTokens", "cachedInputTokens", "reasoningTokens", "latencyMs", "retryCount"):
            if item[field] is not None:
                try:
                    if isinstance(item[field], bool):
                        raise ValueError
                    number = float(item[field])
                    if not math.isfinite(number) or number < 0 or (field != "latencyMs" and number != int(number)):
                        raise ValueError
                    item[field] = int(number) if field != "latencyMs" else number
                except (TypeError, ValueError, OverflowError) as error:
                    raise ValueError(f"Telemetry {field} must be a finite nonnegative number.") from error
        if item["cachedInputTokens"] is not None and item["inputTokens"] is not None and item["cachedInputTokens"] > item["inputTokens"]:
            raise ValueError("Cached input tokens cannot exceed total input tokens.")
        if item["reasoningTokens"] is not None and item["outputTokens"] is not None and item["reasoningTokens"] > item["outputTokens"]:
            raise ValueError("Reasoning tokens cannot exceed total output tokens.")
        if not item["promptHash"] and row.get("prompt"):
            item["promptHash"] = digest(row["prompt"])
        normalized.append(item)
    return normalized


# Registered scopes are supplied by the server operator, not browser URLs or credentials.
# The bundled connection is explicitly sample data, not an Azure subscription connection.
APPLICATIONS = {
    "support-archive": {
        "id": "support-archive", "name": "Registered support archive (sample)",
        "tenant": "local", "scopes": ["telemetry", "test_inputs"],
        "scopeSummary": "Approved synthetic requests only; model execution is not permitted.",
        "fixture": "customer_assistance", "sample": True, "references": ["support-september"],
    },
}


_REGISTRY_ENV = "TOKENOS_OPTIMIZATION_APPLICATIONS_FILE"
_SCOPES = {"telemetry", "test_inputs", "model_execution"}
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,119}$")
_PATH_FIELDS = {"telemetry": "telemetryPaths", "test_inputs": "testInputPaths"}


def _config_error(message: str) -> HTTPException:
    return HTTPException(503, f"Invalid {_REGISTRY_ENV} configuration: {message}")


def _absolute_local_path(value: object) -> Path:
    if (not isinstance(value, str) or not value.strip() or "://" in value
            or value.startswith(("\\\\", "//")) or "\x00" in value):
        raise ValueError("Archive and registry paths must be absolute local file paths, not URLs or UNC paths.")
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("Archive and registry paths must be absolute local file paths without parent traversal.")
    return path


def _read_local_file(path: Path, maximum: int) -> bytes:
    # Never follow a link/junction into a different approved scope or a network
    # target. Archives are read in place, read-only, and ZIPs are never extracted.
    for component in (path, *path.parents):
        if component.is_symlink() or (hasattr(component, "is_junction") and component.is_junction()):
            raise ValueError("Registered archive paths must not traverse symlinks or junctions.")
    with path.open("rb") as source:
        if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
            raise ValueError("Registered archive paths must identify regular files.")
        content = source.read(maximum + 1)
    if not content or len(content) > maximum:
        raise ValueError(f"Registered file must be nonempty and at most {maximum} bytes.")
    return content


def _configured_scopes(value: object, field: str) -> list[str]:
    if (not isinstance(value, list) or not value or any(not isinstance(scope, str) for scope in value)
            or len(set(value)) != len(value) or set(value) - _SCOPES):
        raise ValueError(f"{field} must be a nonempty unique list of telemetry, test_inputs, or model_execution.")
    return value


def _unique_object(pairs: list[tuple]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object keys are not permitted in the registry.")
        result[key] = value
    return result


def application_registry() -> dict[str, dict]:
    """Reload operator-owned registrations; configuration errors fail closed."""
    registry = dict(APPLICATIONS)
    configured = os.getenv(_REGISTRY_ENV)
    if not configured:
        return registry
    try:
        path = _absolute_local_path(configured)
        document = json.loads(
            _read_local_file(path, min(settings.max_file_bytes, 1024 * 1024)).decode("utf-8-sig"),
            object_pairs_hook=_unique_object,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Non-finite registry values are forbidden.")),
        )
        if (not isinstance(document, dict) or set(document) - {"version", "applications"}
                or type(document.get("version", 1)) is not int or document.get("version", 1) != 1
                or not isinstance(document.get("applications"), list)
                or len(document["applications"]) > 100):
            raise ValueError("Expected {version: 1, applications: [...]} with at most 100 registrations.")
        for entry in document["applications"]:
            allowed = {"id", "name", "tenant", "adapter", "scopes", "scopeSummary", "defaultReference", "references"}
            if not isinstance(entry, dict) or set(entry) - allowed:
                raise ValueError("An application contains unknown fields; URLs, credentials, and inline records are not accepted.")
            application_id = entry.get("id")
            if not isinstance(application_id, str) or not _IDENTIFIER.fullmatch(application_id) or application_id in registry:
                raise ValueError("Application IDs must be unique identifiers and cannot shadow the bundled sample.")
            if entry.get("adapter", "normalized_archive") != "normalized_archive":
                raise ValueError(f"{application_id}: only the normalized_archive adapter is supported.")
            if any(not isinstance(entry.get(key), str) or not entry[key].strip() or len(entry[key]) > 200 for key in ("name", "tenant")):
                raise ValueError(f"{application_id}: name and tenant must be nonempty strings of at most 200 characters.")
            scopes = _configured_scopes(entry.get("scopes"), f"{application_id}.scopes")
            references = entry.get("references")
            if not isinstance(references, dict) or not 1 <= len(references) <= 100:
                raise ValueError(f"{application_id}: references must map 1 to 100 approved reference IDs to archive definitions.")
            for reference, archive in references.items():
                if not _IDENTIFIER.fullmatch(reference) or not isinstance(archive, dict) or set(archive) - {"scopes", *_PATH_FIELDS.values()}:
                    raise ValueError(f"{application_id}: invalid reference ID or archive definition.")
                reference_scopes = _configured_scopes(archive.get("scopes", scopes), f"{application_id}.{reference}.scopes")
                if set(reference_scopes) - set(scopes):
                    raise ValueError(f"{application_id}.{reference}: reference scopes cannot exceed application scopes.")
                archive["scopes"] = reference_scopes
                paths = []
                for field in _PATH_FIELDS.values():
                    values = archive.get(field, [])
                    if not isinstance(values, list):
                        raise ValueError(f"{application_id}.{reference}.{field} must be a list of absolute approved paths.")
                    archive[field] = [str(_absolute_local_path(value)) for value in values]
                    allowed_suffixes = {".json", ".jsonl", ".csv", ".zip"} | ({".txt", ".md"} if field == "testInputPaths" else set())
                    if any(Path(value).suffix.lower() not in allowed_suffixes for value in archive[field]):
                        raise ValueError(f"{application_id}.{reference}.{field} must name supported normalized archive formats.")
                    paths.extend(archive[field])
                if not paths or len(paths) > settings.max_files_per_run or len({os.path.normcase(value) for value in paths}) != len(paths):
                    raise ValueError(f"{application_id}.{reference}: supply unique approved archive paths within the per-run file limit.")
            default = entry.get("defaultReference")
            if default is not None and (not isinstance(default, str) or default not in references):
                raise ValueError(f"{application_id}: defaultReference must identify an approved reference.")
            summary = entry.get("scopeSummary", "Read-only approved local archives; execution requires separately registered model_execution scope.")
            if not isinstance(summary, str) or len(summary) > 1000:
                raise ValueError(f"{application_id}: scopeSummary must be a string of at most 1000 characters.")
            registry[application_id] = {
                "id": application_id, "name": entry["name"], "tenant": entry["tenant"],
                "adapter": "normalized_archive", "scopes": scopes, "scopeSummary": summary,
                "sample": False, "references": list(references), "defaultReference": default,
                "_archives": references,
            }
    except (OSError, UnicodeError) as error:
        raise _config_error("The registry file is missing or unreadable. Repair the operator-configured absolute local JSON path.") from error
    except (ValueError, TypeError) as error:
        raise _config_error(str(error)) from error
    return registry


def registered_application(application_id: str | None, reference: str | None = None, *, required_scope: str | None = None) -> dict | None:
    app = application_registry().get(application_id or "")
    if not app or app["tenant"] != tenant_id():
        return None
    if reference and reference not in app["references"]:
        return None
    if app.get("adapter") != "normalized_archive":
        return app if required_scope is None or required_scope in app["scopes"] else None
    selected = reference or app["defaultReference"]
    if not selected:
        if len(app["references"]) != 1:
            raise HTTPException(422, "Select an approved workflow or trace reference for this registered application.")
        selected = app["references"][0]
    scopes = list(app["_archives"][selected]["scopes"])
    if required_scope is not None and required_scope not in scopes:
        return None
    return {**app, "selectedReference": selected, "scopes": scopes}


def applications() -> list[dict]:
    return [{key: item[key] for key in ("id", "name", "scopes", "scopeSummary", "sample", "references")}
            for item in application_registry().values() if item["tenant"] == tenant_id()]


def _time_range(filters: dict) -> tuple[datetime, datetime]:
    window = filters.get("timeRange", "30d")
    if window not in {"24h", "7d", "30d", "custom"}:
        raise HTTPException(422, "Choose 24h, 7d, 30d, or a custom time range.")
    end = datetime.now(timezone.utc)
    start = end - timedelta(days={"24h": 1, "7d": 7, "30d": 30}.get(window, 30))
    if window == "custom":
        try:
            start = datetime.fromisoformat(filters["start"].replace("Z", "+00:00"))
            end = datetime.fromisoformat(filters["end"].replace("Z", "+00:00"))
            if not start.tzinfo or not end.tzinfo or start >= end:
                raise ValueError
        except (KeyError, ValueError) as error:
            raise HTTPException(422, "Custom time range requires ordered, timezone-qualified start and end.") from error
    return start, end


def _filter_telemetry(telemetry: list[dict], start: datetime, end: datetime) -> list[dict]:
    selected = []
    for row in telemetry:
        try:
            at = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
            if not at.tzinfo:
                raise ValueError
        except (KeyError, AttributeError, TypeError, ValueError) as error:
            raise HTTPException(422, "Registered telemetry needs a valid timezone-qualified timestamp on every record to enforce the selected time range.") from error
        if start <= at <= end:
            selected.append(row)
    return selected


def _archive_records(app: dict, reference: str, role: str) -> list:
    paths = app["_archives"][reference][_PATH_FIELDS[role]]
    records, expanded_size, raw_size = [], 0, 0
    for approved in paths:
        # A revocation or scope/reference change takes effect between reads, not
        # just when the browser first fetched the application selector.
        current = registered_application(app["id"], reference)
        if (not current or role not in current["scopes"]
                or approved not in current["_archives"][reference][_PATH_FIELDS[role]]):
            raise HTTPException(403, "The registered archive's tenant, reference, path, or read scope was revoked.")
        try:
            path = _absolute_local_path(approved)
            content = _read_local_file(path, settings.max_file_bytes)
            parsed = parse_export(path.name, content, role)
            raw_size += len(content)
            expanded_size += len(json.dumps(parsed, ensure_ascii=False).encode("utf-8"))
            if raw_size > settings.max_total_bytes or expanded_size > settings.max_total_bytes:
                raise ValueError("Combined registered archives exceed the per-run size limit.")
            records.extend(parsed)
        except OSError as error:
            raise HTTPException(503, f"Registered application '{app['id']}', reference '{reference}', {role} archive is missing or unreadable. Repair its operator registry entry.") from error
        except (ValueError, UnicodeError, zipfile.BadZipFile, RuntimeError, TypeError, KeyError) as error:
            raise HTTPException(422, f"Registered application '{app['id']}', reference '{reference}', {role} archive is invalid: {error}") from error
    return records


def connection(application_id: str | None, filters: dict, mode: str) -> tuple[list, list, dict]:
    if set(filters) - {"reference", "timeRange", "start", "end"}:
        raise HTTPException(422, "Only registered reference and time-range filters are accepted.")
    if mode not in {"analyze", "measure"}:
        raise HTTPException(422, "Mode must be analyze or measure.")
    app = registered_application(application_id, filters.get("reference"))
    if not app:
        raise HTTPException(403, "The registered application or reference is outside this tenant's approved scope.")
    required = "test_inputs" if mode == "measure" else "telemetry"
    if required not in app["scopes"]:
        raise HTTPException(403, f"The registered application does not permit {required} for the selected reference.")
    start, end = _time_range(filters)
    if app.get("adapter") != "normalized_archive":
        telemetry = _filter_telemetry(app.get("telemetry", []), start, end) if "telemetry" in app["scopes"] else []
        records = app["requests"] if "requests" in app else sample_requests(app["fixture"])
        return records if required == "test_inputs" else [], telemetry, app
    reference = app["selectedReference"]
    # Pin a server-selected default into the validated server request so Protect
    # checks that same reference even if the operator later changes the default.
    filters["reference"] = reference
    archive = app["_archives"][reference]
    if not archive[_PATH_FIELDS[required]]:
        raise HTTPException(422, f"The registered reference has no approved {required} archive. Repair its operator configuration.")
    telemetry = _archive_records(app, reference, "telemetry") if "telemetry" in app["scopes"] else []
    records = _archive_records(app, reference, "test_inputs") if mode == "measure" else []
    try:
        telemetry = normalize_telemetry(telemetry)
        records = normalize_requests(records) if records else []
        if len(json.dumps({"requests": records, "telemetry": telemetry}, ensure_ascii=False).encode("utf-8")) > settings.max_total_bytes:
            raise ValueError("Combined registered telemetry and test inputs exceed the per-run size limit.")
    except (ValueError, TypeError) as error:
        raise HTTPException(422, f"The registered archive does not match the normalized import contract: {error}") from error
    return records, _filter_telemetry(telemetry, start, end), app



def parse_context_artifact(filename: str, content: bytes) -> list[dict]:
    from .prompts import parse_context_artifact as parse
    return parse(filename, content)


def context_file_metadata(filename: str, content: bytes) -> dict:
    excerpts = parse_context_artifact(filename, content)
    metadata = file_metadata(filename, content, "context")
    metadata["estimatedTokens"] = sum(item["estimatedTokens"] for item in excerpts)
    metadata["excerptCount"] = len(excerpts)
    return metadata
