"""Relation schema: the declared contract of a relation type (feature 016, T063).

Task T063 of ``specs/016-relation-evidence-graph-fabric``; contract is
``data-model.md`` section 6 with FR-026 to FR-029 and ``docs/adr/0023``.

A :class:`RelationSchema` is a *declaration*: which classes may stand on each
end, which roles a type binds, which evidence patterns may ground it, how its
validity window is read, and which admission rule decides. It is deliberately
separate from :mod:`domain.relation_claim` — a claim is one assertion, a schema
is the vocabulary entry every assertion is checked against — and it borrows the
arity vocabulary from :mod:`domain.relation_identity` rather than redeclaring
one, so a schema can never disagree with identity derivation about what shape a
relation has (constitution I).

:class:`RelationSchemaRegistry` is the single read path for the vocabulary
(FR-028): the relation-candidate proposer, the validator and the admission-rule
evaluator all enumerate ``vocabulary()`` instead of embedding their own copy of
the relation list, and every one of them sees the same deterministic
``(relation_type, schema_version)`` order however the schemas were registered.

Every collection on a schema is canonicalised on construction and the whole
declaration is reduced to one order-insensitive :attr:`RelationSchema.content_key`,
so the three questions "is this the same schema?" and "is this the same version
of the same schema?" are answerable from the declaration alone. That is what
lets re-registration be idempotent for identical content, refused for a
same-version redefinition with different content, and accepted as a new version
when ``schema_version`` differs (FR-029, I-11).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from domain.relation_claim import RelationContractError, RelationRoleBinding, check_role_bindings
from domain.relation_identity import (
    RelationArityMode,
    canonical_material,
    digest128,
)


class RelationSchemaError(ValueError):
    """A schema cannot be registered as it stands.

    A ``ValueError`` (as ``data-model.md`` section 6 specifies) carrying the
    stable snake_case ``code`` the caller reports, in the spirit of
    :class:`domain.relation_claim.RelationContractError` so one caller can
    switch on either.
    """

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


class TemporalSemantics(StrEnum):
    """How a relation type reads its validity window (FR-027).

    - POINT: an instant, not a span (``co_occurs_with``);
    - REQUIRED_INTERVAL: a span is part of the claim (``employment``);
    - OPTIONAL_INTERVAL: a span is permitted but not demanded;
    - OPEN_ENDED: the span runs to the present unless it is closed.
    """

    POINT = "point"
    REQUIRED_INTERVAL = "required_interval"
    OPTIONAL_INTERVAL = "optional_interval"
    OPEN_ENDED = "open_ended"


def _version_order(version: str) -> tuple[int, int, str]:
    """Order one ``schema_version``: numeric versions ascend numerically.

    Sorting the raw text would rank ``"10"`` below ``"2"`` and make the active
    version of a type depend on how many revisions it has had. Numeric versions
    therefore order first and by value; anything else falls back to a stable
    lexicographic order behind them.
    """
    return (0, int(version), "") if version.isdigit() else (1, 0, version)


@dataclass(frozen=True)
class RelationSchema:
    """The declared contract of one relation type, at one version.

    Field order follows ``data-model.md`` section 6 exactly, because it is also
    the order the ``relation_schema_version`` row and the serialised definition
    read. Every collection is canonicalised on construction, so two declarations
    that differ only in the order their producer collected their members are one
    declaration — the property the registry's idempotency and conflict rules
    rest on.
    """

    relation_type: str
    arity_mode: RelationArityMode
    allowed_subject_classes: frozenset[str] = frozenset()
    allowed_object_classes: frozenset[str] = frozenset()
    allowed_role_bindings: tuple[RelationRoleBinding, ...] = ()
    allowed_role_classes: Mapping[str, frozenset[str]] = field(default_factory=dict)
    admissible_evidence_patterns: tuple[str, ...] = ()
    temporal_semantics: TemporalSemantics = TemporalSemantics.OPTIONAL_INTERVAL
    admission_rule_id: str = "default-assert"
    schema_version: str = "1"
    allow_repeated_member: bool = False
    required: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "relation_type", str(self.relation_type))
        object.__setattr__(self, "admission_rule_id", str(self.admission_rule_id))
        object.__setattr__(self, "schema_version", str(self.schema_version))
        object.__setattr__(self, "arity_mode", RelationArityMode(self.arity_mode))
        object.__setattr__(
            self, "temporal_semantics", TemporalSemantics(self.temporal_semantics)
        )
        object.__setattr__(
            self,
            "allowed_subject_classes",
            frozenset(str(entry) for entry in self.allowed_subject_classes),
        )
        object.__setattr__(
            self,
            "allowed_object_classes",
            frozenset(str(entry) for entry in self.allowed_object_classes),
        )
        object.__setattr__(
            self,
            "allowed_role_bindings",
            tuple(
                sorted(
                    set(self.allowed_role_bindings),
                    key=lambda binding: (binding.role, binding.member_ref, binding.member_class),
                )
            ),
        )
        object.__setattr__(
            self,
            "allowed_role_classes",
            MappingProxyType(
                {
                    str(role): frozenset(str(entry) for entry in classes)
                    for role, classes in sorted(
                        self.allowed_role_classes.items(), key=lambda item: str(item[0])
                    )
                }
            ),
        )
        object.__setattr__(
            self,
            "admissible_evidence_patterns",
            tuple(sorted({str(pattern) for pattern in self.admissible_evidence_patterns})),
        )

    @property
    def content_key(self) -> str:
        """128-bit content address of the whole declaration (I-11).

        Taken over the same canonical material :meth:`to_dict` publishes, with
        every collection order-insensitive, so two declarations of the same
        contract share one key however their producer ordered them and a changed
        field never does.
        """
        return digest128(canonical_material(self.to_dict()))

    @property
    def sorted_subject_classes(self) -> tuple[str, ...]:
        """The permitted subject classes in the one order callers may print."""
        return tuple(sorted(self.allowed_subject_classes))

    @property
    def sorted_object_classes(self) -> tuple[str, ...]:
        """The permitted object classes in the one order callers may print."""
        return tuple(sorted(self.allowed_object_classes))

    def role_classes_for(self, role: str) -> frozenset[str]:
        """The classes a role may bind; empty for a role the schema omits.

        An undeclared role is not an error here: reporting it is the semantic
        layer's call, and it needs the absent set to report against.
        """
        return self.allowed_role_classes.get(role, frozenset())

    def to_dict(self) -> dict[str, Any]:
        """The serialised declaration, JSON-native, for ``definition`` JSONB.

        The field set only — the derived :attr:`content_key` is recomputed from
        it on load, so a stored row cannot carry a key that disagrees with the
        declaration it was written beside.
        """
        return {
            "relation_type": self.relation_type,
            "arity_mode": str(self.arity_mode),
            "allowed_subject_classes": list(self.sorted_subject_classes),
            "allowed_object_classes": list(self.sorted_object_classes),
            "allowed_role_bindings": [binding.to_dict() for binding in self.allowed_role_bindings],
            "allowed_role_classes": {
                role: sorted(classes) for role, classes in self.allowed_role_classes.items()
            },
            "admissible_evidence_patterns": list(self.admissible_evidence_patterns),
            "temporal_semantics": str(self.temporal_semantics),
            "admission_rule_id": self.admission_rule_id,
            "schema_version": self.schema_version,
            "allow_repeated_member": self.allow_repeated_member,
            "required": self.required,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> RelationSchema:
        """Rebuild a declaration from a stored definition; absent keys default."""
        return cls(
            relation_type=str(payload.get("relation_type", "")),
            arity_mode=RelationArityMode(payload.get("arity_mode", RelationArityMode.DIRECTED)),
            allowed_subject_classes=frozenset(payload.get("allowed_subject_classes") or ()),
            allowed_object_classes=frozenset(payload.get("allowed_object_classes") or ()),
            allowed_role_bindings=tuple(
                RelationRoleBinding.from_dict(binding)
                for binding in payload.get("allowed_role_bindings") or ()
            ),
            allowed_role_classes={
                str(role): frozenset(classes)
                for role, classes in (payload.get("allowed_role_classes") or {}).items()
            },
            admissible_evidence_patterns=tuple(payload.get("admissible_evidence_patterns") or ()),
            temporal_semantics=TemporalSemantics(
                payload.get("temporal_semantics", TemporalSemantics.OPTIONAL_INTERVAL)
            ),
            admission_rule_id=str(payload.get("admission_rule_id", "default-assert")),
            schema_version=str(payload.get("schema_version", "1")),
            allow_repeated_member=bool(payload.get("allow_repeated_member", False)),
            required=bool(payload.get("required", True)),
        )


def _check_participant_shape(schema: RelationSchema) -> None:
    """Reject a declared ``arity_mode`` its own participant shape contradicts.

    FR-012: ``DIRECTED`` takes its two members from the endpoints, so a role
    binding on it is a declaration that cannot mean anything; ``NARY`` takes
    them from the roles, so fewer than two is a relation with no shape. A role
    is declared once, and a member may fill two roles only where the schema
    declares ``allow_repeated_member`` — the same rule
    :func:`domain.relation_claim.check_role_bindings` applies to a claim,
    re-used here so the two layers cannot drift apart.
    """
    if schema.arity_mode is RelationArityMode.DIRECTED and schema.allowed_role_bindings:
        raise RelationSchemaError(
            "role_binding_on_directed",
            f"directed relation {schema.relation_type!r} takes no role bindings; "
            "the endpoints are the members",
        )
    if schema.arity_mode is RelationArityMode.NARY and len(schema.allowed_role_bindings) < 2:
        raise RelationSchemaError(
            "insufficient_members",
            f"nary relation {schema.relation_type!r} needs at least two declared roles, "
            f"got {len(schema.allowed_role_bindings)}",
        )
    roles = [binding.role for binding in schema.allowed_role_bindings]
    if len(set(roles)) != len(roles):
        repeated = sorted({role for role in roles if roles.count(role) > 1})
        raise RelationSchemaError(
            "duplicate_role",
            f"relation {schema.relation_type!r} declares role(s) {repeated} more than once",
        )
    if all(binding.member_ref for binding in schema.allowed_role_bindings):
        try:
            check_role_bindings(
                schema.allowed_role_bindings,
                allow_repeated_member=schema.allow_repeated_member,
            )
        except RelationContractError as exc:
            raise RelationSchemaError(exc.code, exc.message) from exc


class RelationSchemaRegistry:
    """The relation vocabulary, versioned and deterministically enumerable.

    Holds every registered version of every type: ``get`` answers with the
    active (highest) one, ``versions`` with the whole chain, and ``vocabulary``
    with every entry in the single order all consumers may rely on (FR-028).
    """

    def __init__(self, schemas: Iterable[RelationSchema] = ()) -> None:
        self._by_version: dict[tuple[str, str], RelationSchema] = {}
        self._versions: dict[str, tuple[str, ...]] = {}
        for schema in schemas:
            self.register(schema)

    def register(self, schema: RelationSchema) -> RelationSchema:
        """Register one declaration and return the schema now in force.

        A new ``schema_version`` of a known type is a new version and is
        accepted. The same version is idempotent when the content is identical
        (the existing schema is returned untouched) and refused when it is not,
        so a type can never hold two different contracts under one version.
        """
        if not schema.relation_type:
            raise RelationSchemaError(
                "missing_relation_type", "a schema requires a relation type"
            )
        if not schema.schema_version:
            raise RelationSchemaError(
                "missing_schema_version",
                f"schema {schema.relation_type!r} requires a schema_version",
            )
        _check_participant_shape(schema)

        key = (schema.relation_type, schema.schema_version)
        existing = self._by_version.get(key)
        if existing is not None:
            if existing.content_key == schema.content_key:
                return existing
            raise RelationSchemaError(
                "conflicting_redefinition",
                f"{schema.relation_type!r} version {schema.schema_version!r} is already "
                f"registered with different content ({existing.content_key} != "
                f"{schema.content_key})",
            )
        self._by_version[key] = schema
        self._versions[schema.relation_type] = tuple(
            sorted(
                (*self._versions.get(schema.relation_type, ()), schema.schema_version),
                key=_version_order,
            )
        )
        return schema

    def get(self, relation_type: str) -> RelationSchema | None:
        """The active (highest) version of a type, or ``None`` (honest, I-3)."""
        versions = self._versions.get(relation_type, ())
        return self._by_version[(relation_type, versions[-1])] if versions else None

    def vocabulary(self) -> tuple[RelationSchema, ...]:
        """Every registered schema, ordered by ``(relation_type, schema_version)``.

        The order is a function of the content alone, so a proposer, a validator
        and an admission-rule evaluator enumerating the vocabulary — and two
        processes replaying the same registrations — see the same sequence.
        """
        return tuple(
            self._by_version[key]
            for key in sorted(
                self._by_version, key=lambda key: (key[0], _version_order(key[1]))
            )
        )

    def arity_of(self, relation_type: str) -> RelationArityMode | None:
        """The arity mode the active version declares, or ``None`` if unknown."""
        schema = self.get(relation_type)
        return schema.arity_mode if schema is not None else None

    def versions(self, relation_type: str) -> tuple[RelationSchema, ...]:
        """Every version of one type, oldest first."""
        return tuple(
            self._by_version[(relation_type, version)]
            for version in self._versions.get(relation_type, ())
        )

    def __len__(self) -> int:
        """How many schema versions are registered, not how many types."""
        return len(self._by_version)

    def __contains__(self, relation_type: object) -> bool:
        return relation_type in self._versions


__all__ = [
    "RelationSchema",
    "RelationSchemaError",
    "RelationSchemaRegistry",
    "TemporalSemantics",
]
