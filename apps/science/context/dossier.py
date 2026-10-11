"""Dossier assembly: the one artefact an analyst actually reads.

Every upstream layer produces fragments — a profile of attribute states, a lifecycle
projection, a hypergraph fan, a list of asserted relations, a plan of outstanding work.
None of them is the answer. The analyst opens one screen and needs those fragments lined
up with the uncomfortable parts still visible, and this module is that lining-up. It is
deliberately the last place in the pipeline where a decision could hide, which is why it
resolves nothing.

Three rules decide the whole design:

**A fact without a source is not a fact, it is a guess.** Every lifecycle window, edge and
contact that reaches the dossier carries the refs it was derived from; anything that
arrives unsourced is dropped and *counted* in :attr:`CoverageView.untraced` rather than
silently absorbed. A dossier that quietly lost an unsourced edge reads as a dossier that
never had one, and the analyst's trust in the rest of the screen dies the first time it is
wrong. Keeping the item with an empty provenance list is the same lie with more markup.

**Contradictions are content, not noise.** A conflict enters as a :class:`Conflict`
carrying *every* side, never as a winner. Order-independent merging already lives in
``context.enrichment.merge_offer``; choosing a winner here would make the answer depend on
which source happened to be ingested last, the exact failure mode the five-state
``Coverage`` vocabulary exists to prevent.

**Nothing here knows what kind of thing it is looking at.** Contact kinds, relation names
and the subject's type label are data carried through from the profile and the asserted
relations, so one builder serves every entity type the platform admits — including ones
registered after this file was written.

Purity: stdlib plus the two modules that own the shapes being assembled. No clock, no
randomness, no network, no database, no control-plane imports. A dossier is a pure
function of its inputs, so the same inputs always render the same dossier and a diff
between two runs means something changed rather than that time passed.
"""

from __future__ import annotations

import enum
import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from domain.graph_invariant import GraphInvariant

from context.enrichment import Coverage, EnrichmentPlan, EntityProfile, Saturation

__all__ = [
    "CONTACT_PREFIX",
    "Conflict",
    "ConflictSide",
    "Contact",
    "ContactSet",
    "CoverageView",
    "Dossier",
    "DossierIdentity",
    "Gap",
    "Link",
    "LinkMap",
    "LinkOrigin",
    "TimelineEntry",
    "build_dossier",
]

#: Attribute-name prefix marking a profile attribute as a contact channel. The suffix is
#: the channel kind and is *data* (``email``, ``handle``, whatever a source offers) — the
#: builder never enumerates channel kinds, so a new one needs no change here.
CONTACT_PREFIX = "contact:"

#: Relation labels the builder mints for edges it computes rather than reads. They name
#: the shape of the evidence, not its subject.
ADJACENT_RELATION = "adjacent"
CO_MENTION_RELATION = "co_mentioned"

_PREFIX_LEN = 32


# --------------------------------------------------------------------------
# Edges — where they came from, because "linked" means different things
# --------------------------------------------------------------------------


class LinkOrigin(str, enum.Enum):
    """How the dossier came to believe an edge exists.

    The three origins are three different strengths of evidence, and an analyst who cannot
    tell them apart will read a co-mention as an observation:

    * ``OBSERVED`` — asserted by a relation record carrying that record's own source ref.
      The strongest thing here: somebody stated it and said where from.
    * ``DERIVED`` — aggregated from the subject's own per-window topology. True of the
      projection and traced to the stream it was folded from, but computed over windows
      rather than stated once.
    * ``CO_MENTION`` — implied by sharing a fan. The weakest: co-occurrence is evidence of
      *attention*, never of a relation, which is why fans stay hyperedges and never become
      identity (I-6).
    """

    OBSERVED = "observed"
    DERIVED = "derived"
    CO_MENTION = "co_mention"


@dataclass(frozen=True)
class Link:
    """One directed edge in the dossier's link map.

    ``source_refs`` is mandatory and non-empty: an edge that cannot name the record it came
    from is dropped by :func:`build_dossier` rather than rendered with an empty list. Two
    edges between the same pair under the same relation but with different origins are
    *kept as two edges* — merging them would have to pick a strength, and picking a
    strength silently is what this module exists to refuse.
    """

    source: str
    target: str
    relation: str
    origin: LinkOrigin
    weight: float = 1.0
    source_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "source", str(self.source))
        object.__setattr__(self, "target", str(self.target))
        object.__setattr__(self, "relation", str(self.relation))
        object.__setattr__(self, "origin", LinkOrigin(self.origin))
        object.__setattr__(self, "weight", float(self.weight))
        object.__setattr__(
            self, "source_refs", tuple(sorted({str(r) for r in self.source_refs if r}))
        )
        if not self.source or not self.target:
            raise ValueError("link requires both endpoints")
        if not self.relation:
            raise ValueError("link requires a relation")
        if not self.source_refs:
            raise ValueError("link requires at least one source ref (traceability, I-3)")

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "relation": self.relation,
            "origin": self.origin.value,
            "weight": self.weight,
            "source_refs": list(self.source_refs),
        }


@dataclass(frozen=True)
class LinkMap:
    """Nodes and edges of one subject's neighbourhood, evidence provenance intact.

    ``nodes`` includes the subject even with no edges: a dossier showing an isolated
    subject is showing the truth, whereas an empty node list reads as "we did not look".
    Edges sort by ``(source, target, relation, origin)`` and nodes lexically — both derived
    from content alone, so no run can reorder another run's output.
    """

    subject: str = ""
    nodes: tuple[str, ...] = ()
    edges: tuple[Link, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "nodes", tuple(sorted({str(n) for n in self.nodes if n})))
        object.__setattr__(
            self,
            "edges",
            tuple(sorted(self.edges, key=lambda e: (e.source, e.target, e.relation, e.origin
                                                    .value))),
        )

    @property
    def degree(self) -> int:
        """Neighbour count, excluding the subject itself."""
        return len({e.target for e in self.edges if e.target != self.subject})

    def of_origin(self, origin: LinkOrigin) -> tuple[Link, ...]:
        return tuple(e for e in self.edges if e.origin is origin)

    def as_dict(self) -> dict[str, Any]:
        return {
            "subject": self.subject,
            "nodes": list(self.nodes),
            "degree": self.degree,
            "edges": [e.as_dict() for e in self.edges],
        }


# --------------------------------------------------------------------------
# Timeline — the subject's windows, each traced to the stream it came from
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class TimelineEntry:
    """One lifecycle window as the dossier shows it.

    Built from a real ``TemporalSlice``: its own ``window_start``/``window_end``/``state``/
    ``event_count``, never re-derived here. ``source_refs`` are the invariant's own
    provenance anchors and are mandatory — a window nobody can trace is not shown, because
    a timeline with a hole in its sourcing must not look like a timeline with a hole in its
    coverage.

    ``coverage`` maps window occupancy onto the shared five-state vocabulary so the UI can
    colour a window without inventing a sixth state: a window holding events is
    ``ACQUIRED``; a dormant window is ``EMPTY`` — *we covered that period and there was
    nothing there*, positive evidence of absence, materially different from a period
    nobody looked at.
    """

    window_start: datetime
    window_end: datetime
    state: str
    event_count: int
    source_refs: tuple[str, ...]
    coverage: Coverage = Coverage.UNKNOWN

    def __post_init__(self) -> None:
        if self.window_end <= self.window_start:
            raise ValueError("timeline entry window_end must be after window_start")
        if self.event_count < 0:
            raise ValueError(f"event_count must be >= 0, got {self.event_count}")
        object.__setattr__(self, "state", str(self.state))
        object.__setattr__(
            self, "source_refs", tuple(sorted({str(r) for r in self.source_refs if r}))
        )
        object.__setattr__(self, "coverage", Coverage(self.coverage))
        if not self.source_refs:
            raise ValueError("timeline entry requires source refs (traceability, I-3)")

    @property
    def is_dormant(self) -> bool:
        return self.event_count == 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "window_start": self.window_start.isoformat(),
            "window_end": self.window_end.isoformat(),
            "state": self.state,
            "event_count": self.event_count,
            "coverage": self.coverage.value,
            "source_refs": list(self.source_refs),
        }


# --------------------------------------------------------------------------
# Contacts — every one carries the source it came from
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Contact:
    """One contact channel contributed by exactly one source.

    Two sources reporting the same channel produce two rows rather than one merged row:
    the count of distinct sources *is* the corroboration signal (``Saturation.corroborated``),
    so collapsing them here would destroy the evidence the UI has to display.
    """

    kind: str
    value: str
    source: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", str(self.kind))
        object.__setattr__(self, "value", str(self.value))
        object.__setattr__(self, "source", str(self.source))
        if not self.kind or not self.value:
            raise ValueError("contact requires a kind and a value")
        if not self.source:
            raise ValueError("contact requires a source (traceability, I-3)")

    def as_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "value": self.value, "source": self.source}


@dataclass(frozen=True)
class ContactSet:
    """Contacts grouped by channel kind, ordered from content.

    :attr:`by_type` returns a mapping rather than a tree of nested dataclasses because
    channel kinds are open data: the UI iterates whatever kinds arrived, in a stable order,
    without this module having to know them.
    """

    contacts: tuple[Contact, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "contacts", tuple(sorted(self.contacts, key=lambda c: (c.kind, c.value,
                                                                        c.source)))
        )

    @property
    def kinds(self) -> tuple[str, ...]:
        return tuple(sorted({c.kind for c in self.contacts}))

    def by_kind(self, kind: str) -> tuple[Contact, ...]:
        return tuple(c for c in self.contacts if c.kind == kind)

    @property
    def by_type(self) -> dict[str, tuple[Contact, ...]]:
        """Kind → contacts, deterministically ordered."""
        return {kind: self.by_kind(kind) for kind in self.kinds}

    def sources_for(self, kind: str, value: str) -> tuple[str, ...]:
        """Independent sources asserting this exact channel — the corroboration count."""
        return tuple(
            sorted({c.source for c in self.contacts if c.kind == kind and c.value == value})
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "kinds": list(self.kinds),
            "contacts": [c.as_dict() for c in self.contacts],
        }


# --------------------------------------------------------------------------
# Gaps and conflicts — the uncomfortable parts, kept
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Gap:
    """One attribute the dossier is missing, with where it could have come from.

    Copied from the ``EnrichmentPlan`` rather than recomputed, so the dossier can never
    report a gap list the planner would not schedule. ``blocked_sources`` are capabilities
    that exist but cannot run here — reported, never presented as something a retry fixes.
    """

    attribute: str
    candidate_sources: tuple[str, ...] = ()
    blocked_sources: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "attribute", str(self.attribute))
        object.__setattr__(
            self,
            "candidate_sources",
            tuple(sorted({str(s) for s in self.candidate_sources if s})),
        )
        object.__setattr__(
            self,
            "blocked_sources",
            tuple(sorted({str(s) for s in self.blocked_sources if s})),
        )
        if not self.attribute:
            raise ValueError("gap requires an attribute name")

    def as_dict(self) -> dict[str, Any]:
        return {
            "attribute": self.attribute,
            "candidate_sources": list(self.candidate_sources),
            "blocked_sources": list(self.blocked_sources),
        }


@dataclass(frozen=True)
class ConflictSide:
    """One side of a disagreement.

    ``sources`` is empty whenever the profile cannot say *which* source asserted which
    value — it keeps a flat value set plus a source set, so per-side attribution is
    genuinely unknown. An empty list is the honest outcome; inventing a pairing would
    produce a dossier that looks auditable and is not.
    """

    value: str
    sources: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", str(self.value))
        object.__setattr__(self, "sources", tuple(sorted({str(s) for s in self.sources
                                                          if s})))
        if not self.value:
            raise ValueError("conflict side requires a value")

    def as_dict(self) -> dict[str, Any]:
        return {"value": self.value, "sources": list(self.sources)}


@dataclass(frozen=True)
class Conflict:
    """A recorded contradiction with every side retained.

    ``sources`` is the union of sources that disagreed, ``sides`` the competing values. A
    conflict with no ``sides`` means the disagreement was reported but the individual
    values were not retained upstream; it is still shown, because hiding it *is* the silent
    resolution this module refuses to perform.
    """

    subject: str
    sides: tuple[ConflictSide, ...] = ()
    sources: tuple[str, ...] = ()
    note: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "subject", str(self.subject))
        object.__setattr__(self, "sides", tuple(sorted(self.sides, key=lambda s: s.value)))
        object.__setattr__(self, "sources", tuple(sorted({str(s) for s in self.sources if s})))
        object.__setattr__(self, "note", str(self.note))
        if not self.subject:
            raise ValueError("conflict requires a subject")

    @property
    def sides_known(self) -> bool:
        """Whether the competing values survived to this layer."""
        return bool(self.sides)

    def as_dict(self) -> dict[str, Any]:
        return {
            "subject": self.subject,
            "sides_known": self.sides_known,
            "sides": [s.as_dict() for s in self.sides],
            "sources": list(self.sources),
            "note": self.note,
        }


# --------------------------------------------------------------------------
# Coverage, identity, dossier
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class CoverageView:
    """How much of the dossier is actually backed, in the units the UI can show.

    Two independent axes, deliberately not collapsed into one number:

    * ``attributes`` is the planner's ``Saturation`` — how much of the expected attribute
      surface was attempted at all. ``None`` when no plan was supplied, which is materially
      worse than a plan that ran and found nothing, and is therefore *not* the same value
      as ``plan_known=True`` with zero gaps.
    * the traced/total counters are the traceability ledger. ``untraced`` counts items
      dropped for having no source and is reported rather than hidden, because an item
      silently removed is indistinguishable from an item never seen.
    """

    attributes: Saturation | None = None
    plan_known: bool = False
    traced_facts: int = 0
    total_facts: int = 0
    traced_edges: int = 0
    total_edges: int = 0
    traced_contacts: int = 0
    total_contacts: int = 0
    untraced_facts: int = 0
    untraced_edges: int = 0
    untraced_contacts: int = 0
    untraced_conflicts: int = 0
    #: Lifecycle windows with no event, kept out of the timeline because nobody swept them.
    #: Stated here rather than rendered, so the dossier never reads as fuller than it is.
    dormant_windows: int = 0

    @property
    def untraced(self) -> int:
        """Items discarded for want of a source, across every section."""
        return (
            self.untraced_facts
            + self.untraced_edges
            + self.untraced_contacts
            + self.untraced_conflicts
        )

    @property
    def is_traceable(self) -> bool:
        """Whether nothing was dropped, i.e. the dossier shows all it was given."""
        return self.untraced == 0

    @property
    def traced_ratio(self) -> float:
        seen = self.total_facts + self.total_edges + self.total_contacts
        if seen == 0:
            return 1.0
        kept = self.traced_facts + self.traced_edges + self.traced_contacts
        return kept / seen

    def as_dict(self) -> dict[str, Any]:
        return {
            "plan_known": self.plan_known,
            "attributes": self.attributes.as_dict() if self.attributes else None,
            "traced_facts": self.traced_facts,
            "total_facts": self.total_facts,
            "traced_edges": self.traced_edges,
            "total_edges": self.total_edges,
            "traced_contacts": self.traced_contacts,
            "total_contacts": self.total_contacts,
            "dormant_windows": self.dormant_windows,
        "untraced_facts": self.untraced_facts,
            "untraced_edges": self.untraced_edges,
            "untraced_contacts": self.untraced_contacts,
            "untraced_conflicts": self.untraced_conflicts,
            "untraced_total": self.untraced,
            "is_traceable": self.is_traceable,
            "traced_ratio": round(self.traced_ratio, 4),
        }


@dataclass(frozen=True)
class DossierIdentity:
    """Who the dossier is about, anchored to the stream that established them.

    ``stream_anchor`` and ``revision`` come from the invariant when one was supplied and
    are empty/zero otherwise: a dossier built without a projection still has a subject
    (the profile's ref) but must not claim a stream position it does not have.
    """

    entity_ref: str
    type_label: str = ""
    stream_anchor: str = ""
    revision: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "entity_ref", str(self.entity_ref))
        object.__setattr__(self, "type_label", str(self.type_label))
        object.__setattr__(self, "stream_anchor", str(self.stream_anchor))
        if not self.entity_ref:
            raise ValueError("dossier requires an entity_ref (identity must come from "
                             "somewhere, I-3)")

    def as_dict(self) -> dict[str, Any]:
        return {
            "entity_ref": self.entity_ref,
            "type_label": self.type_label,
            "stream_anchor": self.stream_anchor,
            "revision": self.revision,
        }


@dataclass(frozen=True)
class Dossier:
    """The assembled view of one subject: identity, timeline, links, contacts, coverage,
    gaps and conflicts.

    :attr:`is_complete` is the property the UI must not invent for itself: complete means
    every section is traced, the planner ran, and nothing is missing or contradicted. A
    dossier with no data at all reports ``is_complete=False`` and an empty coverage —
    silence about ignorance is the one presentation this module refuses to produce.
    """

    identity: DossierIdentity
    timeline: tuple[TimelineEntry, ...] = ()
    links: LinkMap = LinkMap()
    contacts: ContactSet = ContactSet()
    coverage: CoverageView = CoverageView()
    gaps: tuple[Gap, ...] = ()
    conflicts: tuple[Conflict, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "timeline",
            tuple(sorted(self.timeline, key=lambda e: (e.window_start, e.window_end, e.state))),
        )
        object.__setattr__(self, "gaps", tuple(sorted(self.gaps, key=lambda g: g.attribute)))
        object.__setattr__(
            self, "conflicts", tuple(sorted(self.conflicts, key=lambda c: c.subject))
        )

    @property
    def is_empty(self) -> bool:
        """No evidence of any kind. Not the same as *complete*: emptiness needs a plan."""
        return not self.timeline and not self.links.edges and not self.contacts.contacts

    @property
    def has_work(self) -> bool:
        return bool(self.gaps)

    @property
    def is_complete(self) -> bool:
        return (
            not self.gaps
            and not self.conflicts
            and self.coverage.is_traceable
            and self.coverage.plan_known
        )

    @property
    def integrity_digest(self) -> str:
        """sha256 over the canonical dossier body.

        Content-addressed like every other identifier here: the same inputs render a
        byte-identical dossier, so two analysts comparing runs compare content rather than
        timestamps. The body excludes ``dossier_id`` itself — a digest over a document that
        contains the digest never terminates.
        """
        return hashlib.sha256(_canonical_json(self._body()).encode("utf-8")).hexdigest()

    @property
    def dossier_id(self) -> str:
        return f"DS-{self.integrity_digest[:_PREFIX_LEN]}"

    def _body(self) -> dict[str, Any]:
        """The dossier's own content, in a fixed key order."""
        return {
            "identity": self.identity.as_dict(),
            "is_empty": self.is_empty,
            "is_complete": self.is_complete,
            "timeline": [e.as_dict() for e in self.timeline],
            "links": self.links.as_dict(),
            "contacts": self.contacts.as_dict(),
            "coverage": self.coverage.as_dict(),
            "gaps": [g.as_dict() for g in self.gaps],
            "conflicts": [c.as_dict() for c in self.conflicts],
        }

    def as_dict(self) -> dict[str, Any]:
        return {"dossier_id": self.dossier_id, **self._body()}


# --------------------------------------------------------------------------
# Canonicalisation + duck-typed record access
# --------------------------------------------------------------------------


def _canonical(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _canonical(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, (list, tuple)):
        return [_canonical(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, enum.Enum):
        return value.value
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def _canonical_json(data: Any) -> str:
    return json.dumps(_canonical(data), sort_keys=True, separators=(",", ":"))


def _field(record: Any, *names: str) -> Any:
    """First present key/attribute among ``names``.

    Relations and fan mentions arrive from several producers — projection rows, admitted
    events, hand-built fixtures — that agree on meaning but not on field spelling. Reading
    the first present name keeps the dossier decoupled from any one of them instead of
    forcing a conversion layer that would quietly drop fields the dossier cannot see.
    """
    for name in names:
        if isinstance(record, Mapping):
            if name in record and record[name] is not None:
                return record[name]
            continue
        value = getattr(record, name, None)
        if value is not None:
            return value
    return None


def _provenance_refs(invariant: GraphInvariant | None) -> tuple[str, ...]:
    """The refs a fact derived from this invariant must cite.

    The genesis stream anchor (the subject's position in its stream), the projection's
    chain tip, and the observation anchors the stream was fed from. Empty when the
    invariant carries no provenance at all — and empty means *nothing derived from it is
    traceable*, the honest outcome for a projection nobody wrote provenance onto.
    """
    if invariant is None:
        return ()
    refs: set[str] = set()
    anchor = invariant.identity.stream_anchor
    if anchor:
        refs.add(str(anchor))
    head = invariant.provenance.event_id or invariant.provenance.stream_head
    if head:
        refs.add(str(head))
    refs.update(str(a) for a in invariant.evidence.observation_anchors if a)
    return tuple(sorted(refs))


# --------------------------------------------------------------------------
# Section builders
# --------------------------------------------------------------------------


def _build_timeline(
    invariant: GraphInvariant | None, refs: tuple[str, ...]
) -> tuple[tuple[TimelineEntry, ...], int, int, int]:
    """Timeline from the invariant's lifecycle windows -> (entries, traced, untraced, dormant).

    Only windows that hold an event become rows. A window grid is derived from the span
    between the events we happened to observe, so with a 7-day window and a registration date
    from 1995 it produces 1627 windows -- and rendering 1626 of them as ``DORMANT`` would claim
    the platform watched every week of the last thirty-one years. It did not. Absence of an
    event inside a span nobody swept is an unknown, not evidence, so it is counted as
    ``dormant`` and left out of the timeline rather than dressed up as a finding.

    The count is returned and surfaced in the coverage ledger, so the omission is stated
    rather than performed.
    """
    if invariant is None:
        return (), 0, 0, 0
    slices = invariant.lifecycle.slices
    dormant = sum(1 for window in slices if window.event_count == 0)
    if not refs:
        return (), 0, len(slices), dormant
    entries = tuple(
        TimelineEntry(
            window_start=window.window_start,
            window_end=window.window_end,
            state=window.state.value,
            event_count=window.event_count,
            source_refs=refs,
            coverage=Coverage.ACQUIRED,
        )
        for window in slices
        if window.event_count > 0
    )
    return entries, len(entries), 0, dormant


def _derived_edges(
    subject: str, invariant: GraphInvariant | None, refs: tuple[str, ...]
) -> tuple[tuple[Link, ...], int]:
    """Edges aggregated from the invariant's own per-window adjacency.

    Weights sum across windows, an aggregation and therefore ``DERIVED`` rather than
    ``OBSERVED``: the projection never saw one asserted edge, it folded per-window
    neighbour hints into a number.
    """
    if invariant is None or not refs:
        return (), 0
    weights: dict[str, float] = {}
    for window in invariant.topology.window_topology:
        for neighbour, weight in window.neighbor_weights:
            if neighbour == subject or not neighbour:
                continue
            weights[neighbour] = weights.get(neighbour, 0.0) + float(weight)
    edges = tuple(
        Link(
            source=subject,
            target=neighbour,
            relation=ADJACENT_RELATION,
            origin=LinkOrigin.DERIVED,
            weight=weights[neighbour],
            source_refs=refs,
        )
        for neighbour in sorted(weights)
    )
    return edges, 0


def _observed_edges(
    subject: str, relations: Iterable[Any], fallback_refs: tuple[str, ...]
) -> tuple[tuple[Link, ...], int]:
    """Edges read from asserted relation records.

    A relation may carry its own ``source_ref``; when it does not, the subject's stream
    refs stand in — an edge asserted inside a known stream is traceable to that stream. A
    relation with neither is dropped and counted, because an edge of unknown provenance is
    exactly the item that turns a link map into fiction.
    """
    edges: list[Link] = []
    untraced = 0
    for record in relations:
        target = str(_field(record, "target", "target_id", "neighbor", "node_id") or "")
        relation = str(_field(record, "relation", "predicate", "edge_type") or "")
        if not target or not relation:
            untraced += 1
            continue
        declared = _field(record, "source_ref", "source", "ref")
        refs = (str(declared),) if declared else fallback_refs
        if not refs:
            untraced += 1
            continue
        weight = _field(record, "weight", "score")
        origin = _field(record, "origin")
        edges.append(
            Link(
                source=subject,
                target=target,
                relation=relation,
                origin=LinkOrigin(origin) if origin else LinkOrigin.OBSERVED,
                weight=float(weight) if weight is not None else 1.0,
                source_refs=refs,
            )
        )
    return tuple(edges), untraced


def _co_mention_edges(
    subject: str, mentions: Sequence[Any], fan: Mapping[Sequence[str], Any] | None
) -> tuple[tuple[Link, ...], int]:
    """Edges implied by co-mention fans, one per other member that shares a page.

    Fans are N-ary hyperedges, so the edge drawn here joins the subject to another member
    of the same fan and asserts nothing about their relationship — which is why the origin
    stays ``CO_MENTION`` and the relation name is deliberately bland.

    A fan may also arrive pre-aggregated (``CoMentionFanBuilder.fans`` output: members
    tuple → count). Such an aggregate carries no page, hence no source ref, so a group
    known only from ``fan`` is dropped and counted rather than rendered as an unsourced
    neighbour. When both a page mention and an aggregate describe the same group, the
    aggregate sets the weight: it is the upstream summary, and recounting it here would let
    the renderer disagree with the producer whose number the analyst is reading.
    """
    pages: dict[tuple[str, ...], set[str]] = {}
    counted: dict[tuple[str, ...], int] = {}
    for mention in mentions:
        other = str(_field(mention, "entity_id", "entity_ref") or "")
        if not other or other == subject:
            continue
        page = str(_field(mention, "page_url", "source_uri", "page") or "")
        amount = _field(mention, "mention_count", "count", "weight")
        count = max(int(amount), 0) if amount is not None else 1
        group = tuple(sorted({subject, other}))
        pages.setdefault(group, set()).add(page)
        counted[group] = counted.get(group, 0) + count
    aggregates = {
        tuple(sorted(str(member) for member in members)): count
        for members, count in (fan or {}).items()
    }

    edges: list[Link] = []
    untraced = 0
    for group in sorted(set(pages) | set(aggregates)):
        refs = tuple(sorted(pages.get(group, set())))
        weight = float(aggregates.get(group, counted.get(group, 0)))
        if not refs:
            untraced += 1
            continue
        edges.append(
            Link(
                source=subject,
                target=group[1] if group[0] == subject else group[0],
                relation=CO_MENTION_RELATION,
                origin=LinkOrigin.CO_MENTION,
                weight=weight,
                source_refs=refs,
            )
        )
    return tuple(edges), untraced


def _build_contacts(profile: EntityProfile) -> tuple[tuple[Contact, ...], int]:
    """Contacts from ``contact:<kind>`` profile attributes → (contacts, untraced).

    One row per (value, source), which is only sound when every contributing source agreed
    on the whole value set — that is what ``ACQUIRED`` means. A ``CONFLICT`` state cannot be
    decomposed per source (the profile holds a flat value set plus a source set, not a
    value→source pairing), so its values are *not* turned into attributed contact rows: the
    cross product would invent four attributions out of two facts. Those values stay visible
    in ``dossier.conflicts``, and the dropped rows are counted. Likewise a value with no
    source behind it is dropped: a contact nobody can attribute is not usable evidence, and
    rendering it beside attributed ones would overstate what is known.
    """
    contacts: list[Contact] = []
    untraced = 0
    for name in sorted(profile.attributes):
        if not name.startswith(CONTACT_PREFIX):
            continue
        state = profile.attributes[name]
        kind = name[len(CONTACT_PREFIX):] or "unspecified"
        for value in state.values:
            if not value:
                continue
            if not state.sources or state.coverage is Coverage.CONFLICT:
                untraced += 1
                continue
            contacts.extend(Contact(kind=kind, value=value, source=source)
                            for source in sorted(set(state.sources)))
    return tuple(contacts), untraced


def _build_gaps(plan: EnrichmentPlan | None) -> tuple[Gap, ...]:
    """Gaps copied from the plan.

    No plan means no gaps — and the dossier says so through ``coverage.plan_known``, since
    an un-run planner is not a planner that found nothing. Conflating them is how an engine
    reports itself finished while holding nothing.
    """
    if plan is None:
        return ()
    return tuple(
        Gap(
            attribute=gap.attribute,
            candidate_sources=gap.candidate_sources,
            blocked_sources=gap.blocked_sources,
        )
        for gap in plan.gaps
    )


def _build_conflicts(
    profile: EntityProfile, plan: EnrichmentPlan | None
) -> tuple[tuple[Conflict, ...], int]:
    """Conflicts from ``CONFLICT`` attributes plus plan-reported ones → (list, untraced).

    ``merge_offer`` already made conflict detection symmetric and order-independent, so
    this layer only reports: every competing value becomes a side and none wins. A conflict
    whose sources cannot be named is dropped rather than shown ungrounded; a conflict the
    *plan* reports but the profile no longer holds is shown with no sides, because a
    disagreement we cannot detail is weaker evidence, not absent evidence.
    """
    conflicts: dict[str, Conflict] = {}
    untraced = 0
    for name in sorted(profile.attributes):
        state = profile.attributes[name]
        if state.coverage is not Coverage.CONFLICT:
            continue
        if not state.sources:
            untraced += 1
            continue
        conflicts[name] = Conflict(
            subject=name,
            sides=tuple(ConflictSide(value=value) for value in sorted(set(state.values))),
            sources=state.sources,
            note=state.note or "sources disagree",
        )
    for name in sorted(plan.conflicts if plan else ()):
        conflicts.setdefault(
            name,
            Conflict(
                subject=name,
                sides=(),
                sources=(),
                note="disagreement reported by the plan; competing values not retained",
            ),
        )
    return tuple(conflicts[name] for name in sorted(conflicts)), untraced


# --------------------------------------------------------------------------
# The builder
# --------------------------------------------------------------------------


def build_dossier(
    entity: EntityProfile,
    *,
    invariant: GraphInvariant | None = None,
    mentions: Sequence[Any] = (),
    relations: Sequence[Any] = (),
    fan: Mapping[Sequence[str], Any] | None = None,
    plan: EnrichmentPlan | None = None,
) -> Dossier:
    """Assemble the dossier for one subject from whatever fragments exist.

    Everything except the profile is optional, because a dossier is required even when it
    has nothing to show: the empty dossier is the artefact that proves the platform looked
    and found nothing, which is a different claim from having no artefact at all.

    * ``invariant`` — the lifecycle/topology projection. ``lifecycle.slices`` becomes the
      timeline verbatim (real ``window_start``/``window_end``/``state``/``event_count``
      fields, never re-derived here) and ``topology.window_topology`` becomes ``DERIVED``
      edges.
    * ``mentions`` — co-mention records (``entity_id``/``page_url``/``mention_count``); the
      page url is the edge's source ref.
    * ``fan`` — pre-aggregated fan counts (members tuple → count). Groups known only from
      a fan are dropped and counted: an aggregate has no page, so it has no source to cite.
    * ``relations`` — asserted edges, duck-typed on ``target``/``relation`` with optional
      ``weight``, ``origin`` and ``source_ref``.
    * ``plan`` — the ``EnrichmentPlan``: gaps are copied verbatim and its conflict names are
      merged with the profile's, so the dossier can never claim a different gap list than
      the planner would schedule.

    Pure and deterministic: identical inputs render a byte-identical ``as_dict``. The
    subject is ``entity.entity_ref``; a profile without one is rejected, because identity
    must come from somewhere.
    """
    if entity is None or not getattr(entity, "entity_ref", ""):
        raise ValueError("build_dossier requires a profile carrying an entity_ref (I-3)")

    subject = str(entity.entity_ref)
    type_label = str(entity.type_label or "")
    stream_anchor = ""
    revision = 0
    if invariant is not None:
        stream_anchor = invariant.identity.stream_anchor
        revision = invariant.identity.revision
        type_label = type_label or invariant.identity.type_label

    refs = _provenance_refs(invariant)

    timeline, traced_facts, untraced_facts, dormant = _build_timeline(invariant, refs)
    derived, derived_untraced = _derived_edges(subject, invariant, refs)
    observed, observed_untraced = _observed_edges(subject, relations, refs)
    co_mentioned, co_untraced = _co_mention_edges(subject, mentions, fan)
    edges = derived + observed + co_mentioned
    contacts, untraced_contacts = _build_contacts(entity)
    conflicts, untraced_conflicts = _build_conflicts(entity, plan)

    coverage = CoverageView(
        attributes=plan.saturation if plan else None,
        plan_known=plan is not None,
        traced_facts=traced_facts,
        total_facts=len(timeline),
        dormant_windows=dormant,
        traced_edges=len(edges),
        total_edges=len(edges) + derived_untraced + observed_untraced + co_untraced,
        traced_contacts=len(contacts),
        total_contacts=len(contacts) + untraced_contacts,
        untraced_facts=untraced_facts,
        untraced_edges=derived_untraced + observed_untraced + co_untraced,
        untraced_contacts=untraced_contacts,
        untraced_conflicts=untraced_conflicts,
    )

    return Dossier(
        identity=DossierIdentity(
            entity_ref=subject,
            type_label=type_label,
            stream_anchor=stream_anchor,
            revision=revision,
        ),
        timeline=timeline,
        links=LinkMap(
            subject=subject,
            nodes=tuple({subject, *(edge.target for edge in edges)}),
            edges=edges,
        ),
        contacts=ContactSet(contacts),
        coverage=coverage,
        gaps=_build_gaps(plan),
        conflicts=conflicts,
    )