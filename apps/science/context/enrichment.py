"""Entity enrichment: what is known, what was tried, and what is still missing (spec 026).

The platform's job for an entity inside a context is not to answer the question once. It is
to keep pulling until there is nothing left to pull, and to be exact about the difference
between "we asked and there was nothing", "we could not ask", and "we did not think to ask".

That distinction is the whole module. ``Coverage`` has five states because collapsing any of
them produces a confident wrong answer:

* ``UNKNOWN`` — nobody tried. This is a *gap*, and it is the only state that generates work.
* ``ACQUIRED`` — a source returned a value.
* ``EMPTY`` — a source ran and reported no such attribute. Different from ``UNKNOWN``:
  positive evidence of absence.
* ``REFUSED`` — the capability exists but cannot run (no credential, no binary, wrong host).
  Not a gap: retrying the same thing forever is the failure mode this state exists to stop.
* ``CONFLICT`` — sources disagree. Recorded as both values; never resolved by arrival order,
  because last-write-wins makes the answer depend on ingestion order.

**Capabilities are data, not code.** :class:`CapabilityOffer` is what a source declares it
can produce for which entity kinds. A source the platform has never heard of is still
enrichable: it registers an offer and the planner picks it up. Nothing in this module names a
domain, an attribute, or a vendor — that is what makes the same code enrich a person, a domain,
an organisation and a CVE.

**Determinism.** Every ordering is derived from sorted content, so the same offers and the
same observed attributes always yield the same plan. A gap list that shuffles between runs
cannot be diffed, and an analyst cannot tell a real change from noise.
"""

from __future__ import annotations

import enum
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "AttributeGap",
    "AttributeState",
    "CapabilityOffer",
    "Coverage",
    "EnrichmentPlan",
    "EntityProfile",
    "Saturation",
    "merge_offer",
    "plan_enrichment",
]


class Coverage(str, enum.Enum):
    """What we know about one attribute of one entity."""

    #: Nobody attempted this. The only state that produces work.
    UNKNOWN = "unknown"
    #: A source returned at least one value.
    ACQUIRED = "acquired"
    #: A source ran and reported no such attribute. Positive evidence of absence.
    EMPTY = "empty"
    #: The capability exists but cannot run here (credential, binary, host).
    REFUSED = "refused"
    #: Sources disagree. Both values are kept.
    CONFLICT = "conflict"

    @property
    def is_resolved(self) -> bool:
        """Whether more attempts could change what we believe."""
        return self in (Coverage.ACQUIRED, Coverage.EMPTY, Coverage.CONFLICT)

    @property
    def needs_work(self) -> bool:
        """Whether the planner should schedule this attribute.

        ``CONFLICT`` deliberately does not qualify. Re-running a source that already
        disagreed resolves nothing on its own; a conflict needs a discriminating test, which
        is a different primitive.
        """
        return self is Coverage.UNKNOWN


@dataclass(frozen=True, slots=True)
class CapabilityOffer:
    """What one source declares it can produce.

    Declared by the source, consumed as data (spec 024 §4.7). ``entity_kinds`` and
    ``attributes`` are both open: a source may offer ``certificate`` for ``domain``, and the
    platform need not have an opinion about what a certificate is to schedule the fetch.
    """

    source_id: str
    entity_kinds: tuple[str, ...]
    attributes: tuple[str, ...]
    cost_class: str = "cheap"
    #: ``passive`` / ``polite`` / ``intrusive`` -- how much this touches the target.
    contact: str = "passive"
    #: Environment variable holding the credential, empty when none is needed.
    key_env: str = ""
    #: Local binary this needs, empty when it is an HTTP source.
    binary: str = ""
    os_requirement: str = "any"

    @property
    def runnable(self) -> bool:
        """Whether this offer could execute in the current environment, all else equal."""
        if self.binary:
            return False
        if self.key_env:
            return True  # resolvable; the planner reports REFUSED when it is absent
        return True

    def applies_to(self, kind: str) -> bool:
        """Whether the offer covers an entity kind.

        An offer with no declared kinds applies to everything. That default is
        deliberate: a source that names no kinds is claiming to be general, and making it
        re-declare per kind would make new entity types silently under-enriched.
        """
        return not self.entity_kinds or kind in self.entity_kinds


@dataclass
class AttributeState:
    """One attribute of one entity, with everything known about it."""

    name: str
    values: tuple[str, ...] = ()
    coverage: Coverage = Coverage.UNKNOWN
    #: Sources that contributed, sorted.
    sources: tuple[str, ...] = ()
    #: Why it is ``REFUSED`` / ``EMPTY``, for the analyst's benefit.
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "values": list(self.values),
            "coverage": self.coverage.value,
            "sources": list(self.sources),
            "note": self.note,
        }


@dataclass(frozen=True, slots=True)
class AttributeGap:
    """One attribute worth fetching, and the offers that could deliver it."""

    entity_ref: str
    attribute: str
    candidate_sources: tuple[str, ...]
    #: Sources that exist but cannot run. Reported, never scheduled.
    blocked_sources: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "entity_ref": self.entity_ref,
            "attribute": self.attribute,
            "candidate_sources": list(self.candidate_sources),
            "blocked_sources": list(self.blocked_sources),
        }


@dataclass(frozen=True, slots=True)
class Saturation:
    """How much of an entity is covered, and by what measure.

    ``n_eff`` is the independent-source count from ADR-0036, carried next to the raw
    count: ten copies of one feed is one source, and a UI that shows "10 sources" for a
    syndicated story is lying in a way no analyst forgives.
    """

    total_attributes: int
    acquired: int
    empty: int
    conflict: int
    unknown: int
    refused: int
    #: How many of the acquired attributes rest on more than one independent source.
    corroborated: int
    distinct_sources: int

    @property
    def resolved(self) -> int:
        return self.acquired + self.empty + self.conflict

    @property
    def ratio(self) -> float:
        if self.total_attributes == 0:
            return 1.0
        return self.resolved / self.total_attributes

    @property
    def is_saturated(self) -> bool:
        """Saturated means nothing is left to *attempt*.

        Not the same as complete: a profile whose every attribute came from one source is
        saturated and thinly evidenced, and the two facts are reported together so the UI
        cannot present one as the other.
        """
        return self.unknown == 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "total": self.total_attributes,
            "acquired": self.acquired,
            "empty": self.empty,
            "conflict": self.conflict,
            "unknown": self.unknown,
            "refused": self.refused,
            "corroborated": self.corroborated,
            "distinct_sources": self.distinct_sources,
            "ratio": round(self.ratio, 4),
            "saturated": self.is_saturated,
        }


@dataclass(frozen=True, slots=True)
class EnrichmentPlan:
    """What to do next about one entity."""

    entity_ref: str
    gaps: tuple[AttributeGap, ...] = ()
    saturation: Saturation | None = None
    #: Attributes that conflict, surfaced rather than hidden behind a single value.
    conflicts: tuple[str, ...] = ()

    @property
    def has_work(self) -> bool:
        return bool(self.gaps)

    def as_dict(self) -> dict[str, Any]:
        return {
            "entity_ref": self.entity_ref,
            "gaps": [g.as_dict() for g in self.gaps],
            "conflicts": list(self.conflicts),
            "saturation": self.saturation.as_dict() if self.saturation else None,
        }


@dataclass
class EntityProfile:
    """Everything the platform knows about one entity, attribute by attribute."""

    entity_ref: str
    type_label: str = ""
    attributes: dict[str, AttributeState] = field(default_factory=dict)

    def state(self, name: str) -> AttributeState:
        return self.attributes.get(name, AttributeState(name=name))

    def value(self, name: str, default: str = "") -> str:
        return self.state(name).values[0] if self.state(name).values else default

    def known(self) -> tuple[str, ...]:
        """Attributes that resolved to at least one value."""
        return tuple(
            sorted(n for n, s in self.attributes.items() if s.values)
        )

    def unresolved(self) -> tuple[str, ...]:
        """Attributes we have no value for, in any state."""
        return tuple(
            sorted(
                n
                for n, s in self.attributes.items()
                if not s.values and s.coverage in (Coverage.UNKNOWN, Coverage.REFUSED)
            )
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "entity_ref": self.entity_ref,
            "type_label": self.type_label,
            "attributes": {
                name: state.as_dict() for name, state in sorted(self.attributes.items())
            },
        }


def merge_offer(
    existing: AttributeState,
    *,
    source_id: str,
    values: Sequence[str] = (),
    refused: bool = False,
    note: str = "",
) -> AttributeState:
    """Fold one source's contribution into an attribute's state.

    The transitions are the interesting part:

    * a value from a new source where there was none → ``ACQUIRED``;
    * a second source with a *different* value → ``CONFLICT``, both kept;
    * a second source agreeing → still ``ACQUIRED``, source added (this is what
      ``corroborated`` counts);
    * a refusal never downgrades an acquired value, and never upgrades ``EMPTY`` to
      ``ACQUIRED`` -- a source that could not run is not evidence of anything.

    Symmetric conflict detection: order-independent, so two sources arriving in either order
    reach the same state.
    """
    incoming = tuple(dict.fromkeys(v for v in values if v and v.strip()))
    sources = tuple(sorted({*existing.sources, source_id}))

    if refused:
        if existing.coverage is Coverage.UNKNOWN:
            return replace_state(
                existing, coverage=Coverage.REFUSED, sources=sources, note=note
            )
        return replace_state(existing, sources=sources)

    if not incoming:
        if existing.coverage is Coverage.UNKNOWN:
            # A source ran and reported nothing: evidence of absence, not absence of evidence.
            return replace_state(
                existing, coverage=Coverage.EMPTY, sources=sources, note=note
            )
        return replace_state(existing, sources=sources)

    merged = tuple(sorted({*existing.values, *incoming}))
    if existing.values and merged != existing.values:
        return replace_state(
            existing,
            values=merged,
            coverage=Coverage.CONFLICT,
            sources=sources,
            note=note or "sources disagree",
        )
    return replace_state(
        existing,
        values=merged,
        coverage=Coverage.ACQUIRED,
        sources=sources,
        note=note,
    )


def replace_state(state: AttributeState, **changes: Any) -> AttributeState:
    """A frozen copy of ``state`` with ``changes`` applied."""
    return AttributeState(
        name=changes.get("name", state.name),
        values=tuple(changes.get("values", state.values)),
        coverage=changes.get("coverage", state.coverage),
        sources=tuple(changes.get("sources", state.sources)),
        note=str(changes.get("note", state.note) or ""),
    )


def plan_enrichment(
    profile: EntityProfile,
    offers: Iterable[CapabilityOffer],
    *,
    available: Mapping[str, bool] | None = None,
    source_groups: Mapping[str, str] | None = None,
) -> EnrichmentPlan:
    """What is still worth fetching for this entity, and where it would come from.

    ``available`` maps a source to whether it can run here (credential present, binary
    installed, host supported). A source that cannot run lands in ``blocked_sources`` on the
    gap rather than being scheduled, so a capability gap is visible without becoming an
    infinite retry.

    ``source_groups`` maps a source to its independence group (ADR-0036). Corroboration
    counts distinct groups, not distinct sources: two outlets carrying the same wire story
    are one source of evidence however many URLs they run it under.

    Gaps are ordered by attribute name so two runs over identical state produce identical
    plans and a diff means something.
    """
    offers = tuple(offers)
    runnable_flags = available or {}

    def can_run(offer: CapabilityOffer) -> bool:
        if offer.binary:
            return False
        if offer.key_env:
            return bool(runnable_flags.get(offer.source_id, False))
        return bool(runnable_flags.get(offer.source_id, True))

    wanted: dict[str, list[CapabilityOffer]] = {}
    for offer in offers:
        if not offer.applies_to(profile.type_label):
            continue
        for attribute in offer.attributes:
            wanted.setdefault(attribute, []).append(offer)

    gaps: list[AttributeGap] = []
    for attribute in sorted(wanted):
        state = profile.state(attribute)
        if not state.coverage.needs_work:
            continue
        candidates: list[str] = []
        blocked: list[str] = []
        for offer in wanted[attribute]:
            (candidates if can_run(offer) else blocked).append(offer.source_id)
        gaps.append(
            AttributeGap(
                entity_ref=profile.entity_ref,
                attribute=attribute,
                candidate_sources=tuple(sorted(set(candidates))),
                blocked_sources=tuple(sorted(set(blocked))),
            )
        )

    groups = source_groups or {}
    # Saturation is measured over the *expected surface* -- what we know plus what the
    # offers say we could know -- not over what we happen to hold. Measured over held
    # attributes alone, an entity the platform has heard of nothing scores 0 unknown and
    # reports itself saturated, which stops the loop before it has done a single fetch.
    expected = set(profile.attributes) | set(wanted)
    counts = Counter(
        profile.state(name).coverage for name in expected
    )
    total = len(expected)
    corroborated = sum(
        1
        for name in expected
        if profile.state(name).coverage is Coverage.ACQUIRED
        and len({groups.get(s, s) for s in profile.state(name).sources}) > 1
    )
    saturation = Saturation(
        total_attributes=total,
        acquired=counts.get(Coverage.ACQUIRED, 0),
        empty=counts.get(Coverage.EMPTY, 0),
        conflict=counts.get(Coverage.CONFLICT, 0),
        unknown=counts.get(Coverage.UNKNOWN, 0),
        refused=counts.get(Coverage.REFUSED, 0),
        corroborated=corroborated,
        distinct_sources=len({s for st in profile.attributes.values() for s in st.sources}),
    )
    conflicts = tuple(
        sorted(
            name
            for name, state in profile.attributes.items()
            if state.coverage is Coverage.CONFLICT
        )
    )
    return EnrichmentPlan(
        entity_ref=profile.entity_ref,
        gaps=tuple(gaps),
        saturation=saturation,
        conflicts=conflicts,
    )

