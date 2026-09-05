"""Bundled sample inputs.

Samples are generated deterministically and then pushed through the same upload
validation, extraction, and hashing pipeline as user files. Their results are
labelled `Measured sample run` because the analysis is real.
"""

from __future__ import annotations

import io
import json
import random
import zipfile

from .storage.uploads import Upload, upload_store

POLICY = """Purchasing Policy 2026
Section 4.1 All supplier charges must reference an approved purchase order.
Section 4.2 Any single line charge has a maximum of $500.00 without director approval.
Section 4.3 Duplicate invoices must be rejected.
Section 5.1 Freight surcharges are payable up to $150.00 per shipment.
Section 6.1 Rework is payable only when it is not attributable to supplier fault. Where responsibility is contested, the charge requires interpretation of the supporting narrative before it can be approved or rejected.
"""

INVOICES = {
    "Supplier-Invoice-1042.txt": """Supplier Invoice 1042
Purchase Order: PO-88120
Approved by: J. Whitfield
Consulting services : $420.00
Freight surcharge : $120.00
Total : $540.00
""",
    "Supplier-Invoice-1043.txt": """Supplier Invoice 1043
Purchase Order: PO-88121
Approved by: J. Whitfield
Replacement parts : $310.00
Freight surcharge : $95.00
Total : $405.00
""",
    "Supplier-Invoice-1044.txt": """Supplier Invoice 1044
Purchase Order: PO-88122
Approved by: R. Alvarez
Emergency site attendance : $980.00
Total : $980.00
""",
    "Supplier-Invoice-1045.txt": """Supplier Invoice 1045
Purchase Order: PO-88123
Rework of previously delivered items : $265.00
Supplier note: The rework followed a specification the customer revised after dispatch. The site supervisor recorded that the original build matched the drawing issued at the time, but the customer maintains the tolerance was always implied. Responsibility for the rework is disputed between the parties and is not settled in this document.
Total : $265.00
""",
    "Supplier-Invoice-1046.txt": """Supplier Invoice 1046
Purchase Order: PO-88124
Approved by: R. Alvarez
Calibration service : $180.00
Freight surcharge : $210.00
Total : $390.00
""",
    "Supplier-Invoice-1042-copy.txt": """Supplier Invoice 1042
Purchase Order: PO-88120
Approved by: J. Whitfield
Consulting services : $420.00
Freight surcharge : $120.00
Total : $540.00
""",
}

PURCHASE_ORDERS = {
    "PO-88120.txt": "Purchase Order PO-88120\nApproved value: $600.00\nApproved by: J. Whitfield\n",
    "PO-88122.txt": "Purchase Order PO-88122\nApproved value: $500.00\nApproved by: R. Alvarez\n",
}

SAMPLE_PROJECT = {
    "openapi.json": json.dumps(
        {
            "openapi": "3.0.0",
            "info": {"title": "Widget API", "version": "1.1.0"},
            "paths": {
                "/widgets": {"get": {"summary": "List widgets"}},
                "/widgets/{id}": {"get": {"summary": "Get widget"}},
                "/widgets/{id}/archive": {"post": {"summary": "Archive widget"}},
            },
        },
        indent=2,
    ),
    "app.py": '''"""Small widget API used by the TokenOS sample."""

WIDGETS = {1: {"id": 1, "name": "Left flange"}, 2: {"id": 2, "name": "Right flange"}}


def list_widgets():
    return list(WIDGETS.values())


def get_widget(widget_id):
    return WIDGETS.get(widget_id)


def widget_name(widget_id):
    widget = get_widget(widget_id)
    return widget["name"] if widget else None
''',
    "test_app.py": '''import unittest

import app


class WidgetTests(unittest.TestCase):
    def test_list_widgets(self):
        self.assertEqual(len(app.list_widgets()), 2)

    def test_get_widget(self):
        self.assertEqual(app.get_widget(1)["name"], "Left flange")

    def test_archive_widget_exists(self):
        # The specification declares /widgets/{id}/archive but the module does not implement it.
        self.assertTrue(hasattr(app, "archive_widget"), "archive_widget is declared in openapi.json but missing")
''',
    "README.md": "Sample project for TokenOS software validation.\n",
}


def _deadline_records(count: int = 10_000) -> str:
    rng = random.Random(20260904)
    categories = ["billing", "shipping", "technical", "account"]
    phrases = {
        "billing": ["invoice query", "refund request", "payment failed"],
        "shipping": ["late delivery", "wrong address", "missing parcel"],
        "technical": ["login error", "app crash", "sync failure"],
        "account": ["password reset", "close account", "update details"],
    }
    lines = ["record_id,received_at,channel,summary"]
    for index in range(count):
        if index % 250 == 7:
            summary = "general enquiry requiring review"  # ambiguous, no rule term
        elif index % 997 == 11:
            lines.append(f"rec-{index:05d},not-a-date")  # intentionally malformed row
            continue
        else:
            category = categories[index % len(categories)]
            summary = rng.choice(phrases[category])
        lines.append(f"rec-{index:05d},2026-09-03T08:{index % 60:02d}:00Z,web,{summary}")
    return "\n".join(lines) + "\n"


DEADLINE_RULES = """# term = category
invoice = Billing
refund = Billing
payment = Billing
delivery = Shipping
address = Shipping
parcel = Shipping
login = Technical
crash = Technical
sync = Technical
password = Account
close account = Account
update details = Account
"""


def _false_savings_runs(count: int = 200) -> str:
    rng = random.Random(4242)
    lines = [
        "run_id,route,ai_cost_usd,successful,accepted_first_pass,quality_score,correction_seconds,review_required,reversed"
    ]
    for index in range(count):
        efficient = index % 2 == 0
        route = "efficient" if efficient else "advanced"
        if efficient:
            ai_cost = round(rng.uniform(0.40, 0.54), 4)
            accepted = rng.random() < 0.71
            quality = round(rng.uniform(0.88, 0.97), 3)
            correction = 0 if accepted else rng.randint(240, 900)
        else:
            ai_cost = round(rng.uniform(0.70, 0.86), 4)
            accepted = rng.random() < 0.94
            quality = round(rng.uniform(0.93, 0.99), 3)
            correction = 0 if accepted else rng.randint(60, 300)
        successful = quality >= 0.90
        lines.append(
            f"run-{index:04d},{route},{ai_cost},{str(successful).lower()},{str(accepted).lower()},"
            f"{quality},{correction},{str(not accepted).lower()},false"
        )
    return "\n".join(lines) + "\n"


def _zip_bytes(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def build_sample_uploads(workflow_id: str) -> dict[str, list[Upload]]:
    """Materializes the bundled sample through the real upload pipeline."""

    def add(name: str, content: bytes | str, role: str) -> Upload:
        raw = content.encode("utf-8") if isinstance(content, str) else content
        return upload_store.add(
            name=name, raw=raw, role=role, workflow_id=workflow_id, origin="sample"
        )

    if workflow_id == "document_review":
        documents = [add(name, text, "business-documents") for name, text in INVOICES.items()]
        documents += [add(name, text, "business-documents") for name, text in PURCHASE_ORDERS.items()]
        rules = [add("Purchasing-Policy-2026.txt", POLICY, "governing-rules")]
        return {"business-documents": documents, "governing-rules": rules}

    if workflow_id == "software_validation":
        archive = add("widget-api-sample.zip", _zip_bytes(SAMPLE_PROJECT), "software-input")
        spec = add("openapi.json", SAMPLE_PROJECT["openapi.json"], "supporting-evidence")
        return {"software-input": [archive], "supporting-evidence": [spec]}

    if workflow_id == "deadline_processing":
        records = add("support-records-10000.csv", _deadline_records(), "records")
        rules = add("category-rules.txt", DEADLINE_RULES, "category-rules")
        return {"records": [records], "category-rules": [rules]}

    if workflow_id == "false_savings":
        history = add("route-history-200-runs.csv", _false_savings_runs(), "outcome-history")
        return {"outcome-history": [history]}

    raise KeyError(f"No sample bundled for workflow '{workflow_id}'")
