from __future__ import annotations

import json
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException

from ..config import settings


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def tenant_id() -> str:
    # This API is single-tenant. Tenant identity comes from server configuration,
    # never a browser header or a caller-supplied request property.
    return os.getenv("TOKENOS_TENANT_ID", "local")


class OptimizationStore:
    def __init__(self, path: Path | None = None):
        self._path = path

    @contextmanager
    def db(self):
        path = self._path or settings.storage_root / "optimization.sqlite3"
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS optimization_runs
              (id TEXT PRIMARY KEY, tenant TEXT NOT NULL, status TEXT NOT NULL,
               created TEXT NOT NULL, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS optimization_events
              (run_id TEXT NOT NULL, sequence INTEGER NOT NULL, body TEXT NOT NULL,
               PRIMARY KEY(run_id,sequence));
            CREATE TABLE IF NOT EXISTS optimization_files
              (id TEXT PRIMARY KEY, tenant TEXT NOT NULL, metadata TEXT NOT NULL, content BLOB NOT NULL);
            CREATE TABLE IF NOT EXISTS optimization_claims
              (run_id TEXT NOT NULL, kind TEXT NOT NULL, created TEXT NOT NULL,
               PRIMARY KEY(run_id,kind));
        """)
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def save(self, run: dict) -> None:
        with self.db() as db:
            db.execute(
                "INSERT INTO optimization_runs VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE "
                "SET status=excluded.status,body=excluded.body",
                (run["runId"], run["_tenant"], run["status"], run["createdAt"], json.dumps(run, allow_nan=False)),
            )

    def get(self, run_id: str) -> dict | None:
        with self.db() as db:
            row = db.execute("SELECT body FROM optimization_runs WHERE id=? AND tenant=?",
                             (run_id, tenant_id())).fetchone()
        return json.loads(row["body"]) if row else None

    def require(self, run_id: str) -> dict:
        run = self.get(run_id)
        if run is None:
            raise HTTPException(404, "Run not found.")
        return run

    def event(self, run: dict, kind: str, data: dict | None = None) -> dict:
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            seq = db.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM optimization_events WHERE run_id=?",
                             (run["runId"],)).fetchone()[0]
            event = {"sequence": seq, "runId": run["runId"], "at": now(), "type": kind, **(data or {})}
            db.execute("INSERT INTO optimization_events VALUES (?,?,?)", (run["runId"], seq, json.dumps(event)))
        run["lastSequence"] = seq
        self.save(run)
        return event

    def events(self, run_id: str, after: int = 0) -> list[dict]:
        with self.db() as db:
            rows = db.execute("SELECT body FROM optimization_events WHERE run_id=? AND sequence>? ORDER BY sequence",
                              (run_id, after)).fetchall()
        return [json.loads(row["body"]) for row in rows]

    def claim(self, run_id: str, kind: str) -> None:
        try:
            with self.db() as db:
                db.execute("INSERT INTO optimization_claims VALUES (?,?,?)", (run_id, kind, now()))
        except sqlite3.IntegrityError as error:
            raise HTTPException(409, f"A {kind} is already active or was already executed. Create a new versioned run.") from error

    def history(self, limit: int = 200) -> list[dict]:
        with self.db() as db:
            rows = db.execute("SELECT body FROM optimization_runs WHERE tenant=? ORDER BY created DESC LIMIT ?",
                              (tenant_id(), max(1, min(limit, 1000)))).fetchall()
        return [json.loads(row["body"]) for row in rows]

    def put_file(self, metadata: dict, content: bytes) -> dict:
        metadata = {"fileId": f"file_{secrets.token_hex(8)}", **metadata}
        with self.db() as db:
            db.execute("INSERT INTO optimization_files VALUES (?,?,?,?)",
                       (metadata["fileId"], tenant_id(), json.dumps(metadata), content))
        return metadata

    def file(self, file_id: str) -> tuple[dict, bytes]:
        with self.db() as db:
            row = db.execute("SELECT metadata,content FROM optimization_files WHERE id=? AND tenant=?",
                             (file_id, tenant_id())).fetchone()
        if not row:
            raise HTTPException(422, "An input artifact is missing or outside the authorized tenant scope.")
        return json.loads(row["metadata"]), row["content"]


store = OptimizationStore()


def public_state(run: dict) -> dict:
    return {key: value for key, value in run.items() if not key.startswith("_")}
