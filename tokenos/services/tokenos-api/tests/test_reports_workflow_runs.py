"""Reporting must span every proof-bearing run, not just optimization runs.

The first three workflows persist their proofs to the durable ledger while the
fourth writes to the optimization store. Reporting originally read only the
optimization store, so a completed document review produced an empty report.
These tests pin the mapping and, more importantly, the claim-strength rules that
mapping must not weaken.

Run: .\\.venv\\Scripts\\python.exe -m pytest tests/test_reports_workflow_runs.py -v
"""

from __future__ import annotations

import pytest

from tokenos_api.optimization import engine
from tokenos_api.storage.ledger import RunLedger

UPLOAD_PROOF = {
    "status": "completed",
    "created_at": "2026-09-10T10:00:52.049354+00:00",
    "input_evidence": "upload",
    "measurement_label": "Measured usage, calculated cost",
    "outcome": {"quality_passed": True},
    "routing": {"operations": 8, "completed_without_generative_ai": 7,
                "efficient_ai": 1, "advanced_ai": 0},
    "usage": {"model_calls": 1, "input_tokens": 1240, "output_tokens": 113},
    "economics": {"calculated_model_cost_usd": 0.000169},
}

SAMPLE_PROOF = {
    **UPLOAD_PROOF,
    "input_evidence": "sample",
    "measurement_label": "Measured sample run",
}

FAILED_QUALITY_PROOF = {
    **UPLOAD_PROOF,
    "outcome": {"quality_passed": False},
}


@pytest.fixture()
def ledger(tmp_path, monkeypatch):
    """Points the engine at a throwaway ledger so these never read a demo run."""
    store = RunLedger(path=tmp_path / "ledger.sqlite3")
    monkeypatch.setattr(engine, "ledger_store", store)
    return store


def rows_for(ledger) -> list[dict]:
    return engine._workflow_report_rows()


def test_a_completed_workflow_run_reaches_reporting(ledger):
    ledger.record_proof("run-1", "document_review", UPLOAD_PROOF)

    rows = rows_for(ledger)

    assert len(rows) == 1
    assert rows[0]["runId"] == "run-1"
    assert rows[0]["dimensions"]["workflowId"] == "document_review"
    assert rows[0]["dimensions"]["source"] == "workflow"
    assert rows[0]["cost"]["modelSpendUsd"] == pytest.approx(0.000169)


def test_uploaded_input_is_measured_and_sample_input_is_not(ledger):
    """Uploaded documents are the operator's real input, so the run is measured.
    A fixture run is reproducible input and must never be read as production
    spend, however real its measurement was."""
    ledger.record_proof("run-upload", "document_review", UPLOAD_PROOF)
    ledger.record_proof("run-sample", "document_review", SAMPLE_PROOF)

    by_id = {row["runId"]: row for row in rows_for(ledger)}

    assert by_id["run-upload"]["dimensions"]["proofType"] == "measured"
    assert by_id["run-sample"]["dimensions"]["proofType"] == "sample"


def test_unmeasured_rates_are_absent_rather_than_zero(ledger):
    """The classic runner records no escalation or context minimisation. Writing
    0.0 would drag the fleet mean toward zero and report governance the run never
    performed, so those keys must simply not appear."""
    ledger.record_proof("run-1", "document_review", UPLOAD_PROOF)

    metrics = rows_for(ledger)[0]["metrics"]

    assert "escalationRate" not in metrics
    assert "contextMinimizationRate" not in metrics
    assert "measuredCachedTokenRate" not in metrics
    assert metrics["qualityPassRate"] == 1.0


def test_absent_rates_do_not_dilute_the_aggregate(ledger):
    ledger.record_proof("run-1", "document_review", UPLOAD_PROOF)

    groups = engine._aggregate_groups(rows_for(ledger))
    measured = groups["measured"]

    assert measured["runCount"] == 1
    assert measured["rates"]["qualityPassRate"] == {"sum": 1.0, "count": 1, "mean": 1.0}
    # No observation at all, so the mean is unknown rather than zero.
    assert measured["rates"]["escalationRate"] == {"sum": 0.0, "count": 0, "mean": None}


def test_quality_pass_rate_averages_across_runs(ledger):
    ledger.record_proof("run-pass", "document_review", UPLOAD_PROOF)
    ledger.record_proof("run-fail", "document_review", FAILED_QUALITY_PROOF)

    measured = engine._aggregate_groups(rows_for(ledger))["measured"]

    assert measured["runCount"] == 2
    assert measured["rates"]["qualityPassRate"]["mean"] == pytest.approx(0.5)
    assert measured["acceptedOutcomes"] == 1


def test_a_run_without_a_baseline_claims_no_saving(ledger):
    ledger.record_proof("run-1", "document_review", UPLOAD_PROOF)

    row = rows_for(ledger)[0]

    assert row["baseline"] == {}
    assert engine._aggregate_groups([row])["measured"]["verifiedSavingsUsd"] == 0.0


def test_an_ineligible_baseline_claims_no_saving(ledger):
    """A cheaper governed run is not a saving unless the comparison itself was
    claimable and both paths passed the same checks."""
    ledger.record_proof("run-1", "document_review", UPLOAD_PROOF)
    ledger.record_baseline("run-1", {
        "status": "no_saving",
        "saving_claimable": False,
        "saving_usd": 0.0058,
        "equal_quality": True,
        "baseline": {"cost_usd": 0.004},
    })

    row = rows_for(ledger)[0]

    assert row["baseline"]["eligible"] is False
    assert "verifiedSavingUsd" not in row["baseline"]
    assert engine._aggregate_groups([row])["measured"]["verifiedSavingsUsd"] == 0.0
    # The baseline still cost real money, so its spend is reported.
    assert row["baseline"]["baselineModelSpendUsd"] == pytest.approx(0.004)


def test_unequal_quality_blocks_the_saving_even_when_claimable(ledger):
    """A cheaper wrong answer is not a saving."""
    ledger.record_proof("run-1", "document_review", UPLOAD_PROOF)
    ledger.record_baseline("run-1", {
        "status": "eligible_saving",
        "saving_claimable": True,
        "saving_usd": 0.0058,
        "equal_quality": False,
        "baseline": {"cost_usd": 0.004},
    })

    row = rows_for(ledger)[0]

    assert row["baseline"]["eligible"] is False
    assert engine._aggregate_groups([row])["measured"]["verifiedSavingsUsd"] == 0.0


def test_a_fully_eligible_baseline_reports_its_saving(ledger):
    ledger.record_proof("run-1", "document_review", UPLOAD_PROOF)
    ledger.record_baseline("run-1", {
        "status": "eligible_saving",
        "saving_claimable": True,
        "saving_usd": 0.0058,
        "equal_quality": True,
        "baseline": {"cost_usd": 0.006},
    })

    row = rows_for(ledger)[0]
    measured = engine._aggregate_groups([row])["measured"]

    assert row["baseline"]["eligible"] is True
    assert measured["verifiedSavingsUsd"] == pytest.approx(0.0058)
    assert measured["baselineModelSpendUsd"] == pytest.approx(0.006)


def test_a_paired_baseline_reports_the_calls_it_avoided(ledger):
    """Model calls avoided is a measured difference against a baseline that
    actually ran, not a guess about a run that never happened."""
    ledger.record_proof("run-1", "document_review", UPLOAD_PROOF)
    ledger.record_baseline("run-1", {
        "status": "eligible_saving",
        "saving_claimable": True,
        "saving_usd": 0.0058,
        "equal_quality": True,
        "governed": {"model_calls": 1},
        "baseline": {"cost_usd": 0.006, "model_calls": 8},
    })

    metrics = rows_for(ledger)[0]["metrics"]

    assert metrics["modelCallsAvoided"] == 7


def test_calls_avoided_is_absent_without_a_baseline(ledger):
    """With no baseline there is nothing to have avoided. Reporting 0 would be a
    claim about a comparison that was never run."""
    ledger.record_proof("run-1", "document_review", UPLOAD_PROOF)

    assert "modelCallsAvoided" not in rows_for(ledger)[0]["metrics"]


def test_calls_avoided_never_goes_negative(ledger):
    """A governed run that made more calls than the baseline avoided none. A
    negative count would read as calls conjured from nowhere."""
    ledger.record_proof("run-1", "document_review", UPLOAD_PROOF)
    ledger.record_baseline("run-1", {
        "status": "no_saving",
        "saving_claimable": False,
        "saving_usd": 0.0,
        "equal_quality": True,
        "governed": {"model_calls": 5},
        "baseline": {"cost_usd": 0.006, "model_calls": 1},
    })

    assert rows_for(ledger)[0]["metrics"]["modelCallsAvoided"] == 0


def test_sample_and_measured_evidence_are_never_summed(ledger):
    """Combining them into one total would overstate production spend by the
    cost of every fixture run."""
    ledger.record_proof("run-real", "document_review", UPLOAD_PROOF)
    ledger.record_proof("run-fixture", "document_review", SAMPLE_PROOF)

    groups = engine._aggregate_groups(rows_for(ledger))

    assert groups["measured"]["runCount"] == 1
    assert groups["sample"]["runCount"] == 1
    assert groups["measured"]["governedModelSpendUsd"] == pytest.approx(0.000169)
    assert groups["sample"]["governedModelSpendUsd"] == pytest.approx(0.000169)


def test_a_corrupt_proof_is_skipped_not_fatal(ledger):
    ledger.record_proof("run-good", "document_review", UPLOAD_PROOF)
    with ledger._connect() as connection:  # noqa: SLF001 - deliberate corruption
        connection.execute(
            "INSERT INTO run_proofs (run_id, workflow_id, status, created_at, proof_json)"
            " VALUES ('run-bad', 'document_review', 'completed', ?, 'not json')",
            (UPLOAD_PROOF["created_at"],),
        )
        connection.commit()

    rows = rows_for(ledger)

    assert [row["runId"] for row in rows] == ["run-good"]


def test_source_filter_separates_the_two_run_kinds(ledger):
    ledger.record_proof("run-1", "document_review", UPLOAD_PROOF)

    assert len(engine.reports(source="workflow")["runs"]) == 1
    assert engine.reports(source="optimization")["runs"] == []


def test_an_unknown_source_is_rejected(ledger):
    with pytest.raises(Exception) as error:
        engine.reports(source="nonsense")

    assert getattr(error.value, "status_code", None) == 422


def test_reports_merges_and_sorts_both_stores(ledger):
    ledger.record_proof("run-old", "document_review", {**UPLOAD_PROOF,
                                                       "created_at": "2026-09-01T10:00:00+00:00"})
    ledger.record_proof("run-new", "invoice_triage", {**UPLOAD_PROOF,
                                                      "created_at": "2026-09-09T10:00:00+00:00"})

    runs = engine.reports()["runs"]

    assert [run["runId"] for run in runs] == ["run-new", "run-old"]
