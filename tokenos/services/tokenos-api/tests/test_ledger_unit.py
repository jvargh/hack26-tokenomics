"""Unit tests for the durable run ledger (`storage/ledger.py`).

Uses a throwaway SQLite file per test so these never touch the runtime ledger a
demo server writes to.

Run: .\\.venv\\Scripts\\python.exe -m pytest tests/test_ledger_unit.py -v
"""

from __future__ import annotations

from tokenos_api.storage.ledger import RunLedger

SAMPLE_PROOF = {
    "status": "completed",
    "measurement_label": "Measured sample run",
    "outcome": {"quality_passed": True},
    "routing": {"operations": 8, "completed_without_generative_ai": 6},
    "usage": {"model_calls": 1, "input_tokens": 500, "output_tokens": 120},
    "economics": {"total_calculated_cost_usd": 0.000176},
}

SAMPLE_COMPARISON_SAVING = {
    "status": "eligible_saving",
    "saving_claimable": True,
    "saving_usd": 0.0058,
    "equal_quality": True,
}

SAMPLE_COMPARISON_NO_SAVING = {
    "status": "no_saving",
    "saving_claimable": False,
    "saving_usd": -0.0002,
    "equal_quality": True,
}


def test_record_proof_persists_measured_fields(tmp_path):
    ledger = RunLedger(path=tmp_path / "ledger.sqlite3")

    ledger.record_proof("run-1", "document_review", SAMPLE_PROOF)
    rows = ledger.report()

    assert len(rows) == 1
    row = rows[0]
    assert row["run_id"] == "run-1"
    assert row["workflow_id"] == "document_review"
    assert row["operations_total"] == 8
    assert row["without_generative_ai"] == 6
    assert row["model_calls"] == 1
    assert row["calculated_cost_usd"] == 0.000176


def test_record_proof_is_idempotent_for_the_same_run_id(tmp_path):
    ledger = RunLedger(path=tmp_path / "ledger.sqlite3")

    ledger.record_proof("run-1", "document_review", SAMPLE_PROOF)
    ledger.record_proof("run-1", "document_review", SAMPLE_PROOF)

    assert len(ledger.report()) == 1


def test_record_baseline_joins_to_its_governed_run(tmp_path):
    ledger = RunLedger(path=tmp_path / "ledger.sqlite3")
    ledger.record_proof("run-1", "document_review", SAMPLE_PROOF)

    ledger.record_baseline("run-1", SAMPLE_COMPARISON_SAVING)
    rows = ledger.report()

    assert rows[0]["baseline_status"] == "eligible_saving"
    assert rows[0]["saving_claimable"] == 1
    assert rows[0]["saving_usd"] == 0.0058


def test_summary_only_counts_eligible_saving_as_verified(tmp_path):
    ledger = RunLedger(path=tmp_path / "ledger.sqlite3")
    ledger.record_proof("run-1", "document_review", SAMPLE_PROOF)
    ledger.record_proof("run-2", "document_review", SAMPLE_PROOF)
    ledger.record_baseline("run-1", SAMPLE_COMPARISON_SAVING)
    ledger.record_baseline("run-2", SAMPLE_COMPARISON_NO_SAVING)

    summary = ledger.summary()

    assert summary["total_runs"] == 2
    assert summary["verified_savings_count"] == 1
    assert summary["total_verified_saving_usd"] == 0.0058


def test_summary_on_empty_ledger_returns_zeros(tmp_path):
    ledger = RunLedger(path=tmp_path / "ledger.sqlite3")

    summary = ledger.summary()

    assert summary["total_runs"] == 0
    assert summary["total_measured_cost_usd"] == 0.0
    assert summary["verified_savings_count"] == 0
