"""Making a sweep survive the process, and survive being asked about again afterwards.

The enrichment service produces everything a dossier needs and then the process exits. Until
something wrote that down, the sweep existed for as long as the request did: the reader had
nothing to read and the only honest thing the platform could say was "we looked at this once,
in a process that no longer exists". This module is the two halves of closing that:

* :class:`PostgresEnrichmentSink` -- writes a completed sweep into ``entity_stream``.
* :class:`DossierReader` -- reads a subject's life-stream back and assembles a dossier from it.

Why the life-stream and not ``entity_facts``
--------------------------------------------
A dossier fact is only worth showing if it names the source that produced it, and
``entity_facts`` has no column for a source. Writing a fact there would mean either a
migration or a value with the source welded into its text -- both of which push the
provenance decision downstream, where nobody is checking. ``entity_stream.payload`` is JSONB
and already carries ``observation_id``, so the source travels with the value in the row that
is its own evidence. One table, one source of truth, provenance that cannot be dropped.

Sequence numbers are assigned from the stream's own current maximum inside the transaction,
not by the caller. The caller numbers within a sweep, which is right for a run and wrong for
a second run against the same subject: it would restart at 1, collide on the composite key,
and silently drop every observation the second sweep made. Re-observing a subject is a new
event and belongs in the stream, so it is appended rather than deduplicated away -- exact
replays are collapsed at read time, where the invariant already dedupes by stream hash.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from datetime import timedelta
from typing import Any

from context.dossier import Dossier, build_dossier
from context.enrichment import (
    AttributeState,
    CapabilityOffer,
    EntityProfile,
    merge_offer,
    plan_enrichment,
)
from domain.graph_invariant import GraphInvariant, from_entity_stream
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

ConnectionFactory = Callable[[], AsyncConnection]


class PostgresEnrichmentSink:
    """Appends a completed sweep to ``entity_stream``.

    Takes a connection factory rather than a connection so it composes with the API's
    per-request lifetime, matching ``PostgresContextStore``. Each report is one transaction:
    a sweep that is half-written would leave a life-stream with a hole in the middle, and a
    hole in the middle of a timeline reads as "nothing happened then" rather than "we lost
    it".
    """

    def __init__(
        self,
        connection_factory: ConnectionFactory,
        *,
        tenant_id: str,
        extraction_version: str = "enrichment.v1",
    ) -> None:
        self._connections = connection_factory
        self.tenant_id = tenant_id
        self.extraction_version = extraction_version

    async def __call__(self, report: Any) -> None:
        entries = tuple(getattr(report, "stream", ()) or ())
        if not entries:
            return
        entity_id = report.subject.entity_ref
        facts = _facts_of(report)
        subject = str(getattr(report, "query", "") or entity_id)
        kind = str(getattr(getattr(report, "subject", None), "type_label", "") or "")
        async with self._connections() as conn, conn.begin():
            start = await self._next_sequence(conn, entity_id)
            for offset, entry in enumerate(entries):
                await conn.execute(
                    text(
                        """
                            INSERT INTO entity_stream (
                                tenant_id, entity_id, sequence, record_hash, kind, ts,
                                payload, valid_from, observation_id, dataset_id,
                                extraction_version
                            ) VALUES (
                                :tenant, :entity, :sequence, :record_hash, :kind, :ts,
                                CAST(:payload AS JSONB), :valid_from, :observation_id,
                                :dataset_id, :extraction_version
                            )
                            ON CONFLICT DO NOTHING
                            """
                    ),
                    {
                        "tenant": self.tenant_id,
                        "entity": entity_id,
                        "sequence": start + offset,
                        "record_hash": str(entry["record_hash"])[:64],
                        "kind": str(entry["kind"])[:32],
                        "ts": entry["ts"],
                        "payload": json.dumps(
                                _payload_of(entry, facts, subject, kind), default=str
                            ),
                        "valid_from": entry["ts"],
                        "observation_id": str(entry.get("observation_id", ""))[:64],
                        "dataset_id": f"enrichment:{entity_id}"[:64],
                        "extraction_version": self.extraction_version,
                    },
                )

    async def _next_sequence(self, conn: AsyncConnection, entity_id: str) -> int:
        result = await conn.execute(
            text(
                "SELECT COALESCE(MAX(sequence), 0) FROM entity_stream "
                "WHERE tenant_id = :tenant AND entity_id = :entity"
            ),
            {"tenant": self.tenant_id, "entity": entity_id},
        )
        return int(result.scalar() or 0) + 1


class DossierReader:
    """Rebuilds a dossier for one subject from its persisted life-stream.

    The reader re-derives rather than re-reads: the invariant is folded again from the rows,
    which is the point of an append-only stream (I-11/I-12). A dossier therefore cannot
    disagree with the events that produced it, and no second copy of the state exists to
    drift.

    ``offers`` are the capabilities to score against. Supplying them is what turns a list of
    observations into a coverage statement; omitting them still yields a dossier, one that
    says ``plan_known=False`` -- materially weaker, and marked as such rather than presented
    as complete.
    """

    def __init__(
        self,
        connection_factory: ConnectionFactory,
        *,
        tenant_id: str,
        window: timedelta = timedelta(days=7),
    ) -> None:
        self._connections = connection_factory
        self.tenant_id = tenant_id
        self.window = window

    async def read(
        self,
        entity_id: str,
        *,
        kind: str = "",
        offers: Sequence[CapabilityOffer] = (),
        invariant: GraphInvariant | None = None,
    ) -> Dossier | None:
        async with self._connections() as conn:
            rows = (
                await conn.execute(
                    text(
                        """
                        SELECT entity_id, sequence, record_hash, kind, ts, payload,
                               observation_id
                        FROM entity_stream
                        WHERE tenant_id = :tenant AND entity_id = :entity
                        ORDER BY sequence, ts, record_hash
                        """
                    ),
                    {"tenant": self.tenant_id, "entity": entity_id},
                )
            ).mappings().all()

        if not rows:
            return None
        entries = [_entry_of(row) for row in rows]
        folded = invariant or from_entity_stream(
            entries,
            window=self.window,
            tenant_id=self.tenant_id,
            type_label=kind,
        )
        subject, stored_kind = _subject_of(rows)
        profile = _profile_of(entity_id, kind or stored_kind or folded.identity.type_label, rows)
        resolved = tuple(offers) or _offers_for(subject, kind or stored_kind)
        plan = (
            plan_enrichment(
                profile,
                resolved,
                available={o.source_id: not o.key_env and not o.binary for o in resolved},
            )
            if resolved
            else None
        )
        return build_dossier(profile, invariant=folded, plan=plan)


def _offers_for(subject: str, kind: str) -> tuple[CapabilityOffer, ...]:
    """The capabilities that could have answered for this subject, from the live catalogue.

    Read from the rows rather than supplied by the caller, so a dossier reached through a bare
    ``GET /dossier/{ref}`` carries a real coverage statement instead of a blank one. Without
    the stored subject this cannot be done honestly -- a referent like ``REF-a1b2`` does not
    say whether it was a domain or a name -- which is why the sink persists it.
    """
    if not subject:
        return ()
    from sources.capabilities import catalogue_offers

    from context_engine.enrichment_service import _query_shapes

    shapes = {shape.lower() for shape in _query_shapes(subject, kind)}
    selected = []
    for offer in catalogue_offers():
        declared = {k.lower() for k in offer["entity_kinds"]}
        if not declared or declared & shapes:
            selected.append(CapabilityOffer(**offer))
    return tuple(selected)


def _subject_of(rows: Sequence[Any]) -> tuple[str, str]:
    for row in rows:
        payload = (
            row["payload"] if isinstance(row["payload"], dict) else json.loads(row["payload"] or "{}")
        )
        subject = str(payload.get("subject") or "")
        if subject:
            return subject, str(payload.get("entity_kind") or "")
    return "", ""


def _entry_of(row: Any) -> dict[str, Any]:
    payload = row["payload"] if isinstance(row["payload"], dict) else json.loads(row["payload"] or "{}")
    return {
        "ts": row["ts"],
        "entity_id": row.get("entity_id", "") if hasattr(row, "get") else "",
        "kind": row["kind"],
        "sequence": row["sequence"],
        "record_hash": row["record_hash"],
        "observation_id": row["observation_id"],
        "payload": payload,
    }


def _payload_of(
    entry: dict[str, Any],
    facts: Sequence[dict[str, Any]],
    subject: str,
    kind: str,
) -> dict[str, Any]:
    """The row's payload: the event, plus the values it produced and who said so.

    ``facts`` travels with the row rather than in a sibling table so that a value and its
    source cannot be separated by a partial write or a join that someone forgets to write.
    """
    payload = dict(entry.get("payload") or {})
    if facts:
        payload["facts"] = list(facts)
    # What was asked, and of what kind. Without it a reader holding only a referent cannot
    # tell which capabilities apply -- it would have to guess from the referent's name, and
    # a wrong guess scores coverage against sources that never had a chance to answer.
    payload["subject"] = subject
    payload["entity_kind"] = kind
    return payload


def _facts_of(report: Any) -> tuple[dict[str, Any], ...]:
    """One entry per attribute value, each naming the source that produced it."""
    facts: list[dict[str, Any]] = []
    for name, state in sorted(getattr(report.subject, "attributes", {}).items()):
        for value in state.values:
            facts.append({"attribute": name, "value": value, "sources": list(state.sources)})
    return tuple(facts)


def _profile_of(entity_id: str, kind: str, rows: Sequence[Any]) -> EntityProfile:
    """Rebuild the attribute profile from the stream, keeping every source citation.

    A later event for the same attribute merges rather than replaces: two sources disagreeing
    is a ``CONFLICT`` the analyst has to see, and last-write-wins would have quietly picked a
    winner the platform has no basis for.
    """
    profile = EntityProfile(entity_id, kind or "unknown")
    for row in rows:
        payload = row["payload"] if isinstance(row["payload"], dict) else json.loads(row["payload"] or "{}")
        for fact in payload.get("facts", ()) or ():
            name = str(fact.get("attribute") or "")
            value = fact.get("value")
            if not name or value in (None, ""):
                continue
            for source in fact.get("sources", ()) or ("unknown",):
                profile.attributes[name] = merge_offer(
                    profile.attributes.get(name, AttributeState(name)),
                    source_id=str(source),
                    values=[str(value)],
                )
    return profile