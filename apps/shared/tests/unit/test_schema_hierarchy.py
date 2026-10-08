"""Contract: the type hierarchy is walkable (FollowTheMoney-shaped, spec 021).

The obstacle this pins down: ``SchemaDefinition.extends`` was in the dataclass from the
start and populated for exactly one schema -- ``Company extends=("Organization",)``. So the
platform had no type hierarchy to ask questions about, which is why ``entity_type`` ended
up free text written by two HTTP routes and constrained by nothing.

Four properties matter, and each one was a failure mode:

**The hierarchy is declared, not inferred.** ``Person`` and ``Organization`` share every
property in the table and are still not subtypes of one another. Inferring from property
overlap would invent subsumptions the registry cannot justify, so the relations are
written out.

**Every admissible type is registered.** Seven of the seventeen names in ``NAME_VALID``
could not be assigned to a stored entity at all, because nothing had ever registered
them. ``Thing`` is now registered too: it is the declared top, so a walk terminates
somewhere and asking for it is a question the registry answers.

**``type_closure`` is the set a derived type may assert.** It is the input to typing as
derivation rather than as a written field, so its shape is part of the contract.

**Cycles do not hang.** A cycle in ``extends`` is a data error and must surface as a
terminating walk, not as a spin.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from domain.schema import (
    DEFAULT_REGISTRY,
    NAME_VALID,
    SchemaDefinition,
    SchemaRegistry,
    UnknownSchemaError,
)

pytestmark = pytest.mark.contract

REGISTRY = DEFAULT_REGISTRY


class TestCoverage:
    def test_every_admissible_name_is_registered(self) -> None:
        assert set(NAME_VALID) <= set(REGISTRY.schemas)

    def test_the_declared_top_is_registered(self) -> None:
        # Otherwise ``ancestors_of`` terminates at a name that cannot be resolved, and
        # asking for it raises instead of answering.
        assert "Thing" in REGISTRY.schemas

    def test_every_extends_target_resolves(self) -> None:
        for name, definition in REGISTRY.schemas.items():
            for parent in definition.extends:
                assert parent in REGISTRY.schemas, f"{name} extends unregistered {parent}"


class TestAncestors:
    def test_a_leaf_has_no_ancestors(self) -> None:
        assert REGISTRY.ancestors_of("Thing") == ()

    def test_a_company_is_an_organization_and_a_legal_entity(self) -> None:
        ancestors = REGISTRY.ancestors_of("Company")
        assert "Organization" in ancestors
        assert "LegalEntity" in ancestors

    def test_the_walk_reaches_the_declared_top(self) -> None:
        assert "Thing" in REGISTRY.ancestors_of("Company")

    def test_a_type_is_not_its_own_ancestor(self) -> None:
        assert "Company" not in REGISTRY.ancestors_of("Company")

    def test_person_is_not_an_organization_despite_identical_properties(self) -> None:
        # The whole reason the hierarchy is declared rather than inferred.
        assert REGISTRY.is_subtype_of("Person", "Thing") is True
        assert REGISTRY.is_subtype_of("Person", "Organization") is False
        assert REGISTRY.is_subtype_of("Organization", "Person") is False

    def test_an_unknown_name_is_refused_rather_than_empty(self) -> None:
        with pytest.raises(UnknownSchemaError):
            REGISTRY.ancestors_of("NoSuchSchema")

    def test_a_cycle_terminates(self) -> None:
        registry = SchemaRegistry(
            schemas={
                "A": SchemaDefinition("A", extends=("B",)),
                "B": SchemaDefinition("B", extends=("A",)),
            }
        )
        # A cycle is a data error. The walk must finish and report what it saw, not spin.
        assert set(registry.ancestors_of("A")) <= {"A", "B"}


class TestDescendants:
    def test_legal_entity_owns_its_people_and_orgs(self) -> None:
        descendants = set(REGISTRY.descendants_of("LegalEntity"))
        assert {"Person", "Organization", "Company"} <= descendants

    def test_the_transitive_descendants_are_included(self) -> None:
        # Company is a grandchild of LegalEntity; a one-level walk would miss it.
        assert "Company" in REGISTRY.descendants_of("LegalEntity")

    def test_everything_but_the_top_is_a_descendant_of_the_top(self) -> None:
        assert len(REGISTRY.descendants_of("Thing")) == len(REGISTRY.schemas) - 1


class TestTypeClosure:
    def test_closure_is_the_type_then_its_ancestors(self) -> None:
        closure = REGISTRY.type_closure("Company")
        assert closure[0] == "Company"
        assert set(closure[1:]) == set(REGISTRY.ancestors_of("Company"))

    def test_a_leaf_closure_is_itself(self) -> None:
        assert REGISTRY.type_closure("Ownership") == ("Ownership", "Thing")

    def test_every_registered_type_has_a_closure_containing_itself(self) -> None:
        for name in REGISTRY.schemas:
            assert name in REGISTRY.type_closure(name)


class TestValidationStillWorks:
    def test_a_valid_entity_validates(self) -> None:
        REGISTRY.validate_entity("Person", {"name": [{"value": "X"}]})

    def test_an_unlisted_property_is_accepted_as_free_text(self) -> None:
        # FtM schemata take unlisted properties as free text, so an unknown *property*
        # is accepted; what is rejected is an unknown *type*.
        REGISTRY.validate_property("Person", "somethingUnlisted", "whatever")

    def test_an_empty_value_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            REGISTRY.validate_property("Person", "name", "   ")

    def test_the_literal_registry_is_sound(self) -> None:
        # Every declared property type is in the closed vocabulary and every ``extends``
        # target resolves. ``DEFAULT_REGISTRY`` is built by handing ``schemas=`` to the
        # constructor, which skips ``register`` -- so this is the only place its
        # declarations are actually checked.
        from domain.schema import _PROPERTY_TYPES

        for name, definition in REGISTRY.schemas.items():
            for prop, value_type in definition.properties.items():
                assert value_type in _PROPERTY_TYPES, f"{name}.{prop} -> {value_type}"
            for parent in definition.extends:
                assert parent in REGISTRY.schemas