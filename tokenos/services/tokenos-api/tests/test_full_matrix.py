"""Full-matrix validation: every workflow against every input source.

Each case asserts the server's findings and reviewed items against values derived
by hand from the bundled inputs, so a silent regression in parsing or rule
evaluation fails loudly here.

Run with the API on 127.0.0.1:8000.
"""

from __future__ import annotations

import io
import json
import sys
import time
import zipfile
from pathlib import Path

import requests

BASE = "http://127.0.0.1:8000/api"
TERMINAL = ("completed", "completed_with_findings", "failed", "blocked", "stopped")

PASS: list[str] = []
FAIL: list[str] = []


def check(case: str, label: str, actual, expected) -> None:
    if actual == expected:
        PASS.append(f"{case} · {label}")
    else:
        FAIL.append(f"{case} · {label}: expected {expected!r}, got {actual!r}")


def check_true(case: str, label: str, condition: bool, detail: str = "") -> None:
    if condition:
        PASS.append(f"{case} · {label}")
    else:
        FAIL.append(f"{case} · {label}{': ' + detail if detail else ''}")


def upload_files(workflow_id: str, role: str, files: list[tuple[str, bytes]]) -> list[str]:
    payload = [("files", (name, io.BytesIO(raw), "application/octet-stream")) for name, raw in files]
    response = requests.post(
        f"{BASE}/uploads",
        data={"workflow_id": workflow_id, "input_role": role, "data_classification": "internal"},
        files=payload,
    )
    response.raise_for_status()
    return [item["upload_id"] for item in response.json()["uploads"]]


def sample_uploads(workflow_id: str) -> dict[str, list[str]]:
    response = requests.post(f"{BASE}/uploads/sample", json={"workflow_id": workflow_id})
    response.raise_for_status()
    return {
        role: [item["upload_id"] for item in items]
        for role, items in response.json()["uploads"].items()
    }


def run(workflow_id: str, source: str, uploads: dict, inputs: dict, connection: dict | None = None):
    """Returns (analyze_response, proof) or (analyze_response, None) when analyze fails."""
    analyze = requests.post(
        f"{BASE}/runs/analyze",
        json={
            "workflow_id": workflow_id,
            "input_source": source,
            "uploads": uploads,
            "inputs": inputs,
            "connection": connection,
            "requirements": {},
        },
    )
    if analyze.status_code != 200:
        return analyze, None

    run_id = requests.post(f"{BASE}/runs", json={"plan_id": analyze.json()["plan_id"]}).json()["run_id"]
    deadline = time.time() + 60
    state = {}
    while time.time() < deadline:
        state = requests.get(f"{BASE}/runs/{run_id}").json()
        if state["status"] in TERMINAL:
            break
        time.sleep(0.15)
    proof = requests.get(f"{BASE}/runs/{run_id}/proof").json()
    proof["_status"] = state.get("status")
    return analyze, proof


def facts(proof: dict) -> dict[str, str]:
    return {item["label"]: item["value"] for item in proof.get("facts", [])}


# --------------------------------------------------------------------------- fixtures

DOC_INVOICE = b"""Acme Supplies: Charge Review
Supplier: Northwind Freight
Invoice: NW-2026-04-0119
Purchase order: PO-55010

| Line | Date | Description | Amount | Reference | Supplier note |
| --- | --- | --- | ---: | --- | --- |
| 1 | 2026-04-02 | Standard ground delivery | $700.00 | Shipment batch GB-0402 | Delivered within the contracted window. |
| 2 | 2026-04-08 | Weekend delivery surcharge | $150.00 | Shipment 990112 | Customer requested Saturday delivery. No approval ID is listed. |
| 3 | 2026-04-14 | Fuel surcharge | $58.00 | April fuel index | Applied at 9.4% of eligible transport charges. |
| 4 | 2026-04-20 | Standard ground delivery | $700.00 | Shipment batch GB-0402 | Same shipment batch and amount as line 1. |
| 5 | 2026-04-26 | Expedited delivery surcharge | $190.00 | Shipment 990884 | Medical shipment. Approval ID AP-3312 is cited. |

Total requested: $1,798.00
"""

DOC_POLICY = b"""Acme Supplies Freight Policy
Policy ID: ACM-FRT-2026-04

## 1. Standard freight services

Standard ground and contracted delivery charges are payable when they reference an
active purchase order and a shipment reference.

## 2. Fuel surcharge

A fuel surcharge is payable when the charge is calculated as a percentage of eligible
transport charges and the percentage does not exceed the published monthly cap of 8.0%.

## 3. Weekend and expedited delivery

Weekend or expedited delivery charges are payable only when the invoice identifies a
valid approval ID issued before dispatch.

## 4. Duplicate charges

A charge must be rejected when it repeats the same shipment or batch reference, charge
type, and amount as a previously invoiced line for the same service period.
"""

UPLOAD_PROJECT = {
    "openapi.json": json.dumps(
        {
            "openapi": "3.0.0",
            "info": {"title": "Orders API", "version": "2.0.0"},
            "paths": {
                "/orders": {"get": {"summary": "List orders"}},
                "/orders/{id}/cancel": {"post": {"summary": "Cancel order"}},
            },
        },
        indent=2,
    ),
    "app.py": '"""Orders API."""\n\nORDERS = {1: {"id": 1, "state": "open"}}\n\n\ndef list_orders():\n    return list(ORDERS.values())\n',
    "test_app.py": (
        "import unittest\n\nimport app\n\n\n"
        "class OrderTests(unittest.TestCase):\n"
        "    def test_list_orders(self):\n"
        "        self.assertEqual(len(app.list_orders()), 1)\n\n"
        "    def test_cancel_exists(self):\n"
        '        self.assertTrue(hasattr(app, "cancel_order"), "cancel_order missing")\n'
    ),
}


def zip_bytes(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


DEADLINE_CSV = (
    "record_id,received_at,channel,summary\n"
    + "\n".join(
        f"rec-{index:04d},2026-09-03T08:{index % 60:02d}:00Z,web,"
        + ["invoice query", "late delivery", "login error", "password reset"][index % 4]
        for index in range(96)
    )
    + "\n"
    + "\n".join(f"rec-{900 + index:04d},2026-09-03T09:00:00Z,web,general enquiry" for index in range(3))
    + "\nrec-bad-1,not-a-date\n"
).encode()

DEADLINE_RULES = (
    "# term = category\ninvoice = Billing\ndelivery = Shipping\nlogin = Technical\npassword = Account\n"
).encode()

FALSE_SAVINGS_CSV = (
    "run_id,route,ai_cost_usd,successful,accepted_first_pass,quality_score,correction_seconds,review_required,reversed\n"
    + "\n".join(
        f"run-{index:03d},efficient,0.50,true,{'true' if index % 10 < 6 else 'false'},0.93,"
        f"{0 if index % 10 < 6 else 600},{'false' if index % 10 < 6 else 'true'},false"
        for index in range(50)
    )
    + "\n"
    + "\n".join(
        f"run-{100 + index:03d},advanced,0.80,true,{'true' if index % 10 < 9 else 'false'},0.96,"
        f"{0 if index % 10 < 9 else 120},{'false' if index % 10 < 9 else 'true'},false"
        for index in range(50)
    )
    + "\n"
).encode()


# --------------------------------------------------------------------------- cases


def case_document_review_sample():
    case = "document_review/sample"
    uploads = sample_uploads("document_review")
    _, proof = run("document_review", "sample", uploads, {"review-focus": "unsupported charges"})
    check(case, "status", proof["_status"], "completed")
    check(case, "measurement", proof["measurement_label"], "Measured sample run")
    check(case, "reviewed count", len(proof["reviewed_items"]), 10)
    # Three rule findings plus the one item rules could not settle.
    check(case, "findings count", len(proof["findings"]), 4)
    unresolved = [item for item in proof["findings"] if item.get("resolved_by") == "unresolved"]
    check(case, "one item reported unresolved", len(unresolved), 1)
    check_true(case, "unresolved item names the reason",
               "defers to judgement" in (unresolved[0]["finding"] if unresolved else ""),
               unresolved[0]["finding"][:120] if unresolved else "none")

    fact = facts(proof)
    check(case, "charges reviewed fact", fact.get("Charges reviewed"), "10")
    check(case, "needs action $", fact.get("Charges needing action"), "$1,190.00")
    check(case, "payable $", fact.get("Recommended for payment"), "$1,930.00")

    texts = " | ".join(item["finding"] for item in proof["findings"])
    check_true(case, "flags $980 over $500", "980.00 exceeds the $500.00" in texts, texts[:120])
    check_true(case, "flags $210 freight over $150", "210.00 exceeds the $150.00" in texts, texts[:120])
    check_true(case, "flags duplicate document", "Duplicate of" in texts, texts[:120])

    outcomes = [item["outcome"] for item in proof["reviewed_items"]]
    check(case, "pay rows", outcomes.count("approve"), 7)
    check(case, "reject rows", outcomes.count("reject"), 2)
    check(case, "one charge needs interpretation", outcomes.count("needs_interpretation"), 1)
    check(case, "no unmatched rows", outcomes.count("unmatched"), 0)
    total = sum(item["amount_usd"] for item in proof["reviewed_items"])
    check(case, "reviewed total", round(total, 2), 3120.00)

    # The escalation ladder must stay visible even with no deployment configured.
    routing = proof["tokenomics"]["routing"]
    check(case, "operations reserved for a model", routing["operations_reserved_for_a_model"], 2)
    check(case, "operations without generative AI", routing["operations_without_generative_ai"], 6)
    check(case, "no model actually ran", routing["operations_on_a_model"], 0)
    check_true(case, "unavailable model is disclosed", bool(routing["note"]), "no note")
    check(case, "no saving claimed from a projection",
          proof["tokenomics"]["saving_claimable"], False)


def case_document_review_upload():
    case = "document_review/upload"
    docs = upload_files("document_review", "business-documents", [("NW-2026-04-0119.md", DOC_INVOICE)])
    rules = upload_files("document_review", "governing-rules", [("ACM-FRT-2026-04.md", DOC_POLICY)])
    _, proof = run(
        "document_review",
        "upload",
        {"business-documents": docs, "governing-rules": rules},
        {"review-focus": "unsupported charges"},
    )
    check(case, "status", proof["_status"], "completed")
    check(case, "measurement", proof["measurement_label"], "Measured usage, calculated cost")
    check(case, "reviewed count", len(proof["reviewed_items"]), 5)

    by_line = {item["line"]: item for item in proof["reviewed_items"]}
    check(case, "line 1 pays", by_line["1"]["outcome"], "approve")
    check(case, "line 2 needs approval", by_line["2"]["outcome"], "request_evidence")
    check(case, "line 3 rejected (9.4% over 8.0% cap)", by_line["3"]["outcome"], "reject")
    check(case, "line 4 rejected (duplicate of line 1)", by_line["4"]["outcome"], "reject")
    check(case, "line 5 pays (AP-3312 cited)", by_line["5"]["outcome"], "approve")

    texts = " | ".join(item["finding"] for item in proof["findings"])
    check_true(case, "percentage cap enforced", "9.4% exceeds the 8.0% cap" in texts, texts[:160])
    check_true(case, "line-item duplicate detected", "repeats line 1" in texts, texts[:160])

    fact = facts(proof)
    # 150 (weekend) + 58 (fuel) + 700 (duplicate) = 908
    check(case, "needs action $", fact.get("Charges needing action"), "$908.00")
    check(case, "payable $", fact.get("Recommended for payment"), "$890.00")


def case_document_review_connected():
    for application, reference, expect_reviewed, expect_findings in (
        ("claims-assistant", "wf-4821", 5, 2),
        ("vendor-desk", "case-7702", 4, 2),
    ):
        case = f"document_review/connected[{application}]"
        _, proof = run(
            "document_review",
            "connected",
            {},
            {"review-focus": "unsupported charges"},
            {"application": application, "reference": reference},
        )
        check(case, "status", proof["_status"], "completed")
        check(case, "labelled as stub", proof["measurement_label"], "Measured run, local connector stub")
        check(case, "reviewed count", len(proof["reviewed_items"]), expect_reviewed)
        check(case, "findings count", len(proof["findings"]), expect_findings)
        check_true(
            case,
            "inputs came from the connector",
            all(item["origin"] == "connected" for item in proof["inputs"]),
            str([item["origin"] for item in proof["inputs"]]),
        )

    # Vendor Desk has a line-item duplicate and an unapproved callout.
    case = "document_review/connected[vendor-desk]"
    _, proof = run(
        "document_review", "connected", {}, {"review-focus": "x"},
        {"application": "vendor-desk", "reference": "case-7702"},
    )
    by_line = {item["line"]: item["outcome"] for item in proof["reviewed_items"]}
    check(case, "line 2 after-hours rejected", by_line.get("2"), "reject")
    check(case, "line 4 duplicate rejected", by_line.get("4"), "reject")
    check(case, "line 1 pays", by_line.get("1"), "approve")


def case_connected_rejections():
    case = "connected/refusals"
    analyze, _ = run("document_review", "connected", {}, {"review-focus": "x"},
                     {"application": "Not Registered", "reference": "wf-4821"})
    check(case, "unknown application refused", analyze.status_code, 422)
    check_true(case, "names registered apps",
               "Claims Assistant" in analyze.text, analyze.text[:140])

    analyze, _ = run("document_review", "connected", {}, {"review-focus": "x"},
                     {"application": "claims-assistant", "reference": "no-such-ref"})
    check(case, "unknown reference refused", analyze.status_code, 422)
    check_true(case, "names available references", "wf-4821" in analyze.text, analyze.text[:140])

    analyze, _ = run("software_validation", "connected", {}, {
        "requested-change": "x", "validation-level": "Static plus allowed tests",
    }, {"application": "claims-assistant", "reference": "wf-4821"})
    check(case, "wrong-workflow application refused", analyze.status_code, 422)


def case_software_validation(source: str):
    case = f"software_validation/{source}"
    if source == "sample":
        uploads = sample_uploads("software_validation")
    else:
        archive = upload_files("software_validation", "software-input",
                               [("orders-api.zip", zip_bytes(UPLOAD_PROJECT))])
        spec = upload_files("software_validation", "supporting-evidence",
                            [("openapi.json", UPLOAD_PROJECT["openapi.json"].encode())])
        uploads = {"software-input": archive, "supporting-evidence": spec}

    _, proof = run("software_validation", source, uploads, {
        "requested-change": "Add the archive endpoint",
        "validation-level": "Static plus allowed tests",
    })
    # A failing test must never be reported as a pass.
    check(case, "status reports findings", proof["_status"], "completed_with_findings")
    check(case, "quality not passed", proof["outcome"]["quality_passed"], False)
    fact = facts(proof)
    check_true(case, "test counts reported",
               any("run" in value for value in fact.values()), json.dumps(fact)[:160])
    failed = [item for item in proof["verification"] if not item["passed"]]
    check_true(case, "failed check is explicit", len(failed) >= 1, str(fact))


def case_deadline_processing(source: str):
    case = f"deadline_processing/{source}"
    if source == "sample":
        uploads = sample_uploads("deadline_processing")
        expected_valid, expected_invalid = "9,989", 11
    else:
        records = upload_files("deadline_processing", "records", [("records.csv", DEADLINE_CSV)])
        rules = upload_files("deadline_processing", "category-rules", [("rules.txt", DEADLINE_RULES)])
        uploads = {"records": records, "category-rules": rules}
        expected_valid, expected_invalid = "99", 1

    _, proof = run("deadline_processing", source, uploads, {
        "processing-instruction": "Classify each record by category and summarize the totals.",
        "completion-deadline": "2026-12-31T23:59",
        "output-format": "CSV",
    })
    check(case, "status", proof["_status"], "completed")
    fact = facts(proof)
    check(case, "records processed", fact.get("Records processed"), expected_valid)
    check_true(case, "invalid rows reported honestly",
               str(expected_invalid) in json.dumps(proof["operations"]),
               f"expected {expected_invalid} invalid rows")
    check(case, "deadline met", proof["outcome"]["deadline_met"], True)


def case_false_savings(source: str):
    case = f"false_savings/{source}"
    if source == "sample":
        uploads = sample_uploads("false_savings")
    else:
        history = upload_files("false_savings", "outcome-history", [("runs.csv", FALSE_SAVINGS_CSV)])
        uploads = {"outcome-history": history}

    _, proof = run("false_savings", source, uploads, {
        "reviewer-hourly-rate": "68",
        "acceptance-rule": "Accepted without correction, retry, or reversal",
        "minimum-quality": "0.9",
        "minimum-cohort": "25",
    })
    check(case, "status", proof["_status"], "completed")
    check_true(case, "produced a comparison", proof.get("baseline") is not None, "no baseline table")
    check_true(case, "reports a finding", proof.get("finding") is not None, "no finding")
    # The cheap route is only a saving if its corrections do not cost more.
    body = json.dumps(proof.get("finding") or {})
    check_true(case, "states a cost-per-accepted-result conclusion",
               "accepted" in body.lower() or "saving" in body.lower(), body[:160])


def case_reviewed_items_scope():
    """reviewed_items is document-review specific; other workflows must return [] rather
    than a partly built list."""
    case = "contract/reviewed_items"
    for workflow, inputs in (
        ("software_validation", {"requested-change": "x", "validation-level": "Static plus allowed tests"}),
        ("deadline_processing", {"processing-instruction": "x", "completion-deadline": "2026-12-31T23:59", "output-format": "CSV"}),
        ("false_savings", {"reviewer-hourly-rate": "68", "acceptance-rule": "Accepted without correction, retry, or reversal", "minimum-quality": "0.9", "minimum-cohort": "25"}),
    ):
        uploads = sample_uploads(workflow)
        _, proof = run(workflow, "sample", uploads, inputs)
        check(case, f"{workflow} returns a list", isinstance(proof.get("reviewed_items"), list), True)
        check(case, f"{workflow} has no charge rows", len(proof.get("reviewed_items", [])), 0)


def main() -> int:
    health = requests.get("http://127.0.0.1:8000/health", timeout=5)
    if health.status_code != 200:
        print("API is not healthy")
        return 1

    case_document_review_sample()
    case_document_review_upload()
    case_document_review_connected()
    case_connected_rejections()
    for source in ("sample", "upload"):
        case_software_validation(source)
        case_deadline_processing(source)
        case_false_savings(source)
    case_reviewed_items_scope()

    print(f"\nPASS {len(PASS)}   FAIL {len(FAIL)}\n")
    for line in FAIL:
        print("  FAIL " + line)
    if not FAIL:
        print("  every assertion matched the expected result")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
