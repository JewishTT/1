"""Kafka wiring for the atomic entity fabric (feature 009, block A).

The fabric domain (`fabric.py`) is persistence- and transport-agnostic; this
module supplies the concrete Kafka side:
- ``KafkaFabricSink`` — emits ``entity.stream.appended`` /
  ``entity.state.projected`` / ``entity.series.projected`` / ``hyperedge.*``
  envelopes through an ``IdempotentProducer`` (deterministic ``event_id``s ->
  produce retries are idempotent, I-11);
- ``EntityStreamConsumer`` — concrete ``IdempotentConsumer``: consumes
  ``entity.stream.appended``, folds into per-entity state, re-emits the
  derived projections. A consumer, not an owner: state is rebuildable from
  the stream (I-12), never mutated by projection consumers.

Consumers subscribe to the ``entity-stream`` topic replicates state; the
Postgres ``entity_stream`` table is the durable substrate (append-only, I-5).
"""

from __future__ import annotations

import json
from typing import Any

from domain.dynamics import EntityState, Series, StreamRecord
from domain.fabric import EntityFabric
from domain.hypergraph import HyperEdge
from events.kafka import Envelope, IdempotentConsumer, IdempotentProducer
from events.topics import topic_for


class KafkaFabricSink:
    """Emit fabric events through an ``IdempotentProducer`` (I-11, I-5)."""

    def __init__(self, producer: IdempotentProducer) -> None:
        self._producer = producer

    def emit_stream_record(self, rec: StreamRecord) -> None:
        from domain.stream_events import emit_stream_record

        emit_stream_record(rec, self._producer)

    def emit_state(self, state: EntityState) -> None:
        from domain.stream_events import emit_entity_state_projected

        emit_entity_state_projected(state, self._producer)

    def emit_series(self, series: Series) -> None:
        from domain.stream_events import emit_entity_series_projected

        emit_entity_series_projected(series, self._producer)

    def emit_hyperedge(self, edge: HyperEdge) -> None:
        from domain.stream_events import emit_hyperedge

        emit_hyperedge(edge, self._producer)

    def emit_hyperedge_temporal_version(self, edge: HyperEdge) -> None:
        from domain.stream_events import emit_hyperedge_temporal_version

        emit_hyperedge_temporal_version(edge, self._producer)

    def emit_hyperedge_expired(self, edge: HyperEdge, expired_at: Any) -> None:
        from domain.stream_events import emit_hyperedge_expired

        emit_hyperedge_expired(edge, self._producer, expired_at)


class EntityStreamConsumer(IdempotentConsumer):
    """Concrete consumer: fold ``entity.stream.appended`` -> re-emit projections.

    Idempotency key is the envelope ``event_id`` (deterministic from the
    record hash), so at-least-once delivery can never double-apply a record.
    """

    def __init__(
        self,
        fabric: EntityFabric,
        group_id: str = "entity-stream",
        bootstrap_servers: str | None = None,
    ) -> None:
        super().__init__(
            group_id=group_id,
            topics=[topic_for("entity.stream.appended")],
            bootstrap_servers=bootstrap_servers,
        )
        self._fabric = fabric

    @property
    def idempotency_key(self, envelope: Envelope) -> str:
        return envelope.event_id

    async def handle(self, envelope: Envelope, raw: bytes) -> None:
        data = json.loads(envelope.payload.decode("utf-8"))
        rec = StreamRecord.from_dict(data)
        self._fabric.append(
            rec,
            schema_name=data.get("_schema_hint", ""),
        )


def produce_entity_stream(
    fabric: EntityFabric, producer: IdempotentProducer, rec: StreamRecord
) -> None:
    """Fire the initial ``entity.stream.appended`` envelope for one record
    (idempotent, I-11) — the entry point acquisition/interpretation calls
    when a new atomic life-event is admitted."""
    from domain.stream_events import stream_record_envelope

    topic = topic_for("entity.stream.appended")
    producer.produce(topic, stream_record_envelope(rec), key=rec.entity_id)


class DanglingStreamError(ValueError):
    """Raised when a fold is attempted on a store that failed to persist a
    record (substrate must win before any projection is derived)."""