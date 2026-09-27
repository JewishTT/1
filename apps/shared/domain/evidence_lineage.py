"""Evidence lineage: bidirectional traversal that states its own incompleteness.

Contract is ``specs/016-relation-evidence-graph-fabric/data-model.md`` section 8
(tasks T058-T062 with T064): every relation answers *why do you believe this?*
by walking ``relation → assertion → mention → segment → observation → capture →
source`` backward, and by walking source → relation forward.

Traversal is pure and I/O-free — the graph holds nothing but what was injected,
and nothing is looked up outside it. It is depth-limited by the canonical chain
order and **stops at the first missing hop**: an incomplete chain returns the
hops it did resolve, ``complete=False``, and the name of the gap (FR-033). An
empty hop list would read as "no evidence at all", which is a different and
false claim, so incompleteness is a result and never a silent truncation.

Independence is by source *family*, not by document: two captures of one wire
story are two publications and one source, and those two counts are never fused
into a single number (FR-034, constitution IV).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any, Literal

__all__ = [
    "BACKWARD_CHAIN",
    "EvidenceGraph",
    "EvidenceHop",
    "HopKind",
    "LineageTrace",
    "independence_groups",
]


class HopKind(StrEnum):
    """One step of the evidence chain; the value is what persistence stores.

    The vocabulary is the chain from the origin (a source) up to what a relation
    claims, so a reader can tell a derived node from the evidence under it.
    """

    SOURCE = "source"
    CAPTURE = "capture"
    OBSERVATION = "observation"
    SEGMENT = "segment"
    MENTION = "mention"
    CANDIDATE = "candidate"
    ASSERTION = "assertion"
    RELATION = "relation"
    ENTITY = "entity"


BACKWARD_CHAIN: tuple[HopKind, ...] = (
    HopKind.RELATION,
    HopKind.ASSERTION,
    HopKind.MENTION,
    HopKind.SEGMENT,
    HopKind.OBSERVATION,
    HopKind.CAPTURE,
    HopKind.SOURCE,
)

# (kind, required): an absent required hop ends the trace and names the gap, an
# absent optional hop is skipped so a chain that never had one still completes.
_FORWARD_STEPS: tuple[tuple[HopKind, bool], ...] = (
    (HopKind.CAPTURE, True),
    (HopKind.OBSERVATION, True),
    (HopKind.SEGMENT, True),
    (HopKind.MENTION, True),
    (HopKind.CANDIDATE, False),
    (HopKind.ASSERTION, True),
    (HopKind.RELATION, True),
    (HopKind.ENTITY, False),
)


@dataclass(frozen=True)
class EvidenceHop:
    """One node of the evidence chain, typed by its ``kind``.

    ``node_id`` is the single identity field for every kind, so the trace is
    uniform and one column stores any step. ``relation_id`` names the relation a
    derived node is grounded in, which is what lets a forward trace hand back
    each derived relation together with the assertion behind it (FR-032); it is
    left empty when the producer has not attributed the hop yet.
    """

    kind: HopKind
    node_id: str
    label: str = ""
    relation_id: str = ""
    tenant_id: str = "default-tenant"

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", HopKind(self.kind))
        if not self.node_id:
            raise ValueError("an evidence hop requires a node_id")

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": str(self.kind),
            "node_id": self.node_id,
            "label": self.label,
            "relation_id": self.relation_id,
            "tenant_id": self.tenant_id,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> EvidenceHop:
        return cls(
            kind=HopKind(str(payload["kind"])),
            node_id=str(payload["node_id"]),
            label=str(payload.get("label", "")),
            relation_id=str(payload.get("relation_id", "")),
            tenant_id=str(payload.get("tenant_id", "default-tenant")),
        )


@dataclass(frozen=True)
class LineageTrace:
    """One traversal and its completeness, recorded rather than implied.

    The fields are the ``claim_context_lineage`` record of
    ``data-model.md`` section 10.1 read as an object: the subject and direction
    identify the row, the hops are its payload, and the last three say exactly
    where the walk stopped. A trace may not claim completeness while naming an
    unresolved hop, so a gap can never be read as a whole chain.
    """

    subject_id: str
    direction: Literal["backward", "forward"]
    hops: tuple[EvidenceHop, ...]
    complete: bool
    first_unresolved_hop: HopKind | None = None
    unresolved_node_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "hops", tuple(self.hops))
        object.__setattr__(self, "direction", str(self.direction))
        if self.first_unresolved_hop is not None:
            object.__setattr__(self, "first_unresolved_hop", HopKind(self.first_unresolved_hop))
        if self.complete and self.first_unresolved_hop is not None:
            raise ValueError("a complete trace cannot name an unresolved hop")

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject_id": self.subject_id,
            "direction": str(self.direction),
            "hops": [hop.to_dict() for hop in self.hops],
            "complete": self.complete,
            "first_unresolved_hop": (
                None if self.first_unresolved_hop is None else str(self.first_unresolved_hop)
            ),
            "unresolved_node_id": self.unresolved_node_id,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> LineageTrace:
        unresolved = payload.get("first_unresolved_hop")
        return cls(
            subject_id=str(payload["subject_id"]),
            direction=str(payload.get("direction", "backward")),
            hops=tuple(EvidenceHop.from_dict(hop) for hop in payload.get("hops") or ()),
            complete=bool(payload.get("complete", False)),
            first_unresolved_hop=None if unresolved is None else HopKind(str(unresolved)),
            unresolved_node_id=str(payload.get("unresolved_node_id", "")),
        )


@dataclass(frozen=True)
class _Link:
    """One registered hop together with the two ids it was registered between."""

    hop: EvidenceHop
    derived_from: str
    derives: str


def independence_groups(
    observation_refs: Iterable[str],
    source_family_of: Mapping[str, str],
) -> tuple[tuple[str, ...], ...]:
    """Group observation refs by resolved source family (FR-034).

    Two captures of one wire story resolve to one family and therefore to one
    independent source, while remaining two publications. A ref with no resolved
    family is attributed to nobody: it groups under its own ref, so an
    unresolved observation is counted as itself rather than dropped or merged
    into a neighbour's family. Groups are ordered by first member and members
    are sorted, so the same inputs always give the same grouping.
    """
    by_family: dict[str, set[str]] = {}
    for ref in observation_refs:
        member = str(ref)
        family = str(source_family_of.get(member, "") or "")
        by_family.setdefault(family or member, set()).add(member)
    return tuple(
        sorted((tuple(sorted(members)) for members in by_family.values()), key=lambda g: g[0])
    )


class EvidenceGraph:
    """Typed adjacency over the evidence chain — pure, in-memory, I/O-free.

    Registration names both neighbours of a hop: ``forward`` is the id the hop is
    derived from, ``backward`` the id it derives. A lineage question is
    therefore answered from injected data alone, with no store or database
    behind it.
    """

    def __init__(self) -> None:
        self._links: list[_Link] = []
        self._seen: set[_Link] = set()
        self._derives: dict[str, list[_Link]] = {}
        self._derived_from: dict[str, list[_Link]] = {}

    def add_hop(self, hop: EvidenceHop, *, forward: str, backward: str) -> None:
        """Register one hop between the node it derives from and the one it derives.

        ``forward`` is ``""`` at the source end of the chain and ``backward`` is
        ``""`` at the relation end, which is what makes the two ends of the
        spine honest rather than dangling. Registering the same hop between the
        same two nodes again is a no-op, so a replayed build does not double a
        trace (I-11).
        """
        link = _Link(hop=hop, derived_from=str(forward), derives=str(backward))
        if link in self._seen:
            return
        self._seen.add(link)
        self._links.append(link)
        if link.derived_from:
            self._derived_from.setdefault(link.derived_from, []).append(link)
        if link.derives:
            self._derives.setdefault(link.derives, []).append(link)

    def backward(self, node_id: str) -> LineageTrace:
        """``relation → source``: the chain behind one node, in canonical order.

        The trace carries every hop after the subject, because the subject is
        the question already asked. It halts at the first hop kind it cannot
        resolve from the subject and names that kind as the gap (FR-033).
        """
        return self._walk(
            subject_id=node_id,
            direction="backward",
            steps=tuple((kind, True) for kind in BACKWARD_CHAIN[1:]),
            index=self._derives,
        )

    def forward(self, node_id: str) -> LineageTrace:
        """``source → relation``: every node this node produced, in chain order.

        One source captured twice yields two paths, both returned; each hop is
        stamped with the relation its own path derives, so every derived
        relation comes back with the assertion that grounds it (FR-032).
        """
        return self._walk(
            subject_id=node_id,
            direction="forward",
            steps=_FORWARD_STEPS,
            index=self._derived_from,
        )

    def independence_groups(
        self,
        observation_refs: Iterable[str],
        source_family_of: Mapping[str, str],
    ) -> tuple[tuple[str, ...], ...]:
        """The module-level grouping, for callers already holding a graph."""
        return independence_groups(observation_refs, source_family_of)

    def _walk(
        self,
        *,
        subject_id: str,
        direction: Literal["backward", "forward"],
        steps: tuple[tuple[HopKind, bool], ...],
        index: Mapping[str, list[_Link]],
    ) -> LineageTrace:
        """One depth-limited pass along ``steps``, halting at the first gap.

        Branching is kept rather than pruned: every link leaving the current
        frontier at the next kind is taken, hops are emitted in chain order, and
        the frontier only ever moves one step along the canonical order, so the
        walk terminates whatever the shape of the injected data.
        """
        reached: list[list[_Link]] = []
        frontier = (subject_id,)
        for kind, required in steps:
            links = self._resolve(index, frontier, kind)
            if not links:
                if required:
                    return LineageTrace(
                        subject_id=subject_id,
                        direction=direction,
                        hops=self._emit(reached, direction),
                        complete=False,
                        first_unresolved_hop=kind,
                        unresolved_node_id=sorted(frontier)[0],
                    )
                continue
            reached.append(links)
            frontier = tuple(sorted({link.hop.node_id for link in links}))
        return LineageTrace(
            subject_id=subject_id,
            direction=direction,
            hops=self._emit(reached, direction),
            complete=True,
        )

    @staticmethod
    def _resolve(
        index: Mapping[str, list[_Link]],
        frontier: tuple[str, ...],
        kind: HopKind,
    ) -> list[_Link]:
        """Every link of ``kind`` leaving the frontier, ordered for determinism."""
        links = [
            link
            for node_id in frontier
            for link in index.get(node_id, ())
            if link.hop.kind is kind
        ]
        return sorted(links, key=lambda link: link.hop.node_id)

    @staticmethod
    def _emit(
        reached: Sequence[Sequence[_Link]],
        direction: str,
    ) -> tuple[EvidenceHop, ...]:
        """Flatten the walked levels, grounding forward hops in their relation."""
        if direction == "forward":
            return _ground_forward(reached)
        return tuple(link.hop for links in reached for link in links)


def _ground_forward(reached: Sequence[Sequence[_Link]]) -> tuple[EvidenceHop, ...]:
    """Stamp each forward hop with the relation its own path derives (FR-032).

    A hop's relations are the relations reachable from it along the rest of the
    walk, so a source captured twice attributes each hop to the branch it came
    from rather than to the source. Where that set is a single relation the hop
    is stamped with it; where it is not, the registered value stands rather than
    a guess. The pass runs deepest level first, because a level is only known
    once the level it produces has been read.
    """
    relations: list[list[set[str]]] = [[set() for _ in links] for links in reached]
    for index in range(len(reached) - 1, -1, -1):
        later = reached[index + 1] if index + 1 < len(reached) else ()
        later_relations = relations[index + 1] if index + 1 < len(reached) else []
        for position, link in enumerate(reached[index]):
            if link.hop.kind is HopKind.RELATION:
                relations[index][position] = {link.hop.relation_id or link.hop.node_id}
                continue
            ids: set[str] = set()
            for offset, derived in enumerate(later):
                if derived.derived_from == link.hop.node_id:
                    ids |= later_relations[offset]
            relations[index][position] = ids
    stamped: list[EvidenceHop] = []
    for index, links in enumerate(reached):
        for position, link in enumerate(links):
            ids = relations[index][position]
            hop = link.hop
            if not hop.relation_id and len(ids) == 1:
                hop = replace(hop, relation_id=next(iter(ids)))
            stamped.append(hop)
    return tuple(stamped)
