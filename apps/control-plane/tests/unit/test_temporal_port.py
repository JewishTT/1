"""Tests for the temporal port.

The port exists so control-plane can feed the temporal graph without importing
projection. What is worth protecting is the shape of what it produces, because a
producer that emits a nested payload silently produces no validity rows -- the
relation facts land on the event stream and then are not queryable over time, which
looks like success and is not.
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime

import pytest

APP = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(APP, "control-plane"))
sys.path.insert(0, os.path.join(APP, "shared"))

from services.temporal_port import (  # noqa: E402
    EntityEvent,
    TemporalSink,
    events_for_entity,
    events_for_relation,
)


def test_entity_event_exposes_the_boundary_shape() -> None:
    e = EntityEvent(
        tenant_id="acme",
        entity_id="ENT-1",
        kind="mention",
        entity_class="person",
        observation_id="OBS-1",
        sequence=2,
        payload={"name": "x"},
    )
    for field in ("tenant_id", "entity_id", "kind", "entity_class", "observation_id",
                  "sequence", "payload", "ts", "valid_from", "valid_until"):
        assert hasattr(e, field)


def test_one_event_per_observation() -> None:
    """The evidence trail is the point: collapsing to one row per entity would throw
    away who saw what."""
    events = events_for_entity(
        tenant_id="acme",
        entity_id="ENT-1",
        entity_class="person",
        observation_ids=["OBS-1", "OBS-2", "OBS-3"],
        attributes={"name": "x"},
    )
    assert [e.observation_id for e in events] == ["OBS-1", "OBS-2", "OBS-3"]
    assert [e.sequence for e in events] == [0, 1, 2]


def test_entity_event_carries_validity() -> None:
    t = datetime(2026, 5, 1, tzinfo=UTC)
    (event,) = events_for_entity(
        tenant_id="acme",
        entity_id="ENT-1",
        entity_class="person",
        observation_ids=["OBS-1"],
        attributes={"name": "x"},
        observed_at=t,
    )
    assert event.valid_from == t


def test_entity_without_observations_yields_nothing() -> None:
    """An entity nothing observed has no temporal claim to make."""
    assert (
        events_for_entity(
            tenant_id="acme",
            entity_id="ENT-1",
            entity_class="person",
            observation_ids=[],
            attributes={},
        )
        == []
    )


def test_relation_attributes_are_flat_scalars() -> None:
    """A nested payload produces no validity row in the store, so the relation would
    be unqueryable over time. Scalars keep it queryable."""
    (event,) = events_for_relation(
        tenant_id="acme",
        subject_id="ENT-1",
        object_id="ENT-2",
        predicate="located_in",
        observation_ids=["OBS-1"],
        confidence=0.8,
    )
    assert event.payload["relation"] == "located_in"
    assert event.payload["relation_object"] == "ENT-2"
    for value in event.payload.values():
        assert isinstance(value, (str, int, float, bool))


def test_relation_without_subject_is_dropped() -> None:
    assert (
        events_for_relation(
            tenant_id="acme",
            subject_id="",
            object_id="ENT-2",
            predicate="p",
            observation_ids=["OBS-1"],
            confidence=0.5,
        )
        == []
    )


def test_sink_protocol_accepts_a_structural_match() -> None:
    class Sink:
        async def ingest(self, events):
            return len(events)

    assert isinstance(Sink(), TemporalSink)

    class NotASink:
        pass

    assert not isinstance(NotASink(), TemporalSink)
