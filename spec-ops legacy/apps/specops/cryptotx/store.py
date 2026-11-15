"""SQLite ledger for plans, runs, node results and audit events.

The ledger is an audit trail, not a source of key material: plans contain
addresses and amounts, runs contain signed transaction payloads (public by
definition) and errors, and nothing here can unlock the vault. Writes are
synchronous and commit before the API answers, so a crash cannot erase the fact
that a broadcast was attempted.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from specops.cryptotx.errors import StoreError
from specops.cryptotx.models import (
    ExecutionResult,
    NodeResult,
    PlanState,
    TransactionTree,
    now_iso,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS plans (
    plan_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    network TEXT NOT NULL,
    digest TEXT NOT NULL,
    state TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    document TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL,
    plan_digest TEXT NOT NULL,
    dry_run INTEGER NOT NULL,
    state TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    document TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS node_results (
    run_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    state TEXT NOT NULL,
    tx_hash TEXT,
    provider TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    error TEXT,
    document TEXT NOT NULL,
    PRIMARY KEY (run_id, node_id)
);
CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    plan_id TEXT,
    run_id TEXT,
    node_id TEXT,
    detail TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_plan ON runs(plan_id);
CREATE INDEX IF NOT EXISTS idx_audit_plan ON audit(plan_id);
"""


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


class Store:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with closing(self._connect()) as db:
                db.executescript(_SCHEMA)
                db.commit()
        except sqlite3.Error as exc:
            raise StoreError(f"cannot open cryptotx ledger: {exc}") from exc

    def _connect(self) -> sqlite3.Connection:
        try:
            db = sqlite3.connect(str(self.path), timeout=30)
        except sqlite3.Error as exc:
            raise StoreError(f"cannot open cryptotx ledger: {exc}") from exc
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=30000")
        return db

    def _write(self, statement: str, params: tuple[Any, ...]) -> None:
        try:
            with closing(self._connect()) as db:
                db.execute(statement, params)
                db.commit()
        except sqlite3.Error as exc:
            raise StoreError(f"ledger write failed: {exc}") from exc

    def save_plan(self, plan: TransactionTree) -> None:
        now = now_iso()
        self._write(
            """
            INSERT INTO plans(plan_id, name, network, digest, state, created_at,
                              updated_at, document)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(plan_id) DO UPDATE SET
                name=excluded.name,
                network=excluded.network,
                digest=excluded.digest,
                state=excluded.state,
                updated_at=excluded.updated_at,
                document=excluded.document
            """,
            (
                plan.plan_id,
                plan.name,
                plan.network.value,
                plan.digest(),
                plan.state.value,
                plan.created_at,
                now,
                _json(plan.to_dict()),
            ),
        )

    def get_plan(self, plan_id: str) -> TransactionTree | None:
        with closing(self._connect()) as db:
            row = db.execute(
                "SELECT document FROM plans WHERE plan_id = ?", (plan_id,)
            ).fetchone()
        if row is None:
            return None
        try:
            return TransactionTree.from_dict(json.loads(row["document"]))
        except (ValueError, KeyError, TypeError) as exc:
            raise StoreError(f"stored plan {plan_id!r} is corrupt") from exc

    def list_plans(self, *, limit: int = 50) -> list[dict[str, Any]]:
        with closing(self._connect()) as db:
            rows = db.execute(
                """
                SELECT plan_id, name, network, digest, state, created_at, updated_at
                FROM plans ORDER BY created_at DESC LIMIT ?
                """,
                (max(1, min(limit, 500)),),
            ).fetchall()
        return [dict(row) for row in rows]

    def start_run(self, result: ExecutionResult) -> None:
        self._write(
            """
            INSERT INTO runs(run_id, plan_id, plan_digest, dry_run, state,
                             started_at, finished_at, document)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.run_id,
                result.plan_id,
                result.plan_digest,
                int(result.dry_run),
                result.state.value,
                result.started_at,
                result.finished_at,
                _json(result.to_dict()),
            ),
        )

    def save_node_result(self, run_id: str, node: NodeResult) -> None:
        self._write(
            """
            INSERT INTO node_results(run_id, node_id, state, tx_hash, provider,
                                     started_at, finished_at, error, document)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id, node_id) DO UPDATE SET
                state=excluded.state,
                tx_hash=excluded.tx_hash,
                provider=excluded.provider,
                finished_at=excluded.finished_at,
                error=excluded.error,
                document=excluded.document
            """,
            (
                run_id,
                node.node_id,
                node.state.value,
                node.tx_hash,
                node.provider,
                node.started_at,
                node.finished_at,
                node.error,
                _json(node.to_dict()),
            ),
        )

    def finish_run(self, result: ExecutionResult) -> None:
        self._write(
            "UPDATE runs SET state=?, finished_at=?, document=? WHERE run_id=?",
            (
                result.state.value,
                result.finished_at,
                _json(result.to_dict()),
                result.run_id,
            ),
        )

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with closing(self._connect()) as db:
            row = db.execute(
                "SELECT document FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        if row is None:
            return None
        try:
            return json.loads(row["document"])
        except ValueError as exc:
            raise StoreError(f"stored run {run_id!r} is corrupt") from exc

    def list_runs(
        self, *, plan_id: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        query = (
            "SELECT run_id, plan_id, plan_digest, dry_run, state, started_at, "
            "finished_at FROM runs"
        )
        params: list[Any] = []
        if plan_id:
            query += " WHERE plan_id = ?"
            params.append(plan_id)
        query += " ORDER BY started_at DESC LIMIT ?"
        params.append(max(1, min(limit, 500)))
        with closing(self._connect()) as db:
            rows = db.execute(query, tuple(params)).fetchall()
        return [dict(row) for row in rows]

    def audit(
        self,
        actor: str,
        action: str,
        *,
        plan_id: str | None = None,
        run_id: str | None = None,
        node_id: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        self._write(
            """
            INSERT INTO audit(at, actor, action, plan_id, run_id, node_id, detail)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (now_iso(), actor, action, plan_id, run_id, node_id, _json(detail or {})),
        )

    def audit_events(self, *, limit: int = 100) -> list[dict[str, Any]]:
        with closing(self._connect()) as db:
            rows = db.execute(
                """
                SELECT id, at, actor, action, plan_id, run_id, node_id, detail
                FROM audit ORDER BY id DESC LIMIT ?
                """,
                (max(1, min(limit, 1000)),),
            ).fetchall()
        events: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            try:
                item["detail"] = json.loads(item["detail"])
            except ValueError:
                item["detail"] = {}
            events.append(item)
        return events

    def stats(self) -> dict[str, Any]:
        with closing(self._connect()) as db:
            plans = db.execute("SELECT COUNT(*) FROM plans").fetchone()[0]
            runs = db.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
            by_state = {
                row["state"]: row["count"]
                for row in db.execute(
                    "SELECT state, COUNT(*) AS count FROM runs GROUP BY state"
                ).fetchall()
            }
        return {
            "plans": plans,
            "runs": runs,
            "runs_by_state": by_state,
            "ledger": str(self.path),
        }


def plan_state_from_results(results: list[NodeResult]) -> PlanState:
    failed = any(item.state.value == "failed" for item in results)
    succeeded = any(item.state.value == "succeeded" for item in results)
    if failed:
        return PlanState.PARTIAL if succeeded else PlanState.FAILED
    return PlanState.COMPLETED if succeeded else PlanState.FAILED
