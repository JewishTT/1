"""P4: turn a record's deferred address into a real ``MN-…`` — through the mention seam.

Feature 021 brief §25 and §26; spec FR-016, FR-018, FR-019; ``ARBITRATION`` §8;
constitution IV (fail-closed) and VI (determinism, Domain Invariant 12).

**This is the layer that makes the records mentionable, and it is one call wide.**
:mod:`parsers.payload.records` mints *deferred* addresses — a position and a surface, content
addressed, naming nothing — because a producer below mention extraction must not mint an
identity (brief §25, FR-019). :class:`domain.mention_occurrence_index.MentionOccurrenceIndex`
is the one place ``MN-`` ids are written, and it needs three keys the payload does not carry:
**which capture**, **which segment**, **which instrument**. Those are somebody else's decisions
— a fetch, a document region, a reading — so this module takes them as required arguments and
never defaults one. A default here would be a silent substitution of one retrieval, document or
instrument for another, which is the collision the capture key exists to prevent.

**Nothing here resolves anything.** :func:`bind_records` registers the occurrences the parser
read and hands back the mention ids those occurrences address. It does not decide that two
mentions are the same thing, does not write a ``RES-`` literal, and cannot: it holds no graph
and imports none. Two records of ``"Acme"`` at two positions are two occurrences and two
mention ids, which is the correct outcome and the reason FR-034's independence count still
works.

**Fail-closed, and the refusals are three different bugs.** :func:`bind_records` returns a
:class:`BoundPayload` in which every record appears exactly once: the addressable ones become
:class:`BoundField` entries carrying their ``MN-``, and the unaddressable ones appear as
:class:`PayloadRefusal` entries carrying the code from
:data:`~parsers.payload.records.ADDRESS_REFUSAL_CODES`. **A record is never dropped** — the
whole of P4's pluggability claim is that a record with no address is *counted as unaddressed
with its reason*, and
:meth:`~parsers.payload.records.ObservedField.require_address` is the door a caller goes
through when it needs the refusal as an exception. The three failure shapes get three codes,
because they are three operator bugs:

``record_address_mint_refused``
    the index would not register this occurrence. Almost always a surface the shared
    normalisation reduces to nothing (a value of ``"..."``, whose punctuation is all stripped
    edge material) — a real record with a real value that has no nameable surface.
``mention_occurrence_unresolved``
    the address is well formed and the index holds no occurrence at that position. In practice
    a caller bound a payload's records against an index built from something else.
``mention_capture_is_not_a_mention`` / ``mention_address_unreadable``
    carried through verbatim from :class:`~domain.mention_occurrence_index.MentionBindingError`
    so a caller can switch on the index's own codes rather than on this module's translation of
    them.

**Determinism.** :func:`bind_records` iterates records in document order, the index sorts its
own keys, and the mint is a digest over the five-key tuple — so two processes handed the same
payload and the same scope produce the same mention ids in the same order (constitution VI,
Domain Invariant 12). Nothing here reads a clock or a random source.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from domain.mention_occurrence_index import (
    MentionBindingError,
    MentionOccurrence,
    MentionOccurrenceIndex,
)
from domain.relation_participant import ParticipantEndKind

from parsers.payload.records import ObservedField, ParsedPayload, PayloadRefusal

#: The ``kind`` every occurrence registered from a payload record carries.
#:
#: **A constant, and the reason is that ``kind`` is a checked field.**
#: :meth:`MentionOccurrenceIndex.bind` *refuses* a second kind at the same five keys with
#: ``mention_kind_disagreement``. A payload record's kind is not in dispute — the record already
#: carries :attr:`~parsers.payload.records.ObservedField.value_type`, which is a fact about the
#: bytes, and carrying it again in the index's ``kind`` would let one span be registered as a
#: string and a number by two runs of the same parser and have the index refuse. The index
#: holds occurrences; what a record *is* is said by the record.
PAYLOAD_OCCURRENCE_KIND = "payload-occurrence"

#: The three codes this module raises or records, beyond the index's own.
BINDING_REFUSAL_CODES: tuple[str, ...] = (
    "record_address_mint_refused",
    "record_address_absent",
)


@dataclass(frozen=True, slots=True)
class BoundField:
    """One record, and the mention its occurrence addresses.

    ``field`` / ``value`` / ``value_type`` restate the record so a bound table reads without a
    join back to the parse, ``address`` is the deferred address that was resolved, and
    ``mention_id`` is what it resolved to. :attr:`~parsers.payload.records.ObservedField.span`
    is carried as ``byte_span`` for the same reason.

    ``end_kind`` is :attr:`domain.relation_participant.ParticipantEndKind` and is ``OCCURRENCE``
    for every entry: these are occurrences, not retrievals. It is on the record so a consumer
    assembling participants from a bound table has the same declared end the producer declared,
    rather than inferring one from the shape of the id.
    """

    field: str
    value: str
    value_type: str
    byte_span: tuple[int, int] | None
    address: str
    mention_id: str
    end_kind: ParticipantEndKind = ParticipantEndKind.OCCURRENCE

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "value": self.value,
            "value_type": self.value_type,
            "byte_span": list(self.byte_span) if self.byte_span is not None else None,
            "address": self.address,
            "mention_id": self.mention_id,
            "end_kind": str(self.end_kind),
        }


@dataclass(frozen=True, slots=True)
class BoundPayload:
    """The whole binding: what resolved, and what did not, in document order.

    ``bound`` and ``refusals`` partition the payload's records — every record is in exactly one,
    which is the property that makes "no record is dropped" checkable rather than asserted: a
    caller can count ``len(bound) + len(refusals)`` against ``len(payload.records)``.
    """

    capture_ref: str
    segment_ref: str
    extractor_ref: str
    bound: tuple[BoundField, ...] = ()
    refusals: tuple[PayloadRefusal, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "bound", tuple(self.bound))
        object.__setattr__(self, "refusals", tuple(self.refusals))

    @property
    def mention_ids(self) -> tuple[str, ...]:
        """Every resolved mention id, in document order — the join key downstream wants."""
        return tuple(entry.mention_id for entry in self.bound)

    def to_dict(self) -> dict[str, Any]:
        return {
            "capture_ref": self.capture_ref,
            "segment_ref": self.segment_ref,
            "extractor_ref": self.extractor_ref,
            "bound": [entry.to_dict() for entry in self.bound],
            "refusals": [refusal.to_dict() for refusal in self.refusals],
        }


def occurrence_index(
    records: tuple[ObservedField, ...],
    *,
    capture_ref: str,
    segment_ref: str,
    extractor_ref: str,
) -> MentionOccurrenceIndex:
    """An index holding exactly the occurrences these records read.

    The index is **built from the records and scoped to one reading**, which is the three-key
    scope FR-018 asks for: the same surface at the same offsets read by a different instrument
    is a different mention, and building the index here rather than reusing somebody else's is
    what guarantees the extractor key on every id is the one that actually read these bytes.

    Unaddressable records are skipped here (they have no span and no surface to register) and
    accounted for by :func:`bind_records`; nothing is registered that the payload did not state.

    **Strict, where :func:`bind_records` is per-record.** This is the front door: an index is
    built or it is not, and a construction the index refuses is a refusal with its own code
    (``mention_occurrence_surface_required`` for a value that the shared normalisation reduces to
    nothing, for instance). :func:`bind_records` deliberately does *not* use this: there, one
    unbindable value must not cost a payload the rest of its mentions, so it binds occurrence by
    occurrence and records each refusal where it happened.
    """
    occurrences = [
        MentionOccurrence(
            kind=PAYLOAD_OCCURRENCE_KIND,
            surface=record.value,
            start=record.byte_span[0],
            end=record.byte_span[1],
        )
        for record in records
        if record.addressable and record.byte_span is not None
    ]
    return MentionOccurrenceIndex(
        capture_ref=capture_ref,
        segment_ref=segment_ref,
        extractor_ref=extractor_ref,
        occurrences=occurrences,
    )


def bind_records(
    payload: ParsedPayload,
    *,
    capture_ref: str,
    segment_ref: str,
    extractor_ref: str,
) -> BoundPayload:
    """Resolve every addressable record of ``payload`` through a mention index built from it.

    **Every record comes back accounted for, and a record that cannot be bound comes back as a
    refusal rather than as an exception.** The caller gets a table and a count, not a stack trace
    for a payload with one punctuation-only value in it — and the count is the point: an
    unaddressable value that vanished would be indistinguishable from a payload that did not
    have one. ``len(result.bound) + len(result.refusals) == len(payload.records)`` always holds,
    which is the mechanical form of "no record is dropped".

    Occurrences are bound **one at a time** rather than through :func:`occurrence_index`, so a
    single value the index refuses costs that value its mention id and nothing else. Binding in
    bulk would make one bad record cost the whole payload its mention table, which is the
    "silent drop" this layer exists to prevent — only silent about which record was lost.

    The one thing that *does* raise is a blank ``capture_ref``, ``segment_ref`` or
    ``extractor_ref``: those three are the index's scope, the index refuses them with its own
    ``mention_index_scope_required``, and there is nothing honest to bind against. All three are
    required keyword arguments and none is defaulted.
    """
    index = MentionOccurrenceIndex(
        capture_ref=capture_ref,
        segment_ref=segment_ref,
        extractor_ref=extractor_ref,
    )
    bound: list[BoundField] = []
    refusals: list[PayloadRefusal] = []
    for record in payload.records:
        if not record.addressable:
            refusals.append(
                PayloadRefusal(
                    record.address_refusal or "record_address_absent",
                    f"{record.field} ({record.value_type}) has no deferred occurrence address: "
                    f"{record.address_refusal or 'the record carries no refusal code'}. The "
                    "record is kept and counted; it is not bound to whatever was nearest",
                )
            )
            continue
        span = record.byte_span
        address = record.require_address()
        try:
            index.bind(
                MentionOccurrence(
                    kind=PAYLOAD_OCCURRENCE_KIND,
                    surface=record.value,
                    start=span[0],
                    end=span[1],
                )
            )
            resolved = index.require_occurrence(address)
        except MentionBindingError as exc:
            refusals.append(
                PayloadRefusal(
                    "record_address_mint_refused",
                    f"{record.field} ({record.value_type}) addresses {address!r} and the index "
                    f"refused it: [{exc.code}] {exc.message}",
                    span[0],
                )
            )
            continue
        bound.append(
            BoundField(
                field=record.field,
                value=record.value,
                value_type=str(record.value_type),
                byte_span=record.byte_span,
                address=record.address,
                mention_id=resolved.mention_id,
            )
        )
    return BoundPayload(
        capture_ref=capture_ref,
        segment_ref=segment_ref,
        extractor_ref=extractor_ref,
        bound=tuple(bound),
        refusals=tuple(refusals),
    )


__all__ = [
    "BINDING_REFUSAL_CODES",
    "PAYLOAD_OCCURRENCE_KIND",
    "BoundField",
    "BoundPayload",
    "bind_records",
    "occurrence_index",
]
