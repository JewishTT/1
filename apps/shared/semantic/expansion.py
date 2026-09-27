"""SKOS ``broaderTransitive`` / ``narrowerTransitive`` as an explicit per-operation opt-in.

Feature 017, FR-008 / T016, SC-6.

The single idea this module enforces is that **widening a query is a decision, not a fact**.
``PublicCompany`` is a kind of ``Company`` is a kind of ``Organization``; that hierarchy is a
statement about the vocabulary. Whether searching for one of those should *reach* the others
is a statement about this query, and the two come apart constantly: widening recall is right
for "find companies mentioned in this document" and wrong for "find this one exact corporate
form, and do not hand me its parent". So nothing here is remembered, nothing here is stored on
a concept, and every call returns the decision it was handed together with the outcome
(``enabled``, ``direction``, ``depth``, ``truncated``) so a caller can record *why* a search
returned what it returned.

:meth:`expand` is therefore the whole public entry point, and ``enabled=False`` is a
first-class, honoured answer rather than a missing feature: with expansion off the result is
exactly the input, and the recorded ``direction`` is still there to show what was declined.
The transitive walks themselves - :func:`broader_transitive` and :func:`narrower_transitive` -
are exposed for callers that want the closure alone, and every one of them is cycle-safe: a
controlled vocabulary is a set of statements, not a proof of well-formedness, so a cycle is
legitimate input that must produce a finite answer with ``truncated=True`` rather than a hang.

Nothing here asserts concept equality. Reaching ``Organization`` from ``PublicCompany`` is a
report about which terms a query should consider, and the concepts remain distinct the whole
way up (FR-008, SC-6). Every output is canonically ordered, so the same input always yields
the same output (constitution VI).
"""

from __future__ import annotations

import heapq
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import StrEnum

from semantic.contracts import content_key
from semantic.vocabularies import ConceptScheme

__all__ = [
    "DEFAULT_MAX_DEPTH",
    "MAX_DEPTH_CEILING",
    "Closure",
    "ExpansionDirection",
    "ExpansionResult",
    "broader_transitive",
    "expand",
    "narrower_transitive",
]

#: Depth allowed by default. Deep enough for any realistic taxonomy, shallow enough that a
#: misconfigured scheme cannot turn one query into an unbounded walk.
DEFAULT_MAX_DEPTH = 8

#: Hard ceiling on the depth a caller may request, so "bounded resources" is a fact rather
#: than a convention (constitution VIII).
MAX_DEPTH_CEILING = 32


class ExpansionDirection(StrEnum):
    """Which way to walk the hierarchy, and which SKOS closure it names."""

    BROADER = "broader"
    NARROWER = "narrower"

    @property
    def closure(self) -> str:
        """The SKOS closure this direction stands for, recorded on every result."""
        return "skos:broaderTransitive" if self is ExpansionDirection.BROADER else (
            "skos:narrowerTransitive"
        )


def _checked_depth(max_depth: int) -> int:
    """Validate a requested depth.

    This is operation configuration rather than world content, so an impossible value is a
    caller bug and is rejected rather than clamped. Clamping would make the recorded
    ``depth`` disagree with the ``depth_limit`` the caller asked for, which is exactly the
    kind of quiet divergence a content-addressed result is supposed to rule out.
    """
    depth = int(max_depth)
    if depth < 0 or depth > MAX_DEPTH_CEILING:
        raise ValueError(
            f"max_depth must be within 0..{MAX_DEPTH_CEILING}, got {depth}"
        )
    return depth


def _has_cycle(nodes: tuple[str, ...], edges: set[tuple[str, str]]) -> bool:
    """Kahn elimination over the traversed subgraph: does the hierarchy contain a cycle?

    Uses a min-heap rather than a sorted queue so the elimination order is a deterministic
    function of the node set, which keeps ``truncated`` reproducible. A directed graph is
    acyclic exactly when every node can be eliminated, so a residue means a cycle - and a
    cycle in a hierarchy is a fact about the vocabulary that the caller deserves to be told
    about rather than have silently normalised away.
    """
    indegree: dict[str, int] = {node: 0 for node in nodes}
    successors: dict[str, set[str]] = {node: set() for node in nodes}
    for source, target in sorted(edges):
        successors[source].add(target)
        indegree[target] += 1
    ready = [node for node, degree in indegree.items() if degree == 0]
    heapq.heapify(ready)
    eliminated = 0
    while ready:
        node = heapq.heappop(ready)
        eliminated += 1
        for successor in sorted(successors[node]):
            indegree[successor] -= 1
            if indegree[successor] == 0:
                heapq.heappush(ready, successor)
    return eliminated != len(nodes)


@dataclass(frozen=True)
class Closure:
    """One transitive walk from one concept: what it reached, how far, and whether it stopped short.

    ``concept_ids`` is canonically ordered and always includes the origin when the scheme
    knows it, so a caller never has to add the term it already had. ``depth`` is the number of
    hops actually taken - ``0`` means "no hop was needed", which is a success, not a failure.
    ``truncated`` is the honest-negative flag: it is set when the depth guard fired or when the
    traversed region contains a cycle, and it means *the closure may be incomplete* rather
    than *the walk failed*. Both guarantees hold at once, because the walk is cycle-safe
    regardless: a cycle produces a finite, complete-for-the-levels-traversed answer plus this
    flag, never a hang.
    """

    direction: ExpansionDirection
    origin: str
    concept_ids: tuple[str, ...] = ()
    depth: int = 0
    truncated: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "direction", ExpansionDirection(self.direction))
        object.__setattr__(self, "origin", str(self.origin))
        object.__setattr__(self, "concept_ids", tuple(self.concept_ids))

    def __len__(self) -> int:
        return len(self.concept_ids)

    def __contains__(self, concept_id: object) -> bool:
        return str(concept_id) in self.concept_ids

    @property
    def closure(self) -> str:
        return self.direction.closure

    def widening(self) -> tuple[str, ...]:
        """Reached concepts excluding the origin - the terms this walk actually added."""
        return tuple(cid for cid in self.concept_ids if cid != self.origin)

    def content_key(self) -> str:
        """Identity of this outcome, via the shared canonical-JSON convention (digest128)."""
        return content_key(
            {
                "direction": str(self.direction),
                "origin": self.origin,
                "concepts": list(self.concept_ids),
                "depth": self.depth,
                "truncated": self.truncated,
            }
        )


def broader_transitive(
    concept_id: str,
    scheme: ConceptScheme | None = None,
    *,
    max_depth: int = DEFAULT_MAX_DEPTH,
) -> Closure:
    """``skos:broaderTransitive`` from one concept - every concept above it, to a limit.

    Multi-hop by definition, unlike :meth:`ConceptScheme.parents`, because walking to a fixed
    point is the entire purpose of the closure. A concept the scheme does not know yields an
    empty closure: an unknown concept has no *known* outgoing links, and guessing them is
    exactly what this platform does not do (FR-001).

    Cycle-safe and bounded. A concept reached by traversal is reported even if the scheme does
    not itself define it, because a declared link is a declaration about its target too.
    """
    return _transitive(concept_id, scheme, ExpansionDirection.BROADER, max_depth)


def narrower_transitive(
    concept_id: str,
    scheme: ConceptScheme | None = None,
    *,
    max_depth: int = DEFAULT_MAX_DEPTH,
) -> Closure:
    """``skos:narrowerTransitive`` from one concept - every concept below it, to a limit.

    The mirror of :func:`broader_transitive`, and used for the opposite question: narrowing a
    query to the most specific terms a source actually used, rather than widening it to their
    parents. ``Company`` narrows to the specific corporate forms beneath it; an analyst who
    wants only exact forms gets them here, and nobody has to widen anything to get them.
    """
    return _transitive(concept_id, scheme, ExpansionDirection.NARROWER, max_depth)


def _step(
    scheme: ConceptScheme, direction: ExpansionDirection
) -> Callable[[str], tuple[str, ...]]:
    """The bound single-hop walk for one direction, borrowed from the scheme's own indexes."""
    return scheme.parents if direction is ExpansionDirection.BROADER else scheme.children


def _transitive(
    concept_id: str,
    scheme: ConceptScheme | None,
    direction: ExpansionDirection,
    max_depth: int,
) -> Closure:
    """Breadth-first closure with a depth guard, a visited set and exact cycle detection."""
    origin = str(concept_id).strip()
    limit = _checked_depth(max_depth)
    if scheme is None or not scheme.has(origin):
        return Closure(
            direction=direction, origin=origin, concept_ids=(), depth=0, truncated=False
        )

    step = _step(scheme, direction)
    visited: set[str] = {origin}
    frontier: tuple[str, ...] = (origin,)
    edges: set[tuple[str, str]] = set()
    depth = 0
    while frontier and depth < limit:
        nxt: set[str] = set()
        for node in frontier:
            for neighbour in step(str(node)):
                edges.add((str(node), str(neighbour)))
                nxt.add(str(neighbour))
        fresh = sorted(nxt - visited)
        if not fresh:
            frontier = ()
            break
        visited.update(fresh)
        depth += 1
        frontier = tuple(fresh)
    truncated = bool(frontier) or _has_cycle(tuple(sorted(visited)), edges)

    return Closure(
        direction=direction,
        origin=origin,
        concept_ids=tuple(sorted(visited)),
        depth=depth,
        truncated=truncated,
    )


@dataclass(frozen=True)
class ExpansionResult:
    """A recorded expansion decision together with everything it produced.

    This is the spec's ``SemanticExpansionRequest`` made concrete: it holds the request
    (``requested_terms``, ``direction``, ``enabled``, ``depth_limit``) *and* the outcome
    (``terms``, ``concept_ids``, ``depth``, ``truncated``) in one immutable, content-addressed
    value, so the two cannot drift apart and an auditor can answer "why did this query return
    ``Organization``?" from the record alone.

    The term set, when expansion ran, is the union of the caller's terms, the concept ids
    reached, and (unless ``include_labels`` was turned off) the labels of every concept
    reached - canonically sorted, because a set of search terms is useless if the same input
    can produce two different orderings (constitution VI). ``requested_terms`` keeps the
    caller's own terms, order and duplicates intact, so when ``enabled`` is false ``terms`` is
    *exactly* the input and nothing else.

    ``unresolved_terms`` are the request's terms no concept claimed. They stay in the request
    and simply reach nothing: an unresolvable term is normal content, never a refusal
    (FR-001).
    """

    requested_terms: tuple[str, ...] = ()
    direction: ExpansionDirection = ExpansionDirection.BROADER
    enabled: bool = False
    terms: tuple[str, ...] = ()
    concept_ids: tuple[str, ...] = ()
    resolved_concepts: tuple[str, ...] = ()
    unresolved_terms: tuple[str, ...] = ()
    depth: int = 0
    depth_limit: int = DEFAULT_MAX_DEPTH
    truncated: bool = False
    scheme_id: str = ""
    include_labels: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "requested_terms", tuple(self.requested_terms))
        object.__setattr__(self, "direction", ExpansionDirection(self.direction))
        object.__setattr__(self, "terms", tuple(self.terms))
        object.__setattr__(self, "concept_ids", tuple(self.concept_ids))
        object.__setattr__(self, "resolved_concepts", tuple(self.resolved_concepts))
        object.__setattr__(self, "unresolved_terms", tuple(self.unresolved_terms))

    @property
    def closure(self) -> str:
        """The SKOS closure actually applied: the requested one, or empty when declined."""
        return self.direction.closure if self.enabled else ""

    @property
    def widened(self) -> bool:
        """True only when the walk actually reached concepts beyond the resolved ones.

        Distinct from ``enabled``: a caller can ask for expansion, get it, and learn that
        their terms named leaf concepts, in which case the recall did not actually grow.
        """
        return self.enabled and len(self.concept_ids) > len(self.resolved_concepts)

    @property
    def added(self) -> tuple[str, ...]:
        """Terms present in the result but absent from the request, canonically ordered.

        This is the only field a caller needs in order to answer "did expansion actually do
        anything?", and it is exactly ``()`` when expansion was declined.
        """
        requested = set(self.requested_terms)
        return tuple(term for term in self.terms if term not in requested)

    def __contains__(self, term: object) -> bool:
        return str(term) in self.terms

    def content_key(self) -> str:
        """Identity of decision plus outcome, via the shared canonical-JSON convention.

        Two identical requests against an unchanged scheme produce one digest, which is what
        makes a search reproducible from its record (constitution VII).
        """
        return content_key(
            {
                "requested": list(self.requested_terms),
                "direction": str(self.direction),
                "enabled": self.enabled,
                "terms": list(self.terms),
                "concepts": list(self.concept_ids),
                "resolved": list(self.resolved_concepts),
                "unresolved": list(self.unresolved_terms),
                "depth": self.depth,
                "depth_limit": self.depth_limit,
                "truncated": self.truncated,
                "scheme": self.scheme_id,
                "labels": self.include_labels,
            }
        )


def _preserve_order(terms: Iterable[str]) -> tuple[str, ...]:
    """The caller's terms, de-duplicated but in the order they were given.

    Order is preserved so that "expansion off returns exactly the input" is literally true
    and not approximately true. Canonical ordering is applied to the *expanded* result
    instead, where it is what guarantees reproducibility.
    """
    seen: set[str] = set()
    ordered: list[str] = []
    for term in terms:
        text = str(term)
        if text not in seen:
            seen.add(text)
            ordered.append(text)
    return tuple(ordered)


def expand(
    terms: Iterable[str],
    direction: ExpansionDirection = ExpansionDirection.BROADER,
    scheme: ConceptScheme | None = None,
    *,
    enabled: bool = True,
    max_depth: int = DEFAULT_MAX_DEPTH,
    include_labels: bool = True,
) -> ExpansionResult:
    """Widen a term set along one hierarchy direction, if and only if the caller asked for it.

    ``enabled=False`` is the whole point of this function's signature: expansion is a
    per-operation opt-in, so declining it must be as cheap, as explicit and as recordable as
    requesting it. With expansion off the result's ``terms`` is exactly ``requested_terms`` -
    the input, unmodified, unexpanded and unresampled.

    With expansion on, each requested term is resolved against the scheme (a term may resolve
    to several concepts, and *all* of them are expanded - ambiguity is information), the
    transitive closure of every resolved concept is taken in ``direction``, and the union of
    the caller's terms, the concepts reached and their labels becomes the result set.

    Asking for expansion with no ``scheme`` is recorded as an unevaluable request rather than
    quietly ignored: ``enabled`` stays true, ``concept_ids`` is empty and ``truncated`` is set,
    because the requested result genuinely was not produced. That is the graded "I could not
    evaluate this" answer (FR-011) rather than a success that looks like a no-op.

    The result is deterministic: ``terms`` is canonically sorted, closures are canonically
    ordered, and identical input against an unchanged scheme yields an identical
    ``content_key`` (constitution VI, VII).
    """
    requested = _preserve_order(terms)
    limit = _checked_depth(max_depth)
    direction = ExpansionDirection(direction)

    if not enabled:
        return ExpansionResult(
            requested_terms=requested,
            direction=direction,
            enabled=False,
            terms=requested,
            unresolved_terms=requested,
            depth=0,
            depth_limit=limit,
            truncated=False,
            include_labels=include_labels,
        )

    if scheme is None:
        return ExpansionResult(
            requested_terms=requested,
            direction=direction,
            enabled=True,
            terms=tuple(sorted(requested)),
            unresolved_terms=requested,
            depth=0,
            depth_limit=limit,
            truncated=True,
            include_labels=include_labels,
        )

    matched: set[str] = set()
    unresolved: list[str] = []
    for term in requested:
        concepts = scheme.resolve_surface_form(term)
        if concepts:
            matched.update(concept.concept_id for concept in concepts)
        else:
            unresolved.append(term)

    reached = set(matched)
    depth = 0
    truncated = False
    for concept_id in sorted(matched):
        closure = _transitive(concept_id, scheme, direction, limit)
        reached.update(closure.concept_ids)
        depth = max(depth, closure.depth)
        truncated = truncated or closure.truncated

    widened_terms = set(requested) | reached
    if include_labels:
        for concept_id in sorted(reached):
            concept = scheme.get(concept_id)
            if concept is not None:
                widened_terms.update(concept.labels)

    return ExpansionResult(
        requested_terms=requested,
        direction=direction,
        enabled=True,
        terms=tuple(sorted(widened_terms)),
        concept_ids=tuple(sorted(reached)),
        resolved_concepts=tuple(sorted(matched)),
        unresolved_terms=tuple(unresolved),
        depth=depth,
        depth_limit=limit,
        truncated=truncated,
        scheme_id=scheme.scheme_id,
        include_labels=include_labels,
    )
