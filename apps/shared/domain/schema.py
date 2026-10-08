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
        # FTM's root: everything else is a ``Thing``. Registered so the hierarchy has a
        # declared top -- ``ancestors_of`` stops at it, and a lookup for it is a question
        # the registry can answer rather than an unknown-name error.
        "Thing",
        "Person", "LegalEntity", "Organization", "Company", "UserAccount",
        "Address", "Asset", "Event", "Document", "Location", "Phone", "Email",
        "CryptoAddress", "Vehicle", "Membership", "Employment", "Ownership",
    }
)

_PROPERTY_TYPES = frozenset(
    {
        "name", "alias", "email", "phone", "country", "address", "url", "ip",
        "username", "identifier", "date", "text", "number", "amount", "registry",
        # A share of an entity is a percentage, not a bare number: 33 and 0.33 must not be
        # the same value. Declaring it as ``number`` is what let ``Ownership.share`` ship
        # with a type outside this vocabulary.
        "percent",
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

    def ancestors_of(self, schema_name: str) -> tuple[str, ...]:
        """Every declared supertype of ``schema_name``, nearest first, excluding itself.

        Walked by the registry rather than supplied by a caller, because a hierarchy
        nobody can ask questions about does not constrain a type -- it is documentation.
        Cycle-guarded: a cycle in ``extends`` is a data error, and letting it spin here
        would turn a bad declaration into a hang rather than a refused lookup.
        """
        self.resolve(schema_name)
        found: list[str] = []
        seen = {schema_name}
        frontier = list(self.schemas[schema_name].extends)
        while frontier:
            name = frontier.pop(0)
            if name in seen:
                continue
            definition = self.schemas.get(name)
            if definition is None:
                continue
            seen.add(name)
            found.append(name)
            frontier.extend(definition.extends)
        return tuple(found)

    def is_subtype_of(self, schema_name: str, ancestor: str) -> bool:
        """Whether ``schema_name`` sits anywhere under ``ancestor``."""
        return ancestor in self.ancestors_of(schema_name)

    def descendants_of(self, ancestor: str) -> tuple[str, ...]:
        """Every registered schema under ``ancestor``, nearest first.

        Computed by walking the declared hierarchy rather than by scanning every schema and
        testing ``is_subtype_of``: the scan is quadratic and, more importantly, would
        resolve an undeclared parent to nothing instead of reporting it.
        """
        self.resolve(ancestor)
        direct = {
            name for name, d in self.schemas.items() if ancestor in d.extends
        }
        found: list[str] = []
        seen: set[str] = set()
        frontier = sorted(direct)
        while frontier:
            name = frontier.pop(0)
            if name in seen:
                continue
            seen.add(name)
            found.append(name)
            frontier.extend(
                sorted(n for n, d in self.schemas.items() if name in d.extends)
            )
        return tuple(found)

    def type_closure(self, schema_name: str) -> tuple[str, ...]:
        """The type plus everything it is a subtype of.

        This is the set a derived type may assert. Ordered widest-last so a caller that
        picks the most specific entry gets the narrowest claim and one that picks the first
        gets the broadest -- and either choice is defensible, which is the point: the
        registry should never have to guess which one the analyst meant.
        """
        return (schema_name,) + self.ancestors_of(schema_name)

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
        "Thing": SchemaDefinition(
            "Thing",
            properties={"name": "name", "summary": "text", "country": "country"},
        ),
        "Person": SchemaDefinition(
            "Person", extends=("LegalEntity",),
            properties={
                "name": "name", "nationality": "country", "birthDate": "date",
                "email": "email", "phone": "phone", "address": "address", "idNumber": "identifier",
                "alias": "alias", "taxNumber": "identifier",
            },
        ),
        "LegalEntity": SchemaDefinition(
            "LegalEntity", extends=("Thing",),
            properties={
                "name": "name", "country": "country", "legalForm": "text",
                "status": "text", "registrationNumber": "identifier", "email": "email",
            },
        ),
        "Organization": SchemaDefinition(
            "Organization", extends=("LegalEntity",),
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
            "UserAccount", extends=("Thing",),
            properties={
                "username": "username", "service": "text", "email": "email",
                "url": "url", "owner": "text", "status": "text",
            },
        ),
        "Address": SchemaDefinition(
            "Address", extends=("Location",),
            properties={
                "address": "address",
                "postalCode": "text",
                "country": "country",
                "city": "text",
            },
        ),
        "Asset": SchemaDefinition(
            "Asset", extends=("Thing",),
            properties={"name": "name", "assetType": "text", "value": "amount", "currency": "text"},
        ),
        "Event": SchemaDefinition(
            "Event", extends=("Thing",),
            properties={
                "summary": "text",
                "date": "date",
                "location": "text",
                "participant": "name",
            },
        ),
        "Email": SchemaDefinition(
            "Email", extends=("Thing",),
            properties={"address": "email", "label": "name", "domain": "text"},
        ),
        "CryptoAddress": SchemaDefinition(
            "CryptoAddress", extends=("Asset",),
            properties={"publicKey": "text", "label": "name", "network": "text"},
        ),
        # Admissible since NAME_VALID listed them; nothing ever registered them, so seven of
        # the seventeen declared types could not be assigned to a stored entity at all.
        "Document": SchemaDefinition(
            "Document", extends=("Thing",),
            properties={"title": "name", "fileName": "name", "mimeType": "text",
                        "contentHash": "identifier", "author": "name", "createdAt": "date"},
        ),
        "Location": SchemaDefinition(
            "Location", extends=("Thing",),
            properties={"name": "name", "latitude": "number", "longitude": "number",
                        "country": "country", "city": "text"},
        ),
        "Phone": SchemaDefinition(
            "Phone", extends=("Thing",),
            properties={"number": "text", "label": "name", "service": "text"},
        ),
        "Vehicle": SchemaDefinition(
            "Vehicle", extends=("Asset",),
            properties={"name": "name", "vin": "identifier", "registration": "identifier",
                        "buildDate": "date", "brand": "name"},
        ),
        "Membership": SchemaDefinition(
            "Membership", extends=("Thing",),
            properties={"role": "text", "organization": "name", "member": "name",
                        "startDate": "date", "endDate": "date"},
        ),
        "Employment": SchemaDefinition(
            "Employment", extends=("Membership",),
            properties={"role": "text", "employer": "name", "employee": "name",
                        "title": "text", "salary": "amount"},
        ),
        "Ownership": SchemaDefinition(
            "Ownership", extends=("Thing",),
            properties={"owner": "name", "asset": "name", "share": "percent",
                        "startDate": "date", "endDate": "date"},
        ),
    }
)


def _assert_registry_is_sound(registry: SchemaRegistry) -> None:
    """Validate the literal ``DEFAULT_REGISTRY`` at import time.

    The registry is built by handing ``schemas=`` straight to the constructor, which
    bypasses :meth:`SchemaRegistry.register` and therefore its property-type check. That
    let ``Ownership.share: "percent"`` ship with a type outside ``_PROPERTY_TYPES`` --
    a bad declaration that no code path could ever have reported, because the only code
    that would have caught it was the one being skipped.

    Import-time rather than test-time on purpose: a vocabulary that can silently disagree
    with the registry is worse than one that refuses to load.
    """
    for name, definition in registry.schemas.items():
        for prop, value_type in definition.properties.items():
            if value_type not in _PROPERTY_TYPES:
                raise ValueError(
                    f"schema {name}.{prop} declares unknown property type {value_type!r}"
                )
        for parent in definition.extends:
            if parent not in registry.schemas:
                raise ValueError(f"schema {name} extends unregistered schema {parent!r}")


_assert_registry_is_sound(DEFAULT_REGISTRY)
