"""The semantic graph: nodes, edges, and quantifiers as things (spec 025 §32).

Spec §32 asks for ASG with three node kinds -- ``ENTITY``, ``RELATION``, ``QUANTIFIED`` --
where the quantifier is a node and not a footnote on the edge. This module is that
structure, built on the referents that :mod:`parsers.to_entities` mints.

**Why the quantifier is a node.** "Every subdomain of example.com resolves to the same AS"
and "example.com itself resolves to AS13335" are different claims, and expressing the first
as an edge with a ``universal`` flag on it makes the second indistinguishable from it. With
the quantifier as a node the first claim is an edge from a quantifier node to a relation
node, and the graph can hold both at once -- and a reader can ask which scope a claim was
made in.

**Two edges, deliberately not one.** ``ENTAILS`` is what inference produced;
``OBSERVED_IN`` is what a source said. They are separate relations because a derived
implication and a source's own claim have different evidence, different reversibility, and
different ways to be wrong. One edge type would make an inferred fact indistinguishable from
a reported one, which is the whole failure this platform exists to avoid.

**The graph asserts nothing it cannot check.** :meth:`SemanticGraph.validate` is a real
invariant check, not a formality: a relation whose endpoints are absent is a dangling edge,
and a quantifier with no variable is not a quantifier.
"""

from __future__ import annotations

import enum
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from domain.derivation import (
    Derivation,
    DerivationGraph,
    MethodFingerprint,
    NumericEnvironment,
)

__all__ = [
    "EdgeKind",
    "NodeKind",
    "Quantifier",
    "Scope",
    "SemanticEdge",
    "SemanticGraph",
    "SemanticNode",
]


class NodeKind(str, enum.Enum):
    ENTITY = "entity"
    RELATION = "relation"
    QUANTIFIED = "quantified"


class EdgeKind(str, enum.Enum):
    #: A source reported this directly.
    OBSERVED_IN = "observed_in"
    #: Inference produced this from premises. Not the same as reported, and never merged.
    ENTAILS = "entails"
    #: Two entities were seen together in one document. The weakest claim available.
    CO_OCCURS = "co_occurs"
    #: Explicit subsumption, produced by the schema registry.
    SUBSUMES = "subsumes"


@dataclass(frozen=True, slots=True)
class Scope:
    """The scope a claim was made in.

    A node, not a string on the edge, because "in the document that said it" and "in
    everything the platform knows" are different claims and a reader must be able to tell
    them apart. ``bitemporal`` names that distinction explicitly rather than leaving a caller
    to guess from a timestamp.
    """

    #: Observation or document the claim came from. Empty for a platform-wide claim.
    observation_ref: str = ""
    tenant_id: str = ""
    #: When the claim stopped being true, if ever. Empty means still asserted.
    valid_until: str = ""

    def is_platform_wide(self) -> bool:
        return not self.observation_ref

    def as_dict(self) -> dict[str, str]:
        return {
            "observation_ref": self.observation_ref,
            "tenant_id": self.tenant_id,
            "valid_until": self.valid_until,
        }


@dataclass(frozen=True, slots=True)
class Quantifier:
    """A quantified pattern: what varies, what is fixed, and how many are needed.

    ``variables`` are the positions that vary; ``constants`` are what stays pinned. The
    distinction is load-bearing -- "every subdomain resolves to AS13335" and "AS13335 owns
    every subdomain" have the same two variables in different roles, and merging them would
    assert the second when the source said the first.
    """

    #: ``every`` (all match), ``some`` (at least one), ``count_at_least`` / ``count_at_most``.
    operator: str
    variables: tuple[str, ...]
    constants: Mapping[str, str] = field(default_factory=dict)
    #: Threshold for the counting operators. ``None`` for every/some.
    threshold: int | None = None
    #: Path the quantifier walks, e.g. ``"subdomain_of"``.
    via: str = ""

    def __post_init__(self) -> None:
        if self.operator not in ("every", "some", "count_at_least", "count_at_most"):
            raise ValueError(f"unknown quantifier operator: {self.operator!r}")
        if not self.variables:
            # A quantifier over nothing is a constant pretending to be a rule.
            raise ValueError("a quantifier needs at least one variable")
        if self.threshold is not None and self.operator.startswith("count_"):
            if self.threshold < 0:
                raise ValueError("threshold must not be negative")
        elif self.threshold is not None:
            raise ValueError("only a counting quantifier takes a threshold")

    def as_dict(self) -> dict[str, Any]:
        return {
            "operator": self.operator,
            "variables": list(self.variables),
            "constants": dict(self.constants),
            "threshold": self.threshold,
            "via": self.via,
        }


@dataclass(frozen=True, slots=True)
class SemanticNode:
    node_id: str
    kind: NodeKind
    #: Entity referent for ``ENTITY``; predicate for ``RELATION``; operator for ``QUANTIFIED``.
    label: str = ""
    entity_type: str = "unknown"
    quantifier: Quantifier | None = None
    #: The claim this node makes, when it is a relation.
    predicate: str = ""
    subject: str = ""
    object: str = ""

    def __post_init__(self) -> None:
        if self.kind is NodeKind.QUANTIFIED and self.quantifier is None:
            raise ValueError("a quantified node needs a quantifier")
        if self.kind is NodeKind.RELATION and not (
            self.predicate and self.subject and self.object
        ):
            raise ValueError("a relation node needs a predicate, a subject and an object")

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "node_id": self.node_id,
            "kind": self.kind.value,
            "label": self.label,
        }
        if self.kind is NodeKind.ENTITY:
            out["entity_type"] = self.entity_type
        if self.quantifier is not None:
            out["quantifier"] = self.quantifier.as_dict()
        if self.kind is NodeKind.RELATION:
            out.update(
                {
                    "predicate": self.predicate,
                    "subject": self.subject,
                    "object": self.object,
                }
            )
        return out


@dataclass(frozen=True, slots=True)
class SemanticEdge:
    source: str
    target: str
    kind: EdgeKind
    scope: Scope = field(default_factory=Scope)
    derivation_id: str = ""
    confidence: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "kind": self.kind.value,
            "scope": self.scope.as_dict(),
            "derivation_id": self.derivation_id,
            "confidence": self.confidence,
        }


class SemanticGraph:
    """Nodes and edges, with derivations attached to the edges that inference produced.

    Construction validates on the way in rather than at query time: a dangling edge is
    refused by :meth:`add_edge`, because a graph that accepted one would answer "who owns
    this domain" with an edge to a node that does not exist, and the reader would have no way
    to tell the difference from a graph that simply had not been loaded yet.
    """

    def __init__(self) -> None:
        self._nodes: dict[str, SemanticNode] = {}
        self._edges: list[SemanticEdge] = []
        self.derivations = DerivationGraph()

    def __len__(self) -> int:
        return len(self._nodes)

    def __contains__(self, node_id: object) -> bool:
        return str(node_id) in self._nodes

    # -- construction -------------------------------------------------------

    def add_node(self, node: SemanticNode) -> str:
        self._nodes[node.node_id] = node
        return node.node_id

    def add_entity(self, referent_id: str, *, entity_type: str = "unknown", label: str = "") -> str:
        return self.add_node(
            SemanticNode(
                node_id=referent_id,
                kind=NodeKind.ENTITY,
                label=label,
                entity_type=entity_type,
            )
        )

    def add_relation(
        self,
        node_id: str,
        *,
        predicate: str,
        subject: str,
        object: str,
        label: str = "",
    ) -> str:
        return self.add_node(
            SemanticNode(
                node_id=node_id,
                kind=NodeKind.RELATION,
                label=label or predicate,
                predicate=predicate,
                subject=subject,
                object=object,
            )
        )

    def add_quantifier(self, node_id: str, quantifier: Quantifier, *, label: str = "") -> str:
        return self.add_node(
            SemanticNode(
                node_id=node_id,
                kind=NodeKind.QUANTIFIED,
                label=label or quantifier.operator,
                quantifier=quantifier,
            )
        )

    def add_edge(
        self,
        source: str,
        target: str,
        kind: EdgeKind,
        *,
        scope: Scope = None,  # type: ignore[assignment]
        derivation_id: str = "",
        confidence: float | None = None,
    ) -> SemanticEdge:
        missing = [n for n in (source, target) if n not in self._nodes]
        if missing:
            raise KeyError(f"edge references {len(missing)} unknown node(s): {missing}")
        if derivation_id and kind is not EdgeKind.OBSERVED_IN and derivation_id not in self.derivations:
            raise KeyError(f"edge cites an unrecorded derivation: {derivation_id}")
        edge = SemanticEdge(
            source=source,
            target=target,
            kind=kind,
            scope=scope or Scope(),
            derivation_id=derivation_id,
            confidence=confidence,
        )
        self._edges.append(edge)
        return edge

    def record(
        self,
        method: MethodFingerprint,
        *,
        inputs: Iterable[str],
        output: str,
        statement: str,
        parents: tuple[str, ...] = (),
        confidence: float | None = None,
    ) -> str:
        """Record a derivation and return its id, for an edge to cite."""
        return self.derivations.add(
            Derivation(
                method=method,
                inputs=tuple(inputs),
                output=output,
                statement=statement,
                parents=parents,
                environment=NumericEnvironment(),
                confidence=confidence,
            )
        )

    # -- reading ------------------------------------------------------------

    def node(self, node_id: str) -> SemanticNode | None:
        return self._nodes.get(str(node_id))

    def nodes_of_kind(self, kind: NodeKind) -> tuple[SemanticNode, ...]:
        return tuple(n for n in self._nodes.values() if n.kind is kind)

    def quantifiers(self) -> tuple[SemanticNode, ...]:
        return self.nodes_of_kind(NodeKind.QUANTIFIED)

    def edges(self, kind: EdgeKind | None = None) -> tuple[SemanticEdge, ...]:
        if kind is None:
            return tuple(self._edges)
        return tuple(e for e in self._edges if e.kind is kind)

    def neighbours(self, node_id: str) -> tuple[SemanticEdge, ...]:
        return tuple(e for e in self._edges if e.source == node_id or e.target == node_id)

    def edges_in_scope(self, scope: Scope) -> tuple[SemanticEdge, ...]:
        return tuple(
            e
            for e in self._edges
            if e.scope.observation_ref == scope.observation_ref
            and e.scope.tenant_id == scope.tenant_id
        )

    def why(self, edge: SemanticEdge) -> tuple[str, ...]:
        """The statements behind an edge. Empty for an observed one -- that is the point."""
        if not edge.derivation_id:
            return ()
        derivation = self.derivations.get(edge.derivation_id)
        return (derivation.statement,) if derivation and derivation.statement else ()

    def supports(self, node_id: str) -> tuple[str, ...]:
        return tuple(s for e in self.neighbours(node_id) for s in self.why(e))

    def validate(self) -> tuple[str, ...]:
        """Every structural defect found. Empty means the graph is well-formed.

        Kept as a method rather than enforced at insertion only: the graph is loaded from
        storage as well as built, and a load can produce what construction cannot.
        """
        problems: list[str] = []
        for edge in self._edges:
            if edge.source not in self._nodes:
                problems.append(f"dangling edge from {edge.source}")
            if edge.target not in self._nodes:
                problems.append(f"dangling edge to {edge.target}")
            if edge.kind is EdgeKind.OBSERVED_IN and edge.derivation_id:
                problems.append(
                    f"{edge.source}->{edge.target}: an observed edge cites a derivation"
                )
            if edge.kind is not EdgeKind.OBSERVED_IN and not edge.derivation_id:
                problems.append(
                    f"{edge.source}->{edge.target}: {edge.kind.value} edge has no derivation"
                )
            if edge.derivation_id and edge.derivation_id not in self.derivations:
                problems.append(f"edge cites unknown derivation {edge.derivation_id}")
        for node in self._nodes.values():
            if node.kind is NodeKind.RELATION:
                for endpoint in (node.subject, node.object):
                    if endpoint not in self._nodes:
                        problems.append(f"relation {node.node_id} cites unknown {endpoint}")
        return tuple(problems)

    def snapshot(self) -> dict[str, Any]:
        return {
            "nodes": len(self._nodes),
            "entities": len(self.nodes_of_kind(NodeKind.ENTITY)),
            "relations": len(self.nodes_of_kind(NodeKind.RELATION)),
            "quantified": len(self.nodes_of_kind(NodeKind.QUANTIFIED)),
            "edges": len(self._edges),
            "edge_kinds": {
                k.value: len(self.edges(k)) for k in EdgeKind if self.edges(k)
            },
            "derivations": len(self.derivations),
            "problems": list(self.validate()),
        }