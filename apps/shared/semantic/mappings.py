"""SSSOM-style cross-vocabulary mappings as first-class, evidence-bearing objects.

Feature 017, FR-009 / T018, US10, defect D3. What this module replaces is a hardcoded
``EXTERNAL_TYPE_MAP`` dict. A mapping held in code carries no provenance, no justification, no
version and no evidence, so an alignment decision cannot be audited, reversed, re-derived or
cited, and the only way to change one is to edit code and redeploy. Here a mapping is a frozen,
content-addressed *record* carrying all four, and the dict is gone (US10: Common Crawl yields
``Managing Director``, and a ``closeMatch`` to ``role`` is recorded rather than hardcoded).

**A mapping is a claim, not an identity.** This is the whole design constraint, and it is
structural rather than a promise in a comment. A :class:`SemanticMapping` asserts a
*correspondence* between an internal reference and an external one, and nothing in this module
is able to make two references denote one thing: there is no field, helper, method or return
value with which identity could be expressed. Even the strongest predicate,
``MatchPredicate.EXACT_MATCH``, means only that a recorded mapping process asserted alignment
(see :class:`semantic.vocabularies.MatchPredicate`) - it does not make the platform treat the
two as one type. Internal identity lives in the graph and is established by evidence there, as a
different object entirely; a mapping is one correspondence among many, and an external ontology
IRI never replaces an internal ID (spec scope guard).

**Several mappings for one pair is the normal case, and none of them is chosen over another.**
:meth:`MappingRegistry.mappings_for` returns a ``tuple`` and never collapses its result. Two
mappings that disagree about the same pair are not an error to be resolved - they are *data to
be surfaced*, which is what :class:`MappingConflict` and
:meth:`MappingRegistry.conflicts` are for. Auto-resolving one would be the worst available
outcome: the platform has no standing to adjudicate between, say, a lexical inference and a
human mapping, and silently discarding either makes the alignment unauditable while still
leaving the survivor in use. Accordingly there is deliberately no ``resolve_conflict``, no
``best_mapping`` and no priority ordering applied to conflicting predicates anywhere in this
file. A caller that wants to know the alignments disagree asks :meth:`~MappingRegistry.conflicts`
and gets every side; a caller validating the pair can turn that into a graded
``Verdict.CONFLICTING`` *finding* attached to whatever asserted it, which is a report and never
a deletion (FR-012).

**Evidence-bearing and re-evaluable.** A mapping is citable: :meth:`SemanticMapping.cite` and
:meth:`MappingRegistry.cite` produce a :class:`MappingCitation` naming the evidence reference an
assertion would point at, alongside the justification, the source that produced the claim, the
confidence and the provenance. It is re-evaluable because the whole claim is deterministic
material: :meth:`SemanticMapping.evaluation_material` returns exactly what
:meth:`SemanticMapping.content_key` hashes, so an independent process can recompute the claim and
diff it rather than trusting the stored id. Re-evaluation is monotonic - a corrected mapping is a
*new* record naming its predecessor in ``supersedes``, and the predecessor stays readable
(FR-004). Nothing here is ever overwritten or withdrawn in place.

**Tenant isolation is structural, fail-closed.** One registry serves one tenant, and registering
a mapping whose ``tenant_id`` disagrees raises :class:`TenantScopeRefused` rather than filing it
somewhere it can be read across a boundary (constitution IV). It is a refusal at the write, not
a filter at the read, so there is no code path in which a cross-tenant mapping is visible.

**Bounded payloads refuse rather than truncate.** Mirroring ``events.ontology_pack``, a payload
is serialised and measured before it is carried, and an oversized one raises
:class:`MappingPayloadTooLarge`. Truncating is not an option here for a specific reason: a
silently shortened mapping set is a mapping set that lies about what it contains, and a mapping
that lost its justification or provenance is a claim nobody can audit - which would defeat the
entire purpose of the record. Carry a reference to an out-of-line set instead (constitution I-5,
constitution VIII).

**Dependency reality.** SSSOM is implemented natively over plain dataclasses. The ``sssom``
package is not installed and is not required; the format is simple enough that a dependency
would cost more than it saves, and FR-005 forbids the vocabulary types leaking anywhere else.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType

from semantic.contracts import SemanticRef, content_key
from semantic.vocabularies import MatchPredicate, normalize_type_ref

__all__ = [
    "DEFAULT_MAX_INLINE_BYTES",
    "MappingCitation",
    "MappingConflict",
    "MappingError",
    "MappingIdCollision",
    "MappingJustification",
    "MappingPayload",
    "MappingPayloadTooLarge",
    "MappingRegistry",
    "MappingSet",
    "SemanticMapping",
    "TenantScopeRefused",
]


#: Inline ceiling for a serialised mapping payload, mirroring the descriptor cap
#: ``events.ontology_pack`` applies before inlining a pack into an event. Exceeding it is a
#: typed refusal (:class:`MappingPayloadTooLarge`), never a truncation.
DEFAULT_MAX_INLINE_BYTES = 4096


class MappingJustification(StrEnum):
    """Why a mapping process produced this correspondence (FR-009).

    The justification travels with the mapping because a correspondence is only as good as the
    reason it was claimed, and an alignment asserted by label similarity needs to be
    distinguishable from one a human approved. A mapping recorded without a defensible
    justification is still a legal record - the world is open and an alignment process may name
    itself in ways this enum does not anticipate - but it is a claim with a weaker audit trail,
    and this vocabulary is what a caller sorts on when it wants to tell the two apart.
    """

    LEXICAL = "lexical"
    MANUAL = "manual"
    INFERENCE = "inference"
    STATED_IN_SOURCE = "stated_in_source"


class MappingError(Exception):
    """Base for the typed failures this module raises.

    A caller can therefore catch every mapping-specific problem - a payload that will not fit, a
    tenant boundary, a duplicated id - with one ``except`` and cannot accidentally swallow an
    unrelated ``ValueError`` from somewhere else in the stack.
    """


class MappingPayloadTooLarge(MappingError):
    """A serialised mapping payload exceeded the inline cap (constitution VIII).

    Raised instead of trimming the mapping list. A truncated mapping set is a mapping set that
    misreports its own contents, and the mappings lost are exactly the ones whose provenance
    would have made the set auditable.
    """

    def __init__(self, what: str, byte_size: int, limit: int) -> None:
        self.what = what
        self.byte_size = byte_size
        self.limit = limit
        super().__init__(
            f"{what} serialises to {byte_size} bytes, over the {limit}-byte inline cap; "
            "carry a reference to an out-of-line mapping set rather than a truncated body"
        )


class TenantScopeRefused(MappingError):
    """A mapping was offered to a registry belonging to a different tenant.

    Refused at the write so that cross-tenant visibility has no code path at all, rather than
    being filtered on every read (constitution IV, fail-closed).
    """

    def __init__(self, mapping_tenant: str, registry_tenant: str) -> None:
        self.mapping_tenant = mapping_tenant
        self.registry_tenant = registry_tenant
        super().__init__(
            f"mapping belongs to tenant {mapping_tenant!r}, registry serves "
            f"{registry_tenant!r}; cross-tenant registration is refused"
        )


class MappingIdCollision(MappingError):
    """Two distinct mapping contents were offered under one ``mapping_id``.

    Reported, never reconciled: accepting the second would leave one id addressing two claims,
    and a citation pointing at that id would then cite neither of them reliably.
    """

    def __init__(self, mapping_id: str) -> None:
        self.mapping_id = mapping_id
        super().__init__(
            f"mapping id {mapping_id!r} is already bound to a different mapping; "
            "content-addressed ids are never rebound"
        )


def _canonical_refs(values: Iterable[str]) -> tuple[str, ...]:
    """A reference set: de-duplicated, blank-free, canonically ordered.

    Reuses :func:`semantic.vocabularies.normalize_type_ref`, which preserves case because a
    reference is an opaque identifier - ``schema:Person`` and ``schema:person`` are different
    references and the platform has no standing to decide otherwise. Sorting is what makes a
    mapping content-addressable without regard to the order its producer collected refs in
    (constitution VI).
    """
    if isinstance(values, str):
        values = (values,)
    return tuple(sorted({ref for ref in (normalize_type_ref(v) for v in values) if ref}))


def _order_key(mapping: SemanticMapping) -> tuple[str, ...]:
    """Total, value-based ordering for every listing this module returns.

    Deterministic and independent of registration order, so a diff between two runs means
    something changed rather than that a dict iterated differently.
    """
    return (
        mapping.subject_ref,
        mapping.object_ref,
        str(mapping.predicate),
        mapping.mapping_set_id,
        mapping.mapping_set_version,
        mapping.mapping_source,
        mapping.evidence_ref,
    )


def _serialise(payload: object) -> tuple[str, int]:
    """Canonical JSON for a payload plus its UTF-8 byte size, measured rather than assumed."""
    body = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )
    return body, len(body.encode("utf-8"))


def _refuse_oversize(byte_size: int, limit: int, what: str) -> None:
    if byte_size > limit:
        raise MappingPayloadTooLarge(what, byte_size, limit)


@dataclass(frozen=True)
class SemanticMapping:
    """One recorded cross-vocabulary correspondence: internal term, external term, and why.

    A mapping is a **claim that a mapping process made**, and it is read as one. ``subject_ref``
    is the internal term the platform itself uses, ``object_ref`` is a term in someone else's
    vocabulary, and ``predicate`` says how the process characterised the relationship - not how
    the platform treats the two references, which is the whole difference between this record
    and an identity assertion. There is no field here able to say the two terms are one thing,
    and the absence is deliberate: identity is established in the graph, by evidence, as a
    different kind of object (spec scope guard).

    The audit trail is the reason this is a record and not a lookup table. ``mapping_source``
    names who produced the claim, ``mapping_version`` and the set's own
    ``mapping_set_version`` say which iteration of which alignment effort this is,
    ``justification`` says on what grounds it was asserted, ``provenance`` carries the evidence
    references the claim rests on, ``confidence`` carries the process's own strength and
    ``observed_at`` when the platform learned it (constitution V - distinct from truth). A
    mapping with an empty ``provenance`` is a legal record: a mapping process may not have
    published its evidence, and refusing to record the claim would be a worse outcome than
    recording it with a thin trail.

    Immutable and content-addressed: :meth:`content_key` digests the entire claim, ``mapping_id``
    is derived from it, and re-recording identical content is a no-op rather than a second row.
    ``supersedes`` chains a re-evaluation without removing what it corrects, so the history of an
    alignment stays reconstructable (FR-004).
    """

    subject_ref: str = ""
    object_ref: str = ""
    predicate: MatchPredicate = MatchPredicate.CLOSE_MATCH

    mapping_set_id: str = "default"
    mapping_set_version: str = "1"

    mapping_source: str = ""
    mapping_version: str = "1"
    justification: MappingJustification = MappingJustification.MANUAL
    provenance: tuple[str, ...] = ()

    confidence: float = 1.0
    tenant_id: str = "default-tenant"
    observed_at: datetime | None = None

    subject_scheme: SemanticRef = SemanticRef.INTERNAL
    object_scheme: SemanticRef = SemanticRef.EXTERNAL

    supersedes: tuple[str, ...] = ()
    mapping_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "subject_ref", normalize_type_ref(self.subject_ref))
        object.__setattr__(self, "object_ref", normalize_type_ref(self.object_ref))
        object.__setattr__(self, "predicate", MatchPredicate(self.predicate))
        object.__setattr__(self, "justification", MappingJustification(self.justification))
        object.__setattr__(self, "subject_scheme", SemanticRef(self.subject_scheme))
        object.__setattr__(self, "object_scheme", SemanticRef(self.object_scheme))
        object.__setattr__(self, "mapping_set_id", str(self.mapping_set_id).strip())
        object.__setattr__(self, "mapping_set_version", str(self.mapping_set_version).strip())
        object.__setattr__(self, "mapping_source", str(self.mapping_source).strip())
        object.__setattr__(self, "mapping_version", str(self.mapping_version).strip())
        object.__setattr__(self, "tenant_id", str(self.tenant_id).strip())
        object.__setattr__(self, "provenance", _canonical_refs(self.provenance))
        object.__setattr__(self, "supersedes", _canonical_refs(self.supersedes))
        object.__setattr__(self, "mapping_id", str(self.mapping_id).strip())
        confidence = float(self.confidence)
        if not 0.0 <= confidence <= 1.0:
            raise ValueError(f"confidence must be within 0.0..1.0, got {confidence}")
        object.__setattr__(self, "confidence", confidence)
        if self.observed_at is not None and not isinstance(self.observed_at, datetime):
            raise TypeError(f"observed_at must be a datetime or None, got {self.observed_at!r}")

    @property
    def pair(self) -> tuple[str, str]:
        """The ``(subject, object)`` reference pair this correspondence is about."""
        return (self.subject_ref, self.object_ref)

    @property
    def identity(self) -> tuple[str, str, str, str, str, str]:
        """``(tenant, subject, object, predicate, set_id, set_version)`` - the spec's key.

        Deliberately *not* including source, confidence or provenance: two processes aligning the
        same pair the same way are making the same claim about the same pair, and they are two
        pieces of evidence for it rather than two claims. They are still both stored and both
        retrievable, because identity is not the same thing as what the store holds.
        """
        return (
            self.tenant_id,
            self.subject_ref,
            self.object_ref,
            str(self.predicate),
            self.mapping_set_id,
            self.mapping_set_version,
        )

    @property
    def version_ref(self) -> str:
        """``<set_id>@<set_version>`` - the mapping-set iteration this record belongs to."""
        return f"{self.mapping_set_id}@{self.mapping_set_version}"

    @property
    def evidence_ref(self) -> str:
        """The reference an assertion may cite for this mapping.

        The declared id when there is one, otherwise the content digest - so a mapping is
        citable the moment it exists, whether or not anyone has stored an id for it.
        """
        return self.mapping_id or self.content_key()

    def evaluation_material(self) -> dict[str, object]:
        """Everything needed to recompute and re-evaluate this claim independently.

        Exactly the material :meth:`content_key` digests, exposed so a re-evaluation process can
        be handed the claim and reach the same digest instead of trusting a stored id. Excludes
        ``mapping_id`` on purpose, since the id is *derived from* this material.
        """
        return {
            "tenant": self.tenant_id,
            "subject": self.subject_ref,
            "object": self.object_ref,
            "subject_scheme": str(self.subject_scheme),
            "object_scheme": str(self.object_scheme),
            "predicate": str(self.predicate),
            "mapping_set": self.mapping_set_id,
            "mapping_set_version": self.mapping_set_version,
            "mapping_source": self.mapping_source,
            "mapping_version": self.mapping_version,
            "justification": str(self.justification),
            "provenance": list(self.provenance),
            "confidence": self.confidence,
            "observed_at": str(self.observed_at) if self.observed_at else None,
            "supersedes": list(self.supersedes),
        }

    def content_key(self) -> str:
        """Order-insensitive identity of the whole claim, via the shared digest convention.

        Reuses :func:`semantic.contracts.content_key` so mappings, type assertions and relational
        objects are all addressed the same way in one graph instead of growing a second hashing
        dialect (constitution VII).
        """
        return content_key(self.evaluation_material())

    def with_id(self) -> SemanticMapping:
        """A copy carrying its own content-addressed ``mapping_id``, or ``self`` if it has one."""
        return replace(self, mapping_id=self.content_key()) if not self.mapping_id else self

    def to_dict(self) -> dict[str, object]:
        """Serialisable form, used to measure a payload before it is inlined anywhere."""
        material = self.evaluation_material()
        material["mapping_id"] = self.mapping_id
        return material

    def cite(self, claim_ref: str = "") -> MappingCitation:
        """The citable form of this claim: what an assertion points at to justify a typing.

        A citation names the evidence reference *and* carries the claim's own audit fields,
        because a citation that could only name an id would force a reader to go looking for the
        reason. ``claim_ref`` is whatever asserted the alignment - an entity, an observation, an
        assertion id - and is recorded so the citation can be read in the direction it was made.
        """
        return MappingCitation(
            evidence_ref=self.evidence_ref,
            claim_ref=str(claim_ref),
            mapping_id=self.mapping_id,
            subject_ref=self.subject_ref,
            object_ref=self.object_ref,
            predicate=self.predicate,
            justification=self.justification,
            mapping_source=self.mapping_source,
            confidence=self.confidence,
            provenance=self.provenance,
        )

    def supersedes_ref(self, evidence_ref: str) -> bool:
        """Whether this record was recorded as correcting ``evidence_ref``.

        A re-evaluation adds a mapping; it never edits or removes the one it revises, so
        correcting an alignment leaves both claims readable and their order derivable.
        """
        return normalize_type_ref(evidence_ref) in self.supersedes

    def conflicts_with(self, other: SemanticMapping) -> bool:
        """Whether two mappings make irreconcilable claims about the same pair.

        Conflict is exactly one thing: the same ``(subject, object)`` pair in the same tenant
        characterised with two different predicates. ``exact_match`` and ``narrow_match`` on one
        pair cannot both be what the mapping processes meant, and that is a fact about the
        alignment data that somebody has to look at.

        It is deliberately *not* "two sources disagree about anything" - two sources asserting
        the same predicate about one pair is corroboration, and both records stay. And this
        method reports; it never picks a side. There is no ordering here that could decide which
        alignment is right, because a lexical inference has no standing over a human mapping and
        vice versa. A caller that wants the disagreement graded turns it into a
        ``Verdict.CONFLICTING`` finding attached to the claim, which is a report, not a deletion
        (FR-012).
        """
        return (
            self.tenant_id == other.tenant_id
            and self.pair == other.pair
            and self.predicate is not other.predicate
        )


@dataclass(frozen=True)
class MappingCitation:
    """One mapping, phrased as evidence: the reference plus the claim it supports.

    This is the shape that lets an alignment decision be audited without a reader having to
    reconstruct the claim. It names *what was claimed* (``subject_ref``, ``object_ref``,
    ``predicate``), *on what grounds* (``justification``, ``mapping_source``, ``confidence``,
    ``provenance``) and *who made the claim* (``claim_ref``) - and, critically, it does not
    assert that the two references denote one thing. Citing a mapping means a correspondence was
    recorded, which is all it ever meant.
    """

    evidence_ref: str
    mapping_id: str = ""
    claim_ref: str = ""
    subject_ref: str = ""
    object_ref: str = ""
    predicate: MatchPredicate = MatchPredicate.CLOSE_MATCH
    justification: MappingJustification = MappingJustification.MANUAL
    mapping_source: str = ""
    confidence: float = 1.0
    provenance: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "predicate", MatchPredicate(self.predicate))
        object.__setattr__(self, "justification", MappingJustification(self.justification))
        object.__setattr__(self, "evidence_ref", str(self.evidence_ref))
        object.__setattr__(self, "mapping_id", str(self.mapping_id))
        object.__setattr__(self, "claim_ref", str(self.claim_ref))
        object.__setattr__(self, "subject_ref", normalize_type_ref(self.subject_ref))
        object.__setattr__(self, "object_ref", normalize_type_ref(self.object_ref))
        object.__setattr__(self, "mapping_source", str(self.mapping_source))
        object.__setattr__(self, "provenance", _canonical_refs(self.provenance))
        object.__setattr__(self, "confidence", float(self.confidence))

    @property
    def pair(self) -> tuple[str, str]:
        return (self.subject_ref, self.object_ref)

    def content_key(self) -> str:
        """Identity of this citation, so a derived claim can record which mapping it used."""
        return content_key(
            {
                "evidence": self.evidence_ref,
                "claim": self.claim_ref,
                "subject": self.subject_ref,
                "object": self.object_ref,
                "predicate": str(self.predicate),
                "justification": str(self.justification),
                "source": self.mapping_source,
                "confidence": self.confidence,
                "provenance": list(self.provenance),
            }
        )


@dataclass(frozen=True)
class MappingConflict:
    """Two or more mappings that cannot both be right about one pair - reported, not resolved.

    This is a first-class report because disagreement between alignment processes is a fact
    somebody needs, and reporting it is the only honest response: the platform cannot tell a
    wrong mapping from a superseded one without the provenance each side carries, and quietly
    preferring either would leave the alignment set saying something its producers did not.

    Every side is present. ``mapping_ids`` holds one entry per claim, ``predicates`` the
    incompatible characterisations, ``mapping_sources`` whoever produced them. Nothing here
    names a winner, and the type offers no method that could.
    """

    subject_ref: str
    object_ref: str
    mapping_ids: tuple[str, ...] = ()
    predicates: tuple[str, ...] = ()
    mapping_sources: tuple[str, ...] = ()
    tenant_id: str = "default-tenant"

    def __post_init__(self) -> None:
        object.__setattr__(self, "subject_ref", normalize_type_ref(self.subject_ref))
        object.__setattr__(self, "object_ref", normalize_type_ref(self.object_ref))
        object.__setattr__(self, "tenant_id", str(self.tenant_id).strip())
        object.__setattr__(self, "mapping_ids", tuple(sorted({str(i) for i in self.mapping_ids})))
        object.__setattr__(
            self, "predicates", tuple(sorted({str(p) for p in self.predicates}))
        )
        object.__setattr__(
            self, "mapping_sources", tuple(sorted({str(s) for s in self.mapping_sources if str(s)}))
        )

    @property
    def pair(self) -> tuple[str, str]:
        return (self.subject_ref, self.object_ref)

    def content_key(self) -> str:
        return content_key(
            {
                "subject": self.subject_ref,
                "object": self.object_ref,
                "mappings": list(self.mapping_ids),
                "predicates": list(self.predicates),
                "sources": list(self.mapping_sources),
                "tenant": self.tenant_id,
            }
        )


@dataclass(frozen=True)
class MappingPayload:
    """A measured, inlinable body of mapping records - or a refusal to produce one.

    ``body`` is canonical JSON and ``byte_size`` is its UTF-8 length, so the cap in
    ``events.ontology_pack`` can be applied to a mapping set on exactly the same terms as to a
    pack descriptor. Producing this type at all means the payload was measured and fitted; an
    oversized one raises :class:`MappingPayloadTooLarge` from
    :meth:`MappingSet.payload` instead.
    """

    mapping_set_id: str
    version: str
    tenant_id: str
    body: str
    byte_size: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "mapping_set_id", str(self.mapping_set_id))
        object.__setattr__(self, "version", str(self.version))
        object.__setattr__(self, "tenant_id", str(self.tenant_id))
        object.__setattr__(self, "body", str(self.body))
        object.__setattr__(self, "byte_size", int(self.byte_size))

    def to_dict(self) -> dict[str, object]:
        """Envelope for an event that carries this payload inline."""
        return {
            "mapping_set_id": self.mapping_set_id,
            "version": self.version,
            "tenant_id": self.tenant_id,
            "byte_size": self.byte_size,
            "body": self.body,
        }

    def content_key(self) -> str:
        return content_key(
            {
                "mapping_set": self.mapping_set_id,
                "version": self.version,
                "tenant": self.tenant_id,
                "body": self.body,
            }
        )


def _bind_to_set(
    mapping: SemanticMapping, set_id: str, version: str, tenant_id: str
) -> SemanticMapping:
    """Attach a mapping to the set that is holding it.

    Mirrors the vocabulary scheme's own adoption rule so a producer does not have to restate the
    set it is contributing to. A mapping that names a *different* set is a caller bug and raises,
    because a set that silently held a mapping belonging to another one would report its own
    contents wrongly.
    """
    if mapping.mapping_set_id and mapping.mapping_set_id != set_id:
        raise ValueError(
            f"mapping belongs to set {mapping.mapping_set_id!r}, not {set_id!r}"
        )
    if mapping.mapping_set_version and mapping.mapping_set_version != version:
        raise ValueError(
            f"mapping declares set version {mapping.mapping_set_version!r}, not {version!r}"
        )
    if mapping.tenant_id and mapping.tenant_id != tenant_id:
        raise ValueError(
            f"mapping belongs to tenant {mapping.tenant_id!r}, not {tenant_id!r}"
        )
    return replace(
        mapping,
        mapping_set_id=set_id,
        mapping_set_version=version,
        tenant_id=tenant_id,
    )


@dataclass(frozen=True)
class MappingSet:
    """One versioned alignment effort: the mappings a single process asserted, together.

    A set exists so that a body of cross-vocabulary alignment has an identity, a version and an
    author - "what did mapping effort 3 believe, and when" is a question a store cannot answer
    from a flat pile of records. Membership is by *content*: mappings are de-duplicated on their
    whole-claim digest, so a producer that contributes the same mapping twice contributes it
    once, while two mappings about the same pair that disagree with each other are two
    distinct records and both stay (see :class:`MappingConflict`).

    Sets are frozen and canonically ordered, so a set is a value: two sets holding the same
    mappings in different orders compare equal and share a :meth:`content_key` (constitution VI).
    """

    mapping_set_id: str
    version: str = "1"
    tenant_id: str = "default-tenant"
    mappings: tuple[SemanticMapping, ...] = ()
    description: str = ""

    def __post_init__(self) -> None:
        set_id = str(self.mapping_set_id).strip()
        version = str(self.version).strip()
        tenant_id = str(self.tenant_id).strip()
        by_content: dict[str, SemanticMapping] = {}
        for mapping in self.mappings:
            bound = _bind_to_set(mapping, set_id, version, tenant_id)
            by_content.setdefault(bound.content_key(), bound)
        ordered = tuple(sorted(by_content.values(), key=_order_key))
        object.__setattr__(self, "mapping_set_id", set_id)
        object.__setattr__(self, "version", version)
        object.__setattr__(self, "tenant_id", tenant_id)
        object.__setattr__(self, "description", str(self.description))
        object.__setattr__(self, "mappings", ordered)

    @classmethod
    def from_mappings(
        cls,
        mapping_set_id: str,
        mappings: Iterable[SemanticMapping],
        version: str = "1",
        tenant_id: str = "default-tenant",
    ) -> MappingSet:
        """Build a set in one pass - prefer this over assembling ``mappings`` by hand."""
        return cls(mapping_set_id, version, tenant_id, tuple(mappings))

    def __len__(self) -> int:
        return len(self.mappings)

    def __iter__(self) -> Iterator[SemanticMapping]:
        return iter(self.mappings)

    def __contains__(self, item: object) -> bool:
        """Membership by mapping id, by content digest, or by subject reference.

        All three because a caller checking "is this in the set?" holds whichever of the three it
        happens to have, and making it convert first would be a needless way to lose a mapping.
        """
        needle = str(item)
        return any(
            mapping.mapping_id == needle
            or mapping.content_key() == needle
            or mapping.subject_ref == needle
            for mapping in self.mappings
        )

    def __repr__(self) -> str:
        return (
            f"MappingSet(mapping_set_id={self.mapping_set_id!r}, "
            f"version={self.version!r}, mappings={len(self)})"
        )

    @property
    def version_ref(self) -> str:
        return f"{self.mapping_set_id}@{self.version}"

    @property
    def mapping_ids(self) -> tuple[str, ...]:
        return tuple(mapping.evidence_ref for mapping in self.mappings)

    def for_subject(
        self, subject_ref: str, predicate: MatchPredicate | None = None
    ) -> tuple[SemanticMapping, ...]:
        """Every mapping asserted *from* an internal ref. All matches, canonically ordered."""
        return _filter(self.mappings, subject_ref, predicate, by_subject=True)

    def for_object(
        self, object_ref: str, predicate: MatchPredicate | None = None
    ) -> tuple[SemanticMapping, ...]:
        """Every mapping asserted *to* an external ref. All matches, canonically ordered."""
        return _filter(self.mappings, object_ref, predicate, by_subject=False)

    def for_predicate(self, predicate: MatchPredicate) -> tuple[SemanticMapping, ...]:
        """Every mapping characterised with one predicate - "what do we align as exact?"."""
        wanted = MatchPredicate(predicate)
        return tuple(m for m in self.mappings if m.predicate is wanted)

    def from_mapping_source(self, mapping_source: str) -> tuple[SemanticMapping, ...]:
        """Every mapping produced by one source - "which of these came from X?"."""
        wanted = str(mapping_source).strip()
        return tuple(m for m in self.mappings if m.mapping_source == wanted)

    def payload(self, max_inline: int = DEFAULT_MAX_INLINE_BYTES) -> MappingPayload:
        """Measure this set for inlining, or refuse.

        Serialises the whole set, measures the UTF-8 body and raises
        :class:`MappingPayloadTooLarge` when it does not fit. Refusing is the point: a truncated
        set would drop mappings silently, and the ones it dropped are precisely those a reader
        would most want to audit (constitution I-5).
        """
        body, byte_size = _serialise([mapping.to_dict() for mapping in self.mappings])
        _refuse_oversize(byte_size, int(max_inline), f"mapping set {self.version_ref!r}")
        return MappingPayload(self.mapping_set_id, self.version, self.tenant_id, body, byte_size)

    def content_key(self) -> str:
        """Order-insensitive identity of the set, usable as a mapping-set version reference."""
        return content_key(
            {
                "mapping_set": self.mapping_set_id,
                "version": self.version,
                "tenant": self.tenant_id,
                "mappings": {mapping.content_key() for mapping in self.mappings},
            }
        )


def _filter(
    mappings: Iterable[SemanticMapping],
    reference: str,
    predicate: MatchPredicate | None,
    *,
    by_subject: bool,
) -> tuple[SemanticMapping, ...]:
    """One indexed listing, shared by the set and the registry so the two cannot disagree."""
    wanted_ref = normalize_type_ref(reference)
    wanted_predicate = MatchPredicate(predicate) if predicate is not None else None
    return tuple(
        mapping
        for mapping in mappings
        if (mapping.subject_ref if by_subject else mapping.object_ref) == wanted_ref
        and (wanted_predicate is None or mapping.predicate is wanted_predicate)
    )


class MappingRegistry:
    """An indexed, tenant-scoped store of recorded mappings.

    The registry answers the two questions an alignment actually gets asked - "what external
    terms do we align to for this internal concept?" and "which internal concepts align to this
    external term?" - and the two provenance questions beside them: by predicate and by mapping
    source. Every listing returns a canonically ordered ``tuple`` and is a pure function of what
    was registered, so results are reproducible across processes and runs (constitution VI).

    Registration is idempotent on *content*: recording an identical mapping again returns the
    stored object and changes nothing, which is what makes replaying an alignment set safe. What
    is never idempotent-and-silent is a genuine disagreement - two mappings for one pair with
    different predicates are two records, and :meth:`conflicts` reports them without picking a
    winner. See :meth:`mappings_for`, which is where that guarantee is stated in full.

    Unlike :class:`~semantic.vocabularies.ConceptScheme` this is a mutable store rather than a
    frozen value, because accumulating recorded claims is what it is for. The records it holds
    are frozen and content-addressed, and every listing is a fresh tuple, so nothing a caller is
    handed can be changed underneath it.
    """

    def __init__(
        self, tenant_id: str = "default-tenant", *, max_inline: int = DEFAULT_MAX_INLINE_BYTES
    ) -> None:
        self._tenant_id = str(tenant_id).strip()
        self._max_inline = int(max_inline)
        self._by_content: dict[str, SemanticMapping] = {}
        self._by_id: dict[str, str] = {}
        self._by_subject: dict[str, set[str]] = {}
        self._by_object: dict[str, set[str]] = {}
        self._by_predicate: dict[str, set[str]] = {}
        self._by_source: dict[str, set[str]] = {}
        self._by_set: dict[tuple[str, str], set[str]] = {}
        self._supersedes: dict[str, set[str]] = {}

    @property
    def tenant_id(self) -> str:
        return self._tenant_id

    @property
    def max_inline(self) -> int:
        return self._max_inline

    def __len__(self) -> int:
        return len(self._by_content)

    def __iter__(self) -> Iterator[SemanticMapping]:
        return iter(self.mappings())

    def __contains__(self, item: object) -> bool:
        needle = str(item)
        return needle in self._by_content or needle in self._by_id

    def __repr__(self) -> str:
        return f"MappingRegistry(tenant_id={self._tenant_id!r}, mappings={len(self)})"

    def register(self, mapping: SemanticMapping) -> SemanticMapping:
        """Record one mapping, or recognise it as already recorded.

        Idempotent on content: an identical mapping re-registered is a no-op returning the stored
        object, so replaying an alignment effort cannot inflate the store or perturb any listing.
        A mapping that differs in any digested field is a different claim and is stored
        alongside - never in place of - the existing one.

        Three things raise, all of them caller bugs rather than world content. A cross-tenant
        mapping raises :class:`TenantScopeRefused` (constitution IV). A payload that will not
        inline raises :class:`MappingPayloadTooLarge`, because a mapping is evidence and
        shortening it is not an option. A ``mapping_id`` already bound to different content
        raises :class:`MappingIdCollision`, because one id must not end up citing two claims.
        None of them rejects *content*: they refuse to record a record ambiguously.
        """
        if mapping.tenant_id and mapping.tenant_id != self._tenant_id:
            raise TenantScopeRefused(mapping.tenant_id, self._tenant_id)
        _refuse_oversize(
            _serialise(mapping.to_dict())[1], self._max_inline, "semantic mapping"
        )
        stored = mapping if mapping.mapping_id else mapping.with_id()
        content = stored.content_key()
        existing = self._by_content.get(content)
        if existing is not None:
            return existing
        if stored.mapping_id:
            bound = self._by_id.get(stored.mapping_id)
            if bound is not None and bound != content:
                raise MappingIdCollision(stored.mapping_id)
        self._by_content[content] = stored
        if stored.mapping_id:
            self._by_id.setdefault(stored.mapping_id, content)
        self._by_subject.setdefault(stored.subject_ref, set()).add(content)
        self._by_object.setdefault(stored.object_ref, set()).add(content)
        self._by_predicate.setdefault(str(stored.predicate), set()).add(content)
        if stored.mapping_source:
            self._by_source.setdefault(stored.mapping_source, set()).add(content)
        self._by_set.setdefault(
            (stored.mapping_set_id, stored.mapping_set_version), set()
        ).add(content)
        for superseded in stored.supersedes:
            self._supersedes.setdefault(superseded, set()).add(content)
        return stored

    def register_all(self, mappings: Iterable[SemanticMapping]) -> tuple[SemanticMapping, ...]:
        """Record several mappings, returning the stored objects in canonical order.

        Each is measured against the inline cap individually rather than as one batch body, so a
        single oversized mapping is named instead of an aggregate that hides which one it was.
        """
        return tuple(sorted((self.register(mapping) for mapping in mappings), key=_order_key))

    def register_set(self, mapping_set: MappingSet) -> MappingSet:
        """Record a whole set, after measuring the *set* payload against the inline cap.

        The per-mapping cap in :meth:`register` cannot see a set that is too large only in
        aggregate, so the batch is measured as it would actually be inlined - the same discipline
        ``events.ontology_pack`` applies to a pack descriptor. The returned set is a value
        reconstructed from what the registry now holds, which is how a caller sees that
        registration changed nothing it did not intend.
        """
        if mapping_set.tenant_id and mapping_set.tenant_id != self._tenant_id:
            raise TenantScopeRefused(mapping_set.tenant_id, self._tenant_id)
        mapping_set.payload(self._max_inline)
        for mapping in mapping_set:
            self.register(mapping)
        return self.mapping_set(mapping_set.mapping_set_id, mapping_set.version) or mapping_set

    def get(self, mapping_id: str) -> SemanticMapping | None:
        """One mapping by id or by content digest; ``None`` when unrecorded.

        Quietly ``None`` rather than raising: a reference to a mapping nobody registered is a
        normal answer in an open world, not an error (FR-001).
        """
        needle = str(mapping_id).strip()
        found = self._by_id.get(needle) or self._by_content.get(needle)
        return self._by_content.get(found) if found is not None else None

    def has(self, mapping_id: str) -> bool:
        return str(mapping_id).strip() in self._by_content or str(mapping_id).strip() in self._by_id

    def mappings(self) -> tuple[SemanticMapping, ...]:
        """Every recorded mapping, canonically ordered. The whole store, in one tuple."""
        return tuple(sorted(self._by_content.values(), key=_order_key))

    def mapping_ids(self) -> tuple[str, ...]:
        """Every recorded mapping's citable evidence reference, canonically ordered."""
        return tuple(sorted(mapping.evidence_ref for mapping in self._by_content.values()))

    def mappings_for(
        self,
        subject_ref: str,
        predicate: MatchPredicate | None = None,
        mapping_source: str | None = None,
    ) -> tuple[SemanticMapping, ...]:
        """Every recorded mapping asserted *from* one internal reference.

        **The return is a tuple and it is never collapsed.** If two mapping processes asserted
        different things about the same pair, both records are here, and no argument to this
        method can select one of them. That is the intended behaviour and not an oversight: a
        mapping is a claim, and a *conflicting* second mapping is data to be surfaced
        (:meth:`conflicts`), not something to auto-resolve. A registry that picked a winner
        would make the alignment unauditable while still putting the winner in use, and the
        platform has no standing to adjudicate between a lexical inference and a human mapping
        in the first place.

        The filters narrow the reporting, not the record: filtering by predicate or source decides
        what a caller is *looking at*, and every filtered-out mapping is still stored, still
        citable and still returned by an unfiltered call. Nothing here is ever used to reject
        content, and a reference no mapping mentions yields ``()`` rather than an error, because
        an unaligned term is admissible content (FR-001).
        """
        wanted_predicate = MatchPredicate(predicate) if predicate is not None else None
        wanted_source = str(mapping_source).strip() if mapping_source is not None else None
        return tuple(
            mapping
            for mapping in self._by_content.values()
            if mapping.subject_ref == normalize_type_ref(subject_ref)
            and (wanted_predicate is None or mapping.predicate is wanted_predicate)
            and (wanted_source is None or mapping.mapping_source == wanted_source)
        )

    def mappings_to(
        self, object_ref: str, predicate: MatchPredicate | None = None
    ) -> tuple[SemanticMapping, ...]:
        """Every recorded mapping asserted *to* one external reference. All matches, never one."""
        return _filter(self.mappings(), object_ref, predicate, by_subject=False)

    def resolve_external(
        self, subject_ref: str, predicate: MatchPredicate | None = None
    ) -> tuple[SemanticMapping, ...]:
        """``internal -> external``: the mappings recording where a concept reaches externally.

        Named as the question it answers ("what do we align this to?") rather than as a
        resolution, because nothing is being resolved to a single answer: the result may be empty,
        one record, or several disagreeing records, and all three are correct answers.
        """
        return _filter(self.mappings(), subject_ref, predicate, by_subject=True)

    def resolve_internal(
        self, object_ref: str, predicate: MatchPredicate | None = None
    ) -> tuple[SemanticMapping, ...]:
        """``external -> internal``: the mappings recording what an external term aligns to here.

        A single external term legitimately aligns to several internal concepts, and a single
        internal concept to several external ones. Both directions return every recorded claim
        for the same reason :meth:`mappings_for` does.
        """
        return self.mappings_to(object_ref, predicate)

    def external_refs_for(
        self, subject_ref: str, predicate: MatchPredicate | None = None
    ) -> tuple[str, ...]:
        """The distinct external references this internal concept has been aligned to.

        The convenience form of "what do we align to schema.org for this concept". Distinct, and
        canonically ordered, so a caller rendering a pick-list sees every candidate once - but
        note that collapsing *references* here is not collapsing *mappings*: the predicates,
        sources and confidences behind them are still available from :meth:`mappings_for`, and a
        reference aligned by two disagreeing processes appears once with both claims intact.
        """
        return tuple(
            sorted(
                {
                    mapping.object_ref
                    for mapping in self.resolve_external(subject_ref, predicate)
                }
            )
        )

    def internal_refs_for(
        self, object_ref: str, predicate: MatchPredicate | None = None
    ) -> tuple[str, ...]:
        """The distinct internal references this external term has been aligned to."""
        return tuple(
            sorted(
                {
                    mapping.subject_ref
                    for mapping in self.resolve_internal(object_ref, predicate)
                }
            )
        )

    def by_predicate(self, predicate: MatchPredicate) -> tuple[SemanticMapping, ...]:
        """Every mapping carrying one predicate - "show me everything claimed as an exact match".

        A predicate is a *characterisation of a claim*, so this listing is a way to find
        assertions to review, not a way to find facts: ``EXACT_MATCH`` here means a mapping
        process said so, and re-evaluating it is expected.
        """
        wanted = str(MatchPredicate(predicate))
        return tuple(
            sorted(self._by_content[key] for key in self._by_predicate.get(wanted, ()))
        )

    def by_mapping_source(self, mapping_source: str) -> tuple[SemanticMapping, ...]:
        """Every mapping produced by one source - "which mappings came from X?".

        The provenance question, and the one that makes an alignment set auditable: an
        unrecognised source yields ``()`` quietly, because a mapping from a source nobody
        recognises is a perfectly good record of somebody's claim.
        """
        wanted = str(mapping_source).strip()
        return tuple(sorted(self._by_content[key] for key in self._by_source.get(wanted, ())))

    def mapping_source_ids(self) -> tuple[str, ...]:
        """Every mapping source with at least one recorded mapping, canonically ordered."""
        return tuple(sorted(self._by_source))

    def cite(self, claim_ref: str, subject_ref: str) -> tuple[MappingCitation, ...]:
        """Every citation available for one internal reference, canonically ordered.

        What an assertion cites to justify a mapped typing: one citation per recorded mapping,
        each carrying the claim, its justification, its source and its provenance. Conflicting
        citations are all present here too, and a caller that notices two citations for one pair
        is looking at real data rather than at a bug in this method.
        """
        return tuple(
            mapping.cite(claim_ref) for mapping in self.mappings_for(subject_ref)
        )

    def evidence_refs_for(self, subject_ref: str) -> tuple[str, ...]:
        """The citable evidence references for one internal reference, canonically ordered.

        The shape an assertion wants to store: refs, not blobs, and every mapping behind them
        still retrievable (constitution I-5).
        """
        return tuple(sorted(mapping.evidence_ref for mapping in self.mappings_for(subject_ref)))

    def conflicts(
        self, subject_ref: str | None = None, object_ref: str | None = None
    ) -> tuple[MappingConflict, ...]:
        """Every pair carrying mutually incompatible mappings. Reported, never resolved.

        Conflict is the same narrow thing :meth:`SemanticMapping.conflicts_with` defines: one pair
        characterised with more than one predicate. Two sources agreeing on a predicate is
        corroboration and produces no conflict; two sources characterising the same pair
        differently produces exactly one :class:`MappingConflict` naming every side.

        There is no ``resolve`` step after this method, and that absence is deliberate. Choosing
        between contradictory alignment claims requires knowing which process is right, which is
        information this platform does not have; guessing would replace a recorded disagreement
        with a silent assumption. The correct downstream use is a graded ``Verdict.CONFLICTING``
        finding attached to whatever made the claim - a report the operator can read, never a
        reason to delete anything (FR-012).
        """
        candidates = self.mappings()
        if subject_ref is not None:
            wanted = normalize_type_ref(subject_ref)
            candidates = tuple(m for m in candidates if m.subject_ref == wanted)
        if object_ref is not None:
            wanted = normalize_type_ref(object_ref)
            candidates = tuple(m for m in candidates if m.object_ref == wanted)
        grouped: dict[tuple[str, str], list[SemanticMapping]] = {}
        for mapping in candidates:
            grouped.setdefault(mapping.pair, []).append(mapping)
        conflicts: list[MappingConflict] = []
        for pair, group in grouped.items():
            if len({m.predicate for m in group}) < 2:
                continue
            ordered = sorted(group, key=_order_key)
            conflicts.append(
                MappingConflict(
                    subject_ref=pair[0],
                    object_ref=pair[1],
                    mapping_ids=tuple(m.evidence_ref for m in ordered),
                    predicates=tuple(str(m.predicate) for m in ordered),
                    mapping_sources=tuple(m.mapping_source for m in ordered),
                    tenant_id=self._tenant_id,
                )
            )
        return tuple(sorted(conflicts, key=lambda conflict: conflict.pair))

    def has_conflicts(self, subject_ref: str | None = None) -> bool:
        """Whether any incompatible mappings exist, optionally scoped to one subject reference."""
        return bool(self.conflicts(subject_ref))

    def superseded_by(self, mapping_id: str) -> tuple[SemanticMapping, ...]:
        """Mappings recorded as correcting the given one, canonically ordered.

        Re-evaluation is additive: the corrected record stays in :meth:`mappings`, the correction
        names it in ``supersedes``, and both are retrievable. Nothing is withdrawn in place, so
        "what did we believe, and when did we change our mind" is answerable from the record
        (FR-004). An id nothing supersedes yields ``()``.
        """
        needle = str(mapping_id).strip()
        successors = self._supersedes.get(needle, ())
        return tuple(sorted((self._by_content[key] for key in successors), key=_order_key))

    def mapping_set(self, mapping_set_id: str, version: str | None = None) -> MappingSet | None:
        """The stored mappings of one set, reconstructed as a frozen value; ``None`` if unrecorded.

        ``version=None`` means the single recorded version, and is refused with a ``ValueError``
        when several versions of the same set id exist - quietly choosing one would make "which
        alignment is active?" a guess. Pass a version and the question is answered exactly.
        """
        wanted_id = str(mapping_set_id).strip()
        versions = sorted(v for (set_id, v) in self._by_set if set_id == wanted_id)
        if not versions:
            return None
        if version is None:
            if len(versions) > 1:
                raise ValueError(
                    f"mapping set {wanted_id!r} has versions {versions}; name one explicitly"
                )
            chosen = versions[0]
        else:
            chosen = str(version).strip()
            if chosen not in versions:
                return None
        return MappingSet(
            wanted_id,
            chosen,
            self._tenant_id,
            tuple(
                self._by_content[key]
                for key in self._by_set[(wanted_id, chosen)]
            ),
        )

    def mapping_sets(self) -> tuple[MappingSet, ...]:
        """Every recorded set, canonically ordered by ``(set_id, version)``."""
        return tuple(
            sorted(
                (self.mapping_set(set_id, version) for set_id, version in self._by_set),
                key=lambda mapping_set: (mapping_set.mapping_set_id, mapping_set.version),
            )
        )

    def mapping_set_ids(self) -> tuple[str, ...]:
        """Every recorded mapping-set id, canonically ordered."""
        return tuple(sorted({set_id for set_id, _ in self._by_set}))

    def predicates(self) -> tuple[str, ...]:
        """Every predicate present in the store, canonically ordered.

        A summary of what has been *claimed*, not of what holds: an ``exact_match`` here is a
        mapping process's characterisation, and re-evaluating it is expected.
        """
        return tuple(sorted(self._by_predicate))

    def pairs(self) -> tuple[tuple[str, str], ...]:
        """Every distinct ``(subject, object)`` pair recorded, canonically ordered."""
        return tuple(sorted({mapping.pair for mapping in self._by_content.values()}))

    def content_key(self) -> str:
        """Order-insensitive identity of the whole store, for proving two runs registered the same.

        Two registries holding the same mappings in a different order share this digest, which is
        what makes "did the mapping set change?" a decidable question rather than an impression.
        """
        return content_key(
            {
                "tenant": self._tenant_id,
                "mappings": {key for key in self._by_content},
                "supersedes": {key: sorted(value) for key, value in self._supersedes.items()},
            }
        )

    def snapshot(self) -> MappingProxyType:
        """An immutable read-only view of the recorded mappings, for handing a caller the store.

        The value is a fresh, canonically ordered copy, so it is a point-in-time observation
        rather than a live window that changes under the caller's feet.
        """
        return MappingProxyType(
            {key: mapping for key, mapping in self.mappings_by_content().items()}
        )

    def mappings_by_content(self) -> dict[str, SemanticMapping]:
        """Recorded mappings keyed by content digest - the storage view, in canonical order."""
        return {mapping.content_key(): mapping for mapping in self.mappings()}
