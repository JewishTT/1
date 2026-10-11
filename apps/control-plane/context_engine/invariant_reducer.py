"""Incremental growth of a ``GraphInvariant`` — one revision per real change.

``domain.graph_invariant.from_entity_stream`` is a *rebuild*: hand it a whole
life-stream and it returns the projection for that stream. It is deterministic
and it is correct, but it has no memory. Every call re-derives everything, the
caller has to diff two projections by hand to decide whether anything actually
happened, and nothing records that revision 3 replaced revision 2. Its
``with_links`` helper is the same story in miniature: it changes the digest and
leaves ``identity.revision`` where it was, so the link is a new body wearing the
old revision's name.

``InvariantReducer`` closes that gap. It holds the accumulated stream, folds a
batch into it, and mints a revision **only when the digest actually moved**:

- a batch that contributes no new event id is a no-op — same revision, same
  digest, so redelivering a batch (at-least-once is the normal delivery
  semantics) cannot inflate the chain;
- a batch that does move the digest mints the next revision and links it to its
  predecessor through ``RevisionRecord.supersedes``, in the single-string,
  empty-means-genesis form ``RelationClaim.supersedes`` already uses
  (``apps/shared/domain/relation_claim.py:215``);
- ``restore`` rebuilds from a persisted ``(stream, history)`` pair and *verifies*
  that the stream still reproduces the recorded head, so a corrupt store is
  reported instead of being smoothed over.

The projection is never computed by hand. Every revision is ``from_entity_stream``
over the entire accumulated stream with ``revision`` as the only varying
argument. Incremental *growth* is the goal: the reducer decides WHEN a revision
exists and LINKS revisions together, and deliberately does not add a second,
drift-prone way to compute the body. So ``invariant.integrity_digest`` is
byte-identical to ``from_entity_stream(records, revision=n)`` over the same
input, and a post-restart rebuild is indistinguishable from the incremental path
that produced it.

Layer position: ``control-plane`` imports ``shared`` (``domain.graph_invariant``)
and, for the bridge into the anchoring path, ``science`` (``context.worldline``).
Both are declared dependencies of ``cognitive-control-plane``, and ``shared`` is
downward in ``LAYER_ORDER`` (``shared -> ... -> control-plane -> science``).
Hermetic by construction — no clock, no network, no database, no randomness.
Ordering comes from the stream's own ``sequence``/``ts``, and every id the module
mints is a content hash.

Stream hashes are *asked of the builder* rather than recomputed: a one-entry
projection is the authority on what a record's hash is, so the reducer cannot
drift from the ``evt-<record_hash>`` convention that ``from_entity_stream``
applies internally.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from context.worldline import RevisionRecord as WorldlineRevision
from domain.graph_invariant import GraphInvariant, TypedLink, from_entity_stream

__all__ = [
    "InvariantReduceError",
    "InvariantReducer",
    "ReduceResult",
    "RevisionRecord",
]

#: Event-id convention, verbatim from ``graph_invariant`` (``evt-<record_hash>``).
EVENT_ID_PREFIX = "evt-"


def _event_id(record_hash: str) -> str:
    return f"{EVENT_ID_PREFIX}{record_hash}"


class InvariantReduceError(ValueError):
    """A batch could not be folded into an invariant's revision chain.

    Carries the repo's ``(code, message)`` shape — the same convention as
    ``relation_claim.RelationContractError`` and ``anchoring.AnchorError`` — so
    callers branch on a stable token instead of parsing text.
    """

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


@dataclass(frozen=True, slots=True)
class RevisionRecord:
    """One link of an invariant's revision chain.

    ``snapshot_id`` is the revision's content address (``GI-<digest>``): the
    address *is* the fingerprint of the body, so a reader verifies the chain
    without trusting a mutable label. ``revision`` is the gapless watermark,
    starting at 1.

    ``supersedes`` names the ``snapshot_id`` of the revision this one replaced
    and is ``""`` for the genesis revision — the declared-absence form
    ``RelationClaim.supersedes`` uses, where "" means "nothing superseded this"
    rather than "unknown". ``caused_by_event_ids`` are the ``evt-<record_hash>``
    ids of the records *this* revision absorbed, which is what makes a replay
    auditable: every event in the stream belongs to exactly one revision.
    """

    entity_id: str
    revision: int
    snapshot_id: str
    digest: str
    supersedes: str = ""
    stream_head: str = ""
    caused_by_event_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.revision < 1:
            raise InvariantReduceError(
                "invalid_revision", f"revision must be >= 1, got {self.revision}"
            )
        if self.supersedes and self.supersedes == self.snapshot_id:
            raise InvariantReduceError(
                "self_supersession", f"revision {self.revision} supersedes itself"
            )

    @property
    def position(self) -> int:
        """Alias for :attr:`revision`, under the name ``WorldlineReader`` uses."""
        return self.revision

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "revision": self.revision,
            "snapshot_id": self.snapshot_id,
            "digest": self.digest,
            "supersedes": self.supersedes,
            "stream_head": self.stream_head,
            "caused_by_event_ids": list(self.caused_by_event_ids),
        }

    def to_worldline_record(self) -> WorldlineRevision:
        """Project onto ``context.worldline.RevisionRecord``.

        The invariant chain is a revision chain in the anchor's sense, so this is
        what lets ``context_engine.worldline.load_worldline`` feed it to a
        ``WorldlineView`` unchanged. ``supersedes`` is the chain edge and does
        not survive the projection — ``position`` ordering already encodes it.
        """
        return WorldlineRevision(
            snapshot_id=self.snapshot_id,
            position=self.revision,
            caused_by_event_ids=self.caused_by_event_ids,
        )


@dataclass(frozen=True, slots=True)
class ReduceResult:
    """Outcome of folding one batch into the chain.

    ``changed`` is False for a batch that added no new event id, and then
    ``invariant``/``record`` are the *existing* head, byte-identical — a
    redelivered batch is indistinguishable from a clean no-op. Only a True
    result appends to ``history()``.
    """

    invariant: GraphInvariant
    record: RevisionRecord
    changed: bool
    accepted_event_ids: tuple[str, ...] = ()


class InvariantReducer:
    """Folds batches of one entity's life-stream into a growing invariant.

    Construct empty and feed batches, or come back from a restart with
    :meth:`restore`. All configuration (``window``, ``tenant_id``, ``type_label``,
    ``community``, ``links``) is constructor-level because it shapes the
    projection body itself: changing it mid-stream would make the digest move
    for a reason no event explains.
    """

    __slots__ = (
        "_community",
        "_entries",
        "_history",
        "_index",
        "_invariant",
        "_links",
        "_tenant_id",
        "_type_label",
        "_window",
    )

    def __init__(
        self,
        *,
        window: timedelta = timedelta(days=7),
        tenant_id: str = "default-tenant",
        type_label: str = "",
        community: str = "",
        links: tuple[TypedLink, ...] = (),
    ) -> None:
        if not window or window <= timedelta(0):
            raise InvariantReduceError("invalid_window", f"window must be positive, got {window!r}")
        if not tenant_id:
            raise InvariantReduceError("missing_tenant", "reducer requires tenant_id (I-12)")
        self._window = window
        self._tenant_id = tenant_id
        self._type_label = type_label
        self._community = community
        self._links = tuple(links)
        self._entries: list[Any] = []
        self._index: dict[str, Any] = {}
        self._invariant: GraphInvariant | None = None
        self._history: list[RevisionRecord] = []

    # -- state ------------------------------------------------------------

    @property
    def invariant(self) -> GraphInvariant:
        """The current projection. Raises while the chain is still empty.

        There is no partial answer to give: a revision with no events behind it
        would be an identity with no source, which ``from_entity_stream``
        refuses for the same reason (I-3).
        """
        if self._invariant is None:
            raise InvariantReduceError(
                "no_revision", "reducer holds no stream yet; fold at least one batch"
            )
        return self._invariant

    @property
    def revision(self) -> int:
        """Head revision, or 0 while the chain is empty (gapless watermarks start at 1)."""
        return self._invariant.identity.revision if self._invariant is not None else 0

    @property
    def entity_id(self) -> str:
        return self.invariant.identity.entity_id

    @property
    def head(self) -> RevisionRecord | None:
        """The latest link in the chain, or None while the chain is empty."""
        return self._history[-1] if self._history else None

    @property
    def stream(self) -> tuple[Any, ...]:
        """The accumulated stream in accepted order, deduplicated by event id."""
        return tuple(self._entries)

    def history(self) -> tuple[RevisionRecord, ...]:
        """The revision chain, genesis first."""
        return tuple(self._history)

    def snapshot(self) -> tuple[tuple[Any, ...], tuple[RevisionRecord, ...]]:
        """The persistence payload :meth:`restore` consumes."""
        return self.stream, self.history()

    # -- folding ----------------------------------------------------------

    def reduce(self, records: Iterable[Any]) -> ReduceResult:
        """Fold one batch of stream entries into the chain.

        Entries may be ``domain.dynamics.StreamRecord`` instances, entity-stream
        row mappings, or anything else exposing ``ts``/``sequence``/``payload`` —
        whatever ``from_entity_stream`` accepts, in any order. New events are
        identified by their ``evt-`` hash, so the same event redelivered inside
        this batch or a later one is folded exactly once (I-11).
        """
        accepted: list[str] = []
        for entry in records:
            stream_hash = self._probe_hash(entry)
            if stream_hash in self._index:
                continue  # already folded: redelivery is not a new event (I-11)
            self._index[stream_hash] = entry
            self._entries.append(entry)
            accepted.append(stream_hash)

        if not accepted:
            if self._invariant is None:
                raise InvariantReduceError(
                    "empty_stream", "cannot mint an identity from an empty batch (I-3)"
                )
            return ReduceResult(invariant=self._invariant, record=self._history[-1], changed=False)

        previous = self._invariant
        next_revision = (previous.identity.revision if previous is not None else 0) + 1
        invariant = self._build(self._entries, next_revision)

        digest = invariant.integrity_digest
        if previous is not None and digest == previous.integrity_digest:
            # Unreachable through the public path — a new event id always lands in
            # ``provenance.source_hashes``, which is inside the digest. Asserted
            # regardless, because "the revision moved but the body did not" is
            # precisely the defect this class exists to prevent, and it should
            # fail loudly rather than mint a hollow link in the chain.
            raise InvariantReduceError(
                "unchanged_digest", f"accepted {len(accepted)} event(s) but digest did not move"
            )

        record = RevisionRecord(
            entity_id=invariant.identity.entity_id,
            revision=next_revision,
            snapshot_id=invariant.content_id,
            digest=digest,
            supersedes=previous.content_id if previous is not None else "",
            stream_head=invariant.provenance.stream_head,
            caused_by_event_ids=self._caused_by(invariant, accepted),
        )
        self._invariant = invariant
        self._history.append(record)
        return ReduceResult(
            invariant=invariant,
            record=record,
            changed=True,
            accepted_event_ids=record.caused_by_event_ids,
        )

    @classmethod
    def restore(
        cls,
        stream: Iterable[Any],
        *,
        history: Iterable[RevisionRecord] = (),
        window: timedelta = timedelta(days=7),
        tenant_id: str = "default-tenant",
        type_label: str = "",
        community: str = "",
        links: tuple[TypedLink, ...] = (),
    ) -> InvariantReducer:
        """Rebuild a reducer from a persisted ``(stream, history)`` pair.

        The stream is replayed through the same accumulate-and-build path
        :meth:`reduce` uses, so a restart lands on exactly the projection the
        incremental path produced — the next folded batch continues at
        ``len(history) + 1``. The recorded head is then checked against the
        rebuilt one: a stream and a history that disagree mean a corrupt store,
        and that is reported rather than papered over (I-12).
        """
        records = tuple(history)
        positions = [record.revision for record in records]
        if positions != list(range(1, len(records) + 1)):
            raise InvariantReduceError(
                "history_not_gapless", f"revision chain must be gapless from 1, got {positions}"
            )

        reducer = cls(
            window=window,
            tenant_id=tenant_id,
            type_label=type_label,
            community=community,
            links=links,
        )
        entries = tuple(stream)
        if not entries:
            raise InvariantReduceError(
                "empty_stream", "cannot restore a reducer from an empty stream (I-3)"
            )
        for entry in entries:
            stream_hash = reducer._probe_hash(entry)
            if stream_hash not in reducer._index:
                reducer._index[stream_hash] = entry
                reducer._entries.append(entry)

        position = records[-1].revision if records else 1
        invariant = reducer._build(reducer._entries, position)
        head = records[-1] if records else None
        if head is not None and head.snapshot_id != invariant.content_id:
            raise InvariantReduceError(
                "head_mismatch",
                f"stream rebuilds to {invariant.content_id}, history head is {head.snapshot_id}",
            )
        reducer._invariant = invariant
        reducer._history = list(records)
        return reducer

    # -- internals -------------------------------------------------------

    def _build(self, entries: Iterable[Any], revision: int) -> GraphInvariant:
        """Project the accumulated stream at ``revision`` via the shared builder."""
        return from_entity_stream(
            tuple(entries),
            window=self._window,
            tenant_id=self._tenant_id,
            type_label=self._type_label,
            revision=revision,
            community=self._community,
            links=self._links,
        )

    def _probe_hash(self, entry: Any) -> str:
        """The event id hash ``from_entity_stream`` assigns to a single entry.

        Asked of the builder instead of recomputed here: the hash convention is
        private to ``domain.graph_invariant``, and a local copy of it is a copy
        that can drift. A one-entry projection is the cheapest way to let the
        builder answer, and its answer does not depend on what else is in the
        stream.
        """
        return self._build((entry,), 1).provenance.source_hashes[0]

    @staticmethod
    def _caused_by(invariant: GraphInvariant, accepted: list[str]) -> tuple[str, ...]:
        """The ids of the events this revision absorbed, in *stream* order.

        Selected from the projection's own ``source_hashes`` rather than from the
        arrival order, so the chain reads the same whether a batch arrived as
        ``(1, 2, 3)`` or as ``(3, 1, 2)``. The set is fixed either way; only the
        order was arrival-dependent.
        """
        fresh = set(accepted)
        return tuple(
            _event_id(stream_hash)
            for stream_hash in invariant.provenance.source_hashes
            if stream_hash in fresh
        )
