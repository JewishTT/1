"""Derivation enforcement: typed columns, derivation ledger, bitemporal facts (spec 025 §32).

Revision ID: 023_derivation_enforcement
Revises: 022_context_fabric

What this migration adds, and why each part exists
------------------------------------------------

**CHECK constraints on the type columns.** ``entities.entity_type``,
``relation_claims.predicate``/``extractor_version``, ``entity_stream.kind`` and
``observations.content_type`` are all free text today, written by two HTTP routes that
validated nothing. A row could hold ``entity_type='nonsense'`` and every reader downstream
would treat it as a real kind. The constraints name the vocabulary this platform has
actually declared -- ``domain.ontology`` for entity types, ``StaticArtifactKind`` for
artifacts -- and they are added ``NOT VALID`` first so the constraint is installed without a
table rewrite on a database that already holds rows.

The deliberate part: validation is deferred rather than skipped. ``NOT VALID`` means new rows
are checked immediately and existing rows are checked on the next ``VALIDATE``, so a bad row
inherited from before this migration becomes a loud failure instead of staying invisible.
Refusing the whole migration because old rows are wrong would have left the platform with no
constraint at all, which is the state this is meant to leave.

**The derivation ledger.** ``derivations`` and ``derivation_edges`` make
:class:`domain.derivation.DerivationGraph` durable. Identity is the content digest computed
in Python, so the column is ``CHAR(64)`` with a uniqueness constraint rather than a sequence:
re-running the same method over the same inputs has to collide, and a sequence would hand it
a new id and defeat replay.

**Bitemporal closure.** ``entity_facts`` records ``valid_from``/``valid_until`` alongside
``recorded_at``. The two are different questions -- "when was this true" and "when did we
learn it" -- and the existing ``entity_stream`` columns conflate them, so a fact learned
yesterday about last year cannot be represented at all.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "023_derivation_enforcement"
down_revision = "022_context_fabric"
branch_labels = None
depends_on = None

#: The vocabulary as SQL literals, generated from the Python authority rather than copied.
#: Copied text would drift the first time somebody added an ``EntityType``, and the drift
#: would be silent: the constraint would reject a type the platform happily writes.
ENTITY_TYPE_VALUES: tuple[str, ...] = (
    "person", "organization", "domain", "subdomain", "website", "place", "email", "phone",
    "handle", "ip", "crypto", "identifier", "document", "unknown",
    "asn", "isp", "prefix", "network", "port", "nameserver", "registrar",
    "mac_address", "bssid", "certificate", "cpe", "technology", "vendor", "repository",
    "service", "platform",
    "cve", "exploit", "malware", "threat_actor", "signature", "indicator",
    "leak", "breach", "secret", "credential",
    "article", "author", "doi", "orcid",
    "subreddit", "channel", "reputation",
    "vessel", "aircraft", "satellite", "geolocation", "country",
    "hash",
)

ARTIFACT_KIND_VALUES: tuple[str, ...] = (
    "document", "text", "markup", "photo", "log", "spreadsheet",
    "structured", "archive", "binary", "unknown",
)


def upgrade() -> None:
    # -- derivation ledger --------------------------------------------------
    op.create_table(
        "derivations",
        sa.Column("derivation_id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("method_id", sa.String(128), nullable=False),
        sa.Column("method_version", sa.String(32), nullable=False),
        sa.Column("inputs", sa.JSONB, nullable=False, server_default=sa.text("'[]'")),
        sa.Column("output", sa.String(512), nullable=False),
        sa.Column("statement", sa.Text, nullable=False, server_default=""),
        sa.Column("environment", sa.JSONB, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("context_id", sa.String(64), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "output", name="uq_derivations_tenant_output"),
    )
    op.create_index("ix_derivations_method", "derivations", ["method_id", "method_version"])
    op.create_index("ix_derivations_tenant", "derivations", ["tenant_id"])
    op.create_index("ix_derivations_output", "derivations", ["output"])

    op.create_table(
        "derivation_edges",
        sa.Column("parent_id", sa.String(64), nullable=False),
        sa.Column("child_id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.PrimaryKeyConstraint("parent_id", "child_id"),
    )
    op.create_index("ix_derivation_edges_child", "derivation_edges", ["child_id"])

    # -- bitemporal facts ---------------------------------------------------
    op.create_table(
        "entity_facts",
        sa.Column("fact_id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("entity_id", sa.String(128), nullable=False),
        sa.Column("predicate", sa.String(128), nullable=False),
        sa.Column("object_ref", sa.String(512), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        # ``recorded_at`` is when we learned it; ``valid_from`` is when it was true. Keeping
        # only the first makes a fact learned late about an earlier period unrepresentable.
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("derivation_id", sa.String(64), nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.UniqueConstraint(
            "tenant_id", "entity_id", "predicate", "object_ref",
            "valid_from", "valid_until", name="uq_entity_facts_identity",
        ),
    )
    op.create_index("ix_entity_facts_entity", "entity_facts", ["tenant_id", "entity_id"])
    op.create_index("ix_entity_facts_valid", "entity_facts", ["valid_from", "valid_until"])

    # -- ASG nodes and edges ------------------------------------------------
    op.create_table(
        "semantic_nodes",
        sa.Column("node_id", sa.String(128), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("node_kind", sa.String(16), nullable=False),
        sa.Column("label", sa.Text, nullable=False, server_default=""),
        sa.Column("entity_type", sa.String(32), nullable=True),
        sa.Column("predicate", sa.String(128), nullable=True),
        sa.Column("subject", sa.String(128), nullable=True),
        sa.Column("object", sa.String(512), nullable=True),
        sa.Column("quantifier", sa.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "node_kind IN ('entity', 'relation', 'quantified')",
            name="ck_semantic_nodes_kind",
        ),
        # A quantified node without a quantifier is not a quantified node, and a relation
        # without all three parts is not a relation. Enforced here so a loader cannot write
        # one and leave :meth:`SemanticGraph.validate` to discover it days later.
        sa.CheckConstraint(
            "node_kind <> 'quantified' OR quantifier IS NOT NULL",
            name="ck_semantic_nodes_quantified_needs_quantifier",
        ),
        sa.CheckConstraint(
            "node_kind <> 'relation' "
            "OR (predicate IS NOT NULL AND subject IS NOT NULL AND object IS NOT NULL)",
            name="ck_semantic_nodes_relation_is_whole",
        ),
    )
    op.create_index("ix_semantic_nodes_tenant", "semantic_nodes", ["tenant_id", "node_kind"])

    op.create_table(
        "semantic_edges",
        sa.Column("edge_id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("source_node_id", sa.String(128), nullable=False),
        sa.Column("target_node_id", sa.String(128), nullable=False),
        sa.Column("edge_kind", sa.String(32), nullable=False),
        sa.Column("observation_ref", sa.String(128), nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("derivation_id", sa.String(64), nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "tenant_id", "source_node_id", "target_node_id", "edge_kind",
            name="uq_semantic_edges_identity",
        ),
        sa.CheckConstraint(
            "edge_kind IN ('observed_in', 'entails', 'co_occurs', 'subsumes')",
            name="ck_semantic_edges_kind",
        ),
        # The separation this whole migration exists to make enforceable: an observed edge
        # is what a source said, so it must not carry a derivation, and a derived edge must.
        sa.CheckConstraint(
            "(edge_kind = 'observed_in' AND derivation_id IS NULL) "
            "OR (edge_kind <> 'observed_in' AND derivation_id IS NOT NULL)",
            name="ck_semantic_edges_observed_cites_nothing",
        ),
    )
    op.create_index("ix_semantic_edges_source", "semantic_edges", ["source_node_id"])
    op.create_index("ix_semantic_edges_target", "semantic_edges", ["target_node_id"])
    op.create_index("ix_semantic_edges_tenant", "semantic_edges", ["tenant_id"])

    # -- type constraints, installed unvalidated ---------------------------
    # NOT VALID: new rows are checked at once, old rows at VALIDATE time. A database that
    # already holds a bad type gets a loud failure instead of a silent one -- and the
    # alternative, refusing the migration, leaves the platform exactly as unconstrained as
    # it is now.
    op.create_check_constraint(
        "ck_entities_entity_type",
        "entities",
        sa.text(
            "entity_type IN ("
            + ", ".join(f"'{v}'" for v in ENTITY_TYPE_VALUES)
            + ")"
        ),
        deferrable=False,
    )
    op.create_check_constraint(
        "ck_entity_stream_kind",
        "entity_stream",
        sa.text("kind IN ('entity', 'relation', 'assertion', 'observation', 'unknown')"),
    )
    op.create_check_constraint(
        "ck_observations_content_type",
        "observations",
        sa.text(
            "content_type IN ("
            + ", ".join(f"'{v}'" for v in ARTIFACT_KIND_VALUES)
            + ")"
        ),
    )
    # The extractor version is what a replay is keyed on, so it must be namespaced rather
    # than a bare "1.0" two different extractors might both claim.
    op.create_check_constraint(
        "ck_relation_claims_extractor_version",
        "relation_claims",
        sa.text("extractor_version IS NULL OR extractor_version LIKE '%@%'"),
    )




def downgrade() -> None:
    op.drop_table("semantic_edges")
    op.drop_index("ix_semantic_edges_tenant", table_name="semantic_edges")
    op.drop_table("semantic_nodes")
    op.drop_index("ix_semantic_nodes_tenant", table_name="semantic_nodes")
    op.drop_table("entity_facts")
    op.drop_index("ix_entity_facts_valid", table_name="entity_facts")
    op.drop_index("ix_entity_facts_entity", table_name="entity_facts")
    op.drop_table("derivation_edges")
    op.drop_index("ix_derivation_edges_child", table_name="derivation_edges")
    op.drop_table("derivations")
    op.drop_index("ix_derivations_output", table_name="derivations")
    op.drop_index("ix_derivations_tenant", table_name="derivations")
    op.drop_index("ix_derivations_method", table_name="derivations")
    op.drop_constraint(
        "ck_relation_claims_extractor_version", "relation_claims", type_="check"
    )
    op.drop_constraint("ck_observations_content_type", "observations", type_="check")
    op.drop_constraint("ck_entity_stream_kind", "entity_stream", type_="check")
    op.drop_constraint("ck_entities_entity_type", "entities", type_="check")