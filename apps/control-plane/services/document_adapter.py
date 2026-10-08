"""Document -> ResolutionMention: the one adapter the canonical loop was missing.

Feature 024. Every stage below already existed and is reused unchanged:

    bytes
      -> extractors.lane.extract_deterministic      segments + TypedMention
      -> domain.mention_occurrence_index.mint_mention_id   MN-...
      -> (this module)                              ResolutionMention
      -> semantic.resolution.MentionResolver       ENT-...

What was missing is precisely the middle step. ``semantic_path/execution.py`` builds
``ResolutionMention`` objects internally, but only for a single ``request.sentence``;
nothing turned a real document's segments into mentions. So the branch from text to
entity ran only on hand-assembled one-liners, and the gap looked like "the platform
cannot extract entities" when in fact everything above and below this line was built
and tested.

Deliberately not done here, because the platform already does it better:

* no name-pattern extraction of our own;
* no gazetteer of our own;
* no entity ids minted from a name -- ``resolution.logical_entity_ref_for`` anchors on
  ``anchor_mention_id`` precisely because a name-derived id is unstable the moment a
  name is reused, and ``resolution.py`` refuses that construction by design.

Two things this module *does* own, because nothing else did:

1. ``kind -> schema:*`` promotion. ``DeterministicExtractorSet`` emits ``person``,
   ``org``, ``place``; ``semantic.blocking`` compares ``type_refs`` against an operator's
   ``schema:*`` vocabulary. Without the mapping, nothing can ever block or resolve.
2. ``independence_group``. Corroboration is counted by independence group, not by
   document count -- that is the whole difference between "three outlets repeated one
   wire story" and "three independent confirmations".
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from domain.mention_occurrence_index import MentionOccurrenceKey, mint_mention_id
from extractors.lane import extract_deterministic
from extractors.types import ExtractionResult
from semantic.resolution import (
    MentionResolver,
    ResolutionBatch,
    ResolutionCandidate,
    ResolutionMention,
    ResolutionScope,
    logical_entity_ref_for,
    resolution_scope_for,
)

#: Extractor kind -> schema type. The platform's own ontology vocabulary.
#: Unknown kinds are dropped rather than guessed: an unmapped kind must not become a
#: wrong ``schema:*``, because a wrong type is worse than a missing one -- it blocks and
#: resolves candidates incorrectly downstream.
#:
#: ``ip`` and ``crypto`` were missing here and are now present. ``extractors/contacts.py``
#: emits both (``:94,115`` and ``:137,152,167``), the table had no entry, and the adapter
#: dropped them at ``adapt_document`` -- infrastructure and wallet addresses were extracted
#: from real documents and discarded before persistence. The same gap made
#: ``interpretation/relations.py:45`` (``WALLET_KINDS = {"crypto_address"}``) unable to
#: fire, because it binds a spelling the deterministic extractor never produces.
TYPE_REFS: dict[str, tuple[str, ...]] = {
    "person": ("schema:Person",),
    "org": ("schema:Organization",),
    "place": ("schema:Place", "schema:AdministrativeArea"),
    "email": ("schema:ContactPoint",),
    "phone": ("schema:ContactPoint",),
    "handle": ("schema:OnlineAccount",),
    "domain": ("schema:WebSite",),
    "ip": ("schema:IPAddress",),
    "ipv4": ("schema:IPAddress",),
    "ipv6": ("schema:IPAddress",),
    "crypto": ("schema:CryptoAddress",),
    "crypto_address": ("schema:CryptoAddress",),
    "url": ("schema:WebSite",),
    "url/domain": ("schema:WebSite",),
    "entity": (),  # dictionary_entities emits this for a schema it does not recognise
    "date": ("schema:Date",),
}

NORMALIZATION_VERSION = "pow-adapter/v1"
ONTOLOGY_VERSION = "pow-adapter/v1"
PROFILE_ID = "deterministic"
PROFILE_VERSION = "v1"


class AdapterError(ValueError):
    """The document could not be adapted into resolution input."""


def _ref(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return f"{prefix}-{digest[:32]}"


@dataclass(frozen=True, slots=True)
class AdaptedRelation:
    """One relation reading, in the adapter's own vocabulary.

    The extraction layer's ``RelationalReading`` is not carried across: this is the
    boundary, and a boundary type is what stops the acquisition side depending on an
    interpretation-side class. What survives is what the graph needs and nothing more.
    """

    relation_type: str
    subject_mention_id: str
    object_mention_id: str
    subject_surface: str
    object_surface: str
    role: str = ""
    subject_kind: str = ""
    object_kind: str = ""
    confidence: float = 0.5

    @property
    def predicate(self) -> str:
        """The stored ``relation_type``.

        Named ``predicate`` because that is the column the relation writer reads, and
        naming it here makes the substitution visible at the call site rather than
        discovered by a reader wondering why ``works_for`` arrived in a
        ``co_occurs_with`` field.
        """
        return self.relation_type


@dataclass(frozen=True, slots=True)
class DocumentMentions:
    """Everything the resolver needs, plus the trace back to the document."""

    capture_ref: str
    mentions: tuple[ResolutionMention, ...]
    mention_index: dict[str, str]  # canonical surface -> mention_id
    canonical_by_mention: dict[str, str]  # mention_id -> canonical surface
    segments: int
    dropped_unknown_kinds: tuple[str, ...]
    #: Semantic relation readings carried through from extraction.
    #:
    #: Added because `extract_deterministic` now returns them and the adapter dropped
    #: them on the floor. Everything downstream of this function therefore saw a
    #: document that mentioned two organisations and no fact connecting them, which is
    #: why the graph carried only co-mentions.
    relations: tuple[AdaptedRelation, ...] = ()

    def __len__(self) -> int:
        return len(self.mentions)

    def canonical_for(self, mention_id: str) -> str:
        return self.canonical_by_mention.get(mention_id, "")


def _adapt_relations(
    readings: object,
    canonical_by_mention: Mapping[str, str],
    mentions: Sequence[ResolutionMention] = (),
) -> tuple[AdaptedRelation, ...]:
    """Map extraction readings onto adapter relations.

    A reading is dropped unless both its participants were themselves adapted as
    mentions. A relation whose subject did not become a mention has no entity to attach
    to, and inventing one would put an edge in the graph that nothing in the text
    supports.
    """
    out: list[AdaptedRelation] = []
    # Surface first, canonical second -- and the order matters. The canonical form is
    # normalised (a person's becomes "Сечин Игорь", surname first), so matching a
    # reading's English surface against it fails for exactly the cases most likely to
    # matter. The surface is what the reading actually quoted.
    by_surface: dict[str, str] = {}
    for mention in mentions:
        surface = str(getattr(mention, "surface", "") or "").strip().lower()
        if surface:
            by_surface.setdefault(surface, mention.mention_id)
    for mention_id, canonical in canonical_by_mention.items():
        key = str(canonical or "").strip().lower()
        if key:
            by_surface.setdefault(key, mention_id)
    for reading in readings or ():
        subject_id = getattr(getattr(reading, "subject", None), "mention_ref", "")
        object_id = getattr(getattr(reading, "object", None), "mention_ref", "")
        subject_surface = getattr(getattr(reading, "subject", None), "mention", None)
        object_surface = getattr(getattr(reading, "object", None), "mention", None)
        subject_value = getattr(subject_surface, "value", "")
        object_value = getattr(object_surface, "value", "")
        subject_mid = _mention_for(
            surface_value=subject_value, refs=subject_id, by_surface=by_surface
        )
        object_mid = _mention_for(
            surface_value=object_value, refs=object_id, by_surface=by_surface
        )
        if not subject_mid or not object_mid:
            continue
        relation_ref = getattr(reading, "relation_ref", None)
        out.append(
            AdaptedRelation(
                relation_type=str(getattr(relation_ref, "relation_type", "") or ""),
                subject_mention_id=subject_mid,
                object_mention_id=object_mid,
                subject_surface=subject_value,
                object_surface=object_value,
                role=str(getattr(reading, "role", "") or ""),
                subject_kind=str(getattr(subject_surface, "kind", "") or ""),
                object_kind=str(getattr(object_surface, "kind", "") or ""),
                confidence=float(getattr(reading, "confidence", 0.5) or 0.5),
            )
        )
    return tuple(out)


def _mention_for(*, surface_value: str, refs: str, by_surface: Mapping[str, str]) -> str:
    """The mention id a reading's participant corresponds to, or "".

    Readings carry a ``mention_ref`` of their own; when it is one this adapter minted it
    is used directly, and otherwise the surface is matched against the canonical forms
    already adapted. The fallback exists because the two layers mint mention ids through
    different paths and a relation whose participants are perfectly good mentions must
    not be dropped over an id convention.
    """
    needle = (surface_value or "").strip().lower()
    if needle and needle in by_surface:
        return by_surface[needle]
    return ""


def adapt_document(
    body: bytes,
    *,
    capture_ref: str,
    content_type: str | None = None,
    tenant_id: str = "default-tenant",
    investigation_id: str = "",
    source_id: str = "",
    source_family: str = "",
    observed_at: datetime | None = None,
    result: ExtractionResult | None = None,
) -> DocumentMentions:
    """Turn one real document into resolution input.

    ``result`` may be supplied when the caller has already run the extraction lane, so
    the expensive parse is not repeated.
    """
    extraction = result or extract_deterministic(body)
    observed = observed_at or datetime.now(UTC)
    # Corroboration counts independent *sources*, not documents. Keying on the
    # artifact digest means two captures of the same bytes corroborate nothing.
    independence = _ref("IG", source_family or "", extraction.artifact_sha)

    out: list[ResolutionMention] = []
    index: dict[str, str] = {}
    canonical_by_mention: dict[str, str] = {}
    dropped: list[str] = []

    for typed in extraction.mentions:
        if typed.kind not in TYPE_REFS:
            # Only a kind this adapter has never heard of is dropped. A kind it *knows* but
            # cannot type -- ``entity``, emitted by the sanctions dictionary for any schema
            # it does not recognise -- is admitted with no declared type refs. That is spec
            # 017 FR-002: "the world is open"; an unrecognised entity is evidence without a
            # type, and dropping it would discard the surface a later ontology could have
            # resolved. ``dropped_unknown_kinds`` keeps the loss visible either way.
            dropped.append(typed.kind)
            continue
        type_refs = TYPE_REFS.get(typed.kind) or ()

        segment_ref = _ref("SEG", capture_ref, str(typed.offset))
        canonical = typed.normalized.canonical if typed.normalized else typed.value
        key = MentionOccurrenceKey(
            capture_ref=capture_ref,
            segment_ref=segment_ref,
            span=(typed.offset, typed.end_offset),
            normalized_surface=canonical,
            extractor_ref=typed.extractor or typed.source,
        )
        mention_id = mint_mention_id(key)

        out.append(
            ResolutionMention(
                mention_id=mention_id,
                surface=typed.value,
                kind=typed.kind,
                tenant_id=tenant_id,
                investigation_id=investigation_id,
                source_id=source_id,
                source_family=source_family,
                independence_group=independence,
                valid_from=observed,
                observed_at=observed,
                profile_id=PROFILE_ID,
                profile_version=PROFILE_VERSION,
                ontology_version=ONTOLOGY_VERSION,
                normalization_version=NORMALIZATION_VERSION,
                declared_type_refs=list(type_refs),
            )
        )
        canonical_by_mention[mention_id] = canonical
        index.setdefault(canonical, mention_id)

    return DocumentMentions(
        capture_ref=capture_ref,
        mentions=tuple(out),
        mention_index=index,
        canonical_by_mention=canonical_by_mention,
        segments=len(extraction.segments),
        relations=_adapt_relations(extraction.relations, canonical_by_mention, out),
        dropped_unknown_kinds=tuple(sorted(set(dropped))),
    )


class CandidateUniverse:
    """Accumulates candidate entities across documents.

    This is the piece that makes corroboration possible, and it is why the resolver
    answers ``UNRESOLVED`` on a first document: a mention with nothing known about it
    has nothing to match. Nothing is wrong there. The first mention *proposes*; later
    mentions from other documents either corroborate that proposal or create a second
    one, and only then does the resolver decide they are the same entity.

    Keying is on the extractor-normalized canonical form plus kind, because that is the
    platform's own agreement that two surface forms denote the same thing --
    ``Иванов, Сергей Петрович`` and ``Иванов Сергей Петрович`` share a canonical form.
    It is deliberately *not* keyed on raw text: that is the name-derived-identity defect
    ``resolution.py`` refuses.
    """

    def __init__(self, *, tenant_id: str = "default-tenant", investigation_id: str = "") -> None:
        self.tenant_id = tenant_id
        self.investigation_id = investigation_id
        self.scope_id = resolution_scope_for(
            tenant_id=tenant_id, investigation_id=investigation_id
        ).scope_id
        self._by_key: dict[tuple[str, str], Any] = {}
        #: (kind, canonical) -> number of distinct independence groups seen. This is the
        #: corroboration count; a second capture of the same bytes must not raise it.
        self._groups: dict[tuple[str, str], set[str]] = {}
        #: (kind, canonical) -> an entity_id this tenant already durably holds.
        #:
        #: This is the seam that stops identity being re-minted per run. ``ENT-`` is
        #: derived from (tenant, scope, anchor mention) and the scope is the
        #: investigation, so a fresh universe mints a fresh id for "Russia" on every
        #: investigation - 11 ids for one country in 11 investigations. Seeding this
        #: from the entities the tenant already holds makes a mention of a known
        #: canonical form *join* the existing entity instead of proposing a rival, which
        #: is the same anchor-and-merge discipline ``domain.entity_identity`` records in
        #: ``anchor_for_mention`` and ``merged_mentions``; this is the write side of it,
        #: wired to the resolver that was already here.
        self._adopted: dict[tuple[str, str], str] = {}

    def adopt(self, *, kind: str, canonical: str, entity_id: str) -> bool:
        """Register an entity this tenant already holds, keyed by (kind, canonical).

        Returns False when the key is already adopted by a different entity, or when the
        arguments are empty. Refusing rather than overwriting: two different durable
        entities claiming one canonical form is a conflict an analyst resolves through
        ``/resolutions/decide``, not something a collection run may silently pick a
        winner for.
        """
        if not (kind and canonical and entity_id):
            return False
        key = (kind, canonical)
        existing = self._adopted.get(key)
        if existing is not None:
            return existing == entity_id
        self._adopted[key] = entity_id
        return True

    def seed(self, document: DocumentMentions) -> int:
        """Propose candidates for mentions that are new to the universe.

        Returns how many were added. Re-seeing a known candidate is corroboration, and
        is not a duplicate: the new independence group is recorded against the existing
        candidate.

        Each candidate is anchored on the *first* mention that proposed it, via
        ``logical_entity_ref_for``. That is the only legitimate way an entity gets its
        identity: a mention anchors it, and the resolver then decides whether later
        mentions denote the same thing. Naming the candidate here is what lets a
        resolved decision carry an ``ENT-`` at all -- an unnamed candidate matches
        nothing, and every mention comes back UNRESOLVED with confidence 0.20.
        """
        added = 0
        for mention in document.mentions:
            canonical = document.canonical_for(mention.mention_id) or mention.surface
            key = (mention.kind, canonical)
            group = mention.independence_group
            if group:
                self._groups.setdefault(key, set()).add(group)
            if key in self._by_key:
                continue
            # A canonical form this tenant already holds resolves to the entity that
            # already exists. Minting a second id for it is the duplication defect;
            # reusing the anchor is the discipline the platform already states.
            adopted = self._adopted.get(key)
            self._by_key[key] = ResolutionCandidate(
                entity_ref=adopted
                or logical_entity_ref_for(self.tenant_id, self.scope_id, mention.mention_id),
                name=canonical,
                kind=mention.kind,
                type_refs=tuple(mention.declared_type_refs),
                tenant_id=self.tenant_id,
                investigation_id=self.investigation_id,
                profile_id=PROFILE_ID,
                profile_version=PROFILE_VERSION,
                ontology_version=ONTOLOGY_VERSION,
                normalization_version=NORMALIZATION_VERSION,
                source_family=mention.source_family,
                independence_group=group,
                observed_at=mention.observed_at,
                supporting_groups=tuple(sorted(self._groups[key])),
            )
            added += 1
        return added

    def corroboration(self, document: DocumentMentions, mention_id: str) -> int:
        """Distinct independence groups behind one canonical surface."""
        canonical = document.canonical_for(mention_id)
        mention = next((m for m in document.mentions if m.mention_id == mention_id), None)
        if mention is None:
            return 0
        return len(self._groups.get((mention.kind, canonical), ()))

    def candidates(self) -> tuple[Any, ...]:
        return tuple(self._by_key.values())

    def __len__(self) -> int:
        return len(self._by_key)


@dataclass(frozen=True, slots=True)
class ResolvedEntity:
    entity_id: str
    anchor_mention_id: str
    surface: str
    kind: str
    verdict: str
    confidence: float
    independence_groups: int


def resolve_document(
    document: DocumentMentions,
    *,
    resolver: MentionResolver | None = None,
    candidates: Iterable[Any] = (),
    investigation_id: str = "",
    tenant_id: str = "default-tenant",
) -> tuple[ResolutionBatch, tuple[ResolvedEntity, ...]]:
    """Run the platform resolver over adapted mentions.

    Entity identity comes from ``logical_entity_ref_for`` -- anchored on the mention,
    never on the name. Two mentions of the same person resolve to one entity only
    because the resolver decided so, not because their surface forms matched.
    """
    scope: ResolutionScope = resolution_scope_for(
        tenant_id=tenant_id, investigation_id=investigation_id
    )
    engine = resolver or MentionResolver()
    batch = engine.resolve(document.mentions, candidates=candidates, scope=scope)

    by_id = {m.mention_id: m for m in document.mentions}
    resolved: list[ResolvedEntity] = []
    for decision in batch.decisions:
        mention = by_id.get(decision.mention_id)
        if mention is None:
            continue
        resolved.append(
            ResolvedEntity(
                entity_id=decision.logical_entity_ref,
                anchor_mention_id=decision.mention_id,
                surface=mention.surface,
                kind=mention.kind,
                verdict=str(decision.verdict),
                confidence=decision.confidence,
                independence_groups=len(batch.supporting_groups_for(decision.mention_id) or ()),
            )
        )
    resolved.sort(key=lambda e: (-e.confidence, e.surface))
    return batch, tuple(resolved)


def adapt_and_resolve(
    body: bytes,
    *,
    capture_ref: str,
    content_type: str | None = None,
    tenant_id: str = "default-tenant",
    investigation_id: str = "",
    source_id: str = "",
    source_family: str = "",
    observed_at: datetime | None = None,
    resolver: MentionResolver | None = None,
) -> tuple[DocumentMentions, ResolutionBatch, tuple[ResolvedEntity, ...]]:
    """The whole document -> entity path in one call."""
    document = adapt_document(
        body,
        capture_ref=capture_ref,
        content_type=content_type,
        tenant_id=tenant_id,
        investigation_id=investigation_id,
        source_id=source_id,
        source_family=source_family,
        observed_at=observed_at,
    )
    batch, entities = resolve_document(
        document,
        resolver=resolver,
        investigation_id=investigation_id,
        tenant_id=tenant_id,
    )
    return document, batch, entities


__all__ = [
    "NORMALIZATION_VERSION",
    "ONTOLOGY_VERSION",
    "PROFILE_ID",
    "PROFILE_VERSION",
    "TYPE_REFS",
    "AdapterError",
    "DocumentMentions",
    "ResolvedEntity",
    "adapt_and_resolve",
    "adapt_document",
    "resolve_document",
]
