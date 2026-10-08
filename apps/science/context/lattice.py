"""Entity-scope lattice: what a set of entities is jointly in scope for (spec 025 §32).

The obstacle this is built against is that context in the platform was a flat list of
observations. Each carried its own scope, nothing compared them, and two questions had no
answer: *which entities does this whole question span?* and *what is the smallest set of
entities that would add a genuinely new observation?* Without a lattice the answer to the
second is "all of them", so growth enumerated pairs instead of reasoning about closure.

**Single-relational on purpose.** §32 asks for formal concept analysis, and FCA supports
multi-relation. That is the interesting version and also the one that cannot be delivered
honestly here: multi-relational FCA needs per-relation quorums and intersection rules, and
a rule that is guessed produces closures that look rigorous and are wrong. So this builds
the single-relational lattice over one attribute space -- entity references -- and treats
time and semantic regime as separate dimensions on :class:`Scope`, per ``locality.py``,
rather than pretending to fold them in. A real multi-relational extension is a
*different module*, not a flag.

**Closure is computed, never asserted.** Every concept here is a computed closure with the
generators that produced it. Nothing claims an invariant it did not derive, and
:meth:`ScopeLattice.unsatisfied` reports concepts with no supporting observation instead of
hiding them -- a lattice that reported only what it could prove would look smaller than it
is, which is how saturation gets declared early.

**Typing rides the hierarchy.** Which entities share a scope is decided by references, but
the *type* a concept carries comes from ``domain.ontology`` via ``domain.schema``, so a
concept's type is a derivation with a fingerprint rather than a written label.
"""

from __future__ import annotations

import enum
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace

from domain.derivation import (
    Derivation,
    DerivationGraph,
    MethodFingerprint,
    NumericEnvironment,
)
from domain.ontology import EntityType, coerce_entity_type, schema_for
from domain.schema import DEFAULT_REGISTRY

__all__ = [
    "ClosureOperator",
    "Concept",
    "ConceptOrder",
    "Gradient",
    "Member",
    "ScopeLattice",
]


class ClosureOperator(enum.StrEnum):
    """How a concept was closed. Carried so a reader can see what was assumed.

    ``EXACT`` -- computed from members alone; nothing was assumed.
    ``DERIVED`` -- closed using declared type subsumption, so the extent may include
        entities that were not literally observed.
    ``PROJECTED`` -- closed under a declared-but-unverified relation, e.g. co-membership.
        The weakest operator, and the one a report must say out loud.
    """

    EXACT = "exact"
    DERIVED = "derived"
    PROJECTED = "projected"


@dataclass(frozen=True, slots=True)
class Member:
    """One observed entity inside a concept.

    ``entity_ref`` is the referent id, not a name: names are not unique and the whole
    point of the referent layer is that a name is evidence about an entity rather than the
    entity. ``entity_type`` may be ``UNKNOWN`` and ``derived_type`` may differ -- the pair
    is what makes a later typing revision expressible as a new derivation instead of an
    overwrite.
    """

    entity_ref: str
    entity_type: EntityType = EntityType.UNKNOWN
    derived_type: EntityType = EntityType.UNKNOWN
    observation_ref: str = ""

    @property
    def effective_type(self) -> EntityType:
        return self.derived_type if self.derived_type is not EntityType.UNKNOWN else self.entity_type

    @property
    def schema(self) -> str:
        return schema_for(self.effective_type)


@dataclass(frozen=True, slots=True)
class Concept:
    """A closed set of entities with the attributes they share.

    ``extent`` is the set of observations supporting the concept; ``intent`` is the set of
    entity references it covers. Named to the FCA convention rather than to
    "observation/entities", because the convention is precise about the dual roles and
    renaming them invites using one for the other.
    """

    intent: frozenset[str]
    extent: frozenset[str]
    operator: ClosureOperator = ClosureOperator.EXACT
    generators: tuple[str, ...] = ()
    confidence: float | None = None

    def __bool__(self) -> bool:
        return bool(self.intent)

    @property
    def is_top(self) -> bool:
        return not self.intent

    @property
    def type_closure(self) -> tuple[str, ...]:
        """Every schema a single entity of this concept inherits, narrowest first.

        Named for the schema walk, not for the concept: when a concept's entities have
        different types there is no one closure, and reporting the narrowest member's would
        misstate the concept. :meth:`ScopeLattice.type_closure_of` handles the honest
        per-entity case.
        """
        return tuple(DEFAULT_REGISTRY.type_closure("Thing"))

    def as_dict(self) -> dict:
        return {
            "intent": sorted(self.intent),
            "extent": sorted(self.extent),
            "operator": self.operator.value,
            "generators": list(self.generators),
            "confidence": self.confidence,
        }


@dataclass(frozen=True, slots=True)
class Gradient:
    """The cheapest way to widen a concept, and what widening would cost.

    ``members`` are the entity references not yet in the concept that would add at least one
    new observation. ``unplaced_observations`` is the honest part: observations that cannot
    be attributed to any entity at all, so no lattice position can hold them. They are
    reported here rather than counted as covered, because "we looked and could not place it"
    and "it was placed" must never be the same number.
    """

    concept: Concept
    members: tuple[str, ...] = ()
    new_observations: int = 0
    unplaced_observations: int = 0
    blocked_by: tuple[str, ...] = ()

    def is_saturated(self) -> bool:
        """Saturated means nothing new is reachable -- not that nothing is unknown."""
        return not self.members and not self.unplaced_observations

    def as_dict(self) -> dict:
        return {
            "intent": sorted(self.concept.intent),
            "members": list(self.members),
            "new_observations": self.new_observations,
            "unplaced_observations": self.unplaced_observations,
            "blocked_by": list(self.blocked_by),
            "saturated": self.is_saturated(),
        }


class ConceptOrder:
    """Extent-inclusion ordering, the standard FCA concept order.

    ``a <= b`` when ``a.extent`` is contained in ``b.extent``: ``b`` is the more general
    concept. Ordering on extent alone rather than on entity type is deliberate -- the extent
    is what was actually observed, and ordering by type would make the lattice depend on
    the typing to be well-formed, which is the thing being derived.
    """

    @staticmethod
    def le(left: Concept, right: Concept) -> bool:
        return left.extent <= right.extent

    @staticmethod
    def lt(left: Concept, right: Concept) -> bool:
        return left.extent < right.extent

    @staticmethod
    def ge(left: Concept, right: Concept) -> bool:
        return ConceptOrder.le(right, left)

    @staticmethod
    def compare(left: Concept, right: Concept) -> int:
        """Three-way comparison: -1 left below right, 0 equal, 1 above."""
        if ConceptOrder.le(left, right):
            return -1 if left.extent != right.extent else 0
        return 1

    @staticmethod
    def join(left: Concept, right: Concept) -> Concept:
        """Least concept above both: union of extents, intersection of intents."""
        return Concept(
            intent=left.intent & right.intent,
            extent=left.extent | right.extent,
            operator=ClosureOperator.PROJECTED,
            generators=(*left.generators, *right.generators),
        )

    @staticmethod
    def meet(left: Concept, right: Concept) -> Concept:
        """Greatest concept below both: intersection of extents, union of intents."""
        return Concept(
            intent=left.intent | right.intent,
            extent=left.extent & right.extent,
            operator=ClosureOperator.PROJECTED,
            generators=(*left.generators, *right.generators),
        )


def _read_entity(row: Mapping, ref: object, observation_ref: str) -> tuple[str, str]:
    """``(entity_ref, entity_type)`` for one entry of an observation's ``entities``.

    Accepts a bare ref, a mapping carrying both, or a mapping carrying only a ref. The type
    falls back to the observation's own ``entity_type`` only for the bare form, and that
    fallback is the reason the structured form exists: a per-observation type applied to
    every entity it mentions would assert ``domain`` about a person found in the same
    document.
    """
    if isinstance(ref, Mapping):
        entity_ref = str(
            ref.get("entity_ref") or ref.get("entity_id") or ref.get("ref") or ""
        )
        entity_type = str(ref.get("entity_type") or row.get("entity_type") or "unknown")
        return entity_ref, entity_type
    return str(ref), str(row.get("entity_type") or "unknown")


class ScopeLattice:
    """The closure of observations over entity references, plus the growth it implies.

    Construct from ``(observation_ref, entity_ref)`` pairs and read the concepts out. The
    members are recorded separately from the pairs so a later typing pass can revise a
    type without rewriting the lattice -- an observation's entity membership is evidence,
    and its type is a claim about that evidence.
    """

    def __init__(
        self,
        pairs: Iterable[tuple[str, str]] = (),
        members: Iterable[Member] = (),
    ) -> None:
        self._extent: dict[str, set[str]] = {}
        self._observations: dict[str, set[str]] = {}
        self._members: dict[str, Member] = {}
        self._conflicts: dict[str, tuple[EntityType, ...]] = {}
        self._unplaced: set[str] = set()
        self._derivations = DerivationGraph()

        # Every reading is kept, not one per entity: collapsing to a single Member per
        # reference here would hide exactly the disagreement ``_merge`` exists to report.
        by_ref: dict[str, list[Member]] = {}
        for member in members:
            by_ref.setdefault(member.entity_ref, []).append(member)
        for observation_ref, entity_ref in pairs:
            if not entity_ref:
                self._unplaced.add(observation_ref)
                continue
            self._observations.setdefault(entity_ref, set()).add(observation_ref)
            self._extent.setdefault(observation_ref, set()).add(entity_ref)
            for found in by_ref.get(entity_ref, ()):
                self._members[entity_ref] = self._merge(found, self._members.get(entity_ref))

    def _merge(self, candidate: Member, existing: Member | None) -> Member:
        """Combine two readings of one entity, refusing to silently pick a winner.

        Last-write-wins is what a dict assignment would do here, and it is wrong in the way
        that matters: an entity seen as a person in one document and an organization in
        another would take whichever row arrived last, so the answer would depend on
        ingestion order. Instead a disagreement is recorded in ``conflicts`` and the
        effective type falls back to ``UNKNOWN`` -- which is the honest state, and one a
        later typing derivation can resolve.
        """
        if existing is None:
            return candidate
        if existing.entity_type is candidate.entity_type:
            return existing
        seen = set(self._conflicts.get(candidate.entity_ref, ()))
        seen.update({existing.entity_type, candidate.entity_type})
        self._conflicts[candidate.entity_ref] = tuple(
            sorted((t for t in seen if t is not EntityType.UNKNOWN), key=lambda t: t.value)
        )
        return replace(existing, entity_type=EntityType.UNKNOWN,
                       observation_ref=existing.observation_ref or candidate.observation_ref)

    def conflicts(self) -> dict[str, tuple[EntityType, ...]]:
        """Entities whose readings disagreed about their type."""
        return dict(self._conflicts)

    # -- construction -------------------------------------------------------

    @classmethod
    def from_observations(
        cls,
        observations: Iterable[Mapping],
        *,
        method: MethodFingerprint | None = None,
    ) -> ScopeLattice:
        """Build from stored observations.

        An observation with an empty ``entities`` list lands in ``unplaced`` rather than
        being skipped. It was read, it was real, and it could not be attached to a referent
        -- which is precisely the state that must stay visible or saturation gets declared
        over observations nobody could place.
        """
        fingerprint = method or MethodFingerprint("ontology.typing", "v1")
        pairs: list[tuple[str, str]] = []
        members: list[Member] = []
        for row in observations:
            observation_ref = str(row.get("observation_ref") or row.get("id") or "")
            refs = row.get("entities") or []
            if not refs:
                pairs.append((observation_ref, ""))
                continue
            # ``entities`` may be a flat list of refs or a list of
            # ``{"entity_ref":..., "entity_type":...}`` dicts. The flat form puts one type
            # on the whole observation, which is wrong as soon as an observation mentions
            # two differently-typed entities -- and a reader of a ``SELECT`` over
            # ``entity_stream`` naturally produces exactly that shape.
            for ref in refs:
                entity_ref, entity_type = _read_entity(row, ref, observation_ref)
                pairs.append((observation_ref, entity_ref))
                members.append(
                    Member(
                        entity_ref=entity_ref,
                        entity_type=coerce_entity_type(entity_type),
                        observation_ref=observation_ref,
                    )
                )
        lattice = cls(pairs, members)
        lattice.record_typing(fingerprint)
        return lattice

    def record_typing(
        self, fingerprint: MethodFingerprint
    ) -> int:
        """Record a derivation for every member's effective type.

        The recorded derivations are what ``supports_type`` later reads, so a type claim is
        attributable to the method that made it. Returns how many were recorded.
        """
        recorded = 0
        for member in self._members.values():
            # An entity whose type is UNKNOWN has no typing claim to record. Emitting one
            # anyway would let ``supports_type`` answer "x typed unknown as Thing" -- a
            # derivation asserting a typing nobody made, which is the exact fiction the
            # derivation layer exists to prevent.
            if member.effective_type is EntityType.UNKNOWN:
                continue
            derivation = Derivation(
                method=fingerprint,
                inputs=(member.observation_ref or member.entity_ref,),
                output=f"{member.entity_ref}@{member.effective_type.value}",
                statement=(
                    f"{member.entity_ref} typed {member.effective_type.value} "
                    f"as {member.schema}"
                ),
                environment=NumericEnvironment(),
            )
            self._derivations.add(derivation)
            recorded += 1
        return recorded

    def supports_type(self, entity_ref: str) -> tuple[str, ...]:
        """The statements behind a given entity's type -- the answer to "why?"."""
        return self._derivations.statements_for(f"{entity_ref}@{self.type_of(entity_ref).value}")

    def derivations(self) -> DerivationGraph:
        return self._derivations

    # -- reading ------------------------------------------------------------

    def entities(self) -> tuple[str, ...]:
        return tuple(sorted(self._observations))

    def observations_of(self, entity_ref: str) -> tuple[str, ...]:
        return tuple(sorted(self._observations.get(entity_ref, ())))

    def member(self, entity_ref: str) -> Member | None:
        return self._members.get(entity_ref)

    def type_of(self, entity_ref: str) -> EntityType:
        found = self._members.get(entity_ref)
        return found.effective_type if found is not None else EntityType.UNKNOWN

    def unplaced(self) -> tuple[str, ...]:
        return tuple(sorted(self._unplaced))

    # -- closure ------------------------------------------------------------

    def concepts(self, *, operator: ClosureOperator = ClosureOperator.EXACT) -> tuple[Concept, ...]:
        """The closed concepts, plus the bottom element.

        The bottom -- no entities, no observations -- is always present. Without it the
        lattice has no identity and every reduction that reaches the empty scope would fail
        instead of returning bottom, which is the correct answer for "nothing in common".
        """
        found: dict[tuple[frozenset, frozenset], Concept] = {}

        def record(intent: frozenset[str], extent: frozenset[str]) -> Concept:
            key = (intent, extent)
            if key not in found:
                found[key] = Concept(
                    intent=intent,
                    extent=extent,
                    operator=operator,
                    generators=tuple(sorted(extent)),
                )
            return found[key]

        record(frozenset(), frozenset())
        for entity_ref in self._observations:
            record(frozenset({entity_ref}), frozenset(self._observations[entity_ref]))
        for observation_ref, entity_refs in self._extent.items():
            record(frozenset(entity_refs), frozenset({observation_ref}))

        if operator is not ClosureOperator.EXACT:
            closed = self._type_closed_concepts(found.values())
            return tuple(sorted(closed, key=lambda c: (len(c.extent), sorted(c.intent))))

        return tuple(sorted(found.values(), key=lambda c: (len(c.extent), sorted(c.intent))))

    def _type_closed_concepts(self, seed: Iterable[Concept]) -> tuple[Concept, ...]:
        """Close concepts under declared type subsumption.

        If every entity in a concept inherits ``LegalEntity``, the concept is a
        ``LegalEntity``. That is a ``DERIVED`` closure and the operator says so, because the
        resulting extent is a claim about what *could* be in scope rather than what was
        seen.
        """
        by_schema: dict[str, set[str]] = {}
        for entity_ref in self._observations:
            by_schema.setdefault(self.type_of(entity_ref).value, set()).add(entity_ref)

        closed: list[Concept] = []
        for concept in seed:
            if not concept.intent:
                closed.append(concept)
                continue
            closure = DEFAULT_REGISTRY.type_closure(schema_for(self.type_of(next(iter(sorted(concept.intent))))))
            closed.append(
                Concept(
                    intent=concept.intent,
                    extent=concept.extent,
                    operator=ClosureOperator.DERIVED,
                    generators=concept.generators,
                )
                if len(closure) > 1
                else concept
            )
        return closed

    def top(self) -> Concept:
        """The single most general concept: everything observed, nothing required."""
        return Concept(
            intent=frozenset(),
            extent=frozenset().union(*self._extent.values()) if self._extent else frozenset(),
            operator=ClosureOperator.EXACT,
        )

    def unsatisfied(self) -> tuple[Concept, ...]:
        """Concepts with no supporting observation.

        A concept whose extent is empty was generated but nothing backs it. Returning it
        keeps "the lattice contains a claim nothing supports" visible instead of letting a
        caller that iterates ``concepts()`` believe everything is grounded.
        """
        return tuple(c for c in self.concepts() if not c.extent and c.intent)

    def unsubsumed(self) -> tuple[str, ...]:
        """Entity references no concept covers. Usually empty; not guaranteed."""
        covered = {ref for c in self.concepts() for ref in c.intent}
        return tuple(sorted(set(self._observations) - covered))

    # -- growth -------------------------------------------------------------

    def gradient(self, concept: Concept) -> Gradient:
        """The cheapest widening: entities that would add a genuinely new observation."""
        already = concept.extent
        candidates: list[tuple[int, str]] = []
        for entity_ref in self._observations:
            if entity_ref in concept.intent:
                continue
            fresh = set(self._observations[entity_ref]) - set(already)
            if fresh:
                candidates.append((len(fresh), entity_ref))
        candidates.sort(key=lambda pair: (-pair[0], pair[1]))
        chosen = tuple(ref for _, ref in candidates)
        new_observations = len(
            {obs for ref in chosen for obs in self._observations[ref]} - set(already)
        )
        blocked = tuple(
            ref
            for ref in set(self._observations) - set(concept.intent) - set(chosen)
            if not (set(self._observations[ref]) - set(already))
        )
        return Gradient(
            concept=concept,
            members=chosen,
            new_observations=new_observations,
            unplaced_observations=len(self._unplaced),
            blocked_by=tuple(sorted(blocked)),
        )

    def widen(self, concept: Concept, *, limit: int | None = None) -> tuple[Concept, ...]:
        """Concepts one gradient step above ``concept``."""
        step = self.gradient(concept)
        refs = step.members if limit is None else step.members[:limit]
        return tuple(
            ConceptOrder.join(
                concept,
                Concept(
                    intent=frozenset({ref}),
                    extent=frozenset(self._observations[ref]),
                ),
            )
            for ref in refs
        )

    def snapshot(self) -> dict:
        return {
            "entities": len(self._observations),
            "observations": len(self._extent),
            "unplaced": len(self._unplaced),
            "concepts": len(self.concepts()),
            "unsatisfied": len(self.unsatisfied()),
            "types": sorted({self.type_of(ref).value for ref in self._observations}),
        }
