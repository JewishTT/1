"""Evidence context: the immutable frame a claim is interpreted under (feature 016, T046/T047).

Contract is ``specs/016-relation-evidence-graph-fabric/data-model.md`` section 5
with ``docs/adr/0024-claim-and-context-persistence.md``.

A context is *evidence*, not a verdict. It records the frame a claim was read
under — which observation, source, document and segment, the source family and
independence group, observed/published/event time, the extractor, normalisation
and ontology versions in force, the completeness and trust state, and the parent
frame — so a reviewer can reconstruct what was permitted when, and by which
rules (FR-013).

``context_id`` is a content address: ``CX-`` + ``digest128`` over the canonical
frame minus the id itself, drawn from :mod:`domain.relation_identity`, the same
primitive that derives relation ids. Two independently constructed frames with
the same content therefore address to the same id (FR-014, I-11), and recomputing
the digest over a stored row detects a hand-edited or corrupted one. A supplied id
is *verified*, never trusted: a frame that carries an id its own content does not
address to cannot be constructed, so no caller can forge one.

The frame is frozen and written only through ``object.__setattr__`` for the derived
id and for canonicalisation of the candidate tuples, so two semantically equal
frames cannot end up with different stored values and therefore different ids
(ADR-0024). Frames are shared by reference; a claim carries a ``context_ref`` and
never a copy (FR-018).

Resolution is loud: an unknown ``context_id`` yields ``None`` and the validator
reports ``context_unresolved`` — it never substitutes a default frame (FR-016).
Parent-cycle detection lives in the resolver and not in the frame, because a frame
cannot see its siblings: :func:`detect_context_cycle` returns the cycle path for
the validator to report as ``context_parent_cycle`` (FR-017).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from domain.relation_identity import canonical_material, digest128

#: Prefix of the content address; the digest follows it, so an id is 35 characters.
_CONTEXT_ID_PREFIX = "CX-"


class ContextContractError(ValueError):
    """A frame cannot be constructed, registered, or is not the frame it claims.

    A ``ValueError`` (as ``data-model.md`` specifies) carrying the stable
    snake_case ``code`` the validation layer reports, in the spirit of
    :class:`domain.relation_claim.RelationContractError` so one caller can switch
    on either.
    """

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


class ContextCompleteness(StrEnum):
    """How much of the frame's own evidence is present, as the producer declares it.

    A declaration, not a measurement: it is a label the extractor writes about
    itself and the validator reads, never a number summed from other fields
    (constitution IV).
    """

    COMPLETE = "complete"
    PARTIAL = "partial"
    FRAGMENT = "fragment"


class ContextTrustState(StrEnum):
    """How far the frame's content has been checked, at the time it was written.

    ``DISPUTED`` is reachable after the fact and caps the grade of any claim read
    under the frame; it is never averaged away.
    """

    VERIFIED = "verified"
    ATTESTED = "attested"
    UNVERIFIED = "unverified"
    DISPUTED = "disputed"


def _iso(value: Any) -> str | None:
    """One timestamp as canonical text (``None`` = honestly unknown)."""
    if value is None or value == "":
        return None
    return value.isoformat() if isinstance(value, datetime) else str(value)


def _moment(value: Any) -> datetime | None:
    """Parse a stored timestamp back, accepting a ``datetime`` unchanged."""
    if value is None or value == "":
        return None
    return value if isinstance(value, datetime) else datetime.fromisoformat(str(value))


def _refs(value: Any) -> tuple[str, ...]:
    """Candidate refs as the sorted, deduplicated tuple identity is taken over."""
    return tuple(sorted({str(ref) for ref in value or ()}))


@dataclass(frozen=True)
class EvidenceContext:
    """The frame one claim is interpreted under, frozen and content-addressed.

    Field order follows ``data-model.md`` section 5 exactly, because it is also
    the order a store column list, an event payload and the serialised material
    read. Candidate collections are canonicalised on construction, so two frames
    differing only in the order a producer collected their candidates are one
    frame (I-11), and the derived ``context_id`` is verified rather than trusted.
    """

    context_id: str = ""
    tenant_id: str = "default-tenant"
    investigation_id: str = ""
    entity_anchor: str = ""

    observation_id: str = ""
    source_id: str = ""
    document_id: str = ""
    segment_id: str = ""

    subject_candidate_ids: tuple[str, ...] = ()
    object_candidate_ids: tuple[str, ...] = ()

    observed_at: datetime | None = None
    published_at: datetime | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None

    source_family: str = ""
    independence_group: str = ""
    language: str = ""
    location_context: str = ""

    extraction_version: str = ""
    normalization_version: str = ""
    ontology_version: str = ""

    completeness: ContextCompleteness = ContextCompleteness.COMPLETE
    trust_state: ContextTrustState = ContextTrustState.UNVERIFIED
    policy_snapshot_ref: str = ""
    parent_context_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "completeness", ContextCompleteness(self.completeness))
        object.__setattr__(self, "trust_state", ContextTrustState(self.trust_state))

        if (
            self.valid_to is not None
            and self.valid_from is not None
            and self.valid_to < self.valid_from
        ):
            raise ContextContractError(
                "validity_interval_inverted",
                f"valid_to {self.valid_to.isoformat()} precedes "
                f"valid_from {self.valid_from.isoformat()}",
            )

        object.__setattr__(self, "subject_candidate_ids", _refs(self.subject_candidate_ids))
        object.__setattr__(self, "object_candidate_ids", _refs(self.object_candidate_ids))

        addressed = _CONTEXT_ID_PREFIX + self.frame_fingerprint
        if not self.context_id:
            object.__setattr__(self, "context_id", addressed)
        elif self.context_id != addressed:
            raise ContextContractError(
                "context_id_mismatch",
                f"frame carries {self.context_id!r} but its own content "
                f"addresses to {addressed!r}",
            )

    @property
    def frame_fingerprint(self) -> str:
        """The 128-bit digest ``context_id`` is built from (FR-014, I-11).

        Persisted beside the id so ``uq_evidence_context_fingerprint`` makes
        registration idempotent at the database, not only in the resolver.
        """
        return digest128(canonical_material(self._material()))

    def to_dict(self) -> dict[str, Any]:
        """The full frame record, plus its fingerprint (I-5, FR-018)."""
        return {
            "context_id": self.context_id,
            **self._material(),
            "frame_fingerprint": self.frame_fingerprint,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> EvidenceContext:
        """Rebuild a frame from its own record; missing keys take the defaults.

        The stored ``context_id`` is passed through and therefore verified
        against the recomputed material, so a round-trip of a tampered row raises
        rather than returning a frame that lies about its content.
        """
        data = dict(payload)
        data.pop("frame_fingerprint", None)
        return cls(
            context_id=str(data.get("context_id", "")),
            tenant_id=str(data.get("tenant_id", "default-tenant")),
            investigation_id=str(data.get("investigation_id", "")),
            entity_anchor=str(data.get("entity_anchor", "")),
            observation_id=str(data.get("observation_id", "")),
            source_id=str(data.get("source_id", "")),
            document_id=str(data.get("document_id", "")),
            segment_id=str(data.get("segment_id", "")),
            subject_candidate_ids=tuple(
                str(ref) for ref in data.get("subject_candidate_ids") or ()
            ),
            object_candidate_ids=tuple(str(ref) for ref in data.get("object_candidate_ids") or ()),
            observed_at=_moment(data.get("observed_at")),
            published_at=_moment(data.get("published_at")),
            valid_from=_moment(data.get("valid_from")),
            valid_to=_moment(data.get("valid_to")),
            source_family=str(data.get("source_family", "")),
            independence_group=str(data.get("independence_group", "")),
            language=str(data.get("language", "")),
            location_context=str(data.get("location_context", "")),
            extraction_version=str(data.get("extraction_version", "")),
            normalization_version=str(data.get("normalization_version", "")),
            ontology_version=str(data.get("ontology_version", "")),
            completeness=ContextCompleteness(data.get("completeness", ContextCompleteness.COMPLETE)),
            trust_state=ContextTrustState(data.get("trust_state", ContextTrustState.UNVERIFIED)),
            policy_snapshot_ref=str(data.get("policy_snapshot_ref", "")),
            parent_context_id=str(data.get("parent_context_id", "")),
        )

    def _material(self) -> dict[str, Any]:
        """The serialised field set ``context_id`` and the fingerprint address."""
        return {
            "tenant_id": self.tenant_id,
            "investigation_id": self.investigation_id,
            "entity_anchor": self.entity_anchor,
            "observation_id": self.observation_id,
            "source_id": self.source_id,
            "document_id": self.document_id,
            "segment_id": self.segment_id,
            "subject_candidate_ids": list(self.subject_candidate_ids),
            "object_candidate_ids": list(self.object_candidate_ids),
            "observed_at": _iso(self.observed_at),
            "published_at": _iso(self.published_at),
            "valid_from": _iso(self.valid_from),
            "valid_to": _iso(self.valid_to),
            "source_family": self.source_family,
            "independence_group": self.independence_group,
            "language": self.language,
            "location_context": self.location_context,
            "extraction_version": self.extraction_version,
            "normalization_version": self.normalization_version,
            "ontology_version": self.ontology_version,
            "completeness": str(self.completeness),
            "trust_state": str(self.trust_state),
            "policy_snapshot_ref": self.policy_snapshot_ref,
            "parent_context_id": self.parent_context_id,
        }


@runtime_checkable
class ContextResolver(Protocol):
    """The one way a claim's ``context_ref`` reaches its frame (FR-016, FR-018).

    Resolution is total or absent: an id the resolver does not hold yields
    ``None`` and the claim is reported ``context_unresolved``, because a
    substituted default frame would make an unresolved reference look licensed.
    """

    def resolve(self, context_id: str) -> EvidenceContext | None: ...

    def register(self, frame: EvidenceContext) -> str: ...


class InMemoryContextResolver:
    """The reference resolver and the test oracle for ``ContextResolver``.

    Registration is idempotent on ``context_id`` (I-11): re-registering an equal
    frame returns the same id and stores nothing new, and re-registering a
    *different* frame under one id raises rather than overwriting, so a frame
    that is already referenced by claims can never change underneath them. The
    same discipline as the database unique index on
    ``(tenant_id, frame_fingerprint)``, made explicit in memory.
    """

    def __init__(self, frames: Iterable[EvidenceContext] = ()) -> None:
        self._frames: dict[str, EvidenceContext] = {}
        for frame in frames:
            self.register(frame)

    def register(self, frame: EvidenceContext) -> str:
        """Store a frame and return its ``context_id``; idempotent on content."""
        registered = self._frames.get(frame.context_id)
        if registered is not None:
            if registered != frame:
                raise ContextContractError(
                    "context_id_conflict",
                    f"context {frame.context_id} is already registered with "
                    f"different content; frames are never overwritten",
                )
            return registered.context_id
        self._frames[frame.context_id] = frame
        return frame.context_id

    def resolve(self, context_id: str) -> EvidenceContext | None:
        """The registered frame, or ``None`` for an id this resolver does not hold."""
        return self._frames.get(context_id)

    def ancestors(self, context_id: str) -> tuple[EvidenceContext, ...]:
        """The parent chain of a frame, from the immediate parent upward.

        The shape the SQL store's cycle-detecting ancestor query mirrors. The
        chain stops at the first id that is not registered — an unresolved
        parent is not an ancestor this resolver can attest to — and at the first
        repeated id, so a corrupt row cannot spin the walk. An unknown
        ``context_id`` has no chain, and neither has a root.
        """
        frame = self.resolve(context_id)
        if frame is None:
            return ()
        chain: list[EvidenceContext] = []
        seen = {context_id}
        current = frame.parent_context_id
        while current and current not in seen:
            parent = self.resolve(current)
            if parent is None:
                break
            chain.append(parent)
            seen.add(current)
            current = parent.parent_context_id
        return tuple(chain)

    def __len__(self) -> int:
        return len(self._frames)

    def __contains__(self, context_id: object) -> bool:
        return context_id in self._frames


def detect_context_cycle(frames: Iterable[EvidenceContext]) -> tuple[str, ...]:
    """The parent cycle among ``frames``, or ``()`` when the links are acyclic.

    Return contract: on a cycle the first and last element are the same
    ``context_id`` and every consecutive pair is one ``parent_context_id`` hop,
    so the path renders directly (``a -> b -> c -> a``) as the
    ``context_parent_cycle`` detail (FR-017). Acyclic, empty and unresolved
    inputs all return ``()``.

    A ``parent_context_id`` naming a frame outside ``frames`` is *unresolved*,
    not cyclic: the walk stops there and the missing parent is
    ``provenance_context_parent_missing`` (ADR-0024), which is a different
    defect from a loop. Start ids are visited in sorted order so the reported
    path does not depend on the order the frames were supplied in.
    """
    parents = {frame.context_id: frame.parent_context_id for frame in frames}
    for start in sorted(parents):
        path: list[str] = []
        seen: dict[str, int] = {}
        current = start
        while current in parents:
            if current in seen:
                return tuple([*path[seen[current] :], current])
            seen[current] = len(path)
            path.append(current)
            current = parents[current]
    return ()


__all__ = [
    "ContextCompleteness",
    "ContextContractError",
    "ContextResolver",
    "ContextTrustState",
    "EvidenceContext",
    "InMemoryContextResolver",
    "detect_context_cycle",
]
