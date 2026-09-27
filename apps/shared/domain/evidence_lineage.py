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

Both directions are entry-point-agnostic. :meth:`EvidenceGraph.backward` walks up
from wherever it is asked, and :meth:`EvidenceGraph.forward` walks down from
*wherever it is asked*: a source, a capture, an observation, a segment, a mention,
a candidate, an assertion, a relation or an entity. The forward step sequence is
derived from the kind of the node the walk starts at (see
:data:`FORWARD_CHAIN`) rather than from a fixed tuple that assumes a source root,
because an observation sits *mid-chain* and asking to walk forward from one is a
question about direction, not a report of a defect.

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
    "FORWARD_CHAIN",
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

#: The whole evidence chain, origin to apex. The forward counterpart of
#: :data:`BACKWARD_CHAIN`, and the single source of truth for the forward step
#: sequence: a walk that starts at kind ``K`` traverses exactly the entries that
#: come *after* ``K`` here, which is what makes a walk startable at any node
#: instead of only at a source.
FORWARD_CHAIN: tuple[HopKind, ...] = (
    HopKind.SOURCE,
    HopKind.CAPTURE,
    HopKind.OBSERVATION,
    HopKind.SEGMENT,
    HopKind.MENTION,
    HopKind.CANDIDATE,
    HopKind.ASSERTION,
    HopKind.RELATION,
    HopKind.ENTITY,
)

# (kind, required): an absent required hop ends the trace and names the gap, an
# absent optional hop is skipped so a chain that never had one still completes.
#
# Requiredness is a property of the *ladder*, not of the walk's origin, and that is
# the whole answer to what a mid-chain start does to these flags: a required step
# means "the chain does not skip this kind", which is a statement about the ladder
# that is equally true whether the walk arrived from below or began here. Starting at
# an OBSERVATION, a missing SEGMENT is still a gap — the observation reached a
# mention without the segment that must sit between them — so SEGMENT stays
# required. What the origin changes is only *where the walk enters the ladder*: the
# start node's own kind is consumed by being the subject, never looked up as a step.
# That is the one flag that would have been wrong, and it is wrong only in a
# source-rooted ladder, which is why the source-relative tuple below is derived
# rather than written out.
#
# Only CANDIDATE and ENTITY are optional, for the ladder's own reasons: a mention may
# be promoted straight to an assertion, and a relation need not have a resolved
# entity in this vocabulary. The spine is otherwise mandatory, and that is what
# makes an unresolved hop a defect report rather than a stylistic gap.
_OPTIONAL_HOP_KINDS: frozenset[HopKind] = frozenset({HopKind.CANDIDATE, HopKind.ENTITY})

_CHAIN_STEPS: tuple[tuple[HopKind, bool], ...] = tuple(
    (kind, kind not in _OPTIONAL_HOP_KINDS) for kind in FORWARD_CHAIN
)

#: The forward ladder as seen from a source: every step after SOURCE. Kept as a
#: named module constant because it is the shape ``forward`` is contractually
#: specified against, and it is defined *from* :data:`FORWARD_CHAIN` so a source
#: walk and a mid-chain walk cannot drift apart.
_FORWARD_STEPS: tuple[tuple[HopKind, bool], ...] = _CHAIN_STEPS[1:]


def _forward_steps_from(start: HopKind | None) -> tuple[tuple[HopKind, bool], ...]:
    """The ladder strictly after ``start``; the source-relative ladder for ``None``.

    Deriving the sequence from the start kind is the whole fix: an observation is
    mid-chain, so its walk begins at SEGMENT and a capture hop is never requested of
    it. A start of ``HopKind.ENTITY`` yields an empty sequence, which walks to a
    complete empty trace — an entity is the apex of the vocabulary, so nothing is
    derived from it and the ladder above it is genuinely exhausted rather than
    missing.

    ``None`` is the start kind of a node the graph never registered a hop for, and
    the source-relative ladder is the answer that cannot be wrong: it asks for the
    first thing a forward walk from the origin needs, finds nothing, and returns
    ``complete=False`` naming ``capture`` as the gap. The result is marked, not
    silent, and it is what an unregistered node has always reported.
    """
    if start is None:
        return _FORWARD_STEPS
    if start not in FORWARD_CHAIN:
        raise ValueError(
            f"hop kind {start!r} is not part of FORWARD_CHAIN; a forward walk cannot "
            f"start there, and answering anyway would be a silent wrong answer"
        )
    return _CHAIN_STEPS[FORWARD_CHAIN.index(start) + 1 :]


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

    Both traversals accept any node as their subject, and the kind of the subject
    is what the walk derives its remaining steps from — see
    :meth:`EvidenceGraph.forward` and :data:`FORWARD_CHAIN`.
    """

    def __init__(self) -> None:
        self._links: list[_Link] = []
        self._seen: set[_Link] = set()
        self._derives: dict[str, list[_Link]] = {}
        self._derived_from: dict[str, list[_Link]] = {}
        self._node_kinds: dict[str, set[HopKind]] = {}

    def add_hop(self, hop: EvidenceHop, *, forward: str, backward: str) -> None:
        """Register one hop between the node it derives from and the one it derives.

        ``forward`` is ``""`` at the source end of the chain and ``backward`` is
        ``""`` at the relation end, which is what makes the two ends of the spine
        honest rather than dangling. Registering the same hop between the same two
        nodes again is a no-op, so a replayed build does not double a trace (I-11).
        """
        link = _Link(hop=hop, derived_from=str(forward), derives=str(backward))
        if link in self._seen:
            return
        self._seen.add(link)
        self._links.append(link)
        self._node_kinds.setdefault(hop.node_id, set()).add(hop.kind)
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

    def forward(self, node_id: str, *, kind: HopKind | None = None) -> LineageTrace:
        """``source → relation``, or any node → whatever it produced (FR-032).

        The step sequence is derived from the kind of ``node_id`` rather than fixed
        to a source root, so the walk starts wherever the caller is standing:
        ``forward(source)``, ``forward(capture)``, ``forward(observation)``,
        ``forward(segment)``, ``forward(mention)``, ``forward(candidate)``,
        ``forward(assertion)``, ``forward(relation)`` and ``forward(entity)`` are all
        legal and all correct. The subject's own kind is consumed by being the
        subject, so a walk from an observation never asks for a capture hop of it and
        never reports one unresolved.

        One source captured twice yields two paths, both returned; each hop is stamped
        with the relation its own path derives, so every derived relation comes back
        with the assertion that grounds it (FR-032). ``forward(source)`` is
        unchanged by this and is asserted byte-identical against the pre-change
        behaviour, because ``_FORWARD_STEPS`` is derived from :data:`FORWARD_CHAIN`
        rather than written out beside it.

        ``kind`` declares the start kind for a node the graph holds no registered hop
        for, and is coerced through :class:`HopKind` so an unknown value raises
        instead of being treated as some kind. Omitted, the start kind is read from
        the kinds the node was registered under, lowest in the chain first so a
        malformed node registered twice is walked conservatively and reports the gap
        rather than silently skipping hops. A node registered under no kind at all is
        answered with the source-relative ladder and a ``complete=False`` trace naming
        the first hop it could not resolve — marked, not silent, and unchanged.
        """
        return self._walk(
            subject_id=node_id,
            direction="forward",
            steps=_forward_steps_from(self._start_kind(node_id, kind)),
            index=self._derived_from,
        )

    def _start_kind(self, node_id: str, declared: HopKind | None) -> HopKind | None:
        """The kind a forward walk starts at, or ``None`` when it cannot be known.

        A declared kind wins over the registry: the caller asserting the kind is
        claiming to know more about the node than the graph does. Otherwise the
        lowest registered kind is chosen, because the lower a walk enters the ladder
        the more steps it must traverse, and a walk that is forced to traverse more
        steps can only ever report a gap — never skip one.
        """
        if declared is not None:
            return HopKind(declared)
        registered = self._node_kinds.get(node_id)
        if not registered:
            return None
        return min(registered, key=FORWARD_CHAIN.index)

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
