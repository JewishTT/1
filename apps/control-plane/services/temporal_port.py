"""The port through which control-plane writes into the temporal graph.

Layering note: control-plane must not import projection -- that is a dependency
edge the layer guard rightly forbids. So the *shape* of a temporal sink is declared
here, structurally, and the ClickHouse implementation in
``apps/projection/analytics/temporal_graph.py`` satisfies it without either side
importing the other. Anything with a matching ``ingest`` method is a valid sink.

This is the same discipline as the other stores: the caller depends on a contract,
never on a vendor class.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class TemporalSink(Protocol):
    """Anything that can durably record entity events with validity intervals."""

    async def ingest(self, events: Sequence[Any]) -> int: ...


class EntityEvent:
    """A single assertion about one entity, with when it was true.

    Deliberately not the ClickHouse row and not ``domain.dynamics.StreamRecord``: this
    is the boundary shape, so the temporal store can change its physical schema
    without every producer in the platform changing with it.
    """

    __slots__ = (
        "tenant_id",
        "entity_id",
        "kind",
        "entity_class",
        "observation_id",
        "dataset_id",
        "sequence",
        "extraction_version",
        "ts",
        "valid_from",
        "valid_until",
        "payload",
    )

    def __init__(
        self,
        *,
        tenant_id: str,
        entity_id: str,
        kind: str,
        entity_class: str = "unknown",
        observation_id: str = "",
        dataset_id: str = "",
        sequence: int = 0,
        extraction_version: str = "",
        ts: datetime | None = None,
        valid_from: datetime | None = None,
        valid_until: datetime | None = None,
        payload: Mapping[str, Any] | None = None,
    ) -> None:
        self.tenant_id = tenant_id
        self.entity_id = entity_id
        self.kind = kind
        self.entity_class = entity_class
        self.observation_id = observation_id
        self.dataset_id = dataset_id
        self.sequence = sequence
        self.extraction_version = extraction_version
        self.ts = ts
        self.valid_from = valid_from
        self.valid_until = valid_until
        self.payload = dict(payload or {})


def events_for_entity(
    *,
    tenant_id: str,
    entity_id: str,
    entity_class: str,
    observation_ids: Sequence[str],
    attributes: Mapping[str, Any],
    observed_at: datetime | None = None,
    extraction_version: str = "",
    kind: str = "mention",
) -> list[EntityEvent]:
    """One event per observation that saw this entity.

    One row per observation rather than one per entity is deliberate: the graph's
    temporality is "who saw this, and when". Collapsing to a single row would throw
    away the evidence trail that makes a belief contestable.
    """
    return [
        EntityEvent(
            tenant_id=tenant_id,
            entity_id=entity_id,
            kind=kind,
            entity_class=entity_class,
            observation_id=obs,
            sequence=index,
            extraction_version=extraction_version,
            valid_from=observed_at,
            payload=attributes,
        )
        for index, obs in enumerate(observation_ids)
    ]


def events_for_relation(
    *,
    tenant_id: str,
    subject_id: str,
    object_id: str,
    predicate: str,
    observation_ids: Sequence[str],
    confidence: float,
    observed_at: datetime | None = None,
    extraction_version: str = "",
) -> list[EntityEvent]:
    """A relation asserted about its subject, with the object as an attribute.

    Recorded on the subject because a temporal graph has to answer "what did this
    entity relate to, as of when" -- the subject is the entity being queried.

    Attributes are deliberately flat scalars. A nested ``{"relation": {...}}`` would
    land on the event stream but produce no validity row, because an interval over a
    nested structure asserts more than the data says; flattening keeps the relation
    queryable over time, which is the point.
    """
    if not subject_id:
        return []
    attributes: dict[str, Any] = {"relation": predicate}
    if object_id:
        attributes["relation_object"] = object_id
    attributes["relation_confidence"] = confidence
    return [
        EntityEvent(
            tenant_id=tenant_id,
            entity_id=subject_id,
            kind="relation",
            entity_class="occurrence",
            observation_id=obs,
            sequence=index,
            extraction_version=extraction_version,
            valid_from=observed_at,
            payload=attributes,
        )
        for index, obs in enumerate(observation_ids)
    ]


__all__ = [
    "EntityEvent",
    "TemporalSink",
    "events_for_entity",
    "events_for_relation",
]
