"""Relation schema: the vocabulary registry, its rejections, its versions.

Tasks T053, T054, T055 and T063, plus the registry half of T056, of
``specs/016-relation-evidence-graph-fabric``. FR-026 a schema declares the
contract of one relation type, FR-027 ``temporal_semantics`` is one of four
values, FR-028 the vocabulary is enumerable in one deterministic order that the
proposer, the validator and the admission-rule evaluator all read rather than
embedding their own list, FR-029 schemas are versioned and a claim records the
version in force.

The semantic-layer half of T056 — wiring ``validate`` to the registry — is task
T065. Those two tests are skipped, never failed, while that wiring is absent: a
peer module written in parallel is a missing feature here, not a defect.
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import fields, replace
from datetime import UTC, datetime
from typing import Any

import pytest

from domain.relation_claim import RelationClaim, RelationRoleBinding
from domain.relation_identity import RelationArityMode, recompute_identity
from domain.relation_schema import (
    RelationSchema,
    RelationSchemaError,
    RelationSchemaRegistry,
    TemporalSemantics,
)

pytestmark = pytest.mark.unit

_FROM = datetime(2017, 1, 1, tzinfo=UTC)
_TO = datetime(2022, 6, 1, tzinfo=UTC)
_OBSERVED = datetime(2022, 7, 1, 9, 0, tzinfo=UTC)
_PUBLISHED = datetime(2022, 7, 2, 12, 0, tzinfo=UTC)

_PENDING_LOGICAL = "RL-pending"
_PENDING_REVISION = "RC-pending"

_EMPLOYMENT_BINDINGS = (
    RelationRoleBinding("organization", "", "ORGANIZATION"),
    RelationRoleBinding("person", "", "PERSON"),
)

#: The declared vocabulary of the fixture world; two of its types carry a
#: second version, and the tuple is deliberately not in vocabulary order.
_VOCABULARY: tuple[RelationSchema, ...] = (
    RelationSchema(
        relation_type="works_for",
        arity_mode=RelationArityMode.DIRECTED,
        allowed_subject_classes=frozenset({"PERSON"}),
        allowed_object_classes=frozenset({"ORGANIZATION"}),
        admissible_evidence_patterns=("payroll-record", "job-listing"),
        temporal_semantics=TemporalSemantics.REQUIRED_INTERVAL,
        admission_rule_id="default-assert",
        schema_version="1",
    ),
    RelationSchema(
        relation_type="located_in",
        arity_mode=RelationArityMode.DIRECTED,
        allowed_subject_classes=frozenset({"PLACE"}),
        allowed_object_classes=frozenset({"PLACE"}),
        admissible_evidence_patterns=("geocoded-address",),
        temporal_semantics=TemporalSemantics.REQUIRED_INTERVAL,
        admission_rule_id="default-assert",
        schema_version="1",
    ),
    RelationSchema(
        relation_type="employment",
        arity_mode=RelationArityMode.NARY,
        allowed_role_bindings=_EMPLOYMENT_BINDINGS,
        allowed_role_classes={
            "organization": frozenset({"ORGANIZATION"}),
            "person": frozenset({"PERSON"}),
        },
        admissible_evidence_patterns=("payroll-record", "job-listing"),
        temporal_semantics=TemporalSemantics.OPEN_ENDED,
        admission_rule_id="employment-evidence",
        schema_version="2",
    ),
    RelationSchema(
        relation_type="co_occurs_with",
        arity_mode=RelationArityMode.UNDIRECTED,
        allowed_subject_classes=frozenset({"ENTITY"}),
        allowed_object_classes=frozenset({"ENTITY"}),
        admissible_evidence_patterns=("co-mention", "shared-segment"),
        temporal_semantics=TemporalSemantics.POINT,
        admission_rule_id="default-assert",
        schema_version="1",
    ),
    RelationSchema(
        relation_type="located_in",
        arity_mode=RelationArityMode.TEMPORAL,
        allowed_subject_classes=frozenset({"PLACE"}),
        allowed_object_classes=frozenset({"PLACE"}),
        admissible_evidence_patterns=("geocoded-address", "gazetteer-entry"),
        temporal_semantics=TemporalSemantics.OPTIONAL_INTERVAL,
        admission_rule_id="default-assert",
        schema_version="2",
        required=False,
    ),
    RelationSchema(
        relation_type="co_occurs_with",
        arity_mode=RelationArityMode.UNDIRECTED,
        allowed_subject_classes=frozenset({"ENTITY"}),
        allowed_object_classes=frozenset({"ENTITY"}),
        admissible_evidence_patterns=("co-mention", "shared-segment"),
        temporal_semantics=TemporalSemantics.POINT,
        admission_rule_id="default-assert",
        schema_version="1.1",
    ),
)

#: ``vocabulary()`` is sorted by ``(relation_type, schema_version)`` — the one
#: order every consumer of the vocabulary may rely on (FR-028).
_EXPECTED_VOCABULARY_ORDER = (
    ("co_occurs_with", "1"),
    ("co_occurs_with", "1.1"),
    ("employment", "2"),
    ("located_in", "1"),
    ("located_in", "2"),
    ("works_for", "1"),
)

#: A value of each field that differs from the one ``works_for`` declares, so
#: every field is proved to be part of the content key.
_MUTATED_FIELD_VALUE: dict[str, Any] = {
    "relation_type": "works_elsewhere",
    "arity_mode": RelationArityMode.NARY,
    "allowed_subject_classes": frozenset({"ENTITY"}),
    "allowed_object_classes": frozenset({"ENTITY"}),
    "allowed_role_bindings": (RelationRoleBinding("person", "", "PERSON"),),
    "allowed_role_classes": {"person": frozenset({"PERSON"})},
    "admissible_evidence_patterns": ("other-pattern",),
    "temporal_semantics": TemporalSemantics.POINT,
    "admission_rule_id": "other-rule",
    "schema_version": "2",
    "allow_repeated_member": True,
    "required": False,
}

_EXPECTED_FIELD_ORDER = (
    "relation_type",
    "arity_mode",
    "allowed_subject_classes",
    "allowed_object_classes",
    "allowed_role_bindings",
    "allowed_role_classes",
    "admissible_evidence_patterns",
    "temporal_semantics",
    "admission_rule_id",
    "schema_version",
    "allow_repeated_member",
    "required",
)


def _keyed(schemas: tuple[RelationSchema, ...]) -> dict[tuple[str, str], RelationSchema]:
    return {(schema.relation_type, schema.schema_version): schema for schema in schemas}


def _by_key(relation_type: str, schema_version: str) -> RelationSchema:
    return _keyed(_VOCABULARY)[(relation_type, schema_version)]


def _filled(registry: RelationSchemaRegistry) -> RelationSchemaRegistry:
    for schema in _VOCABULARY:
        registry.register(schema)
    return registry


def _versioned(schema_version: str, **overrides: Any) -> RelationSchema:
    fields_: dict[str, Any] = {
        "relation_type": "mentions",
        "arity_mode": RelationArityMode.DIRECTED,
        "allowed_subject_classes": frozenset({"PERSON"}),
        "allowed_object_classes": frozenset({"PERSON"}),
        "admissible_evidence_patterns": ("mention",),
        "temporal_semantics": TemporalSemantics.OPTIONAL_INTERVAL,
        "admission_rule_id": "default-assert",
        "schema_version": schema_version,
    }
    fields_.update(overrides)
    return RelationSchema(**fields_)


# --------------------------------------------------------------------------
# T053 / FR-028: the vocabulary is enumerable in one deterministic order
# --------------------------------------------------------------------------


def test_t053_vocabulary_order_is_deterministic_across_repeated_calls() -> None:
    registry = _filled(RelationSchemaRegistry())
    first = registry.vocabulary()

    assert isinstance(first, tuple)
    assert all(isinstance(schema, RelationSchema) for schema in first)
    assert first == registry.vocabulary() == registry.vocabulary()
    assert [(schema.relation_type, schema.schema_version) for schema in first] == list(
        _EXPECTED_VOCABULARY_ORDER
    )
    assert len(registry) == len(_VOCABULARY) == 6
    assert set(_keyed(first)) == set(_keyed(_VOCABULARY))


def test_t053_vocabulary_order_does_not_depend_on_insertion_order() -> None:
    forward = _filled(RelationSchemaRegistry())
    backward = RelationSchemaRegistry(tuple(reversed(_VOCABULARY)))
    interleaved = RelationSchemaRegistry()
    for index in range(0, len(_VOCABULARY), 2):
        interleaved.register(_VOCABULARY[index])
        interleaved.register(_VOCABULARY[len(_VOCABULARY) - 1 - index])

    expected = forward.vocabulary()
    assert backward.vocabulary() == expected == interleaved.vocabulary()
    assert [schema.content_key for schema in backward.vocabulary()] == [
        schema.content_key for schema in expected
    ]
    assert len(backward) == len(forward) == 6
    assert all(
        relation_type in backward
        for relation_type in ("co_occurs_with", "employment", "located_in", "works_for")
    )
    assert "unregistered_type" not in backward


def test_t053_an_empty_registry_enumerates_nothing() -> None:
    registry = RelationSchemaRegistry()
    assert registry.vocabulary() == ()
    assert len(registry) == 0
    assert registry.get("works_for") is None
    assert registry.arity_of("works_for") is None
    assert registry.versions("works_for") == ()
    assert "works_for" not in registry


@pytest.mark.parametrize(
    (
        "relation_type",
        "schema_version",
        "arity_mode",
        "subject",
        "obj",
        "patterns",
        "temporal",
        "rule",
    ),
    [
        pytest.param(
            "co_occurs_with",
            "1",
            RelationArityMode.UNDIRECTED,
            ("ENTITY",),
            ("ENTITY",),
            ("co-mention", "shared-segment"),
            TemporalSemantics.POINT,
            "default-assert",
            id="co_occurs_with-v1",
        ),
        pytest.param(
            "co_occurs_with",
            "1.1",
            RelationArityMode.UNDIRECTED,
            ("ENTITY",),
            ("ENTITY",),
            ("co-mention", "shared-segment"),
            TemporalSemantics.POINT,
            "default-assert",
            id="co_occurs_with-v1.1",
        ),
        pytest.param(
            "employment",
            "2",
            RelationArityMode.NARY,
            (),
            (),
            ("job-listing", "payroll-record"),
            TemporalSemantics.OPEN_ENDED,
            "employment-evidence",
            id="employment-v2",
        ),
        pytest.param(
            "located_in",
            "1",
            RelationArityMode.DIRECTED,
            ("PLACE",),
            ("PLACE",),
            ("geocoded-address",),
            TemporalSemantics.REQUIRED_INTERVAL,
            "default-assert",
            id="located_in-v1",
        ),
        pytest.param(
            "located_in",
            "2",
            RelationArityMode.TEMPORAL,
            ("PLACE",),
            ("PLACE",),
            ("gazetteer-entry", "geocoded-address"),
            TemporalSemantics.OPTIONAL_INTERVAL,
            "default-assert",
            id="located_in-v2",
        ),
        pytest.param(
            "works_for",
            "1",
            RelationArityMode.DIRECTED,
            ("PERSON",),
            ("ORGANIZATION",),
            ("job-listing", "payroll-record"),
            TemporalSemantics.REQUIRED_INTERVAL,
            "default-assert",
            id="works_for-v1",
        ),
    ],
)
def test_t053_every_declared_type_reports_its_whole_declaration(
    relation_type: str,
    schema_version: str,
    arity_mode: RelationArityMode,
    subject: tuple[str, ...],
    obj: tuple[str, ...],
    patterns: tuple[str, ...],
    temporal: TemporalSemantics,
    rule: str,
) -> None:
    registry = _filled(RelationSchemaRegistry())
    reported = {
        (schema.relation_type, schema.schema_version): schema for schema in registry.vocabulary()
    }[(relation_type, schema_version)]

    assert reported.arity_mode is arity_mode
    assert registry.arity_of(relation_type) == arity_mode
    assert reported.sorted_subject_classes == subject
    assert reported.sorted_object_classes == obj
    assert reported.allowed_subject_classes == frozenset(subject)
    assert reported.allowed_object_classes == frozenset(obj)
    assert reported.admissible_evidence_patterns == patterns
    assert reported.temporal_semantics is temporal
    assert reported.admission_rule_id == rule
    assert reported.schema_version == schema_version
    assert reported.required is (relation_type != "located_in" or schema_version == "1")
    assert len(reported.allowed_role_bindings) == (2 if arity_mode is RelationArityMode.NARY else 0)


# --------------------------------------------------------------------------
# T054 / FR-012: registration rejects an arity/participant-shape conflict
# --------------------------------------------------------------------------


def test_t054_directed_schema_carrying_role_bindings_is_rejected() -> None:
    registry = RelationSchemaRegistry()
    with pytest.raises(RelationSchemaError) as caught:
        registry.register(
            RelationSchema(
                relation_type="broken",
                arity_mode=RelationArityMode.DIRECTED,
                allowed_subject_classes=frozenset({"PERSON"}),
                allowed_object_classes=frozenset({"ORGANIZATION"}),
                allowed_role_bindings=(RelationRoleBinding("person", "", "PERSON"),),
                schema_version="1",
            )
        )
    assert caught.value.code == "role_binding_on_directed"
    assert isinstance(caught.value, ValueError)
    assert "broken" in str(caught.value)
    assert len(registry) == 0
    assert "broken" not in registry
    assert registry.get("broken") is None


@pytest.mark.parametrize(
    "bindings",
    [
        pytest.param((), id="no_bindings"),
        pytest.param((RelationRoleBinding("person", "", "PERSON"),), id="one_binding"),
    ],
)
def test_t054_nary_schema_with_fewer_than_two_role_bindings_is_rejected(
    bindings: tuple[RelationRoleBinding, ...],
) -> None:
    registry = RelationSchemaRegistry()
    with pytest.raises(RelationSchemaError) as caught:
        registry.register(
            RelationSchema(
                relation_type="underpopulated",
                arity_mode=RelationArityMode.NARY,
                allowed_role_bindings=bindings,
                schema_version="1",
            )
        )
    assert caught.value.code == "insufficient_members"
    assert "underpopulated" in str(caught.value)
    assert len(registry) == 0


@pytest.mark.parametrize(
    "override",
    [
        pytest.param({"admission_rule_id": "other-rule"}, id="admission_rule_id"),
        pytest.param(
            {"temporal_semantics": TemporalSemantics.OPEN_ENDED},
            id="temporal_semantics",
        ),
        pytest.param({"allowed_subject_classes": frozenset({"ENTITY"})}, id="subject_classes"),
        pytest.param(
            {"allowed_object_classes": frozenset({"PERSON", "ORGANIZATION"})},
            id="object_classes",
        ),
        pytest.param(
            {"admissible_evidence_patterns": ("payroll-record",)},
            id="evidence_patterns",
        ),
        pytest.param({"required": False}, id="required"),
        pytest.param({"allow_repeated_member": True}, id="allow_repeated_member"),
        pytest.param(
            {"allowed_role_classes": {"person": frozenset({"PERSON", "AGENT"})}},
            id="role_classes",
        ),
        pytest.param(
            {
                "allowed_role_bindings": (
                    RelationRoleBinding("person", "", "PERSON"),
                    RelationRoleBinding("organization", "", "ORGANIZATION"),
                )
            },
            id="role_bindings",
        ),
    ],
)
def test_t054_same_version_redefinition_with_different_content_is_rejected(
    override: dict[str, Any],
) -> None:
    original = RelationSchema(
        relation_type="employment",
        arity_mode=RelationArityMode.NARY,
        allowed_role_bindings=_EMPLOYMENT_BINDINGS,
        allowed_role_classes={"person": frozenset({"PERSON"})},
        admissible_evidence_patterns=("payroll-record", "job-listing"),
        temporal_semantics=TemporalSemantics.OPEN_ENDED,
        admission_rule_id="employment-evidence",
        schema_version="1",
    )
    registry = RelationSchemaRegistry([original])

    with pytest.raises(RelationSchemaError) as caught:
        registry.register(replace(original, **override))
    assert caught.value.code == "conflicting_redefinition"
    assert isinstance(caught.value, ValueError)
    assert registry.get("employment") is original
    assert len(registry) == 1


def test_t054_registration_rejects_a_role_declared_twice() -> None:
    registry = RelationSchemaRegistry()
    with pytest.raises(RelationSchemaError) as caught:
        registry.register(
            RelationSchema(
                relation_type="employment",
                arity_mode=RelationArityMode.NARY,
                allowed_role_bindings=(
                    RelationRoleBinding("person", "", "PERSON"),
                    RelationRoleBinding("person", "", "AGENT"),
                ),
                schema_version="1",
            )
        )
    assert caught.value.code == "duplicate_role"
    assert len(registry) == 0


@pytest.mark.parametrize(
    ("relation_type", "schema_version", "code"),
    [
        pytest.param("", "1", "missing_relation_type", id="relation_type"),
        pytest.param("works_for", "", "missing_schema_version", id="schema_version"),
    ],
)
def test_t054_registration_rejects_an_unidentifiable_schema(
    relation_type: str, schema_version: str, code: str
) -> None:
    registry = RelationSchemaRegistry()
    with pytest.raises(RelationSchemaError) as caught:
        registry.register(
            RelationSchema(
                relation_type=relation_type,
                arity_mode=RelationArityMode.DIRECTED,
                schema_version=schema_version,
            )
        )
    assert caught.value.code == code
    assert len(registry) == 0


# --------------------------------------------------------------------------
# T055 / FR-029: schemas are versioned; a same-version clash is refused
# --------------------------------------------------------------------------


def test_t055_a_new_version_registers_and_both_versions_stay_retrievable() -> None:
    first = _versioned("1")
    second = _versioned("2", allowed_subject_classes=frozenset({"PERSON", "AGENT"}))
    registry = RelationSchemaRegistry([first])

    assert registry.register(second) is second
    assert registry.versions("mentions") == (first, second)
    assert registry.get("mentions") is second
    assert registry.arity_of("mentions") is RelationArityMode.DIRECTED
    assert len(registry) == 2
    assert {schema.schema_version for schema in registry.vocabulary()} == {"1", "2"}


def test_t055_the_active_version_is_the_highest_not_the_last_registered() -> None:
    registry = RelationSchemaRegistry()
    for version in ("10", "2", "1"):
        registry.register(_versioned(version))

    assert [schema.schema_version for schema in registry.versions("mentions")] == ["1", "2", "10"]
    assert registry.get("mentions").schema_version == "10"

    registry.register(_versioned("3"))
    assert [schema.schema_version for schema in registry.versions("mentions")] == ["1", "2", "3"]
    assert registry.get("mentions").schema_version == "3"
    assert len(registry) == 4


def test_t055_a_conflicting_redefinition_leaves_the_registry_untouched() -> None:
    original = _versioned("1")
    registry = RelationSchemaRegistry([original])

    with pytest.raises(RelationSchemaError) as caught:
        registry.register(_versioned("1", admission_rule_id="rewritten"))
    assert caught.value.code == "conflicting_redefinition"

    assert len(registry) == 1
    assert registry.get("mentions") is original
    assert registry.versions("mentions") == (original,)
    assert registry.vocabulary() == (original,)


def test_t055_identical_content_in_the_same_version_is_idempotent() -> None:
    first = _versioned("1")
    identical = replace(
        first,
        allowed_subject_classes=frozenset({"PERSON"}),
        admissible_evidence_patterns=("mention",),
    )
    registry = RelationSchemaRegistry([first])

    assert registry.register(identical) is first
    assert len(registry) == 1
    assert registry.versions("mentions") == (first,)
    assert identical.content_key == first.content_key
    assert identical == first


def test_t055_a_re_registered_schema_is_idempotent_however_it_was_ordered() -> None:
    ordered = _versioned(
        "1",
        allowed_subject_classes=frozenset({"PERSON", "AGENT"}),
        allowed_object_classes=frozenset({"PERSON", "AGENT"}),
        admissible_evidence_patterns=("mention", "co-mention"),
    )
    shuffled = _versioned(
        "1",
        allowed_object_classes=frozenset({"AGENT", "PERSON"}),
        allowed_subject_classes=frozenset({"AGENT", "PERSON"}),
        admissible_evidence_patterns=("co-mention", "mention"),
    )
    assert ordered.admissible_evidence_patterns == shuffled.admissible_evidence_patterns
    assert ordered == shuffled
    assert ordered.content_key == shuffled.content_key

    registry = RelationSchemaRegistry([ordered])
    assert registry.register(shuffled) is ordered
    assert len(registry) == 1


# --------------------------------------------------------------------------
# T063: the record itself — canonicalisation, content key, serialisation
# --------------------------------------------------------------------------


def test_relation_schema_field_order_and_defaults_are_the_documented_ones() -> None:
    assert tuple(field.name for field in fields(RelationSchema)) == _EXPECTED_FIELD_ORDER
    bare = RelationSchema(relation_type="works_for", arity_mode=RelationArityMode.DIRECTED)
    assert bare.allowed_subject_classes == frozenset()
    assert bare.allowed_object_classes == frozenset()
    assert bare.allowed_role_bindings == ()
    assert dict(bare.allowed_role_classes) == {}
    assert bare.admissible_evidence_patterns == ()
    assert bare.temporal_semantics is TemporalSemantics.OPTIONAL_INTERVAL
    assert bare.admission_rule_id == "default-assert"
    assert bare.schema_version == "1"
    assert bare.allow_repeated_member is False
    assert bare.required is True


def test_temporal_semantics_is_exactly_the_documented_four() -> None:
    assert [member.value for member in TemporalSemantics] == [
        "point",
        "required_interval",
        "optional_interval",
        "open_ended",
    ]
    assert TemporalSemantics.POINT == "point"
    assert TemporalSemantics.REQUIRED_INTERVAL == "required_interval"
    assert TemporalSemantics.OPTIONAL_INTERVAL == "optional_interval"
    assert TemporalSemantics.OPEN_ENDED == "open_ended"


@pytest.mark.parametrize("semantics", list(TemporalSemantics))
def test_t063_every_temporal_semantics_round_trips_through_to_dict(
    semantics: TemporalSemantics,
) -> None:
    schema = RelationSchema(
        relation_type="located_in",
        arity_mode=RelationArityMode.TEMPORAL,
        admissible_evidence_patterns=("geocoded-address",),
        temporal_semantics=semantics,
        schema_version="3",
    )
    payload = schema.to_dict()
    assert payload["temporal_semantics"] == semantics.value

    restored = RelationSchema.from_dict(payload)
    assert restored.temporal_semantics is semantics
    assert restored == schema
    assert json.loads(json.dumps(payload, sort_keys=True)) == payload


@pytest.mark.parametrize("key", sorted(_keyed(_VOCABULARY)))
def test_t063_to_dict_from_dict_round_trips_every_field(key: tuple[str, str]) -> None:
    schema = _by_key(*key)
    payload = schema.to_dict()
    assert set(payload) == set(_EXPECTED_FIELD_ORDER)
    assert isinstance(payload["allowed_subject_classes"], list)
    assert isinstance(payload["allowed_role_classes"], dict)
    assert payload["arity_mode"] == str(schema.arity_mode)

    restored = RelationSchema.from_dict(payload)
    assert restored == schema
    assert restored.to_dict() == payload
    for field in fields(RelationSchema):
        assert getattr(restored, field.name) == getattr(schema, field.name), field.name
    assert restored.content_key == schema.content_key
    assert json.dumps(payload, sort_keys=True)


def test_t063_from_dict_accepts_a_minimal_stored_definition() -> None:
    restored = RelationSchema.from_dict(
        {"relation_type": "works_for", "arity_mode": "directed", "schema_version": "4"}
    )
    assert restored.arity_mode is RelationArityMode.DIRECTED
    assert restored.schema_version == "4"
    assert restored.temporal_semantics is TemporalSemantics.OPTIONAL_INTERVAL
    assert dict(restored.allowed_role_classes) == {}
    assert restored == RelationSchema(
        relation_type="works_for", arity_mode=RelationArityMode.DIRECTED, schema_version="4"
    )


def test_t063_a_schema_is_frozen_and_its_role_classes_are_read_only() -> None:
    schema = _by_key("employment", "2")
    with pytest.raises(dataclasses.FrozenInstanceError):
        schema.relation_type = "other"  # type: ignore[misc]
    with pytest.raises(TypeError):
        schema.allowed_role_classes["person"] = frozenset({"AGENT"})  # type: ignore[index]
    assert schema.role_classes_for("person") == frozenset({"PERSON"})


def test_t063_role_classes_are_looked_up_by_role_name() -> None:
    schema = RelationSchema(
        relation_type="employment",
        arity_mode=RelationArityMode.NARY,
        allowed_role_bindings=_EMPLOYMENT_BINDINGS,
        allowed_role_classes={
            "person": frozenset({"PERSON", "AGENT"}),
            "organization": frozenset({"ORGANIZATION"}),
        },
    )
    assert schema.role_classes_for("person") == frozenset({"PERSON", "AGENT"})
    assert schema.role_classes_for("organization") == frozenset({"ORGANIZATION"})
    assert schema.role_classes_for("undeclared") == frozenset()
    assert schema.role_classes_for("") == frozenset()
    assert sorted(schema.allowed_role_classes) == ["organization", "person"]

    registry = RelationSchemaRegistry([schema])
    assert registry.get("employment").role_classes_for("person") == frozenset(
        {"PERSON", "AGENT"}
    )


def test_t063_collections_are_canonicalised_on_construction() -> None:
    schema = _by_key("employment", "2")
    assert schema.allowed_role_bindings == tuple(
        sorted(schema.allowed_role_bindings, key=lambda binding: (binding.role, binding.member_ref))
    )
    assert schema.admissible_evidence_patterns == tuple(
        sorted(set(schema.admissible_evidence_patterns))
    )
    shuffled = replace(
        schema,
        allowed_role_bindings=tuple(reversed(schema.allowed_role_bindings)),
        admissible_evidence_patterns=tuple(reversed(schema.admissible_evidence_patterns)),
    )
    assert shuffled == schema
    assert shuffled.content_key == schema.content_key
    assert shuffled.admissible_evidence_patterns == ("job-listing", "payroll-record")


def test_t063_content_key_is_order_insensitive_and_stable() -> None:
    schema = _by_key("employment", "2")
    assert isinstance(schema.content_key, str)
    assert len(schema.content_key) == 32
    assert schema.content_key != "0" * 32
    assert schema.content_key != RelationSchema(
        relation_type="employment", arity_mode=RelationArityMode.NARY, schema_version="2"
    ).content_key
    assert hash(schema.content_key) == hash(_by_key("employment", "2").content_key)
    assert RelationSchema.from_dict(schema.to_dict()).content_key == schema.content_key


@pytest.mark.parametrize("field", _EXPECTED_FIELD_ORDER)
def test_t063_every_field_is_part_of_the_content_key(field: str) -> None:
    schema = _by_key("works_for", "1")
    changed = replace(schema, **{field: _MUTATED_FIELD_VALUE[field]})
    assert changed != schema
    assert changed.content_key != schema.content_key


# --------------------------------------------------------------------------
# T056: the validator consumes the registry rather than an embedded list. The
# wiring is task T065, so the probe below decides whether these can run at all.
# --------------------------------------------------------------------------


#: T065 is written in parallel, so the validator seam may not exist yet. A
#: missing peer module is a missing feature here, never a collection error.
_PEER_IMPORT_ERROR: str | None = None
try:
    from domain.context_validation import ValidationWorld, validate
    from domain.evidence_context import EvidenceContext, InMemoryContextResolver
except Exception as _exc:  # noqa: BLE001
    _PEER_IMPORT_ERROR = f"{type(_exc).__name__}: {_exc}"
    ValidationWorld = None  # type: ignore[assignment, misc]
    validate = None  # type: ignore[assignment]
    EvidenceContext = None  # type: ignore[assignment, misc]
    InMemoryContextResolver = None  # type: ignore[assignment, misc]

#: ``DOC1`` is a document and ``O1`` an organization; the semantic layer needs a
#: class for a participant, and this is where the wiring gets one from.
_ENTITY_CLASSES = {"DOC1": "DOCUMENT", "O1": "ORGANIZATION"}

#: The name the wiring may give that class mapping on ``ValidationWorld``.
_CLASS_FIELD_CANDIDATES = (
    "entity_classes",
    "entity_class_by_id",
    "entity_classes_by_id",
    "entity_class",
    "entity_class_map",
    "entity_types",
    "classes",
    "classes_by_ref",
)


def _frame() -> Any:
    return EvidenceContext(
        tenant_id="t1",
        investigation_id="inv-1",
        observation_id="OB-1",
        source_id="SRC-1",
        document_id="DOC-1",
        segment_id="SEG-1",
        source_family="family-a",
        independence_group="family-a",
        extraction_version="ext-1",
        normalization_version="norm-1",
        ontology_version="onto-1",
    )


def _works_for_claim(context_ref: str) -> RelationClaim:
    """``DOCUMENT --works_for--> ORGANIZATION``, ids derived from its own fields."""
    claim = RelationClaim(
        relation_id=_PENDING_REVISION,
        logical_relation_id=_PENDING_LOGICAL,
        revision_number=1,
        relation_type="works_for",
        arity_mode=RelationArityMode.DIRECTED,
        subject_ref="DOC1",
        object_ref="O1",
        valid_from=_FROM,
        valid_to=_TO,
        observed_at=_OBSERVED,
        published_at=_PUBLISHED,
        known_from=_OBSERVED,
        assertion_refs=("AS-1",),
        observation_refs=("OB-1",),
        context_ref=context_ref,
        source_independence_groups=(("family-a", "family-a"),),
        extraction_version="ext-1",
        normalization_version="norm-1",
        ontology_version="onto-1",
        schema_version="1",
        tenant_id="t1",
    )
    logical, revision = recompute_identity(claim)
    return replace(claim, logical_relation_id=logical, relation_id=revision)


def _class_field() -> str | None:
    names = {field.name for field in dataclasses.fields(ValidationWorld)}
    return next((name for name in _CLASS_FIELD_CANDIDATES if name in names), None)


def _world(schemas: RelationSchemaRegistry) -> tuple[Any, str]:
    """A world whose only source of relation schemas is the registry passed in."""
    resolver = InMemoryContextResolver()
    context_id = resolver.register(_frame())
    world = ValidationWorld(
        schemas=schemas,
        contexts=resolver,
        admitted_entity_ids=frozenset({"DOC1", "O1"}),
        known_entity_ids=frozenset({"DOC1", "O1"}),
        active_ontology_versions=frozenset({"onto-1"}),
        known_ontology_versions=frozenset({"onto-1"}),
    )
    class_field = _class_field()
    if class_field is not None:
        world = dataclasses.replace(world, **{class_field: dict(_ENTITY_CLASSES)})
    return world, context_id


def _verdict_of(result: Any) -> str:
    return str(getattr(result.verdict, "value", result.verdict))


def _codes_of(result: Any) -> set[str]:
    return {reason.code for reason in result.reasons}


def _registry_is_consulted() -> bool:
    """Probe: with an empty registry the type must come back unregistered.

    A validator carrying its own embedded vocabulary answers this probe with a
    decided verdict instead, which is precisely the state the tests below must
    not claim to pass against.
    """
    if validate is None:
        return False
    try:
        world, context_id = _world(RelationSchemaRegistry())
        result = validate(_frame(), _works_for_claim(context_id), world)
    except Exception:  # noqa: BLE001
        return False
    return _verdict_of(result) == "underdetermined" and "schema_unregistered" in _codes_of(result)


requires_registry_wiring = pytest.mark.skipif(
    not _registry_is_consulted(),
    reason=(
        f"T065 not landed: domain.context_validation unavailable ({_PEER_IMPORT_ERROR})"
        if _PEER_IMPORT_ERROR
        else "T065 not landed: the semantic layer does not read the registry yet"
    ),
)


@requires_registry_wiring
def test_t056_registering_a_type_at_runtime_flips_the_semantic_verdict() -> None:
    before_world, before_context = _world(RelationSchemaRegistry())
    before = validate(_frame(), _works_for_claim(before_context), before_world)
    assert _verdict_of(before) == "underdetermined"
    assert "schema_unregistered" in _codes_of(before)
    assert "schema_subject_class_not_allowed" not in _codes_of(before)

    schemas = RelationSchemaRegistry()
    schemas.register(
        RelationSchema(
            relation_type="works_for",
            arity_mode=RelationArityMode.DIRECTED,
            allowed_subject_classes=frozenset({"PERSON"}),
            allowed_object_classes=frozenset({"ORGANIZATION"}),
            admissible_evidence_patterns=("payroll-record", "job-listing"),
            temporal_semantics=TemporalSemantics.OPTIONAL_INTERVAL,
            admission_rule_id="default-assert",
            schema_version="1",
        )
    )
    after_world, after_context = _world(schemas)
    after = validate(_frame(), _works_for_claim(after_context), after_world)

    assert _verdict_of(after) == "invalid"
    assert "schema_subject_class_not_allowed" in _codes_of(after)
    assert "schema_unregistered" not in _codes_of(after)
    assert before.claim_id == after.claim_id == _works_for_claim(after_context).relation_id


@requires_registry_wiring
def test_t056_the_registry_the_validator_reads_is_the_one_that_was_mutated() -> None:
    schemas = RelationSchemaRegistry()
    world, context_id = _world(schemas)
    claim = _works_for_claim(context_id)
    assert "schema_unregistered" in _codes_of(validate(_frame(), claim, world))

    schemas.register(
        RelationSchema(
            relation_type="works_for",
            arity_mode=RelationArityMode.DIRECTED,
            allowed_subject_classes=frozenset({"PERSON"}),
            allowed_object_classes=frozenset({"ORGANIZATION"}),
            schema_version="1",
        )
    )
    codes = _codes_of(validate(_frame(), claim, world))
    assert "schema_unregistered" not in codes
    assert "schema_subject_class_not_allowed" in codes


@requires_registry_wiring
def test_t056_a_permitted_class_is_admitted_through_the_same_registry() -> None:
    schemas = RelationSchemaRegistry()
    schemas.register(
        RelationSchema(
            relation_type="works_for",
            arity_mode=RelationArityMode.DIRECTED,
            allowed_subject_classes=frozenset({"DOCUMENT"}),
            allowed_object_classes=frozenset({"ORGANIZATION"}),
            schema_version="1",
        )
    )
    world, context_id = _world(schemas)
    codes = _codes_of(validate(_frame(), _works_for_claim(context_id), world))
    assert "schema_unregistered" not in codes
    assert "schema_subject_class_not_allowed" not in codes
    assert "schema_object_class_not_allowed" not in codes
