"""Unit tests for the price table and cost calculation.

Run: .\\.venv\\Scripts\\python.exe -m pytest tests/test_pricing_unit.py -v
"""

from __future__ import annotations

import json

from tokenos_api import pricing


def test_calculate_cost_usd_uses_configured_price_table(tmp_path, monkeypatch):
    table = {
        "test-deployment": {
            "input_per_1m_usd": 1.0,
            "output_per_1m_usd": 4.0,
            "effective_date": "2026-01-01",
            "model": "test-model",
            "model_version": "v1",
            "region": "eastus",
        }
    }
    price_file = tmp_path / "price_table.json"
    price_file.write_text(json.dumps(table), encoding="utf-8")
    monkeypatch.setattr(pricing, "PRICE_TABLE_PATH", price_file)

    cost, configured = pricing.calculate_cost_usd("test-deployment", 1_000_000, 500_000)

    assert configured is True
    # 1,000,000 input tokens @ $1/1M = $1.00; 500,000 output tokens @ $4/1M = $2.00
    assert cost == 3.0


def test_calculate_cost_usd_zero_tokens_is_zero_cost(tmp_path, monkeypatch):
    table = {
        "test-deployment": {
            "input_per_1m_usd": 1.0,
            "output_per_1m_usd": 4.0,
            "effective_date": "2026-01-01",
        }
    }
    price_file = tmp_path / "price_table.json"
    price_file.write_text(json.dumps(table), encoding="utf-8")
    monkeypatch.setattr(pricing, "PRICE_TABLE_PATH", price_file)

    cost, configured = pricing.calculate_cost_usd("test-deployment", 0, 0)

    assert configured is True
    assert cost == 0.0


def test_calculate_cost_usd_unpriced_deployment_reports_not_configured(tmp_path, monkeypatch):
    price_file = tmp_path / "price_table.json"
    price_file.write_text(json.dumps({}), encoding="utf-8")
    monkeypatch.setattr(pricing, "PRICE_TABLE_PATH", price_file)

    cost, configured = pricing.calculate_cost_usd("unknown-deployment", 1000, 1000)

    # Never invents a cost for an unpriced deployment.
    assert configured is False
    assert cost == 0.0


def test_load_price_table_missing_file_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(pricing, "PRICE_TABLE_PATH", tmp_path / "does-not-exist.json")

    assert pricing.load_price_table() == {}


def test_load_price_table_invalid_json_returns_empty(tmp_path, monkeypatch):
    price_file = tmp_path / "price_table.json"
    price_file.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(pricing, "PRICE_TABLE_PATH", price_file)

    assert pricing.load_price_table() == {}


def test_price_source_returns_full_entry(tmp_path, monkeypatch):
    table = {
        "test-deployment": {
            "input_per_1m_usd": 1.0,
            "output_per_1m_usd": 4.0,
            "effective_date": "2026-01-01",
            "model": "test-model",
            "model_version": "v1",
            "region": "eastus",
        }
    }
    price_file = tmp_path / "price_table.json"
    price_file.write_text(json.dumps(table), encoding="utf-8")
    monkeypatch.setattr(pricing, "PRICE_TABLE_PATH", price_file)

    entry = pricing.price_source("test-deployment")

    assert entry is not None
    assert entry["effective_date"] == "2026-01-01"
    assert entry["model_version"] == "v1"
