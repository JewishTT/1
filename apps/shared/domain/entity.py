"""Canonical Entity for the knowledge model (feature 005, US1).

Ported pattern: FollowTheMoney (MIT) `followthemoney/entity.py` / proxy — an
entity is a named subject with a schema-backed, typed property set. Here the
entity is a plain dataclass (stdlib-only); validation is delegated to the
SchemaRegistry so it can never silently drift from the declared schema.

   Source repo : donors/followthemoney (https://github.com/alephdata/followthemoney)
   License     : MIT
   What changed: dropped proxy/proxy-class machinery and type cleaning; kept
                 schema-backed Entity with dataset/temporal metadata.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from domain.property import Property
from domain.schema import SchemaRegistry


@dataclass
class Entity:
    """Named subject of an investigation with a schema-backed property set."""

    schema_name: str
    entities_id: str = ""
    properties: dict[str, list[Property]] = field(default_factory=dict)
    dataset_id: str = ""
    first_seen: datetime | None = None
    last_seen: datetime | None = None

    @property
    def entity_id(self) -> str:
        return self.entities_id

    @property
    def id(self) -> str:
        return self.entities_id

    def __post_init__(self) -> None:
        if not self.entities_id:
            self.entities_id = "E-" + uuid.uuid4().hex[:12]
        self.regenerate()

    @classmethod
    def new(
        cls,
        schema_name: str,
        *,
        registry: SchemaRegistry,
        properties: dict[str, list[Property]] | None = None,
        dataset_id: str = "",
        entities_id: str | None = None,
    ) -> Entity:
        registry.resolve(schema_name)
        registry.validate_entity(schema_name, properties or {})
        now = datetime.now(UTC)
        return cls(
            schema_name=schema_name,
            entities_id=entities_id or "E-" + uuid.uuid4().hex[:12],
            properties=properties or {},
            dataset_id=dataset_id,
            first_seen=now,
            last_seen=now,
        )

    def regenerate(self) -> None:
        for entries in self.properties.values():
            for prop in entries:
                if not prop.type or prop.type == "text":
                    prop.type = "text"
                if not prop.original_value:
                    prop.original_value = prop.value

    def get(self, name: str) -> list[Property]:
        return self.properties.get(name, [])

    def add(self, prop: Property) -> None:
        self.properties.setdefault(prop.name, []).append(prop)

    def to_dict(self) -> dict:
        return {
            "entity_id": self.entities_id,
            "schema_name": self.schema_name,
            "properties": {
                name: [p.to_dict() for p in entries]
                for name, entries in self.properties.items()
            },
            "dataset_id": self.dataset_id,
            "first_seen": self.first_seen.isoformat() if self.first_seen else None,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Entity:
        return cls(
            schema_name=data.get("schema_name", ""),
            entities_id=data.get("entity_id", ""),
            properties={
                name: [Property.from_dict(p) for p in entries]
                for name, entries in (data.get("properties") or {}).items()
            },
            dataset_id=data.get("dataset_id", ""),
            first_seen=(
                datetime.fromisoformat(data["first_seen"]) if data.get("first_seen") else None
            ),
            last_seen=(
                datetime.fromisoformat(data["last_seen"]) if data.get("last_seen") else None
            ),
        )