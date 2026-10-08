"""CIRCULARITY: elementary cycles over a predicate graph, and the classification
FR-022 requires (spec 026 §C FR-022, tasks 026-F3-01/02).

FR-022 is the whole reason this module is not "detect cycles":

    CIRCULARITY MUST classify a cycle as load-bearing or inert.
    A 2-cycle between mutual references is not the same finding as circular ownership.

Two findings share a shape and mean opposite things, so returning the shape alone would
be an answer nobody can act on. Everything below exists to make the second sentence
real.

**Algorithm: Johnson's elementary circuits, in the variant that anchors every cycle at
its own minimum node.** Johnson (1975) enumerates all elementary (simple) cycles of a
directed graph in ``O((V+E)(C+1))``, where ``C`` is the number of cycles actually
present. Both rejected alternatives fail for reasons specific to this problem:

* *Subset enumeration* -- every node subset, test whether it forms a cycle -- is
  ``O(2^n)`` before it finds anything, and it can only run with a maximum cycle length.
  That cap is an invisible parameter of the finding: a cycle the analyst needed would be
  absent because of a default nobody declared.
* *Plain DFS with back-edge* enumerates cycles of **one** DFS tree. Its output is a
  subset of the elementary cycles and its content depends on the visiting order, so it
  cannot answer the question classification actually asks: "is this 2-cycle a chord of a
  longer loop, and is this loop the only route?" Both questions are about loops the naive
  walk may never mention.

  Johnson's blocked-set search is what supplies the complete inventory, and it supplies
  each cycle exactly once. Uniqueness then comes from the algorithm rather than from
  rotation-and-reversal dedup, which is what lets the output order be a function of the
  edge set alone.

  Implementation note: both the component decomposition (Kosaraju) and the blocked-set
  search use explicit stacks. Recursion would cap this module at CPython's recursion
  limit on a long path, and "fails above roughly a thousand nodes" is not a size
  boundary, it is a false statement about where one is.

**Determinism is by content, never by arrival.** Nodes are sorted, adjacency lists are
sorted, the component walk starts from sorted nodes, each cycle is anchored at its
minimum node, parallel edges resolve to the lexicographic minimum predicate, and the
result tuple is sorted by ``(length, nodes)``. Shuffling the input cannot change the
output -- the property FR-013 demands of every derived artifact, and the one that lets a
stored finding be compared against a recomputed one.

**No silent truncation.** The number of elementary cycles is factorial in the worst case
(a complete digraph on *n* nodes carries ``(n-1)!`` cycles), so an unbounded search is a
hang, not a slow answer. When the budget is reached the search raises
:class:`CircularityBudgetExceeded` carrying the cycles already enumerated. A truncated
tuple that looks like a complete one is the failure this repository treats as a defect
everywhere else; a finding that stops at an undeclared default is that failure wearing
a plausible shape.

**A 2-cycle is INERT by default and is always returned.** "Inert" is a classification;
dropping the object is a different and unauditable act. So it comes back carrying
:attr:`CycleMark.MUTUAL_REFERENCE`, and the verdict carries the signals that produced
it. The single hatch out of INERT -- reciprocal reach *and* real traffic through the
pair *and* two different predicates *and* no longer loop sharing the pair -- is
deliberately narrow, because every extra condition is one more way a pair can turn out
to be nothing but a pair.

**A loop of three or more nodes carries meaning only on proof.** The proof is a
conjunction, and each half guards a different failure:

* ``NO_BYPASS`` -- no two distinct nodes of the loop reach each other once the loop's
  own edges are removed, so the loop is the only way around. Without this half every
  co-occurrence pair that happens to close a triangle reads as load-bearing.
* ``CARRIES_TRAFFIC`` -- some node outside the loop is both reachable from it and able
  to reach it, so the loop genuinely sits on a route. Without this half a closed
  triangle floating alone in a subgraph would be promoted on the strength of its own
  closure, which is circular.

Missing either half yields ``SUSPECT`` -- never ``INERT``, never ``LOAD_BEARING``.
Absence of proof is not proof of noise and certainly not proof of structure. ``INERT``
is reserved for the two positive demonstrations of noise: a uniform predicate vocabulary
(one relation restated around a loop) and a complete induced relation with nothing
outside it (pairwise co-occurrence wearing the shape of a cycle).

**No vocabulary is enumerated anywhere** (FR-021, FR-030). Predicates are opaque strings,
compared only for equality and counted. A predicate no cue list has heard of still
yields an edge, still closes a cycle and still classifies. Nothing here can name what
the loop is *about*, and nothing here needs to -- which is the property the spec is
actually testing.
"""

from __future__ import annotations

import enum
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "CircularityBudget",
    "CircularityBudgetExceeded",
    "CircularityError",
    "CircularityInputError",
    "Cycle",
    "CycleClass",
    "CycleMark",
    "CycleVerdict",
    "PredicateGraph",
    "Signal",
    "classify",
    "cycles_in",
    "find_cycles",
]


class CircularityError(ValueError):
    """Base for every refusal this module raises on malformed or unbounded input."""


class CircularityInputError(CircularityError):
    """Nodes or edges that cannot be read as a predicate graph.

    Raised rather than coerced: an edge with the wrong arity is a defect upstream, and
    guessing which element was meant relocates the error into the finding itself.
    """


class CircularityBudgetExceeded(CircularityError):
    """The search hit a declared budget and stopped instead of guessing.

    ``partial`` holds the cycles already enumerated -- each of them a complete cycle
    with complete evidence, but the inventory is **not** complete. A caller must read
    the answer as truncated, never as "no further cycles exist".
    """

    def __init__(self, message: str, *, partial: tuple[Cycle, ...] = ()) -> None:
        super().__init__(message)
        self.partial = partial


class CycleMark(enum.StrEnum):
    """Marks a cycle carries before anything is classified.

    Deliberately distinct from :class:`Signal`: a mark is a fact about the cycle's own
    shape, readable without the rest of the graph. It is what stops an inert 2-cycle
    from disappearing between detection and classification.
    """

    SELF_REFERENCE = "self_reference"
    MUTUAL_REFERENCE = "mutual_reference"


class CycleVerdict(enum.StrEnum):
    """FR-022's split, plus the honest middle state.

    ``SUSPECT`` exists because the primitive answers two questions -- is this a cycle,
    and does it mean anything -- and only the first has a yes/no answer backed by
    evidence. Folding "unproven" into "inert" would bury the loops worth a human's
    attention under the ones that were never worth reporting.
    """

    LOAD_BEARING = "load_bearing"
    INERT = "inert"
    SUSPECT = "suspect"


class Signal(enum.StrEnum):
    """The only evidence classification is allowed to reason from.

    Every member is computable from a bare predicate graph with opaque predicate
    strings. None of them encodes what a predicate *means*, which is what makes FR-021
    and FR-030 true by construction rather than by review.

    Declaration order is the reporting order, so the signal list attached to a verdict
    is a deterministic, diffable artifact.
    """

    #: A loop of exactly two nodes: A points at B, B points at A.
    LENGTH_2 = "length_2"
    #: A node asserting a relation to itself.
    SELF_REFERENCE = "self_reference"
    #: Both halves of the 2-cycle are present: the shape is reciprocal reference.
    MUTUAL_REFERENCE = "mutual_reference"
    #: Every edge of the loop carries the same predicate -- one relation restated.
    UNIFORM_PREDICATE = "uniform_predicate"
    #: A strictly longer loop shares at least two nodes with this one.
    REDUNDANT_CHORD = "redundant_chord"
    #: Inside the loop, every ordered pair is also a direct edge.
    CLIQUE_INDUCTION = "clique_induction"
    #: Two distinct nodes of the loop still reach each other without the loop's edges.
    BYPASSABLE = "bypassable"
    #: The loop's edges are the only route: removing them breaks every pair.
    NO_BYPASS = "no_bypass"
    #: A node outside the loop is both downstream of and upstream of the loop.
    CARRIES_TRAFFIC = "carries_traffic"
    #: Nothing outside the loop touches it in either direction.
    PERIPHERAL = "peripheral"


# -- graph ----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PredicateGraph:
    """A directed multigraph whose edges carry opaque predicate strings.

    Compiled once and shared by both stages. Classification asks questions of the whole
    graph -- does anything attach here, can this route be bypassed -- so it must not
    re-derive adjacency from the raw edge list on every call.

    Two normalisations happen at build time, both chosen so that ordering noise in the
    input cannot reach the output:

    * duplicate edges with an identical ``(source, target, predicate)`` are idempotent.
      The same relation extracted twice is one relation, and counting it twice would
      double-weight it in every downstream statement.
    * parallel edges with *different* predicates are preserved. FR-030 requires an
      unlisted predicate to survive as an edge, and merging it into a neighbour is
      precisely the discarding the spec forbids.
    """

    nodes: tuple[str, ...]
    edges: tuple[tuple[str, str, str], ...]
    _successors: dict[str, tuple[str, ...]] = field(default_factory=dict, repr=False, compare=False)
    _predecessors: dict[str, tuple[str, ...]] = field(
        default_factory=dict, repr=False, compare=False
    )
    _between: dict[tuple[str, str], tuple[str, ...]] = field(
        default_factory=dict, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        successors: dict[str, list[str]] = {node: [] for node in self.nodes}
        predecessors: dict[str, list[str]] = {node: [] for node in self.nodes}
        between: dict[tuple[str, str], list[str]] = {}
        for source, target, predicate in self.edges:
            if source not in successors:
                raise CircularityInputError(f"edge source is not a declared node: {source!r}")
            if target not in successors:
                raise CircularityInputError(f"edge target is not a declared node: {target!r}")
            successors[source].append(target)
            predecessors[target].append(source)
            between.setdefault((source, target), []).append(predicate)
        object.__setattr__(
            self,
            "_successors",
            {node: tuple(sorted(set(targets))) for node, targets in successors.items()},
        )
        object.__setattr__(
            self,
            "_predecessors",
            {node: tuple(sorted(set(sources))) for node, sources in predecessors.items()},
        )
        object.__setattr__(
            self,
            "_between",
            {pair: tuple(sorted(set(predicates))) for pair, predicates in between.items()},
        )

    @classmethod
    def build(cls, nodes: Iterable[str], edges: Iterable[Sequence[str]]) -> PredicateGraph:
        """Compile ``(nodes, edges)`` into a canonical graph.

        An edge whose endpoint was not listed in ``nodes`` **adds** that node instead
        of raising or being skipped. The alternative -- dropping the edge because the
        node list was incomplete -- would delete a real relation on the strength of an
        unrelated bookkeeping omission, and a graph that quietly loses edges invents
        cycles that are not there while missing the ones that are.
        """
        node_set: set[str] = set()
        for node in nodes:
            if not isinstance(node, str):
                raise CircularityInputError(f"node is not a string: {node!r}")
            node_set.add(node)

        normalised: list[tuple[str, str, str]] = []
        for edge in edges:
            if len(edge) != 3:
                raise CircularityInputError(
                    f"edge must be (source, target, predicate); got arity {len(edge)}: {edge!r}"
                )
            source, target, predicate = edge
            for part in (source, target, predicate):
                if not isinstance(part, str):
                    raise CircularityInputError(f"edge component is not a string: {edge!r}")
            node_set.add(source)
            node_set.add(target)
            normalised.append((source, target, predicate))

        ordered_nodes = tuple(sorted(node_set))
        position = {node: index for index, node in enumerate(ordered_nodes)}
        unique = set(normalised)
        ordered_edges = tuple(
            sorted(unique, key=lambda edge: (position[edge[0]], position[edge[1]], edge[2]))
        )
        return cls(nodes=ordered_nodes, edges=ordered_edges)

    def successors(self, node: str) -> tuple[str, ...]:
        """Out-neighbours of ``node``, ascending. Unknown node yields an empty tuple."""
        return self._successors.get(node, ())

    def predecessors(self, node: str) -> tuple[str, ...]:
        """In-neighbours of ``node``, ascending. Unknown node yields an empty tuple."""
        return self._predecessors.get(node, ())

    def has_edge(self, source: str, target: str) -> bool:
        return (source, target) in self._between

    def predicates_between(self, source: str, target: str) -> tuple[str, ...]:
        """Every predicate on ``source -> target``, ascending. May be empty."""
        return self._between.get((source, target), ())

    def to_dict(self) -> dict[str, Any]:
        return {"nodes": list(self.nodes), "edges": [list(edge) for edge in self.edges]}


# -- cycle ----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Cycle:
    """One elementary cycle in canonical form.

    Canonical means: minimum node first, following the unique edge direction. Every
    elementary cycle has exactly one such representation, so two runs -- or two callers
    who assembled the same graph in different orders -- produce equal objects and the
    finding can be compared, cached and deduplicated by value.
    """

    #: Nodes in traversal order; the repeat of the first node is *not* included.
    nodes: tuple[str, ...]
    #: Predicate of each step; ``len == len(nodes)``. Entry *i* carries
    #: ``nodes[i] -> nodes[(i + 1) % n]``.
    predicates: tuple[str, ...]
    #: Every distinct predicate on any edge of the loop, ascending.
    vocabulary: tuple[str, ...]
    #: Shape marks, readable without the wider graph.
    marks: tuple[CycleMark, ...] = ()

    @property
    def length(self) -> int:
        return len(self.nodes)

    @property
    def is_mutual_reference(self) -> bool:
        """True for the A->B->A shape FR-022 calls out as a different finding."""
        return CycleMark.MUTUAL_REFERENCE in self.marks

    @property
    def is_self_reference(self) -> bool:
        return CycleMark.SELF_REFERENCE in self.marks

    def edge_pairs(self) -> tuple[tuple[str, str], ...]:
        """The loop's edges as ordered pairs, wrapping at the end."""
        return tuple(
            (self.nodes[index], self.nodes[(index + 1) % len(self.nodes)])
            for index in range(len(self.nodes))
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": list(self.nodes),
            "predicates": list(self.predicates),
            "vocabulary": list(self.vocabulary),
            "length": self.length,
            "marks": [mark.value for mark in self.marks],
        }


# -- verdict --------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CycleClass:
    """A verdict that cannot be returned without its own justification.

    ``verdict`` alone would be an oracle. ``reason`` names the argument in prose and
    ``signals`` names the observations the argument rests on, so a reviewer can
    disagree with the rule without having to re-run the search (FR-012, FR-082: no
    displayed statement may lack a path back to raw observations).
    """

    cycle: Cycle
    verdict: CycleVerdict
    reason: str
    signals: tuple[Signal, ...]

    @property
    def length(self) -> int:
        return self.cycle.length

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle": self.cycle.to_dict(),
            "verdict": self.verdict.value,
            "reason": self.reason,
            "signals": [signal.value for signal in self.signals],
        }


@dataclass(frozen=True, slots=True)
class CircularityBudget:
    """Declared limits. Exceeding one raises; none of them silently narrows a result.

    ``max_cycle_length`` is a refusal, not a filter: a loop longer than the cap makes
    the inventory incomplete, so it is reported as incompleteness instead of being
    quietly left out of a tuple that would then claim to be all cycles.
    """

    max_cycles: int = 10_000
    max_cycle_length: int = 64
    max_nodes: int = 50_000
    max_edges: int = 500_000


# -- search ---------------------------------------------------------------------


def _first_predicate(graph: PredicateGraph, source: str, target: str) -> str:
    """The one predicate to report for a step, when parallel edges exist.

    The lexicographic minimum. Any choice would do; a deterministic one means two
    callers holding the same graph report the same cycle, which is what makes the
    finding comparable as a value.
    """
    predicates = graph.predicates_between(source, target)
    return predicates[0] if predicates else ""


def _build_cycle(
    graph: PredicateGraph,
    nodes: Sequence[str],
    step_predicates: Sequence[str],
) -> Cycle:
    """Assemble a :class:`Cycle` from the search stack it was found on."""
    length = len(nodes)
    predicates = tuple(step_predicates) + (_first_predicate(graph, nodes[-1], nodes[0]),)
    vocabulary: set[str] = set()
    for index, node in enumerate(nodes):
        vocabulary.update(graph.predicates_between(node, nodes[(index + 1) % length]))
    if length == 1:
        marks: tuple[CycleMark, ...] = (CycleMark.SELF_REFERENCE,)
    elif length == 2:
        marks = (CycleMark.MUTUAL_REFERENCE,)
    else:
        marks = ()
    return Cycle(
        nodes=tuple(nodes),
        predicates=predicates,
        vocabulary=tuple(sorted(vocabulary)),
        marks=marks,
    )


def _record(found: list[Cycle], cycle: Cycle, limit: CircularityBudget) -> None:
    """Append, or refuse -- never truncate quietly."""
    if cycle.length > limit.max_cycle_length:
        raise CircularityBudgetExceeded(
            f"cycle of length {cycle.length} exceeds budget max_cycle_length="
            f"{limit.max_cycle_length}; the inventory is incomplete, so it is not "
            f"reported as one (partial: {len(found)} cycles)",
            partial=tuple(found),
        )
    if len(found) >= limit.max_cycles:
        raise CircularityBudgetExceeded(
            f"cycle count reached budget max_cycles={limit.max_cycles}; further cycles "
            f"may exist and none were searched (partial: {len(found)} cycles)",
            partial=tuple(found),
        )
    found.append(cycle)


def _components(graph: PredicateGraph) -> dict[str, frozenset[str]]:
    """Map each node to the member set of its strongly connected component.

    Kosaraju, both passes iterative, both walking nodes in ascending order. Only
    components that can hold a cycle are reported: a singleton without a self-loop is
    acyclic by inspection, and returning one entry per node would make the search loop
    over the whole vertex set for nothing.

    Computing the components once for the whole graph, rather than recomputing an SCC
    per start node, is what keeps the whole search ``O(V+E)`` plus the per-cycle work:
    the component of *s* restricted to the nodes *s* can reach **is** ``SCC(s)``, since
    anything reachable from *s* that also returns to *s* is mutually reachable with it.
    """
    finish_order: list[str] = []
    visited: set[str] = set()
    for start in graph.nodes:
        if start in visited:
            continue
        visited.add(start)
        frames: list[tuple[str, Any]] = [(start, iter(graph.successors(start)))]
        while frames:
            node, pending = frames[-1]
            nxt = next(pending, None)
            if nxt is None:
                frames.pop()
                finish_order.append(node)
            elif nxt not in visited:
                visited.add(nxt)
                frames.append((nxt, iter(graph.successors(nxt))))

    assignment: dict[str, int] = {}
    members: dict[int, list[str]] = {}
    for start in reversed(finish_order):
        if start in assignment:
            continue
        label = len(members)
        members[label] = []
        pending_stack = [start]
        assignment[start] = label
        while pending_stack:
            node = pending_stack.pop()
            members[label].append(node)
            for source in graph.predecessors(node):
                if source not in assignment:
                    assignment[source] = label
                    pending_stack.append(source)

    component_of: dict[str, frozenset[str]] = {}
    for label, group in members.items():
        if len(group) < 2:
            continue
        shared = frozenset(group)
        for node in group:
            component_of[node] = shared
    return component_of


def _unblock(blocked: set[str], blocked_by: dict[str, set[str]], node: str) -> None:
    """Release a node and everything that was blocked waiting on it.

    Without this the search reports a dead end as a dead end and the blocking turns
    into under-reporting: a path that exists behind a temporarily exhausted node would
    never be walked.
    """
    pending = [node]
    while pending:
        current = pending.pop()
        if current not in blocked:
            continue
        blocked.remove(current)
        for dependent in sorted(blocked_by.pop(current, ())):
            if dependent in blocked:
                pending.append(dependent)


def _circuits_through(
    graph: PredicateGraph,
    start: str,
    members: frozenset[str],
    found: list[Cycle],
    limit: CircularityBudget,
) -> None:
    """Enumerate every elementary cycle whose minimum node is exactly ``start``.

    The recursive formulation of Johnson's ``circuit`` is written here as an explicit
    frame stack. Each frame carries ``(node, pending successors, found_any)``, and
    ``found_any`` is propagated to the parent on pop -- the propagation is what tells a
    parent that its subtree emitted something and must therefore unblock itself rather
    than park its predecessors.

    ``start`` is held fixed for the whole search and no other node below it is
    entered, which makes ``start`` the minimum node of everything emitted. That is the
    uniqueness argument: each elementary cycle has exactly one minimum, so it is
    enumerated exactly once, at the iteration whose ``start`` is that minimum.
    """
    blocked: set[str] = {start}
    blocked_by: dict[str, set[str]] = {}
    stack: list[str] = [start]
    step_predicates: list[str] = []
    frames: list[list[Any]] = [[start, iter(graph.successors(start)), False]]

    while frames:
        frame = frames[-1]
        node = frame[0]
        nxt = next(frame[1], None)

        if nxt is None:
            frames.pop()
            stack.pop()
            if step_predicates:
                step_predicates.pop()
            if frame[2]:
                _unblock(blocked, blocked_by, node)
            else:
                for candidate in graph.successors(node):
                    if candidate in members and candidate > start:
                        blocked_by.setdefault(candidate, set()).add(node)
            if frames:
                frames[-1][2] = frames[-1][2] or frame[2]
            continue

        if nxt == start:
            _record(found, _build_cycle(graph, stack, step_predicates), limit)
            frame[2] = True
            continue

        if nxt <= start or nxt in blocked:
            continue

        step_predicates.append(_first_predicate(graph, node, nxt))
        stack.append(nxt)
        blocked.add(nxt)
        frames.append([nxt, iter(graph.successors(nxt)), False])


def cycles_in(
    graph: PredicateGraph,
    *,
    budget: CircularityBudget | None = None,
) -> tuple[Cycle, ...]:
    """All elementary cycles of ``graph``, canonically ordered.

    Sorted by ``(length, nodes)`` rather than by discovery order: discovery order is a
    function of traversal, and a finding whose identity depends on traversal is not
    reproducible.
    """
    limit = budget or CircularityBudget()
    if len(graph.nodes) > limit.max_nodes:
        raise CircularityBudgetExceeded(
            f"node count {len(graph.nodes)} exceeds budget max_nodes={limit.max_nodes}; "
            "no cycle was searched",
            partial=(),
        )
    if len(graph.edges) > limit.max_edges:
        raise CircularityBudgetExceeded(
            f"edge count {len(graph.edges)} exceeds budget max_edges={limit.max_edges}; "
            "no cycle was searched",
            partial=(),
        )

    found: list[Cycle] = []
    # Self-loops are emitted here rather than inside the search: the search excludes
    # `start` from its own expansion, so a self-loop on the anchor is invisible to it.
    for node in graph.nodes:
        if graph.has_edge(node, node):
            _record(found, _build_cycle(graph, (node,), ()), limit)

    component_of = _components(graph)
    for start in graph.nodes:
        members = component_of.get(start)
        if members is None:
            continue
        _circuits_through(graph, start, members, found, limit)

    found.sort(key=lambda cycle: (cycle.length, cycle.nodes))
    return tuple(found)


def find_cycles(
    nodes: Iterable[str],
    edges: Iterable[Sequence[str]],
    *,
    budget: CircularityBudget | None = None,
) -> tuple[Cycle, ...]:
    """Build the graph and enumerate its elementary cycles.

    The two-stage shape is deliberate: classification needs the same canonical graph,
    so callers that are about to classify should keep the :class:`PredicateGraph` and
    use :func:`cycles_in` rather than rebuilding from the raw lists.
    """
    return cycles_in(PredicateGraph.build(nodes, edges), budget=budget)


# -- classification -------------------------------------------------------------


def _shared_with_longer(cycle: Cycle, inventory: Sequence[Cycle]) -> bool:
    """True when a strictly longer loop contains at least two of this loop's nodes.

    Two shared nodes is the threshold because one shared node is unremarkable: loops
    sharing exactly one node are two findings that happen to touch, not one finding
    that has been split.
    """
    members = frozenset(cycle.nodes)
    return any(
        other.length > cycle.length and len(members.intersection(other.nodes)) >= 2
        for other in inventory
    )


def _clique_induced(cycle: Cycle, graph: PredicateGraph) -> bool:
    """True when the loop's own node set is completely connected in the edge direction.

    Such a loop is a restatement of pairwise co-occurrence, not a chain: there is no
    ordering to collapse, because every pair was already directly asserted.
    """
    if cycle.length < 3:
        return False
    nodes = cycle.nodes
    for source in nodes:
        for target in nodes:
            if source != target and target not in graph.successors(source):
                return False
    return True


def _bypassable(cycle: Cycle, graph: PredicateGraph) -> bool:
    """True when the loop's edges are not the only route between its own nodes.

    The loop's own node pairs are removed from the graph and every loop node is grown
    backwards over what remains; if any two distinct loop nodes end up mutually
    reachable, the loop is decoration on a route that exists without it.
    """
    pairs = frozenset(cycle.edge_pairs())
    residual_successors: dict[str, tuple[str, ...]] = {
        node: tuple(target for target in graph.successors(node) if (node, target) not in pairs)
        for node in graph.nodes
    }
    residual_predecessors: dict[str, list[str]] = {node: [] for node in graph.nodes}
    for node, targets in residual_successors.items():
        for target in targets:
            residual_predecessors[target].append(node)

    loop_nodes = frozenset(cycle.nodes)
    for anchor in cycle.nodes:
        seen = {anchor}
        pending = [anchor]
        while pending:
            node = pending.pop()
            for source in residual_predecessors[node]:
                if source not in seen:
                    seen.add(source)
                    pending.append(source)
        if (seen - {anchor}).intersection(loop_nodes):
            return True
    return False


def _carries_traffic(cycle: Cycle, graph: PredicateGraph) -> bool:
    """True when some node outside the loop is both downstream of and upstream of it.

    A loop that nothing else can enter or leave is a closed fact about itself. A loop
    with a node sitting on such a route is part of how the rest of the graph is wired.
    """
    downstream = set(cycle.nodes)
    pending = list(downstream)
    while pending:
        node = pending.pop()
        for target in graph.successors(node):
            if target not in downstream:
                downstream.add(target)
                pending.append(target)

    upstream = set(cycle.nodes)
    pending = list(upstream)
    while pending:
        node = pending.pop()
        for source in graph.predecessors(node):
            if source not in upstream:
                upstream.add(source)
                pending.append(source)

    return bool(downstream.intersection(upstream).difference(cycle.nodes))


def _observe(cycle: Cycle, graph: PredicateGraph, inventory: Sequence[Cycle]) -> tuple[Signal, ...]:
    """Every applicable signal, in declaration order.

    Collected before the verdict is chosen rather than inside the choice, so the record
    shows what was true even when a higher-priority rule decided the outcome. That is
    the difference between an explanation and a post-hoc gloss.
    """
    fired: set[Signal] = set()
    length = cycle.length
    if length == 2:
        fired.add(Signal.LENGTH_2)
        fired.add(Signal.MUTUAL_REFERENCE)
    if length == 1:
        fired.add(Signal.SELF_REFERENCE)
    if len(cycle.vocabulary) == 1:
        fired.add(Signal.UNIFORM_PREDICATE)
    if _shared_with_longer(cycle, inventory):
        fired.add(Signal.REDUNDANT_CHORD)
    if _clique_induced(cycle, graph):
        fired.add(Signal.CLIQUE_INDUCTION)
    if _bypassable(cycle, graph):
        fired.add(Signal.BYPASSABLE)
    else:
        fired.add(Signal.NO_BYPASS)
    if _carries_traffic(cycle, graph):
        fired.add(Signal.CARRIES_TRAFFIC)
    else:
        fired.add(Signal.PERIPHERAL)
    return tuple(signal for signal in Signal if signal in fired)


def _decide(cycle: Cycle, signals: Sequence[Signal]) -> tuple[CycleVerdict, str]:
    """Map signals to a verdict, by fixed precedence.

    Precedence is declared, not emergent: two signals can both hold and they can imply
    different verdicts (a tautological loop inside a busy region is still a tautology),
    and an undeclared tie-break would make the winner depend on evaluation order.
    """
    fired = frozenset(signals)
    node = cycle.nodes[0]
    pair = " and ".join(cycle.nodes)
    unique_predicate = cycle.vocabulary[0] if cycle.vocabulary else ""

    if Signal.SELF_REFERENCE in fired:
        return (
            CycleVerdict.INERT,
            (
                f"self reference: {node} asserts a relation to itself, so the loop restates "
                "one relation and orders nothing"
            ),
        )

    if Signal.LENGTH_2 in fired:
        if Signal.REDUNDANT_CHORD in fired:
            return (
                CycleVerdict.INERT,
                (
                    f"mutual reference: {pair} point at each other and the pair is also a "
                    "chord of a strictly longer loop; the longer loop is the finding and "
                    "the pair on its own orders nothing"
                ),
            )
        if Signal.UNIFORM_PREDICATE in fired:
            return (
                CycleVerdict.INERT,
                (
                    f"tautology: both halves of the pair carry the predicate "
                    f"{unique_predicate!r}, so one relation is restated rather than chained"
                ),
            )
        if Signal.NO_BYPASS in fired and Signal.CARRIES_TRAFFIC in fired:
            return (
                CycleVerdict.LOAD_BEARING,
                (
                    f"forced reciprocal route carrying traffic: removing the two edges of "
                    f"{pair} breaks the only connection between them, and an outside node "
                    "travels through the pair, so the reciprocal reference is load-bearing"
                ),
            )
        return (
            CycleVerdict.INERT,
            (
                f"mutual reference by default: {pair} point at each other and the graph "
                "shows no forced route through the pair. Reported rather than dropped, "
                "because an inert 2-cycle and a closed chain are indistinguishable in the "
                "node set alone (FR-022)"
            ),
        )

    if Signal.UNIFORM_PREDICATE in fired:
        return (
            CycleVerdict.INERT,
            (
                f"tautology: every edge of the loop carries the predicate "
                f"{unique_predicate!r}, so the loop restates one relation around "
                f"{len(cycle.nodes)} nodes instead of chaining distinct ones"
            ),
        )

    if Signal.CLIQUE_INDUCTION in fired and Signal.CARRIES_TRAFFIC not in fired:
        return (
            CycleVerdict.INERT,
            (
                "co-occurrence density: every ordered pair inside the loop is already a "
                "direct edge and nothing outside the loop reaches or leaves it, so the "
                "loop is pairwise association wearing the shape of a cycle"
            ),
        )

    if (
        Signal.NO_BYPASS in fired
        and Signal.CARRIES_TRAFFIC in fired
        and Signal.CLIQUE_INDUCTION not in fired
    ):
        return (
            CycleVerdict.LOAD_BEARING,
            (
                f"forced route carrying traffic: the {len(cycle.nodes)} edges of the loop "
                "are the only way between its nodes once removed, and an outside node is "
                "reachable from the loop and reaches back, so the loop is load-bearing"
            ),
        )

    missing: list[str] = []
    if Signal.NO_BYPASS not in fired:
        missing.append("the loop can be bypassed, so it is not the only route")
    if Signal.CARRIES_TRAFFIC not in fired:
        missing.append("nothing outside the loop travels through it")
    if Signal.CLIQUE_INDUCTION in fired:
        missing.append("the induced relation is complete, so there is no ordering to collapse")
    return (
        CycleVerdict.SUSPECT,
        "unproven: the loop is longer than two nodes but no load-bearing proof is present -- "
        + "; ".join(missing),
    )


def classify(
    cycle: Cycle,
    graph: PredicateGraph,
    *,
    cycles: Sequence[Cycle] | None = None,
) -> CycleClass:
    """Classify one cycle against the graph it lives in, with its own justification.

    ``cycles`` accepts an inventory the caller already holds -- the chord test is
    inherently global, and recomputing the whole inventory per cycle would make a batch
    quadratic for no new information. Omitted, it is computed from ``graph``.
    """
    inventory = tuple(cycles) if cycles is not None else cycles_in(graph)
    signals = _observe(cycle, graph, inventory)
    verdict, reason = _decide(cycle, signals)
    return CycleClass(cycle=cycle, verdict=verdict, reason=reason, signals=signals)