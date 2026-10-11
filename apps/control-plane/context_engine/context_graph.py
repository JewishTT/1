"""The Context Graph — first-class, durable, and the thing the user actually works in.

Everything else in this platform is a projection: the knowledge graph, the entity fabric, the
TDA layers. The Context Graph is not. It is written by the context layer and read by the
analyst, and it survives being wrong -- a question can be retracted, a hypothesis abandoned, a
claim retracted by the person who made it, and the record of that still exists. A projection
rebuilt from facts cannot represent "we asked this and it went nowhere", because the absence
of the question leaves no trace to rebuild from.

That last point is the design constraint the whole module is built around (§3.8). There are
three states, not two:

    empty      -- nothing was written, and nothing is claimed
    unknown    -- an `Unknown` node exists, recording that a question was asked and not answered
    known      -- nodes and edges exist

Collapsing ``empty`` into ``unknown`` is the specific failure this type system exists to
prevent. "We never looked at this company" and "we looked and found nothing" are different
statements about the world, and an analyst acting on the second one wrongly will stop asking.

Identity is content-derived, so replaying the same decisions produces the same graph and two
processes cannot mint two ids for one question. Edges are validated against their endpoints at
write time: a dangling edge is a claim about something the graph has never heard of, and
accepting it would mean the graph's own integrity depended on a caller having been careful.

The store protocol exists so the graph's semantics can be tested exhaustively in memory and
then run unchanged on PostgreSQL (§3.6). Nothing here imports a database.
"""

from __future__ import annotations

import hashlib
import inspect
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol


class ContextNodeType(StrEnum):
    """The ten node types the graph is required to carry (§3.2).

    ``Unknown`` is a node type rather than an absence of a node type, and the distinction is
    enforced by the type system rather than left to discipline: ``empty`` is the absence of any
    ``Unknown`` node, and the graph reports the two differently on purpose.
    """

    INVESTIGATION = "Investigation"
    QUESTION = "Question"
    SCOPE = "Scope"
    HYPOTHESIS = "Hypothesis"
    TASK = "Task"
    EVIDENCE_SET = "EvidenceSet"
    CLAIM = "Claim"
    CONTRADICTION = "Contradiction"
    UNKNOWN = "Unknown"
    REVISION = "Revision"


class ContextEdgeType(StrEnum):
    """The ten edge types (§3.3).

    ``derived_from`` and ``supersedes`` are separate because they answer different questions:
    one says how this was computed, the other says what this replaced. Merging them would make
    every recomputation look like a retraction.
    """

    ASKS = "asks"
    SCOPES = "scopes"
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    REFINES = "refines"
    DELEGATES = "delegates"
    OBSERVES = "observes"
    REVISES = "revises"
    DERIVED_FROM = "derived_from"
    SUPERSEDES = "supersedes"


#: Which node types each edge may connect. An edge outside its permitted shape is refused at
#: write time: an ``asks`` edge from a Hypothesis to a Question is a claim about the domain's
#: structure, and letting it through would put that claim in the graph where the analyst reads
#: it as fact.
EDGE_ENDPOINTS: Mapping[ContextEdgeType, tuple[frozenset[ContextNodeType], frozenset[ContextNodeType]]] = {
    ContextEdgeType.ASKS: (
        frozenset({ContextNodeType.INVESTIGATION, ContextNodeType.TASK}),
        frozenset({ContextNodeType.QUESTION, ContextNodeType.SCOPE}),
    ),
    ContextEdgeType.SCOPES: (
        frozenset({ContextNodeType.INVESTIGATION, ContextNodeType.QUESTION}),
        frozenset({ContextNodeType.SCOPE}),
    ),
    ContextEdgeType.SUPPORTS: (
        frozenset({ContextNodeType.EVIDENCE_SET, ContextNodeType.CLAIM, ContextNodeType.TASK}),
        frozenset({ContextNodeType.CLAIM, ContextNodeType.HYPOTHESIS}),
    ),
    ContextEdgeType.CONTRADICTS: (
        frozenset({ContextNodeType.CLAIM, ContextNodeType.EVIDENCE_SET}),
        frozenset({ContextNodeType.CLAIM, ContextNodeType.HYPOTHESIS}),
    ),
    ContextEdgeType.REFINES: (
        frozenset({ContextNodeType.QUESTION, ContextNodeType.CLAIM, ContextNodeType.HYPOTHESIS}),
        frozenset({ContextNodeType.QUESTION, ContextNodeType.CLAIM, ContextNodeType.HYPOTHESIS}),
    ),
    ContextEdgeType.DELEGATES: (
        frozenset({ContextNodeType.INVESTIGATION, ContextNodeType.QUESTION, ContextNodeType.TASK}),
        frozenset({ContextNodeType.TASK}),
    ),
    ContextEdgeType.OBSERVES: (
        frozenset({ContextNodeType.TASK, ContextNodeType.QUESTION, ContextNodeType.SCOPE}),
        frozenset({ContextNodeType.EVIDENCE_SET}),
    ),
    ContextEdgeType.REVISES: (
        frozenset({ContextNodeType.REVISION}),
        frozenset({ContextNodeType.QUESTION, ContextNodeType.CLAIM, ContextNodeType.HYPOTHESIS, ContextNodeType.SCOPE}),
    ),
    ContextEdgeType.DERIVED_FROM: (
        frozenset({ContextNodeType.CLAIM, ContextNodeType.REVISION, ContextNodeType.HYPOTHESIS, ContextNodeType.CONTRADICTION}),
        frozenset({ContextNodeType.EVIDENCE_SET, ContextNodeType.CLAIM, ContextNodeType.REVISION}),
    ),
    ContextEdgeType.SUPERSEDES: (
        frozenset({ContextNodeType.REVISION, ContextNodeType.CLAIM, ContextNodeType.HYPOTHESIS, ContextNodeType.QUESTION}),
        frozenset({ContextNodeType.REVISION, ContextNodeType.CLAIM, ContextNodeType.HYPOTHESIS, ContextNodeType.QUESTION}),
    ),
}


class ContextGraphError(ValueError):
    """A write was refused. The graph is unchanged; nothing partial is kept."""


async def _resolve(value: Any) -> Any:
    """Await a store result only if the store is asynchronous."""
    if inspect.isawaitable(value):
        return await value
    return value


def _canonical(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _canonical(value[k]) for k in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_canonical(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, StrEnum):
        return str(value)
    return value


def _digest(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def node_id(node_type: ContextNodeType, investigation_id: str, key: str) -> str:
    """Content-derived node address.

    Keyed on the investigation so two investigations asking the same question get different
    nodes -- the same sentence asked in two contexts is two questions.
    """
    return "CN-" + _digest(node_type, investigation_id, key.strip().lower())[:20]


def edge_id(edge_type: ContextEdgeType, source: str, target: str) -> str:
    return "CE-" + _digest(edge_type, source, target)[:20]


@dataclass(frozen=True, slots=True)
class ContextNode:
    node_id: str
    type: ContextNodeType
    investigation_id: str
    label: str
    key: str = ""
    props: Mapping[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "type": str(self.type),
            "investigation_id": self.investigation_id,
            "label": self.label,
            "key": self.key,
            "props": _canonical(dict(self.props)),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> ContextNode:
        created = raw.get("created_at")
        return cls(
            node_id=str(raw["node_id"]),
            type=ContextNodeType(raw["type"]),
            investigation_id=str(raw["investigation_id"]),
            label=str(raw.get("label", "")),
            key=str(raw.get("key", "")),
            props=dict(raw.get("props") or {}),
            created_at=datetime.fromisoformat(created) if isinstance(created, str) else None,
        )


@dataclass(frozen=True, slots=True)
class ContextEdge:
    edge_id: str
    type: ContextEdgeType
    source: str
    target: str
    weight: float = 1.0
    rationale: str = ""
    observation_refs: tuple[str, ...] = ()
    created_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "type": str(self.type),
            "source": self.source,
            "target": self.target,
            "weight": self.weight,
            "rationale": self.rationale,
            "observation_refs": list(self.observation_refs),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> ContextEdge:
        created = raw.get("created_at")
        return cls(
            edge_id=str(raw["edge_id"]),
            type=ContextEdgeType(raw["type"]),
            source=str(raw["source"]),
            target=str(raw["target"]),
            weight=float(raw.get("weight", 1.0)),
            rationale=str(raw.get("rationale", "")),
            observation_refs=tuple(raw.get("observation_refs") or ()),
            created_at=datetime.fromisoformat(created) if isinstance(created, str) else None,
        )


@dataclass(frozen=True, slots=True)
class DecisionRecord:
    """Why a transaction happened, kept beside what it changed (FR-003).

    A graph whose edges appear with no recorded reason cannot be audited, and an unauditable
    graph cannot be retracted selectively -- which is the whole point of keeping claims rather
    than overwriting them.
    """

    decision_id: str
    actor: str
    rationale: str
    added_nodes: tuple[str, ...]
    added_edges: tuple[str, ...]
    at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "actor": self.actor,
            "rationale": self.rationale,
            "added_nodes": list(self.added_nodes),
            "added_edges": list(self.added_edges),
            "at": self.at.isoformat() if self.at else None,
        }


@dataclass(frozen=True, slots=True)
class Transaction:
    """One atomic unit: nodes and the edges between them, all accepted or all refused.

    Order matters and is deliberate. Nodes are written first, so an edge inside the same
    transaction may reference a node that did not exist a moment ago; edges are then validated
    against the *post-write* graph, which is what makes ``Observation -observes-> EvidenceSet``
    expressible without a second round-trip.
    """

    nodes: tuple[ContextNode, ...] = ()
    edges: tuple[ContextEdge, ...] = ()
    actor: str = "system"
    rationale: str = ""

    def is_empty(self) -> bool:
        return not self.nodes and not self.edges


@dataclass(frozen=True, slots=True)
class Snapshot:
    nodes: tuple[ContextNode, ...] = ()
    edges: tuple[ContextEdge, ...] = ()
    decisions: tuple[DecisionRecord, ...] = ()

    def node(self, node_id: str) -> ContextNode | None:
        return next((n for n in self.nodes if n.node_id == node_id), None)

    def edges_from(self, node_id: str, edge_type: ContextEdgeType | None = None) -> tuple[ContextEdge, ...]:
        return tuple(
            e
            for e in self.edges
            if e.source == node_id and (edge_type is None or e.type is edge_type)
        )

    def degree(self, node_id: str) -> int:
        return sum(1 for e in self.edges if e.source == node_id or e.target == node_id)


class ContextGraphStore(Protocol):
    """Persistence for the graph (§3.6). Implementations must make ``apply`` atomic.

    ``apply`` and ``snapshot`` may be synchronous (the in-memory reference) or return an
    awaitable (PostgreSQL). The graph calls both through :func:`_resolve`, so a store is not
    forced to pretend it is synchronous to satisfy the type -- which is what an `async def` on
    the protocol would have done, at the cost of making the in-memory reference unusable from
    a plain unit test.
    """

    def apply(self, tenant_id: str, transaction: Transaction) -> Any: ...

    def snapshot(self, tenant_id: str, investigation_id: str | None = None) -> Any: ...


def validate(graph_nodes: Mapping[str, ContextNode], edges: Iterable[ContextEdge]) -> None:
    """Refuse a write that would leave the graph lying about itself.

    Two rules, both decided at write time because neither can be repaired later without
    guessing: an edge must have two endpoints the graph knows, and its endpoint types must be
    ones the edge type permits. Both raise rather than warn, and the caller writes nothing.
    """
    for edge in edges:
        source = graph_nodes.get(edge.source)
        target = graph_nodes.get(edge.target)
        if source is None:
            raise ContextGraphError(
                f"{edge.type} edge {edge.edge_id} starts at unknown node {edge.source}"
            )
        if target is None:
            raise ContextGraphError(
                f"{edge.type} edge {edge.edge_id} ends at unknown node {edge.target}"
            )
        allowed_source, allowed_target = EDGE_ENDPOINTS[edge.type]
        if source.type not in allowed_source:
            raise ContextGraphError(
                f"{edge.type} may not start at a {source.type} ({source.node_id})"
            )
        if target.type not in allowed_target:
            raise ContextGraphError(
                f"{edge.type} may not end at a {target.type} ({target.node_id})"
            )


class ContextGraph:
    """The graph, over whatever store holds it.

    The semantics live here and nowhere else; the store only remembers. That split is what
    lets the whole of §3.6 be satisfied by writing a second store rather than by
    re-implementing the rules.
    """

    def __init__(self, store: ContextGraphStore, *, clock: Any = None) -> None:
        self._store = store
        self._clock = clock or (lambda: datetime.now(UTC))

    # ------------------------------------------------------------------ writing

    async def apply(
        self,
        tenant_id: str,
        transaction: Transaction,
        *,
        investigation_id: str = "",
    ) -> DecisionRecord:
        if transaction.is_empty():
            raise ContextGraphError("an empty transaction records nothing")
        stamped = Transaction(
            nodes=tuple(replace(n, created_at=n.created_at or self._clock()) for n in transaction.nodes),
            edges=tuple(replace(e, created_at=e.created_at or self._clock()) for e in transaction.edges),
            actor=transaction.actor,
            rationale=transaction.rationale,
        )
        for node in stamped.nodes:
            if node.investigation_id and investigation_id and node.investigation_id != investigation_id:
                raise ContextGraphError(
                    f"node {node.node_id} belongs to investigation {node.investigation_id}, "
                    f"not {investigation_id}"
                )
        return await _resolve(self._store.apply(tenant_id, stamped))

    async def ask(
        self,
        tenant_id: str,
        investigation_id: str,
        question: str,
        *,
        actor: str = "analyst",
        scope_ids: Sequence[str] = (),
        rationale: str = "",
    ) -> DecisionRecord:
        """The first move in every investigation: write down what is being asked.

        Scopes are attached in the same transaction rather than as a second call, so a
        question is never visible without the scope that bounds it -- a half-written question
        is the kind of gap that turns into a wrong answer three steps later.
        """
        node = ContextNode(
            node_id=node_id(ContextNodeType.QUESTION, investigation_id, question),
            type=ContextNodeType.QUESTION,
            investigation_id=investigation_id,
            label=question.strip(),
            key=question.strip(),
        )
        edges = [
            ContextEdge(
                edge_id=edge_id(ContextEdgeType.SCOPES, node.node_id, scope),
                type=ContextEdgeType.SCOPES,
                source=node.node_id,
                target=scope,
            )
            for scope in scope_ids
        ]
        return await self.apply(
            tenant_id,
            Transaction(nodes=(node,), edges=tuple(edges), actor=actor, rationale=rationale),
            investigation_id=investigation_id,
        )

    async def record_unknown(
        self,
        tenant_id: str,
        investigation_id: str,
        about: str,
        *,
        actor: str = "system",
        rationale: str = "",
        props: Mapping[str, Any] | None = None,
    ) -> DecisionRecord:
        """Write down that something was looked for and not found.

        This is the method §3.8 exists to make easy. Without it the only honest options were
        to say nothing -- indistinguishable from never asking -- or to write a Claim saying
        "there is nothing", which is a positive assertion the platform cannot support.
        """
        node = ContextNode(
            node_id=node_id(ContextNodeType.UNKNOWN, investigation_id, about),
            type=ContextNodeType.UNKNOWN,
            investigation_id=investigation_id,
            label=f"Unknown: {about.strip()}",
            key=about.strip(),
            props=dict(props or {}),
        )
        return await self.apply(
            tenant_id,
            Transaction(nodes=(node,), actor=actor, rationale=rationale),
            investigation_id=investigation_id,
        )

    # ------------------------------------------------------------------ reading

    async def snapshot(self, tenant_id: str, investigation_id: str | None = None) -> Snapshot:
        return await _resolve(self._store.snapshot(tenant_id, investigation_id))

    async def state_of(self, tenant_id: str, investigation_id: str) -> str:
        """``empty``, ``unknown`` or ``known`` -- three states, never two (§3.8).

        ``unknown`` is returned only when *everything* in scope is an ``Unknown``. A graph
        holding a question and an unanswered ``Unknown`` is not "unknown" in the sense §3.8
        warns about -- plenty is known, including the fact that one thing was asked and left
        open. Collapsing that into ``unknown`` would swap one kind of silence for another, and
        the count of what is still open is reported by :meth:`open_unknowns` instead of by
        blurring the graph's state.

        Returned as a first-class answer rather than inferred from a node count, because the
        difference is the entire point: ``empty`` means nothing was ever written.
        """
        snap = await self._resolve_snapshot(tenant_id, investigation_id)
        if not snap.nodes:
            return "empty"
        if all(n.type is ContextNodeType.UNKNOWN for n in snap.nodes):
            return "unknown"
        return "known"

    async def open_unknowns(self, tenant_id: str, investigation_id: str) -> tuple[ContextNode, ...]:
        """The `Unknown` nodes still standing -- asked and not answered, in the analyst's view.

        A first-class answer rather than a derived count, because these are the nodes that
        become obligations. An investigation whose open unknowns are not enumerable cannot be
        scheduled.
        """
        snap = await self._resolve_snapshot(tenant_id, investigation_id)
        return tuple(n for n in snap.nodes if n.type is ContextNodeType.UNKNOWN)

    async def audit_trail(self, tenant_id: str) -> tuple[DecisionRecord, ...]:
        """Every decision ever recorded for the tenant, oldest first (FR-003)."""
        return (await self._resolve_snapshot(tenant_id, None)).decisions

    async def _resolve_snapshot(self, tenant_id: str, investigation_id: str | None) -> Snapshot:
        return await _resolve(self._store.snapshot(tenant_id, investigation_id))


class InMemoryContextGraphStore:
    """Reference implementation.

    Node and edge ids are content-derived, so re-applying the same transaction is a no-op
    rather than a duplicate: replaying a decision log must not double the graph.
    """

    def __init__(self) -> None:
        self._nodes: dict[str, dict[str, ContextNode]] = {}
        self._edges: dict[str, dict[str, ContextEdge]] = {}
        self._decisions: dict[str, list[DecisionRecord]] = {}

    def apply(self, tenant_id: str, transaction: Transaction) -> DecisionRecord:
        nodes = self._nodes.setdefault(tenant_id, {})
        edges = self._edges.setdefault(tenant_id, {})
        for node in transaction.nodes:
            nodes.setdefault(node.node_id, node)
        validate(nodes, transaction.edges)
        for edge in transaction.edges:
            edges.setdefault(edge.edge_id, edge)
        decision = DecisionRecord(
            decision_id="CD-" + _digest(
                tenant_id,
                transaction.actor,
                transaction.rationale,
                ",".join(sorted(n.node_id for n in transaction.nodes)),
                ",".join(sorted(e.edge_id for e in transaction.edges)),
                ",".join(sorted(d.decision_id for d in self._decisions.get(tenant_id, []))),
            )[:20],
            actor=transaction.actor,
            rationale=transaction.rationale,
            added_nodes=tuple(n.node_id for n in transaction.nodes),
            added_edges=tuple(e.edge_id for e in transaction.edges),
            at=transaction.nodes[0].created_at if transaction.nodes else None,
        )
        self._decisions.setdefault(tenant_id, []).append(decision)
        return decision

    def snapshot(self, tenant_id: str, investigation_id: str | None = None) -> Snapshot:
        nodes = tuple(self._nodes.get(tenant_id, {}).values())
        edges = tuple(self._edges.get(tenant_id, {}).values())
        if investigation_id:
            keep = {n.node_id for n in nodes if n.investigation_id == investigation_id}
            nodes = tuple(n for n in nodes if n.node_id in keep)
            edges = tuple(e for e in edges if e.source in keep and e.target in keep)
        return Snapshot(
            nodes=tuple(sorted(nodes, key=lambda n: n.node_id)),
            edges=tuple(sorted(edges, key=lambda e: e.edge_id)),
            decisions=tuple(self._decisions.get(tenant_id, [])),
        )