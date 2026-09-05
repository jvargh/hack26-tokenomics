"""Durable run ledger.

`storage/runs.py` holds live run state in memory so the event stream can fan out to
a connected browser with no I/O in the hot path. That store is cleared on restart,
which is fine for driving a single session but is not a record an enterprise
reporting view or an auditor could rely on.

This module is the persisted side: every completed proof, and every baseline
comparison computed against it, is written to a local SQLite file so historical
measured cost, route counts, and verified-saving outcomes survive a restart and can
be queried later. It never generates data — it only durably stores what a run
already measured.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import Lock

from ..config import settings

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS run_proofs (
    run_id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    status TEXT NOT NULL,
    measurement_label TEXT,
    quality_passed INTEGER,
    model_calls INTEGER,
    operations_total INTEGER,
    without_generative_ai INTEGER,
    input_tokens INTEGER,
    output_tokens INTEGER,
    calculated_cost_usd REAL,
    created_at TEXT NOT NULL,
    proof_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS run_baselines (
    run_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    saving_claimable INTEGER,
    saving_usd REAL,
    equal_quality INTEGER,
    recorded_at TEXT NOT NULL,
    comparison_json TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES run_proofs(run_id)
);
"""


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


class RunLedger:
    """Thread-safe wrapper around a single SQLite file used as the durable ledger."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or (settings.storage_root / "tokenos_ledger.sqlite3")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._migrate()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        return connection

    def _migrate(self) -> None:
        with self._lock, self._connect() as connection:
            connection.executescript(_SCHEMA)
            row = connection.execute(
                "SELECT value FROM schema_meta WHERE key = 'version'"
            ).fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO schema_meta (key, value) VALUES ('version', ?)",
                    (str(SCHEMA_VERSION),),
                )
            connection.commit()

    def record_proof(self, run_id: str, workflow_id: str, proof: dict) -> None:
        """Persists a completed run's proof. Called once, when the run finishes."""
        usage = proof.get("usage", {})
        economics = proof.get("economics", {})
        outcome = proof.get("outcome", {})
        routing = proof.get("routing", {})
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO run_proofs (
                    run_id, workflow_id, status, measurement_label, quality_passed,
                    model_calls, operations_total, without_generative_ai,
                    input_tokens, output_tokens, calculated_cost_usd, created_at, proof_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    status = excluded.status,
                    proof_json = excluded.proof_json
                """,
                (
                    run_id,
                    workflow_id,
                    str(proof.get("status", "")),
                    proof.get("measurement_label"),
                    1 if outcome.get("quality_passed") else 0,
                    int(usage.get("model_calls", 0)),
                    int(routing.get("operations", 0)),
                    int(routing.get("completed_without_generative_ai", 0)),
                    int(usage.get("input_tokens", 0)),
                    int(usage.get("output_tokens", 0)),
                    float(economics.get("total_calculated_cost_usd", 0.0)),
                    _now(),
                    json.dumps(proof, default=str),
                ),
            )
            connection.commit()

    def record_baseline(self, run_id: str, comparison: dict) -> None:
        """Persists a computed baseline comparison, keyed to its governed run."""
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO run_baselines (
                    run_id, status, saving_claimable, saving_usd, equal_quality,
                    recorded_at, comparison_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    status = excluded.status,
                    saving_claimable = excluded.saving_claimable,
                    saving_usd = excluded.saving_usd,
                    equal_quality = excluded.equal_quality,
                    recorded_at = excluded.recorded_at,
                    comparison_json = excluded.comparison_json
                """,
                (
                    run_id,
                    str(comparison.get("status", "")),
                    1 if comparison.get("saving_claimable") else 0,
                    comparison.get("saving_usd"),
                    1 if comparison.get("equal_quality") else 0,
                    _now(),
                    json.dumps(comparison, default=str),
                ),
            )
            connection.commit()

    def report(self, limit: int = 200) -> list[dict]:
        """Enterprise reporting view: one row per persisted run, joined with its
        baseline outcome when one exists."""
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    p.run_id, p.workflow_id, p.status, p.measurement_label,
                    p.quality_passed, p.model_calls, p.operations_total,
                    p.without_generative_ai, p.input_tokens, p.output_tokens,
                    p.calculated_cost_usd, p.created_at,
                    b.status AS baseline_status, b.saving_claimable, b.saving_usd,
                    b.equal_quality
                FROM run_proofs p
                LEFT JOIN run_baselines b ON b.run_id = p.run_id
                ORDER BY p.created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def summary(self) -> dict:
        """Aggregate measures across every persisted run, for the reporting card."""
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    COUNT(*) AS total_runs,
                    COALESCE(SUM(model_calls), 0) AS total_model_calls,
                    COALESCE(SUM(operations_total), 0) AS total_operations,
                    COALESCE(SUM(without_generative_ai), 0) AS total_without_generative_ai,
                    COALESCE(SUM(calculated_cost_usd), 0.0) AS total_measured_cost_usd
                FROM run_proofs
                """
            ).fetchone()
            saving_row = connection.execute(
                """
                SELECT
                    COUNT(*) AS verified_savings,
                    COALESCE(SUM(saving_usd), 0.0) AS total_verified_saving_usd
                FROM run_baselines
                WHERE status = 'eligible_saving' AND saving_claimable = 1
                """
            ).fetchone()
        return {
            "total_runs": row["total_runs"],
            "total_model_calls": row["total_model_calls"],
            "total_operations": row["total_operations"],
            "total_without_generative_ai": row["total_without_generative_ai"],
            "total_measured_cost_usd": round(row["total_measured_cost_usd"], 6),
            "verified_savings_count": saving_row["verified_savings"],
            "total_verified_saving_usd": round(saving_row["total_verified_saving_usd"], 6),
        }


ledger_store = RunLedger()
