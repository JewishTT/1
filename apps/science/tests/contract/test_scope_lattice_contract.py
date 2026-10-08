"""Contract: context is closed, ordered, and honest about what it could not place.

The flat design this replaces stored each observation with its own scope and never compared
them, so two questions had no answer: which entities does a question jointly span, and what
is the smallest set of entities that would add a genuinely new observation. Without a lattice
the second answer is "all of them", and growth enumerates pairs instead of reasoning about
closure.

What is pinned here:

* **Closure is computed** -- bottom is present, concepts are extent-closed.
* **Order is by extent, not by type** -- ordering on type would make the lattice depend on
  the typing being derived, which is the thing not yet derived.
* **Unplaced observations stay visible** -- an observation with no entity is not coverage.
* **Saturation is not emptiness** -- ``is_saturated`` also requires nothing unplaced.
* **A type disagreement falls back to ``UNKNOWN``** -- never last-write-wins, because that
  would make the answer depend on ingestion order.

Explicitly *not* claimed: multi-relational closure. See the module docstring -- the honest
version is a different module, not a flag.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from context.lattice import (
    ClosureOperator,
    Concept,
    ConceptOrder,
    ScopeLattice,
)

pytestmark = pytest.mark.contract

ROWS = [
    {"observation_ref": "o1", "entities": ["a", "b"], "entity_type": "person"},
    {"observation_ref": "o2", "entities": ["b", "c"], "entity_type": "organization"},
    {"observation_ref": "o3", "entities": ["c", "d"], "entity_type": "crypto"},
    {"observation_ref": "o4", "entities": [], "entity_type": "unknown"},
]


@pytest.fixture
def lattice() -> ScopeLattice:
    return ScopeLattice.from_observations(ROWS)


class TestClosure:
    def test_the_bottom_is_always_present(self, lattice: ScopeLattice) -> None:
        # Without a bottom the lattice has no identity, and any reduction that reaches the
        # empty scope fails instead of returning bottom -- which is the right answer for
        # "nothing in common".
        assert any(c.is_top for c in lattice.concepts())

    def test_every_entity_has_a_concept(self, lattice: ScopeLattice) -> None:
        intents = {ref for c in lattice.concepts() for ref in c.intent}
        assert intents == set(lattice.entities())

    def test_every_observation_appears_in_some_extent(self, lattice: ScopeLattice) -> None:
        extents = {o for c in lattice.concepts() for o in c.extent}
        assert extents == {"o1", "o2", "o3"}

    def test_an_entity_in_two_observations_carries_both(self, lattice: ScopeLattice) -> None:
        assert lattice.observations_of("b") == ("o1", "o2")

    def test_an_empty_lattice_is_still_well_formed(self) -> None:
        empty = ScopeLattice.from_observations([])
        assert empty.concepts()[0].is_top
        assert empty.gradient(empty.top()).is_saturated()

    def test_no_concept_is_left_unsupported(self, lattice: ScopeLattice) -> None:
        # ``unsatisfied`` exists to catch a generator that produced an unbacked concept; with
        # no such generator it must be empty, or the check itself is untested.
        assert lattice.unsatisfied() == ()
        assert lattice.unsubsumed() == ()


class TestOrder:
    def test_ordering_follows_extent_inclusion(self, lattice: ScopeLattice) -> None:
        small = Concept(intent=frozenset({"a"}), extent=frozenset({"o1"}))
        large = Concept(intent=frozenset({"a", "b"}), extent=frozenset({"o1", "o2"}))
        assert ConceptOrder.le(small, large)
        assert ConceptOrder.lt(small, large)
        assert ConceptOrder.ge(large, small)
        assert not ConceptOrder.le(large, small)

    def test_equal_extents_compare_equal(self) -> None:
        left = Concept(intent=frozenset({"a"}), extent=frozenset({"o1"}))
        right = Concept(intent=frozenset({"z"}), extent=frozenset({"o1"}))
        assert ConceptOrder.compare(left, right) == 0

    def test_join_unions_extents_and_meet_intersects_them(self) -> None:
        left = Concept(intent=frozenset({"a", "b"}), extent=frozenset({"o1"}))
        right = Concept(intent=frozenset({"b", "c"}), extent=frozenset({"o2"}))
        join = ConceptOrder.join(left, right)
        meet = ConceptOrder.meet(left, right)
        # join is the least concept above both: more observations, fewer entities.
        assert join.extent == frozenset({"o1", "o2"})
        assert join.intent == frozenset({"b"})
        # meet is the greatest concept below both: fewer observations, more entities.
        assert meet.extent == frozenset()
        assert meet.intent == frozenset({"a", "b", "c"})

    def test_a_join_is_a_projection_not_an_observation(self) -> None:
        # The join of two concepts is a claim built from them. Calling it EXACT would let a
        # reader treat a derived scope as observed.
        left = Concept(intent=frozenset({"a"}), extent=frozenset({"o1"}))
        right = Concept(intent=frozenset({"b"}), extent=frozenset({"o2"}))
        assert ConceptOrder.join(left, right).operator is ClosureOperator.PROJECTED


class TestUnplacedIsNotCoverage:
    def test_an_observation_with_no_entity_is_unplaced(self, lattice: ScopeLattice) -> None:
        assert lattice.unplaced() == ("o4",)

    def test_unplaced_does_not_become_an_entity(self, lattice: ScopeLattice) -> None:
        assert "o4" not in lattice.entities()

    def test_saturation_requires_nothing_unplaced(self, lattice: ScopeLattice) -> None:
        # The distinction that matters: "we looked and could not place it" and "it was
        # placed" must never be the same number.
        assert not lattice.gradient(lattice.top()).is_saturated()


class TestGradient:
    def test_it_prefers_entities_adding_the_most_new_observations(self, lattice: ScopeLattice) -> None:
        seed = Concept(intent=frozenset({"a"}), extent=frozenset({"o1"}))
        step = lattice.gradient(seed)
        # "c" brings o2 and o3; "b" brings only o2, since o1 is already covered.
        assert step.members[0] == "c"
        assert step.members[1] == "b"
        assert step.new_observations == 2

    def test_an_entity_already_in_concept_is_not_offered(self, lattice: ScopeLattice) -> None:
        seed = Concept(intent=frozenset({"a", "b"}), extent=frozenset({"o1", "o2"}))
        assert "a" not in lattice.gradient(seed).members

    def test_an_entity_adding_nothing_new_is_blocked_not_offered(self) -> None:
        # "y" is seen only in o2, which the seed already covers, so widening by it would
        # cost a lookup and add no observation. It belongs in blocked_by, not members.
        rows = [
            {"observation_ref": "o1", "entities": ["x"], "entity_type": "person"},
            {"observation_ref": "o2", "entities": ["x", "y"], "entity_type": "person"},
        ]
        narrow = ScopeLattice.from_observations(rows)
        seed = Concept(intent=frozenset({"x"}), extent=frozenset({"o1", "o2"}))
        step = narrow.gradient(seed)
        assert "y" not in step.members
        assert "y" in step.blocked_by
        assert step.new_observations == 0

    def test_the_gradient_serializes_with_its_honest_counts(self, lattice: ScopeLattice) -> None:
        payload = lattice.gradient(lattice.top()).as_dict()
        assert payload["unplaced_observations"] == 1
        assert payload["saturated"] is False

    def test_widening_stays_above_the_seed(self, lattice: ScopeLattice) -> None:
        seed = lattice.concepts()[1]
        for wider in lattice.widen(seed):
            assert ConceptOrder.le(seed, wider)

    def test_a_widened_concept_is_marked_projected(self, lattice: ScopeLattice) -> None:
        seed = lattice.concepts()[1]
        assert all(c.operator is ClosureOperator.PROJECTED for c in lattice.widen(seed))


class TestTypingIsDerivedNotWritten:
    def test_a_type_comes_from_the_shared_registry(self, lattice: ScopeLattice) -> None:
        # Person inherits LegalEntity; the schema walk is what makes that queryable.
        assert lattice.member("a").schema == "Person"

    def test_a_type_is_attributable_to_a_method(self, lattice: ScopeLattice) -> None:
        assert lattice.supports_type("a")
        assert any("typed" in s for s in lattice.supports_type("a"))

    def test_method_versions_are_visible(self, lattice: ScopeLattice) -> None:
        assert lattice.derivations().methods() == ("ontology.typing@v1",)

    def test_a_disagreement_becomes_unknown_not_last_write_wins(self) -> None:
        rows = [
            {"observation_ref": "o1", "entities": ["x"], "entity_type": "person"},
            {"observation_ref": "o2", "entities": ["x"], "entity_type": "organization"},
        ]
        split = ScopeLattice.from_observations(rows)
        # Last-write-wins would make the answer depend on ingestion order.
        assert split.type_of("x") is split.member("x").effective_type
        assert split.conflicts()["x"]
        assert {t.value for t in split.conflicts()["x"]} == {"person", "organization"}

    def test_a_conflicted_entity_has_no_type_claim_at_all(self) -> None:
        rows = [
            {"observation_ref": "o1", "entities": ["x"], "entity_type": "person"},
            {"observation_ref": "o2", "entities": ["x"], "entity_type": "organization"},
        ]
        assert ScopeLattice.from_observations(rows).supports_type("x") == ()

    def test_agreement_across_observations_keeps_the_type(self) -> None:
        rows = [
            {"observation_ref": "o1", "entities": ["x"], "entity_type": "person"},
            {"observation_ref": "o2", "entities": ["x"], "entity_type": "person"},
        ]
        agreed = ScopeLattice.from_observations(rows)
        assert agreed.type_of("x").value == "person"
        assert agreed.conflicts() == {}


class TestPerEntityTypes:
    def test_a_per_entity_type_is_not_overwritten_by_the_observation_type(self) -> None:
        # An observation mentioning a domain and a person must not label both "domain".
        rows = [{
            "observation_ref": "o1",
            "entity_type": "domain",
            "entities": [
                {"entity_ref": "a", "entity_type": "domain"},
                {"entity_ref": "b", "entity_type": "person"},
            ],
        }]
        typed = ScopeLattice.from_observations(rows)
        assert typed.type_of("a").value == "domain"
        assert typed.type_of("b").value == "person"

    def test_a_flat_ref_falls_back_to_the_observation_type(self) -> None:
        rows = [{"observation_ref": "o1", "entity_type": "domain", "entities": ["a"]}]
        assert ScopeLattice.from_observations(rows).type_of("a").value == "domain"

    def test_a_mixed_shape_reads_each_entry_on_its_own_terms(self) -> None:
        rows = [{
            "observation_ref": "o1",
            "entity_type": "unknown",
            "entities": [{"entity_ref": "a", "entity_type": "ip"}, "b"],
        }]
        mixed = ScopeLattice.from_observations(rows)
        assert mixed.type_of("a").value == "ip"
        assert mixed.type_of("b").value == "unknown"

    def test_every_entity_gets_a_schema_from_the_shared_registry(self) -> None:
        rows = [{"observation_ref": "o1", "entities": [
            {"entity_ref": "a", "entity_type": "crypto"},
        ]}]
        assert ScopeLattice.from_observations(rows).member("a").schema == "CryptoAddress"


class TestSnapshot:
    def test_it_counts_and_names_types(self, lattice: ScopeLattice) -> None:
        payload = lattice.snapshot()
        assert payload["entities"] == 4
        assert payload["observations"] == 3
        assert payload["unplaced"] == 1
        assert "person" in payload["types"]
