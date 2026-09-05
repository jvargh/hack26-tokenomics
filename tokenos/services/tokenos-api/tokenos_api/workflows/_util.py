"""Shared parsing helpers for the workflow handlers."""

from __future__ import annotations

import csv
import io
import json
import re

MONEY_PATTERN = re.compile(r"\$\s?(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)")
SECRET_PATTERNS = [
    ("AWS access key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("Private key block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("Generic API key assignment", re.compile(r"(?i)(api[_-]?key|secret|password)\s*[:=]\s*['\"][^'\"]{8,}['\"]")),
    ("Azure storage key", re.compile(r"(?i)AccountKey=[A-Za-z0-9+/=]{20,}")),
]


def parse_money(text: str) -> list[float]:
    return [float(match.replace(",", "")) for match in MONEY_PATTERN.findall(text)]


def read_tabular(text: str, name: str) -> tuple[list[dict], list[str], list[dict]]:
    """Parses CSV, JSON, or JSONL into rows, columns, and invalid-row reports."""
    stripped = text.strip()
    invalid: list[dict] = []

    if name.lower().endswith(".jsonl") or (stripped.startswith("{") and "\n{" in stripped):
        rows = []
        for number, line in enumerate(stripped.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as error:
                invalid.append({"row": number, "reason": f"Invalid JSON: {error.msg}"})
        columns = sorted({key for row in rows for key in row})
        return rows, columns, invalid

    if stripped.startswith("[") or stripped.startswith("{"):
        parsed = json.loads(stripped)
        rows = parsed if isinstance(parsed, list) else parsed.get("records", [])
        columns = sorted({key for row in rows for key in row})
        return rows, columns, invalid

    reader = csv.DictReader(io.StringIO(stripped))
    columns = list(reader.fieldnames or [])
    rows = []
    for number, row in enumerate(reader, start=2):
        if row.get(None) is not None or any(value is None for value in row.values()):
            invalid.append({"row": number, "reason": "Column count does not match the header"})
            continue
        rows.append(row)
    return rows, columns, invalid


def as_float(value, default: float = 0.0) -> float:
    try:
        return float(str(value).replace("$", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return default


def as_int(value, default: int = 0) -> int:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def as_bool(value, default: bool = False) -> bool:
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    return default


def scan_for_secrets(text: str) -> list[str]:
    return [name for name, pattern in SECRET_PATTERNS if pattern.search(text)]


def usage_fields(result, why_ai: str | None = None, quality: dict | None = None) -> dict:
    """One normalized, provider-measured record for a single paid model call.

    Shared across every workflow so `model_calls`, `input_tokens`/`output_tokens`,
    and the newer `cached_input_tokens`/`reasoning_tokens` fields are reported the
    same way everywhere the proof is assembled or rendered.
    """
    record = {
        "route": result.route,
        "deployment": result.deployment,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "cached_input_tokens": getattr(result, "cached_input_tokens", 0),
        "reasoning_tokens": getattr(result, "reasoning_tokens", 0),
        "duration_ms": result.duration_ms,
        "calculated_cost_usd": result.calculated_cost_usd,
        "price_configured": result.price_configured,
        "token_source": "model response usage",
    }
    if why_ai is not None:
        record["why_ai"] = why_ai
    if quality is not None:
        record["quality_check"] = quality
    return record
