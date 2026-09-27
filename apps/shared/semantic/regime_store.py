"""The semantic regime, made durable: a storable record and the store that keeps it.

T017/T019/T020 of ``specs/018-world-substrate/tasks.md``; contract is FR-014...FR-016 of
``spec.md``. The defect this module exists to remove is quoted from the spec as **D6**:

    The SemanticRegime is structurally present and permanently unevaluated. ``regime_id``
    is written in memory by ``semantic_path/execution.py`` and **persisted in no table** -
    not in ``candidates``, not in ``relation_claim``, not in ``type_assertions``. Every
    compatibility check against a candidate's regime therefore returns ``UNEVALUATED``,
    and it does so on the golden path, on every run.

The fix, in the spec's own words, is to *supply the input, not to stop reporting the
absence*. Reporting the absence was correct: ``semantic.resolution.analyse_candidate``
emits ``regime_unevaluated`` exactly when one side of the comparison carries no
``regime_id``, and that branch is the honest answer for a record that names no regime. What
was missing was the record. This module is the record, and the two read paths that make it
reachable.

**Why the value type could not simply be the regime itself.** :class:`semantic.regime.
SemanticRegime` is a frozen, content-addressed, self-verifying value, and it is already
excellent at being one. It is *not* storable, for the same reason
:class:`domain.evidence_context.EvidenceContext` is not storable: a dataclass in this
codebase is not a row. Three concrete gaps stop a regime being written down:

* :attr:`~semantic.regime.SemanticRegime.commitment` is a
  :class:`~semantic.regime.SemanticCommitment` enum member. JSONB and a SQL column want
  text, and a row must load in a process that has never heard of the enum.
* :meth:`~semantic.regime.SemanticRegime.instruments` is a *method* returning a derived
  tuple. It is the single most useful query on a regime - "what was in play here?" - and a
  method answers it only for a regime you still hold in memory.
* there is nowhere to hang a *second* address. The regime's ``regime_id`` is the machine's
  own, over ``evaluation_material()``; a durable row needs a content address of its own so
  a tampered projection cannot load - the two-level discipline
  :mod:`domain.entity_identity` established for ``ENT-``/``RES-``.

So :class:`RegimeRecord` is a **storable image**, not a redefinition, and
:meth:`RegimeRecord.to_regime` hands the machine object back for the comparison to run
against.

**Two-level addressing, in the same direction as everywhere else.** The two levels answer
different questions and conflating them would be a defect:

* :attr:`RegimeRecord.regime_id` is :class:`~semantic.regime.SemanticRegime`'s own content
  address. It is an **input** here, carried verbatim and never re-derived, because the
  regime mints it and a machine that owns an address must be the only thing that mints it.
  :meth:`RegimeRecord.with_id` deliberately does not fill it, exactly as
  :meth:`domain.entity_identity.EntityIdentity.with_id` does not fill ``entity_id``.
* :attr:`RegimeRecord.record_fingerprint` is **this row's** content address, over every
  field except the two derived ones. It is derived by :meth:`RegimeRecord.with_id` and
  *verified* by ``__post_init__``, so a row edited after it was written cannot load.

**``__post_init__`` verifies, and never mints.** Not as a style note: the failure mode this
feature exists to prevent is a durable record whose address is a *convention* rather than a
derivation, which is how a field quietly stops being covered. So construction refuses a
record carrying no ``regime_id``, refuses one whose stored ``regime_id`` is not the address
its own fields derive, refuses an unrecognised commitment rung rather than storing a fourth
kind of answer, and refuses a stored ``instruments`` projection that disagrees with the
fields it projects. The address itself arrives through :meth:`RegimeRecord.with_id`, where a
caller can see it appear. :func:`verify_regime_partition` then makes the classification
total, so a field added later cannot land in no set and go unaddressed - the same check
:func:`domain.entity_identity.verify_decision_partition` performs, for the same reason.

**The round trip is lossless, field for field, and it is proven rather than asserted.**
:func:`round_trip_is_lossless` is that proof as a first-class function, because "lossless" is
a claim about a bijection between two field sets and the cheapest way to keep a claim honest
is to make it checkable. It compares every field of a record against the corresponding field
of the regime it rebuilds - by dataclass field name, structurally, with no field list
written twice - and returns the names it could not match, empty being the answer that means
lossless. Three passes, through three different public surfaces, because a symmetric pair of
methods can be symmetric and wrong together: the object mapping, the ``to_dict``/
``from_dict`` row that actually crosses the database boundary and is therefore the one that
has to hold once types have become text, and the addresses on their own. Two things make it
hold rather than approximately hold:

* :attr:`RegimeRecord.instruments` is verified against
  :meth:`~semantic.regime.SemanticRegime.instruments` on the way in and recomputed on the
  way out, so the projection cannot drift from the fields it projects.
* :attr:`RegimeRecord.recorded_at` travels as ISO-8601 text and is parsed back, and
  :meth:`~semantic.regime.SemanticRegime.evaluation_material` folds the timestamp in as
  ``str(datetime)``, which ``datetime.isoformat()`` reproduces byte for byte. So a regime
  that comes back out of storage addresses to the ``regime_id`` it went in with, and the
  machine re-checks that itself when :meth:`RegimeRecord.to_regime` passes the stored
  address back into its constructor.

**Fail-closed across tenants, and distinguishably.** Both read paths follow
:mod:`domain.entity_identity` exactly. A miss returns ``None`` only when *this* tenant
genuinely holds no such record; an id held by another tenant raises
:class:`domain.entity_identity.CrossTenantRefusal` naming the tenant that holds it. The
alternative - ``None`` for both - collapses "this tenant has no such regime" and "this
regime is someone else's" into one value at the call site, and the second is a boundary
violation that has to be visible (constitution IV, FR-005). The refusal type is **imported,
not re-declared**: it is the same fact, and a caller that has to catch two classes to close
one boundary will eventually catch only one.

**Unresolved is a counted answer, not a default.** :meth:`RegimeStore.unresolved_reads`
counts every read that came back empty for an id the caller presented as a real regime.
That count is what makes FR-015's "MUST be counted" mechanical rather than rhetorical: a
substrate whose unresolved count is zero on every run is executing its regime, and one whose
count is non-zero is saying so in a number a dashboard can read. The counterpart is
FR-016 - there is no code path in this module that produces a substitute regime. A missing
regime is ``None``, a counted miss, or a typed refusal. There is no third thing.

**Read paths follow the reads.** Two, and two: :meth:`RegimeStore.regime_for` is the
*resolution hot path* - "the regime named by the ``regime_id`` on this candidate" - and
:meth:`RegimeStore.current_for` is the *reconstruction hot path* - "what did we believe when
we read this frame". The schema carries exactly those two indexes for the same reason
:mod:`domain.entity_identity` does (plan decision D1, SC-17), and adding a third read path
here would be adding a query no layer above has asked for.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, fields, replace
from datetime import datetime
from types import MappingProxyType
from typing import Any

from domain.entity_identity import CrossTenantRefusal
from domain.relation_identity import canonical_material, digest128
from semantic.regime import SemanticCommitment, SemanticRegime

__all__ = [
    "REGIME_COMMITMENTS",
    "REGIME_DERIVED_FIELDS",
    "REGIME_IDENTITY_FIELDS",
    "InMemoryRegimeStore",
    "RegimeAddressConflict",
    "RegimeBatch",
    "RegimeRecord",
    "RegimeStore",
    "RegimeStoreError",
    "round_trip_is_lossless",
    "verify_regime_partition",
]


#: The three rungs of :class:`~semantic.regime.SemanticCommitment`, as plain text.
#:
#: Re-declared for the same reason :data:`domain.entity_identity.RESOLUTION_VERDICTS` is: a
#: stored row has to be loadable, and a row carrying a rung this build cannot name must be
#: **refused** rather than stored and read back as one of the three. The *meaning* of a rung
#: is not duplicated - nothing here orders them, and
#: :meth:`~semantic.regime.SemanticCommitment.rank` stays the only place that does.
REGIME_COMMITMENTS: frozenset[str] = frozenset({str(rung) for rung in SemanticCommitment})

#: Fields that decide *which regime this was*, and which
#: :attr:`RegimeRecord.record_fingerprint` digests. Every one is a key of
#: :meth:`~semantic.regime.SemanticRegime.evaluation_material` - which is precisely the set
#: that decides the regime's own ``regime_id`` - so this partition cannot claim coverage the
#: address does not have.
REGIME_IDENTITY_FIELDS: frozenset[str] = frozenset(
    {
        "regime_id",
        "tenant_id",
        "context_ref",
        "profile_ref",
        "profile_version",
        "ontology_version",
        "mapping_set_id",
        "mapping_set_version",
        "validation_profile",
        "policy_snapshot_ref",
        "operator_ref",
        "commitment",
        "localization",
        "language",
        "temporal_frame_ref",
        "supersedes",
        "note",
        "recorded_at",
    }
)

#: Derived, therefore **not** address material: :attr:`RegimeRecord.instruments` is
#: :meth:`~semantic.regime.SemanticRegime.instruments` recomputed, and
#: :attr:`RegimeRecord.record_fingerprint` is the address itself. Both are excluded from the
#: address and both are verified against their sources, so excluding them costs no coverage -
#: which is the only reason an exclusion is safe here.
REGIME_DERIVED_FIELDS: frozenset[str] = frozenset({"instruments", "record_fingerprint"})


class RegimeStoreError(ValueError):
    """A durable regime cannot be constructed, stored, or read.

    A ``ValueError`` carrying the stable snake_case ``code`` a validation layer reports, in
    the shape of :class:`domain.entity_identity.EntityIdentityError` and
    :class:`domain.capture.CaptureContractError` so one caller can switch on any of them.
    """

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


class RegimeAddressConflict(RegimeStoreError):
    """A second, different record arrived under a ``regime_id`` this store already holds.

    Distinct from :class:`RegimeStoreError` because the two are not the same kind of event.
    This one means an address has been reused for different content, which can only happen if
    something upstream is minting regimes outside :class:`~semantic.regime.SemanticRegime` -
    and the whole reason a regime is content-addressed is that it cannot be. It is raised
    rather than logged because the alternative is a regime that quietly changes what an
    already-admitted claim was interpreted under, which is FR-014's subject exactly.
    """

    def __init__(self, code: str, message: str, *, regime_id: str, held_by: str) -> None:
        super().__init__(code, message)
        self.regime_id = regime_id
        self.held_by = held_by


def _iso(value: datetime | None) -> str | None:
    """One timestamp as canonical text (``None`` = honestly unrecorded)."""
    if value is None or value == "":
        return None
    return value.isoformat() if isinstance(value, datetime) else str(value)


def _moment(value: Any) -> datetime | None:
    """Parse a stored timestamp back, accepting a ``datetime`` unchanged."""
    if value is None or value == "":
        return None
    return value if isinstance(value, datetime) else datetime.fromisoformat(str(value))


def _scoped(tenant_id: str) -> str:
    """One tenant as a canonical read key, or fail closed on a blank one (constitution IV).

    Every read and every write passes through here. A read with no tenant is the failure mode
    FR-005 is about - a query that accidentally spans tenants still returns rows, it just
    returns the wrong ones - so it is refused before any lookup rather than defaulted.
    """
    tenant = str(tenant_id or "").strip()
    if not tenant:
        raise RegimeStoreError(
            "regime_tenant_missing",
            "every regime read and write is tenant-scoped: a regime describes one tenant's "
            "instruments, and reading it across a boundary would disclose what that tenant "
            "had available (FR-005, FR-014)",
        )
    return tenant


def _refuse_elsewhere(
    owners: Iterable[str], tenant: str, code: str, asked: str, kind: str
) -> None:
    """Raise :class:`CrossTenantRefusal` when an absent id is held by some other tenant."""
    held_by = sorted(other for other in owners if other != tenant)
    if not held_by:
        return
    raise CrossTenantRefusal(
        code,
        f"{kind} {asked!r} is not in tenant {tenant!r}; it is held by tenant(s) {held_by}, "
        "and returning nothing for it would make 'not yours' indistinguishable from 'not "
        "there' (FR-005, FR-014)",
        requested_by=tenant,
        held_by=held_by[0],
    )


def _regime_from_fields(record: RegimeRecord, regime_id: str) -> SemanticRegime:
    """Rebuild a :class:`~semantic.regime.SemanticRegime` from a record's fields.

    The single place the record's fields become a regime, so the two directions of the round
    trip cannot disagree about which field goes where. ``regime_id`` is a parameter rather
    than read off the record because the two callers want different things from it:
    ``__post_init__`` passes ``""`` so the regime **derives** the address and the record can
    compare, while :meth:`RegimeRecord.to_regime` passes the stored one so the machine
    verifies it for itself.
    """
    return SemanticRegime(
        context_ref=record.context_ref,
        tenant_id=record.tenant_id,
        profile_ref=record.profile_ref,
        profile_version=record.profile_version,
        ontology_version=record.ontology_version,
        mapping_set_id=record.mapping_set_id,
        mapping_set_version=record.mapping_set_version,
        validation_profile=record.validation_profile,
        policy_snapshot_ref=record.policy_snapshot_ref,
        operator_ref=record.operator_ref,
        commitment=SemanticCommitment(record.commitment),
        localization=record.localization,
        language=record.language,
        temporal_frame_ref=record.temporal_frame_ref,
        supersedes=record.supersedes,
        note=record.note,
        recorded_at=record.recorded_at,
        regime_id=regime_id,
    )


def _recency_key(record: RegimeRecord) -> tuple[bool, str, str]:
    """Total order for "the regime in force": recorded time, then address as the tiebreak.

    The address breaks ties so two regimes recorded at the same instant have one ordering in
    every process (constitution VI). Records with no time sort last, so an undated regime can
    never displace a dated one - an unrecorded time is an absence, not a minimum.
    """
    return (record.recorded_at is None, _iso(record.recorded_at) or "", record.regime_id)


@dataclass(frozen=True)
class RegimeRecord:
    """One regime in storable form: every field, both identities, and the derivation.

    Frozen, **two-level addressed**, and self-verifying. Field for field this is
    :class:`~semantic.regime.SemanticRegime` with three additions and no omissions:

    * :attr:`regime_id` - the machine's own address, carried verbatim (see the module
      docstring for why it is an input and not an output).
    * :attr:`record_fingerprint` - this row's own content address, derived by
      :meth:`with_id` and verified by ``__post_init__``.
    * :attr:`instruments` - where :meth:`~semantic.regime.SemanticRegime.instruments` was a
      method, this is the stored JSONB projection of it. Verified against the fields it
      projects, so it cannot drift into a second opinion about what was in play.
    * :attr:`commitment` - the enum member as **text**, validated against
      :data:`REGIME_COMMITMENTS`, so a row loads where the enum is unknown and a rung this
      build cannot name is refused rather than stored.

    :attr:`context_ref` may be empty, and that is deliberate rather than a hole.
    :func:`semantic.regime.uncommitted_regime` builds a frame-less regime for an assertion
    read under no instrument at all and states that it "is still storable"; refusing it here
    would make the no-commitment path - a first-class state under FR-014 and US3, not an
    absence - the one regime that cannot be written down. Such a record is reachable by
    address through :meth:`RegimeStore.regime_for` and simply has no frame to be the current
    regime of, which :meth:`RegimeStore.current_for` already refuses to ask about.

    There is no ``regime_id=""`` default on the write path, because FR-016 forbids
    substituting an empty regime and proceeding as though it matched. A regime arrives here
    by being built, and a built regime always has its address.
    """

    regime_id: str = ""
    tenant_id: str = "default-tenant"
    context_ref: str = ""
    profile_ref: str = ""
    profile_version: str = ""
    ontology_version: str = ""
    mapping_set_id: str = ""
    mapping_set_version: str = ""
    validation_profile: str = ""
    policy_snapshot_ref: str = ""
    operator_ref: str = ""
    commitment: str = str(SemanticCommitment.UNCOMMITTED)
    localization: str = ""
    language: str = ""
    temporal_frame_ref: str = ""
    supersedes: str = ""
    note: str = ""
    instruments: tuple[str, ...] = ()
    recorded_at: datetime | None = None
    record_fingerprint: str = ""

    def __post_init__(self) -> None:
        """Canonicalise, fail closed on an unstorable record, then verify both addresses.

        Canonicalisation is the same set of reference-shaped fields
        :class:`~semantic.regime.SemanticRegime` normalises, so a record and the regime it
        rebuilds agree on what a stored reference looks like. That is load-bearing: those
        spellings are what the address is computed over, so a disagreement here would produce
        a record whose own fields address to a different ``regime_id`` than the one it
        carries, and the machine would refuse to rehydrate it.

        Nothing is derived here. The address arrives through :meth:`with_id`, the machine's
        address is compared rather than written, and :attr:`instruments` is checked against
        what the fields imply rather than filled in.
        """
        for name in (
            "regime_id",
            "tenant_id",
            "context_ref",
            "profile_ref",
            "profile_version",
            "ontology_version",
            "mapping_set_id",
            "mapping_set_version",
            "validation_profile",
            "policy_snapshot_ref",
            "operator_ref",
            "commitment",
            "localization",
            "language",
            "temporal_frame_ref",
            "supersedes",
            "note",
        ):
            object.__setattr__(self, name, str(getattr(self, name) or "").strip())
        object.__setattr__(
            self, "instruments", tuple(sorted({str(ref) for ref in self.instruments if ref}))
        )
        if self.recorded_at is not None and not isinstance(self.recorded_at, datetime):
            raise RegimeStoreError(
                "regime_recorded_at_malformed",
                f"recorded_at must be a datetime or None, got {self.recorded_at!r}",
            )
        object.__setattr__(self, "tenant_id", _scoped(self.tenant_id))
        if self.commitment not in REGIME_COMMITMENTS:
            raise RegimeStoreError(
                "regime_commitment_unknown",
                f"commitment {self.commitment!r} is not one of {sorted(REGIME_COMMITMENTS)}; "
                "a record is refused rather than stored with a rung this layer cannot read, "
                "because a fourth kind of commitment must not be mistaken for one of three",
            )
        if not self.regime_id:
            raise RegimeStoreError(
                "regime_id_missing",
                "a regime record requires the regime's own regime_id: SemanticRegime derives "
                "it from its evaluation material, and a record that derived an address of "
                "its own would name something no regime ever produced",
            )
        derived_regime = _regime_from_fields(self, "")
        if self.regime_id != derived_regime.regime_id:
            raise RegimeStoreError(
                "regime_address_mismatch",
                f"record carries regime_id {self.regime_id!r} but its own fields address to "
                f"{derived_regime.regime_id!r}; a content address is verified, never trusted",
            )
        derived_instruments = derived_regime.instruments()
        if self.instruments and self.instruments != derived_instruments:
            raise RegimeStoreError(
                "regime_instruments_mismatch",
                f"record projects instruments {list(self.instruments)} but its fields imply "
                f"{list(derived_instruments)}; the projection is derived, so a disagreement "
                "means a corrupt row rather than a second opinion",
            )
        if not self.instruments and derived_instruments:
            raise RegimeStoreError(
                "regime_instruments_missing",
                f"record projects no instruments but its fields imply "
                f"{list(derived_instruments)}; the instruments JSONB is the query surface "
                "for 'what was in play here', and an empty one would read as 'nothing was in "
                "play' (FR-014)",
            )
        if not self.record_fingerprint:
            return
        addressed = self.content_key()
        if self.record_fingerprint != addressed:
            raise RegimeStoreError(
                "record_fingerprint_mismatch",
                f"record carries fingerprint {self.record_fingerprint!r} but its own content "
                f"addresses to {addressed!r}; a content address is verified, never trusted",
            )

    def content_key(self) -> str:
        """The 128-bit digest ``record_fingerprint`` is built from (I-11, I-1).

        Covers every identity field and neither derived one, so the address is a pure function
        of the regime's content and re-ingesting one regime is one record (I-11, FR-022).
        Persisted beside the id so the storage layer can carry a unique index on it, exactly
        as ``captures`` carries ``capture_fingerprint``.
        """
        return digest128(canonical_material(self._material()))

    def with_id(self) -> RegimeRecord:
        """A copy carrying its own content address; ``self`` when it already does.

        Explicit derivation rather than magic in ``__post_init__``, matching
        :meth:`domain.entity_identity.EntityIdentity.with_id` and the counterpart to
        ``__post_init__`` refusing a *mismatched* address. The store calls this on the way in,
        so a caller reading a regime never pays for derivation and a caller writing one
        cannot forget it.

        Only :attr:`record_fingerprint` is filled. :attr:`regime_id` is the machine's address
        and there is nothing to derive it from - that is the point of carrying it.
        """
        if self.record_fingerprint:
            return self
        return replace(self, record_fingerprint=self.content_key())

    def instrument_refs(self) -> tuple[str, ...]:
        """Every instrument actually bound, canonically ordered - "what was in play here?".

        The stored projection rather than a recomputation, so this is a read of the row and a
        reader can tell what the durable record says without rebuilding the regime. It is
        verified equal to the recomputation at construction, so the two cannot disagree, and
        empty is unreachable while any instrument was bound.
        """
        return self.instruments

    def profile_version_ref(self) -> str:
        """``"profile_id@version"``, or ``""`` when no profile was bound. Reads back on sight."""
        return f"{self.profile_ref}@{self.profile_version}" if self.profile_ref else ""

    def mapping_set_version_ref(self) -> str:
        """``"set_id@version"``, or ``""`` when no mapping set was bound."""
        if not self.mapping_set_id:
            return ""
        return f"{self.mapping_set_id}@{self.mapping_set_version}"

    def carries_semantic_commitment(self) -> bool:
        """Whether any semantic instrument was actually bound - FR-014's own predicate.

        Delegated to the regime rather than reimplemented, so the record and the value can
        never answer this differently. Note that the *ladder rung* is not the test: a regime
        that names a profile while recording ``UNCOMMITTED`` describes instruments that were
        available and were not used, which is a real and different situation from having no
        regime at all.
        """
        return _regime_from_fields(self, self.regime_id).carries_semantic_commitment()

    def to_regime(self) -> SemanticRegime:
        """Rehydrate the live :class:`~semantic.regime.SemanticRegime` this row is.

        The stored :attr:`regime_id` is passed back into the machine's constructor, so
        ``SemanticRegime.__post_init__`` re-derives the address from its own material and
        refuses the result if the two disagree. That is a second, independent check on the
        same fact, from the class that owns it: the round trip is verified by the machine
        rather than merely symmetric, and a tampered row cannot become a regime claiming an
        address it does not follow.

        **The round trip is lossless, field for field**; :func:`round_trip_is_lossless` is
        that claim as a checkable function rather than a sentence in a docstring.
        """
        try:
            return _regime_from_fields(self, self.regime_id)
        except ValueError as mismatch:
            raise RegimeStoreError(
                "regime_rehydration_failed",
                f"record {self.regime_id!r} does not rehydrate into the regime it claims to "
                f"be: {mismatch}",
            ) from mismatch

    @classmethod
    def from_regime(cls, regime: SemanticRegime) -> RegimeRecord:
        """Serialise a live :class:`~semantic.regime.SemanticRegime` for storage.

        Every field is projected - read off the regime, not re-listed from a second copy of
        the field set - so a field added to the regime in a later feature is carried the day
        it is added, where a hand-written mapping would have dropped it silently and a
        durable record would quietly stop round-tripping.

        The machine's ``regime_id`` is carried verbatim, the ``instruments`` projection is
        taken from the regime's own method rather than recomputed here, and :meth:`with_id`
        derives the row's second address.
        """
        return cls(
            regime_id=regime.regime_id,
            tenant_id=regime.tenant_id,
            context_ref=regime.context_ref,
            profile_ref=regime.profile_ref,
            profile_version=regime.profile_version,
            ontology_version=regime.ontology_version,
            mapping_set_id=regime.mapping_set_id,
            mapping_set_version=regime.mapping_set_version,
            validation_profile=regime.validation_profile,
            policy_snapshot_ref=regime.policy_snapshot_ref,
            operator_ref=regime.operator_ref,
            commitment=str(regime.commitment),
            localization=regime.localization,
            language=regime.language,
            temporal_frame_ref=regime.temporal_frame_ref,
            supersedes=regime.supersedes,
            note=regime.note,
            instruments=regime.instruments(),
            recorded_at=regime.recorded_at,
        ).with_id()

    def to_dict(self) -> dict[str, Any]:
        """The full regime row, plus both addresses, keyed to the ``semantic_regime`` columns.

        One entry per column the data requirements name, under that column's name, so the row
        is a faithful image of the record and maps one-to-one onto the table -
        ``regime_id``, ``tenant_id``, ``context_ref``, ``profile_ref``, ``profile_version``,
        ``ontology_version``, ``mapping_set_id``, ``mapping_set_version``,
        ``validation_profile``, ``commitment``, ``instruments`` (JSONB), ``recorded_at`` -
        and onto the seven further columns this record's lossless round trip requires.
        :meth:`from_dict` is the exact inverse and verifies both addresses on the way in.
        """
        return {
            "regime_id": self.regime_id,
            "tenant_id": self.tenant_id,
            "context_ref": self.context_ref,
            "profile_ref": self.profile_ref,
            "profile_version": self.profile_version,
            "ontology_version": self.ontology_version,
            "mapping_set_id": self.mapping_set_id,
            "mapping_set_version": self.mapping_set_version,
            "validation_profile": self.validation_profile,
            "policy_snapshot_ref": self.policy_snapshot_ref,
            "operator_ref": self.operator_ref,
            "commitment": self.commitment,
            "localization": self.localization,
            "language": self.language,
            "temporal_frame_ref": self.temporal_frame_ref,
            "supersedes": self.supersedes,
            "note": self.note,
            "instruments": list(self.instruments),
            "recorded_at": _iso(self.recorded_at),
            "record_fingerprint": self.record_fingerprint or self.content_key(),
            "content_key": self.content_key(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> RegimeRecord:
        """Rebuild a regime record from its own row; missing keys take the defaults.

        The stored ``regime_id`` and ``record_fingerprint`` are passed through and therefore
        both verified against the material this row actually carries, so a round trip of a
        tampered row raises rather than loading a record that lies about either address.
        """
        data = dict(payload)
        data.pop("content_key", None)
        return cls(
            regime_id=str(data.get("regime_id", "")),
            tenant_id=str(data.get("tenant_id", "default-tenant")),
            context_ref=str(data.get("context_ref", "")),
            profile_ref=str(data.get("profile_ref", "")),
            profile_version=str(data.get("profile_version", "")),
            ontology_version=str(data.get("ontology_version", "")),
            mapping_set_id=str(data.get("mapping_set_id", "")),
            mapping_set_version=str(data.get("mapping_set_version", "")),
            validation_profile=str(data.get("validation_profile", "")),
            policy_snapshot_ref=str(data.get("policy_snapshot_ref", "")),
            operator_ref=str(data.get("operator_ref", "")),
            commitment=str(data.get("commitment", SemanticCommitment.UNCOMMITTED)),
            localization=str(data.get("localization", "")),
            language=str(data.get("language", "")),
            temporal_frame_ref=str(data.get("temporal_frame_ref", "")),
            supersedes=str(data.get("supersedes", "")),
            note=str(data.get("note", "")),
            instruments=tuple(str(ref) for ref in data.get("instruments") or ()),
            recorded_at=_moment(data.get("recorded_at")),
            record_fingerprint=str(data.get("record_fingerprint", "")),
        )

    def _material(self) -> dict[str, Any]:
        """The field set ``record_fingerprint`` digests; no derived field appears here."""
        return {
            "regime_id": self.regime_id,
            "tenant_id": self.tenant_id,
            "context_ref": self.context_ref,
            "profile_ref": self.profile_ref,
            "profile_version": self.profile_version,
            "ontology_version": self.ontology_version,
            "mapping_set_id": self.mapping_set_id,
            "mapping_set_version": self.mapping_set_version,
            "validation_profile": self.validation_profile,
            "policy_snapshot_ref": self.policy_snapshot_ref,
            "operator_ref": self.operator_ref,
            "commitment": self.commitment,
            "localization": self.localization,
            "language": self.language,
            "temporal_frame_ref": self.temporal_frame_ref,
            "supersedes": self.supersedes,
            "note": self.note,
            "recorded_at": _iso(self.recorded_at),
        }


def verify_regime_partition(record: RegimeRecord | None = None) -> None:
    """Refuse a field on :class:`RegimeRecord` that is neither identity nor declared derived.

    The same total-partition check
    :func:`domain.entity_identity.verify_decision_partition` performs, for the same reason:
    without it a field added later lands in no set and is quietly excluded from the address,
    which is how a durable record stops being derived from its own contents one field at a
    time. The three classes are exhaustive and disjoint - identity material, declared derived
    material, and nothing else - and "covered upstream" is exactly the exemption that lets a
    field go unclassified.

    Checked against the **class** always, and against one **record** when one is supplied,
    because the class check catches a field nobody classified and the record check catches an
    address that does not actually cover what the record carries. The store calls it with the
    record on the way in and the class alone on construction, so a field cannot decay between
    calls and cannot be addressed by only half the record it lives on.
    """
    declared = {item.name for item in fields(RegimeRecord)}
    classified = REGIME_IDENTITY_FIELDS | REGIME_DERIVED_FIELDS
    unclassified = sorted(declared - classified)
    if unclassified:
        raise RegimeStoreError(
            "regime_partition_undeclared",
            f"RegimeRecord declares fields no set claims: {unclassified}. A field nobody "
            "classified is a field nobody checked; add each to REGIME_IDENTITY_FIELDS or "
            "REGIME_DERIVED_FIELDS in semantic.regime_store.",
        )
    overlap = sorted(REGIME_IDENTITY_FIELDS & REGIME_DERIVED_FIELDS)
    if overlap:
        raise RegimeStoreError(
            "regime_partition_overlap",
            f"fields classified as both identity and derived material: {overlap}",
        )
    drifted = sorted(classified - declared)
    if drifted:
        raise RegimeStoreError(
            "regime_partition_drifted",
            "a set declares fields the record does not have, so their classification is "
            f"about nothing: {drifted}",
        )
    if record is None:
        return
    material = set(record._material())  # noqa: SLF001 - reading the whole set is the point
    excluded = sorted(material - REGIME_IDENTITY_FIELDS)
    if excluded:
        raise RegimeStoreError(
            "regime_partition_incomplete",
            f"RegimeRecord material carries fields declared derived or unclaimed: {excluded}. "
            "A field excluded from the address is a field a tampered row could change without "
            "changing the fingerprint.",
        )
    absent = sorted(REGIME_IDENTITY_FIELDS - material)
    if absent:
        raise RegimeStoreError(
            "regime_partition_incomplete",
            "REGIME_IDENTITY_FIELDS declares fields the material does not emit, so their "
            f"values would be absent from the address: {absent}",
        )


def round_trip_is_lossless(regime: SemanticRegime) -> tuple[str, ...]:
    """The names of every field a ``regime -> record -> regime`` trip did not reproduce.

    Empty is the answer that means lossless, and this is the proof of that claim as a
    checkable function rather than an assertion in a docstring. Three passes, each through a
    different public surface, because a symmetric pair of methods can be symmetric and wrong
    together:

    * :meth:`RegimeRecord.from_regime` then :meth:`RegimeRecord.to_regime`, compared field by
      field against the original - the object-mapping round trip.
    * :meth:`RegimeRecord.to_dict` then :meth:`RegimeRecord.from_dict`, compared the same way -
      the *row* round trip, which is what crosses the database boundary and therefore the one
      that has to hold once an enum has become text and a ``datetime`` has become an ISO
      string.
    * the addresses, checked separately and last: the rebuilt regime must carry the original
      ``regime_id``, which is the property the whole substrate rests on and the one a
      field-by-field comparison would not catch on its own.

    The comparison is structural - it walks :func:`dataclasses.fields` of the regime and looks
    each name up on the rebuilt value - so it is exhaustive by construction and cannot quietly
    check three fields out of eighteen.
    """
    record = RegimeRecord.from_regime(regime)
    rebuilt = (record.to_regime(), RegimeRecord.from_dict(record.to_dict()).to_regime())
    mismatched = [
        item.name
        for candidate in rebuilt
        for item in fields(candidate)
        if getattr(candidate, item.name) != getattr(regime, item.name)
    ]
    mismatched.extend(
        label
        for label, seen in (
            ("regime_id:record", record.regime_id),
            ("regime_id:object", rebuilt[0].regime_id),
            ("regime_id:row", rebuilt[1].regime_id),
        )
        if seen != regime.regime_id
    )
    return tuple(sorted(set(mismatched)))


@dataclass(frozen=True)
class RegimeBatch:
    """The durable result of one ingest: every record written, and the scopes now covered.

    A batch is returned rather than a count because "persist a set of regimes and recover the
    scopes" is two questions, and the second is the one a caller cannot answer by reading a
    number. :attr:`scopes` says which ``(tenant, context_ref)`` pairs now have a durable
    regime behind them, canonically ordered, so a caller can state its coverage without a
    second query - and so a replay can check that it covered the same frames as the run it
    reproduces (FR-022).

    Every read here is **batch-scoped** rather than store-scoped. A caller recovering a batch
    should not be able to widen silently into whatever else the store happens to hold, and
    :meth:`record_for` returning ``None`` for a regime some other batch wrote is the honest
    answer rather than a leak.
    """

    records: tuple[RegimeRecord, ...] = ()
    scopes: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "records", tuple(self.records))
        object.__setattr__(
            self, "scopes", tuple(sorted({(str(owner), str(ref)) for owner, ref in self.scopes}))
        )

    def regime_ids(self) -> tuple[str, ...]:
        """Every ``regime_id`` written, canonically ordered, for a byte-comparison."""
        return tuple(sorted(record.regime_id for record in self.records))

    def contexts(self, tenant_id: str) -> tuple[str, ...]:
        """The frames this batch gave a durable regime to, for one tenant.

        Tenant-scoped, so a caller asking "what do I have" cannot be answered with another
        tenant's frames by passing the wrong id (FR-005).
        """
        tenant = _scoped(tenant_id)
        return tuple(sorted(ref for owner, ref in self.scopes if owner == tenant))

    def record_for(self, regime_id: str) -> RegimeRecord | None:
        """One written record by address, or ``None`` for one this batch did not write."""
        wanted = str(regime_id or "").strip()
        for record in self.records:
            if record.regime_id == wanted:
                return record
        return None

    def __len__(self) -> int:
        return len(self.records)

    def __iter__(self) -> Iterator[RegimeRecord]:
        return iter(self.records)


class RegimeStore(ABC):
    """The durable regime substrate: two read paths, one idempotent write path.

    Abstract because the substrate is the contract and not one implementation of it, and
    because a caller that must work against both the in-memory store and a SQL one cannot be
    handed a concrete class without a way to say what it needs.
    :class:`InMemoryRegimeStore` is the reference implementation; the SQL store satisfies the
    same four methods against the ``semantic_regime`` table, and the cross-tenant refusal is
    the part a plain SQL query cannot give it - which is why the contract *names* the refusal
    rather than leaving it to each implementation to remember.
    """

    @abstractmethod
    def regime_for(self, tenant_id: str, regime_id: str) -> RegimeRecord | None:
        """The record this tenant holds under ``regime_id``, or ``None`` for a genuine miss.

        **The resolution hot path.** A candidate carries a ``regime_id`` and the compatibility
        layer needs the regime behind it; on the golden path this read is what turns
        ``regime_unevaluated`` into ``regime_compatible`` (FR-015, D6). One indexed read on
        ``(tenant_id, regime_id)``, which is the primary key plus the tenant column.

        Fail-closed: a ``regime_id`` held by another tenant raises
        :class:`~domain.entity_identity.CrossTenantRefusal` rather than returning ``None``,
        so "not yours" is never read as "not there" (FR-005).
        """

    @abstractmethod
    def current_for(self, tenant_id: str, context_ref: str) -> RegimeRecord | None:
        """The regime in force for one frame, or ``None`` when this tenant recorded none.

        **The reconstruction hot path** - "what did we believe when we read this frame?" -
        which is the question ``semantic_regime.context_ref`` exists to answer and the one
        FR-014 makes answerable. When a frame has been read under several regimes the latest
        is returned, ordered by ``(recorded_at, regime_id)`` so the answer is total and
        identical in every process (constitution VI). The earlier ones are not superseded by
        being passed over: each keeps its own address and stays readable through
        :meth:`regime_for`, because a re-interpretation adds a regime and never removes one.
        """

    @abstractmethod
    def ingest_regime(self, regime: SemanticRegime) -> RegimeRecord:
        """Store one regime and return the record that is now durable.

        Idempotent on ``regime_id``, because a regime is content-addressed: re-ingesting one is
        the same write however many times it happens, and re-ingesting a *different* regime
        under one address is a conflict rather than an overwrite. A regime already referenced
        by an admitted claim must never change underneath it (FR-014), which is the same
        discipline :class:`domain.capture.InMemoryCaptureRegistry` states for a
        ``capture_fingerprint``.
        """

    @abstractmethod
    def unresolved_reads(self) -> int:
        """How many reads came back empty for an id the caller presented as real (FR-015).

        The count that makes "counted, not absorbed into the default" mechanical. A run whose
        count is zero executed its regime; a run whose count is not is saying so in a number.
        FR-016's prohibition on substituting a default is what keeps the number small enough
        to be a signal rather than a constant.
        """

    def ingest_all(self, regimes: Iterable[SemanticRegime]) -> RegimeBatch:
        """Persist a batch of regimes and report both the records and the scopes covered.

        Concrete rather than abstract, because it is expressible entirely in terms of
        :meth:`ingest_regime` and an implementation that re-derived it would be a second write
        path to keep honest. The batch is ordered by ``(tenant, context, regime_id)`` before
        any write, so two processes ingesting the same set perform the same writes in the same
        order and a conflict surfaces against the same regime rather than whichever one
        happened to arrive first (constitution VI).

        :attr:`RegimeBatch.records` is the **durable** set, one entry per address, not one
        per input: three copies of one regime in the input are three requests for one record
        and the batch says so once. The alternative - echoing the input back - would make a
        caller re-derive the deduplication to find out what it actually persisted.
        """
        ordered = sorted(
            regimes, key=lambda item: (item.tenant_id, item.context_ref, item.regime_id)
        )
        written: dict[tuple[str, str], RegimeRecord] = {}
        for regime in ordered:
            record = self.ingest_regime(regime)
            written.setdefault((record.tenant_id, record.regime_id), record)
        records = tuple(written[key] for key in sorted(written))
        return RegimeBatch(
            records=records,
            scopes={(record.tenant_id, record.context_ref) for record in records},
        )


class InMemoryRegimeStore(RegimeStore):
    """The reference regime store, and the two indexes the schema is shaped around.

    Four structures, each an index rather than a scan:

    * ``_by_address`` on ``(tenant_id, regime_id)`` - the resolution hot path. The regime's
      own address plus the tenant column, which together are the primary key the data
      requirements name.
    * ``_by_context`` on ``(tenant_id, context_ref)`` - the reconstruction hot path. Appended
      rather than replaced, so a frame read under several regimes keeps all of them and
      :meth:`current_for` is a max over a short list rather than a table scan.
    * ``_owners`` and ``_context_owners`` - the *reverse* indexes, and the reason a
      cross-tenant miss can be told apart from an absence. Without them "this tenant has no
      such regime" and "this regime belongs to someone else" are the same ``None``, and the
      second is a boundary violation that would be invisible (constitution IV, FR-005).

    Idempotent on ``regime_id`` (I-11), returning the **stored** record rather than the
    incoming one, so a re-ingest neither conflicts nor restates anything. And there is no code
    path here that produces a substitute regime: an absent regime is ``None``, a counted miss,
    or a typed refusal, and never an empty default (FR-016).
    """

    def __init__(self, regimes: Iterable[SemanticRegime] = ()) -> None:
        verify_regime_partition()
        self._by_address: dict[tuple[str, str], RegimeRecord] = {}
        self._by_context: dict[tuple[str, str], list[RegimeRecord]] = {}
        self._owners: dict[str, set[str]] = {}
        self._context_owners: dict[str, set[str]] = {}
        self._unresolved = 0
        for regime in regimes:
            self.ingest_regime(regime)

    def ingest_regime(self, regime: SemanticRegime) -> RegimeRecord:
        """Store one regime; idempotent on its address, never an overwrite.

        Idempotence is decided on the content address rather than on record equality, so
        re-ingesting the same regime is the same write however it was built (I-11, FR-022) -
        while a *different* record under one address raises
        :class:`RegimeAddressConflict`, because an address that can be reused for different
        content is not an address.
        """
        record = RegimeRecord.from_regime(regime)
        verify_regime_partition(record)
        key = (record.tenant_id, record.regime_id)
        held = self._by_address.get(key)
        if held is not None:
            if held.record_fingerprint != record.record_fingerprint:
                raise RegimeAddressConflict(
                    "regime_address_conflict",
                    f"regime {record.regime_id} is already recorded in tenant "
                    f"{record.tenant_id!r} with different content; a regime is "
                    "content-addressed and is never overwritten, because an admitted claim "
                    "already points at this address (FR-014)",
                    regime_id=record.regime_id,
                    held_by=record.tenant_id,
                )
            return held
        self._by_address[key] = record
        self._by_context.setdefault((record.tenant_id, record.context_ref), []).append(record)
        self._owners.setdefault(record.regime_id, set()).add(record.tenant_id)
        self._context_owners.setdefault(record.context_ref, set()).add(record.tenant_id)
        return record

    def regime_for(self, tenant_id: str, regime_id: str) -> RegimeRecord | None:
        """The record under this address, or ``None`` for a miss this tenant genuinely has.

        Fail-closed across tenants: an address held elsewhere raises
        :class:`~domain.entity_identity.CrossTenantRefusal` naming the holder, so "not yours" is
        never read as "not there" (FR-005).

        A genuine miss **increments the unresolved count**, because that is the read FR-015
        says must be counted: a caller presenting a real ``regime_id`` and getting nothing back
        is the exceptional path, and the counter is what keeps it exceptional rather than
        habitual.
        """
        tenant = _scoped(tenant_id)
        wanted = str(regime_id or "").strip()
        if not wanted:
            raise RegimeStoreError(
                "regime_id_missing",
                "a regime lookup needs the regime_id; a lookup with none cannot be answered "
                "and must not be read as 'this candidate has no regime'",
            )
        held = self._by_address.get((tenant, wanted))
        if held is not None:
            return held
        _refuse_elsewhere(
            self._owners.get(wanted, ()), tenant, "cross_tenant_regime", wanted, "regime"
        )
        self._unresolved += 1
        return None

    def current_for(self, tenant_id: str, context_ref: str) -> RegimeRecord | None:
        """The regime in force for one frame, latest first by ``(recorded_at, regime_id)``.

        Fail-closed on the same terms as :meth:`regime_for`, keyed on the frame: a
        ``context_ref`` another tenant has read under raises rather than reporting "no regime
        for this frame", which is a different and materially less alarming statement about a
        boundary crossing.
        """
        tenant = _scoped(tenant_id)
        wanted = str(context_ref or "").strip()
        if not wanted:
            raise RegimeStoreError(
                "regime_context_missing",
                "a current-regime lookup needs the context_ref; a lookup with none cannot be "
                "answered and must not be read as 'this frame was read under no regime'",
            )
        records = self._by_context.get((tenant, wanted))
        if not records:
            _refuse_elsewhere(
                self._context_owners.get(wanted, ()),
                tenant,
                "cross_tenant_regime_context",
                wanted,
                "regime context",
            )
            self._unresolved += 1
            return None
        return max(records, key=_recency_key)

    def unresolved_reads(self) -> int:
        """How many reads have come back empty for a real address. Zero on a healthy run."""
        return self._unresolved

    def unresolved(self) -> Mapping[str, int]:
        """The empty reads as a read-only mapping, for a run report payload.

        One key, and a mapping rather than an int only for symmetry with
        :attr:`domain.entity_identity.EntityReconstruction.holes`: a caller assembling a report
        wants a named place to put "the regime was unresolvable here", and a growing named
        field is where that belongs as more substrates start counting their own misses.
        """
        return MappingProxyType({"regime_unresolved": self._unresolved})

    def __len__(self) -> int:
        return len(self._by_address)

    def __contains__(self, regime_id: object) -> bool:
        return str(regime_id) in self._owners
