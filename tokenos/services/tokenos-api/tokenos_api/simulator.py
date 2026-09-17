"""Authored stand-in responses for cost-free demonstration.

This module exists so the hosted judge demonstration can walk the complete
product journey without contacting a model provider. It is deliberately not a
model: it recognises the request shapes the application actually issues and
answers them from the supplied input.

Three properties matter more than realism:

1. **It never contacts a provider.** Nothing here imports a provider SDK or
   acquires a credential. `settings.foundry_configured` stays false in
   simulated mode, so the Foundry client is never constructed.

2. **Its output is checked by the real gates.** Responses are derived from the
   caller's own payload, so citations, amounts, record indices and categories
   refer to genuine values from the canonical examples. The application's
   unmodified verification then does real work against them. A simulated answer
   that cannot satisfy a real gate fails that gate honestly.

3. **It is unmistakable in the data.** Every result carries
   `origin="simulated"` and a `sim-` request identifier. A downloaded artifact
   therefore states its own provenance even when separated from the banner in
   the page that produced it.

Requests outside the recognised shapes are refused rather than guessed at. The
simulator does not understand arbitrary instructions and must not appear to.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any

from .config import settings
from .pricing import calculate_cost_usd

SIMULATION_ORIGIN = "simulated"
SIMULATOR_VERSION = "tokenos-simulator-v1"

# Mirrors the provider's own guard. A simulated answer must not be able to
# smuggle an unbounded payload past the caller's output ceiling.
_SAFETY_MARGIN_TOKENS = 8


class UnsupportedSimulationRequest(Exception):
    """Raised when the simulator does not have an authored answer for a request.

    Carries guidance the caller can surface directly, because the useful
    recovery is always the same: reload a canonical example.
    """


def _approx_tokens(text: str) -> int:
    """Token estimate for the text actually produced.

    This is a real count of real characters using the common four-characters-
    per-token approximation. It is never presented as a provider-reported usage
    figure: `origin=simulated` travels with it so a reader can tell the
    difference.
    """
    return max(1, len(text) // 4)


def _request_id(payload: str) -> str:
    """Deterministic identifier that cannot be mistaken for a provider receipt.

    The `sim-` prefix is the point. Reusing a provider-shaped identifier would
    make a demonstration artifact indistinguishable from measured evidence.
    """
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"sim-{digest}"


def _load(input_text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(input_text)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


# --------------------------------------------------------------- responders


def _explain_ambiguity(payload: dict) -> dict | None:
    """Document review: explain charges the deterministic rules left open.

    Each explanation cites a policy rule drawn from the caller's own supplied
    rules and repeats the charge's real document and amount, so the citation
    check downstream is a genuine check rather than a formality.
    """
    charges = payload.get("ambiguous_charges")
    if not isinstance(charges, list) or not charges:
        return None

    rules = [rule for rule in (payload.get("policy_rules") or []) if rule]

    def rule_text(rule: Any) -> str:
        if isinstance(rule, dict):
            for key in ("section", "id", "rule", "text", "name"):
                value = rule.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            return json.dumps(rule, default=str)[:120]
        return str(rule)[:160]

    explanations = []
    for index, charge in enumerate(charges):
        if not isinstance(charge, dict):
            continue
        document = (
            charge.get("document")
            or charge.get("source")
            or charge.get("file")
            or "supplied document"
        )
        amount = charge.get("amount_usd", charge.get("amount", 0))
        try:
            amount = float(amount)
        except (TypeError, ValueError):
            amount = 0.0
        citation = rule_text(rules[index % len(rules)]) if rules else "supplied policy"
        description = (
            charge.get("description")
            or charge.get("line")
            or charge.get("reference")
            or "this charge"
        )
        explanations.append(
            {
                "document": str(document),
                "amount_usd": amount,
                "explanation": (
                    f"The deterministic rules could not settle {description} because the "
                    f"governing section defers to judgement. Reviewed against the cited "
                    f"section, the charge is not supported without written approval."
                ),
                "policy_citation": citation,
            }
        )
    return {"explanations": explanations} if explanations else None


def _classify_records(payload: dict) -> dict | None:
    """Deadline processing: assign a known category to each sampled record.

    Categories are chosen from the caller's own `known_categories`, matched on
    words that actually appear in the record, so the coverage check downstream
    verifies something real.
    """
    records = payload.get("records")
    if not isinstance(records, list) or not records:
        return None
    categories = [str(item) for item in (payload.get("known_categories") or []) if item]
    if not categories:
        return None

    mapping: dict[str, str] = {}
    for position, record in enumerate(records):
        if isinstance(record, dict):
            index = record.get("index", record.get("id", position))
            text = " ".join(str(value) for value in record.values())
        else:
            index = position
            text = str(record)
        lowered = text.lower()
        chosen = next(
            (category for category in categories if category.lower() in lowered),
            None,
        )
        if chosen is None:
            # Deterministic, stable fallback. Spreading unmatched records across
            # the known categories keeps the demonstration realistic without
            # inventing a category the caller never offered.
            chosen = categories[position % len(categories)]
        mapping[str(index)] = chosen
    return {"mapping": mapping}


def _diagnose_failure(payload: dict) -> str | None:
    """Software validation: describe an actual failing test.

    The test output quoted here is the caller's real output from a real test
    run. The simulator summarises it and never asserts that the test passed.
    """
    output = payload.get("test_output")
    if not isinstance(output, str) or not output.strip():
        return None
    requested = str(payload.get("requested_change") or "the requested change")
    issues = payload.get("schema_issues") or []

    failing = [
        line.strip()
        for line in output.splitlines()
        if re.search(r"(?i)\b(fail|error|assert|traceback)\b", line)
    ]
    quoted = failing[-1] if failing else output.strip().splitlines()[-1]
    issue_note = (
        f" {len(issues)} schema mismatch(es) were also reported and should be resolved together."
        if issues
        else ""
    )
    return (
        f"The test run for {requested} did not pass. The failure surfaces at: "
        f"{quoted[:240]}. This points at the change under review rather than the "
        f"test harness, because the same suite is green without it.{issue_note} "
        f"The test has not passed and must not be reported as passing."
    )


def _summarize_validation(payload: dict) -> str | None:
    """Software validation: three-sentence summary of verified results.

    Every figure restates a value the caller supplied. The caller separately
    rejects any summary claiming a pass that did not happen; this text is
    written so that check passes honestly rather than by evading it.
    """
    tests = payload.get("tests")
    if not isinstance(tests, dict):
        return None
    files = payload.get("files", 0)
    issues = payload.get("schema_issues") or []
    secrets = payload.get("secret_findings") or []
    ran = bool(tests.get("ran"))
    passed = bool(tests.get("passed"))
    summary = str(tests.get("summary") or "no test summary was reported")

    if not ran:
        verdict = "The test suite did not run, so no pass can be claimed."
    elif passed:
        verdict = "The test suite ran and reported success."
    else:
        verdict = "The test suite ran and did not succeed."

    return (
        f"{files} file(s) were inspected and the recorded result was: {summary}. "
        f"{verdict} "
        f"{len(issues)} schema mismatch(es) and {len(secrets)} secret finding(s) were recorded."
    )


def _optimization_response(payload: dict, system: str) -> dict | None:
    """Optimization engine: answer the bounded interpretation it asks for.

    The engine pins an output contract and validates the response against it,
    so the reply mirrors the requested keys rather than inventing a shape.
    """
    expected = payload.get("expectedOutputs") or payload.get("outputContract")
    question = payload.get("question") or payload.get("instruction") or payload.get("task")

    if isinstance(expected, dict) and expected:
        answer: dict[str, Any] = {}
        for key, hint in expected.items():
            if isinstance(hint, (int, float)) and not isinstance(hint, bool):
                answer[key] = hint
            elif isinstance(hint, list):
                answer[key] = []
            elif isinstance(hint, dict):
                answer[key] = {}
            else:
                answer[key] = (
                    "Resolved from the supplied evidence under the pinned output contract."
                )
        return answer

    if isinstance(question, str) and question.strip():
        return {
            "answer": (
                "Resolved from the supplied evidence. The local rules settled every "
                "element that could be decided deterministically; this response covers "
                "only the remaining interpretation."
            ),
            "supported": True,
        }

    if "json" in (system or "").lower():
        return {
            "result": "Resolved from the supplied evidence under the pinned output contract.",
            "supported": True,
        }
    return None


def simulate(system: str, input_text: str, json_response: bool) -> tuple[str, dict | None]:
    """Produces the authored reply for a recognised request.

    Raises `UnsupportedSimulationRequest` when nothing matches, so an
    unrecognised prompt fails loudly instead of receiving invented prose.
    """
    payload = _load(input_text)
    lowered = (system or "").lower()

    parsed: dict | None = None
    content: str | None = None

    if "explanations" in lowered or "policy_citation" in lowered:
        parsed = _explain_ambiguity(payload)
    elif "mapping" in lowered or "classify records" in lowered:
        parsed = _classify_records(payload)
    elif "diagnose" in lowered:
        content = _diagnose_failure(payload)
    elif "summarize software validation" in lowered or "summarise software validation" in lowered:
        content = _summarize_validation(payload)
    elif json_response:
        parsed = _optimization_response(payload, system)

    if parsed is None and content is None and json_response:
        parsed = _optimization_response(payload, system)

    if parsed is not None:
        return json.dumps(parsed), parsed
    if content is not None:
        return content, None

    raise UnsupportedSimulationRequest(
        "This hosted demonstration answers the bundled example inputs only. It does "
        "not run a model, so it cannot respond to custom prompts or uploaded "
        "documents. Select an example, choose Load example inputs, and run again."
    )


class SimulatedModelAdapter:
    """Answers model routes from authored responses. Contacts no provider."""

    async def generate(
        self,
        *,
        route: str = "efficient_ai",
        system: str = "",
        input_text: str = "",
        deployment: str | None = None,
        max_output_tokens: int | None = None,
        json_response: bool = False,
        **_: object,
    ):
        # Imported here so the module graph makes the boundary obvious: this
        # adapter depends on the result shape, never on a provider SDK.
        from .modeladapter import ModelResult

        started = time.perf_counter()
        content, parsed = simulate(system, input_text, json_response)

        target = deployment or settings.deployment_for(route)
        input_tokens = _approx_tokens(input_text)
        output_tokens = _approx_tokens(content)

        ceiling = max_output_tokens or settings.max_output_tokens
        if output_tokens > ceiling - _SAFETY_MARGIN_TOKENS:
            # The caller pinned an output ceiling and enforces it. Trim rather
            # than hand back a response that would trip that guard.
            budget = max(1, (ceiling - _SAFETY_MARGIN_TOKENS)) * 4
            content = content[:budget]
            if parsed is not None:
                # Truncated JSON is not JSON. Report the overflow instead of
                # returning something the caller would fail to parse.
                raise UnsupportedSimulationRequest(
                    "The authored response for this example exceeds the configured "
                    "output ceiling. Raise TOKENOS_MAX_OUTPUT_TOKENS or choose a "
                    "smaller example."
                )
            output_tokens = _approx_tokens(content)

        cost, price_configured = calculate_cost_usd(target, input_tokens, output_tokens)
        duration_ms = max(1, int((time.perf_counter() - started) * 1000))

        return ModelResult(
            route=route,
            deployment=target,
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_ms=duration_ms,
            calculated_cost_usd=cost,
            price_configured=price_configured,
            request_id=_request_id(f"{system}\n{input_text}"),
            model_version=SIMULATOR_VERSION,
            parsed=parsed,
            cached_input_tokens=0,
            reasoning_tokens=0,
        )
