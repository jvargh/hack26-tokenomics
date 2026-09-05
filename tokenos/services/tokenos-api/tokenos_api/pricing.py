"""Administrator-configured model price table.

Prices are not shipped with values: an implementation owner must populate
`price_table.json` for the deployments actually in use. Until then the API
reports measured token usage with a zero calculated cost and says so.
"""

from __future__ import annotations

import json
from pathlib import Path

from .config import SERVICE_ROOT

PRICE_TABLE_PATH = Path(SERVICE_ROOT, "price_table.json")


def load_price_table() -> dict:
    if not PRICE_TABLE_PATH.exists():
        return {}
    try:
        return json.loads(PRICE_TABLE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def calculate_cost_usd(deployment: str, input_tokens: int, output_tokens: int) -> tuple[float, bool]:
    """Returns (calculated cost, whether a price was configured)."""
    entry = load_price_table().get(deployment)
    if not entry:
        return 0.0, False
    input_price = float(entry.get("input_per_1m_usd", 0.0))
    output_price = float(entry.get("output_per_1m_usd", 0.0))
    cost = (input_tokens / 1_000_000) * input_price + (output_tokens / 1_000_000) * output_price
    return round(cost, 6), True


def price_source(deployment: str) -> dict | None:
    return load_price_table().get(deployment)


def save_price_table(table: dict) -> None:
    PRICE_TABLE_PATH.write_text(json.dumps(table, indent=2), encoding="utf-8")

