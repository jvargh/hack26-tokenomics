"""Local connected-application registry.

A registered application is a named integration whose adapter, permitted scope, and
records live on the server. The browser never holds credentials and never names a
file — it names an application and a reference, and the server resolves what that
application is permitted to return.

Every connector here is a LOCAL STUB. It returns bundled records so the connected
path can be exercised end to end without external credentials. Runs made this way
are labelled `measured_connected_stub` so a stub result is never mistaken for a
live system of record.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .storage.uploads import Upload, upload_store


class ConnectionError(Exception):
    """Raised when an application or reference cannot be resolved."""


@dataclass(frozen=True)
class ConnectedApplication:
    application_id: str
    name: str
    workflow_id: str
    adapter: str
    scope: str
    permitted_actions: tuple[str, ...]
    reference_label: str
    reference_example: str
    records: dict[str, dict] = field(default_factory=dict)

    def public(self) -> dict:
        return {
            "application_id": self.application_id,
            "name": self.name,
            "workflow_id": self.workflow_id,
            "adapter": self.adapter,
            "scope": self.scope,
            "permitted_actions": list(self.permitted_actions),
            "reference_label": self.reference_label,
            "reference_example": self.reference_example,
            "available_references": sorted(self.records),
            "connection_kind": "local_stub",
        }


CLAIMS_INVOICE = """Northstar Logistics: Supplier Charge Review
Supplier: Contoso Freight Services
Invoice: CFS-2026-03-2043
Purchase order: PO-78421

| Line | Date | Description | Amount | Reference | Supplier note |
| --- | --- | --- | ---: | --- | --- |
| 1 | 2026-03-04 | Standard parcel delivery, Midwest region | $980.00 | Shipment batch MW-0304 | Delivered within the contracted window. |
| 2 | 2026-03-09 | Weekend delivery surcharge | $210.00 | Shipment 461201 | Customer requested Sunday delivery. No approval ID is listed. |
| 3 | 2026-03-12 | Fuel surcharge | $74.50 | March fuel index | Applied at 7.6% of eligible transport charges. |
| 4 | 2026-03-18 | Peak season capacity surcharge | $415.00 | March network capacity | Supplier indicates a seasonal capacity event. |
| 5 | 2026-03-22 | Expedited delivery surcharge | $260.00 | Shipment 461884 | Urgent medical shipment. Approval ID AP-7731 is cited. |

Total requested: $1,939.50
"""

CLAIMS_POLICY = """Northstar Logistics Supplier Freight Policy
Policy ID: NLS-FRT-2026-03

## 1. Standard freight services

Standard parcel, ground, and contracted delivery charges are payable when they are tied
to an active purchase order and a shipment reference.

## 2. Fuel surcharge

A fuel surcharge is payable when the charge is calculated as a percentage of eligible
transport charges and the percentage does not exceed the published monthly cap of 8.0%.

## 3. Weekend and expedited delivery

Weekend or expedited delivery charges are payable only when the invoice identifies a
valid approval ID issued before dispatch.

## 4. Peak season capacity surcharge

Peak season or network-capacity surcharges are not payable unless a written exception
approval from Logistics Operations is attached.

## 5. Duplicate charges

A charge must be rejected when it repeats the same supplier, shipment or batch reference,
charge type, and amount as a previously invoiced line for the same service period.
"""

VENDOR_INVOICE = """Harbour Point Facilities: Contractor Charge Review
Supplier: Meridian Site Services
Invoice: MSS-2026-02-0771
Purchase order: PO-33914

| Line | Date | Description | Amount | Reference | Supplier note |
| --- | --- | --- | ---: | --- | --- |
| 1 | 2026-02-05 | Scheduled maintenance visit | $640.00 | Work order WO-5521 | Completed against the maintenance schedule. |
| 2 | 2026-02-11 | After-hours callout | $520.00 | Work order WO-5560 | Attended outside contracted hours. No approval reference supplied. |
| 3 | 2026-02-16 | Materials handling | $180.00 | Work order WO-5560 | Consumables used during the callout. |
| 4 | 2026-02-23 | Scheduled maintenance visit | $640.00 | Work order WO-5521 | Same work order and amount as line 1. |

Total requested: $1,980.00
"""

VENDOR_POLICY = """Harbour Point Facilities Contractor Policy
Policy ID: HPF-CON-2026-01

## 1. Scheduled maintenance

Scheduled maintenance visits are payable when they reference an open work order.

## 2. After-hours attendance

After-hours or callout charges are not payable unless a documented approval reference
issued by the facilities manager is supplied with the invoice.

## 3. Materials handling

Materials handling is payable when it references the work order it was consumed against.

## 4. Duplicate charges

A charge must be rejected when it repeats the same work order reference, charge type,
and amount as a previously invoiced line.
"""


REGISTRY: dict[str, ConnectedApplication] = {
    "claims-assistant": ConnectedApplication(
        application_id="claims-assistant",
        name="Claims Assistant",
        workflow_id="document_review",
        adapter="local_stub",
        scope="Read-only access to charge reviews and the freight policy for Logistics Operations.",
        permitted_actions=("read_document", "read_policy"),
        reference_label="Workflow or trace ID",
        reference_example="wf-4821",
        records={
            "wf-4821": {
                "business-documents": [("CFS-2026-03-2043.md", CLAIMS_INVOICE)],
                "governing-rules": [("NLS-FRT-2026-03.md", CLAIMS_POLICY)],
            }
        },
    ),
    "vendor-desk": ConnectedApplication(
        application_id="vendor-desk",
        name="Vendor Desk",
        workflow_id="document_review",
        adapter="local_stub",
        scope="Read-only access to contractor invoices and the facilities contractor policy.",
        permitted_actions=("read_document", "read_policy"),
        reference_label="Case reference",
        reference_example="case-7702",
        records={
            "case-7702": {
                "business-documents": [("MSS-2026-02-0771.md", VENDOR_INVOICE)],
                "governing-rules": [("HPF-CON-2026-01.md", VENDOR_POLICY)],
            }
        },
    ),
}


def list_applications(workflow_id: str | None = None) -> list[dict]:
    items = REGISTRY.values()
    if workflow_id:
        items = [item for item in items if item.workflow_id == workflow_id]
    return [item.public() for item in items]


def resolve_connection(workflow_id: str, connection: dict | None) -> dict[str, list[Upload]]:
    """Turns an application plus reference into real uploads.

    The server decides what the application is permitted to return. An unknown
    application or reference is refused rather than guessed at.
    """
    if not connection:
        raise ConnectionError("Select a registered application.")

    requested = str(connection.get("application", "")).strip()
    reference = str(connection.get("reference", "")).strip()
    if not requested:
        raise ConnectionError("Select a registered application.")
    if not reference:
        raise ConnectionError("Enter the reference to retrieve.")

    key = requested.lower().replace(" ", "-")
    application = REGISTRY.get(key) or next(
        (item for item in REGISTRY.values() if item.name.lower() == requested.lower()), None
    )
    if application is None:
        known = ", ".join(item.name for item in REGISTRY.values()) or "none"
        raise ConnectionError(f"'{requested}' is not a registered application. Registered: {known}.")

    if application.workflow_id != workflow_id:
        raise ConnectionError(
            f"{application.name} is registered for a different workflow and cannot be used here."
        )

    record = application.records.get(reference)
    if record is None:
        known = ", ".join(sorted(application.records)) or "none"
        raise ConnectionError(
            f"{application.name} has no record for '{reference}'. Available: {known}."
        )

    grouped: dict[str, list[Upload]] = {}
    for role, documents in record.items():
        grouped[role] = [
            upload_store.add(
                name=name,
                raw=text.encode("utf-8"),
                role=role,
                workflow_id=workflow_id,
                origin="connected",
            )
            for name, text in documents
        ]
    return grouped
