"""Schema registry for the canonical knowledge model (feature 005, US1).

Ported pattern: FollowTheMoney (MIT) `followthemoney/model.py` schema/type
registry — reduced to a stdlib-only, dependency-free subset: a SchemaRegistry
keyed by ``schema_name`` maps to property sets, validates Entities/Statements,
and raises ``UnknownSchemaError`` on unknown keys (never a silently mis-typed
Entity). No YAML/rigour/banal machinery is carried over (FR-002).

   Source repo : donors/followthemoney (https://github.com/alephdata/followthemoney)
   License     : MIT
   What changed: dropped Model/module-loading, type system, banal/rigour deps;
                 kept schema->properties registry semantics + validation.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class UnknownSchemaError(KeyError):
    """Raised when a schema_name cannot be resolved in the registry."""

    def __init__(self, schema_name: str) -> None:
        self.schema_name = schema_name
        super().__init__(f"Unknown schema: {schema_name!r}")


NAME_VALID = frozenset(
    {
        "Person", "LegalEntity", "Organization", "Company", "UserAccount",
        "Address", "Asset", "Event", "Document", "Location", "Phone", "Email",
        "CryptoAddress", "Vehicle", "Membership", "Employment", "Ownership",
    }
)

_PROPERTY_TYPES = frozenset(
    {
        "name", "alias", "email", "phone", "country", "address", "url", "ip",
        "username", "identifier", "date", "text", "number", "amount", "registry",
    }
)

# FTM `schema.featured` ordering — the properties an analyst most wants to see first.
DEFAULT_FEATURED = {
    "Person": ("name", "nationality", "birthDate"),
    "LegalEntity": ("name", "country", "legalForm", "status"),
    "Organization": ("name", "country", "legalForm", "status"),
    "UserAccount": ("username", "service", "email", "owner"),
    "Company": ("name", "country", "legalForm", "status"),
    "Address": ("address", "postalCode", "country"),
    "Asset": ("name", "assetType", "value"),
}


@dataclass(frozen=True)
class SchemaDefinition:
    """Declared schema: name + allowed property names and their value types."""

    schema_name: str
    name: str = ""
    extends: tuple[str, ...] = ()
    properties: dict[str, str] = field(default_factory=dict)  # prop -> type

    @property
    def featured(self) -> tuple[str, ...]:
        return DEFAULT_FEATURED.get(self.schema_name, ())

    def property_types(self, prop: str) -> str | None:
        return self.properties.get(prop)


@dataclass
class SchemaRegistry:
    """Canonical schema registry: register / resolve / validate entities."""

    schemas: dict[str, SchemaDefinition] = field(default_factory=dict)

    def register(self, definition: SchemaDefinition) -> SchemaDefinition:
        name = definition.schema_name
        if name not in NAME_VALID and name not in self.schemas:
            raise UnknownSchemaError(name)
        if name in self.schemas:
            raise ValueError(f"schema already registered: {name}")
        for prop, value_type in definition.properties.items():
            if value_type not in _PROPERTY_TYPES:
                raise ValueError(
                    f"schema {name}: unknown property type {value_type!r} for {prop!r}"
                )
        self.schemas[name] = definition
        return definition

    def resolve(self, schema_name: str) -> SchemaDefinition:
        if schema_name not in self.schemas:
            raise UnknownSchemaError(schema_name)
        return self.schemas[schema_name]

    def has(self, schema_name: str) -> bool:
        return schema_name in self.schemas

    def property_types(self, schema_name: str) -> dict[str, str]:
        return dict(self.resolve(schema_name).properties)

    def featured(self, schema_name: str) -> tuple[str, ...]:
        return self.resolve(schema_name).featured

    def validate_property(self, schema_name: str, prop: str, value: str) -> None:
        definition = self.resolve(schema_name)
        declared = definition.properties.get(prop)
        if declared is None and prop not in definition.featured:
            # FtM schemata accept unlisted props as free text; we reject unknown
            # *types*, not unknown props — a property is valid if declared or text.
            declared = "text"
        if declared not in _PROPERTY_TYPES:
            raise ValueError(f"schema {schema_name}: unknown property type {declared!r}")
        if value is None or not str(value).strip():
            raise ValueError(f"schema {schema_name}: empty value for property {prop!r}")

    def validate_entity(self, schema_name: str, properties: dict) -> None:
        self.resolve(schema_name)
        for prop, entries in (properties or {}).items():
            for entry in entries:
                value = getattr(entry, "value", entry) if not isinstance(entry, str) else entry
                self.validate_property(schema_name, prop, str(value))

    def validate_property_list(
        self, schema_name: str, properties: list | None, *, registry_prop: str = "_props"
    ) -> None:
        """Validate a flat list of Property objects against the declared schema."""
        definition = self.resolve(schema_name)
        declared: dict[str, str] = dict(definition.properties)
        for prop in properties or []:
            prop_name = getattr(prop, "name", None)
            if not prop_name:
                raise ValueError(f"schema {schema_name}: property without a name")
            prop_type = getattr(prop, "type", "text") or "text"
            expected = declared.get(prop_name)
            if expected is not None and expected not in _PROPERTY_TYPES:
                raise ValueError(f"schema {schema_name}: unknown property type {expected!r}")
            if prop_type not in _PROPERTY_TYPES:
                raise ValueError(
                    f"schema {schema_name}: property {prop_name!r} has unknown type {prop_type!r}"
                )
            value = getattr(prop, "value", "")
            if value is None or not str(value).strip():
                raise ValueError(f"schema {schema_name}: empty value for property {prop_name!r}")


DEFAULT_REGISTRY = SchemaRegistry(
    schemas={
        "Person": SchemaDefinition(
            "Person",
            properties={
                "name": "name", "nationality": "country", "birthDate": "date",
                "email": "email", "phone": "phone", "address": "address", "idNumber": "identifier",
                "alias": "alias", "taxNumber": "identifier",
            },
        ),
        "LegalEntity": SchemaDefinition(
            "LegalEntity",
            properties={
                "name": "name", "country": "country", "legalForm": "text",
                "status": "text", "registrationNumber": "identifier", "email": "email",
            },
        ),
        "Organization": SchemaDefinition(
            "Organization",
            properties={
                "name": "name", "country": "country", "legalForm": "text",
                "status": "text", "registrationNumber": "identifier", "email": "email",
            },
        ),
        "Company": SchemaDefinition(
            "Company", extends=("Organization",),
            properties={
                "name": "name", "country": "country", "legalForm": "text",
                "status": "text", "registrationNumber": "identifier", "email": "email",
                "leiNumber": "identifier",
            },
        ),
        "UserAccount": SchemaDefinition(
            "UserAccount",
            properties={
                "username": "username", "service": "text", "email": "email",
                "url": "url", "owner": "text", "status": "text",
            },
        ),
        "Address": SchemaDefinition(
            "Address",
            properties={
                "address": "address",
                "postalCode": "text",
                "country": "country",
                "city": "text",
            },
        ),
        "Asset": SchemaDefinition(
            "Asset",
            properties={"name": "name", "assetType": "text", "value": "amount", "currency": "text"},
        ),
        "Event": SchemaDefinition(
            "Event",
            properties={
                "summary": "text",
                "date": "date",
                "location": "text",
                "participant": "name",
            },
        ),
        "Email": SchemaDefinition(
            "Email",
            properties={"address": "email", "label": "name", "domain": "text"},
        ),
        "CryptoAddress": SchemaDefinition(
            "CryptoAddress",
            properties={"publicKey": "text", "label": "name", "network": "text"},
        ),
    }
)