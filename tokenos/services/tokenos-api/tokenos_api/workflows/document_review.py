"""Review documents against rules.

Extraction, hashing, duplicate detection, threshold matching, and citation
verification all run as regular software. A model is used only for a bounded
summary, and the advanced route only when an ambiguity survives local analysis.
"""

from __future__ import annotations

import hashlib
import json
import re

from ..comparison import CITATION_REQUIREMENT, MAX_OUTPUT_TOKENS, OUTPUT_SCHEMA_VERSION
from ..config import settings
from ..modeladapter import ModelUnavailable, model_adapter, model_available
from ..storage.uploads import Upload
from ._util import MONEY_PATTERN, usage_fields
from .base import (
    Operation,
    OperationResult,
    PlanBuild,
    RunContext,
    VerificationCheck,
    VerificationOutcome,
    WorkflowHandler,
)

LIMIT_PATTERN = re.compile(
    r"(?:maximum|max|limit|not exceed|no more than|up to|threshold)[^.$\n]{0,40}\$\s?"
    r"(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)",
    re.IGNORECASE,
)
PERCENT_CAP_PATTERN = re.compile(
    r"(?:cap|maximum|max|limit|not exceed|no more than|up to|threshold)[^.\n]{0,40}?"
    r"(\d{1,3}(?:\.\d+)?)\s*%",
    re.IGNORECASE,
)
PERCENT_APPLIED_PATTERN = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*%")
SECTION_PATTERN = re.compile(r"(?:section|clause|policy)\s+(\d{1,2}(?:\.\d+)*)\b", re.IGNORECASE)
SECTION_PREFIX_PATTERN = re.compile(r"^(?:section|clause|policy)\s+\d{1,2}(?:\.\d+)*\s*[.:\-]?\s*", re.IGNORECASE)
# Markdown heading such as "## 3. Weekend and expedited delivery".
MD_HEADING_PATTERN = re.compile(
    r"^\s*#{1,6}\s*(?:(?P<num>\d+(?:\.\d+)*)[.)]\s*)?(?P<title>\S.*?)\s*$"
)
# A bare numbered heading must look like a title: short, and with no sentence
# punctuation. This keeps numbered list items inside a section body.
PLAIN_HEADING_PATTERN = re.compile(r"^\s*(?P<num>\d+(?:\.\d+)*)[.)]\s+(?P<title>[^.$%\n]{3,60})$")
CHARGE_LINE_PATTERN = re.compile(r"^(?P<label>[^$\n]{3,80}?)\s*[:\-]?\s*\$\s?(?P<amount>[\d,]+(?:\.\d{1,2})?)", re.MULTILINE)
# An approval identifier is a token like "AP-9465", not merely the word "approval".
APPROVAL_ID_PATTERN = re.compile(r"\b[A-Z]{2,}[-\s]?\d{3,}\b")
APPROVAL_ABSENT_PATTERN = re.compile(r"(?i)\b(?:no|without|missing|lacks?|not)\b[^.]{0,40}?approv")
APPROVAL_REQUIRED_PATTERN = re.compile(
    r"(?i)(?:payable\s+only\s+when|not\s+payable\s+unless|only\s+when|requires?\b"
    r"|must\s+be\s+accompanied\s+by)"
    r"[\s\S]{0,160}?(?:approval|authorisation|authorization|written\s+exception)"
)
# "not payable unless" is a prohibition; "payable only when" leaves room for evidence.
APPROVAL_STRICT_PATTERN = re.compile(r"(?i)not\s+payable\s+unless|are\s+not\s+payable")
PAYABLE_PATTERN = re.compile(r"(?i)(?:are|is)\s+payable\b|payable\s+when\b")
DUPLICATE_RULE_PATTERN = re.compile(r"(?i)duplicat|repeats\s+the\s+same|previously\s+invoiced")
# A rule that explicitly defers to judgement cannot be settled by pattern matching.
INTERPRETATION_PATTERN = re.compile(
    r"(?i)requires?\s+interpretation|where\s+responsibility\s+is\s+contested"
    r"|matter\s+of\s+judge?ment|reasonable\s+and\s+customary"
)
# A rule written about "any charge" or "all invoices" governs charges no section names.
GENERAL_RULE_PATTERN = re.compile(r"(?i)\b(?:any|all|every|each)\b[^.]{0,40}?(?:charge|line|invoice|item|supplier)")
NON_CHARGE_LABELS = ("total", "subtotal", "amount due", "approved value", "purchase order", "balance")
LIMIT_STOPWORDS = {
    "section", "maximum", "limit", "charge", "charges", "without", "approval", "approved",
    "single", "line", "must", "payable", "per", "any", "the", "and", "with", "shipment",
}
# Words too generic to identify which policy section governs a charge.
MATCH_STOPWORDS = {
    "charge", "charges", "fee", "fees", "cost", "costs", "amount", "amounts", "must",
    "payable", "when", "with", "that", "this", "from", "they", "their", "been", "were",
    "are", "the", "and", "for", "all", "any", "per", "line", "item", "items", "service",
    "services", "supplier", "invoice", "invoiced", "total", "requested",
}


def _amount(value: str) -> float:
    return float(value.replace(",", ""))


def _words(text: str) -> set[str]:
    """Normalizes to singular so 'surcharges' and 'surcharge' match."""
    found = set()
    for word in re.findall(r"[a-z]{3,}", text.lower()):
        if len(word) > 4 and word.endswith("s") and not word.endswith("ss"):
            word = word[:-1]
        if word not in MATCH_STOPWORDS:
            found.add(word)
    return found


def _clean_label(label: str) -> str:
    """Strips markdown emphasis and table pipes so guard checks see the real label."""
    return label.strip().strip("|*#_ \t").strip()


def _parse_markdown_tables(text: str) -> list[dict[str, str]]:
    """Returns table rows as header-keyed dicts. Markdown tables are exact, so this is
    deterministic structure rather than guesswork."""
    rows: list[dict[str, str]] = []
    lines = text.splitlines()
    index = 0
    while index < len(lines) - 1:
        line = lines[index].strip()
        separator = lines[index + 1].strip()
        is_header = line.startswith("|") and line.endswith("|")
        is_separator = bool(re.fullmatch(r"\|(?:\s*:?-{2,}:?\s*\|)+", separator))
        if not (is_header and is_separator):
            index += 1
            continue

        headers = [cell.strip().lower() for cell in line.strip("|").split("|")]
        index += 2
        while index < len(lines):
            row_line = lines[index].strip()
            if not (row_line.startswith("|") and row_line.endswith("|")):
                break
            cells = [cell.strip() for cell in row_line.strip("|").split("|")]
            if len(cells) == len(headers):
                row = dict(zip(headers, cells))
                row["__raw__"] = row_line
                rows.append(row)
            index += 1
    return rows


def _column(row: dict[str, str], *candidates: str) -> str:
    for key, value in row.items():
        if key == "__raw__":
            continue
        if any(candidate in key for candidate in candidates):
            return value
    return ""


class DocumentReviewWorkflow(WorkflowHandler):
    workflow_id = "document_review"
    label = "Review documents against rules"
    # The single approved supporting string for this workflow. `short_label` in
    # definition() points at this so the card, the selected-workflow panel, and the
    # docs can never drift into separate variants.
    description = (
        "Upload records and policies. TokenOS checks what software can verify before "
        "using AI for unclear cases."
    )
    default_outcome = (
        "Review the supplied documents against the supporting policy, identify unsupported charges, "
        "cite the evidence, and produce a decision summary."
    )

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
                    "role": "business-documents",
                    "label": "Documents to review",
                    "help": "Invoices, statements, or other business documents with extractable text.",
                    "accept": ".pdf,.txt,.md,.csv",
                    "multiple": True,
                    "required": True,
                },
                {
                    "role": "governing-rules",
                    "label": "Policy, contract, or rules",
                    "help": "The approved rules the documents are checked against.",
                    "accept": ".pdf,.txt,.md,.csv",
                    "multiple": True,
                    "required": True,
                },
            ],
            "fields": [
                {
                    "name": "review-focus",
                    "label": "What should be checked?",
                    "control": "textarea",
                    "required": True,
                    "default": "Unsupported charges and missing approvals",
                    "maxLength": 500,
                },
                {
                    "name": "require-citations",
                    "label": "Require a citation for every finding",
                    "control": "checkbox",
                    "required": False,
                    "default": "true",
                },
            ],
            "sample": {
                "id": "document-review-supplier-pack",
                "name": "Supplier invoice pack and purchasing policy",
                "description": "Six invoices, two purchase orders, one policy, one duplicate, one over-limit charge, one ambiguous charge.",
            },
            "model_use": "One efficient model call to interpret contested policy ambiguity, with zero generative AI for rules, citations, or summary.",
        }

    def validate(self, request: dict, uploads_by_role: dict[str, list[Upload]]) -> list[dict]:
        errors: list[dict] = []
        if not uploads_by_role.get("business-documents"):
            errors.append({"field": "business-documents", "message": "Add at least one document to review."})
        if not uploads_by_role.get("governing-rules"):
            errors.append({"field": "governing-rules", "message": "Add at least one policy, contract, or rules file."})
        if not str(request.get("inputs", {}).get("review-focus", "")).strip():
            errors.append({"field": "review-focus", "message": "Describe what should be checked."})
        return errors

    def build_plan(self, request: dict, uploads_by_role: dict[str, list[Upload]]) -> PlanBuild:
        documents = uploads_by_role["business-documents"]
        rules = uploads_by_role["governing-rules"]
        extracted = sum(upload.extracted_character_count for upload in documents + rules)

        operations = [
            Operation("op-01", 1, "Validate file types and sizes", "Validation",
                      "Type, size, and extraction status are known file rules", "software",
                      handler=_validate_files),
            Operation("op-02", 2, "Calculate hashes and detect duplicates", "Comparison",
                      "SHA-256 digests are compared directly", "software",
                      depends_on=[1], handler=_detect_duplicates),
            Operation("op-03", 3, "Read the approved policy rules", "Retrieval",
                      "Limits, caps, approval requirements, and duplicate rules are read from the policy", "retrieval",
                      depends_on=[1], handler=_read_policy),
            Operation("op-04", 4, "Extract charges and identifiers", "Extraction",
                      "Amounts and identifiers are parsed from the extracted text", "software",
                      depends_on=[1], handler=_extract_charges),
            Operation("op-05", 5, "Evaluate charges against policy rules", "Rule evaluation",
                      "Limits, caps, approvals, and duplicates are exact checks", "software",
                      depends_on=[3, 4], handler=_match_limits),
            Operation("op-06", 6, "Resolve contested policy interpretation", "Reasoning",
                      "Tries the efficient model first, and escalates once only if the citation "
                      "confidence check fails",
                      "efficient_ai" if model_available() else "software",
                      depends_on=[5], quality_check="grounded-explanation",
                      intended_route="efficient_ai", handler=_explain_ambiguity),
            Operation("op-07", 7, "Verify citations and amounts", "Validation",
                      "Every cited amount and section is checked against extracted source text",
                      "software", depends_on=[5, 6], quality_check="citation-check",
                      handler=_verify_citations),
            Operation("op-08", 8, "Create decision summary", "Template",
                      "Formatted deterministically from verified findings",
                      "software",
                      depends_on=[7], handler=_summarize),
        ]

        maximum_calls = 1 if model_available() else 0
        return PlanBuild(
            operations=operations,
            input_summary={
                "business_documents": len(documents),
                "policy_documents": len(rules),
                "extracted_characters": extracted,
            },
            summary={
                "title": f"{len(operations)} operations identified",
                "description": (
                    f"{len(documents)} documents and {len(rules)} rule files were read locally, "
                    f"producing {extracted:,} characters of extractable text."
                ),
                "facts": [
                    {"label": "Documents", "value": f"{len(documents)} ready"},
                    {"label": "Rules", "value": f"{len(rules)} ready"},
                    {"label": "Extracted text", "value": f"{extracted:,} characters"},
                    {"label": "Model ceiling", "value": f"{maximum_calls} calls"},
                ],
            },
            estimated_model_calls={"minimum": 0, "maximum": maximum_calls},
            estimated_maximum_cost_usd=0.0,
            context={},
        )

    def verify(self, context: RunContext) -> VerificationOutcome:
        artifacts = context.artifacts
        findings = artifacts["findings"]
        citation = artifacts["citation_check"]

        checks = [
            VerificationCheck("Extraction", "Text could be read from every input",
                              artifacts["extraction_result"], artifacts["extraction_passed"]),
            VerificationCheck("Duplicate detection", "Duplicate documents and repeated charge lines are identified",
                              artifacts["duplicate_result"], True),
            VerificationCheck("Policy rules", "At least one machine-readable rule was found",
                              artifacts["policy_result"], artifacts["policy_passed"]),
            VerificationCheck("Rule coverage", "Every charge was matched to a governing policy section",
                              artifacts["coverage_result"], artifacts["coverage_passed"]),
            VerificationCheck("Findings grounded", "Every finding references an uploaded document",
                              citation["grounded_result"], citation["grounded_passed"]),
            VerificationCheck("Amounts verified", "Every stated amount exists in extracted source text",
                              citation["amount_result"], citation["amount_passed"]),
            VerificationCheck("Citations present", "Every finding cites a policy section or rule line",
                              citation["citation_result"], citation["citation_passed"]),
        ]
        passed = sum(1 for check in checks if check.passed)
        score = round(passed / len(checks), 4)

        facts = [
            {
                "label": "Items needing attention",
                "value": f"{len(findings)}",
                "detail": "Charges to reject or hold while evidence is supplied.",
            },
            {"label": "Charges reviewed", "value": f"{artifacts['charges_reviewed']}"},
            {
                "label": "Charges needing action",
                "value": f"${artifacts['amount_withheld']:,.2f}",
                "detail": "This amount includes charges to reject and charges waiting for evidence.",
            },
            {
                "label": "Recommended for payment",
                "value": f"${artifacts['amount_payable']:,.2f}",
                "detail": "This is the amount supported by the documents and policy.",
            },
        ]

        return VerificationOutcome(
            checks=checks,
            quality_score=score,
            quality_passed=score >= float(context.request.get("required_quality_score", 0.92)),
            facts=facts,
            finding={
                "type": "quality",
                "title": artifacts["summary_title"],
                "body": artifacts["summary_body"],
            },
        )


async def _validate_files(context: RunContext) -> OperationResult:
    uploads = context.uploads
    empty = [upload.name for upload in uploads if upload.extracted_character_count == 0 and upload.media_type != "application/zip"]
    context.artifacts["extraction_passed"] = not empty
    context.artifacts["extraction_result"] = (
        f"Text extracted from all {len(uploads)} files"
        if not empty
        else f"No extractable text in: {', '.join(empty)}"
    )
    return OperationResult(
        detail={
            "files": len(uploads),
            "total_bytes": sum(upload.size_bytes for upload in uploads),
            "extracted_characters": sum(upload.extracted_character_count for upload in uploads),
        }
    )


async def _detect_duplicates(context: RunContext) -> OperationResult:
    seen: dict[str, str] = {}
    duplicates: list[dict] = []
    for upload in context.uploads:
        digest = upload.sha256
        if digest in seen:
            duplicates.append({"file": upload.name, "duplicate_of": seen[digest], "sha256": digest[:16]})
        else:
            seen[digest] = upload.name

    # Near-duplicate detection on normalized text catches re-issued documents.
    text_digests: dict[str, str] = {}
    for upload in context.uploads:
        normalized = re.sub(r"\s+", " ", upload.extracted_text.lower()).strip()
        if not normalized:
            continue
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        if digest in text_digests and not any(item["file"] == upload.name for item in duplicates):
            duplicates.append(
                {"file": upload.name, "duplicate_of": text_digests[digest], "sha256": digest[:16]}
            )
        else:
            text_digests[digest] = upload.name

    context.artifacts["duplicates"] = duplicates
    context.artifacts["duplicate_count"] = len(duplicates)
    context.artifacts["duplicate_result"] = (
        f"{len(duplicates)} duplicate documents identified" if duplicates else "No duplicate documents found"
    )
    return OperationResult(detail={"duplicates": duplicates})


async def _read_policy(context: RunContext) -> OperationResult:
    """Reads rules of every machine-checkable kind, not just dollar caps. Rules are read
    per line, which keeps flat policies precise, and per section, which catches rules whose
    condition spans several lines. A policy that states a percentage cap or an approval
    requirement is still fully machine-readable."""
    rules: list[dict] = []
    limits: list[dict] = []

    def build(source: str, section: str | None, title: str, text: str,
              title_words: set[str], body_words: set[str], line_level: bool) -> list[dict]:
        base = {
            "source": source,
            "section": section,
            "title": title,
            "title_keywords": sorted(title_words),
            "keywords": sorted(body_words),
            "text": text[:400],
            "general": bool(GENERAL_RULE_PATTERN.search(text)) or not title,
            "line_level": line_level,
        }
        found: list[dict] = []
        amount_match = LIMIT_PATTERN.search(text)
        if amount_match:
            found.append({**base, "kind": "amount_limit", "limit_usd": _amount(amount_match.group(1))})
        percent_match = PERCENT_CAP_PATTERN.search(text)
        if percent_match:
            found.append({**base, "kind": "percentage_cap", "cap_percent": float(percent_match.group(1))})
        if APPROVAL_REQUIRED_PATTERN.search(text):
            found.append({**base, "kind": "approval_required",
                          "strict": bool(APPROVAL_STRICT_PATTERN.search(text))})
        if DUPLICATE_RULE_PATTERN.search(text):
            found.append({**base, "kind": "duplicate_prohibited"})
        if INTERPRETATION_PATTERN.search(text):
            found.append({**base, "kind": "requires_interpretation"})
        # A section that only states a charge is payable still governs it, so the charge is
        # covered by the policy rather than left unexplained.
        if PAYABLE_PATTERN.search(text):
            found.append({**base, "kind": "payable_condition"})
        return found

    for upload in context.role("governing-rules"):
        section_number: str | None = None
        section_title = ""
        section_body: list[str] = []
        collected: list[dict] = []
        saw_heading = False

        def flush() -> None:
            # Without a heading there is no section boundary, so a "section" rule would
            # span the whole document and match almost any charge. Line rules suffice.
            if not saw_heading:
                return
            text = " ".join(section_body).strip()
            if text:
                collected.extend(build(upload.name, section_number, section_title, text,
                                       _words(section_title), _words(text), False))

        for line in upload.extracted_text.splitlines():
            stripped = line.strip()
            heading = None
            if not stripped.startswith("|"):
                heading = MD_HEADING_PATTERN.match(line) or PLAIN_HEADING_PATTERN.match(line)
            if heading and heading.group("title"):
                flush()
                saw_heading = True
                section_number = heading.group("num") or section_number
                section_title = heading.group("title").strip("*_# ")
                section_body = [section_title]
                continue

            section_body.append(line)
            if not stripped:
                continue
            explicit = SECTION_PATTERN.search(stripped)
            if explicit and section_number is None:
                section_number = explicit.group(1)
            line_words = _words(stripped)
            collected.extend(build(upload.name, explicit.group(1) if explicit else section_number,
                                   section_title or SECTION_PREFIX_PATTERN.sub("", stripped)[:60].rstrip(" .,"),
                                   stripped, _words(section_title) or line_words, line_words, True))

        flush()

        # A line-level rule is more specific than the section-level rule it sits inside,
        # so it wins and the charge is never reported twice for the same rule.
        best: dict[tuple, dict] = {}
        for rule in collected:
            key = (rule["source"], rule["section"], rule["kind"])
            if key not in best or (rule["line_level"] and not best[key]["line_level"]):
                best[key] = rule
        for rule in best.values():
            rules.append(rule)
            if rule["kind"] == "amount_limit":
                limits.append(rule)

    by_kind: dict[str, int] = {}
    for rule in rules:
        by_kind[rule["kind"]] = by_kind.get(rule["kind"], 0) + 1

    context.artifacts["rules"] = rules
    context.artifacts["limits"] = limits
    context.artifacts["rule_kinds"] = by_kind
    context.artifacts["policy_passed"] = bool(rules)
    context.artifacts["policy_result"] = (
        f"{len(rules)} machine-readable rules read from the supplied policy "
        f"({', '.join(f'{count} {kind.replace(chr(95), chr(32))}' for kind, count in sorted(by_kind.items()))})"
        if rules
        else "No machine-readable rule was found in the supplied policy, so no charge could be evaluated"
    )
    return OperationResult(detail={"rules": rules[:20], "rule_count": len(rules), "rule_kinds": by_kind})


async def _extract_charges(context: RunContext) -> OperationResult:
    charges: list[dict] = []
    for upload in context.role("business-documents"):
        rows = _parse_markdown_tables(upload.extracted_text)
        table_charges = 0
        for row in rows:
            amount_text = _column(row, "amount", "value", "cost", "price", "total")
            money = MONEY_PATTERN.search(amount_text) if amount_text else None
            if not money:
                continue
            label = _clean_label(_column(row, "description", "detail", "item", "charge", "narrative"))
            if not label or label.lower().startswith(NON_CHARGE_LABELS):
                continue
            raw = row.get("__raw__", "")
            charges.append(
                {
                    "document": upload.name,
                    "line": _clean_label(_column(row, "line", "no", "#", "item")) or None,
                    "label": label[:80],
                    "amount_usd": _amount(money.group(0).lstrip("$").strip()),
                    "reference": _clean_label(_column(row, "reference", "ref", "shipment", "batch")) or None,
                    "note": _clean_label(_column(row, "note", "comment", "evidence", "remark")) or None,
                    "excerpt": raw.strip()[:200],
                    "context_text": raw,
                }
            )
            table_charges += 1

        if table_charges:
            continue

        # Documents without a table still get line-level parsing.
        for match in CHARGE_LINE_PATTERN.finditer(upload.extracted_text):
            label = _clean_label(match.group("label"))
            if not label or label.lower().startswith(NON_CHARGE_LABELS):
                continue
            charges.append(
                {
                    "document": upload.name,
                    "line": None,
                    "label": label[:80],
                    "amount_usd": _amount(match.group("amount")),
                    "reference": None,
                    "note": None,
                    "excerpt": match.group(0).strip()[:200],
                    "context_text": match.group(0),
                }
            )

    # Approval evidence is judged from the charge's own row, never the whole document.
    for charge in charges:
        text = charge["context_text"]
        has_id = bool(APPROVAL_ID_PATTERN.search(text))
        denies = bool(APPROVAL_ABSENT_PATTERN.search(text))
        charge["approval_id"] = APPROVAL_ID_PATTERN.search(text).group(0) if has_id and not denies else None
        charge["approved"] = bool(charge["approval_id"])
        percent = PERCENT_APPLIED_PATTERN.search(text)
        charge["percent_applied"] = float(percent.group(1)) if percent else None
        charge.pop("context_text", None)

    context.artifacts["charges"] = charges
    return OperationResult(
        detail={
            "charges_found": len(charges),
            "documents_scanned": len(context.role("business-documents")),
            "with_approval_id": sum(1 for charge in charges if charge["approved"]),
            "sample": charges[:5],
        }
    )


def _governing_rules(charge: dict, rules: list[dict]) -> list[dict]:
    """Finds the policy section that governs a charge. Heading words are weighted above
    body words because a section title names the charge type directly."""
    label_words = _words(f"{charge['label']} {charge.get('note') or ''}")
    if not label_words:
        return []

    scored: dict[str, tuple[int, list[dict]]] = {}
    for rule in rules:
        if rule["kind"] == "duplicate_prohibited":
            continue
        key = f"{rule['source']}#{rule['section']}"
        score = 2 * len(label_words & set(rule["title_keywords"])) + len(label_words & set(rule["keywords"]))
        if score <= 0:
            continue
        existing = scored.get(key)
        if existing is None:
            scored[key] = (score, [rule])
        else:
            existing[1].append(rule)

    if not scored:
        # No section names this charge, so rules written about "any charge" still apply.
        # Only one rule per kind is kept, so a charge is never reported twice for one rule.
        general: dict[str, dict] = {}
        for rule in rules:
            if not rule.get("general") or rule["kind"] == "duplicate_prohibited":
                continue
            current = general.get(rule["kind"])
            if current is None:
                general[rule["kind"]] = rule
            elif rule["kind"] == "amount_limit" and rule["limit_usd"] < current["limit_usd"]:
                general[rule["kind"]] = rule
            elif rule["line_level"] and not current["line_level"]:
                general[rule["kind"]] = rule
        return list(general.values())
    best_key = max(scored, key=lambda key: scored[key][0])
    return scored[best_key][1]


def _citation(rule: dict) -> str:
    if rule.get("section"):
        title = f" ({rule['title']})" if rule.get("title") else ""
        return f"{rule['source']} section {rule['section']}{title}"
    return rule["source"]


async def _match_limits(context: RunContext) -> OperationResult:
    charges = context.artifacts["charges"]
    rules = context.artifacts["rules"]
    findings: list[dict] = []
    ambiguous: list[dict] = []
    over_limit = 0
    unapproved = 0
    duplicate_lines = 0

    def add(charge: dict, rule: dict, text: str, recommendation: str) -> None:
        findings.append(
            {
                "document": charge["document"],
                "line": charge.get("line"),
                "finding": text,
                "amount_usd": charge["amount_usd"],
                "policy_citation": _citation(rule),
                "source_excerpt": charge["excerpt"],
                "recommendation": recommendation,
                "resolved_by": "software",
            }
        )
        # A rejection outranks a request for evidence on the same charge.
        if charge.get("outcome") != "reject":
            charge["outcome"] = recommendation
        charge["policy_citation"] = _citation(rule)
        charge["reason"] = text

    # Section 6-style duplicate rules apply across every charge, not to one section.
    duplicate_rule = next((rule for rule in rules if rule["kind"] == "duplicate_prohibited"), None)
    if duplicate_rule:
        seen: dict[tuple, dict] = {}
        for charge in charges:
            reference = (charge.get("reference") or "").strip().lower()
            if not reference:
                continue
            key = (charge["document"], reference, round(charge["amount_usd"], 2))
            if key in seen:
                first = seen[key]
                origin = f"line {first['line']}" if first.get("line") else first["label"]
                add(
                    charge,
                    duplicate_rule,
                    f"{charge['label']} of ${charge['amount_usd']:,.2f} repeats {origin} "
                    f"(same reference {charge['reference']} and amount)",
                    "reject",
                )
                duplicate_lines += 1
            else:
                seen[key] = charge

    for charge in charges:
        governing = _governing_rules(charge, rules)
        if not governing:
            ambiguous.append({**charge, "reason": "No policy section matched this charge"})
            charge["outcome"] = "unmatched"
            charge["reason"] = "No policy section matched this charge"
            continue
        flagged = False
        reported: set[str] = set()

        # A rule that defers to judgement is escalated, not guessed at. This is the
        # only path on which a model is permitted to act.
        interpretation = next((r for r in governing if r["kind"] == "requires_interpretation"), None)
        if interpretation:
            ambiguous.append({
                **charge,
                "reason": "The governing policy section defers to judgement on this charge",
                "policy_citation": _citation(interpretation),
                "rule_text": interpretation["text"],
            })
            charge["outcome"] = "needs_interpretation"
            charge["reason"] = "The governing policy section defers to judgement on this charge"
            charge["policy_citation"] = _citation(interpretation)
            continue

        for rule in governing:
            if rule["kind"] in reported:
                continue
            if rule["kind"] == "amount_limit" and charge["amount_usd"] > rule["limit_usd"]:
                add(
                    charge,
                    rule,
                    f"{charge['label']} of ${charge['amount_usd']:,.2f} exceeds the "
                    f"${rule['limit_usd']:,.2f} approved limit",
                    "reject",
                )
                over_limit += 1
                reported.add(rule["kind"])
                flagged = True
            elif rule["kind"] == "percentage_cap" and charge.get("percent_applied") is not None:
                if charge["percent_applied"] > rule["cap_percent"]:
                    add(
                        charge,
                        rule,
                        f"{charge['label']} applied at {charge['percent_applied']}% exceeds the "
                        f"{rule['cap_percent']}% cap",
                        "reject",
                    )
                    over_limit += 1
                    reported.add(rule["kind"])
                    flagged = True
            elif rule["kind"] == "approval_required" and not charge["approved"]:
                strict = bool(rule.get("strict"))
                add(
                    charge,
                    rule,
                    f"{charge['label']} of ${charge['amount_usd']:,.2f} is "
                    + (
                        "not payable without the required exception approval, which is not attached"
                        if strict
                        else "payable only with an approval reference, and none is present"
                    ),
                    "reject" if strict else "request_evidence",
                )
                unapproved += 1
                reported.add(rule["kind"])
                flagged = True

        # A duplicate is detected before this loop, so an existing decision must not be
        # overwritten — otherwise the reviewed table would contradict the findings.
        if not flagged and not charge.get("outcome"):
            charge["outcome"] = "approve"
            charge["reason"] = "Meets every rule in the governing policy section"
            charge["policy_citation"] = _citation(governing[0])

    for duplicate in context.artifacts["duplicates"]:
        findings.append(
            {
                "document": duplicate["file"],
                "line": None,
                "finding": f"Duplicate of {duplicate['duplicate_of']}",
                "amount_usd": None,
                "policy_citation": _citation(duplicate_rule) if duplicate_rule else "Duplicate-document control",
                "source_excerpt": f"sha256 {duplicate['sha256']}",
                "recommendation": "reject",
                "resolved_by": "software",
            }
        )

    withheld = sum(item["amount_usd"] or 0 for item in findings)
    total = sum(charge["amount_usd"] for charge in charges)

    context.artifacts["findings"] = findings
    context.artifacts["reviewed_charges"] = [
        {
            "document": charge["document"],
            "line": charge.get("line"),
            "label": charge["label"],
            "amount_usd": charge["amount_usd"],
            "outcome": charge.get("outcome", "approve"),
            "reason": charge.get("reason", "Meets every rule in the governing policy section"),
            "policy_citation": charge.get("policy_citation"),
            "reference": charge.get("reference"),
            "approval_id": charge.get("approval_id"),
        }
        for charge in charges
    ]
    context.artifacts["ambiguous"] = ambiguous
    context.artifacts["over_limit_count"] = over_limit
    context.artifacts["unapproved_count"] = unapproved
    context.artifacts["duplicate_line_count"] = duplicate_lines
    if duplicate_lines:
        context.artifacts["duplicate_result"] = (
            f"{context.artifacts['duplicate_count']} duplicate document(s) and "
            f"{duplicate_lines} repeated charge line(s) identified"
        )
    context.artifacts["ambiguous_count"] = len(ambiguous)
    context.artifacts["charges_reviewed"] = len(charges)
    context.artifacts["amount_withheld"] = round(withheld, 2)
    context.artifacts["amount_reviewed"] = round(total, 2)
    context.artifacts["amount_payable"] = round(total - withheld, 2)
    context.artifacts["coverage_passed"] = bool(charges) and not [
        item for item in ambiguous if item.get("reason", "").startswith("No policy section")
    ]
    context.artifacts["coverage_result"] = (
        f"All {len(charges)} charges matched a policy section"
        if context.artifacts["coverage_passed"]
        else f"{len(ambiguous)} of {len(charges)} charges matched no policy section"
    )
    return OperationResult(
        detail={
            "charges_evaluated": len(charges),
            "findings": len(findings),
            "over_limit": over_limit,
            "missing_approval": unapproved,
            "duplicate_lines": duplicate_lines,
            "ambiguous": len(ambiguous),
            "rules_applied": len(rules),
            "amount_withheld": context.artifacts["amount_withheld"],
        }
    )


def _explanation_quality(explanations: list, ambiguous: list, context: RunContext) -> dict:
    """Deterministic confidence gate applied to a model answer before it is accepted.

    The efficient model is only trusted when its answer is grounded: it must name a
    supplied document, cite a policy section, and state an amount that exists in the
    extracted source text. Failing any of these is what authorises one escalation.
    """
    document_names = {upload.name for upload in context.uploads}
    source_text = " ".join(upload.extracted_text for upload in context.uploads)
    if not explanations:
        return {"passed": False, "reason": "The efficient model returned no explanation", "grounded": 0}

    grounded = 0
    for item in explanations:
        if str(item.get("document", "")) not in document_names:
            continue
        if not str(item.get("policy_citation", "")).strip():
            continue
        if not str(item.get("explanation", "")).strip():
            continue
        amount = item.get("amount_usd")
        if amount is not None and not any(
            abs(_amount(match) - float(amount)) < 0.01 for match in MONEY_PATTERN.findall(source_text)
        ):
            continue
        grounded += 1

    expected = min(len(ambiguous), settings.ambiguous_sample_limit)
    passed = grounded >= expected and expected > 0
    return {
        "passed": passed,
        "grounded": grounded,
        "expected": expected,
        "reason": (
            "Every explanation named a supplied document, cited a policy section, and stated a "
            "verifiable amount"
            if passed
            else f"Only {grounded} of {expected} explanations met the citation confidence threshold"
        ),
    }


def _usage_record(result, route: str, why_ai: str, quality: dict | None = None) -> dict:
    """One paid call, with the governance reason it was allowed to happen."""
    return usage_fields(result, why_ai=why_ai, quality=quality)


_AMBIGUITY_SYSTEM = (
    "You explain why a charge may not be supported. Reply with JSON only, shaped as "
    '{"explanations":[{"document":"...","amount_usd":0,"explanation":"...",'
    '"policy_citation":"..."}]}. '
    f"{CITATION_REQUIREMENT} Only reference the supplied documents and thresholds. "
    f"(schema {OUTPUT_SCHEMA_VERSION})"
)


async def _explain_ambiguity(context: RunContext) -> OperationResult:
    ambiguous = context.artifacts["ambiguous"]
    context.artifacts["explanations"] = []
    context.artifacts["escalation"] = None

    if not ambiguous:
        return OperationResult(
            route="software",
            reason="Local analysis resolved every item, so no model route was used",
            detail={"ambiguous": 0, "model_calls": 0},
        )

    if not model_available():
        context.artifacts["explanations"] = [
            {
                "document": item["document"],
                "line": item.get("line"),
                "explanation": (
                    f"{item['label']} of ${item['amount_usd']:,.2f} could not be settled by rules. "
                    f"{item.get('reason', 'The governing policy section defers to judgement.')} "
                    "No model deployment is configured, so TokenOS did not answer it."
                ),
                "amount_usd": item["amount_usd"],
                "policy_citation": item.get("policy_citation", "policy"),
                "recommendation": "needs_interpretation",
                "resolved_by": "unresolved",
            }
            for item in ambiguous[:5]
        ]
        return OperationResult(
            route="software",
            reason="No model deployment is configured, so ambiguity is reported rather than explained",
            detail={
                "ambiguous": len(ambiguous),
                "model_calls": 0,
                "reported_unresolved": len(context.artifacts["explanations"]),
                "escalation": "a model route was required but unavailable",
            },
        )

    payload = {
        "review_focus": context.request.get("inputs", {}).get("review-focus", ""),
        "policy_rules": context.artifacts["rules"][:10],
        "ambiguous_charges": ambiguous[: settings.ambiguous_sample_limit],
    }
    payload_text = json.dumps(payload, default=str)
    usages: list[dict] = []
    cost = 0.0

    # Step 1: the cheapest model that could plausibly do the job goes first.
    efficient_why = (
        f"Deterministic policy checks left {len(ambiguous)} charge(s) unresolved because the "
        "governing policy section defers to judgement. The efficient model is tried before any "
        "premium model."
    )
    try:
        efficient = await model_adapter.generate(
            route="efficient_ai",
            system=_AMBIGUITY_SYSTEM,
            input_text=payload_text,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            json_response=True,
        )
    except ModelUnavailable as error:
        efficient = None
        efficient_quality = {"passed": False, "reason": f"Efficient route unavailable: {error}"}
    else:
        explanations = (efficient.parsed or {}).get("explanations", []) if efficient.parsed else []
        efficient_quality = _explanation_quality(explanations, ambiguous, context)
        cost += efficient.calculated_cost_usd
        usages.append(_usage_record(efficient, "efficient_ai", efficient_why, efficient_quality))
        if efficient_quality["passed"]:
            for item in explanations:
                item.setdefault("resolved_by", "efficient_ai")
            context.artifacts["explanations"] = explanations
            return OperationResult(
                cost_usd=cost,
                route="efficient_ai",
                reason="The efficient model met the citation confidence threshold, so no escalation was needed",
                quality=efficient_quality,
                detail={
                    "ambiguous": len(ambiguous),
                    "explanations": len(explanations),
                    "model_calls": len(usages),
                    "escalated": False,
                    "quality_check": efficient_quality,
                },
                model_usages=usages,
            )

    # Step 2: escalate exactly once, and only because the quality gate failed.
    advanced_why = (
        "Efficient model did not meet the citation confidence threshold "
        f"({efficient_quality.get('reason', 'quality check failed')}). One advanced call is "
        "authorised because the contested charge is material to the payment decision."
    )
    try:
        advanced = await model_adapter.generate(
            route="advanced_ai",
            system=_AMBIGUITY_SYSTEM,
            input_text=payload_text,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            json_response=True,
        )
    except ModelUnavailable as error:
        context.artifacts["escalation"] = advanced_why
        return OperationResult(
            cost_usd=cost,
            route="efficient_ai" if usages else "software",
            reason=f"Advanced route unavailable after the efficient attempt failed its quality check: {error}",
            detail={
                "ambiguous": len(ambiguous),
                "model_calls": len(usages),
                "escalated": False,
                "error": str(error),
                "quality_check": efficient_quality,
            },
            model_usages=usages,
        )

    explanations = (advanced.parsed or {}).get("explanations", []) if advanced.parsed else []
    advanced_quality = _explanation_quality(explanations, ambiguous, context)
    cost += advanced.calculated_cost_usd
    usages.append(_usage_record(advanced, "advanced_ai", advanced_why, advanced_quality))
    for item in explanations:
        item.setdefault("resolved_by", "advanced_ai")
    context.artifacts["explanations"] = explanations
    context.artifacts["escalation"] = advanced_why
    return OperationResult(
        cost_usd=cost,
        route="advanced_ai",
        reason="Escalated once after the efficient model failed the citation confidence check",
        quality=advanced_quality,
        detail={
            "ambiguous": len(ambiguous),
            "explanations": len(explanations),
            "model_calls": len(usages),
            "escalated": True,
            "quality_check": advanced_quality,
        },
        model_usages=usages,
    )


async def _verify_citations(context: RunContext) -> OperationResult:
    findings = list(context.artifacts["findings"])
    source_text = " ".join(upload.extracted_text for upload in context.uploads)
    document_names = {upload.name for upload in context.uploads}
    policy_names = {upload.name for upload in context.role("governing-rules")}

    # Model explanations only become findings after they survive verification.
    accepted_explanations = []
    for explanation in context.artifacts.get("explanations", []):
        document = str(explanation.get("document", ""))
        amount = explanation.get("amount_usd")
        amount_ok = amount is None or any(
            abs(_amount(match) - float(amount)) < 0.01 for match in MONEY_PATTERN.findall(source_text)
        )
        if document in document_names and amount_ok:
            accepted_explanations.append(explanation)
            findings.append(
                {
                    "document": document,
                    "line": explanation.get("line"),
                    "finding": str(explanation.get("explanation", ""))[:400],
                    "amount_usd": amount,
                    "policy_citation": str(explanation.get("policy_citation", "")) or "policy",
                    "source_excerpt": "model explanation verified against extracted text"
                    if explanation.get("resolved_by") != "unresolved"
                    else "reported unresolved; no model answer was produced",
                    "recommendation": explanation.get("recommendation", "request_evidence"),
                    "resolved_by": explanation.get("resolved_by", "advanced_ai"),
                }
            )

    grounded = [item for item in findings if item["document"] in document_names]
    with_citation = [item for item in findings if item.get("policy_citation")]
    amounts_ok = []
    for item in findings:
        if item.get("amount_usd") is None:
            amounts_ok.append(item)
            continue
        if any(abs(_amount(match) - float(item["amount_usd"])) < 0.01 for match in MONEY_PATTERN.findall(source_text)):
            amounts_ok.append(item)

    citation_check = {
        "grounded_passed": len(grounded) == len(findings),
        "grounded_result": f"{len(grounded)} of {len(findings)} findings reference an uploaded document",
        "amount_passed": len(amounts_ok) == len(findings),
        "amount_result": f"{len(amounts_ok)} of {len(findings)} stated amounts exist in extracted source text",
        "citation_passed": len(with_citation) == len(findings),
        "citation_result": f"{len(with_citation)} of {len(findings)} findings carry a citation",
        "policy_sources": sorted(policy_names),
    }
    context.artifacts["findings"] = findings
    context.artifacts["citation_check"] = citation_check
    context.artifacts["accepted_explanations"] = accepted_explanations

    return OperationResult(
        detail=citation_check,
        quality={
            "score": round(len(grounded) / len(findings), 4) if findings else 1.0,
            "required": 1.0,
            "passed": citation_check["grounded_passed"] and citation_check["amount_passed"],
            "check": "citation-check",
        },
    )


async def _summarize(context: RunContext) -> OperationResult:
    findings = context.artifacts["findings"]
    artifacts = context.artifacts
    if findings:
        parts = []
        if artifacts["duplicate_line_count"]:
            parts.append(f"{artifacts['duplicate_line_count']} duplicate charge line(s)")
        if artifacts["unapproved_count"]:
            parts.append(f"{artifacts['unapproved_count']} charge(s) missing required approval")
        if artifacts["over_limit_count"]:
            parts.append(f"{artifacts['over_limit_count']} charge(s) above an approved limit or cap")
        if artifacts["duplicate_count"]:
            parts.append(f"{artifacts['duplicate_count']} duplicate document(s)")
        reason = ", ".join(parts) if parts else "policy exceptions"
        deterministic = (
            f"{len(findings)} finding(s) across {artifacts['charges_reviewed']} charges in "
            f"{len(context.role('business-documents'))} document(s): {reason}. "
            f"${artifacts['amount_withheld']:,.2f} needs action before payment, leaving "
            f"${artifacts['amount_payable']:,.2f} recommended for payment."
        )
    else:
        deterministic = (
            f"No policy exceptions found across {artifacts['charges_reviewed']} charges in "
            f"{len(context.role('business-documents'))} document(s). All "
            f"${artifacts['amount_reviewed']:,.2f} is recommended for payment."
        )

    context.artifacts["summary_title"] = "Evidence-backed decision summary"
    context.artifacts["summary_body"] = deterministic
    return OperationResult(
        route="software",
        reason="Formatted deterministically from verified findings using regular software template (zero model tokens)",
        detail={"summary": deterministic, "model_calls": 0},
    )
