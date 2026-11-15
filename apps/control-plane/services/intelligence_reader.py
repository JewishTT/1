"""Read-only PostgreSQL adapter for the foundational Intelligence Silo.

This is an adapter over the platform's existing authoritative tables. It creates no
second entity store, graph or observation registry. Every returned record is tenant
scoped and must resolve to an immutable S3 raw-object reference before it can enter
an IntelligenceSnapshot.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import bindparam, text

from shared.contracts.intelligence_feed import (
    EvidenceReference,
    IntelligenceEntity,
    IntelligenceQuery,
    IntelligenceRelation,
    IntelligenceSnapshot,
)


class IntelligenceReadError(RuntimeError):
    """Base class for failures at the Intelligence read boundary."""


class IntelligenceReadDenied(PermissionError, IntelligenceReadError):
    """The caller or declared purpose cannot read the requested Intelligence scope."""


class IntelligenceSubjectNotFound(LookupError, IntelligenceReadError):
    """No tenant-scoped entity exists for the exact requested entity reference."""


class IntelligenceEvidenceUnavailable(IntelligenceReadError):
    """The entity has no resolvable immutable evidence in the durable substrate."""


class IntelligenceSnapshotBudgetExceeded(IntelligenceReadError):
    """A graph expansion exceeded the configured result budget; it was not truncated."""


def _as_aware(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _as_string_list(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (tuple, list)):
        return ()
    return tuple(item for item in value if isinstance(item, str) and item.strip())


class PostgresIntelligenceReadPort:
    """Tenant-bound read port backed by the existing COGNITIVE PostgreSQL substrate.

    connection_factory is the control-plane's existing async session factory.
    allowed_purposes must be selected by the authenticated API boundary; purpose
    strings never grant access on their own. The tenant ID is captured from the verified
    request principal and is never accepted from an HTTP query parameter.
    """

    def __init__(
        self,
        connection_factory: Callable[[], Any],
        *,
        tenant_id: str,
        allowed_purposes: frozenset[str],
        max_entities: int = 250,
        max_relations: int = 1000,
    ) -> None:
        if not tenant_id or not tenant_id.strip():
            raise ValueError("tenant_id must be non-empty")
        if not allowed_purposes:
            raise ValueError("at least one authenticated purpose must be allowed")
        if max_entities < 1 or max_relations < 1:
            raise ValueError("snapshot budgets must be positive")
        self._connections = connection_factory
        self.tenant_id = tenant_id
        self._allowed_purposes = allowed_purposes
        self._max_entities = max_entities
        self._max_relations = max_relations

    async def get_snapshot(self, query: IntelligenceQuery) -> IntelligenceSnapshot:
        if query.tenant_id != self.tenant_id:
            raise IntelligenceReadDenied("query tenant differs from authenticated tenant")
        if query.purpose not in self._allowed_purposes:
            raise IntelligenceReadDenied("purpose is not authorized for this caller")

        async with self._connections() as conn:
            subject_row = await self._entity_by_id(conn, query, query.subject_ref)
            if subject_row is None:
                raise IntelligenceSubjectNotFound(
                    f"entity {query.subject_ref!r} is not present in this tenant"
                )

            entity_rows: dict[str, Any] = {str(subject_row["entity_id"]): subject_row}
            relation_rows: dict[str, Any] = {}
            frontier = {query.subject_ref}

            for _depth in range(query.max_hops):
                if not frontier:
                    break
                claims = await self._relations_for_frontier(conn, query, frontier)
                if len(claims) > self._max_relations:
                    raise IntelligenceSnapshotBudgetExceeded(
                        f"snapshot contains more than {self._max_relations} relationship claims"
                    )

                candidates: set[str] = set()
                for claim in claims:
                    relation_id = str(claim["relation_id"])
                    relation_rows.setdefault(relation_id, claim)
                    source_id = str(claim.get("subject_ref") or "")
                    target_id = str(claim.get("object_ref") or "")
                    candidates.update(
                        value for value in (source_id, target_id) if value and value not in entity_rows
                    )

                if not candidates:
                    frontier = set()
                    continue
                new_entities = await self._entities_by_ids(conn, query, candidates)
                if len(entity_rows) + len(new_entities) > self._max_entities:
                    raise IntelligenceSnapshotBudgetExceeded(
                        f"snapshot contains more than {self._max_entities} entities"
                    )
                entity_rows.update(new_entities)
                frontier = set(new_entities)

            if len(relation_rows) > self._max_relations:
                raise IntelligenceSnapshotBudgetExceeded(
                    f"snapshot contains more than {self._max_relations} relationship claims"
                )

            entity_ids = set(entity_rows)
            entity_observations, relation_contexts = await self._evidence_edges(
                conn, entity_ids, tuple(relation_rows.values())
            )
            observation_ids = set(relation_contexts)
            for refs in entity_observations.values():
                observation_ids.update(refs)

            observations = await self._observations(conn, query, observation_ids)
            evidence_by_id = self._evidence_refs(observations)

            entities: list[IntelligenceEntity] = []
            by_entity_evidence: dict[str, tuple[EvidenceReference, ...]] = {}
            for entity_id, row in entity_rows.items():
                evidence = tuple(
                    evidence_by_id[observation_id]
                    for observation_id in sorted(entity_observations.get(entity_id, set()))
                    if observation_id in evidence_by_id
                )
                if not evidence:
                    continue
                entity = IntelligenceEntity(
                    entity_id=entity_id,
                    entity_type=str(row.get("entity_type") or "unknown"),
                    label=str(row.get("canonical_name") or entity_id),
                    evidence=evidence,
                )
                entities.append(entity)
                by_entity_evidence[entity_id] = evidence

            if query.subject_ref not in by_entity_evidence:
                raise IntelligenceEvidenceUnavailable(
                    "subject exists but has no resolvable immutable S3 evidence reference"
                )

            relations: list[IntelligenceRelation] = []
            for relation_id, row in sorted(relation_rows.items()):
                source_id = str(row.get("subject_ref") or "")
                target_id = str(row.get("object_ref") or "")
                if source_id not in by_entity_evidence or target_id not in by_entity_evidence:
                    continue
                observation_refs = set(_as_string_list(row.get("observation_refs")))
                context_ref = str(row.get("context_ref") or "")
                if context_ref:
                    observation_refs.update(relation_contexts.get(context_ref, ()))
                evidence = tuple(
                    evidence_by_id[observation_id]
                    for observation_id in sorted(observation_refs)
                    if observation_id in evidence_by_id
                )
                if not evidence:
                    continue
                relations.append(
                    IntelligenceRelation(
                        source_entity_id=source_id,
                        predicate=str(row.get("relation_type") or "unknown"),
                        target_entity_id=target_id,
                        evidence=evidence,
                        status=str(row.get("status") or "unreviewed"),
                        confidence=(
                            float(row["confidence"]) if row.get("confidence") is not None else None
                        ),
                        evidence_grade=(
                            str(row["evidence_grade"])
                            if row.get("evidence_grade") is not None
                            else None
                        ),
                        valid_from=_as_aware(row.get("valid_from")),
                        valid_to=_as_aware(row.get("valid_to")),
                    )
                )

        snapshot_material = {
            "tenant_id": self.tenant_id,
            "subject_entity_id": query.subject_ref,
            "as_of": query.as_of.isoformat() if query.as_of else None,
            "entities": [
                {
                    "entity_id": entity.entity_id,
                    "entity_type": entity.entity_type,
                    "label": entity.label,
                    "evidence": [ref.observation_id for ref in entity.evidence],
                }
                for entity in sorted(entities, key=lambda item: item.entity_id)
            ],
            "relations": [
                {
                    "source": relation.source_entity_id,
                    "predicate": relation.predicate,
                    "target": relation.target_entity_id,
                    "status": relation.status,
                    "evidence": [ref.observation_id for ref in relation.evidence],
                }
                for relation in sorted(
                    relations,
                    key=lambda item: (
                        item.source_entity_id,
                        item.predicate,
                        item.target_entity_id,
                    ),
                )
            ],
        }
        snapshot_id = hashlib.sha256(
            json.dumps(snapshot_material, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return IntelligenceSnapshot(
            tenant_id=self.tenant_id,
            snapshot_id=snapshot_id,
            subject_entity_id=query.subject_ref,
            created_at=datetime.now(timezone.utc),
            entities=tuple(sorted(entities, key=lambda item: item.entity_id)),
            relations=tuple(
                sorted(
                    relations,
                    key=lambda item: (
                        item.source_entity_id,
                        item.predicate,
                        item.target_entity_id,
                    ),
                )
            ),
        )

    async def _entity_by_id(self, conn: Any, query: IntelligenceQuery, entity_id: str) -> Any:
        statement = text(
            """
            SELECT entity_id, entity_type, canonical_name, created_at
            FROM entities
            WHERE tenant_id = :tenant_id AND entity_id = :entity_id
              AND (:as_of IS NULL OR created_at <= :as_of)
            LIMIT 1
            """
        )
        return (
            await conn.execute(
                statement,
                {"tenant_id": self.tenant_id, "entity_id": entity_id, "as_of": query.as_of},
            )
        ).mappings().first()

    async def _entities_by_ids(
        self, conn: Any, query: IntelligenceQuery, entity_ids: set[str]
    ) -> dict[str, Any]:
        if not entity_ids:
            return {}
        statement = text(
            """
            SELECT entity_id, entity_type, canonical_name, created_at
            FROM entities
            WHERE tenant_id = :tenant_id AND entity_id IN :entity_ids
              AND (:as_of IS NULL OR created_at <= :as_of)
            """
        ).bindparams(bindparam("entity_ids", expanding=True))
        rows = (
            await conn.execute(
                statement,
                {
                    "tenant_id": self.tenant_id,
                    "entity_ids": sorted(entity_ids),
                    "as_of": query.as_of,
                },
            )
        ).mappings().all()
        return {str(row["entity_id"]): row for row in rows}

    async def _relations_for_frontier(
        self, conn: Any, query: IntelligenceQuery, frontier: set[str]
    ) -> list[Any]:
        statement = text(
            """
            SELECT relation_id, relation_type, subject_ref, object_ref,
                   observation_refs, context_ref, status, confidence, evidence_grade,
                   valid_from, valid_to, created_at
            FROM relation_claim
            WHERE tenant_id = :tenant_id
              AND (subject_ref IN :source_ids OR object_ref IN :target_ids)
              AND (:as_of IS NULL OR created_at <= :as_of)
            ORDER BY created_at DESC, relation_id
            LIMIT :limit_plus_one
            """
        ).bindparams(
            bindparam("source_ids", expanding=True),
            bindparam("target_ids", expanding=True),
        )
        rows = (
            await conn.execute(
                statement,
                {
                    "tenant_id": self.tenant_id,
                    "source_ids": sorted(frontier),
                    "target_ids": sorted(frontier),
                    "as_of": query.as_of,
                    "limit_plus_one": self._max_relations + 1,
                },
            )
        ).mappings().all()
        if len(rows) > self._max_relations:
            raise IntelligenceSnapshotBudgetExceeded(
                f"relationship expansion exceeded {self._max_relations} claims"
            )
        return rows

    async def _evidence_edges(
        self,
        conn: Any,
        entity_ids: set[str],
        relation_rows: tuple[Any, ...],
    ) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
        entity_observations: dict[str, set[str]] = {entity_id: set() for entity_id in entity_ids}
        relation_contexts: dict[str, set[str]] = {}

        if entity_ids:
            statement = text(
                """
                SELECT entity_id, observation_id
                FROM entity_stream
                WHERE tenant_id = :tenant_id AND entity_id IN :entity_ids
                  AND observation_id <> ''
                UNION
                SELECT entity_anchor AS entity_id, observation_id
                FROM evidence_context
                WHERE tenant_id = :tenant_id AND entity_anchor IN :entity_ids
                  AND observation_id <> ''
                """
            ).bindparams(bindparam("entity_ids", expanding=True))
            rows = (
                await conn.execute(
                    statement,
                    {"tenant_id": self.tenant_id, "entity_ids": sorted(entity_ids)},
                )
            ).mappings().all()
            for row in rows:
                entity_observations.setdefault(str(row["entity_id"]), set()).add(
                    str(row["observation_id"])
                )

        context_ids = {
            str(row.get("context_ref") or "")
            for row in relation_rows
            if str(row.get("context_ref") or "")
        }
        if context_ids:
            statement = text(
                """
                SELECT context_id, observation_id
                FROM evidence_context
                WHERE tenant_id = :tenant_id AND context_id IN :context_ids
                  AND observation_id <> ''
                """
            ).bindparams(bindparam("context_ids", expanding=True))
            rows = (
                await conn.execute(
                    statement,
                    {"tenant_id": self.tenant_id, "context_ids": sorted(context_ids)},
                )
            ).mappings().all()
            for row in rows:
                relation_contexts.setdefault(str(row["context_id"]), set()).add(
                    str(row["observation_id"])
                )

        return entity_observations, relation_contexts

    async def _observations(
        self, conn: Any, query: IntelligenceQuery, observation_ids: set[str]
    ) -> list[Any]:
        if not observation_ids:
            return []
        statement = text(
            """
            SELECT o.observation_id, o.source_id, o.uri, o.raw_ref, o.content_hash,
                   o.created_at, s.uri AS source_uri
            FROM observations AS o
            LEFT JOIN sources AS s
              ON s.tenant_id = o.tenant_id AND s.source_id = o.source_id
            WHERE o.tenant_id = :tenant_id
              AND o.observation_id IN :observation_ids
              AND (:as_of IS NULL OR o.created_at <= :as_of)
            """
        ).bindparams(bindparam("observation_ids", expanding=True))
        return (
            await conn.execute(
                statement,
                {
                    "tenant_id": self.tenant_id,
                    "observation_ids": sorted(observation_ids),
                    "as_of": query.as_of,
                },
            )
        ).mappings().all()

    def _evidence_refs(self, rows: list[Any]) -> dict[str, EvidenceReference]:
        found: dict[str, EvidenceReference] = {}
        for row in rows:
            observation_id = str(row.get("observation_id") or "")
            object_uri = str(row.get("raw_ref") or "")
            digest = str(row.get("content_hash") or "").lower()
            recorded_at = _as_aware(row.get("created_at"))
            source_ref = str(row.get("source_uri") or row.get("source_id") or row.get("uri") or "")
            if (
                not observation_id
                or not object_uri.startswith("s3://")
                or re.fullmatch(r"[0-9a-f]{64}", digest) is None
                or recorded_at is None
                or not source_ref
            ):
                continue
            found[observation_id] = EvidenceReference(
                tenant_id=self.tenant_id,
                observation_id=observation_id,
                source_ref=source_ref,
                object_uri=object_uri,
                sha256=digest,
                recorded_at=recorded_at,
            )
        return found


__all__ = [
    "IntelligenceEvidenceUnavailable",
    "IntelligenceReadDenied",
    "IntelligenceReadError",
    "IntelligenceSnapshotBudgetExceeded",
    "IntelligenceSubjectNotFound",
    "PostgresIntelligenceReadPort",
]
