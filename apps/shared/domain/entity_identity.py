"""Entity identity: the durable statement of which mention introduced an entity (feature 018).

T001-T004 of ``specs/018-world-substrate/tasks.md``; contract is FR-001...FR-005 of
``spec.md`` with plan decision D1 and the data requirements for ``entity_identity`` and
``resolution_decision``.

**The defect this module exists to remove**, quoted from the spec: ``ENT-`` is
technically deterministic, but that determinism depends on external call discipline.
``ResolutionBatch(scope) -> anchor state``. If a caller loses the scope, the next batch
mints a new anchor and the same entity gets a new ``ENT-``. The ``entities`` table holds
``entity_id``, ``entity_type``, ``canonical_name`` and no anchor and no reference to any
resolution that produced it.

Nothing here re-implements resolution. The logic is closed; this is the durability layer
underneath it, and it is deliberately smaller than the machine it serves. Three facts:

- :class:`EntityIdentity` is the *durable statement of an anchor*: which mention
  introduced this entity, which observation that mention came from, which capture
  fetched those bytes, and which resolution concluded it. Written once, immutable, and
  recovered by ``anchor_for_mention`` - the resolution hot path - so a caller that has
  forgotten everything may still resolve a later mention of the same entity onto the same
  ``ENT-``. The resolver stays stateless (FR-002) and its state becomes something other
  than a caller obligation.
- :class:`ResolutionDecisionRecord` is the *durable statement of a reasoning*: a ``RES-``
  content address over the merged mentions, the surviving candidates, the per-candidate
  compatibility reasons, the corroboration, the collective outcome, the blocking report,
  the confidence and its parts, and the notes. Append-only, and **ambiguous and
  unresolved decisions are included**, because a decision that named no entity is still a
  decision and without it the history cannot be reconstructed (FR-004, SC-2).
- ``reconstruct`` turns one ``ENT-`` back into the anchor, the ordered ``RES-`` history,
  the mentions merged and the terminal verdict, **naming any link it cannot find** rather
  than returning a shorter chain that reads as whole.

**Where the write-once guarantee actually lives.** The durable uniqueness that matters is
a UNIQUE index on ``(tenant_id, anchor_mention_id)`` in the storage layer (plan D1, T005):
a column cannot enforce anything, and an index is what makes a second bind impossible
rather than merely discouraged. :class:`InMemoryEntityIdentityStore` reproduces that index
in memory - the same discipline :class:`~domain.capture.InMemoryCaptureRegistry` states for
its fingerprint index - and :class:`AnchorConflict` is the part a bare index cannot give a
caller: a *typed* refusal naming the mention that is already taken and the entity that
already holds it. Rebinding the *same* identity is idempotent and returns the stored
record, so re-ingesting a batch neither forks history nor moves ``created_at``.

**How ``domain`` stays free of a ``semantic`` import edge.** The only permitted edge is
``semantic.contracts`` (see :mod:`domain.relation_candidate`), and
:class:`semantic.resolution.ResolutionDecision` is not on it - it lives in the module
above this package. Three disciplines follow, each the least one that still works:

1. ``ResolutionDecision``, ``ResolutionBatch`` and ``ResolutionScope`` are imported under
   ``TYPE_CHECKING`` only, so every signature here names the real types while importing
   none of them.
2. :meth:`ResolutionDecisionRecord.from_decision` **serialises duck-typed**. It never
   checks a type and never names a semantic class: it reads ``dataclasses.fields`` off
   whatever it is handed and projects the whole field set, so it cannot silently drop a
   field a later version of the resolver adds. The load path therefore has no runtime
   dependency on the semantic layer at all.
3. :meth:`ResolutionDecisionRecord.to_decision` **reconstructs** the machine objects, and
   that is the one place a function-local ``import semantic.resolution`` and
   ``import semantic.blocking`` appear. It is deferred rather than module-level because
   the direction that matters - reading a stored row - must not require the semantic layer
   to be installed, and a deferral that is *used* is honest where a deferral that is never
   used is only a way of hiding a cycle. There is no cycle: nothing in :mod:`semantic`
   imports this module. If the import fails, the failure is reported as
   ``decision_rehydration_unavailable`` rather than a bare ``ImportError``.

The two prefix constants and the four verdict strings are re-declared here rather than
imported, and each re-declaration is documented at its definition. A duplicated string
constant is a cost; a ``domain`` -> ``semantic.resolution`` import is a dependency
inversion, and the platform is trying to remove exactly that.

**What is deliberately excluded from every address, and why.**
:data:`domain.relation_identity.MUTABLE_PROJECTION_FIELDS` already answers this for claims
and the answers transfer verbatim: ``created_at`` and ``decided_at`` are wall clock, so
folding either in would make an event replayed at a different moment mint a different id -
precisely the determinism constitution VII and FR-022 require of a rebuild. And
``supersedes`` is excluded for the reason that file gives: it is a link to a record that
may not exist yet, so it is filled in after the fact. Both exclusions are enforced by
:func:`verify_identity_partition` and :func:`verify_decision_partition`, which refuse any
field that is neither identity material, a declared projection field, nor a derived id -
the same total-partition check ``RelationClaim`` is held to, so the partition cannot decay
one new field at a time.

**The boundary of reconstruction.** This module attests the identity and decision links of
``Entity -> resolution decision -> mentions``: the anchor's own references, the ordered
decisions, and the merged mentions. Whether the anchor *observation* and *capture* rows
exist, and whether they reach a source, is another store's business and this module says
so rather than claiming a hole on every healthy run - :mod:`domain.evidence_lineage` is
what traverses those hops. What *is* reported here is every hole this store can see, each
naming the link it belongs to, and :meth:`EntityReconstruction.assert_complete` refuses to
let a caller read a partial chain as a whole.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, fields, is_dataclass, replace
from datetime import datetime
from enum import Enum, StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from domain.evidence_lineage import EvidenceHop, HopKind
from domain.relation_identity import canonical_material, digest128

if TYPE_CHECKING:
    from semantic.blocking import BlockingResult, Candidate, StageReduction, TypeHypothesis
    from semantic.resolution import (
        BlockingOutcome,
        CollectiveOutcome,
        CompatibilityEvidence,
        CompatibilityReason,
        EntityHypothesis,
        ResolutionDecision,
        ResolutionScope,
    )

#: ``ENT-`` - the logical entity ref, minted by the resolver from its recorded anchor.
#:
#: Re-declared rather than imported from :mod:`semantic.resolution`, and only the prefix
#: is checked: the digest width and the derivation belong to the resolver, and re-deriving
#: an anchor here would be the defect this module exists to remove. The prefix *is* checked
#: because a record keyed by anything but an ``ENT-`` would never join the decisions that
#: name it, and that is the one failure a value type can still catch.
ENTITY_ID_PREFIX = "ENT-"

#: ``RES-`` - the content address of one resolution, minted by the resolver and verified
#: here rather than minted again, so a stored decision and a live one cannot disagree.
RESOLUTION_ID_PREFIX = "RES-"

#: Stands in for "no resolution created this entity's anchor", for an identity adopted from
#: state written before this table existed.
#:
#: A **declared absence**, in the shape :data:`~domain.capture.UNBATCHED_INGEST_BATCH` set
#: for captures: the alternative is a null column, which cannot distinguish "nobody has said
#: who created this" from "not yet written", and that distinction is the one this substrate
#: exists to keep. It is part of the address, so an anchor bound under the sentinel and the
#: same anchor bound later with a real ``RES-`` are two different statements and the second
#: bind is refused - the first statement of who created an entity stands, and the fix is a
#: superseding decision, never an edit. ``is_creation_attributed`` is the query that says
#: which case a record is.
UNATTRIBUTED_RESOLUTION = "unattributed"

#: The four verdicts :class:`semantic.resolution.ResolutionVerdict` admits, as plain text.
#:
#: A stored row must be loadable in a process with no semantic layer at all, so the record
#: carries the verdict as its serialised string and validates it against this vocabulary.
#: The *rule* is not duplicated - nothing here decides what a verdict means, whether it is
#: settled, or what it implies. Adding a verdict to the semantic layer means adding it
#: here, and a row carrying an unknown one is refused (``decision_verdict_unknown``) rather
#: than stored, so a corrupted row can never be read as a fifth kind of answer.
RESOLUTION_VERDICTS: frozenset[str] = frozenset(
    {"resolved", "ambiguous", "unresolved", "conflicted"}
)

#: Fields that decide *which entity this is*, and which its ``identity_fingerprint``
#: digests. Every one is write-once: changing any of them is a different identity, not an
#: update (FR-001). The derived ``entity_id`` is an *input* rather than an output, and
#: ``__post_init__`` says why.
ENTITY_IDENTITY_IDENTITY_FIELDS: frozenset[str] = frozenset(
    {
        "entity_id",
        "tenant_id",
        "anchor_mention_id",
        "anchor_observation_id",
        "anchor_capture_id",
        "created_by_resolution",
    }
)

#: Fields an identity's anchor may legitimately restate without that being a new identity.
#:
#: ``created_at`` - wall clock, and the reason it is here rather than in the address is the
#: reason :data:`domain.relation_identity.MUTABLE_PROJECTION_FIELDS` excludes it from a
#: claim: an event replayed at a different moment must address to the same id or FR-022
#: cannot hold. Because it is excluded, two binds of one anchor that disagree only on
#: ``created_at`` are the *same* write and the first one stands - which is what makes
#: re-ingest idempotent rather than a silent timestamp change.
ENTITY_IDENTITY_MUTABLE_PROJECTION_FIELDS: frozenset[str] = frozenset({"created_at"})


class EntityIdentityError(ValueError):
    """A durable identity or decision cannot be constructed, stored, or read.

    A ``ValueError`` carrying the stable snake_case ``code`` a validation layer reports, in
    the shape of :class:`domain.capture.CaptureContractError` and
    :class:`domain.evidence_context.ContextContractError` so one caller can switch on any
    of them.
    """

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


class AnchorConflict(EntityIdentityError):
    """A second bind tried to make one mention anchor a different entity (FR-001).

    Distinct from :class:`EntityIdentityError` because the two are not the same kind of
    event and a caller handles them differently: this one means a *bug somewhere upstream* -
    two places elected an anchor for one mention, or a scope was rebuilt from a different
    batch - and the fix is to find that, not to retry. It is raised rather than logged
    because the alternative is an identity that silently depends on write order, which is
    the defect the durable anchor was introduced to remove.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(code, message)
        self.anchor_mention_id = ""
        self.held_entity_id = ""
        self.rejected_entity_id = ""


class CrossTenantRefusal(EntityIdentityError):
    """A read or write crossed a tenant boundary, and was refused (constitution IV).

    Fail-closed, and distinguishable from "not found" on purpose. Returning ``None`` for a
    cross-tenant read would make two very different situations - *this tenant has no such
    record* and *this record belongs to someone else* - indistinguishable at the call site,
    and the second is a boundary violation that has to be seen (FR-005).

    The message names the owning tenant. That is deliberate: the caller already holds the id
    it asked for, so the only thing the refusal adds is that the id is not theirs, and a
    refusal withholding that would be less actionable than the disclosure is dangerous.
    """

    def __init__(self, code: str, message: str, *, requested_by: str, held_by: str) -> None:
        super().__init__(code, message)
        self.requested_by = requested_by
        self.held_by = held_by


class ChainLink(StrEnum):
    """One hop of the reconstruction chain, so a hole names where it is."""

    ANCHOR_MENTION = "anchor_mention"
    ANCHOR_OBSERVATION = "anchor_observation"
    ANCHOR_CAPTURE = "anchor_capture"
    CREATING_DECISION = "creating_decision"
    DECISION_HISTORY = "decision_history"
    TERMINAL_VERDICT = "terminal_verdict"
    MERGED_MENTIONS = "merged_mentions"


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


def _required(code: str, field: str, value: str, why: str) -> str:
    """Return a non-blank field, or fail closed with ``code`` naming what is missing."""
    text = str(value or "").strip()
    if not text:
        raise EntityIdentityError(code, f"an identity record requires {field}: {why}")
    return text


def _frozen(value: Any) -> Mapping[str, Any]:
    """A stored projection as a read-only mapping, so a record cannot be edited in place."""
    if value is None:
        return MappingProxyType({})
    return MappingProxyType(dict(value))


def _frozen_each(value: Any) -> tuple[Mapping[str, Any], ...]:
    """A stored collection of projections, each read-only, in recorded order.

    Order is load-bearing: ``reasons`` is the order the compatibility layers produced them
    in, and a reordering would change the address of a decision whose reasoning did not
    change. So these are tuples, not sorted sets.
    """
    return tuple(_frozen(item) for item in value or ())


def _plain(value: Any) -> Any:
    """One stored value as a JSON-shaped plain value, unwrapping read-only mappings.

    The inverse of :func:`_storable` for the containers this module introduces; a projection
    is already plain and passes through unchanged.
    """
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_plain(item) for item in value]
    return value


def _storable(value: Any) -> Any:
    """Project one live value to the storable plain form, structurally.

    Reads ``dataclasses.fields`` rather than naming a class, which is the whole point: the
    serialiser cannot fall behind the machine it serialises. A field added to
    :class:`semantic.resolution.ResolutionDecision` in a later feature is carried by this
    function the day it is added, and a hand-written mapping would have dropped it silently
    - which is how a durable record stops round-tripping and nobody notices until a
    reconstruction is wrong.

    Enums are tested before ``str`` because a ``StrEnum`` member *is* a string, and
    ``str(member)`` is what the machine would have put in its own digest. Sets are sorted
    because an unordered container must never leak its hash order into an address, matching
    :func:`domain.relation_identity.canonical_material`.
    """
    if value is None or isinstance(value, bool | float | int):
        return value
    if isinstance(value, Enum):
        return str(value)
    if isinstance(value, str):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {
            str(key): _storable(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: _storable(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, set | frozenset):
        return sorted(_storable(item) for item in value)
    if isinstance(value, list | tuple):
        return [_storable(item) for item in value]
    return str(value)


def _pairs(value: Any) -> tuple[tuple[str, float], ...]:
    """One ``(ref, score)`` or ``(code, delta)`` collection as the record stores it."""
    return tuple((str(item[0]), float(item[1])) for item in value or ())


@dataclass(frozen=True)
class EntityIdentity:
    """One entity's durable identity statement: the mention that introduced it.

    Frozen, content-addressed on :attr:`identity_fingerprint`, and self-verifying: a
    supplied fingerprint is **verified** against the record's own material, so a tampered
    row cannot load and no caller can forge one. The address is *not* the ``entity_id``,
    and that separation is the two-level discipline the platform already follows
    (``RL-``/``RC-``, ``TA-``/``TAR-``, ``CAND-``/``CNDR-``, and now ``ENT-``/``RES-``):

    - ``entity_id`` is the **logical** ref, the anchor-derived ``ENT-`` the resolver
      minted. It is an *input* here rather than an output, and deliberately so: deriving it
      again would mean re-deriving an anchor, and a recomputed anchor is the defect
      (FR-001). The resolver owns the derivation; this record states its result durably.
      It is the reason :meth:`with_id` fills in only the fingerprint and never the
      ``entity_id``, and the reason a caller may not pass a scope id in to "help".
    - :attr:`identity_fingerprint` is this **record's** content address, over every
      write-once field. Two records with identical anchor material are one record, which is
      what makes a re-ingest idempotent; two that differ on any of them are a conflict.

    :attr:`created_at` is excluded from the address and declared a projection field, for
    the reason :data:`ENTITY_IDENTITY_MUTABLE_PROJECTION_FIELDS` gives. The load-bearing
    uniqueness is not this fingerprint at all: it is a UNIQUE index on
    ``(tenant_id, anchor_mention_id)`` in the storage layer (plan D1), and
    :class:`InMemoryEntityIdentityStore` is that index in memory. This type supplies what an
    index cannot - a typed :class:`AnchorConflict` naming the mention already taken.
    """

    entity_id: str = ""
    tenant_id: str = "default-tenant"
    anchor_mention_id: str = ""
    anchor_observation_id: str = ""
    anchor_capture_id: str = ""
    created_by_resolution: str = ""
    created_at: datetime | None = None
    identity_fingerprint: str = ""

    def __post_init__(self) -> None:
        """Fail closed on an incomplete anchor, then verify a supplied fingerprint.

        Derivation is *not* performed here: it is :meth:`with_id`, so construction stays a
        plain value operation and a caller can see an address appear rather than discover
        one. What is refused here is a record that could not be an identity at all, and a
        record whose stored address does not follow from its own contents.
        """
        entity = _required(
            "identity_entity_missing",
            "an entity_id",
            self.entity_id,
            "an identity record states an identity; a record without one is not one",
        )
        if not entity.startswith(ENTITY_ID_PREFIX):
            raise EntityIdentityError(
                "identity_entity_malformed",
                f"entity_id {entity!r} does not carry the {ENTITY_ID_PREFIX} prefix the "
                "resolver mints; a record keyed by anything else would never join the "
                "decisions that name it",
            )
        tenant = _required(
            "identity_tenant_missing",
            "a tenant_id",
            self.tenant_id,
            "every read is tenant-scoped and a durable anchor is tenant-scoped (FR-005)",
        )
        anchor = _required(
            "anchor_mention_missing",
            "an anchor_mention_id",
            self.anchor_mention_id,
            "the anchor is the whole record; without it the entity has no introduction and "
            "identity is whatever the caller last held (FR-001)",
        )
        creator = _required(
            "identity_creator_missing",
            "a created_by_resolution",
            self.created_by_resolution,
            "which resolution introduced this entity is part of the identity statement; use "
            f"{UNATTRIBUTED_RESOLUTION} to declare that there is none",
        )
        created = self.created_at
        if created is None or _iso(created) is None:
            raise EntityIdentityError(
                "identity_created_at_missing",
                "an identity record requires created_at: this module reads no clock, and a "
                "defaulted creation time would make replay non-deterministic (VII)",
            )

        object.__setattr__(self, "entity_id", entity)
        object.__setattr__(self, "tenant_id", tenant)
        object.__setattr__(self, "anchor_mention_id", anchor)
        object.__setattr__(self, "created_by_resolution", creator)

        if not self.identity_fingerprint:
            return
        addressed = self.content_key()
        if self.identity_fingerprint != addressed:
            raise EntityIdentityError(
                "identity_fingerprint_mismatch",
                f"record carries fingerprint {self.identity_fingerprint!r} but its own "
                f"content addresses to {addressed!r}; a content address is verified, "
                "never trusted",
            )

    def content_key(self) -> str:
        """The 128-bit digest ``identity_fingerprint`` is built from (I-11, I-1).

        Covers every write-once field and deliberately not :attr:`created_at`, so re-ingest
        of one anchor is one record. Persisted beside the id so the storage layer can carry
        a unique index on it exactly as ``captures`` carries ``capture_fingerprint``.
        """
        return digest128(canonical_material(self._material()))

    def with_id(self) -> EntityIdentity:
        """A copy carrying its own content address; ``self`` when it already does.

        Explicit derivation rather than magic in ``__post_init__``, matching
        :meth:`semantic.contracts.TypeAssertion.with_id` and the counterpart to
        ``__post_init__`` refusing a *mismatched* address. Deriving the logical
        ``entity_id`` is not offered and must not be added: the resolver mints it from the
        anchor, and re-minting it here would need the resolution scope - the very
        caller-held value whose loss this feature exists to survive.
        """
        if self.identity_fingerprint:
            return self
        return replace(self, identity_fingerprint=self.content_key())

    @property
    def is_creation_attributed(self) -> bool:
        """Whether a real ``RES-`` created this anchor, rather than the declared absence."""
        return self.created_by_resolution != UNATTRIBUTED_RESOLUTION

    def anchor_keys(self) -> tuple[tuple[str, str], ...]:
        """The ``(kind, id)`` references the anchor carries, for a chain walk.

        Ordered observation then capture, which is the direction of the chain: the capture
        fetched the bytes the observation saw. An absent reference is omitted rather than
        emitted empty, so a caller can tell "no capture recorded" from "capture recorded as
        nothing" - the latter is not constructible, and that is the point.
        """
        keys: list[tuple[str, str]] = [("mention", self.anchor_mention_id)]
        if self.anchor_observation_id:
            keys.append(("observation", self.anchor_observation_id))
        if self.anchor_capture_id:
            keys.append(("capture", self.anchor_capture_id))
        return tuple(keys)

    def to_hop(self, *, tenant_id: str | None = None, label: str = "") -> EvidenceHop:
        """The ``HopKind.ENTITY`` lineage hop for this identity.

        Imports lineage one-way at module level, exactly as
        :meth:`domain.capture.Capture.to_hop` does and for the same reason: this is this
        module's own value being projected into the chain, and ``EvidenceGraph`` derives its
        step sequence from the hop kinds registered in the graph rather than from any value
        type, so there is no cycle. A ``tenant_id`` other than the record's own raises
        rather than minting a hop carrying one tenant's id under another's chain (IV).
        """
        if tenant_id is not None and str(tenant_id) != self.tenant_id:
            raise EntityIdentityError(
                "identity_tenant_mismatch",
                f"identity {self.entity_id} belongs to tenant {self.tenant_id!r} and cannot "
                f"be linked into tenant {str(tenant_id)!r}'s chain (FR-005)",
            )
        return EvidenceHop(
            kind=HopKind.ENTITY,
            node_id=self.entity_id,
            label=label or self.anchor_mention_id,
            tenant_id=self.tenant_id,
        )

    def to_dict(self) -> dict[str, Any]:
        """The full identity record, plus its fingerprint and content key (I-5)."""
        return {
            "entity_id": self.entity_id,
            **_plain(self._material()),
            "created_at": _iso(self.created_at),
            "identity_fingerprint": self.identity_fingerprint or self.content_key(),
            "content_key": self.content_key(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> EntityIdentity:
        """Rebuild an identity from its own record; missing keys take the defaults.

        The stored fingerprint is passed through and therefore verified against the
        recomputed material, so a round trip of a tampered row raises rather than returning
        an identity that lies about its anchor.
        """
        data = dict(payload)
        data.pop("content_key", None)
        return cls(
            entity_id=str(data.get("entity_id", "")),
            tenant_id=str(data.get("tenant_id", "default-tenant")),
            anchor_mention_id=str(data.get("anchor_mention_id", "")),
            anchor_observation_id=str(data.get("anchor_observation_id", "")),
            anchor_capture_id=str(data.get("anchor_capture_id", "")),
            created_by_resolution=str(data.get("created_by_resolution", "")),
            created_at=_moment(data.get("created_at")),
            identity_fingerprint=str(data.get("identity_fingerprint", "")),
        )

    def _material(self) -> dict[str, Any]:
        """The write-once field set ``identity_fingerprint`` digests; no ``created_at``."""
        return {
            "entity_id": self.entity_id,
            "tenant_id": self.tenant_id,
            "anchor_mention_id": self.anchor_mention_id,
            "anchor_observation_id": self.anchor_observation_id,
            "anchor_capture_id": self.anchor_capture_id,
            "created_by_resolution": self.created_by_resolution,
        }


@dataclass(frozen=True)
class ResolutionDecisionRecord:
    """One resolution's durable record: what was decided, and the complete reasoning.

    Frozen and **two-level addressed** like every other identity in the platform: it carries
    the resolver's own ``RES-`` as :attr:`resolution_decision_id`, and derives a second,
    self-verifying address of its own content as :attr:`record_fingerprint`. The two answer
    different questions and conflating them would be a defect:

    - ``resolution_decision_id`` is the **machine's** address - ``RES-`` as
      :class:`semantic.resolution.ResolutionDecision` minted it. It is carried verbatim and
      never re-derived here, for the same reason :attr:`EntityIdentity.entity_id` is: a
      machine that owns an address must be the only thing that mints it. It is the primary
      key the data requirements name, so a stored decision and a live one are joinable and
      :meth:`to_decision` can hand the address back to the machine to check itself against.
    - :attr:`record_fingerprint` is **this record's** content address, over the whole
      serialised row including every nested projection. This is the self-verifying part: a
      supplied fingerprint is verified against the record's own material, so a tampered row
      cannot load, and the nested ``blocking``/``collective``/``hypothesis`` values are
      covered by it directly rather than through a content key somebody could get wrong.

    Field for field this is :class:`semantic.resolution.ResolutionDecision` in storable form
    - the flat scalars are fields, and the six nested values (``reasons``,
    ``blocked_out``, ``evidence``, ``blocking``, ``collective``, ``hypothesis``) are the
    machine objects projected to plain values by :func:`_storable`, which reads their
    dataclass fields rather than naming their classes. :meth:`from_decision` and
    :meth:`to_decision` are exact inverses, and the round trip is verified by the machine
    rather than asserted here.

    **Ambiguous and unresolved decisions are records.** :attr:`entity_ref` is then empty -
    faithfully, because the resolver declined to name an entity and a record that invented
    one would be the silent coin-flip the architecture forbids. What links such a decision
    to an entity is :attr:`supersedes`, walked by
    ``InMemoryResolutionDecisionLog.history_for``, which is why an ``AMBIGUOUS`` pass shows
    up in the history of the entity a later pass settled (FR-004, SC-2, US2).

    :attr:`decided_at` and :attr:`supersedes` are projection fields, excluded from the
    address for the reasons :data:`ENTITY_IDENTITY_MUTABLE_PROJECTION_FIELDS` gives: the
    first is wall clock and would break the replay fixed point (FR-022), the second is a
    link to a record that may not have existed when this one was written. Both are declared
    in :data:`RESOLUTION_DECISION_MUTABLE_PROJECTION_FIELDS` and enforced by
    :func:`verify_decision_partition`.
    """

    resolution_decision_id: str = ""
    record_fingerprint: str = ""
    tenant_id: str = "default-tenant"
    mention_id: str = ""
    surface: str = ""
    verdict: str = "unresolved"
    entity_ref: str = ""
    anchor_mention_id: str = ""
    anchor_key: str = ""
    merged_mentions: tuple[str, ...] = ()
    considered: tuple[str, ...] = ()
    surviving: tuple[str, ...] = ()
    scored: tuple[tuple[str, float], ...] = ()
    corroboration: int = 0
    confidence: float = 0.0
    confidence_parts: tuple[tuple[str, float], ...] = ()
    normalization: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    resolution_scope_id: str = ""
    operator_ref: str = ""
    normalization_version: str = ""
    ontology_version: str = ""
    regime_id: str = ""
    reasons: tuple[Mapping[str, Any], ...] = ()
    blocked_out: tuple[Mapping[str, Any], ...] = ()
    evidence: tuple[Mapping[str, Any], ...] = ()
    blocking: Mapping[str, Any] | None = None
    collective: Mapping[str, Any] | None = None
    hypothesis: Mapping[str, Any] | None = None
    decided_at: datetime | None = None
    supersedes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Canonicalise, fail closed on an unusable record, then verify a supplied address."""
        for name in ("merged_mentions", "considered", "surviving", "normalization", "notes"):
            object.__setattr__(self, name, tuple(getattr(self, name)))
        object.__setattr__(self, "scored", _pairs(self.scored))
        object.__setattr__(self, "confidence_parts", _pairs(self.confidence_parts))
        object.__setattr__(self, "supersedes", tuple(str(ref) for ref in self.supersedes))
        object.__setattr__(self, "reasons", _frozen_each(self.reasons))
        object.__setattr__(self, "blocked_out", _frozen_each(self.blocked_out))
        object.__setattr__(self, "evidence", _frozen_each(self.evidence))
        object.__setattr__(self, "blocking", None if self.blocking is None else _frozen(
            self.blocking
        ))
        object.__setattr__(self, "collective", None if self.collective is None else _frozen(
            self.collective
        ))
        object.__setattr__(self, "hypothesis", None if self.hypothesis is None else _frozen(
            self.hypothesis
        ))

        tenant = str(self.tenant_id or "").strip()
        if not tenant:
            raise EntityIdentityError(
                "decision_tenant_missing",
                "a decision record requires a tenant_id: reconstruction is tenant-scoped "
                "and a decision from one tenant must not be readable while rebuilding "
                "another's entity (FR-005)",
            )
        mention = str(self.mention_id or "").strip()
        if not mention:
            raise EntityIdentityError(
                "decision_mention_missing",
                "a decision record requires a mention_id: a decision is about one mention, "
                "and a record without one cannot be filed in any history (FR-004)",
            )
        verdict = str(self.verdict or "").strip()
        if verdict not in RESOLUTION_VERDICTS:
            raise EntityIdentityError(
                "decision_verdict_unknown",
                f"verdict {self.verdict!r} is not one of {sorted(RESOLUTION_VERDICTS)}; a "
                "record is refused rather than stored with a verdict this layer cannot read, "
                "because a fifth kind of answer must not be mistaken for one of four",
            )
        decided = self.decided_at
        if decided is None or _iso(decided) is None:
            raise EntityIdentityError(
                "decision_time_missing",
                "a decision record requires decided_at: this module reads no clock, and the "
                "ordered history is only ordered if the caller says when (VII)",
            )
        addressed_id = str(self.resolution_decision_id or "").strip()
        if not addressed_id:
            raise EntityIdentityError(
                "decision_id_missing",
                "a decision record requires the resolver's own resolution_decision_id: the "
                "machine mints it from its decision material, and a record that derived its "
                "own would address to something the resolver never produced",
            )
        if not addressed_id.startswith(RESOLUTION_ID_PREFIX):
            raise EntityIdentityError(
                "decision_id_malformed",
                f"resolution_decision_id {addressed_id!r} does not carry the "
                f"{RESOLUTION_ID_PREFIX} prefix the resolver mints",
            )
        for ref in self.supersedes:
            if not ref.startswith(RESOLUTION_ID_PREFIX):
                raise EntityIdentityError(
                    "decision_supersedes_malformed",
                    f"supersedes entry {ref!r} is not a {RESOLUTION_ID_PREFIX} address; a "
                    "decision may only be superseded by another recorded decision",
                )
        object.__setattr__(self, "tenant_id", tenant)
        object.__setattr__(self, "mention_id", mention)
        object.__setattr__(self, "verdict", verdict)
        object.__setattr__(self, "resolution_decision_id", addressed_id)

        if not self.record_fingerprint:
            return
        addressed = self.content_key()
        if self.record_fingerprint != addressed:
            raise EntityIdentityError(
                "record_fingerprint_mismatch",
                f"record carries fingerprint {self.record_fingerprint!r} but its own content "
                f"addresses to {addressed!r}; a content address is verified, never trusted",
            )

    def content_key(self) -> str:
        """The 128-bit digest ``record_fingerprint`` is built from (I-11, I-1).

        Covers every reasoning field and neither :attr:`decided_at` nor
        :attr:`supersedes`, for the two declared reasons above. Persisted beside the id so
        the storage layer can carry a unique index on it, exactly as ``captures`` carries
        ``capture_fingerprint``.
        """
        return digest128(canonical_material(self._material()))

    def with_id(self) -> ResolutionDecisionRecord:
        """A copy carrying its own content address; ``self`` when it already does.

        Explicit derivation rather than magic in ``__post_init__``, matching
        :meth:`semantic.contracts.TypeAssertion.with_id` and the counterpart to
        ``__post_init__`` refusing a *mismatched* address. The store calls this on the way
        in, so a caller reading a decision never pays for derivation and a caller writing
        one cannot forget it.

        Only :attr:`record_fingerprint` is filled. :attr:`resolution_decision_id` is the
        machine's address and there is nothing to derive it from - that is the point of
        carrying it.
        """
        if self.record_fingerprint:
            return self
        return replace(self, record_fingerprint=self.content_key())

    @property
    def names_entity(self) -> bool:
        """Whether the resolver named an entity, faithfully reported.

        False for ``ambiguous``, ``unresolved`` and ``conflicted`` alike, because
        :class:`semantic.resolution.ResolutionDecision` leaves ``logical_entity_ref`` empty
        for every one of them. This reports the stored ``entity_ref`` and applies no rule
        about verdicts, so no verdict semantics are duplicated here.
        """
        return bool(self.entity_ref)

    def reason_codes(self) -> tuple[str, ...]:
        """Every recorded reason code, canonically ordered, for a log line or a diff."""
        return tuple(sorted(str(reason.get("code", "")) for reason in self.reasons))

    def reason_codes_for(self, layer: str) -> tuple[str, ...]:
        """The reason codes one compatibility layer produced, in recorded order."""
        return tuple(
            str(reason.get("code", ""))
            for reason in self.reasons
            if str(reason.get("layer", "")) == str(layer)
        )

    def to_dict(self) -> dict[str, Any]:
        """The full decision record for storage, plus its fingerprint and content key (I-5).

        Every field, under its own name, so the row is a faithful image of the record and
        maps one-to-one onto the ``resolution_decision`` columns the data requirements name
        (``mention_id``, ``entity_ref``, ``verdict``, ``merged_mentions``, ``surviving``,
        ``reasons``, ``corroboration``, ``collective``, ``blocking``, ``supersedes``,
        ``decided_at``). The nested projections are already plain values, so this is
        directly JSONB-shaped - which is what those columns are. :meth:`from_dict` is the
        exact inverse, and it verifies the fingerprint on the way back in.
        """
        return {
            **_plain(self._row()),
            "record_fingerprint": self.record_fingerprint or self.content_key(),
            "content_key": self.content_key(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ResolutionDecisionRecord:
        """Rebuild a decision record from its own row; missing keys take the defaults.

        The stored fingerprint is passed through and therefore verified against the
        recomputed material, so a tampered row raises rather than loading a record whose
        reasoning no longer matches the fingerprint taken over it.
        """
        data = dict(payload)
        data.pop("content_key", None)
        return cls(
            resolution_decision_id=str(data.get("resolution_decision_id", "")),
            record_fingerprint=str(data.get("record_fingerprint", "")),
            tenant_id=str(data.get("tenant_id", "default-tenant")),
            mention_id=str(data.get("mention_id", "")),
            surface=str(data.get("surface", "")),
            verdict=str(data.get("verdict", "unresolved")),
            entity_ref=str(data.get("entity_ref", "")),
            anchor_mention_id=str(data.get("anchor_mention_id", "")),
            anchor_key=str(data.get("anchor_key", "")),
            merged_mentions=tuple(str(ref) for ref in data.get("merged_mentions") or ()),
            considered=tuple(str(ref) for ref in data.get("considered") or ()),
            surviving=tuple(str(ref) for ref in data.get("surviving") or ()),
            scored=_pairs(data.get("scored") or ()),
            corroboration=int(data.get("corroboration", 0)),
            confidence=float(data.get("confidence", 0.0)),
            confidence_parts=_pairs(data.get("confidence_parts") or ()),
            normalization=tuple(str(ref) for ref in data.get("normalization") or ()),
            notes=tuple(str(note) for note in data.get("notes") or ()),
            resolution_scope_id=str(data.get("resolution_scope_id", "")),
            operator_ref=str(data.get("operator_ref", "")),
            normalization_version=str(data.get("normalization_version", "")),
            ontology_version=str(data.get("ontology_version", "")),
            regime_id=str(data.get("regime_id", "")),
            reasons=tuple(dict(item) for item in data.get("reasons") or ()),
            blocked_out=tuple(dict(item) for item in data.get("blocked_out") or ()),
            evidence=tuple(dict(item) for item in data.get("evidence") or ()),
            blocking=data.get("blocking"),
            collective=data.get("collective"),
            hypothesis=data.get("hypothesis"),
            decided_at=_moment(data.get("decided_at")),
            supersedes=tuple(str(ref) for ref in data.get("supersedes") or ()),
        )

    def _row(self) -> dict[str, Any]:
        """The storable field set, one entry per dataclass field, under its own name.

        Distinct from :meth:`_material`, which is the *address*: the same fields, shortened
        keys, no projection fields. Keeping the two apart is what lets the row be a faithful
        image of the record while the address stays a pure function of the write-once
        content.
        """
        return {
            "resolution_decision_id": self.resolution_decision_id,
            "record_fingerprint": self.record_fingerprint,
            "tenant_id": self.tenant_id,
            "mention_id": self.mention_id,
            "surface": self.surface,
            "verdict": self.verdict,
            "entity_ref": self.entity_ref,
            "anchor_mention_id": self.anchor_mention_id,
            "anchor_key": self.anchor_key,
            "merged_mentions": self.merged_mentions,
            "considered": self.considered,
            "surviving": self.surviving,
            "scored": self.scored,
            "corroboration": self.corroboration,
            "confidence": self.confidence,
            "confidence_parts": self.confidence_parts,
            "normalization": self.normalization,
            "notes": self.notes,
            "resolution_scope_id": self.resolution_scope_id,
            "operator_ref": self.operator_ref,
            "normalization_version": self.normalization_version,
            "ontology_version": self.ontology_version,
            "regime_id": self.regime_id,
            "reasons": self.reasons,
            "blocked_out": self.blocked_out,
            "evidence": self.evidence,
            "blocking": self.blocking,
            "collective": self.collective,
            "hypothesis": self.hypothesis,
            "decided_at": self.decided_at,
            "supersedes": self.supersedes,
        }

    def _material(self) -> dict[str, Any]:
        """The field set ``record_fingerprint`` digests; no decided_at, no supersedes."""
        return {
            "decision": self.resolution_decision_id,
            "tenant": self.tenant_id,
            "mention": self.mention_id,
            "surface": self.surface,
            "verdict": self.verdict,
            "entity": self.entity_ref,
            "anchor_mention": self.anchor_mention_id,
            "anchor_key": self.anchor_key,
            "merged_mentions": list(self.merged_mentions),
            "considered": list(self.considered),
            "surviving": list(self.surviving),
            "scored": [[ref, round(score, 6)] for ref, score in self.scored],
            "corroboration": self.corroboration,
            "confidence": round(self.confidence, 6),
            "confidence_parts": [[code, round(delta, 6)] for code, delta in self.confidence_parts],
            "normalization": list(self.normalization),
            "notes": list(self.notes),
            "scope": self.resolution_scope_id,
            "operator": self.operator_ref,
            "normalization_version": self.normalization_version,
            "ontology_version": self.ontology_version,
            "regime": self.regime_id,
            "reasons": self.reasons,
            "blocked_out": self.blocked_out,
            "evidence": self.evidence,
            "blocking": self.blocking,
            "collective": self.collective,
            "hypothesis": self.hypothesis,
        }


    @classmethod
    def from_decision(
        cls,
        decision: ResolutionDecision,
        *,
        decided_at: datetime | None,
        supersedes: tuple[str, ...] = (),
    ) -> ResolutionDecisionRecord:
        """Serialise a live :class:`semantic.resolution.ResolutionDecision` for storage.

        **Duck-typed on purpose.** Nothing here names a semantic class or checks its type:
        the projection walks ``dataclasses.fields`` of whatever it is handed (see
        :func:`_storable`), so this method holds no runtime import edge and cannot fall
        behind a field the resolver later adds. That is what keeps the *load* path free of
        the semantic layer, which is the direction that matters - a stored row must be
        readable by a process with no resolver in it.

        ``decided_at`` is required and supplied by the caller, because this module reads no
        clock. ``supersedes`` is the caller's statement of what this decision revises; a
        first decision has none.
        """
        return cls(
            resolution_decision_id=str(getattr(decision, "resolution_decision_id", "")),
            tenant_id=getattr(decision, "tenant_id", ""),
            mention_id=getattr(decision, "mention_id", ""),
            surface=getattr(decision, "surface", ""),
            verdict=str(getattr(decision, "verdict", "")),
            entity_ref=getattr(decision, "logical_entity_ref", ""),
            anchor_mention_id=getattr(decision, "anchor_mention_id", ""),
            anchor_key=getattr(decision, "anchor_key", ""),
            merged_mentions=tuple(getattr(decision, "merged_mentions", ())),
            considered=tuple(getattr(decision, "considered", ())),
            surviving=tuple(getattr(decision, "surviving", ())),
            scored=tuple(getattr(decision, "scored", ())),
            corroboration=int(getattr(decision, "corroboration", 0)),
            confidence=float(getattr(decision, "confidence", 0.0)),
            confidence_parts=tuple(getattr(decision, "confidence_parts", ())),
            normalization=tuple(getattr(decision, "normalization", ())),
            notes=tuple(getattr(decision, "notes", ())),
            resolution_scope_id=getattr(decision, "resolution_scope_id", ""),
            operator_ref=getattr(decision, "operator_ref", ""),
            normalization_version=getattr(decision, "normalization_version", ""),
            ontology_version=getattr(decision, "ontology_version", ""),
            regime_id=getattr(decision, "regime_id", ""),
            reasons=_storable(getattr(decision, "reasons", ())),
            blocked_out=_storable(getattr(decision, "blocked_out", ())),
            evidence=_storable(getattr(decision, "evidence", ())),
            blocking=_storable(getattr(decision, "blocking", None)) or None,
            collective=_storable(getattr(decision, "collective", None)) or None,
            hypothesis=_storable(getattr(decision, "hypothesis", None)) or None,
            decided_at=decided_at,
            supersedes=supersedes,
        ).with_id()

    def to_decision(self) -> ResolutionDecision:
        """Rehydrate the machine object this record was serialised from.

        **The one runtime import of :mod:`semantic.resolution` in this module**, and it is
        function-local on purpose. Rebuilding a :class:`ResolutionDecision` means
        constructing it, and constructing it means the class; the alternative was to make
        the inverse mapping structural too, and it cannot be - a generic rehydrator has to
        know *which* class each stored projection was, and guessing would be worse than
        naming. Deferring the import keeps the dependency out of module import and out of
        :meth:`from_decision`, so reading a durable record never requires the semantic
        layer; only asking for a live machine object does, and only a caller who wants one
        will.

        **The round trip is lossless, field for field, and it is verified rather than
        asserted.** Every field of the record is projected, so a rebuilt
        :class:`ResolutionDecision` re-derives the same ``confidence`` from the same
        ``confidence_parts`` and addresses to the same ``RES-`` - and the machine checks
        that itself: ``ResolutionDecision.__post_init__`` recomputes its own id from its own
        material and raises if a supplied one disagrees. A tampered record therefore cannot
        be rehydrated into a decision claiming an address it does not follow. A failure
        here is reported as :class:`EntityIdentityError` with the machine's own message
        preserved, because a caller of a ``domain`` API should not have to catch a
        ``ValueError`` from a layer above it to handle a bad row.
        """
        try:
            return _rebuild_decision(self)
        except ImportError as unavailable:
            raise EntityIdentityError(
                "decision_rehydration_unavailable",
                "rehydrating a ResolutionDecision needs the semantic layer, which is not "
                f"importable here ({unavailable}); the stored record is still readable, and "
                "no caller that only reads durable state ever needs this direction",
            ) from unavailable
        except ValueError as mismatch:
            raise EntityIdentityError(
                "decision_rehydration_failed",
                f"record {self.resolution_decision_id!r} does not rehydrate into the "
                f"decision it claims to be: {mismatch}",
            ) from mismatch


#: Fields that decide *which resolution this was*. They are covered by
#: :meth:`ResolutionDecisionRecord._material` and enter ``resolution_decision_id``, so two
#: decisions that reasoned differently never share an address. Listed explicitly because
#: :func:`verify_decision_partition` has to be total, and "covered upstream" is exactly the
#: exemption that lets a field go unclassified.
RESOLUTION_DECISION_IDENTITY_FIELDS: frozenset[str] = frozenset(
    {
        "decision",
        "tenant",
        "mention",
        "surface",
        "verdict",
        "entity",
        "anchor_mention",
        "anchor_key",
        "merged_mentions",
        "considered",
        "surviving",
        "scored",
        "corroboration",
        "confidence",
        "confidence_parts",
        "normalization",
        "notes",
        "scope",
        "operator",
        "normalization_version",
        "ontology_version",
        "regime",
        "reasons",
        "blocked_out",
        "evidence",
        "blocking",
        "collective",
        "hypothesis",
    }
)
#: Fields a decision may restate without that being a different resolution, each for a
#: stated reason - the two reasons :data:`domain.relation_identity.MUTABLE_PROJECTION_FIELDS`
#: gives, applied to decisions:
#:
#: - ``decided_at`` - wall clock. Folding it in would make a decision re-run next week
#:   address differently from the identical decision run this week, which is the whole of
#:   D2 and the opposite of SC-3.
#: - ``supersedes`` - a link to a record that may not exist yet. A decision is written
#:   first and linked to what it revises afterwards, so a re-run reaching the same
#:   conclusion must reach the same address before the link exists.
#:
#: Both are mutable, so two records sharing a ``RES-`` may legitimately differ here. That
#: residual is bounded by ``decided_at`` being the tiebreak in the history order and by the
#: address being recomputed from the other fields alone.
RESOLUTION_DECISION_MUTABLE_PROJECTION_FIELDS: frozenset[str] = frozenset(
    {"decided_at", "supersedes"}
)


def _reason_from(record: Mapping[str, Any]) -> CompatibilityReason:
    """One recorded layer judgement, rebuilt as the machine's frozen value."""
    from semantic.resolution import CompatibilityLayer, CompatibilityReason, ReasonVerdict

    return CompatibilityReason(
        candidate_ref=record["candidate_ref"],
        layer=CompatibilityLayer(record["layer"]),
        code=record["code"],
        verdict=ReasonVerdict(record["verdict"]),
        detail=record["detail"],
        delta=float(record["delta"]),
    )


def _evidence_from(record: Mapping[str, Any]) -> CompatibilityEvidence:
    """One surviving candidate's compatibility record, rebuilt with its reasons."""
    from semantic.resolution import CompatibilityEvidence

    return CompatibilityEvidence(
        candidate_ref=record["candidate_ref"],
        reasons=tuple(_reason_from(reason) for reason in record.get("reasons") or ()),
        score=float(record.get("score", 0.0)),
        refused=bool(record.get("refused", False)),
        independent_corroboration=int(record.get("independent_corroboration", 0)),
        same_source_only=bool(record.get("same_source_only", False)),
        block_key=str(record.get("block_key", "")),
    )


def _type_hypothesis_from(record: Mapping[str, Any]) -> TypeHypothesis:
    """One type hypothesis, rebuilt with the vocabulary scheme it was framed in."""
    from semantic.blocking import TypeHypothesis
    from semantic.contracts import SemanticRef

    return TypeHypothesis(
        type_ref=record["type_ref"],
        scheme=SemanticRef(record["scheme"]),
        confidence=float(record.get("confidence", 1.0)),
    )


def _stage_reduction_from(record: Mapping[str, Any]) -> StageReduction:
    """One narrowing step's before/after counts, rebuilt."""
    from semantic.blocking import BlockingStage, StageReduction

    return StageReduction(
        stage=BlockingStage(record["stage"]),
        before_count=int(record["before_count"]),
        after_count=int(record["after_count"]),
    )


def _candidate_from(record: Mapping[str, Any]) -> Candidate:
    """One universe record as blocking saw it, rebuilt unaltered.

    Rebuilt rather than re-derived, so "pruning asserts nothing" survives the round trip:
    the frozen candidate a decision cites is the same value, not a fresh copy of a name.
    """
    from semantic.blocking import Candidate

    return Candidate(
        entity_ref=record["entity_ref"],
        name=record.get("name", ""),
        kind=record.get("kind", ""),
        type_refs=tuple(record.get("type_refs") or ()),
    )


def _blocking_result_from(record: Mapping[str, Any]) -> BlockingResult:
    """One per-comparison-key blocking result, rebuilt with its stages and hypotheses."""
    from semantic.blocking import BlockingResult, UnknownKindPolicy

    return BlockingResult(
        before_count=int(record["before_count"]),
        after_count=int(record["after_count"]),
        candidates=tuple(_candidate_from(item) for item in record.get("candidates") or ()),
        pruned_candidates=tuple(
            _candidate_from(item) for item in record.get("pruned_candidates") or ()
        ),
        blocking_keys=tuple(record.get("blocking_keys") or ()),
        scanned_keys=tuple(record.get("scanned_keys") or ()),
        stage_reductions=tuple(
            _stage_reduction_from(item) for item in record.get("stage_reductions") or ()
        ),
        type_hypotheses=tuple(
            _type_hypothesis_from(item) for item in record.get("type_hypotheses") or ()
        ),
        allowed_kinds=tuple(record.get("allowed_kinds") or ()),
        query_name=str(record.get("query_name", "")),
        unknown_kind_policy=UnknownKindPolicy(record.get("unknown_kind_policy", "retain")),
        unknown_kind_retained=int(record.get("unknown_kind_retained", 0)),
        unknown_kind_pruned=int(record.get("unknown_kind_pruned", 0)),
    )


def _blocking_from(record: Mapping[str, Any]) -> BlockingOutcome:
    """The whole blocking report for one mention, rebuilt."""
    from semantic.blocking import RelationRole
    from semantic.resolution import BlockingOutcome

    return BlockingOutcome(
        role=RelationRole(record["role"]),
        before_count=int(record.get("before_count", 0)),
        after_count=int(record.get("after_count", 0)),
        results=tuple(_blocking_result_from(item) for item in record.get("results") or ()),
        survivor_refs=tuple(record.get("survivor_refs") or ()),
        pruned_refs=tuple(record.get("pruned_refs") or ()),
        hypotheses=tuple(
            _type_hypothesis_from(item) for item in record.get("hypotheses") or ()
        ),
        allowed_kinds=tuple(record.get("allowed_kinds") or ()),
        query_keys=tuple(record.get("query_keys") or ()),
        type_hypotheses_offered=tuple(
            _type_hypothesis_from(item) for item in record.get("type_hypotheses_offered") or ()
        ),
        unknown_kind_retained=int(record.get("unknown_kind_retained", 0)),
        universe_fingerprint=tuple(record.get("universe_fingerprint") or ()),
        notes=tuple(record.get("notes") or ()),
    )


def _collective_from(record: Mapping[str, Any]) -> CollectiveOutcome:
    """The collective pass's outcome, rebuilt with every edge it removed."""
    from semantic.resolution import CollectiveOutcome, CollectiveRemoval

    return CollectiveOutcome(
        applied=bool(record.get("applied", False)),
        converged=bool(record.get("converged", False)),
        iterations=int(record.get("iterations", 0)),
        edges_before=int(record.get("edges_before", 0)),
        edges_after=int(record.get("edges_after", 0)),
        feasible={
            str(key): tuple(value) for key, value in (record.get("feasible") or {}).items()
        },
        committed={
            str(key): str(value) for key, value in (record.get("committed") or {}).items()
        },
        support={
            str(key): int(value) for key, value in (record.get("support") or {}).items()
        },
        contested=tuple(record.get("contested") or ()),
        removals=tuple(
            CollectiveRemoval(
                mention_id=item["mention_id"],
                candidate_ref=item["candidate_ref"],
                code=item["code"],
                detail=item.get("detail", ""),
            )
            for item in record.get("removals") or ()
        ),
        notes=tuple(record.get("notes") or ()),
    )


def _hypothesis_from(record: Mapping[str, Any]) -> EntityHypothesis:
    """The entity hypothesis, rebuilt with the anchor and the corroboration count."""
    from semantic.resolution import EntityHypothesis

    return EntityHypothesis(
        logical_entity_ref=record["logical_entity_ref"],
        candidate_ref=record.get("candidate_ref", ""),
        name=record.get("name", ""),
        anchor_mention_id=record.get("anchor_mention_id", ""),
        merged_mentions=tuple(record.get("merged_mentions") or ()),
        evidence_refs=tuple(record.get("evidence_refs") or ()),
        corroboration=int(record.get("corroboration", 0)),
        new_entity=bool(record.get("new_entity", False)),
        established=bool(record.get("established", False)),
    )


def _rebuild_decision(record: ResolutionDecisionRecord) -> ResolutionDecision:
    """Assemble the live decision from a stored record, field for field.

    Split out of :meth:`ResolutionDecisionRecord.to_decision` so that method carries only
    the error discipline and this one carries only the mapping. Every argument is supplied
    from the record, and the record's ``resolution_decision_id`` is passed back in, so the
    machine re-derives its own ``confidence``, recomputes its own address from its own
    decision material, and **refuses the result if the two disagree**. That is what makes
    the round trip self-checking rather than merely symmetric, and it is why the record
    carries the machine's address verbatim instead of deriving one of its own.
    """
    from semantic.resolution import ResolutionDecision, ResolutionVerdict

    return ResolutionDecision(
        resolution_decision_id=record.resolution_decision_id,
        mention_id=record.mention_id,
        surface=record.surface,
        verdict=ResolutionVerdict(record.verdict),
        logical_entity_ref=record.entity_ref,
        anchor_mention_id=record.anchor_mention_id,
        anchor_key=record.anchor_key,
        merged_mentions=record.merged_mentions,
        considered=record.considered,
        surviving=record.surviving,
        scored=record.scored,
        evidence=tuple(_evidence_from(item) for item in record.evidence),
        reasons=tuple(_reason_from(item) for item in record.reasons),
        blocked_out=tuple(_reason_from(item) for item in record.blocked_out),
        normalization=record.normalization,
        blocking=None if record.blocking is None else _blocking_from(record.blocking),
        collective=None if record.collective is None else _collective_from(record.collective),
        hypothesis=None if record.hypothesis is None else _hypothesis_from(record.hypothesis),
        corroboration=record.corroboration,
        confidence_parts=record.confidence_parts,
        resolution_scope_id=record.resolution_scope_id,
        tenant_id=record.tenant_id,
        operator_ref=record.operator_ref,
        normalization_version=record.normalization_version,
        ontology_version=record.ontology_version,
        regime_id=record.regime_id,
        notes=record.notes,
    )


def verify_identity_partition(identity: EntityIdentity) -> None:
    """Refuse a field on :class:`EntityIdentity` that is neither material nor declared.

    The same total-partition check
    :func:`domain.relation_identity.verify_material_partition` performs, and for the same
    reason: without it a field added later lands in no set and is quietly excluded from the
    address, which is how a durable anchor stops being derived from its own record one
    field at a time. The three classes are exhaustive and disjoint - write-once identity
    material, declared projection material, and the derived address. A store calls this on
    the way in, the way a claim store calls ``verify_material_partition``.
    """
    material = set(identity._material())  # noqa: SLF001 - the point is to read it all
    derived = {"identity_fingerprint"}
    classified = (
        ENTITY_IDENTITY_IDENTITY_FIELDS | ENTITY_IDENTITY_MUTABLE_PROJECTION_FIELDS | derived
    )
    unclassified = sorted(material - classified)
    if unclassified:
        raise EntityIdentityError(
            "identity_partition_incomplete",
            f"EntityIdentity fields are neither identity material nor declared mutable "
            f"projection metadata: {unclassified}. Add each to "
            "ENTITY_IDENTITY_IDENTITY_FIELDS or ENTITY_IDENTITY_MUTABLE_PROJECTION_FIELDS "
            "in domain.entity_identity so the partition stays total.",
        )
    overlap = sorted(ENTITY_IDENTITY_IDENTITY_FIELDS & ENTITY_IDENTITY_MUTABLE_PROJECTION_FIELDS)
    if overlap:
        raise EntityIdentityError(
            "identity_partition_overlap",
            f"fields classified as both identity and mutable material: {overlap}",
        )


def verify_decision_partition(record: ResolutionDecisionRecord) -> None:
    """Refuse a field on :class:`ResolutionDecisionRecord` that is neither material nor declared.

    The decision-side twin of :func:`verify_identity_partition`, over
    :meth:`ResolutionDecisionRecord._material`. It also checks the declared set against the
    material actually digested, so a field added to one and not the other is caught here
    rather than surfacing as a decision whose id ignores part of its own reasoning.
    """
    material = set(record._material())  # noqa: SLF001 - read it all
    identity = RESOLUTION_DECISION_IDENTITY_FIELDS
    mutable = RESOLUTION_DECISION_MUTABLE_PROJECTION_FIELDS
    derived = {"record_fingerprint"}
    unclassified = sorted(material - identity - mutable)
    if unclassified:
        raise EntityIdentityError(
            "decision_partition_incomplete",
            f"ResolutionDecisionRecord fields are neither identity material nor declared "
            f"mutable projection metadata: {unclassified}. Add each to "
            "RESOLUTION_DECISION_IDENTITY_FIELDS or "
            "RESOLUTION_DECISION_MUTABLE_PROJECTION_FIELDS in domain.entity_identity so the "
            "partition stays total.",
        )
    for left, right, label in (
        (identity, mutable, "identity and mutable"),
        (identity, derived, "identity and derived"),
        (mutable, derived, "mutable and derived"),
    ):
        overlap = sorted(left & right)
        if overlap:
            raise EntityIdentityError(
                "decision_partition_overlap",
                f"fields classified as both {label} material: {overlap}",
            )
    drifted = sorted(identity - material)
    if drifted:
        raise EntityIdentityError(
            "decision_partition_drifted",
            "RESOLUTION_DECISION_IDENTITY_FIELDS declares fields the material does not emit, "
            f"so their values would be absent from the address: {drifted}",
        )


@dataclass(frozen=True)
class ReconstructionHole:
    """One link of the reconstruction chain this store cannot show, named rather than hidden."""

    link: ChainLink
    code: str
    detail: str

    def __str__(self) -> str:
        """The hole as one line, naming the link so a report points at the missing hop."""
        return f"[{self.link}] {self.code}: {self.detail}"


@dataclass(frozen=True)
class EntityReconstruction:
    """One entity's history, reassembled from durable state, with its holes named.

    What it answers: which mention introduced this entity, which resolution created it, every
    decision ever made about it in order - including the ones that concluded ``ambiguous``
    and named no entity, reached through :attr:`supersedes` - the mentions merged along the
    way, and what the last decision concluded. That is FR-004 and SC-2, and the reason
    :attr:`merged_mentions` and :attr:`terminal_verdict` are here at all: an outcome without
    the mentions that produced it is not a reconstruction.

    What it does **not** do is return a short chain that reads as whole. Every gap this
    store can see is a :class:`ReconstructionHole` naming its :class:`ChainLink`, so
    :attr:`complete` is a fact rather than an impression and :meth:`assert_complete` turns a
    partial chain into a refusal for a caller that must not proceed on one. Whether the
    anchor's *observation* and *capture* rows exist is another store's question -
    :mod:`domain.evidence_lineage` is what traverses those hops - and a hole is claimed here
    only for a reference this record failed to write down.
    """

    tenant_id: str
    entity_id: str
    identity: EntityIdentity
    decisions: tuple[ResolutionDecisionRecord, ...] = ()
    current_decision: ResolutionDecisionRecord | None = None
    terminal_verdict: str = ""
    merged_mentions: tuple[str, ...] = ()
    holes: tuple[ReconstructionHole, ...] = ()

    @property
    def complete(self) -> bool:
        """Whether every link this store can attest is present."""
        return not self.holes

    @property
    def anchor_mention_id(self) -> str:
        """The mention that introduced the entity; always present or refused at bind time."""
        return self.identity.anchor_mention_id

    @property
    def anchor_observation_id(self) -> str:
        """The observation the anchor mention came from, or empty if never recorded."""
        return self.identity.anchor_observation_id

    @property
    def anchor_capture_id(self) -> str:
        """The capture that fetched those bytes, or empty if never recorded."""
        return self.identity.anchor_capture_id

    def decision_ids(self) -> tuple[str, ...]:
        """Every ``RES-`` in the history, in order, for a byte-comparison or a log line."""
        return tuple(record.resolution_decision_id for record in self.decisions)

    def non_resolving(self) -> tuple[ResolutionDecisionRecord, ...]:
        """The decisions that named no entity, in order (FR-004, SC-2).

        Included deliberately and not as a curiosity: "why is this entity this entity"
        includes the passes that *failed* to say, and a history that omits them cannot
        answer the question. Returns every decision whose recorded ``entity_ref`` is empty -
        ambiguous, unresolved and conflicted alike - because the machine declines to name an
        entity for all three and this module does not rank them against each other.
        """
        return tuple(record for record in self.decisions if not record.names_entity)

    def assert_complete(self) -> EntityReconstruction:
        """Return ``self``, or refuse naming every hole.

        For the caller that must not act on a partial chain: the error message carries all
        of them rather than the first, so one pass shows the whole extent of the gap instead
        of one link per attempt.
        """
        if self.holes:
            raise EntityIdentityError(
                "reconstruction_incomplete",
                f"entity {self.entity_id} does not reconstruct with no hole: "
                + "; ".join(str(hole) for hole in self.holes),
            )
        return self

    def to_dict(self) -> dict[str, Any]:
        """The reconstruction as a plain mapping, for a log line or a report payload."""
        return {
            "tenant_id": self.tenant_id,
            "entity_id": self.entity_id,
            "identity": self.identity.to_dict(),
            "anchor_mention_id": self.anchor_mention_id,
            "anchor_observation_id": self.anchor_observation_id,
            "anchor_capture_id": self.anchor_capture_id,
            "decisions": [record.to_dict() for record in self.decisions],
            "terminal_verdict": self.terminal_verdict,
            "merged_mentions": list(self.merged_mentions),
            "complete": self.complete,
            "holes": [
                {"link": str(hole.link), "code": hole.code, "detail": hole.detail}
                for hole in self.holes
            ],
        }


def _scoped(tenant_id: str) -> str:
    """One tenant as a canonical read key, or fail closed on a blank one (constitution IV).

    Every read passes through here. A read with no tenant is the failure mode FR-005 is
    about - a query that accidentally spans tenants still returns rows, it just returns the
    wrong ones - so it is refused before any lookup rather than defaulted.
    """
    tenant = str(tenant_id or "").strip()
    if not tenant:
        raise EntityIdentityError(
            "tenant_missing",
            "every anchor read, decision read and reconstruction is tenant-scoped; a read "
            "with no tenant would span tenants silently (FR-005)",
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
        f"{kind} {asked!r} is not in tenant {tenant!r}; it is held by tenant(s) "
        f"{held_by}, and returning nothing for it would make 'not yours' indistinguishable "
        "from 'not there' (FR-005)",
        requested_by=tenant,
        held_by=held_by[0],
    )


def _history_key(record: ResolutionDecisionRecord) -> tuple[bool, str, str]:
    """Total order for a decision history: decided time, then address as the tiebreak.

    The address breaks ties so two decisions recorded at the same instant have one ordering
    in every process (constitution VI). Records with no time sort last, so a decided chain
    is never displaced by an undecided one.
    """
    return (
        record.decided_at is None,
        _iso(record.decided_at) or "",
        record.resolution_decision_id,
    )


class InMemoryResolutionDecisionLog:
    """The append-only decision log, and the ordered history one entity is read back from.

    Append-only in the strict sense the data requirements ask for: :meth:`append` refuses a
    *different* record under an address it already holds, and there is no update or delete
    operation at all. Growth of knowledge adds decisions; it never edits one (FR-003,
    US3).

    :meth:`history_for` is the reconstruction read path, and it does something the table
    cannot do for free: it walks the ``supersedes`` chain in both directions. A decision
    that named no entity - ``ambiguous``, ``unresolved``, ``conflicted`` - has an empty
    ``entity_ref`` and cannot be filed under one without a record lying about what the
    resolver concluded, so the link is the chain, and the chain is what puts those decisions
    in the history of the entity a later pass settled (FR-004, SC-2).
    """

    def __init__(self, records: Iterable[ResolutionDecisionRecord] = ()) -> None:
        self._by_id: dict[tuple[str, str], ResolutionDecisionRecord] = {}
        self._owners: dict[str, set[str]] = {}
        self._by_mention: dict[tuple[str, str], list[ResolutionDecisionRecord]] = {}
        self._successors: dict[tuple[str, str], set[str]] = {}
        for record in records:
            self.append(record)

    def _link(self, record: ResolutionDecisionRecord) -> None:
        """Index one record's outgoing ``supersedes`` edges and the reverse of them.

        Maintained on write rather than scanned on read, because :meth:`history_for` walks
        the chain in both directions and a scan per read would make the reconstruction hot
        path linear in the whole log. The two indexes are the shape the SQL store carries
        for the same read: ``(tenant_id, entity_ref, decided_at)`` for the roots and
        ``(tenant_id, supersedes)`` for the edges.
        """
        for referenced in record.supersedes:
            self._successors.setdefault((record.tenant_id, referenced), set()).add(
                record.resolution_decision_id
            )

    def append(self, record: ResolutionDecisionRecord) -> ResolutionDecisionRecord:
        """Store one decision; idempotent on its address, never an overwrite.

        Idempotence is decided on the content address rather than on record equality, so
        re-appending the same decision recorded at a different time is the same write - the
        same reasoning about the same mention is one decision however often it is replayed
        (I-11, FR-022) - while a *different* record under one address is refused rather
        than merged.

        **A re-append may still fill in ``supersedes``**, because that field is excluded
        from the address for exactly this reason: a decision is written first and linked to
        what it revises afterwards. So the links are unioned onto the stored record and
        everything else keeps the stored value - ``decided_at`` included, so a replay cannot
        move when a decision was taken. That is a link fill, not an edit, and it is the
        only way this log mutates anything it already holds.
        """
        addressed = record.with_id()
        key = (addressed.tenant_id, addressed.resolution_decision_id)
        held = self._by_id.get(key)
        if held is not None:
            if held.content_key() != addressed.content_key():
                raise EntityIdentityError(
                    "decision_id_conflict",
                    f"decision {addressed.resolution_decision_id} is already recorded with "
                    "different reasoning; decisions are never overwritten (FR-003)",
                )
            links = tuple(sorted({*held.supersedes, *addressed.supersedes}))
            if links == held.supersedes:
                return held
            linked = replace(held, supersedes=links)
            self._by_id[key] = linked
            self._link(linked)
            return linked
        self._by_id[key] = addressed
        self._owners.setdefault(addressed.resolution_decision_id, set()).add(
            addressed.tenant_id
        )
        self._by_mention.setdefault((addressed.tenant_id, addressed.mention_id), []).append(
            addressed
        )
        self._link(addressed)
        return addressed

    def record(
        self, tenant_id: str, resolution_decision_id: str
    ) -> ResolutionDecisionRecord | None:
        """One decision by address, or ``None`` for an id this tenant has not recorded.

        Fail-closed across tenants: an address held by another tenant raises
        :class:`CrossTenantRefusal` rather than returning ``None``, so "not yours" is never
        read as "not there" (FR-005).
        """
        tenant = _scoped(tenant_id)
        wanted = str(resolution_decision_id or "").strip()
        held = self._by_id.get((tenant, wanted))
        if held is not None:
            return held
        _refuse_elsewhere(
            self._owners.get(wanted, ()), tenant, "cross_tenant_decision", wanted, "decision"
        )
        return None

    def history_for_mention(
        self, tenant_id: str, mention_id: str
    ) -> tuple[ResolutionDecisionRecord, ...]:
        """Every decision taken about one mention, in order, chain links included.

        A mention that was resolved, then re-examined and found ambiguous has two records
        here and one entity; this is the view that shows both, and the entity view
        (:meth:`history_for`) is the one that shows which entity they concern.
        """
        tenant = _scoped(tenant_id)
        records = self._by_mention.get((tenant, str(mention_id or "").strip()), [])
        return tuple(sorted(records, key=_history_key))

    def history_for(self, tenant_id: str, entity_ref: str) -> tuple[ResolutionDecisionRecord, ...]:
        """Every decision about one entity, in order, including those that named none.

        Roots are the records that name the entity, and from each root the chain is walked
        **in both directions**, which is what it takes to reach every non-naming decision:

        - backwards, through a root's :attr:`ResolutionDecisionRecord.supersedes`, so the
          passes the entity's own decision revised are reached;
        - forwards, through the records that supersede a reached decision - but only those
          that either name this entity or **name no entity at all**. A successor that named
          a *different* entity is excluded, because a mention re-resolved away from here
          belongs to that other entity's history and not to this one.

        That asymmetry is the whole mechanism. An ``ambiguous``, ``unresolved`` or
        ``conflicted`` pass has an empty ``entity_ref`` and cannot be filed under an entity
        without a record lying about what the resolver concluded, so the chain is what puts
        it in the history of the entity a later pass settled (FR-004, SC-2, US2). Ordered by
        ``(decided_at, address)``, which is total, so two processes reading the same log
        read it the same way (constitution VI).
        """
        tenant = _scoped(tenant_id)
        wanted = str(entity_ref or "").strip()
        if not wanted:
            return ()
        reachable: dict[str, ResolutionDecisionRecord] = {}
        frontier = [
            key[1]
            for key, record in self._by_id.items()
            if record.tenant_id == tenant and record.entity_ref == wanted
        ]
        while frontier:
            current = frontier.pop()
            if current in reachable:
                continue
            record = self._by_id.get((tenant, current))
            if record is None:
                continue
            reachable[current] = record
            frontier.extend(record.supersedes)
            for other in sorted(self._successors.get((tenant, current), ())):
                candidate = self._by_id.get((tenant, other))
                if candidate is not None and candidate.entity_ref in ("", wanted):
                    frontier.append(other)
        return tuple(sorted(reachable.values(), key=_history_key))

    def terminal(self, tenant_id: str, entity_ref: str) -> ResolutionDecisionRecord | None:
        """The current decision for an entity, or ``None`` when it has none yet.

        The last of :meth:`history_for`: the latest reasoning is the current one, and a
        later decision that revised it is exactly what "current" means here.
        """
        history = self.history_for(tenant_id, entity_ref)
        return history[-1] if history else None

    def __len__(self) -> int:
        return len(self._by_id)

    def __contains__(self, resolution_decision_id: object) -> bool:
        return str(resolution_decision_id) in self._owners


class InMemoryEntityIdentityStore:
    """The durable anchor substrate, with exactly the two read paths the layers above need.

    Three operations and no fourth:

    - :meth:`anchor_for_mention` - the **resolution hot path**: "does this mention already
      anchor an entity?" It is one indexed read on ``(tenant_id, anchor_mention_id)`` in the
      storage layer, which is why the index exists and why the column pair is the one
      UNIQUE constraint in the schema (D-A, SC-17).
    - :meth:`identity_for_entity` and :meth:`history` - the **reconstruction hot path**:
      "which anchor introduced this entity, and what has been decided about it since?"
      Index on ``(tenant_id, entity_id)``, returning the record and the ordered set.

    Adding a third read path here would be adding a query no layer above has asked for, and
    the schema follows the read paths rather than the other way round (plan D1).

    **Both read paths are fail-closed across tenants.** A miss returns ``None`` only when
    the tenant genuinely holds no such record; if the id exists under a *different* tenant
    the call raises :class:`CrossTenantRefusal` naming the tenant that holds it. The
    alternative - returning ``None`` for both - makes "this tenant has no such entity" and
    "this entity belongs to someone else" the same value at the call site, and the second
    is a boundary violation that has to be visible (constitution IV, FR-005).

    :meth:`bind` is the write-once check: the in-memory form of the UNIQUE index, and the
    place a typed :class:`AnchorConflict` is raised. Re-binding the same identity is
    idempotent and returns the *stored* record, so a re-ingest cannot move ``created_at``.
    """

    def __init__(
        self,
        identities: Iterable[EntityIdentity] = (),
        decisions: Iterable[ResolutionDecisionRecord] = (),
    ) -> None:
        self._by_anchor: dict[tuple[str, str], EntityIdentity] = {}
        self._by_entity: dict[tuple[str, str], list[EntityIdentity]] = {}
        self._mention_owners: dict[str, set[str]] = {}
        self._entity_owners: dict[str, set[str]] = {}
        self.decisions = InMemoryResolutionDecisionLog(decisions)
        for identity in identities:
            self.bind(identity)

    def bind(self, identity: EntityIdentity) -> EntityIdentity:
        """Store one anchor, write-once, and return the record that is now durable.

        The write-once check has two halves, because "write-once" constrains two things at
        once: one mention may not anchor two entities, and one entity may not have two
        anchors. A bare UNIQUE index on ``(tenant_id, anchor_mention_id)`` covers the first
        and not the second, so the second is checked here and reported with its own code
        (``entity_reanchored``) - a second anchor for one entity is exactly the "an anchor
        silently moved" failure FR-001 forbids, and it is invisible to the index.

        Idempotent when the incoming record addresses to the same content, returning the
        **stored** record rather than the incoming one, so a re-ingest with a different
        ``created_at`` neither conflicts nor silently restates when the anchor was written.
        """
        record = identity.with_id()
        held = self._by_anchor.get((record.tenant_id, record.anchor_mention_id))
        if held is not None:
            if held.identity_fingerprint == record.identity_fingerprint:
                return held
            conflict = AnchorConflict(
                "anchor_mention_rebound",
                f"mention {record.anchor_mention_id!r} in tenant {record.tenant_id!r} "
                f"already anchors {held.entity_id!r}; it cannot also anchor "
                f"{record.entity_id!r}. An anchor is elected once and recorded, and a "
                "recomputed one is the defect (FR-001).",
            )
            conflict.anchor_mention_id = record.anchor_mention_id
            conflict.held_entity_id = held.entity_id
            conflict.rejected_entity_id = record.entity_id
            raise conflict
        for existing in self._by_entity.get((record.tenant_id, record.entity_id), ()):
            conflict = AnchorConflict(
                "entity_reanchored",
                f"entity {record.entity_id!r} is already anchored by mention "
                f"{existing.anchor_mention_id!r}; it cannot also be anchored by "
                f"{record.anchor_mention_id!r}. Growth of knowledge adds decisions; it "
                "never re-elects an anchor.",
            )
            conflict.anchor_mention_id = existing.anchor_mention_id
            conflict.held_entity_id = record.entity_id
            conflict.rejected_entity_id = record.entity_id
            raise conflict
        self._by_anchor[(record.tenant_id, record.anchor_mention_id)] = record
        self._by_entity.setdefault((record.tenant_id, record.entity_id), []).append(record)
        self._mention_owners.setdefault(record.anchor_mention_id, set()).add(record.tenant_id)
        self._entity_owners.setdefault(record.entity_id, set()).add(record.tenant_id)
        return record

    def anchor_for_mention(
        self, tenant_id: str, anchor_mention_id: str
    ) -> EntityIdentity | None:
        """Whether this mention already anchors an entity, and which one (the hot path).

        ``None`` only for a mention this tenant has never anchored anything with. A mention
        anchored under another tenant raises instead: the caller is asking about a real
        mention and the answer "not yours" is a different fact from "no" (FR-005).
        """
        tenant = _scoped(tenant_id)
        wanted = str(anchor_mention_id or "").strip()
        if not wanted:
            raise EntityIdentityError(
                "anchor_mention_missing",
                "an anchor lookup needs the mention id; a lookup with none cannot be "
                "answered and must not be read as 'this mention anchors nothing'",
            )
        held = self._by_anchor.get((tenant, wanted))
        if held is not None:
            return held
        _refuse_elsewhere(
            self._mention_owners.get(wanted, ()),
            tenant,
            "cross_tenant_anchor",
            wanted,
            "anchor mention",
        )
        return None

    def identity_for_entity(self, tenant_id: str, entity_id: str) -> EntityIdentity | None:
        """The durable anchor of one entity, or ``None`` when this tenant holds no record.

        The current record, which is the only one: an anchor is write-once, so the tuple
        :meth:`history` returns has one member until this store carries a second kind of
        statement about identity.
        """
        tenant = _scoped(tenant_id)
        wanted = str(entity_id or "").strip()
        if not wanted:
            raise EntityIdentityError(
                "entity_id_missing",
                "an identity lookup needs the entity id; a lookup with none cannot be "
                "answered",
            )
        records = self._by_entity.get((tenant, wanted))
        if records:
            return records[-1]
        _refuse_elsewhere(
            self._entity_owners.get(wanted, ()),
            tenant,
            "cross_tenant_identity",
            wanted,
            "entity",
        )
        return None

    def history(self, tenant_id: str, entity_id: str) -> tuple[EntityIdentity, ...]:
        """Every identity statement recorded for one entity, in bind order.

        The same answer :meth:`identity_for_entity` gives as a single value, in the shape
        the storage layer's ordered query returns, so a caller reconstructing a history and
        a caller checking one identity read the same index rather than two code paths.
        """
        tenant = _scoped(tenant_id)
        wanted = str(entity_id or "").strip()
        records = tuple(self._by_entity.get((tenant, wanted), ()))
        if records:
            return records
        _refuse_elsewhere(
            self._entity_owners.get(wanted, ()),
            tenant,
            "cross_tenant_identity",
            wanted,
            "entity",
        )
        return ()

    def record_decision(
        self, record: ResolutionDecisionRecord
    ) -> ResolutionDecisionRecord:
        """Append one decision to the log; idempotent on its address, never an overwrite."""
        return self.decisions.append(record)

    def ingest_scope(
        self,
        scope: ResolutionScope,
        decisions: Iterable[ResolutionDecision | ResolutionDecisionRecord] = (),
        *,
        anchor_observations: Mapping[str, str] | None = None,
        anchor_captures: Mapping[str, str] | None = None,
        decided_at: datetime | None = None,
        created_at: datetime | None = None,
    ) -> tuple[EntityIdentity, ...]:
        """Persist a resolver's scope into durable state, so the scope may then be dropped.

        **This is the bridge that makes FR-002 real.** ``MentionResolver`` stays stateless
        and its caller stays free to lose everything; what survives is a row per anchor.
        A later batch re-reads those rows through :meth:`anchor_for_mention`, rebuilds the
        scope, and the later mention of the same entity joins the entity the first mention
        created instead of minting a new ``ENT-`` (SC-1, US1). The loss the spec describes
        becomes a missed optimisation rather than an identity change.

        Every decision supplied is recorded, **including the ones that named no entity** -
        an ``ambiguous`` or ``unresolved`` pass is a decision, and it is the only evidence
        that the resolver tried and declined (FR-004, SC-2). Such a decision creates no
        anchor, because there is no entity to anchor.

        An anchor whose creating decision is not among those supplied is **refused**, not
        bound with a guessed attribution: the orchestrator has the decisions in hand at this
        point, so a failure to match is a defect in the wiring, and binding anyway would put
        a chain hole at step one of every reconstruction. An identity adopted from state
        written before this table existed uses :data:`UNATTRIBUTED_RESOLUTION` instead, which
        is a declared absence rather than a guess.

        ``anchor_observations`` and ``anchor_captures`` map an anchor mention id to the
        observation and the capture it came from. They are not derivable here - resolution
        never sees an observation or a capture - and they are exactly the two references that
        make the entity half of SC-14's chain reachable, so a caller with them supplies them
        and a caller without them records a reconstruction hole rather than a fabricated id.

        Both ``decided_at`` and ``created_at`` are the caller's. This module reads no clock,
        and a defaulted one would make replay non-deterministic (constitution VII).
        """
        observations = dict(anchor_observations or {})
        captures = dict(anchor_captures or {})
        creators: dict[tuple[str, str], ResolutionDecisionRecord] = {}
        for decision in decisions:
            record = (
                decision
                if isinstance(decision, ResolutionDecisionRecord)
                else ResolutionDecisionRecord.from_decision(decision, decided_at=decided_at)
            )
            self.decisions.append(record)
            if record.entity_ref and record.anchor_mention_id:
                creators.setdefault(
                    (record.entity_ref, record.anchor_mention_id), record
                )
        if created_at is None:
            raise EntityIdentityError(
                "identity_created_at_missing",
                "ingest_scope requires created_at: this module reads no clock, and a "
                "defaulted creation time would make replay non-deterministic (VII)",
            )
        bound: list[EntityIdentity] = []
        for anchor in scope.anchors:
            if not anchor.logical_entity_ref:
                continue
            creator = creators.get((anchor.logical_entity_ref, anchor.anchor_mention_id))
            if creator is None:
                raise EntityIdentityError(
                    "anchor_creation_unrecorded",
                    f"anchor {anchor.logical_entity_ref!r} on mention "
                    f"{anchor.anchor_mention_id!r} has no recorded resolution that created "
                    "it among the decisions supplied; an identity whose origin is unknown "
                    "cannot be durably bound, because the chain would have a hole at its "
                    "first link (FR-001, FR-004). Supply the batch's decisions, or adopt "
                    f"the entity explicitly with {UNATTRIBUTED_RESOLUTION}.",
                )
            bound.append(
                self.bind(
                    EntityIdentity(
                        entity_id=anchor.logical_entity_ref,
                        tenant_id=scope.tenant_id,
                        anchor_mention_id=anchor.anchor_mention_id,
                        anchor_observation_id=observations.get(anchor.anchor_mention_id, ""),
                        anchor_capture_id=captures.get(anchor.anchor_mention_id, ""),
                        created_by_resolution=creator.resolution_decision_id,
                        created_at=created_at,
                    )
                )
            )
        return tuple(sorted(bound, key=lambda record: record.entity_id))

    def supersede(
        self,
        tenant_id: str,
        entity_id: str,
        decision: ResolutionDecision | ResolutionDecisionRecord,
        *,
        decided_at: datetime | None = None,
        supersedes: tuple[str, ...] | None = None,
    ) -> ResolutionDecisionRecord:
        """Record a later decision about a known entity, leaving its anchor untouched.

        This is the operation the platform's own vocabulary calls "growth of knowledge
        adds decisions; it never re-elects an anchor", made structural: nothing on this path
        can reach the anchor indexes. The identity record is not read for anything but
        existence, and the returned value is a decision - the anchor cannot be changed from
        here even by a caller that asks for it, because there is no parameter to ask with.

        ``supersedes`` defaults to the entity's current terminal decision, so a re-decision
        links itself to what it revised and the chain the history walks is automatic. It may
        name *more* - and that is how an ``ambiguous`` or ``unresolved`` pass reaches the
        history of the entity a later pass settled, without that record ever claiming to name
        an entity the resolver declined to name (FR-004, SC-2).

        Fail-closed: an entity this tenant does not hold is refused, an entity another
        tenant holds is a :class:`CrossTenantRefusal`, a decision belonging to another
        tenant is refused, and a decision that names a *different* entity is refused rather
        than filed under this one.
        """
        tenant = _scoped(tenant_id)
        wanted = str(entity_id or "").strip()
        identity = self.identity_for_entity(tenant, wanted)
        if identity is None:
            raise EntityIdentityError(
                "entity_identity_unknown",
                f"tenant {tenant!r} holds no identity record for {wanted!r}; a decision "
                "cannot be attributed to an entity whose anchor was never bound (FR-001)",
            )
        if isinstance(decision, ResolutionDecisionRecord):
            record = decision.with_id()
        else:
            if decided_at is None:
                raise EntityIdentityError(
                    "decision_time_missing",
                    "supersede requires decided_at for a live decision: this module reads no "
                    "clock, and the ordered history is only ordered if the caller says when",
                )
            record = ResolutionDecisionRecord.from_decision(decision, decided_at=decided_at)
        if record.tenant_id != tenant:
            raise CrossTenantRefusal(
                "cross_tenant_decision",
                f"decision {record.resolution_decision_id} belongs to tenant "
                f"{record.tenant_id!r} and cannot be recorded against tenant {tenant!r}'s "
                "entity (FR-005)",
                requested_by=tenant,
                held_by=record.tenant_id,
            )
        if record.entity_ref and record.entity_ref != wanted:
            raise EntityIdentityError(
                "decision_entity_mismatch",
                f"decision {record.resolution_decision_id} names entity "
                f"{record.entity_ref!r} and cannot be filed against {wanted!r}; a decision "
                "is filed under the entity it concluded, never under one it did not",
            )
        if supersedes is None:
            current = self.decisions.terminal(tenant, wanted)
            links = (current.resolution_decision_id,) if current is not None else ()
        else:
            links = tuple(supersedes)
        if links != record.supersedes:
            record = replace(record, supersedes=links).with_id()
        return self.decisions.append(record)

    def reconstruct(self, tenant_id: str, entity_id: str) -> EntityReconstruction:
        """Rebuild one entity's whole history from durable state, naming any hole (FR-004).

        The reconstruction hot path's answer: the anchor, the ordered ``RES-`` history, the
        mentions merged, and the terminal verdict. It reads the identity record, the
        decision chain the log can reach, and nothing else - so it works in a fresh process
        with an empty caller and a discarded scope, which is the point (SC-1).

        Every gap this store can see becomes a :class:`ReconstructionHole` on the result
        rather than a shorter chain, so ``complete`` is a fact and
        :meth:`EntityReconstruction.assert_complete` can refuse a caller that must not act on
        a partial one. What it cannot see is reported as absent from the *check*, not as a
        hole: whether the anchor observation and capture rows exist is another store's
        question, and claiming a hole there would put a false hole on every healthy run.
        """
        tenant = _scoped(tenant_id)
        wanted = str(entity_id or "").strip()
        identity = self.identity_for_entity(tenant, wanted)
        if identity is None:
            raise EntityIdentityError(
                "entity_identity_unknown",
                f"tenant {tenant!r} holds no identity record for {wanted!r}; there is no "
                "anchor to reconstruct from (FR-004)",
            )
        decisions = self.decisions.history_for(tenant, wanted)
        current = decisions[-1] if decisions else None
        holes: list[ReconstructionHole] = []

        creator = self.decisions.record(tenant, identity.created_by_resolution)
        if creator is None:
            holes.append(
                ReconstructionHole(
                    link=ChainLink.CREATING_DECISION,
                    code="creating_decision_missing",
                    detail=(
                        f"the identity names {identity.created_by_resolution} as the "
                        "resolution that created it, and no such decision is recorded for "
                        "this tenant"
                    ),
                )
            )
        elif creator.entity_ref and creator.entity_ref != identity.entity_id:
            holes.append(
                ReconstructionHole(
                    link=ChainLink.CREATING_DECISION,
                    code="creating_decision_entity_mismatch",
                    detail=(
                        f"{creator.resolution_decision_id} created {creator.entity_ref}, but "
                        f"the identity record claims {identity.entity_id}"
                    ),
                )
            )
        if not decisions:
            holes.append(
                ReconstructionHole(
                    link=ChainLink.DECISION_HISTORY,
                    code="decision_history_empty",
                    detail="no decision naming this entity is recorded for this tenant",
                )
            )
        for record in decisions:
            for referenced in record.supersedes:
                if referenced in {held.resolution_decision_id for held in decisions}:
                    continue
                if self.decisions.record(tenant, referenced) is not None:
                    continue
                holes.append(
                    ReconstructionHole(
                        link=ChainLink.DECISION_HISTORY,
                        code="superseded_decision_missing",
                        detail=(
                            f"{record.resolution_decision_id} supersedes "
                            f"{referenced}, which is not recorded for this tenant"
                        ),
                    )
                )
        if current is None:
            holes.append(
                ReconstructionHole(
                    link=ChainLink.TERMINAL_VERDICT,
                    code="terminal_verdict_unreadable",
                    detail="with no decision in the history there is no current verdict",
                )
            )
        merged: set[str] = set()
        for record in decisions:
            merged.update(record.merged_mentions)
        if current is not None and current.names_entity and not current.merged_mentions:
            holes.append(
                ReconstructionHole(
                    link=ChainLink.MERGED_MENTIONS,
                    code="merged_mentions_unrecorded",
                    detail=(
                        f"{current.resolution_decision_id} resolved to this entity but "
                        "records no merged mention, so the mentions behind the identity are "
                        "not reconstructable"
                    ),
                )
            )
        if decisions and identity.anchor_mention_id not in merged:
            holes.append(
                ReconstructionHole(
                    link=ChainLink.MERGED_MENTIONS,
                    code="anchor_mention_not_merged",
                    detail=(
                        f"the anchor mention {identity.anchor_mention_id!r} appears in no "
                        "recorded decision's merged set"
                    ),
                )
            )
        if not identity.anchor_observation_id:
            holes.append(
                ReconstructionHole(
                    link=ChainLink.ANCHOR_OBSERVATION,
                    code="anchor_observation_unrecorded",
                    detail=(
                        f"anchor mention {identity.anchor_mention_id!r} records no "
                        "observation, so the entity cannot be traced back to content"
                    ),
                )
            )
        if not identity.anchor_capture_id:
            holes.append(
                ReconstructionHole(
                    link=ChainLink.ANCHOR_CAPTURE,
                    code="anchor_capture_unrecorded",
                    detail=(
                        f"anchor mention {identity.anchor_mention_id!r} records no capture, "
                        "so the bytes behind the entity cannot be traced back to a fetch"
                    ),
                )
            )
        return EntityReconstruction(
            tenant_id=tenant,
            entity_id=identity.entity_id,
            identity=identity,
            decisions=decisions,
            current_decision=current,
            terminal_verdict=current.verdict if current is not None else "",
            merged_mentions=tuple(sorted(merged)),
            holes=tuple(holes),
        )

    def __len__(self) -> int:
        return len(self._by_anchor)

    def __contains__(self, entity_id: object) -> bool:
        return str(entity_id) in self._entity_owners


__all__ = [
    "ENTITY_IDENTITY_IDENTITY_FIELDS",
    "ENTITY_IDENTITY_MUTABLE_PROJECTION_FIELDS",
    "ENTITY_ID_PREFIX",
    "RESOLUTION_DECISION_IDENTITY_FIELDS",
    "RESOLUTION_DECISION_MUTABLE_PROJECTION_FIELDS",
    "RESOLUTION_ID_PREFIX",
    "RESOLUTION_VERDICTS",
    "UNATTRIBUTED_RESOLUTION",
    "AnchorConflict",
    "ChainLink",
    "CrossTenantRefusal",
    "EntityIdentity",
    "EntityIdentityError",
    "EntityReconstruction",
    "InMemoryEntityIdentityStore",
    "InMemoryResolutionDecisionLog",
    "ReconstructionHole",
    "ResolutionDecisionRecord",
    "verify_decision_partition",
    "verify_identity_partition",
]
