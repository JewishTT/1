"""Alembic migration for worldline reconstruction persistence (feature 015).

Forward-only by policy: revision ``014_temporal_materialization`` is treated as
already released and is never edited. Deployments that already applied 014 must
reach the same schema state as a fresh install that applies every revision in
order (FR-033, SC-012).

Ordering inside ``upgrade`` is deliberate: create tables, then add columns, then
backfill, and only then create indexes -- so no index is ever built against a
column that does not exist yet, and no unique index is created while rows that
would collide inside it are still unbackfilled.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "015_worldline_reconstruction"
down_revision = "014_temporal_materialization"
branch_labels = None
depends_on = None

_ACTIVE_STATUSES = "status IN ('PENDING', 'DISPATCHING', 'FAILED')"


def _identity_fingerprint(identity: dict[str, Any] | None) -> str:
    """Return the canonical identity hash used for active-request uniqueness.

    Intentionally duplicated from the application helper of the same name in
    ``db.materialization_outbox``. A migration must keep producing correct data
    even after application code moves on, so it does not import it. A regression
    test asserts the two implementations agree on a shared fixture set; if this
    function ever changes, that test fails and the migration is corrected rather
    than silently left inconsistent.
    """
    material = json.dumps(
        dict(sorted((identity or {}).items())),
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _backfill_identity_fingerprints() -> int:
    """Populate ``identity_fingerprint`` for rows written before revision 015.

    Must run before the partial unique index is created, otherwise pre-existing
    rows carry a NULL fingerprint and the index cannot enforce one-active-request.
    """
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT outbox_id, identity FROM materialization_outbox "
            "WHERE identity_fingerprint IS NULL"
        )
    ).fetchall()
    if not rows:
        return 0
    bind.execute(
        sa.text(
            "UPDATE materialization_outbox "
            "SET identity_fingerprint = :fp WHERE outbox_id = :oid"
        ),
        [
            {"fp": _identity_fingerprint(identity), "oid": outbox_id}
            for outbox_id, identity in rows
        ],
    )
    return len(rows)


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. New tables
    # ------------------------------------------------------------------
    op.create_table(
        "source_query_set",
        sa.Column("query_set_id", sa.String(96), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("entity_id", sa.String(64), nullable=False),
        sa.Column("identity_fingerprint", sa.String(64), nullable=False),
        sa.Column("surface_digest", sa.String(64), nullable=False),
        sa.Column("query_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("executable_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unsupported_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "source_query",
        sa.Column("query_id", sa.String(96), primary_key=True),
        sa.Column("query_set_id", sa.String(96), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("entity_id", sa.String(64), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("route_kind", sa.String(32), nullable=False),
        sa.Column("query_value", sa.String(512), nullable=False),
        sa.Column("match_type", sa.String(16), nullable=False),
        sa.Column("surt_prefix", sa.String(255)),
        sa.Column("provider", sa.String(32)),
        sa.Column("executable", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("unsupported_reason", sa.String(64)),
        sa.Column("origin_refs", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "reconstruction_frontier",
        sa.Column("frontier_entry_id", sa.String(96), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("entity_id", sa.String(64), nullable=False),
        sa.Column("query_id", sa.String(96), nullable=False),
        sa.Column("partition", sa.String(64), nullable=False),
        sa.Column("page", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="PENDING"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lease_owner", sa.String(128)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("last_page_digest", sa.String(64)),
        sa.Column("last_hit_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("result_ref", sa.String(96)),
        sa.Column("last_error", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("exhausted_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "entity_stream_sequence",
        sa.Column("tenant_id", sa.String(36), primary_key=True),
        sa.Column("entity_id", sa.String(64), primary_key=True),
        sa.Column("next_sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ------------------------------------------------------------------
    # 2. Outbox columns (add, do not index yet)
    # ------------------------------------------------------------------
    op.add_column(
        "materialization_outbox",
        sa.Column("identity_fingerprint", sa.String(64), nullable=True),
    )
    op.add_column(
        "materialization_outbox",
        sa.Column("lease_owner", sa.String(128), nullable=True),
    )
    op.add_column(
        "materialization_outbox",
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "materialization_outbox",
        sa.Column("reclaim_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "materialization_outbox",
        sa.Column("last_outcome", sa.String(32), nullable=True),
    )

    # ------------------------------------------------------------------
    # 3. Backfill before any unique index depends on the new column
    # ------------------------------------------------------------------
    _backfill_identity_fingerprints()

    # ------------------------------------------------------------------
    # 4. Indexes (last, so every column they reference already exists)
    # ------------------------------------------------------------------
    op.create_index(
        "uq_source_query_set_scope",
        "source_query_set",
        ["tenant_id", "entity_id", "identity_fingerprint"],
        unique=True,
    )
    op.create_index("ix_source_query_set_tenant", "source_query_set", ["tenant_id"])
    op.create_index(
        "uq_source_query_identity",
        "source_query",
        ["query_set_id", "route_kind", "query_value"],
        unique=True,
    )
    op.create_index(
        "ix_source_query_entity", "source_query", ["tenant_id", "entity_id"]
    )
    op.create_index(
        "ix_source_query_executable",
        "source_query",
        ["tenant_id", "entity_id", "executable"],
    )
    op.create_index(
        "uq_reconstruction_frontier_unit",
        "reconstruction_frontier",
        ["tenant_id", "entity_id", "query_id", "partition", "page"],
        unique=True,
    )
    op.create_index(
        "ix_reconstruction_frontier_ready",
        "reconstruction_frontier",
        ["tenant_id", "entity_id", "status", "partition", "page"],
    )
    op.create_index(
        "ix_reconstruction_frontier_lease",
        "reconstruction_frontier",
        ["status", "lease_expires_at"],
    )
    op.create_index(
        "ix_reconstruction_frontier_coverage",
        "reconstruction_frontier",
        ["tenant_id", "entity_id", "partition", "status"],
    )
    op.create_index(
        "ix_materialization_outbox_lease",
        "materialization_outbox",
        ["status", "lease_expires_at"],
    )
    # One active request per entity + identity fingerprint, enforced by the
    # database rather than by a racy application-level check (ADR-0020).
    op.create_index(
        "uq_materialization_outbox_active",
        "materialization_outbox",
        ["tenant_id", "entity_id", "identity_fingerprint"],
        unique=True,
        postgresql_where=sa.text(_ACTIVE_STATUSES),
    )


def downgrade() -> None:
    op.drop_index("uq_materialization_outbox_active", table_name="materialization_outbox")
    op.drop_index("ix_materialization_outbox_lease", table_name="materialization_outbox")
    op.drop_index(
        "ix_reconstruction_frontier_coverage", table_name="reconstruction_frontier"
    )
    op.drop_index(
        "ix_reconstruction_frontier_lease", table_name="reconstruction_frontier"
    )
    op.drop_index(
        "ix_reconstruction_frontier_ready", table_name="reconstruction_frontier"
    )
    op.drop_index(
        "uq_reconstruction_frontier_unit", table_name="reconstruction_frontier"
    )
    op.drop_index("ix_source_query_executable", table_name="source_query")
    op.drop_index("ix_source_query_entity", table_name="source_query")
    op.drop_index("uq_source_query_identity", table_name="source_query")
    op.drop_index("ix_source_query_set_tenant", table_name="source_query_set")
    op.drop_index("uq_source_query_set_scope", table_name="source_query_set")
    op.drop_table("entity_stream_sequence")
    op.drop_table("reconstruction_frontier")
    op.drop_table("source_query")
    op.drop_table("source_query_set")
    op.drop_column("materialization_outbox", "last_outcome")
    op.drop_column("materialization_outbox", "reclaim_count")
    op.drop_column("materialization_outbox", "lease_expires_at")
    op.drop_column("materialization_outbox", "lease_owner")
    op.drop_column("materialization_outbox", "identity_fingerprint")

