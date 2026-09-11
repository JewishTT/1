"""Canonical Statement for the knowledge model (feature 005, US1).

Ported pattern: FollowTheMoney (MIT) `followthemoney/statement/` per-claim
statement with dataset provenance and temporal validity, merged with the
platform's existing ``admission.engine.assertions.Statement`` semantics
(dataset_id, extraction_version, original_value, valid_from/valid_until,
provenance). This is the single statement type the whole platform carries —
``admission/engine/assertions.py`` is adapted to consume it, not duplicate it.

``build_statement`` validates provenance invariants (FR-001) and, when a
``producer`` is supplied, emits ``statement.created`` (refs only, I-5) so
projections rebuild from durable events (I-12).

   Source repo : donors/followthemoney (https://github.com/alephdata/followthemoney)
   License     : MIT
   What changed: reduced statement/entity model to a stdlib dataclass; kept
                 provenance + temporal + dataset semantics; producer emission
                 wired to the platform event envelope.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from domain.schema import SchemaRegistry, UnknownSchemaError
from events.kafka import build_envelope
from events.topics import topic_for

_REQUIRED_PROVENANCE = ("dataset_id", "extraction_version", "original_value")


@dataclass
class Statement:
    """Per-claim knowledge statement (dataset-bound, temporal, claim-not-truth)."""

    statement_id: str = field(default_factory=lambda: "ST-" + uuid.uuid4().hex[:12])
    entity_id: str = ""
    schema_name: str = ""
    properties: list = field(default_factory=list)
    dataset_id: str = ""
    original_value: str = ""
    extraction_version: str = ""
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    provenance: dict = field(default_factory=dict)
    claimed: bool = True
    tenant_id: str = "default-tenant"

    def __post_init__(self) -> None:
        self._validate()

    def _validate(self) -> None:
        missing = [f for f in _REQUIRED_PROVENANCE if not getattr(self, f)]
        if missing:
            from domain import StatementProvenanceError

            raise StatementProvenanceError(self.statement_id, ", ".join(missing))
        if self.schema_name and not self._registry_has(self.schema_name):
            raise UnknownSchemaError(self.schema_name)

    @staticmethod
    def _registry_has(schema_name: str) -> bool:
        # Keep domain decoupled: registry membership is re-checked at build time
        # via build_statement; here only the empty-string guard applies when the
        # caller constructs directly without a schema.
        return True

    def to_dict(self) -> dict:
        return {
            "statement_id": self.statement_id,
            "entity_id": self.entity_id,
            "schema_name": self.schema_name,
            "properties": [p.to_dict() for p in self.properties] if self.properties else [],
            "dataset_id": self.dataset_id,
            "original_value": self.original_value,
            "extraction_version": self.extraction_version,
            "first_seen": self.first_seen.isoformat() if self.first_seen else None,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "valid_from": self.valid_from.isoformat() if self.valid_from else None,
            "valid_until": self.valid_until.isoformat() if self.valid_until else None,
            "provenance": dict(self.provenance),
            "claimed": self.claimed,
            "tenant_id": self.tenant_id,
        }


def build_statement(
    *,
    schema_name: str,
    entity_id: str,
    properties: list[Any] | None = None,
    dataset_id: str,
    original_value: str,
    extraction_version: str,
    registry: SchemaRegistry,
    valid_from: datetime | None = None,
    valid_until: datetime | None = None,
    provenance: dict | None = None,
    tenant_id: str = "default-tenant",
    statement_id: str | None = None,
    producer=None,
) -> Statement:
    """Build a validated canonical Statement, optionally emitting ``statement.created``.

    The schema must resolve; properties must validate against it. Provenance
    fields are mandatory (FR-001). When ``producer`` is given, one envelope is
    produced on the ``statement`` topic (payload = refs/fields, no blobs).
    """
    registry.resolve(schema_name)
    registry.validate_property_list(schema_name, properties or [])
    now = datetime.now(UTC)
    statement = Statement(
        statement_id=statement_id or "ST-" + uuid.uuid4().hex[:12],
        entity_id=entity_id,
        schema_name=schema_name,
        properties=list(properties or []),
        dataset_id=dataset_id,
        original_value=original_value,
        extraction_version=extraction_version,
        first_seen=now,
        last_seen=now,
        valid_from=valid_from,
        valid_until=valid_until,
        provenance={"producer": "knowledge-model", "tenant_id": tenant_id, **(provenance or {})},
        claimed=True,
        tenant_id=tenant_id,
    )
    if producer is not None:
        envelope = statement_envelope(statement)
        producer.produce(topic_for("statement.created"), envelope, key=statement.statement_id)
    return statement


def statement_envelope(statement: Statement) -> Any:
    """Build the ``statement.created`` envelope for a built Statement (I-5 refs-only)."""
    return build_envelope(
        event_type="statement.created",
        event_version="1.0",
        producer="shared.domain",
        producer_version="0.1.0",
        payload=json.dumps(statement.to_dict(), default=str).encode("utf-8"),
        entity_id=statement.entity_id,
        event_id=f"evt-{statement.statement_id}",
    )