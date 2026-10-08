"""HIERARCHY: transitive closure over asymmetric predicates, one derivation per edge
(spec 026 §C, FR-023).

**What this is.** Given observed edges ``A owns B`` and ``B owns C``, this returns one
*derived* edge ``A owns C``, carrying the chain that produced it. Nothing else in the
platform composes a predicate with itself, so this module is the only place that can
answer "is X below Y" when nobody ever wrote that down.

**How it differs from the closure it is modelled on.**
:meth:`domain.schema.SchemaRegistry.descendants_of` walks ``extends`` -- a hierarchy over
*type names*, where the edge set is a declaration shipped in the code, where every relation
means the same thing on both ends, and where "how far apart are these?" always answers
"one hop". The shape is deliberately the same: bounded, cycle-guarded, deterministic, and
computed by walking a declared relation instead of testing every pair. That is exactly why
the difference has to be stated:

* the relation walked here is over *predicates on data*, so each edge carries its own
  predicate and composition is legal only where a **law** says it is;
* an undeclared predicate is neither an error nor a closure. ``descendants_of`` can raise
  ``UnknownSchemaError`` because its vocabulary is closed and shipped. Here the vocabulary
  is open by requirement (FR-030), so an unknown name has no law, no law means no
  composition, and the report names the predicates it left untouched -- otherwise an empty
  result reads as "these things are unrelated", which is the unknown-for-empty confusion
  FR-004 exists to prevent;
* "how far apart are these?" now answers with a depth, and that depth is *budgeted*. A
  closure over data can be arbitrarily deep, so the finite bound is a refusal to compute,
  not an approximation of what was computed.

**Asymmetry without a closed dictionary.** The question this module exists to settle is
"which predicates may be composed, and which are asymmetric?", and a hardcoded version has
only two answers available: "the ones already in the list" -- a second closed vocabulary,
stale the day an extractor invents a predicate nobody anticipated -- or "all of them",
which fabricates ``A controls C`` from an analogy and is the precise failure the derivation
layer exists to prevent. So asymmetry is not read off a name. It is computed from data:

    a predicate is transitive when some law in its inheritance closure declares it so;
    a transitive predicate is asymmetric unless a law also declares it symmetric.

The second line is the whole asymmetry answer. Transitivity plus symmetry makes the closure
an equivalence relation: every connected component collapses into a clique, "A is above B"
and "B is above A" both hold, and the result is a partition wearing the grammar of a
hierarchy. Such a predicate is still closed over -- deleting an analyst's data is not this
module's decision -- but every edge is flagged :attr:`ClosureFlag.EQUIVALENCE` and the
predicate is listed in :attr:`ClosureReport.equivalence_predicates`, so the primitive
declines to present a mutual reference as a hierarchy (FR-022).

**What has to be declared for a predicate to become transitive.** One object, by data:

    DEFAULT_LAWS.declare(PredicateLaw("subsidiary_of", transitive=True))

Four optional fields change how the law is *applied*, and all four are inherited:

``extends``
    Which predicates' laws this one inherits. A law is declared once at the coarse level
    (``controls``) and a finer predicate picks it up (``branch_of extends controls``)
    rather than restating it. Resolution is nearest-wins per field, so a child can tighten
    one field without restating the rest. A cycle in ``extends`` is refused at the
    declaration that closes it, because a law whose own definition loops has no
    resolution; a parent declared later is picked up when it arrives, and one that never
    arrives is named by :meth:`PredicateRegistry.unresolved_parents` rather than silently
    inheriting nothing.
``composes_with``
    Which predicates a hop of this one may continue along. Defaults to ``(name,)`` -- the
    strict self-composition case. ``PredicateLaw("subsidiary_of", transitive=True,
    composes_with=("subsidiary_of", "controls"))`` derives ``A subsidiary_of C`` from
    ``A subsidiary_of B`` and ``B controls C``: the actual containment case, otherwise
    unreachable without inventing a second predicate name for the same fact.
``symmetric``
    Set only when the relation genuinely is mutual. See above.
``depth_limit``
    A tighter budget than the caller's, for domains where a long chain is itself a data
    error. The effective budget is ``min(caller, declared)`` -- a caller asking for eight
    hops has not granted every predicate eight hops.
``inverse``
    Recorded for readers, and not inherited: it names this predicate's read-back spelling,
    which is a fact about the predicate rather than about the law. The reverse edge is
    **never** synthesized for an asymmetric predicate -- the walk only ever composes
    subject-to-object -- so this field documents that spelling and drives no behaviour,
    which is stated here because a field that looks load-bearing and is not is worse than
    no field.

Undeclared is not atomic, and the two are reported separately: ``UNDECLARED`` means nobody
said, ``ATOMIC`` means a law said no. One number for both would make "we were told not to"
and "we never thought to ask" indistinguishable in the output.

**Depth is finite because the data is.** :data:`DEFAULT_DEPTH_LIMIT` is 8 hops. Real
containment hierarchies -- organisations, administrative divisions, component trees,
taxonomy paths -- are shallow, and a shallow answer is one a reader can audit by hand. An
unbounded closure over a cyclic graph does not terminate; over an acyclic one it returns
combinations, not facts. So exceeding the budget is reported and never emulated:
:attr:`ClosureReport.truncated` names the edges that could have gone deeper and each
carries :attr:`ClosureFlag.DEPTH_LIMIT`. The repository's rule applies unchanged -- no
truncated estimate is emitted as though it were the answer (``structure/graph.py``).

**Determinism is content, not order.** Every stage sorts: laws resolve through a sorted
ancestry, expansion iterates keys, nodes and candidates in sorted order, the output is
sorted by ``(depth, subject, predicate, object, path)``, and every identity is a content
digest. Two runs over one edge set in any permutation produce the same tuple, in the same
order, with the same ids -- the property FR-013 requires of replay, and the reason a
permutation test is worth writing.

**Observed and derived never share a list.** They are different types
(:class:`ObservedEdge`, :class:`DerivedEdge`), different fields of the report, and both
carry an :attr:`EdgeOrigin`. An observed edge cites no derivation, which is the invariant
:meth:`context.semantic_graph.SemanticGraph.validate` enforces there in the other
direction, so the two graphs cannot drift apart. A derived triple that a source also
reported is emitted with :attr:`ClosureFlag.CORROBORATED` and counted apart from the novel
ones: the chain is real evidence, and dropping it silently would throw away the
corroboration while emitting it as new would double-count the claim.

**Cycles are detected, marked and cut.** The walk refuses any step that re-enters a node
already on the current chain, records the chain that tried to close it in
:attr:`ClosureReport.cycles`, and flags every edge derived from a subject that is itself on
a cycle. Nothing is discarded quietly: a cycle in relation data is legitimate input --
``semantic/validation.py`` says so about mutually subsidiary companies -- so a loop is a
property of the component to be reported, not an exception to raise. A self-loop is
reported the same way, as :attr:`ClosureReport.self_loops`, and is never composed from.

**Every edge cites observations, never other derivations.** The walk composes observed
edges only, so a premise list is checkable against raw data (FR-082) and a cycle of
derivations is structurally impossible rather than merely detected. The cost is that
alternative chains past the shallowest are counted rather than enumerated:
:attr:`DerivedEdge.alternative_paths` is exact for chains of minimal length and a floor
above that, and the floor is flagged as :attr:`ClosureFlag.PATH_BUDGET` whenever it bites.
"""

from __future__ import annotations

import enum
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from domain.derivation import (
    Derivation,
    DerivationGraph,
    MethodFingerprint,
    NumericEnvironment,
    digest_of,
)

__all__ = [
    "DEFAULT_DEPTH_LIMIT",
    "DEFAULT_LAWS",
    "DEFAULT_MAX_PATHS",
    "HIERARCHY_METHOD",
    "AmbiguousPredicateLaw",
    "ClosureCycle",
    "ClosureFlag",
    "ClosureReport",
    "DerivedEdge",
    "EdgeOrigin",
    "HierarchyError",
    "ObservedEdge",
    "PredicateDeclarationCycle",
    "PredicateDeclarationError",
    "PredicateLaw",
    "PredicateLawKind",
    "PredicateRegistry",
    "hierarchy",
    "transitive_closure",
]

#: Chops walked before the closure stops. Eight hops covers every containment hierarchy
#: the platform ingests while keeping a chain short enough to read by hand; the module
#: docstring says why the bound is a refusal rather than an approximation.
DEFAULT_DEPTH_LIMIT = 8

#: Ceiling on the number of chains counted towards ``alternative_paths`` for one triple.
#: Counting distinct chains is combinatorially unbounded, so the count is capped and the
#: edge is flagged rather than quietly truncated.
DEFAULT_MAX_PATHS = 32

#: ``id@version`` in the platform's existing spelling. Bumping ``v1`` is how a reader sees
#: that every edge this module produced came from different code.
HIERARCHY_METHOD = MethodFingerprint("hierarchy.transitive_closure", "v1")


class HierarchyError(ValueError):
    """Base for this module's refusals. Always about a declaration, never about content."""


class PredicateDeclarationError(HierarchyError):
    """A predicate law is unusable as written."""


class PredicateDeclarationCycle(PredicateDeclarationError):
    """``extends`` loops, so the law has no resolution."""


class AmbiguousPredicateLaw(PredicateDeclarationError):
    """Two parents declare the same field differently at the same distance."""


class EdgeOrigin(enum.StrEnum):
    """Whether a source said this edge or this module inferred it.

    Not decoration. ``semantic_graph`` refuses to let the two share an edge type because
    they have different evidence, different reversibility and different ways to be wrong,
    and the same separation is what stops ``A owns C``, inferred from ``A owns B`` plus
    ``B owns C``, from being read as something a document stated.
    """

    OBSERVED = "observed"
    DERIVED = "derived"


class PredicateLawKind(enum.StrEnum):
    """How a predicate behaves under composition, once inheritance is resolved.

    ``UNDECLARED`` -- no law anywhere in the inheritance closure says. Composition is
        refused and the predicate is reported as undeclared: "nobody said", which is not
        the same claim as "said no".
    ``ATOMIC`` -- a law declared ``transitive=False``. Composition is refused and the
        predicate is reported as atomic.
    ``ASYMMETRIC`` -- transitive, not symmetric. The hierarchy case: the walk composes
        subject-to-object and the reverse edge is never synthesized.
    ``EQUIVALENCE`` -- transitive and symmetric. The closure is an equivalence relation, so
        it is computed and flagged, but it is not a hierarchy and is not shown as one
        (FR-022).
    """

    UNDECLARED = "undeclared"
    ATOMIC = "atomic"
    ASYMMETRIC = "asymmetric"
    EQUIVALENCE = "equivalence"


class ClosureFlag(enum.StrEnum):
    """A condition attached to one derived edge, so nothing is dropped quietly."""

    #: The triple a source also reported: the chain corroborates it rather than adding it.
    CORROBORATED = "corroborated"
    #: This edge's subject sits on a detected cycle, so the entailment rests on a
    #: non-well-founded premise. The edge stands; the component is not a hierarchy.
    CYCLE_AT_SUBJECT = "cycle_at_subject"
    #: A declared symmetric predicate closed a loop through this edge.
    EQUIVALENCE = "equivalence"
    #: This edge is as deep as the budget allows and had successors left to walk.
    DEPTH_LIMIT = "depth_limit"
    #: ``alternative_paths`` reached ``max_paths``, so the count is a floor to read as
    #: "at least this many" rather than a total. Flagged because a floored count shown as
    #: an exact one is a number no code path measured (FR-083).
    PATH_BUDGET = "path_budget"


# -- declarations -------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PredicateLaw:
    """How one predicate behaves under composition. Declared by data, resolved by a registry.

    ``transitive``, ``symmetric`` and ``composes_with`` are tri-state on purpose: ``None``
    means "this level said nothing", which is what makes inheritance per-field instead of
    all-or-nothing. A ``False`` default would be indistinguishable from a child explicitly
    refusing a law its parent declared, and every inherited law would then have to be
    restated at every level.

    ``extends`` names predicates whose law this one inherits. It is a hierarchy over laws,
    not an assertion about the data: nothing here says that ``branch_of`` edges are
    ``controls`` edges, only that the two compose under one law.
    """

    name: str
    transitive: bool | None = None
    symmetric: bool | None = None
    extends: tuple[str, ...] = ()
    composes_with: tuple[str, ...] | None = None
    depth_limit: int | None = None
    inverse: str = ""

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise PredicateDeclarationError("a predicate law must name its predicate")
        object.__setattr__(self, "name", str(self.name))
        object.__setattr__(self, "inverse", str(self.inverse))
        object.__setattr__(self, "extends", tuple(str(p) for p in self.extends if str(p)))
        if self.name in self.extends:
            # A self-extending law is the smallest possible cycle and the easiest to ship
            # by accident, so it is named here rather than discovered by the ancestry walk.
            raise PredicateDeclarationCycle(f"predicate {self.name!r} extends itself")
        if self.composes_with is not None:
            object.__setattr__(
                self, "composes_with", tuple(str(p) for p in self.composes_with if str(p))
            )
        if self.depth_limit is not None and self.depth_limit < 1:
            raise PredicateDeclarationError(
                f"predicate {self.name!r} declares depth_limit {self.depth_limit}; a limit "
                "below 1 would compose nothing while looking configured"
            )

    @property
    def composes(self) -> bool:
        """Whether this law permits composition at all, without resolving inheritance."""
        return self.transitive is True


#: Fields an inheritance chain may fill. ``name`` and ``extends`` are structural: a child
#: has its own name and its own parents, and inheriting either would erase that.
_INHERITED_FIELDS = ("transitive", "symmetric", "composes_with", "depth_limit")

#: Ceiling on one law-resolution walk. A declaration graph is data too, so the walk is
#: bounded rather than trusted to terminate.
_MAX_DECLARATION_NODES = 1024


def _deref(merged: dict[str, tuple[int, Any]], attribute: str) -> Any:
    """The value a field resolved to, or ``None`` when no declaration in the chain set it."""
    held = merged.get(attribute)
    return None if held is None else held[1]


class PredicateRegistry:
    """Declared laws, resolved through ``extends`` into one effective law per predicate.

    Deliberately not a vocabulary. It holds whatever laws a caller declares and knows
    nothing about any predicate in particular, because a registry that had heard of
    ``ownership`` and not of the predicate an extractor invented yesterday is exactly the
    closed apparatus spec 026 exists to remove (FR-030).
    """

    def __init__(self, declarations: Iterable[PredicateLaw] = ()) -> None:
        self._declared: dict[str, PredicateLaw] = {}
        for law in declarations:
            self.declare(law)

    def declare(self, law: PredicateLaw) -> PredicateLaw:
        """Record one law. Refuses a second law for one name, or an ``extends`` cycle.

        A parent that has no law *yet* is admitted rather than refused: laws arrive as a
        table, and a declaration order the author did not choose is not a data error. What
        that costs is named by :meth:`unresolved_parents` and shows up in the closure report
        as an undeclared predicate, so a typo is visible instead of silently inheriting
        nothing forever.
        """
        existing = self._declared.get(law.name)
        if existing is not None:
            # Merging two declarations silently would leave the merged law answering to a
            # name two parties wrote down differently, with no record that it was ever two
            # declarations. Refused here, where the author can see it.
            if existing == law:
                return existing
            raise PredicateDeclarationError(
                f"predicate {law.name!r} already has a different law; declare one law per name"
            )
        self._declared[law.name] = law
        try:
            # Resolving on the way in is what makes the cycle refusal land at the
            # declaration that closed it, where the author is still reading.
            self.resolve(law.name)
        except PredicateDeclarationError:
            del self._declared[law.name]
            raise
        return law

    def declared(self) -> tuple[PredicateLaw, ...]:
        """Every declaration, sorted by name -- the input, not the resolution."""
        return tuple(self._declared[name] for name in sorted(self._declared))

    def known(self, predicate: str) -> bool:
        """Whether any law declares this predicate. Unknown is admissible, not an error."""
        return predicate in self._declared

    def unresolved_parents(self, predicate: str) -> tuple[str, ...]:
        """Declared parents of ``predicate`` that have no law of their own.

        Usually empty. Non-empty means a declaration names a law nobody has written, so the
        inheritance it asked for contributes nothing -- reported here so that condition is
        named rather than showing up only as a predicate that composes nothing.
        """
        self.resolve(predicate)
        return tuple(
            sorted(p for p in self._declared[predicate].extends if p not in self._declared)
        )

    def ancestors_of(self, predicate: str) -> tuple[str, ...]:
        """Predicates whose law ``predicate`` inherits from, nearest first, excluding itself.

        The same shape as :meth:`domain.schema.SchemaRegistry.ancestors_of` -- walk the
        declared hierarchy, nearest first, cycle-guarded -- over laws instead of types. It
        is also the answer to "under which predicate should I declare this?", which is why
        it is public rather than a private walk.
        """
        self.resolve(predicate)
        found: list[str] = []
        seen = {predicate}
        frontier = list(self._declared[predicate].extends)
        while frontier:
            name = frontier.pop(0)
            if name in seen:
                continue
            found.append(name)
            seen.add(name)
            declaration = self._declared.get(name)
            if declaration is not None:
                frontier.extend(sorted(declaration.extends))
        return tuple(found)

    def descendants_of(self, law_name: str) -> tuple[str, ...]:
        """Every predicate that inherits ``law_name``'s law, nearest first.

        The law-side mirror of ``descendants_of`` over types: which fine-grained predicates
        become transitive because one coarse law was declared, which is the question a
        caller asks before deciding whether a declaration is too broad.
        """
        self.resolve(law_name)
        found: list[str] = []
        seen = {law_name}
        frontier = sorted(name for name, d in self._declared.items() if law_name in d.extends)
        while frontier:
            name = frontier.pop(0)
            if name in seen:
                continue
            found.append(name)
            seen.add(name)
            declaration = self._declared.get(name)
            if declaration is not None:
                frontier.extend(sorted(n for n, d in self._declared.items() if name in d.extends))
        return tuple(found)

    def resolve(self, predicate: str) -> PredicateLaw:
        """The effective law for ``predicate``, nearest declaration winning per field.

        Two rules, both there to keep the answer a function of the declarations alone.
        Nearest wins, so a child may tighten one field without restating its parents. Two
        parents disagreeing at equal distance is a refusal, not a tie-break: letting the
        sorted-first one win would make the law depend on how the parents happened to be
        spelled, and a closure that looks rigorous while resting on that is worse than no
        closure at all.
        """
        declaration = self._declared.get(predicate)
        if declaration is None:
            # Open world: an unheard-of predicate is UNDECLARED, not an error. It composes
            # nothing, and the report names it, which is what separates "we refused" from
            # "nothing is there".
            return PredicateLaw(predicate)

        chain: list[tuple[int, PredicateLaw]] = []
        visited: set[str] = set()
        # Each entry carries its own ancestor path, so a re-entry of an ancestor -- and only
        # an ancestor -- is recognisable as a cycle without recursion.
        stack: list[tuple[int, str, tuple[str, ...]]] = [(0, predicate, (predicate,))]
        while stack:
            distance, name, ancestry = stack.pop()
            if name in visited:
                if name in ancestry[:-1]:
                    raise PredicateDeclarationCycle(
                        f"predicate {predicate!r} has a cyclic extends chain: "
                        f"{' -> '.join((*ancestry, name))}"
                    )
                continue
            if len(visited) >= _MAX_DECLARATION_NODES:
                raise PredicateDeclarationCycle(
                    f"predicate {predicate!r} inherits more than {_MAX_DECLARATION_NODES} "
                    "laws; that is a law graph with no resolution order"
                )
            found = self._declared.get(name)
            if found is None:
                # A parent declared later, or never. Its law contributes nothing, which is
                # reported by ``unresolved_parents`` rather than refused here -- laws are
                # loaded as a table and load order is not a data error.
                continue
            visited.add(name)
            chain.append((distance, found))
            stack.extend(
                (distance + 1, parent, (*ancestry, parent)) for parent in sorted(found.extends)
            )

        merged: dict[str, tuple[int, Any]] = {}
        conflicts: list[str] = []
        for distance, found in chain:
            for attribute in _INHERITED_FIELDS:
                value = getattr(found, attribute)
                if value is None:
                    continue
                held = merged.get(attribute)
                if held is None or held[0] > distance:
                    merged[attribute] = (distance, value)
                elif held[0] == distance and held[1] != value:
                    conflicts.append(f"{attribute}@{found.name}")
        if conflicts:
            raise AmbiguousPredicateLaw(
                f"predicate {predicate!r} inherits conflicting {sorted(conflicts)}; "
                "no declaration may win by spelling order"
            )
        return replace(
            declaration,
            transitive=_deref(merged, "transitive"),
            symmetric=_deref(merged, "symmetric"),
            composes_with=_deref(merged, "composes_with"),
            depth_limit=_deref(merged, "depth_limit"),
        )

    def kind(self, predicate: str) -> PredicateLawKind:
        """Composition behaviour for ``predicate``, after inheritance is resolved.

        This is where asymmetry is decided: transitive and not symmetric is the hierarchy
        case, transitive and symmetric is an equivalence and is labelled as one, and
        anything else composes nothing.
        """
        law = self.resolve(predicate)
        if law.transitive is not True:
            return (
                PredicateLawKind.ATOMIC if law.transitive is False else PredicateLawKind.UNDECLARED
            )
        return (
            PredicateLawKind.EQUIVALENCE if law.symmetric is True else PredicateLawKind.ASYMMETRIC
        )

    def composes_with(self, predicate: str) -> tuple[str, ...]:
        """Predicates a hop of ``predicate`` may continue along. ``(name,)`` by default.

        The default is the strict case: a transitive predicate composes with itself and
        nothing else. Cross-predicate composition is declared, never inferred from a
        similarity between two names.
        """
        law = self.resolve(predicate)
        if not law.composes:
            return ()
        declared = law.composes_with or ()
        return tuple(sorted({law.name, *declared}))

    def effective_depth_limit(self, predicate: str, depth_limit: int) -> int:
        """``min(caller, declared)`` -- a law may bound a walk tighter, never looser.

        A caller asking for depth 8 has not granted every predicate eight hops. Where a law
        declares a tighter bound the tighter one wins, because the caller sets the budget
        and the law sets its own domain's tolerance for a chain that long.
        """
        declared = self.resolve(predicate).depth_limit
        return depth_limit if declared is None else min(depth_limit, declared)


#: An engine that has declared nothing derives nothing. The safe direction: a law nobody
#: wrote down is not a law this module may infer from, and the default registry holds no
#: predicate names at all, so a caller must opt in by data (FR-030).
DEFAULT_LAWS = PredicateRegistry()


# -- edges --------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ObservedEdge:
    """One triple a source reported, with the reference that reported it.

    ``source_ref`` is hashed into :attr:`edge_id`, so a corroborated triple is a *different
    premise* from an uncorroborated one and everything derived above it re-derives when a
    second source arrives. That churn is deliberate: it is visible, where an id ignoring
    the evidence would let a cache serve a claim whose premise has changed.
    """

    subject: str
    predicate: str
    object: str
    source_ref: str = ""

    def __post_init__(self) -> None:
        for name in ("subject", "predicate", "object"):
            if not str(getattr(self, name)).strip():
                raise HierarchyError(f"an observed edge needs a {name}")
        object.__setattr__(self, "subject", str(self.subject))
        object.__setattr__(self, "predicate", str(self.predicate))
        object.__setattr__(self, "object", str(self.object))
        object.__setattr__(self, "source_ref", str(self.source_ref))

    @property
    def origin(self) -> EdgeOrigin:
        """Always :attr:`EdgeOrigin.OBSERVED`.

        A property rather than a field so no caller can construct an observed edge that
        claims to be derived -- the same separation ``semantic_graph`` enforces the other
        way round, where an observed edge must cite no derivation.
        """
        return EdgeOrigin.OBSERVED

    @property
    def claim(self) -> str:
        return f"{self.subject} {self.predicate} {self.object}"

    @property
    def sources(self) -> tuple[str, ...]:
        """Every reference that reported this triple, sorted."""
        return tuple(sorted(s for s in self.source_ref.split(";") if s))

    @property
    def edge_id(self) -> str:
        """Content digest of the triple and its evidence: stable across runs and machines."""
        digest = digest_of(
            {
                "subject": self.subject,
                "predicate": self.predicate,
                "object": self.object,
                "sources": list(self.sources),
            }
        )
        return f"HE-{digest[:16]}"

    def merge(self, other: ObservedEdge) -> ObservedEdge:
        """Two reports of one triple become one edge carrying both references."""
        if (self.subject, self.predicate, self.object) != (
            other.subject,
            other.predicate,
            other.object,
        ):
            raise HierarchyError("only reports of the same triple merge")
        return replace(self, source_ref=";".join(sorted({*self.sources, *other.sources})))

    def as_dict(self) -> dict[str, Any]:
        return {
            "origin": self.origin.value,
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.object,
            "claim": self.claim,
            "sources": list(self.sources),
            "edge_id": self.edge_id,
        }


@dataclass(frozen=True, slots=True)
class DerivedEdge:
    """One edge this module inferred, with the chain that produced it and why.

    Carries both marks a reader needs: :attr:`origin` is always
    :attr:`EdgeOrigin.DERIVED` and :attr:`derivation_id` is always populated.

    ``path`` holds the intermediate nodes only -- ``("B",)`` for ``A owns B`` plus
    ``B owns C`` -- so ``(subject, *path, object)`` is the full chain and
    ``depth == len(path) + 1`` holds by construction rather than by bookkeeping.
    """

    subject: str
    predicate: str
    object: str
    path: tuple[str, ...]
    depth: int
    law: PredicateLawKind
    asymmetric: bool
    premises: tuple[str, ...]
    premise_edges: tuple[ObservedEdge, ...]
    alternative_paths: int = 1
    flags: frozenset[ClosureFlag] = field(default_factory=frozenset)
    derivation: Derivation | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", tuple(str(node) for node in self.path))
        object.__setattr__(self, "premises", tuple(str(p) for p in self.premises))
        object.__setattr__(self, "flags", frozenset(self.flags))
        if self.subject == self.object:
            raise HierarchyError(
                f"derived edge {self.claim!r} is a self-derivation; the walk refuses these"
            )
        if self.depth != len(self.path) + 1:
            raise HierarchyError(
                f"derived edge {self.claim!r}: depth {self.depth} does not match a chain of "
                f"{len(self.path) + 1} hops"
            )
        if self.derivation is None:
            raise HierarchyError(f"derived edge {self.claim!r} must carry its derivation")

    @property
    def origin(self) -> EdgeOrigin:
        """Always :attr:`EdgeOrigin.DERIVED`. See :attr:`ObservedEdge.origin`."""
        return EdgeOrigin.DERIVED

    @property
    def claim(self) -> str:
        return f"{self.subject} {self.predicate} {self.object}"

    @property
    def chain(self) -> tuple[str, ...]:
        """The whole node chain, subject and object included."""
        return (self.subject, *self.path, self.object)

    @property
    def is_derived(self) -> bool:
        return self.origin is EdgeOrigin.DERIVED

    @property
    def is_observed(self) -> bool:
        """Always ``False`` here, and named so a caller can ask the question symmetrically."""
        return self.origin is EdgeOrigin.OBSERVED

    @property
    def derivation_id(self) -> str:
        """The content digest :class:`domain.derivation.Derivation` computes.

        Covers method, premise set, numeric environment and output, and the premise set is
        itself a set of observed-edge content digests -- so the id transitively covers the
        whole chain. Two chains proving one claim from the same observations therefore share
        an identity, which is right (it is one claim with one provenance), while a chain
        differing anywhere in its premises does not.
        """
        return self.derivation.derivation_id  # type: ignore[union-attr]

    @property
    def is_novel(self) -> bool:
        """Whether this edge adds a triple no source reported."""
        return not self.has(ClosureFlag.CORROBORATED)

    def has(self, flag: ClosureFlag) -> bool:
        return flag in self.flags

    def as_dict(self) -> dict[str, Any]:
        """Everything a reader needs, per FR-081: the edge, its chain and its derivation."""
        return {
            "origin": self.origin.value,
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.object,
            "claim": self.claim,
            "path": list(self.path),
            "chain": list(self.chain),
            "depth": self.depth,
            "law": self.law.value,
            "asymmetric": self.asymmetric,
            "premises": list(self.premises),
            "alternative_paths": self.alternative_paths,
            "flags": sorted(f.value for f in self.flags),
            "derivation_id": self.derivation_id,
            "statement": self.derivation.statement,  # type: ignore[union-attr]
        }


@dataclass(frozen=True, slots=True)
class ClosureCycle:
    """A chain that tried to re-enter a node, kept so the finding shows its work.

    ``path`` is the node chain up to the step that closed and ``reopened_node`` is the node
    it tried to return to. Reported rather than raised: a cycle in relation data is
    legitimate input, and a primitive that refused to compute because the analyst's data
    loops would be unusable on the data most worth analysing.
    """

    subject: str
    predicate: str
    path: tuple[str, ...]
    reopened_node: str

    @property
    def closed_path(self) -> tuple[str, ...]:
        """The full loop, closing node repeated at both ends."""
        return (*self.path, self.reopened_node)

    def as_dict(self) -> dict[str, Any]:
        return {
            "subject": self.subject,
            "predicate": self.predicate,
            "path": list(self.path),
            "reopened_node": self.reopened_node,
            "closed_path": list(self.closed_path),
        }


@dataclass(frozen=True, slots=True)
class ClosureReport:
    """Everything one closure produced, with every refusal and cut kept visible.

    ``observed`` and ``derived`` are separate fields of separate types and are never
    concatenated anywhere in this module. A caller wanting both has to ask for both, which
    is the only way "what did the source say" and "what did we work out" stay
    distinguishable downstream (FR-004: unknown is not empty).
    """

    observed: tuple[ObservedEdge, ...]
    derived: tuple[DerivedEdge, ...]
    undeclared_predicates: tuple[str, ...]
    atomic_predicates: tuple[str, ...]
    equivalence_predicates: tuple[str, ...]
    cycles: tuple[ClosureCycle, ...]
    self_loops: tuple[str, ...]
    truncated: tuple[str, ...]
    depth_limit: int
    derivations: DerivationGraph = field(default_factory=DerivationGraph, repr=False)

    @property
    def cycle_closed(self) -> bool:
        """Whether the closure was cut by a cycle rather than running out of chains."""
        return bool(self.cycles) or bool(self.self_loops)

    @property
    def is_total(self) -> bool:
        """Whether the closure is complete: no cycle, no self-loop, no depth cut.

        A report that is not total has a known hole in it, and the hole is named in
        ``cycles``, ``self_loops`` and ``truncated`` instead of being left for a reader to
        assume away.
        """
        return not (self.cycle_closed or self.truncated)

    @property
    def novel(self) -> tuple[DerivedEdge, ...]:
        """Derived edges whose triple no source reported."""
        return tuple(e for e in self.derived if e.is_novel)

    @property
    def corroborated(self) -> tuple[DerivedEdge, ...]:
        """Derived edges whose triple a source did report: new support, not a new claim."""
        return tuple(e for e in self.derived if not e.is_novel)

    @property
    def nodes(self) -> tuple[str, ...]:
        """Every node mentioned anywhere, observed or derived, sorted."""
        seen = {e.subject for e in self.observed} | {e.object for e in self.observed}
        for edge in self.derived:
            seen.update(edge.chain)
        return tuple(sorted(seen))

    def derived_from(self, subject: str) -> tuple[DerivedEdge, ...]:
        """Edges inferred below one node."""
        return tuple(e for e in self.derived if e.subject == subject)

    def ancestors(self, node: str, *, predicate: str | None = None) -> tuple[str, ...]:
        """Every node that reaches ``node``, nearest first.

        Walked over the whole relation -- observed edges as the base, derived edges on top
        -- because the question is about the hierarchy itself and the direct parent of a
        node is normally an observation rather than an entailment. A node nothing reaches
        is simply absent from the answer, which is the correct answer for "what is above
        this" and not a claim that nothing is.
        """
        above: dict[str, list[str]] = {}
        for edge in self.derived:
            if predicate is None or edge.predicate == predicate:
                above.setdefault(edge.object, []).append(edge.subject)
        for edge in self.observed:
            if predicate is None or edge.predicate == predicate:
                above.setdefault(edge.object, []).append(edge.subject)
        found: list[str] = []
        seen = {node}
        frontier = [node]
        while frontier:
            for parent in sorted(above.get(frontier.pop(0), ())):
                if parent not in seen:
                    seen.add(parent)
                    found.append(parent)
                    frontier.append(parent)
        return tuple(found)

    def as_dict(self) -> dict[str, Any]:
        return {
            "observed": [e.as_dict() for e in self.observed],
            "derived": [e.as_dict() for e in self.derived],
            "undeclared_predicates": list(self.undeclared_predicates),
            "atomic_predicates": list(self.atomic_predicates),
            "equivalence_predicates": list(self.equivalence_predicates),
            "cycles": [c.as_dict() for c in self.cycles],
            "self_loops": list(self.self_loops),
            "truncated": list(self.truncated),
            "depth_limit": self.depth_limit,
            "cycle_closed": self.cycle_closed,
            "is_total": self.is_total,
            "derivations": len(self.derivations),
        }

    def snapshot(self) -> dict[str, Any]:
        """Counts only -- what a status line shows, never a verdict about the data."""
        return {
            "observed": len(self.observed),
            "derived": len(self.derived),
            "novel": len(self.novel),
            "corroborated": len(self.corroborated),
            "max_depth": max((e.depth for e in self.derived), default=0),
            "cycles": len(self.cycles),
            "self_loops": len(self.self_loops),
            "truncated": len(self.truncated),
            "depth_limit": self.depth_limit,
            "is_total": self.is_total,
        }


# -- the closure --------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Reached:
    """One node reached below one ``(subject, predicate)`` key, at its shallowest depth.

    ``hops`` pairs each node with the observed edge it was reached through, so the chain is
    reconstructable without re-deriving which predicate each hop used -- a hop may continue
    along a different predicate, and ``composes_with`` is exactly what makes that possible.

    ``alternatives`` counts the distinct minimal chains that reach this node. It is summed
    from the parents rather than enumerated forward, which is exact for chains of minimal
    length: each parent contributes its own count, and two chains differing anywhere in
    their prefix have different prefixes.
    """

    hops: tuple[tuple[str, ObservedEdge], ...]
    alternatives: int

    @property
    def path(self) -> tuple[str, ...]:
        """Every node the chain passed through, the object included."""
        return tuple(node for node, _ in self.hops)

    @property
    def intermediates(self) -> tuple[str, ...]:
        """The chain without its endpoints -- what :class:`DerivedEdge` reports as ``path``."""
        return self.path[:-1]


def _as_observed(item: ObservedEdge | Sequence[str] | Mapping[str, Any]) -> ObservedEdge:
    """Normalize one input into an :class:`ObservedEdge`.

    Accepts the dataclass, a ``(subject, predicate, object)`` or
    ``(subject, predicate, object, source_ref)`` sequence, and a mapping with those keys,
    because the three shapes a caller actually holds are those three and a keyword-only
    constructor call at every call site would be noise. A blank part is refused: an edge
    with no predicate cannot compose with anything, and admitting it would make it look
    like a predicate nobody declared.
    """
    if isinstance(item, ObservedEdge):
        return item
    if isinstance(item, Mapping):
        return ObservedEdge(
            subject=str(item.get("subject", "")),
            predicate=str(item.get("predicate", "")),
            object=str(item.get("object", item.get("obj", ""))),
            source_ref=str(item.get("source_ref", item.get("source", ""))),
        )
    parts = tuple(str(part) for part in item)
    if len(parts) not in (3, 4):
        raise HierarchyError(
            f"an edge needs (subject, predicate, object[, source_ref]); got {len(parts)} parts"
        )
    return ObservedEdge(*parts)


def _normalize(
    items: Iterable[ObservedEdge | Sequence[str] | Mapping[str, Any]],
) -> tuple[tuple[ObservedEdge, ...], dict[tuple[str, str, str], ObservedEdge]]:
    """De-duplicate by triple, merging evidence, then sort.

    Two reports of one triple are one edge with two sources. Collapsing them is not counting
    them twice; keeping them apart would make one derived edge be emitted twice for no
    informational gain, and the merge keeps both references.
    """
    merged: dict[tuple[str, str, str], ObservedEdge] = {}
    for raw in items:
        edge = _as_observed(raw)
        key = (edge.subject, edge.predicate, edge.object)
        existing = merged.get(key)
        merged[key] = existing.merge(edge) if existing is not None else edge
    return tuple(merged[key] for key in sorted(merged)), merged


def _adjacency(
    by_triple: Mapping[tuple[str, str, str], ObservedEdge],
) -> dict[tuple[str, str], tuple[tuple[str, ObservedEdge], ...]]:
    """``(node, predicate) -> ((object, edge), ...)``, sorted.

    Built once and indexed rather than filtered per step: a closure visits each node once
    per depth, and re-scanning every edge at each visit is the difference between a linear
    walk and a quadratic one on the graphs this primitive is pointed at.
    """
    buckets: dict[tuple[str, str], list[tuple[str, ObservedEdge]]] = {}
    for key in sorted(by_triple):
        edge = by_triple[key]
        buckets.setdefault((edge.subject, edge.predicate), []).append((edge.object, edge))
    return {key: tuple(sorted(values)) for key, values in buckets.items()}


def _expand(
    frontier: dict[tuple[str, str], dict[str, _Reached]],
    *,
    adjacency: Mapping[tuple[str, str], tuple[tuple[str, ObservedEdge], ...]],
    laws: PredicateRegistry,
    depth_limit: int,
    max_paths: int,
    depth: int,
) -> tuple[dict[tuple[str, str], dict[str, _Reached]], list[ClosureCycle], set[str], set[str]]:
    """One level of composition: every hop out of the frontier, in sorted order.

    Yields a fresh level rather than mutating the frontier, so a cycle found at this level
    cannot remove the very node whose edge exposed it. Also returns the claims that hit the
    depth budget and the subjects found on a cycle, because both are refusals that have to
    leave a mark somewhere visible.
    """
    next_level: dict[tuple[str, str], dict[str, _Reached]] = {}
    cycles: list[ClosureCycle] = []
    cyclic_subjects: set[str] = set()
    truncated: set[str] = set()

    for key in sorted(frontier):
        subject, predicate = key
        limit = laws.effective_depth_limit(predicate, depth_limit)
        for node in sorted(frontier[key]):
            reached = frontier[key][node]
            walked = (subject, *reached.path)
            for hop_predicate in laws.composes_with(predicate):
                for obj, edge in adjacency.get((node, hop_predicate), ()):
                    if obj in walked:
                        # Re-entering a node makes every further hop of this chain
                        # unfalsifiable by construction, so the walk stops here and says so
                        # rather than returning a clique.
                        cycles.append(ClosureCycle(subject, predicate, walked, obj))
                        cyclic_subjects.add(subject)
                        continue
                    if depth + 1 > limit:
                        # The budget, not the graph, is what stopped this hop. Recorded on
                        # the parent claim, which is the edge a reader would ask about.
                        truncated.add(f"{subject} {predicate} {node}")
                        continue
                    hops = (*reached.hops, (obj, edge))
                    bucket = next_level.setdefault((subject, predicate), {})
                    current = bucket.get(obj)
                    if current is None:
                        bucket[obj] = _Reached(
                            hops=hops, alternatives=min(max_paths, reached.alternatives)
                        )
                    elif len(current.hops) == len(hops):
                        # Same shallowest depth by a different route: distinct chains, one
                        # claim. Counted rather than emitted twice.
                        bucket[obj] = replace(
                            current,
                            alternatives=min(
                                max_paths, current.alternatives + reached.alternatives
                            ),
                        )
    return next_level, cycles, cyclic_subjects, truncated


def hierarchy(
    edges: Iterable[ObservedEdge | Sequence[str] | Mapping[str, Any]],
    *,
    depth_limit: int = DEFAULT_DEPTH_LIMIT,
    registry: PredicateRegistry | None = None,
    method: MethodFingerprint = HIERARCHY_METHOD,
    max_paths: int = DEFAULT_MAX_PATHS,
) -> ClosureReport:
    """The full closure: derived edges plus every refusal and cut, in one report.

    :func:`transitive_closure` is the derived edges alone; this is what they were derived
    from. Both run the same walk, so there is no second implementation that could disagree.
    """
    if depth_limit < 1:
        raise HierarchyError(
            f"depth_limit {depth_limit} would compose nothing; ask for at least 1 or take "
            "the empty closure deliberately"
        )
    if max_paths < 1:
        raise HierarchyError(f"max_paths {max_paths} must be positive")

    laws = registry if registry is not None else DEFAULT_LAWS
    observed, by_triple = _normalize(edges)
    adjacency = _adjacency(by_triple)

    kinds: dict[str, PredicateLawKind] = {}
    undeclared: set[str] = set()
    atomic: set[str] = set()
    equivalence: set[str] = set()
    self_loops: set[str] = set()
    for edge in observed:
        kind = laws.kind(edge.predicate)
        kinds[edge.predicate] = kind
        if kind is PredicateLawKind.UNDECLARED:
            undeclared.add(edge.predicate)
        elif kind is PredicateLawKind.ATOMIC:
            atomic.add(edge.predicate)
        elif kind is PredicateLawKind.EQUIVALENCE:
            equivalence.add(edge.predicate)
        if edge.subject == edge.object:
            # A self-loop is not deleted -- it was observed -- but it is never composed
            # from, and it is reported, because "A is inside A" is a data finding and not a
            # reason to return nothing.
            self_loops.add(edge.claim)

    frontier: dict[tuple[str, str], dict[str, _Reached]] = {}
    for edge in observed:
        if kinds[edge.predicate] is PredicateLawKind.ATOMIC:
            continue
        if kinds[edge.predicate] is PredicateLawKind.UNDECLARED:
            continue
        if edge.subject == edge.object:
            continue
        frontier.setdefault((edge.subject, edge.predicate), {})[edge.object] = _Reached(
            hops=((edge.object, edge),), alternatives=1
        )

    cycles: list[ClosureCycle] = []
    cyclic_subjects: set[str] = set()
    truncated: set[str] = set()
    reached: list[tuple[tuple[str, str], str, _Reached]] = []
    depth = 1
    while frontier:
        next_level, level_cycles, level_cyclic, level_truncated = _expand(
            frontier,
            adjacency=adjacency,
            laws=laws,
            depth_limit=depth_limit,
            max_paths=max_paths,
            depth=depth,
        )
        cycles.extend(level_cycles)
        cyclic_subjects |= level_cyclic
        truncated |= level_truncated
        if not next_level:
            break
        for key in sorted(next_level):
            for node in sorted(next_level[key]):
                reached.append((key, node, next_level[key][node]))
        frontier = next_level
        depth += 1

    derived = _derive(
        reached,
        by_triple=by_triple,
        laws=laws,
        method=method,
        depth_limit=depth_limit,
        max_paths=max_paths,
        cyclic_subjects=cyclic_subjects,
        truncated=truncated,
    )
    derivations = DerivationGraph()
    for edge in derived:
        derivations.add(edge.derivation)  # type: ignore[arg-type]

    return ClosureReport(
        observed=observed,
        derived=derived,
        undeclared_predicates=tuple(sorted(undeclared)),
        atomic_predicates=tuple(sorted(atomic)),
        equivalence_predicates=tuple(sorted(equivalence)),
        cycles=tuple(cycles),
        self_loops=tuple(sorted(self_loops)),
        truncated=tuple(sorted(truncated)),
        depth_limit=depth_limit,
        derivations=derivations,
    )


def _derive(
    reached: list[tuple[tuple[str, str], str, _Reached]],
    *,
    by_triple: Mapping[tuple[str, str, str], ObservedEdge],
    laws: PredicateRegistry,
    method: MethodFingerprint,
    depth_limit: int,
    max_paths: int,
    cyclic_subjects: set[str],
    truncated: set[str],
) -> tuple[DerivedEdge, ...]:
    """One :class:`DerivedEdge` per reached triple, each with its derivation, sorted.

    The sort key is the ordering contract: shallowest first, because the most direct
    entailment is the most useful one to read, then subject, predicate, object and path.
    Nothing in here depends on the order the edges arrived in.
    """
    records: list[tuple[tuple[Any, ...], DerivedEdge]] = []
    for (subject, predicate), obj, reached_state in reached:
        premise_edges = tuple(edge for _, edge in reached_state.hops)
        premises = tuple(sorted(edge.edge_id for edge in premise_edges))
        # ``path`` holds the intermediates only; the object is the last hop, not an
        # intermediate, and counting it would make every chain one node too long.
        path = reached_state.intermediates
        depth = len(reached_state.hops)
        kind = laws.kind(predicate)
        flags: set[ClosureFlag] = set()
        if (subject, predicate, obj) in by_triple:
            flags.add(ClosureFlag.CORROBORATED)
        if subject in cyclic_subjects:
            flags.add(ClosureFlag.CYCLE_AT_SUBJECT)
        if kind is PredicateLawKind.EQUIVALENCE:
            flags.add(ClosureFlag.EQUIVALENCE)
        if f"{subject} {predicate} {obj}" in truncated:
            flags.add(ClosureFlag.DEPTH_LIMIT)
        if reached_state.alternatives >= max_paths:
            flags.add(ClosureFlag.PATH_BUDGET)

        chain = " -> ".join((subject, *path, obj))
        derivation = Derivation(
            method=method,
            inputs=premises,
            output=f"{subject}|{predicate}->{obj}",
            statement=(
                f"{subject} {predicate} {obj} follows from {chain} by the declared "
                f"transitivity of {predicate!r} "
                f"({depth} hop(s), {reached_state.alternatives} distinct chain(s))"
            ),
            # The budget is part of the environment because it is part of the method: a
            # chain proven inside three hops is not the same derivation as the same chain
            # proven inside eight, which is the argument ``derivation.py`` makes for
            # carrying a ``char_limit`` at all.
            environment=NumericEnvironment(
                values={
                    "depth_limit": laws.effective_depth_limit(predicate, depth_limit),
                    "max_paths": max_paths,
                }
            ),
        )
        edge = DerivedEdge(
            subject=subject,
            predicate=predicate,
            object=obj,
            path=path,
            depth=depth,
            law=kind,
            asymmetric=kind is PredicateLawKind.ASYMMETRIC,
            premises=premises,
            premise_edges=premise_edges,
            alternative_paths=reached_state.alternatives,
            flags=frozenset(flags),
            derivation=derivation,
        )
        records.append(((depth, subject, predicate, obj, path), edge))
    return tuple(edge for _, edge in sorted(records, key=lambda pair: pair[0]))


def transitive_closure(
    edges: Iterable[ObservedEdge | Sequence[str] | Mapping[str, Any]],
    *,
    depth_limit: int = DEFAULT_DEPTH_LIMIT,
    registry: PredicateRegistry | None = None,
    method: MethodFingerprint = HIERARCHY_METHOD,
    max_paths: int = DEFAULT_MAX_PATHS,
) -> tuple[DerivedEdge, ...]:
    """Every edge reachable by composing a declared-transitive predicate with itself.

    A pure function of ``edges``: the same edges in any order give the same tuple, in the
    same order, with the same derivation ids. The refusals -- undeclared predicates, cycles,
    the depth cut -- are not in the return value because a tuple cannot carry them, so a
    caller that needs to know whether the closure was *complete* must ask :func:`hierarchy`,
    which reports the same walk.
    """
    return hierarchy(
        edges,
        depth_limit=depth_limit,
        registry=registry,
        method=method,
        max_paths=max_paths,
    ).derived
