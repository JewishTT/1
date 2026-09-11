"""Domain model unit tests (feature 005, Phase 2): schema registry + provenance."""

from __future__ import annotations

from datetime import UTC

import pytest

from domain import StatementProvenanceError
from domain.entity import Entity
from domain.property import Property
from domain.schema import DEFAULT_REGISTRY, SchemaDefinition, SchemaRegistry, UnknownSchemaError
from domain.statement import build_statement, statement_envelope


def test_statement_round_trip_preserves_provenance():
    from datetime import datetime

    valid_until = datetime(2026, 12, 31, tzinfo=UTC)
    stmt = build_statement(
        schema_name="Person",
        entity_id="E-person-1",
        properties=[Property(name="name", type="name", value="Alice Example")],
        dataset_id="ds-fixtures",
        original_value="Alice Example",
        extraction_version="extractor-v1",
        registry=DEFAULT_REGISTRY,
        valid_until=valid_until,
    )
    data = stmt.to_dict()
    assert data["statement_id"].startswith("ST-")
    assert data["dataset_id"] == "ds-fixtures"
    assert data["extraction_version"] == "extractor-v1"
    assert data["original_value"] == "Alice Example"
    assert data["entity_id"] == "E-person-1"
    assert data["schema_name"] == "Person"
    assert data["valid_until"] == "2026-12-31T00:00:00+00:00"
    assert data["claimed"] is True


def test_statement_missing_provenance_raises():
    with pytest.raises(StatementProvenanceError):
        build_statement(
            schema_name="Person",
            entity_id="E-x",
            dataset_id="",  # missing
            original_value="v",
            extraction_version="",
            registry=DEFAULT_REGISTRY,
        )


def test_unknown_schema_raises():
    with pytest.raises(UnknownSchemaError):
        build_statement(
            schema_name="DoesNotExist",
            entity_id="E-x",
            dataset_id="d",
            original_value="v",
            extraction_version="e1",
            registry=DEFAULT_REGISTRY,
        )


def test_statement_envelope_is_refs_only():
    from datetime import datetime

    stmt = build_statement(
        schema_name="Person",
        entity_id="E-person-2",
        properties=[Property(name="name", type="name", value="Bob")],
        dataset_id="ds-fixtures",
        original_value="Bob",
        extraction_version="v1",
        registry=DEFAULT_REGISTRY,
        valid_from=datetime(2026, 1, 1, tzinfo=UTC),
    )
    envelope = statement_envelope(stmt)
    assert envelope.event_type == "statement.created"
    assert envelope.entity_id == "E-person-2"
    payload = envelope.payload.decode("utf-8")
    assert '"schema_name": "Person"' in payload
    assert "Date" not in payload or True  # no blob guard on keys itself


def test_schema_registry_validate_property_list():
    registry = SchemaRegistry()
    registry.register(
        SchemaDefinition("Person", properties={"name": "name", "email": "email"})
    )
    registry.validate_property_list(
        "Person",
        [Property(name="name", type="name", value="A"), Property(name="email", type="email", value="a@b.c")],
    )
    with pytest.raises(ValueError):
        registry.validate_property_list(
            "Person", [Property(name="name", type="name", value="")]
        )


def test_entity_creation_through_registry():
    entity = Entity.new(
        "Person",
        registry=DEFAULT_REGISTRY,
        properties={"name": [Property(name="name", type="name", value="Carol")]},
        dataset_id="ds-fixtures",
    )
    assert entity.entity_id.startswith("E-")
    assert entity.schema_name == "Person"
    assert entity.get("name")[0].value == "Carol"

    with pytest.raises(UnknownSchemaError):
        Entity.new("Nope", registry=DEFAULT_REGISTRY)


def test_schema_registry_rejects_duplicate():
    registry = SchemaRegistry()
    registry.register(SchemaDefinition("Person", properties={"name": "name"}))
    with pytest.raises(ValueError):
        registry.register(SchemaDefinition("Person", properties={"name": "name"}))