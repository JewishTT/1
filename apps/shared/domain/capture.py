"""Capture: the fetch event the evidence chain was missing (feature 016, T030/T033).

Contract is ``specs/016-relation-evidence-graph-fabric/spec.md`` D5 and FR-030 —
``Source -> Capture -> Observation -> Segment -> Mention -> Candidate -> Assertion
-> Relation -> Entity`` — with ``data-model.md`` section 8.

The lineage vocabulary has required a capture hop since the chain was declared, and
nothing in the platform modelled one. Acquisition emits observation dicts onto the
bus, every downstream layer carries a bare ``observation_id``, and the one link with
no value type of its own was filled in by a derived string
(``capture_id_for(source_id, observation_id)`` in
``apps/control-plane/semantic_path/execution.py``). That derivation is why replay,
provenance, source independence, ingestion-batch lineage, deduplication and
capture-level reproducibility were all broken at once: an id computed *from the
observation it explains* cannot be a fact that came *before* the observation, cannot
distinguish two fetches of one target, and cannot say which batch produced it. This
module is the first-class value those five properties need.

Id prefix is ``CAP-``. The prefix is taken deliberately and not invented: the
orchestrator already minted ``CAP-`` ids by hand, ``specs/.../contracts/api.md``
already documents ``CAP-`` capture nodes in its lineage payloads, and reusing it means
the derived strings this replaces stay in the same namespace rather than
double-prefixing into a second capture id space. It is distinct from every other
prefix on the platform (``OBS-``, ``CX-``, ``MN-``, ``TAR-``, ``TA-``, ``RC-``,
``RL-``, ``CNDR-``, ``CAND-``, ``EVT-``), so a capture id can never be confused with
the observation it will go on to explain.

``capture_id`` is a content address, exactly as
:class:`domain.evidence_context.EvidenceContext` derives and verifies
``context_id``: ``CAP-`` + ``digest128`` over the canonical capture record minus the
id itself, drawn from :mod:`domain.relation_identity` — the same primitive that
derives relation and frame ids, so an operator can recompute a capture id from the
record alone. Two independently recorded captures of the same fetch event therefore
address to the same id (I-11), and a supplied id is **verified, never trusted**: a
capture carrying an id its own content does not address to cannot be constructed, so
no caller can forge one and a tampered row cannot load.

What the address covers, and why each part is load-bearing for the properties above:

- ``tenant_id`` — the address is tenant-scoped, so two tenants fetching the same URL
  can never collide on one id (constitution IV). Every read is tenant-scoped, so a
  cross-tenant read must be refused (FR-048).
- ``source_id`` / ``source_family`` — which origin, and which independence family,
  the fetch came from. FR-034 counts two captures of one family as one independent
  source and keeps the publication count separate; that count is only computable if
  the family is a property of the capture rather than of the string that stood in
  for it.
- ``target_uri`` / ``locator`` — *what* was fetched, and the byte-exact position it
  came from (``warc-file@offset,length``). Either one alone locates the target; both
  together say *this* copy of it.
- ``content_digest`` / ``content_length`` / ``media_type`` — what came back.
  Required, not optional: a capture that cannot name its own bytes cannot be
  deduplicated, verified, or replayed honestly.
- ``fetched_at`` / ``time_basis`` — *when* the bytes were obtained, and **where
  that answer came from**. The pair is what makes a missing fetch time a stated
  fact rather than a hole: a crawl index honestly has no fetch time, so it
  records :attr:`CaptureTimeBasis.INDEX_OBSERVATION` with no ``fetched_at``, and
  a reader can tell that apart from a capture whose fetch time simply has not
  been written yet. Only :attr:`CaptureTimeBasis.FETCH` may carry a
  ``fetched_at``, so no stream can substitute the nearest timestamp it holds
  (FR-006, FR-007, FR-025, D-B).
- ``ingest_batch_id`` / ``ingest_attempt`` — which ingestion attempt produced the
  record. See :data:`UNBATCHED_INGEST_BATCH` for what happens when no batch concept
  exists yet.
- ``transport`` / ``recorded_by`` — how the bytes were obtained and which producer
  wrote the record. ``recorded_by`` is identity material for the same reason
  ``created_by`` is on ``RelationClaim``: a re-run under a different producer is a
  different record, not a silent overwrite.

The one field deliberately **absent** is any list of the observations the capture
produced. Identity flows capture -> observation by reference, through the lineage
graph, and folding a downstream result back into an upstream event's address would
make the fetch change identity the moment extraction ran.

Deduplication is therefore two honest questions with two answers, and the module
refuses to conflate them. *Is this the same fetch event?* is
:attr:`Capture.payload_key` — tenant, origin, target and content digest, with
``fetched_at``, batch and attempt excluded. *Is this the same event?* is
``capture_id``, and a re-ingest of the same event is the same capture. So a re-fetch
of one target at a new time that returns identical bytes is a **new capture of a
known payload**: a second publication, not a second payload, and the two counts stay
apart exactly as FR-034 and constitution IV require.

The conversion to a lineage hop is :meth:`Capture.to_hop`. It imports
:class:`~domain.evidence_lineage.EvidenceHop` and
:class:`~domain.evidence_lineage.HopKind` at module level, one-way, and
:mod:`domain.evidence_lineage` imports nothing from here — no Protocol and no
function-local import. The cycle the task anticipates does not arise, because
``EvidenceGraph.forward`` derives its step sequence from the *hop kinds registered
in the graph*, never from a ``Capture`` value: the lineage module has no reason to
know the type exists. A Protocol would have named a contract without a shared
definition and still needed a cast to build the concrete ``EvidenceHop``; a local
import would have hidden a cycle that is not there. The honest reading is that the
dependency arrow is one-way, and it is stated here so a future
``evidence_lineage`` import of ``Capture`` is recognised as the cycle it would
create.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol

from domain.evidence_lineage import EvidenceHop, HopKind
from domain.relation_identity import canonical_material, digest128

#: Prefix of the content address; the digest follows it, so an id is 36 characters.
CAPTURE_ID_PREFIX = "CAP-"

#: Stands in for "no ingestion batch exists for this record".
#:
#: The platform has no ingestion-batch concept to reference — no table, no id, no
#: producer that emits one — so this sentinel records a **declared absence** rather
#: than inventing a batch id the way the old derivation invented a capture id. It is
#: part of the address material, so a capture taken under no batch and the same
#: capture later taken under a real batch are different records, and
#: :attr:`Capture.is_batch_attributed` is the query that says which. Replace it with
#: a real batch reference once one exists; the field is already in the material and
#: nothing else has to move.
UNBATCHED_INGEST_BATCH = "unbatched"


class CaptureTimeBasis(StrEnum):
    """Where a capture's answer to "when did you fetch this?" came from (D-B).

    A ``fetched_at`` typed ``datetime | None`` cannot distinguish *we do not know
    when this was fetched* from *we have not written it yet*, and for a substrate
    whose whole purpose is telling those apart that is the one distinction a
    nullable column cannot make. The basis is the typed, closed-vocabulary answer,
    carried on the record rather than inferred from a null.

    The members are the dispositions a stream may honestly declare, not a ranking:

    - :attr:`FETCH` — the stream performed the retrieval and measured it. The only
      basis that may carry a ``fetched_at``.
    - :attr:`INDEX_OBSERVATION` — the stream read a publisher's index of
      retrievals that happened elsewhere, so its instant is when *the index
      entry* was written, not when anything was fetched. This is Common Crawl's
      CDX ``timestamp`` and it is a fact about the index, not about the document.
    - :attr:`PUBLICATION` — the stream read a public record whose instant is when
      the record entered the public record (a filing's acceptance datetime, a
      register's publication date). A world fact; still not a fetch time.
    - :attr:`DERIVED` — the stream's instant is computed rather than read: a
      release snapshot's interval, an instant derived from a day-granularity
      field. A convention, stated so a reader can discount it.
    - :attr:`ABSENT` — the stream expresses no time of its own. A stated
      emptiness, which is what a caller must choose rather than inherit.

    Because the vocabulary is closed, a stream cannot answer "unknown" with prose
    and a stream cannot invent a seventh disposition: the alternatives are all
    here, and :class:`Capture` refuses any pair outside the invariant
    ``fetched_at is None`` if and only if ``time_basis is not FETCH`` (FR-007,
    FR-025).
    """

    FETCH = "fetch"
    INDEX_OBSERVATION = "index_observation"
    PUBLICATION = "publication"
    DERIVED = "derived"
    ABSENT = "absent"


#: The only basis a capture may hold alongside a populated ``fetched_at``.
#:
#: Named so the substitution refusal in :meth:`Capture.__post_init__` reads as a
#: rule about the model rather than as a string comparison, and so a reader can
#: grep for the one place where the two are allowed to agree.
FETCH_TIME_BASIS = CaptureTimeBasis.FETCH



class CaptureContractError(ValueError):
    """A capture cannot be constructed, or is not the capture it claims to be.

    A ``ValueError`` carrying the stable snake_case ``code`` a validation layer
    reports, matching :class:`domain.evidence_context.ContextContractError` so one
    caller can switch on either.
    """

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


class HopLike(Protocol):
    """What tenant scoping reads off anything hop-shaped.

    Structural rather than the concrete type so a chain builder can pass a mixture of
    lineage hops and capture hops to :func:`assert_single_tenant` without this module
    claiming a type for the other one.
    """

    tenant_id: str


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
        raise CaptureContractError(code, f"a capture requires {field}: {why}")
    return text


def _time_basis(value: Any) -> CaptureTimeBasis:
    """Coerce a stored basis back to the enum, or refuse it by name.

    ``from_dict`` receives whatever a row holds, and a row can hold a string, a
    member, or something a future writer invented. Coercion is total for the
    members and refusing for everything else is the point: an unrecognised basis
    is an unstated answer to "when did you fetch this", which is the question
    :class:`CaptureTimeBasis` exists to make unanswerable silently.
    """
    if isinstance(value, CaptureTimeBasis):
        return value
    try:
        return CaptureTimeBasis(str(value))
    except ValueError as exc:
        raise CaptureContractError(
            "capture_time_basis_invalid",
            f"{value!r} is not a CaptureTimeBasis; a capture's time means one of "
            f"{[member.value for member in CaptureTimeBasis]}",
        ) from exc


@dataclass(frozen=True)
class Capture:
    """One fetch/ingest event, frozen and content-addressed.

    Field order is the record's own audit surface: who fetched what, from where,
    when, and under which ingestion attempt. Required fields are
    ``tenant_id``, ``source_id``, ``target_uri`` or ``locator`` and
    ``content_digest``; each is checked in :meth:`__post_init__` rather than
    defaulted, because a defaulted required field is a fabricated event. The
    fourth is ``fetched_at``, which is required *only* under
    :attr:`CaptureTimeBasis.FETCH` and is a stated absence under every other
    basis — see :class:`CaptureTimeBasis` and the invariant below. The derived
    ``capture_id`` is verified rather than trusted, and the address is
    tenant-scoped so one tenant's capture can never be addressed by another's.
    """

    capture_id: str = ""
    tenant_id: str = "default-tenant"
    source_id: str = ""
    source_family: str = ""
    target_uri: str = ""
    locator: str = ""
    content_digest: str = ""
    content_length: int | None = None
    media_type: str = ""
    fetched_at: datetime | None = None
    time_basis: CaptureTimeBasis = CaptureTimeBasis.FETCH
    transport: str = ""
    ingest_batch_id: str = UNBATCHED_INGEST_BATCH
    ingest_attempt: int = 1
    recorded_by: str = ""

    def __post_init__(self) -> None:
        """Fail closed on an incomplete event, then derive or verify the address."""
        tenant = _required(
            "capture_tenant_missing",
            "a tenant_id",
            self.tenant_id,
            "every read is tenant-scoped and a capture address is tenant-scoped (FR-048)",
        )
        source = _required(
            "capture_source_missing",
            "a source_id",
            self.source_id,
            "the chain starts at a source, and independence is resolved by origin",
        )
        target = str(self.target_uri or "").strip()
        locator = str(self.locator or "").strip()
        if not target and not locator:
            raise CaptureContractError(
                "capture_locator_missing",
                "a capture requires target_uri or locator: a fetch event that names "
                "neither what was fetched nor where it came from cannot be replayed",
            )
        digest = _required(
            "capture_content_digest_missing",
            "a content_digest",
            self.content_digest,
            "bytes that cannot be named cannot be deduplicated, verified or replayed",
        )
        basis = _time_basis(self.time_basis)
        fetched_at = self.fetched_at
        has_fetch = fetched_at is not None and _iso(fetched_at) is not None
        if basis is FETCH_TIME_BASIS and not has_fetch:
            raise CaptureContractError(
                "capture_fetch_time_missing",
                "a capture whose time_basis is FETCH requires fetched_at: this module "
                "reads no clock, and a defaulted fetch time would make replay "
                "non-deterministic (VII)",
            )
        if has_fetch and basis is not FETCH_TIME_BASIS:
            raise CaptureContractError(
                "capture_fetch_time_substituted",
                f"fetched_at is {fetched_at!r} on a capture whose time_basis is "
                f"{basis.value!r}; only a measured retrieval carries a fetch time, and "
                "promoting an index, publication or derived timestamp into one is the "
                "conflation FR-007 and FR-025 forbid",
            )
        if self.content_length is not None and self.content_length < 0:
            raise CaptureContractError(
                "capture_content_length_invalid",
                f"content_length cannot be negative, got {self.content_length}",
            )
        if self.ingest_attempt < 1:
            raise CaptureContractError(
                "capture_attempt_invalid",
                f"ingest_attempt is 1-based, got {self.ingest_attempt}",
            )
        batch = str(self.ingest_batch_id or "").strip() or UNBATCHED_INGEST_BATCH

        object.__setattr__(self, "tenant_id", tenant)
        object.__setattr__(self, "source_id", source)
        object.__setattr__(self, "target_uri", target)
        object.__setattr__(self, "locator", locator)
        object.__setattr__(self, "content_digest", digest)
        object.__setattr__(self, "time_basis", basis)
        object.__setattr__(self, "ingest_batch_id", batch)

        addressed = CAPTURE_ID_PREFIX + self.capture_fingerprint
        if not self.capture_id:
            object.__setattr__(self, "capture_id", addressed)
        elif self.capture_id != addressed:
            raise CaptureContractError(
                "capture_id_mismatch",
                f"capture carries {self.capture_id!r} but its own content addresses to "
                f"{addressed!r}; a content address is verified, never trusted",
            )

    @property
    def capture_fingerprint(self) -> str:
        """The 128-bit digest ``capture_id`` is built from (I-11, I-1).

        Persisted beside the id so a unique index on
        ``(tenant_id, capture_fingerprint)`` makes registration idempotent at the
        database, not only in :class:`InMemoryCaptureRegistry`.
        """
        return digest128(canonical_material(self._material()))

    @property
    def payload_key(self) -> str:
        """The address of *what came back*, independent of when and by which attempt.

        Tenant, origin, target and content digest only. ``fetched_at``,
        ``time_basis``, ``ingest_batch_id`` and ``ingest_attempt`` are excluded on
        purpose: two fetches of one target returning identical bytes are one payload
        and two publications, and deduplicating them is a *query over payload keys*,
        never a change to either capture's identity (FR-034, constitution IV). The
        basis is excluded for the same reason it is included in ``capture_id``: what
        a capture *is* depends on how its time was obtained, and what a payload *is*
        does not.
        """
        return digest128(
            canonical_material(
                {
                    "tenant_id": self.tenant_id,
                    "source_id": self.source_id,
                    "target_uri": self.target_uri,
                    "locator": self.locator,
                    "content_digest": self.content_digest,
                }
            )
        )

    @property
    def is_batch_attributed(self) -> bool:
        """Whether this capture names a real ingestion batch (see the sentinel)."""
        return self.ingest_batch_id != UNBATCHED_INGEST_BATCH

    @property
    def has_fetch_time(self) -> bool:
        """Whether a retrieval time is actually present, as opposed to declared absent.

        The query ``fetched_at is not None`` already answers this, so the property
        exists to make the *distinction* greppable: a reader that must not treat an
        absent fetch time as a fetch time has one name for the condition.
        """
        return self.fetched_at is not None and _iso(self.fetched_at) is not None

    @property
    def hop_label(self) -> str:
        """Default lineage label: the fetch time, or the target and the stated gap.

        A capture with no fetch time labels itself with why it has none, so a
        lineage walk that reaches one shows the absence instead of rendering a
        bare URL and letting the reader assume a retrieval happened.
        """
        fetched = _iso(self.fetched_at)
        if fetched:
            return fetched
        target = self.target_uri or self.locator
        return f"{target} [no fetch time: {self.time_basis.value}]"

    def same_payload(self, other: Capture) -> bool:
        """Whether two captures are two fetches of one identical payload."""
        return self.payload_key == other.payload_key

    def to_hop(
        self,
        *,
        tenant_id: str | None = None,
        label: str = "",
        relation_id: str = "",
    ) -> EvidenceHop:
        """The ``HopKind.CAPTURE`` lineage hop for this capture.

        The conversion lives here, importing lineage one-way, because it is this
        module's own value being projected into the chain and not lineage's business
        to know the type. ``tenant_id`` may be supplied to assert the tenant the hop
        is being minted into; a value other than the capture's own tenant raises
        ``capture_tenant_mismatch`` rather than minting a hop that would carry one
        tenant's id under another tenant's chain.
        """
        if tenant_id is not None and str(tenant_id) != self.tenant_id:
            raise CaptureContractError(
                "capture_tenant_mismatch",
                f"capture {self.capture_id} belongs to tenant {self.tenant_id!r} and "
                f"cannot be linked into tenant {str(tenant_id)!r}'s chain (FR-048)",
            )
        return EvidenceHop(
            kind=HopKind.CAPTURE,
            node_id=self.capture_id,
            label=label or self.hop_label,
            relation_id=relation_id,
            tenant_id=self.tenant_id,
        )

    def to_dict(self) -> dict[str, Any]:
        """The full capture record, plus its fingerprint (I-1, I-5)."""
        return {
            "capture_id": self.capture_id,
            **self._material(),
            "capture_fingerprint": self.capture_fingerprint,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Capture:
        """Rebuild a capture from its own record; missing keys take the defaults.

        The stored ``capture_id`` is passed through and therefore verified against the
        recomputed material, so a round-trip of a tampered row raises rather than
        returning a capture that lies about its content (I-1). ``time_basis`` is read
        back through :func:`_time_basis`, so a row whose basis is a string outside
        the enum raises ``capture_time_basis_invalid`` instead of being coerced into
        the nearest member.
        """
        data = dict(payload)
        data.pop("capture_fingerprint", None)
        length = data.get("content_length")
        return cls(
            capture_id=str(data.get("capture_id", "")),
            tenant_id=str(data.get("tenant_id", "default-tenant")),
            source_id=str(data.get("source_id", "")),
            source_family=str(data.get("source_family", "")),
            target_uri=str(data.get("target_uri", "")),
            locator=str(data.get("locator", "")),
            content_digest=str(data.get("content_digest", "")),
            content_length=None if length is None else int(length),
            media_type=str(data.get("media_type", "")),
            fetched_at=_moment(data.get("fetched_at")),
            time_basis=_time_basis(data.get("time_basis", CaptureTimeBasis.FETCH)),
            transport=str(data.get("transport", "")),
            ingest_batch_id=str(data.get("ingest_batch_id", UNBATCHED_INGEST_BATCH)),
            ingest_attempt=int(data.get("ingest_attempt", 1)),
            recorded_by=str(data.get("recorded_by", "")),
        )

    def _material(self) -> dict[str, Any]:
        """The serialised field set ``capture_id`` and the fingerprint address.

        ``time_basis`` is in this material and not only on the record because a
        capture whose time means two different things is a different fact: the
        same bytes read out of an index entry and the same bytes measured by our
        own retrieval are two events with two addresses, and collapsing them
        would put a fetch time and an index observation under one id.

        No wall clock is in this material. ``fetched_at`` belongs here because it
        is a *fact of the event* — a replay of the same retrieval has the same
        one, which is what makes a replay reproduce the same id (constitution
        VII) — and no field that records when the row was *written* ever is, so
        re-ingesting a record at a different moment yields the same address.
        """
        return {
            "tenant_id": self.tenant_id,
            "source_id": self.source_id,
            "source_family": self.source_family,
            "target_uri": self.target_uri,
            "locator": self.locator,
            "content_digest": self.content_digest,
            "content_length": self.content_length,
            "media_type": self.media_type,
            "fetched_at": _iso(self.fetched_at),
            "time_basis": self.time_basis.value,
            "transport": self.transport,
            "ingest_batch_id": self.ingest_batch_id,
            "ingest_attempt": self.ingest_attempt,
            "recorded_by": self.recorded_by,
        }


def assert_single_tenant(tenant_id: str, hops: Iterable[HopLike]) -> str:
    """Refuse a chain that mixes tenants, and return the tenant it belongs to.

    ``EvidenceGraph.add_hop`` records two node ids and a hop, and nothing in its
    signature names the tenant the *chain* belongs to, so cross-tenant linking cannot
    be refused at the graph — the hop would have to carry two tenants and it carries
    one. The guard therefore sits where the chain is assembled: a builder states the
    tenant it is building for, and this raises ``capture_tenant_mismatch`` naming the
    first hop that disagrees rather than leaving a cross-tenant chain to be discovered
    later as a wrong answer (FR-048).
    """
    chain_tenant = str(tenant_id or "").strip()
    for hop in hops:
        if str(hop.tenant_id) != chain_tenant:
            raise CaptureContractError(
                "capture_tenant_mismatch",
                f"hop {getattr(hop, 'node_id', '?')} carries tenant "
                f"{str(hop.tenant_id)!r} but the chain is being built for "
                f"{chain_tenant!r}; a cross-tenant chain is never assembled (FR-048)",
            )
    return chain_tenant


class InMemoryCaptureRegistry:
    """The reference capture store and the dedup oracle for :class:`Capture`.

    Registration is idempotent on ``capture_id`` (I-11): re-registering an equal
    capture returns the same id and stores nothing new, and re-registering a
    *different* capture under one id raises rather than overwriting, so a capture
    already referenced by observations can never change underneath them. The same
    discipline as the database unique index on
    ``(tenant_id, capture_fingerprint)``, made explicit in memory.

    ``payload_duplicates`` answers the other deduplication question — "have these
    bytes been fetched from this target before?" — and reports rather than merges.
    A repeated payload is a second publication of one payload, and collapsing it
    would destroy the publication count that FR-034 and constitution IV require to
    stay separate from the independent-source count.
    """

    def __init__(self, captures: Iterable[Capture] = ()) -> None:
        self._captures: dict[str, Capture] = {}
        for capture in captures:
            self.register(capture)

    def register(self, capture: Capture) -> str:
        """Store a capture and return its ``capture_id``; idempotent on content."""
        registered = self._captures.get(capture.capture_id)
        if registered is not None:
            if registered != capture:
                raise CaptureContractError(
                    "capture_id_conflict",
                    f"capture {capture.capture_id} is already registered with different "
                    f"content; captures are never overwritten",
                )
            return registered.capture_id
        self._captures[capture.capture_id] = capture
        return capture.capture_id

    def resolve(self, capture_id: str) -> Capture | None:
        """The registered capture, or ``None`` for an id this registry does not hold."""
        return self._captures.get(capture_id)

    def by_payload(self, payload_key: str) -> tuple[Capture, ...]:
        """Every registered capture sharing one payload key, in capture-id order."""
        return tuple(
            sorted(
                (
                    capture
                    for capture in self._captures.values()
                    if capture.payload_key == payload_key
                ),
                key=lambda capture: capture.capture_id,
            )
        )

    def payload_duplicates(self) -> tuple[tuple[Capture, ...], ...]:
        """Every payload fetched more than once, as groups ordered by payload key.

        Reported, never merged: each member is a real fetch event with its own
        ``fetched_at`` and its own observations, and the pair of counts they feed —
        publication count and independent-source count — is only honest while they
        stay separate.
        """
        buckets: dict[str, list[Capture]] = {}
        for capture in self._captures.values():
            buckets.setdefault(capture.payload_key, []).append(capture)
        return tuple(
            tuple(sorted(group, key=lambda capture: capture.capture_id))
            for _, group in sorted(buckets.items())
            if len(group) > 1
        )

    def __len__(self) -> int:
        return len(self._captures)

    def __contains__(self, capture_id: object) -> bool:
        return capture_id in self._captures


__all__ = [
    "CAPTURE_ID_PREFIX",
    "FETCH_TIME_BASIS",
    "UNBATCHED_INGEST_BATCH",
    "Capture",
    "CaptureContractError",
    "CaptureTimeBasis",
    "HopLike",
    "InMemoryCaptureRegistry",
    "assert_single_tenant",
]
