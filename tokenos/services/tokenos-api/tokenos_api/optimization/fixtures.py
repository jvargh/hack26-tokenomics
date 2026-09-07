"""Synthetic inputs, not synthetic execution, token usage, or prices."""

import json
from copy import deepcopy


_FAQ = [
    {"id": "returns#window", "key": "return window", "text": "Returns are accepted within 30 days.",
     "output": {"decision": "30 days", "citations": ["returns#window"]}},
    {"id": "shipping#standard", "key": "shipping time", "text": "Standard shipping takes 3 business days.",
     "output": {"decision": "3 business days", "citations": ["shipping#standard"]}},
]


def _support() -> list[dict]:
    return [{
        "id": f"support-{index + 1}", "taskType": "lookup", "input": question,
        "context": _FAQ, "irrelevantHistory": "Earlier unrelated conversation. " * 80,
        "expectedOutput": deepcopy(_FAQ[0 if question == "return window" else 1]["output"]),
        "reuseScope": "support-public-v1", "freshnessVersion": "2026-09",
    } for index, question in enumerate(["return window", "shipping time", "return window", "return window"])]


def _policy() -> list[dict]:
    sources = [
        {"id": "policy#standard", "text": "Standard freight with a purchase order is payable."},
        {"id": "policy#expedited", "text": "Expedited delivery needs prior dispatch approval."},
        {"id": "policy#exception", "text": "Emergency medical shipments may qualify for retrospective approval only when operations confirms necessity."},
    ]
    return [
        {"id": "policy-1", "taskType": "policy", "input": {"chargeType": "standard", "purchaseOrder": "PO-1"},
         "context": sources, "expectedOutput": {"decision": "payable", "citations": ["policy#standard"]}},
        {"id": "policy-2", "taskType": "policy", "input": {"chargeType": "expedited", "approvalId": ""},
         "context": sources, "expectedOutput": {"decision": "approval_required", "citations": ["policy#expedited"]}},
        {"id": "policy-3", "taskType": "interpretation",
         "input": "Emergency medical delivery: retrospective approval is requested; operations has not confirmed necessity. Determine whether human approval remains required.",
         "context": sources, "expectedOutput": {"decision": "approval_required", "citations": ["policy#exception"]}},
    ]


def _code() -> list[dict]:
    return [
        {"id": "code-1", "taskType": "code_validation", "input": {"expression": "price * quantity",
         "tests": [{"args": {"price": 5, "quantity": 3}, "expected": 15}]},
         "context": [{"id": "tests#total", "text": "The total equals price times quantity."}],
         "expectedOutput": {"decision": "tests_passed", "citations": ["tests#total"]}},
        {"id": "code-2", "taskType": "code_validation", "input": {"expression": "subtotal - discount",
         "tests": [{"args": {"subtotal": 100, "discount": 10}, "expected": 90}]},
         "context": [{"id": "tests#discount", "text": "Discount is subtracted from subtotal."}],
         "expectedOutput": {"decision": "tests_passed", "citations": ["tests#discount"]}},
        {"id": "code-3", "taskType": "code_validation", "input": {"expression": "price + quantity",
         "tests": [{"args": {"price": 5, "quantity": 3}, "expected": 15}]},
         "context": [{"id": "tests#total", "text": "The total must equal price times quantity, not their sum. A failed test requires diagnosis, not execution of a patch."}],
         "expectedOutput": {"decision": "change_required", "citations": ["tests#total"]}},
    ]


def _classification() -> list[dict]:
    rules = [
        {"id": "labels#billing", "terms": ["invoice", "refund"], "label": "billing", "text": "Invoice and refund requests are billing."},
        {"id": "labels#technical", "terms": ["crash", "login"], "label": "technical", "text": "Crashes and login failures are technical."},
        {"id": "labels#ambiguous", "text": "Mixed payment and access concerns require interpretation of the primary unresolved issue. Use human_review when neither category alone captures the requested outcome."},
    ]
    inputs = ["invoice question", "login failed", "refund please"] * 5 + ["refund after login failed"]
    return [{
        "id": f"class-{i + 1}", "taskType": "classification", "input": text, "context": rules,
        "expectedOutput": {"decision": "human_review" if i == 15 else ("technical" if "login" in text else "billing"),
                           "citations": ["labels#ambiguous" if i == 15 else ("labels#technical" if "login" in text else "labels#billing")]},
        "reuseScope": "classification-v1", "freshnessVersion": "2026-09",
    } for i, text in enumerate(inputs)]


PROMPT_EXAMPLE_REQUIREMENTS = {
    "qualityRequirements": ["same_answer_quality", "grounded_citations", "structured_output", "latency_target"],
    "optimizationGoal": "cost_per_accepted_outcome",
    "maxModelSpendUsd": 0.05,
    "maxInputTokens": 8000,
    "maxOutputTokens": 500,
    "latencyTargetMs": 30000,
    "allowAdvancedEscalation": True,
    "maxAdvancedCalls": 1,
}


PROMPT_FIXTURES = {
    "verbose_support_reply": {
        "id": "verbose_support_reply",
        "title": "Verbose support reply with stale history",
        "description": "A customer-support prompt that repeats instructions and includes policy, shipping, and unrelated account context.",
        "badge": "Prompt sample",
        "inputs": {
            "userPrompt": (
                "Please analyze everything below very carefully, consider every prior interaction, restate the relevant policy, "
                "explain the customer's options in detail, and draft the best possible support reply. The customer asks whether "
                "a damaged kitchen mixer delivered three days ago can be replaced or refunded. Please be thorough, polite, and "
                "do not skip any part of the policy, even if some pasted material is unrelated."
            ),
            "systemInstructions": "You are a support assistant. Be accurate, cite policy sections, and keep the answer customer-safe.",
            "conversationHistory": (
                "Turn 1: Customer asked about loyalty points. Agent explained rewards.\n"
                "Turn 2: Customer asked about store hours. Agent answered.\n"
                "Turn 3: Customer repeated that the mixer arrived damaged and included order photos.\n"
                "Turn 4: Agent pasted the full return policy twice and did not decide the remedy.\n"
            ) * 6,
            "currentModel": "recommend",
            "outputFormat": "markdown",
            "desiredOutcome": "Produce a concise grounded customer reply with the applicable damaged-item remedy, citations, and the policy decision code.",
            "expectedResult": "replacement_or_refund",
            "recurringVolume": {"value": 25, "period": "week"},
        },
        "contextArtifacts": [
            {"filename": "returns-policy.md", "content": "# Damaged on arrival\nItems reported damaged within 14 days of delivery are eligible for replacement or refund after photo review. Record the decision code replacement_or_refund. Cite policy DOA-14.\n\n# Standard returns\nUnused items may be returned within 30 days. Record the decision code standard_return.\n\n# Outside the return window\nItems reported after the applicable window are not remediable. Record the decision code not_eligible."},
            {"filename": "shipping-policy.md", "content": "Standard shipping takes 3 business days. Express shipping fees are not refunded unless delivery missed the promised date."},
            {"filename": "loyalty-notes.txt", "content": "Reward points expire after twelve months. Birthday coupons cannot be combined with appliance discounts."},
        ],
    },
    "repeated_policy_lookup": {
        "id": "repeated_policy_lookup",
        "title": "Repeated policy lookup with irrelevant excerpts",
        "description": "A policy prompt with duplicated history and several artifacts where only approval rules are relevant.",
        "badge": "Prompt sample",
        "inputs": {
            "userPrompt": (
                "Review all of the following policy material, prior approvals, and conversation notes. Determine whether an "
                "expedited freight charge without a dispatch approval can be paid. Include the exact decision and cite the policy. "
                "The same instructions may appear more than once because this is copied from our current prompt template."
            ),
            "systemInstructions": "Return a compliance-safe answer. Do not approve payment unless the policy permits it.",
            "conversationHistory": (
                "Analyst: Please check expedited freight.\n"
                "Bot: I need the policy.\n"
                "Analyst: No dispatch approval ID is present.\n"
                "Bot: Repeating prior policy lookup and stale vendor notes.\n"
            ) * 8,
            "currentModel": "application",
            "outputFormat": "json",
            "desiredOutcome": "Return the payable decision for an expedited freight charge without approval, with citations.",
            "expectedResult": "approval_required",
            "recurringVolume": {"value": 100, "period": "month"},
        },
        "contextArtifacts": [
            {"filename": "freight-policy.json", "content": json.dumps({"sources": [
                {"id": "policy#expedited-no-approval",
                 "key": "expedited freight charge without a dispatch approval",
                 "text": "Expedited delivery needs prior dispatch approval before payment. Missing approval means approval_required.",
                 "output": {"decision": "approval_required", "citations": ["self"]}},
                {"id": "policy#standard",
                 "key": "standard freight with purchase order",
                 "text": "Standard freight with a purchase order is payable.",
                 "output": {"decision": "payable", "citations": ["self"]}},
            ]})},
            {"filename": "vendor-history.txt", "content": "Vendor changed remittance address in 2024. Historical dispute notes are closed and unrelated to freight approval."},
            {"filename": "stale-chat.md", "content": "Old conversation: the requester discussed office snacks, building access, and another invoice that was already paid."},
        ],
    },
}


def prompt_example(example_id: str) -> dict:
    if example_id not in PROMPT_FIXTURES:
        raise ValueError("Select a registered prompt example.")
    return deepcopy(PROMPT_FIXTURES[example_id])


def prompt_example_catalog() -> list[dict]:
    result = []
    for item in PROMPT_FIXTURES.values():
        prompt_characters = sum(len(str(item["inputs"].get(key) or "")) for key in ("userPrompt", "systemInstructions", "conversationHistory"))
        result.append({
            "id": item["id"],
            "title": item["title"],
            "description": item["description"],
            "badge": item["badge"],
            "promptCharacters": prompt_characters,
            "contextArtifacts": len(item["contextArtifacts"]),
            # The UI must be able to actually load a reproducible prompt, so the
            # bundled prompt text is returned for prefill. Its context artifacts are
            # still materialized server-side from the pinned fixture, never trusted
            # from the browser.
            "prompt": item["inputs"].get("userPrompt", ""),
            "systemInstructions": item["inputs"].get("systemInstructions", ""),
            "conversationHistory": item["inputs"].get("conversationHistory", ""),
            "desiredOutcome": item["inputs"].get("desiredOutcome", ""),
            "currentModel": item["inputs"].get("currentModel", "recommend"),
            "outputFormat": item["inputs"].get("outputFormat", "json"),
            "expectedResult": item["inputs"]["expectedResult"],
            "recurringVolume": deepcopy(item["inputs"]["recurringVolume"]),
            "requirements": deepcopy(PROMPT_EXAMPLE_REQUIREMENTS),
            "contextFilenames": [artifact["filename"] for artifact in item["contextArtifacts"]],
        })
    return result


FIXTURES = {
    "customer_assistance": ("Repeated customer-assistance prompts with reusable context", _support),
    "policy_review": ("Policy document review with one genuine interpretation exception", _policy),
    "code_validation": ("Code-change validation with a failed test requiring bounded diagnosis", _code),
    "classification": ("High-volume classification with a small ambiguous subset", _classification),
}

WORKFLOW_EXAMPLE_DEFAULTS = {
    "customer_assistance": {
        "description": "Our support assistant sends the same return and shipping policies and conversation history for every customer question.",
        "desiredOutcome": "Answer each customer question using the applicable policy, cite its source, and reuse only validated matching answers.",
        "recurringVolume": {"value": 1000, "period": "month"},
    },
    "policy_review": {
        "description": "Our freight reviewer sends every charge and the complete policy library to a model, including routine charges and an emergency-delivery exception.",
        "desiredOutcome": "Return the correct payment or approval decision for each charge, with policy citations and unresolved approval requirements preserved.",
        "recurringVolume": {"value": 250, "period": "month"},
    },
    "code_validation": {
        "description": "Our code-change assistant asks a model to inspect every arithmetic change, even when local tests can verify the result.",
        "desiredOutcome": "Run the supplied checks, report passing results accurately, and diagnose the failed calculation without claiming that diagnosis repairs the test.",
        "recurringVolume": {"value": 25, "period": "week"},
    },
    "classification": {
        "description": "Our classifier sends all support records to a model, although most match explicit billing or technical rules and only a small subset is ambiguous.",
        "desiredOutcome": "Classify each record using the supplied rules and citations, preserving human review for ambiguous mixed-category requests.",
        "recurringVolume": {"value": 10000, "period": "day"},
    },
}

WORKFLOW_SAMPLE_ANALYSIS_NOTICE = (
    "This example contains representative requests, not historical provider telemetry. "
    "Analyze builds recommendations locally; current model usage and cost remain unavailable. "
    "Choose Measure an optimized workflow to replay the requests."
)


def sample_catalog() -> list[dict]:
    return [{"id": key, "title": title, **deepcopy(WORKFLOW_EXAMPLE_DEFAULTS[key]),
             "requestCount": len(build()), "requirements": deepcopy(PROMPT_EXAMPLE_REQUIREMENTS),
             "qualityRequirements": list(PROMPT_EXAMPLE_REQUIREMENTS["qualityRequirements"]),
             "analysisNotice": WORKFLOW_SAMPLE_ANALYSIS_NOTICE,
             "badge": "Measured sample run"} for key, (title, build) in FIXTURES.items()]


def sample_requests(sample_id: str) -> list[dict]:
    if sample_id not in FIXTURES:
        raise ValueError("Select one of the four registered measured examples.")
    return deepcopy(FIXTURES[sample_id][1]())
