"""Durable persistence for the context fabric.

``control-plane`` is the only writer of durable context state (spec 025 plan.md), so
the fabric's output is written here and nowhere else. The fabric itself in
``apps/science/context/fabric.py`` stays pure and knows nothing about storage -- which
is what lets the same pass be replayed, diffed, or tested without a database.

The load/save asymmetry is deliberate. Cells, propositions and contradictions are
written every pass and read back on the next one, so repeated passes accumulate into
one growing structure. Reports are write-mostly: they exist so a reader can ask why
the obligation ledger says what it says, and they are read back only on demand.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from hashlib import sha256
from typing import Any

from context.epistemic import Contradiction, Proposition
from context.fabric import FabricReport
from context.locality import CellKind, ContextCell, Scope, ScopeKind


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _digest(payload: Any) -> str:
    return sha256(_json(payload).encode("utf-8")).hexdigest()[:12]


def cell_from_payload(payload: dict[str, Any]) -> ContextCell:
    """Rebuild a cell from its stored form.

    Written against the stored shape rather than a dataclass round-trip because the
    scope is a nested object: reconstructing it explicitly is the only way to notice
    when the stored shape and the type have drifted.
    """
    scope_payload = payload.get("scope") or {}
    scope = Scope(
        kind=ScopeKind(scope_payload.get("kind", "entity")),
        members=frozenset(scope_payload.get("members") or ()),
        unknown=bool(scope_payload.get("unknown", False)),
        qualifier=str(scope_payload.get("qualifier", "")),
    )
    return ContextCell(
        context_id=payload["context_id"],
        kind=CellKind(payload.get("kind", "document")),
        scope=scope,
        cell_id=payload.get("cell_id", ""),
        parent_cell=payload.get("parent_cell", ""),
        temporal_slice=tuple(payload.get("temporal_slice") or ()),
        observation_refs=tuple(payload.get("observation_refs") or ()),
        entity_refs=tuple(payload.get("entity_refs") or ()),
        relation_refs=tuple(payload.get("relation_refs") or ()),
        state_refs=tuple(payload.get("state_refs") or ()),
        semantic_regime_ref=str(payload.get("semantic_regime_ref", "")),
        completeness=payload.get("completeness") or {},
        trust_state=str(payload.get("trust_state", "unknown")),
        produced_by=str(payload.get("produced_by", "")),
        method_fingerprint=str(payload.get("method_fingerprint", "")),
    )


#: Indexes installed alongside the tables, mirroring ``022_context_fabric`` and
#: ``db.schema``. ``parent_cell`` is indexed because every "everything under X" query is a
#: descent through it, which is the query a deepening investigation asks most.
_INDEX_DDL: tuple[str, ...] = (
    "CREATE INDEX IF NOT EXISTS ix_context_cells_context ON context_cells (context_id)",
    "CREATE INDEX IF NOT EXISTS ix_context_cells_parent ON context_cells (parent_cell)",
    "CREATE INDEX IF NOT EXISTS ix_context_cells_tenant ON context_cells (tenant_id)",
    "CREATE INDEX IF NOT EXISTS ix_fabric_reports_context ON fabric_reports (context_id)",
    "CREATE INDEX IF NOT EXISTS ix_fabric_reports_tenant ON fabric_reports (tenant_id)",
    (
        "CREATE INDEX IF NOT EXISTS ix_fabric_reports_context_created"
        " ON fabric_reports (context_id, created_at)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_context_propositions_context"
        " ON context_propositions (context_id)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_context_propositions_truth"
        " ON context_propositions (truth_state)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_context_contradictions_proposition"
        " ON context_contradictions (proposition_id)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_context_contradictions_context"
        " ON context_contradictions (context_id)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_context_contradictions_status"
        " ON context_contradictions (status)"
    ),
)

class FabricStore:
    """Load and save fabric artifacts against a :class:`ContextStore`.

    Writes and reads are delegated to the store's own ``_write`` / ``_all`` rather than
    reimplemented. That is not brevity: the store is the one place that knows how to
    speak to whichever async driver it was wired with, and a second SQL path here would
    be a second set of dialect bugs -- which is exactly what happened the first time
    this class opened its own connections.
    """

    def __init__(self, store: Any, *, tenant_id: str = "") -> None:
        self._store = store
        self._tenant_id = tenant_id

    # -- SQL ----------------------------------------------------------------

    async def _write(self, statement: str, params: dict[str, Any]) -> None:
        await self._store._write(statement, params)

    async def _read(self, statement: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        return await self._store._all(statement, params)

    async def _create(self, statement: str) -> None:
        """Run DDL through the store's driver-aware path.

        ``_write`` would also work, but schema creation is not a domain write and
        keeping it separate means the store's write path never carries DDL.
        """
        async with self._store._session() as handle:
            await self._store._exec(handle, statement, None)

    async def ensure_schema(self) -> None:
        """Idempotent DDL, matching ``022_context_fabric`` and ``db.schema`` exactly.

        The three install paths -- ``alembic upgrade head``, ``Base.metadata.create_all``
        and this -- must produce one schema, or a database bootstrapped at runtime is
        quietly missing what a migrated one has. The indexes below were missing here
        while the migration and the ORM both had them, which is exactly that divergence;
        ``tests/integration/test_orm_migration_parity.py`` is the guard.
        """
        await self._create(
            """
            CREATE TABLE IF NOT EXISTS context_cells (
                cell_id    VARCHAR(64) PRIMARY KEY,
                context_id VARCHAR(36) NOT NULL,
                tenant_id  VARCHAR(36) NOT NULL,
                parent_cell VARCHAR(64),
                kind       VARCHAR(32) NOT NULL,
                payload    JSONB NOT NULL,
                created_at TIMESTAMPTZ DEFAULT now(),
                CONSTRAINT uq_context_cells_identity UNIQUE (context_id, cell_id)
            )
            """,
        )
        await self._create(
            """
            CREATE TABLE IF NOT EXISTS fabric_reports (
                report_id  VARCHAR(64) PRIMARY KEY,
                context_id VARCHAR(36) NOT NULL,
                tenant_id  VARCHAR(36) NOT NULL,
                revision_id VARCHAR(64),
                payload    JSONB NOT NULL,
                created_at TIMESTAMPTZ DEFAULT now()
            )
            """,
        )
        await self._create(
            """
            CREATE TABLE IF NOT EXISTS context_propositions (
                proposition_id VARCHAR(64) PRIMARY KEY,
                context_id     VARCHAR(36) NOT NULL,
                tenant_id      VARCHAR(36) NOT NULL,
                truth_state    VARCHAR(16) NOT NULL,
                payload        JSONB NOT NULL,
                created_at     TIMESTAMPTZ DEFAULT now()
            )
            """,
        )
        await self._create(
            """
            CREATE TABLE IF NOT EXISTS context_contradictions (
                contradiction_id VARCHAR(64) PRIMARY KEY,
                proposition_id  VARCHAR(64) NOT NULL,
                context_id      VARCHAR(36) NOT NULL,
                tenant_id       VARCHAR(36) NOT NULL,
                status          VARCHAR(16) NOT NULL,
                payload         JSONB NOT NULL,
                created_at      TIMESTAMPTZ DEFAULT now()
            )
            """,
        )
        for statement in _INDEX_DDL:
            await self._create(statement)

    # -- cells ----------------------------------------------------------------

    async def save_cells(self, cells: Sequence[ContextCell]) -> int:
        """Upsert by content address, so a re-derived cell overwrites its own row."""
        if not cells:
            return 0
        await self.ensure_schema()
        for cell in cells:
            payload = cell.as_dict()
            await self._write(
                """
                INSERT INTO context_cells
                    (cell_id, context_id, tenant_id, parent_cell, kind, payload)
                VALUES (:cid, :ctx, :tenant, :parent, :kind, CAST(:payload AS jsonb))
                ON CONFLICT (cell_id) DO UPDATE SET payload = EXCLUDED.payload
                """,
                {
                    "cid": cell.cell_id,
                    "ctx": cell.context_id,
                    "tenant": self._tenant_id,
                    "parent": cell.parent_cell or None,
                    "kind": cell.kind.value,
                    "payload": _json(payload),
                },
            )
        return len(cells)

    async def load_cells(self, context_id: str) -> tuple[ContextCell, ...]:
        """All cells of a context, parents before children so ancestry resolves."""
        await self.ensure_schema()
        rows = await self._read(
            """
            SELECT payload FROM context_cells
            WHERE context_id = :ctx
            ORDER BY (parent_cell IS NOT NULL), cell_id
            """,
            {"ctx": context_id},
        )
        return tuple(cell_from_payload(row) for row in rows)

    # -- epistemic state ------------------------------------------------------

    async def save_propositions(
        self, propositions: Sequence[Proposition], *, context_id: str
    ) -> int:
        """Persist epistemic state.

        ``context_id`` is an explicit argument rather than read off
        ``proposition.scope``: scope is the domain region a claim is about, and using it
        as the row key filed every claim under a region name. It happens to coincide in
        the fabric pass because that pass sets scope to the context id, which is exactly
        what made the bug invisible until a caller passed real scopes.
        """
        if not propositions:
            return 0
        await self.ensure_schema()
        for proposition in propositions:
            payload = proposition.as_dict()
            await self._write(
                """
                INSERT INTO context_propositions
                    (proposition_id, context_id, tenant_id, truth_state, payload)
                VALUES (:pid, :ctx, :tenant, :truth, CAST(:payload AS jsonb))
                ON CONFLICT (proposition_id) DO UPDATE
                    SET truth_state = EXCLUDED.truth_state, payload = EXCLUDED.payload
                """,
                {
                    "pid": proposition.proposition_id,
                    "ctx": context_id,
                    "tenant": self._tenant_id,
                    "truth": proposition.truth_state.value,
                    "payload": _json(payload),
                },
            )
        return len(propositions)

    async def load_propositions(self, context_id: str) -> tuple[dict[str, Any], ...]:
        await self.ensure_schema()
        rows = await self._read(
            "SELECT payload FROM context_propositions WHERE context_id = :ctx ORDER BY proposition_id",
            {"ctx": context_id},
        )
        return tuple(row for row in rows)

    async def save_contradictions(
        self, contradictions: Sequence[Contradiction], *, context_id: str
    ) -> int:
        if not contradictions:
            return 0
        await self.ensure_schema()
        for contradiction in contradictions:
            payload = contradiction.as_dict()
            await self._write(
                """
                INSERT INTO context_contradictions
                    (contradiction_id, proposition_id, context_id, tenant_id, status, payload)
                VALUES (:cid, :pid, :ctx, :tenant, :status, CAST(:payload AS jsonb))
                ON CONFLICT (contradiction_id) DO UPDATE
                    SET status = EXCLUDED.status, payload = EXCLUDED.payload
                """,
                {
                    "cid": contradiction.contradiction_id,
                    "pid": contradiction.proposition_id,
                    "ctx": context_id,
                    "tenant": self._tenant_id,
                    "status": contradiction.status.value,
                    "payload": _json(payload),
                },
            )
        return len(contradictions)

    async def load_contradictions(self, context_id: str) -> tuple[dict[str, Any], ...]:
        await self.ensure_schema()
        rows = await self._read(
            """
            SELECT payload FROM context_contradictions
            WHERE context_id = :ctx ORDER BY contradiction_id
            """,
            {"ctx": context_id},
        )
        return tuple(row for row in rows)

    # -- reports --------------------------------------------------------------

    async def save_report(self, report: FabricReport, *, revision_id: str = "") -> str:
        """Persist one whole pass. The id is content-addressed over the report body."""
        await self.ensure_schema()
        body = report.as_dict()
        report_id = f"FR-{_digest(body)}"
        await self._write(
            """
            INSERT INTO fabric_reports
                (report_id, context_id, tenant_id, revision_id, payload)
            VALUES (:rid, :ctx, :tenant, :rev, CAST(:payload AS jsonb))
            ON CONFLICT (report_id) DO UPDATE SET payload = EXCLUDED.payload
            """,
            {
                "rid": report_id,
                "ctx": report.context_id,
                "tenant": self._tenant_id,
                "rev": revision_id or None,
                "payload": _json(body),
            },
        )
        return report_id

    async def load_report(self, report_id: str) -> dict[str, Any] | None:
        await self.ensure_schema()
        rows = await self._read(
            "SELECT payload FROM fabric_reports WHERE report_id = :rid",
            {"rid": report_id},
        )
        return rows[0] if rows else None

    async def latest_report(self, context_id: str) -> dict[str, Any] | None:
        await self.ensure_schema()
        rows = await self._read(
            """
            SELECT payload FROM fabric_reports
            WHERE context_id = :ctx ORDER BY created_at DESC LIMIT 1
            """,
            {"ctx": context_id},
        )
        return rows[0] if rows else None

    async def link_report_revision(self, report_id: str, revision_id: str) -> None:
        """Attach an engine revision to a report already written.

        The fabric pass runs *before* ``engine.ingest`` so a contradiction it finds can
        be answered in the same tick; that ordering means the revision does not exist yet
        when the report is written. Linking afterwards keeps both properties: the report
        is durable before anything can fail, and it still ends up attributable.
        """
        await self._write(
            "UPDATE fabric_reports SET revision_id = :rev WHERE report_id = :rid",
            {"rev": revision_id, "rid": report_id},
        )
