"""Materialised worldline view satisfying ``anchoring.WorldlineReader``.

``anchoring.py`` (300 LOC, 21 tests) defined ``WorldlineReader`` and shipped with
no implementation outside a test fake, so ``AnchoredEvaluator.check_anchor`` --
the gate that refuses to read past a superseded snapshot -- could never run in
production. This module supplies the missing implementation.

Why a materialised view rather than live queries: the ``WorldlineReader``
protocol is synchronous by contract, while the context store is async. Rather
than change a ratified protocol, the reader is built from revisions already
loaded by the owning layer (``context_engine.worldline``) and answers from
memory. That is also the honest shape for an anchor: an anchor pins a prefix,
so the prefix must be stable for as long as the anchor lives.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from anchoring import AnchorError


@dataclass(frozen=True, slots=True)
class RevisionRecord:
    """The minimum a reader needs from a revision, decoupled from its owner.

    ``snapshot_id`` is the revision's content address, so it already *is* a
    fingerprint of the material. ``position`` is the watermark: revisions are
    gapless from 1, so it doubles as the sequence number.
    """

    snapshot_id: str
    position: int
    caused_by_event_ids: tuple[str, ...] = ()


class WorldlineView:
    """Serves a context's revision chain through the ``WorldlineReader`` protocol."""

    __slots__ = ("_by_id", "_by_position", "_events_through", "_head")

    def __init__(self, records: Sequence[RevisionRecord]) -> None:
        ordered = sorted(records, key=lambda record: record.position)
        positions = [record.position for record in ordered]
        if len(set(positions)) != len(positions):
            raise AnchorError(
                "worldline_positions_duplicated",
                f"revision positions must be unique, got {positions}",
            )
        self._by_id: dict[str, RevisionRecord] = {}
        self._by_position: dict[int, RevisionRecord] = {}
        for record in ordered:
            if not record.snapshot_id:
                raise AnchorError(
                    "anchor_snapshot_missing", f"revision {record.position} has no snapshot id"
                )
            self._by_id[record.snapshot_id] = record
            self._by_position[record.position] = record
        self._head = ordered[-1].snapshot_id if ordered else ""
        # Cumulative event stream per snapshot position, so `events_through` costs
        # the size of the answer rather than the length of the chain.
        self._events_through: dict[int, tuple[str, ...]] = {}
        seen: set[str] = set()
        accumulated: list[str] = []
        for record in ordered:
            for event_id in record.caused_by_event_ids:
                if event_id not in seen:
                    seen.add(event_id)
                    accumulated.append(event_id)
            self._events_through[record.position] = tuple(accumulated)

    # -- WorldlineReader protocol -------------------------------------------

    def current_snapshot_id(self) -> str:
        return self._head

    def snapshot_fingerprint(self, snapshot_id: str) -> str:
        record = self._by_id.get(snapshot_id)
        if record is None:
            raise AnchorError("anchor_snapshot_missing", f"unknown snapshot {snapshot_id!r}")
        return record.snapshot_id

    def events_through(self, snapshot_id: str, watermark: int) -> tuple[Any, ...]:
        """Events up to and including ``watermark`` in the snapshot's stream.

        ``watermark`` is an *inclusive* position: ``watermark=2`` yields the first
        three events. This matches the ratified contract in ``test_anchoring.py``
        (``events[: watermark + 1]``), where an anchor can be pinned to a prefix
        and cannot silently consume events published after it was computed.

        The stream is cumulative over the revision chain, so a snapshot at
        position ``p`` can be pinned to any prefix of everything up to ``p``.

        A watermark past the end is refused rather than clamped. Returning a
        short list would let an evaluation look reproducible at a position that
        does not exist -- the exact silent-truncation failure this protocol
        exists to prevent. The one exception is a snapshot with no events at all,
        which is legal for a revision caused solely by decisions or operator
        actions; there the honest answer is the empty stream, not a refusal.
        """
        record = self._by_id.get(snapshot_id)
        if record is None:
            raise AnchorError("anchor_snapshot_missing", f"unknown snapshot {snapshot_id!r}")
        if watermark < 0:
            raise AnchorError("anchor_watermark_negative", f"watermark {watermark}")
        available = self._events_through.get(record.position, ())
        if not available:
            return ()
        if watermark >= len(available):
            raise AnchorError(
                "anchor_watermark_past_snapshot",
                f"watermark {watermark} exceeds the {len(available)} events of "
                f"snapshot at position {record.position}",
            )
        return available[: watermark + 1]

    # -- introspection -------------------------------------------------------

    @property
    def positions(self) -> tuple[int, ...]:
        return tuple(sorted(self._by_position))

    def position_of(self, snapshot_id: str) -> int:
        record = self._by_id.get(snapshot_id)
        if record is None:
            raise AnchorError("anchor_snapshot_missing", f"unknown snapshot {snapshot_id!r}")
        return record.position

    def __len__(self) -> int:
        return len(self._by_position)


def records_from_payloads(
    payloads: Sequence[Mapping[str, Any]],
) -> tuple[RevisionRecord, ...]:
    """Build records from raw revision payloads without importing their owner.

    The caller hands over ``{revision, revision_id, caused_by_event_ids}``-shaped
    mappings, so this module stays free of any dependency on the context store's
    domain classes while remaining tolerant of both tuple and list encoding.
    """
    records: list[RevisionRecord] = []
    for payload in payloads:
        events = payload.get("caused_by_event_ids") or ()
        records.append(
            RevisionRecord(
                snapshot_id=str(payload.get("revision_id") or ""),
                position=int(payload.get("revision") or 0),
                caused_by_event_ids=tuple(str(event) for event in events),
            )
        )
    return tuple(records)
