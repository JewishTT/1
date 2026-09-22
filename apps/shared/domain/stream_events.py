"""Kafka emission for the atomic entity fabric (feature 009, I-5 refs-only).

The append-only entity life-stream is the substrate of the platform: every
mutation of an entity's state is one ``entity.stream.appended`` event (refs
and fields only — raw evidence stays in object storage, I-5). State folds,
time series and hyperedges are rebuildable projections of this stream
(I-11/I-12).

Emitter follows the ``domain.statement`` pattern: build the envelope with
``build_envelope`` and hand it to an ``IdempotentProducer``; deterministic
``event_id`` (``evt-<record_hash>``) makes produce retries naturally
idempotent (I-11).
"""

from __future__ import annotations

import json
from typing import Any

from domain.dynamics import EntityState, Series, StreamRecord
from domain.hypergraph import HyperEdge
from events.kafka import build_envelope
from events.topics import topic_for


def stream_record_envelope(rec: StreamRecord) -> Any:
    """``entity.stream.appended`` envelope for one atomic life-event (refs-only)."""
    payload = json.dumps(rec.to_dict(), default=str).encode("utf-8")
    return build_envelope(
        event_type="entity.stream.appended",
        event_version="1.0",
        producer="shared.domain",
        producer_version="0.2.0",
        payload=payload,
        entity_id=rec.entity_id,
        event_id=f"evt-{rec.record_hash}",
        observation_id=rec.observation_id or None,
        tenant_id=rec.tenant_id,
    )


def emit_stream_record(rec: StreamRecord, producer) -> None:
    """Produce one life-event; key = entity_id preserves per-entity ordering."""
    producer.produce(
        topic_for("entity.stream.appended"),
        stream_record_envelope(rec),
        key=rec.entity_id,
    )


def entity_state_projected_envelope(state: EntityState) -> Any:
    """``entity.state.projected`` — folded state after an appended event.

    Load-bearing projection event for consumers of entity state (admission,
    interpretation, search): deterministic ``event_id`` from ``head_hash``
    plus the record hash guarantees the last-applied event is traceable.
    """
    payload = json.dumps(state.to_dict(), default=str).encode("utf-8")
    return build_envelope(
        event_type="entity.state.projected",
        event_version="1.0",
        producer="shared.domain",
        producer_version="0.2.0",
        payload=payload,
        entity_id=state.entity_id,
        event_id=f"evt-{state.head_hash}",
        tenant_id=state.tenant_id,
    )


def emit_entity_state_projected(state: EntityState, producer) -> None:
    """Emit folded state; key = entity_id keeps a consumer's state cache hot."""
    producer.produce(
        topic_for("entity.state.projected"),
        entity_state_projected_envelope(state),
        key=state.entity_id,
    )


def entity_series_projected_envelope(series: Series) -> Any:
    """``entity.series.projected`` — one derived series (content-addressed)."""
    payload = json.dumps(series.to_dict(), default=str).encode("utf-8")
    return build_envelope(
        event_type="entity.series.projected",
        event_version="1.0",
        producer="shared.domain",
        producer_version="0.2.0",
        payload=payload,
        entity_id=series.entity_id,
        event_id=f"evt-{series.series_hash}",
        tenant_id=series.tenant_id,
    )


def emit_entity_series_projected(series: Series, producer) -> None:
    producer.produce(
        topic_for("entity.series.projected"),
        entity_series_projected_envelope(series),
        key=series.entity_id,
    )


def hyperedge_envelope(edge: HyperEdge) -> Any:
    """``hyperedge.created`` envelope (refs-only; N-ary native form)."""
    payload = json.dumps(edge.to_dict(), default=str).encode("utf-8")
    return build_envelope(
        event_type="hyperedge.created",
        event_version="1.0",
        producer="shared.domain",
        producer_version="0.2.0",
        payload=payload,
        entity_id=edge.members[0] if edge.members else "",
        event_id=f"evt-{edge.content_hash}",
        observation_id=edge.observation_id or None,
        tenant_id=edge.tenant_id,
    )


def emit_hyperedge(edge: HyperEdge, producer) -> None:
    producer.produce(
        topic_for("hyperedge.created"),
        hyperedge_envelope(edge),
        key=";".join(edge.members[:2]),
    )


def hyperedge_temporal_version_envelope(edge: HyperEdge, version_no: int = 1) -> Any:
    """``hyperedge.temporal_version_created`` — one version of a logical edge.

    Identifies the stable logical edge (block G) plus the version index (1 +
    per created version) so consumers can rebuild a version history (block H).
    """
    payload = json.dumps(edge.to_dict(), default=str).encode("utf-8")
    return build_envelope(
        event_type="hyperedge.temporal_version_created",
        event_version="1.0",
        producer="shared.domain",
        producer_version="0.2.0",
        payload=payload,
        entity_id=edge.members[0] if edge.members else "",
        event_id=f"evt-{edge.edge_id}-v{version_no}",
        observation_id=edge.observation_id or None,
        tenant_id=edge.tenant_id,
    )


def emit_hyperedge_temporal_version(edge: HyperEdge, producer, version_no: int = 1) -> None:
    producer.produce(
        topic_for("hyperedge.temporal_version_created"),
        hyperedge_temporal_version_envelope(edge, version_no=version_no),
        key=edge.logical_id,
    )


def hyperedge_expired_envelope(edge: HyperEdge, expired_at: Any) -> Any:
    """``hyperedge.expired`` — logical edge closed (terminal version)."""
    payload = json.dumps(
        {
            "logical_id": edge.logical_id,
            "edge_id": edge.edge_id,
            "edge_type": edge.edge_type,
            "members": list(edge.members),
            "valid_until": edge.valid_until.isoformat() if edge.valid_until else None,
            "expired_at": (
                expired_at.isoformat()
                if hasattr(expired_at, "isoformat")
                else expired_at
            ),
            "tenant_id": edge.tenant_id,
        },
        default=str,
    ).encode("utf-8")
    return build_envelope(
        event_type="hyperedge.expired",
        event_version="1.0",
        producer="shared.domain",
        producer_version="0.2.0",
        payload=payload,
        entity_id=edge.members[0] if edge.members else "",
        event_id=f"evt-{edge.logical_id}-expired",
        observation_id=edge.observation_id or None,
        tenant_id=edge.tenant_id,
    )


def emit_hyperedge_expired(edge: HyperEdge, producer, expired_at: Any) -> None:
    producer.produce(
        topic_for("hyperedge.expired"),
        hyperedge_expired_envelope(edge, expired_at=expired_at),
        key=edge.logical_id,
    )