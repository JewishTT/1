"""The semantic regime an assertion was interpreted under - as an overlay, not as a field.

Feature 017, T021, FR-014. FR-014 says ``EvidenceContext`` MUST carry the semantic regime:
active profile, profile version, ontology version, mapping set, validation profile, temporal
frame, localisation and language, and that an assertion MUST be storable with no semantic
commitment at all. The first instinct is to open ``apps/shared/domain/evidence_context.py``
and add the missing columns. **That would be wrong, and this module is the reason it is
obviously wrong.**

``EvidenceContext`` is a *content-addressed* record. Its ``context_id`` is ``CX-`` plus
``digest128`` over the canonical frame, and ``__post_init__`` **verifies** the supplied id
against a recomputation rather than trusting it. So adding one field does not "add a column" -
it changes the material every frame is addressed by, which means every context id already
persisted, every ``frame_fingerprint`` unique index, every claim whose ``context_ref`` points at
one, and every event payload carrying a frame becomes a row that no longer addresses to its own
content and can no longer be loaded at all. A stored frame would fail construction with
``context_id_mismatch`` rather than degrade: the failure is total, and it is total *because* the
frame verifies its own address. That property is the most valuable thing feature 016 built and it
is incompatible with a feature boundary quietly walking through it.

So the regime is a **separate frozen value that references the frame**, and
:func:`extend_context` composes the two without either one being edited:

* :class:`SemanticRegime` is its own content-addressed object, digested by the same
  :func:`~semantic.contracts.content_key` every other semantic object uses, so it introduces no
  second hashing dialect (constitution VII).
* It holds ``context_ref`` - the parent frame it was declared against - and the direction of the
  link is deliberate. The regime points at the frame; the frame never points at the regime. A
  one-way link is what lets the frame stay byte-identical, and it is also the honest shape:
  the frame is evidence about where a claim came from, and "which instruments were in play" is a
  separate record about how it was read.
* :func:`extend_context` returns a **new** frame built with :func:`dataclasses.replace`, with the
  regime's pinned values (``ontology_version``, ``language``, ``location_context``,
  ``policy_snapshot_ref``) filled in and a **freshly derived** ``context_id``. The original is
  frozen, untouched, and keeps its id forever. This is exactly the monotonic discipline D5 sets
  out for typing in the first place: attaching a regime adds a claim, it never rewrites one.

What FR-014 still gets, unchanged: a caller reads the regime, sees the profile, the versions,
the mapping set and the validation profile, and can state precisely under which interpretation an
assertion was recorded. What it does not get, and cannot get on these terms: a single row that
holds both. That is a deliberate trade of denormalised storage for not invalidating a
content-addressed record owned by another feature, and it is the right trade - the alternative
repairs a readability convenience with a fleet-wide id migration.

**The no-commitment path is explicit, not incidental.** :meth:`SemanticRegime.uncommitted` and
:func:`uncommitted_regime` build the regime an assertion carries when nothing interpreted it: no
profile, no mapping set, no types, ``commitment = UNCOMMITTED``. US3 is the case - an
unclassifiable token is bound to nothing and the mention is stored anyway - and FR-014 requires
the context to *record* that, so "we did not interpret this" is a storable fact rather than a
missing value. :meth:`SemanticRegime.carries_semantic_commitment` is the predicate a caller uses
to tell the two situations apart, and it is the same one
:meth:`~semantic.contracts.TypeAssertion.carries_semantic_commitment` already answers on the
assertion side.

Commitment is monotonic here exactly as it is on :class:`~semantic.contracts.SemanticStatus`:
:meth:`SemanticRegime.promoted` returns the same value when asked for a weaker rung, and
:meth:`with_profile` / :meth:`with_mapping_set` only ever add an instrument, never clear one. A
regime that is later re-interpreted under a different profile gets a **new** regime that
supersedes the old one; the old one stays readable (FR-004).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from domain.evidence_context import EvidenceContext
from semantic.contracts import content_key
from semantic.mappings import MappingSet
from semantic.profiles import ProfileResolution, SemanticProfile
from semantic.vocabularies import normalize_type_ref

__all__ = [
    "DEFAULT_VALIDATION_PROFILE",
    "SemanticCommitment",
    "SemanticRegime",
    "ValidationProfile",
    "extend_context",
    "uncommitted_regime",
]


class SemanticCommitment(StrEnum):
    """How far up the ladder one assertion was carried in *this* regime (FR-014, FR-018).

    A platform vocabulary rather than a world one, and the distinction is why it is an enum at
    all. Unlike a type reference, whose value space is open because the world is open, this names
    stages **of the platform's own commitment process**, which the platform has to be able to
    order in order to refuse a downgrade. :meth:`rank` is that ordering, and it is the same shape
    as :meth:`semantic.contracts.SemanticStatus.rank` for the same reason.

    ``UNCOMMITTED`` is the load-bearing member and it is a first-class state, not a null. An
    assertion interpreted under no instrument at all is stored, queryable and resolvable, and the
    regime says so explicitly (FR-014, US3).
    """

    UNCOMMITTED = "uncommitted"
    TYPED = "typed"
    MAPPED = "mapped"

    def rank(self) -> int:
        """Position on the ladder; higher is a stronger semantic commitment."""
        return _COMMITMENT_RANK[self]


_COMMITMENT_RANK: dict[SemanticCommitment, int] = {
    SemanticCommitment.UNCOMMITTED: 0,
    SemanticCommitment.TYPED: 1,
    SemanticCommitment.MAPPED: 2,
}


class ValidationProfile(StrEnum):
    """Which validation configuration was in force when the assertion was read.

    The *name* of a validation policy, not its contents: the graded machinery itself lives in
    :mod:`semantic.validation`, and a regime records which configuration was applied rather than
    re-describing it. :data:`~semantic.operators.ValidationPolicy` is the per-operator setting
    this pairs with, and the two are independent on purpose - an operator may validate
    conservatively inside a permissive regime without either record changing.

    The value space is **open in practice**. The field is stored as text and an unrecognised
    name is retained verbatim and reported by
    :meth:`SemanticRegime.known_validation_profile`, exactly as
    :class:`~semantic.profiles.ScopeTag` reports a scope kind this build has no name for. A
    regime recorded by a newer build must still load here (FR-001), so coercing an unknown name
    would trade a reportable fact for an unopenable record.
    """

    LAYERED = "layered"
    PERMISSIVE = "permissive"
    CONSERVATIVE = "conservative"
    SIDECAR = "shacl_sidecar"


DEFAULT_VALIDATION_PROFILE: str = ValidationProfile.LAYERED.value

_KNOWN_VALIDATION_PROFILES: frozenset[str] = frozenset(
    str(profile) for profile in ValidationProfile
)


def _text(value: object) -> str:
    """One canonical string field: reference-shaped values keep their case (see
    :func:`semantic.vocabularies.normalize_type_ref` - a reference is an opaque identifier)."""
    return normalize_type_ref(value) if value is not None else ""


@dataclass(frozen=True)
class SemanticRegime:
    """The instruments in play when one assertion was read, as a standalone value.

    Every field is a **reference to an instrument**, never an assertion about a record. A regime
    saying ``profile ``investigation.base@2`` was active says nothing whatever about the entity
    it is paired with, in the same way and for the same reason as
    :class:`~semantic.profiles.SemanticProfile` itself: this object answers "what did we believe
    when we read that?", never "what may exist" (spec scope guard).

    The temporal frame, localisation and language that FR-014 also names are **referenced, not
    copied**: ``temporal_frame_ref`` points at the worldline record whose interval applies, while
    the interval itself (``valid_from`` / ``valid_to``) and the localisation string stay on the
    parent :class:`~domain.evidence_context.EvidenceContext`, which already carries both. Copying
    them here would create two homes for one fact and a second thing to drift - the exact
    duplication that is refused everywhere else in this feature.

    ``tenant_id`` is here for the same reason it is on every other semantic record: a regime
    describes one tenant's instruments, and reading it across a boundary would disclose what that
    tenant had available (constitution IV).

    Frozen and content-addressed. :meth:`evaluation_material` returns exactly what
    :meth:`content_key` digests, so an independent process can recompute the regime and diff it
    rather than trusting a stored id - the re-evaluability discipline
    :meth:`semantic.mappings.SemanticMapping.evaluation_material` established.
    """

    context_ref: str = ""
    tenant_id: str = "default-tenant"

    profile_ref: str = ""
    profile_version: str = ""
    ontology_version: str = ""
    mapping_set_id: str = ""
    mapping_set_version: str = ""
    validation_profile: str = DEFAULT_VALIDATION_PROFILE
    policy_snapshot_ref: str = ""
    operator_ref: str = ""

    commitment: SemanticCommitment = SemanticCommitment.UNCOMMITTED
    localization: str = ""
    language: str = ""
    temporal_frame_ref: str = ""
    supersedes: str = ""

    note: str = ""
    recorded_at: datetime | None = None
    regime_id: str = ""

    def __post_init__(self) -> None:
        for name in (
            "context_ref",
            "profile_ref",
            "profile_version",
            "ontology_version",
            "mapping_set_id",
            "mapping_set_version",
            "policy_snapshot_ref",
            "operator_ref",
            "localization",
            "language",
            "temporal_frame_ref",
            "supersedes",
        ):
            object.__setattr__(self, name, _text(getattr(self, name)))
        object.__setattr__(self, "tenant_id", _text(self.tenant_id) or "default-tenant")
        object.__setattr__(self, "validation_profile", _text(self.validation_profile))
        object.__setattr__(self, "note", str(self.note))
        object.__setattr__(self, "commitment", SemanticCommitment(self.commitment))
        if self.recorded_at is not None and not isinstance(self.recorded_at, datetime):
            raise TypeError(
                f"recorded_at must be a datetime or None, got {self.recorded_at!r}"
            )
        addressed = content_key(self.evaluation_material())
        if not self.regime_id:
            object.__setattr__(self, "regime_id", addressed)
        elif self.regime_id != addressed:
            raise ValueError(
                f"regime carries {self.regime_id!r} but its own content addresses to "
                f"{addressed!r}; a content address is verified, never trusted"
            )

    @classmethod
    def uncommitted(
        cls,
        context_ref: str = "",
        *,
        tenant_id: str = "default-tenant",
        validation_profile: str = DEFAULT_VALIDATION_PROFILE,
        temporal_frame_ref: str = "",
        language: str = "",
        localization: str = "",
        note: str = "",
        recorded_at: datetime | None = None,
    ) -> SemanticRegime:
        """The regime of an assertion that carries **no** semantic commitment (FR-014, US3).

        This is the explicit path the spec requires, and it is a first-class constructor rather
        than the absence of one. An extractor that finds an unclassifiable token binds nothing,
        stores the mention, and records that the record was read under no instruments at all -
        which is a fact, is worth auditing, and is emphatically not a gap in the record. The
        returned regime has no profile, no mapping set and no ontology version, so
        :meth:`carries_semantic_commitment` is ``False`` and every downstream check that would
        need an instrument has a truthful ``UNKNOWN`` to report.
        """
        return cls(
            context_ref=context_ref,
            tenant_id=tenant_id,
            validation_profile=validation_profile,
            commitment=SemanticCommitment.UNCOMMITTED,
            temporal_frame_ref=temporal_frame_ref,
            language=language,
            localization=localization,
            note=note,
            recorded_at=recorded_at,
        )

    @classmethod
    def from_profile(
        cls,
        profile: SemanticProfile | ProfileResolution,
        *,
        context_ref: str = "",
        ontology_version: str = "",
        mapping_set: MappingSet | None = None,
        validation_profile: str = DEFAULT_VALIDATION_PROFILE,
        operator_ref: str = "",
        language: str = "",
        localization: str = "",
        temporal_frame_ref: str = "",
        note: str = "",
        recorded_at: datetime | None = None,
    ) -> SemanticRegime:
        """Bind a profile - or a whole resolved lineage - into a regime.

        Accepts a :class:`~semantic.profiles.ProfileResolution` as readily as a bare
        :class:`~semantic.profiles.SemanticProfile`, because the interesting regime is usually
        the *inherited* one and a caller should not have to re-derive it. The regime records the
        requested profile and its version and nothing about the lineage: which ancestors
        contributed which instruments is the resolution's question
        (:meth:`~semantic.profiles.ProfileResolution.declared_by`), and duplicating the union
        here would give the lineage two homes.
        """
        resolved = profile.profile if isinstance(profile, ProfileResolution) else profile
        regime = cls(
            context_ref=context_ref,
            tenant_id=resolved.tenant_id,
            profile_ref=resolved.profile_id,
            profile_version=resolved.version,
            ontology_version=ontology_version,
            validation_profile=validation_profile,
            operator_ref=operator_ref,
            language=language,
            localization=localization,
            temporal_frame_ref=temporal_frame_ref,
            note=note,
            recorded_at=recorded_at,
        )
        return regime.with_mapping_set(mapping_set) if mapping_set is not None else regime

    @property
    def profile_version_ref(self) -> str:
        """``"profile_id@version"``, or ``""`` when no profile was bound. Reads back on sight."""
        return f"{self.profile_ref}@{self.profile_version}" if self.profile_ref else ""

    @property
    def mapping_set_version_ref(self) -> str:
        """``"set_id@version"``, or ``""`` when no mapping set was bound."""
        if not self.mapping_set_id:
            return ""
        return f"{self.mapping_set_id}@{self.mapping_set_version}"

    @property
    def identity(self) -> tuple[str, str]:
        """``(tenant, context_ref)`` - the frame this regime interprets.

        Deliberately not the content digest: two regimes read the same frame under different
        profiles are two readings of one frame, both retained, and :attr:`regime_id` distinguishes
        them.
        """
        return (self.tenant_id, self.context_ref)

    def carries_semantic_commitment(self) -> bool:
        """Whether any semantic instrument was actually bound.

        ``False`` for a genuinely uninterpreted assertion and the predicate FR-014 turns on. Note
        that the *ladder rung* is not the test: a regime that names a profile while recording
        ``UNCOMMITTED`` describes a regime that was available and was not used, which is a real
        and different situation from having no regime at all.
        """
        return bool(self.profile_ref or self.mapping_set_id or self.ontology_version)

    def known_validation_profile(self) -> ValidationProfile | None:
        """The named :class:`ValidationProfile`, or ``None`` if this build has never heard it.

        A diagnostic, and the reason :attr:`validation_profile` is stored as text: a regime
        written by a newer build must still load here, and a name this build cannot interpret is
        better retained and reported than rejected at construction (FR-001).
        """
        try:
            return ValidationProfile(self.validation_profile)
        except ValueError:
            return None

    def instruments(self) -> tuple[str, ...]:
        """Every instrument actually bound, canonically ordered - "what was in play here?".

        ``("")``-free by construction, so a caller rendering the answer never has to filter, and
        empty means the honest answer: nothing was in play.
        """
        return tuple(
            sorted(
                {
                    ref
                    for ref in (
                        self.profile_version_ref,
                        self.ontology_version,
                        self.mapping_set_version_ref,
                        self.validation_profile,
                        self.policy_snapshot_ref,
                        self.operator_ref,
                    )
                    if ref
                }
            )
        )

    def promoted(self, commitment: SemanticCommitment | str) -> SemanticRegime:
        """A stronger version of this regime, or this same value when not stronger.

        Returns ``self`` for a non-upgrade, so a caller can apply a promotion unconditionally and
        never perform a destructive downgrade. The rung is moved, never the instruments: a
        re-read that reached a mapped concept still happened in the profile that was active.
        """
        wanted = SemanticCommitment(commitment)
        if wanted.rank() <= self.commitment.rank():
            return self
        return replace(self, commitment=wanted, regime_id="")

    def with_profile(self, profile: SemanticProfile | ProfileResolution) -> SemanticRegime:
        """Bind a profile, adding to whatever was already bound. Never clears.

        Monotone by construction: the current profile reference is kept as
        :attr:`supersedes` so the earlier reading stays reconstructable, and the result is a new
        value with a new digest rather than an edit of this one (FR-004).
        """
        resolved = profile.profile if isinstance(profile, ProfileResolution) else profile
        if self.profile_ref and self.profile_ref != resolved.profile_id:
            return replace(
                self,
                profile_ref=resolved.profile_id,
                profile_version=resolved.version,
                supersedes=self.supersedes or self.profile_version_ref,
                regime_id="",
            )
        if self.profile_ref:
            return self
        return replace(
            self,
            profile_ref=resolved.profile_id,
            profile_version=resolved.version,
            regime_id="",
        )

    def with_mapping_set(self, mapping_set: MappingSet) -> SemanticRegime:
        """Bind a mapping set. Never clears an existing binding."""
        if self.mapping_set_id and self.mapping_set_id != mapping_set.mapping_set_id:
            return replace(
                self,
                mapping_set_id=mapping_set.mapping_set_id,
                mapping_set_version=mapping_set.version,
                regime_id="",
            )
        if self.mapping_set_id:
            return self
        return replace(
            self,
            mapping_set_id=mapping_set.mapping_set_id,
            mapping_set_version=mapping_set.version,
            regime_id="",
        )

    def context_overlay(self) -> dict[str, object]:
        """The :class:`~domain.evidence_context.EvidenceContext` fields this regime pins.

        Only non-empty values appear, so an uncommitted regime writes nothing and the frame keeps
        addressing to exactly the content it always did. The set is the intersection of the two
        records: ``ontology_version`` (the ontology in force), ``language`` and
        ``location_context`` (the localisation FR-014 names) and ``policy_snapshot_ref`` (the
        policy bundle the validation profile was drawn from).

        The temporal frame is deliberately *not* written. ``valid_from`` / ``valid_to`` belong to
        the frame and the regime points at the worldline through ``temporal_frame_ref``;
        copying an interval into both records would create two homes for one fact and a second
        thing to drift.
        """
        overlay: dict[str, object] = {}
        if self.ontology_version:
            overlay["ontology_version"] = self.ontology_version
        if self.language:
            overlay["language"] = self.language
        if self.localization:
            overlay["location_context"] = self.localization
        if self.policy_snapshot_ref:
            overlay["policy_snapshot_ref"] = self.policy_snapshot_ref
        return overlay

    def extends(self, context: EvidenceContext) -> EvidenceContext:
        """Shorthand for :func:`extend_context`; see there for why a new frame is returned."""
        return extend_context(context, self)

    def evaluation_material(self) -> dict[str, object]:
        """Everything needed to recompute and re-evaluate this regime independently.

        Exactly the material :meth:`content_key` digests, and it deliberately **excludes**
        :attr:`regime_id` because the id is derived from this material - the same exclusion
        :meth:`semantic.mappings.SemanticMapping.evaluation_material` makes.
        """
        return {
            "context": self.context_ref,
            "tenant": self.tenant_id,
            "profile": self.profile_ref,
            "profile_version": self.profile_version,
            "ontology_version": self.ontology_version,
            "mapping_set": self.mapping_set_id,
            "mapping_set_version": self.mapping_set_version,
            "validation_profile": self.validation_profile,
            "policy_snapshot": self.policy_snapshot_ref,
            "operator": self.operator_ref,
            "commitment": str(self.commitment),
            "localization": self.localization,
            "language": self.language,
            "temporal_frame": self.temporal_frame_ref,
            "supersedes": self.supersedes,
            "note": self.note,
            "recorded_at": str(self.recorded_at) if self.recorded_at else None,
        }

    def content_key(self) -> str:
        """Order-insensitive identity of the regime, via the shared digest convention.

        Reuses :func:`semantic.contracts.content_key` rather than minting a scheme of its own, so
        a regime, a profile, a mapping and a relation are all addressed the same way in one graph
        (constitution VII).
        """
        return content_key(self.evaluation_material())

    def with_id(self) -> SemanticRegime:
        """A copy carrying its own ``regime_id``; construction already derives one."""
        return replace(self, regime_id=self.content_key()) if not self.regime_id else self

    def __repr__(self) -> str:
        return (
            f"SemanticRegime(context_ref={self.context_ref!r}, "
            f"profile={self.profile_version_ref!r}, "
            f"mapping_set={self.mapping_set_version_ref!r}, "
            f"commitment={str(self.commitment)!r})"
        )


def extend_context(context: EvidenceContext, regime: SemanticRegime) -> EvidenceContext:
    """Return a **new** frame carrying the regime's pinned values. The original is untouched.

    Three things happen and one thing deliberately does not.

    The regime's own values are filled in through :func:`dataclasses.replace`, so the result is
    built by the frame's own constructor and re-canonicalised by it - there is no second way to
    make a frame in this codebase. The ``context_id`` is passed as **empty** so
    :class:`~domain.evidence_context.EvidenceContext` derives a fresh address over the new
    material; passing the old one would raise ``ContextContractError("context_id_mismatch")``,
    and that is the frame verifying itself rather than a bug to work around. And the input frame
    is not modified in any way: it is frozen, so its id is stable forever and a claim already
    pointing at it keeps resolving (constitution I-5, FR-012).

    What is *not* here is any way to write the regime's remaining instruments into the frame.
    ``profile_ref``, ``mapping_set_id``, ``commitment`` and the rest have no home on
    :class:`~domain.evidence_context.EvidenceContext` and none was added - see the module
    docstring. A caller that needs the whole story joins the two by ``context_ref``, which is
    exactly what :attr:`SemanticRegime.context_ref` is for.

    Only fields the regime actually pins are written. An uncommitted regime pins none of the
    frame's existing values and so returns an equivalent frame with the same address - correct,
    because "read under no instruments" changes nothing about where the claim came from.
    """
    return replace(context, context_id="", **regime.context_overlay())


def uncommitted_regime(
    context: EvidenceContext | None = None,
    *,
    tenant_id: str = "",
    validation_profile: str = DEFAULT_VALIDATION_PROFILE,
    temporal_frame_ref: str = "",
    note: str = "",
) -> SemanticRegime:
    """The regime to store alongside an assertion that was interpreted under no instrument.

    The FR-014 path, named so a caller does not have to assemble an empty profile and an empty
    mapping set to express it. Given a frame it adopts that frame's tenant, language, location
    and context reference, so the regime and the frame agree about provenance without either
    being edited; given nothing it is a bare tenant-scoped record, which is still storable.

    ``tenant_id`` overrides the frame's only when a caller knows better, and the frame's is the
    default precisely because a frame and the regime describing it should not disagree about who
    owns the record.
    """
    if context is None:
        return SemanticRegime.uncommitted(
            tenant_id=tenant_id or "default-tenant",
            validation_profile=validation_profile,
            temporal_frame_ref=temporal_frame_ref,
            note=note,
        )
    return SemanticRegime.uncommitted(
        context_ref=context.context_id,
        tenant_id=tenant_id or context.tenant_id,
        validation_profile=validation_profile,
        temporal_frame_ref=temporal_frame_ref,
        language=context.language,
        localization=context.location_context,
        note=note,
    )
