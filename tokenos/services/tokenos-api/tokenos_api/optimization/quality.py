from __future__ import annotations

import ast
import json
import math
import operator
import re


VERIFIER_VERSION = "optimization-verifier-v1"
SUPPORTED_GATES = {
    "same_answer_quality", "grounded_citations", "structured_output",
    "required_tests", "latency_target", "human_approval",
}


def schema_supported(schema: dict) -> bool:
    if not isinstance(schema, dict) or set(schema) - {"type", "required", "properties", "additionalProperties", "items", "enum", "maxLength"}:
        return False
    kind = schema.get("type")
    if kind not in {"object", "array", "string", "number", "integer", "boolean", "null"}:
        return False
    if "enum" in schema and not isinstance(schema["enum"], list):
        return False
    if "maxLength" in schema and (not isinstance(schema["maxLength"], int) or schema["maxLength"] < 0):
        return False
    if kind == "object":
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        return (isinstance(properties, dict) and isinstance(required, list)
                and all(isinstance(key, str) and key in properties for key in required)
                and isinstance(schema.get("additionalProperties", True), bool)
                and all(schema_supported(value) for value in properties.values()))
    if kind == "array":
        return schema_supported(schema.get("items", {}))
    return True


def matches_schema(value, schema: dict) -> bool:
    kind = schema.get("type")
    if "enum" in schema and value not in schema["enum"]:
        return False
    if kind == "object":
        if not isinstance(value, dict) or any(key not in value for key in schema.get("required", [])):
            return False
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False and any(key not in properties for key in value):
            return False
        return all(matches_schema(item, properties[key]) for key, item in value.items() if key in properties)
    if kind == "array":
        return isinstance(value, list) and all(matches_schema(item, schema["items"]) for item in value)
    if kind == "string":
        return isinstance(value, str) and len(value) <= schema.get("maxLength", 1_000_000)
    if kind == "boolean":
        return isinstance(value, bool)
    if kind in {"number", "integer"}:
        return (not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)
                and (kind == "number" or value == int(value)))
    return value is None if kind == "null" else False


def run_arithmetic_tests(item: dict) -> list[dict]:
    """Evaluate an allowlisted arithmetic AST, never execute uploaded Python."""
    payload = item.get("input", {})
    if not isinstance(payload, dict):
        raise ValueError("Arithmetic test input must be an object.")
    expression = payload.get("expression", "")
    tests = payload.get("tests")
    if not isinstance(expression, str) or len(expression) > 1000 or not isinstance(tests, list) or not 1 <= len(tests) <= 30:
        raise ValueError("The allowlisted arithmetic suite needs an expression and 1 to 30 tests.")
    tree = ast.parse(expression, mode="eval")
    if len(list(ast.walk(tree))) > 100:
        raise ValueError("Arithmetic expression is too complex.")
    operators = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
                 ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod}

    def evaluate(node, args):
        if isinstance(node, ast.Expression):
            return evaluate(node.body, args)
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            result = node.value
        elif isinstance(node, ast.Name) and node.id in args:
            result = args[node.id]
        elif isinstance(node, ast.BinOp) and type(node.op) in operators:
            result = operators[type(node.op)](evaluate(node.left, args), evaluate(node.right, args))
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            result = evaluate(node.operand, args) * (-1 if isinstance(node.op, ast.USub) else 1)
        else:
            raise ValueError("Only finite arithmetic is permitted; calls, attributes, and code execution are prohibited.")
        if type(result) not in (int, float) or not math.isfinite(result) or abs(result) > 1e15:
            raise ValueError("Arithmetic value is out of bounds.")
        return result

    results = []
    for index, test in enumerate(tests):
        if not isinstance(test, dict) or not isinstance(test.get("args"), dict) or "expected" not in test:
            raise ValueError("Each arithmetic test needs args and expected.")
        if type(test["expected"]) not in (int, float) or not math.isfinite(test["expected"]):
            raise ValueError("Arithmetic expected results must be finite numbers.")
        actual = evaluate(tree, test["args"])
        results.append({"testId": f"arithmetic-{index + 1}", "actual": actual,
                        "expected": test["expected"], "passed": actual == test["expected"]})
    return results


def local_result(item: dict) -> tuple[dict | None, dict]:
    kind, value, sources = item["taskType"], item["input"], item["context"]
    if kind == "lookup" and isinstance(value, str):
        matches = [source for source in sources if isinstance(source.get("key"), str)
                   and source["key"].strip().casefold() == value.strip().casefold()]
        if len(matches) == 1 and isinstance(matches[0].get("output"), dict):
            return dict(matches[0]["output"]), {"method": "exact_source_lookup", "sourceIds": [matches[0]["id"]]}
    if kind == "classification" and isinstance(value, str):
        matches = [source for source in sources if isinstance(source.get("terms"), list)
                   and any(isinstance(term, str) and re.search(r"\b" + re.escape(term) + r"\b", value, re.I)
                           for term in source["terms"])]
        if len(matches) == 1 and isinstance(matches[0].get("label"), str):
            return {"decision": matches[0]["label"], "citations": [matches[0]["id"]]}, {"method": "explicit_classification_rule"}
        return None, {"method": "classification_rules", "reason": "Zero or multiple labels match; interpretation is required."}
    if kind == "policy" and isinstance(value, dict):
        sources_by_id = {source["id"]: source["text"] for source in sources}
        if (value.get("chargeType") == "standard" and value.get("purchaseOrder")
                and sources_by_id.get("policy#standard") == "Standard freight with a purchase order is payable."):
            return {"decision": "payable", "citations": ["policy#standard"]}, {"method": "registered_freight_rule_v1"}
        if (value.get("chargeType") == "expedited"
                and sources_by_id.get("policy#expedited") == "Expedited delivery needs prior dispatch approval."):
            return {"decision": "payable" if value.get("approvalId") else "approval_required",
                    "citations": ["policy#expedited"]}, {"method": "registered_freight_rule_v1"}
    if kind == "code_validation":
        tests = run_arithmetic_tests(item)
        if all(test["passed"] for test in tests):
            return {"decision": "tests_passed", "citations": [source["id"] for source in sources]}, {
                "method": "allowlisted_arithmetic_tests_v1", "tests": tests}
        return None, {"method": "allowlisted_arithmetic_tests_v1", "tests": tests,
                      "reason": "An actual test failed; bounded diagnosis is required. No patch is executed."}
    return None, {"method": "local_eligibility", "reason": "No deterministic rule proves this request's required outcome."}


MAX_DECISION_WORDS = 6
MAX_DECISION_CHARACTERS = 64


def expected_result_is_verifiable(item: dict) -> bool:
    """Exact-match acceptance can only pass if the model is able to produce the value.

    That holds for a short decision value the policy defines, or for a longer string the
    model can copy verbatim out of approved context. Free prose that appears nowhere in
    context can never match exactly, so the run would spend money only to fail.
    """
    expected = str(item.get("_expectedResult") or "").strip()
    if not expected:
        return False
    if ("\n" not in expected and len(expected) <= MAX_DECISION_CHARACTERS
            and len(expected.split()) <= MAX_DECISION_WORDS):
        return True
    return any(expected in str(source.get("text") or "") for source in item.get("context") or [])


def gate_blockers(requests: list[dict], requirements: dict) -> list[str]:
    blockers = [f"Unsupported quality criterion: {name}. Register an outcome verifier before execution."
                for name in requirements["qualityRequirements"] if name not in SUPPORTED_GATES]
    if not schema_supported(requirements["outputContract"]):
        blockers.append("The output contract uses an unsupported schema construct.")
    if not requests:
        blockers.append("Representative requests are required to measure a route.")
    prompt_mode = any(item.get("promptMode") for item in requests)
    if prompt_mode:
        if "same_answer_quality" in requirements["qualityRequirements"] and not any(item.get("_expectedResult") for item in requests):
            blockers.append("same_answer_quality for a prompt requires inputs.expectedResult so TokenOS can verify the answer instead of auto-passing it.")
        if any(item.get("_expectedResult") and not expected_result_is_verifiable(item) for item in requests):
            blockers.append(
                "inputs.expectedResult is free prose that no model can be expected to reproduce word for word, so outcome "
                "acceptance could never pass and the run would spend money only to fail. Use the short decision value your "
                "policy defines, or text that appears verbatim in approved context.")
        if "required_tests" in requirements["qualityRequirements"]:
            blockers.append("required_tests is unsupported for a single prompt. Provide a workflow test adapter or remove that prompt gate.")
        if "grounded_citations" in requirements["qualityRequirements"] and any(not item.get("context") for item in requests):
            blockers.append("Grounded prompt citations require at least one approved context excerpt.")
    else:
        for item in requests:
            if not item.get("expectedOutput"):
                blockers.append(f"{item['id']}: provide representative expectedOutput for real outcome acceptance.")
            elif schema_supported(requirements["outputContract"]) and not matches_schema(item["expectedOutput"], requirements["outputContract"]):
                blockers.append(f"{item['id']}: expectedOutput does not meet the required output contract.")
            if len(json.dumps(item.get("expectedOutput"), ensure_ascii=False, separators=(",", ":"))) > requirements["maxOutputCharacters"]:
                blockers.append(f"{item['id']}: expectedOutput exceeds the protected maximum output length.")
        if "grounded_citations" in requirements["qualityRequirements"]:
            if any(not item["context"] for item in requests):
                blockers.append("Grounded citations require identified source excerpts for every representative input.")
        if "required_tests" in requirements["qualityRequirements"]:
            if any(item["taskType"] != "code_validation" for item in requests):
                blockers.append("Required tests are supported only by the allowlisted arithmetic test adapter.")
    if "latency_target" in requirements["qualityRequirements"] and not requirements.get("latencyTargetMs"):
        blockers.append("Set latencyTargetMs to verify the required latency target.")
    return blockers


def verify_output(item: dict, output: object, requirements: dict, duration_ms: float, approved: bool) -> list[dict]:
    expected = item.get("expectedOutput")
    checks = []

    def add(name: str, passed: bool, detail: str):
        checks.append({"id": name, "requestId": item["id"], "version": VERIFIER_VERSION,
                       "passed": bool(passed), "detail": detail})

    structured = matches_schema(output, requirements["outputContract"]) if schema_supported(requirements["outputContract"]) else False
    add("output_contract", structured, "Produced output is checked against the pinned contract.")
    add("output_length", len(json.dumps(output, ensure_ascii=False, separators=(",", ":"))) <= requirements["maxOutputCharacters"],
        "The same canonical JSON character limit is enforced for local, governed model, and baseline output.")
    if item.get("promptMode"):
        expected_result = item.get("_expectedResult")
        accepted = (("same_answer_quality" not in requirements["qualityRequirements"]) if not expected_result else
                    isinstance(output, dict) and (output.get("decision") == expected_result or output.get("response") == expected_result))
    else:
        accepted = isinstance(output, dict) and bool(expected) and all(
            key in output and output[key] == value for key, value in (expected or {}).items())
    add("outcome_acceptance", accepted, "Produced values, not the existence of a response, must match representative expected values.")
    for gate in requirements["qualityRequirements"]:
        if gate == "same_answer_quality":
            add(gate, accepted, "Deterministic representative expected-output comparison.")
        elif gate == "structured_output":
            add(gate, structured, "Required fields, types, and additional properties checked.")
        elif gate == "grounded_citations":
            citations = output.get("citations") if isinstance(output, dict) else None
            allowed = {source["id"] for source in item["context"]}
            passed = (isinstance(citations, list) and bool(citations)
                      and all(isinstance(citation, str) and citation in allowed for citation in citations))
            add(gate, passed, "Every citation references an allowed source and section; expected citations are also acceptance-tested.")
        elif gate == "required_tests":
            if item.get("promptMode"):
                passed = False
            else:
                try:
                    tests = run_arithmetic_tests(item) if item["taskType"] == "code_validation" else []
                    passed = bool(tests) and all(test["passed"] for test in tests)
                except (ValueError, SyntaxError, ArithmeticError, TypeError):
                    passed = False
            add(gate, passed, "The same allowlisted tests execute on both routes; diagnosis does not make a failed test pass.")
        elif gate == "latency_target":
            target = requirements.get("latencyTargetMs")
            add(gate, target is not None and duration_ms <= target, f"Measured request latency {duration_ms:.3f} ms.")
        elif gate == "human_approval":
            add(gate, approved, "Explicit human approval is preserved and recorded in Protect.")
        else:
            add(gate, False, "No registered verifier supports this criterion.")
    return checks
