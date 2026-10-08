"""The severed link, closed: real bytes to persisted entities, graph and invariants.

What this module exists to fix, precisely
-----------------------------------------
The deterministic extraction stack is complete and correct. ``extract_deterministic``
parses bytes into typed mentions; ``document_adapter.adapt_document`` turns those into
resolution input; ``resolve_document`` merges them into ``ENT-`` entities. Every one of those
is reached only from tests, from proof scripts, or from ``services/pow_run.py`` -- which has
**zero importers**.

The live path, ``POST /api/v1/entities`` -> ``entity_pipeline`` -> ``interpret_warc_capture``,
ends in a plain dict inside a process-local ``Catalog``. It never writes an entity row, never
writes a relation row, never emits an event, and never appends to ``entity_stream``. So the
tables that ``GET /api/v1/entities/graph`` reads, that ``from_entity_stream`` materialises
invariants from, and that the context fabric resolves membership against, were all empty in
any real deployment.

This module is the production writer that was missing. It performs, in order:

1. **Fetch** real bytes through a catalogue source, or accept bytes directly.
2. **Extract** with the deterministic lane -- no model, no inference.
3. **Resolve** mentions into entities, deterministically.
4. **Persist** ``observations``, ``entities``, ``entity_versions`` and ``relation_claims``,
   typed against the single ontology authority in ``domain.ontology``.
5. **Append to ``entity_stream``**, which is what makes an invariant derivable at all, and
   return the ``observation_id -> entities`` mapping the fabric needs.

Step 5 is the one the rest of the platform was waiting on. Until a stream row exists,
:func:`context_engine.return_path.resolve_outcomes` resolves nothing, every observation
arrives with an undetermined scope, and the context cannot deepen past its root no matter how
much evidence is gathered.

Every failure is reported, never swallowed: a document that yields no entities is a finding
about the source, not a success.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any

from services.document_adapter import NORMALIZATION_VERSION, ONTOLOGY_VERSION

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class InterpretationResult:
    """What one document produced, all the way through persistence."""

    observation_id: str
    content_hash: str
    content_type: str
    artifact_kind: str
    mentions: int = 0
    entities: tuple[str, ...] = ()
    relations: int = 0
    unresolved: int = 0
    dropped_kinds: tuple[str, ...] = ()
    persisted: bool = False
    reason: str = ""

    @property
    def produced_nothing(self) -> bool:
        return not self.entities

    def as_dict(self) -> dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "content_hash": self.content_hash,
            "content_type": self.content_type,
            "artifact_kind": self.artifact_kind,
            "mentions": self.mentions,
            "entities": list(self.entities),
            "relations": self.relations,
            "unresolved": self.unresolved,
            "dropped_kinds": list(self.dropped_kinds),
            "persisted": self.persisted,
            "reason": self.reason,
        }


@dataclass(slots=True)
class EntityStore:
    """The Postgres writers, behind one seam.

    A class rather than free functions because every method needs a session, and because the
    caller should not have to know that persisting an entity means an ``entities`` row *and* an
    ``entity_versions`` row *and* an ``entity_stream`` row. Getting the third wrong is what
    makes invariants vanish while entities appear present.
    """

    session_factory: Any
    tenant_id: str = "default-tenant"
    extra: dict[str, Any] = field(default_factory=dict)


class InterpretationBridge:
    """Bytes to persisted entities, graph rows and stream records."""

    def __init__(
        self, store: EntityStore, *, source_family: str = "", scope_id: str = "default"
    ) -> None:
        self._store = store
        self._source_family = source_family
        #: The resolution scope referent ids are minted within. Passed by the caller so the
        #: same investigation mints the same referent on every tick.
        self._scope_id = scope_id

    # -- 1. fetch -------------------------------------------------------------

    async def fetch(self, source: Any, query: str) -> tuple[bytes, str]:
        """Fetch through a catalogue source. Returns ``(body, content_type)``.

        Imported lazily because ``sources.executor`` pulls in httpx and the catalogue, and a
        caller that already holds bytes should not pay for either.
        """
        from sources.executor import AcquisitionError, HttpSourceExecutor

        executor = HttpSourceExecutor()
        try:
            captured = await executor.run(source, query)
        except AcquisitionError as exc:
            raise RuntimeError(f"source {getattr(source, 'name', '?')} failed: {exc}") from exc
        return captured.body, str(captured.content_type or "")

    # -- 2..3. extract and resolve --------------------------------------------

    def interpret(
        self,
        body: bytes,
        *,
        capture_ref: str,
        content_type: str = "",
        investigation_id: str = "",
        source_id: str = "",
        observed_at: str = "",
    ) -> InterpretationResult:
        """Extract and resolve, without touching the database.

        Separated from persistence so the extraction path can be exercised on real bytes with
        no infrastructure -- which is how the ``ip``/``crypto`` drop was found.
        """
        from domain.ontology import kind_of_media_type
        from extractors.lane import extract_deterministic

        from services.document_adapter import (
            CandidateUniverse,
            adapt_document,
            resolve_document,
        )

        digest = hashlib.sha256(body).hexdigest()
        artifact = kind_of_media_type(content_type).value
        extraction = extract_deterministic(body)
        if not extraction.mentions:
            return InterpretationResult(
                observation_id=observation_id_for(digest, self._store.tenant_id),
                content_hash=digest,
                content_type=content_type,
                artifact_kind=artifact,
                reason=extraction.reason or "no mentions extracted",
            )

        document = adapt_document(
            body,
            capture_ref=capture_ref,
            content_type=content_type or None,
            tenant_id=self._store.tenant_id,
            investigation_id=investigation_id,
            source_id=source_id,
            source_family=self._source_family,
            observed_at=observed_at or datetime.now(UTC).isoformat(),
        )
        universe = CandidateUniverse()
        universe.seed(document)
        batch, resolved = resolve_document(
            document,
            candidates=universe.candidates(),
            investigation_id=investigation_id,
            tenant_id=self._store.tenant_id,
        )
        return InterpretationResult(
            observation_id=observation_id_for(digest, self._store.tenant_id),
            content_hash=digest,
            content_type=content_type,
            artifact_kind=artifact,
            mentions=len(document.mentions),
            entities=tuple(entity.entity_id for entity in resolved),
            relations=len(document.relations),
            unresolved=sum(
                1 for candidate in batch.candidates if candidate.verdict.value == "UNRESOLVED"
            ),
            dropped_kinds=document.dropped_unknown_kinds,
            reason="" if resolved else "every mention was refused an identity",
        )

    # -- 4. persist -----------------------------------------------------------

    async def persist(
        self,
        body: bytes,
        result: InterpretationResult,
        document: Any = None,
        resolved: Sequence[Any] = (),
        *,
        investigation_id: str = "",
        source_id: str = "",
        uri: str = "",
        task_id: str = "",
    ) -> bool:
        """Write the observation, its entities, their versions, relations and stream rows.

        Every write shares one transaction. A committed observation with no entities is a row
        that looks like evidence and is not, and it is the state this platform was in.
        """
        from domain.ontology import coerce_entity_type
        from sqlalchemy import select

        from db.schema import Candidate as CandidateRow
        from db.schema import Entity as EntityRow
        from db.schema import EntityVersion as EntityVersionRow
        from db.schema import Observation as ObservationRow
        from db.schema import RelationClaim as RelationClaimRow

        session = self._store.session_factory()
        try:
            # ``no_autoflush``: the existence probe must not flush a pending add. Without
            # it the SELECT triggers an early INSERT, and a document already stored raises
            # a primary-key violation inside the probe instead of being recognised as a
            # retry.
            with session.no_autoflush:
                existing = await session.execute(
                select(ObservationRow).where(
                    ObservationRow.observation_id == result.observation_id,
                    ObservationRow.tenant_id == self._store.tenant_id,
                )
            )
            if existing.scalar_one_or_none() is None:
                session.add(
                    ObservationRow(
                        observation_id=result.observation_id,
                        tenant_id=self._store.tenant_id,
                        investigation_id=investigation_id or None,
                        source_id=source_id or None,
                        task_id=task_id or None,
                        uri=uri or None,
                        raw_ref=f"sha256://{result.content_hash}",
                        content_hash=result.content_hash,
                        content_type=result.content_type or None,
                        status="created",
                        duplicate=False,
                        provenance={
                            "artifact_kind": result.artifact_kind,
                            "mentions": result.mentions,
                            "extraction_version": "interpretation-bridge-v1",
                        },
                    )
                )

            for entity in resolved:
                # A referent, so an unresolved mention is still storable. The resolver mints
                # no id for it, and refusing to store it left the graph structurally empty.
                entity_type = coerce_entity_type(entity.kind).value
                canonical = getattr(entity, "surface", "") or ""
                entity_id = entity.entity_id or referent_id_for(
                    entity.kind,
                    canonical,
                    tenant_id=self._store.tenant_id,
                    scope_id=investigation_id or "default",
                )
                verdict = str(getattr(entity, "verdict", "") or "")
                row = await session.execute(
                    select(EntityRow).where(
                        EntityRow.entity_id == entity_id,
                        EntityRow.tenant_id == self._store.tenant_id,
                    )
                )
                found = row.scalar_one_or_none()
                if found is None:
                    session.add(
                        EntityRow(
                            entity_id=entity_id,
                            tenant_id=self._store.tenant_id,
                            entity_type=entity_type,
                            canonical_name=canonical,
                            current_version=1,
                            attributes={
                                "verdict": verdict,
                                "kind": entity.kind,
                                "observation_id": result.observation_id,
                            },
                        )
                    )
                    # An unresolved mention is a *candidate*, which is what spec 021's second
                    # semantic layer is for. It is not admitted, and this is the row that
                    # says so.
                    if verdict.lower() != "resolved":
                        session.add(
                            CandidateRow(
                                candidate_id="CAN-" + entity_id[4:][:24],
                                tenant_id=self._store.tenant_id,
                                mention_ids=[entity.anchor_mention_id],
                                surface_form=canonical,
                                normalized_form=canonical,
                                type_hypothesis=entity_type,
                                state="OPEN",
                                # The column is a Postgres enum whose members are
                                # PROVISIONAL/DEFERRED/QUARANTINED/ACCEPTED/REJECTED.
                                # Writing the resolver's verdict verbatim raised
                                # ``invalid input value for enum epistemicstatus`` and
                                # rolled back the whole document -- entities, observation
                                # and all -- so the terminology had to be translated rather
                                # than copied.
                                epistemic_status=_EPISTEMIC_BY_VERDICT.get(
                                    verdict.lower(), "PROVISIONAL"
                                ),
                            )
                        )
                    # The column set is ``version_id``/``version_number``/``attributes``;
                    # writing ``version`` and ``payload`` -- the names an earlier draft used
                    # -- raised "invalid keyword argument" and took the whole transaction
                    # with it, so the document produced entities and persisted nothing.
                    session.add(
                        EntityVersionRow(
                            version_id=f"EV-{entity_id[:20]}-1",
                            entity_id=entity_id,
                            tenant_id=self._store.tenant_id,
                            version_number=1,
                            canonical_name=getattr(entity, "surface", "") or "",
                            attributes={
                                "kind": entity.kind,
                                "entity_type": entity_type,
                                "surface": getattr(entity, "surface", ""),
                                "confidence": float(getattr(entity, "confidence", 0.0) or 0.0),
                                "observation_id": result.observation_id,
                            },
                        )
                    )

            if document is not None:
                for relation in document.relations:
                    session.add(
                        RelationClaimRow(
                            relation_id=_relation_id(relation),
                            logical_relation_id=_relation_id(relation),
                            revision_number=1,
                            tenant_id=self._store.tenant_id,
                            investigation_id=investigation_id or None,
                            relation_type=relation.relation_type,
                            arity_mode="BINARY",
                            subject_ref=relation.subject_mention_id,
                            object_ref=relation.object_mention_id,
                            observation_refs=[result.observation_id],
                            ontology_version=ONTOLOGY_VERSION,
                            normalization_version=NORMALIZATION_VERSION,
                            extraction_version="interpretation-bridge-v1",
                            status="EXTRACTED",
                            confidence=float(relation.confidence),
                            created_by="interpretation_bridge",
                        )
                    )

            await session.commit()
            return True
        except Exception as exc:  # noqa: BLE001 - a write failure is reported, not raised
            await session.rollback()
            log.warning("persist failed for %s: %s", result.observation_id, exc)
            return False
        finally:
            await session.close()

    # -- 5. stream ------------------------------------------------------------

    async def append_stream(
        self, result: InterpretationResult, resolved: Sequence[Any], *, sequence_base: int = 0
    ) -> int:
        """Append one stream record per entity. This is what makes an invariant derivable.

        ``from_entity_stream`` reads only this table. Without these rows the entity exists,
        the graph endpoint shows it, and the invariant endpoint reports nothing -- which is
        exactly the 404 users saw.
        """
        from domain.dynamics import StreamRecord
        from sqlalchemy import func, select

        from db.schema import EntityStreamRow

        if not resolved:
            return 0
        session = self._store.session_factory()
        written = 0
        try:
            for offset, entity in enumerate(resolved, start=1):
                stream_id = entity.entity_id or referent_id_for(
                    entity.kind,
                    getattr(entity, "surface", "") or "",
                    tenant_id=self._store.tenant_id,
                    scope_id=self._scope_id,
                )
                highest = await session.execute(
                    select(func.max(EntityStreamRow.sequence)).where(
                        EntityStreamRow.tenant_id == self._store.tenant_id,
                        EntityStreamRow.entity_id == stream_id,
                    )
                )
                current = highest.scalar() or 0
                record = StreamRecord(
                    tenant_id=self._store.tenant_id,
                    entity_id=stream_id,
                    sequence=current + 1,
                    ts=datetime.now(UTC),
                    kind="extraction",
                    payload={
                        "surface": getattr(entity, "surface", ""),
                        "kind": entity.kind,
                        "verdict": getattr(getattr(entity, "verdict", None), "value", ""),
                        "confidence": float(getattr(entity, "confidence", 0.0) or 0.0),
                    },
                    observation_id=result.observation_id,
                )
                session.add(
                    EntityStreamRow(
                        tenant_id=record.tenant_id,
                        entity_id=record.entity_id,
                        sequence=record.sequence,
                        record_hash=record.record_hash,
                        kind=record.kind,
                        ts=datetime.now(UTC),
                        payload=record.payload,
                        observation_id=record.observation_id,
                        extraction_version="interpretation-bridge-v1",
                    )
                )
                written += 1
            await session.commit()
        except Exception as exc:  # noqa: BLE001
            await session.rollback()
            log.warning("stream append failed for %s: %s", result.observation_id, exc)
            return 0
        finally:
            await session.close()
        return written

    # -- the whole path -------------------------------------------------------

    async def ingest(
        self,
        body: bytes,
        *,
        content_type: str = "",
        investigation_id: str = "",
        source_id: str = "",
        uri: str = "",
        capture_ref: str = "",
        task_id: str = "",
        observed_at: str = "",
    ) -> tuple[InterpretationResult, dict[str, tuple[str, ...]]]:
        """Fetch-free end-to-end pass. Returns ``(result, observation -> entities)``.

        The returned mapping is the handoff to the context fabric: it is what makes an
        observation placeable, and returning it here means the caller does not have to know
        that the mapping is assembled from ``entity_stream`` rows.
        """
        from domain.ontology import kind_of_media_type

        from services.document_adapter import (
            CandidateUniverse,
            adapt_document,
            resolve_document,
        )

        capture = capture_ref or f"cap-{hashlib.sha256(body).hexdigest()[:24]}"
        digest = hashlib.sha256(body).hexdigest()

        document = adapt_document(
            body,
            capture_ref=capture,
            content_type=content_type or None,
            tenant_id=self._store.tenant_id,
            investigation_id=investigation_id,
            source_id=source_id,
            source_family=self._source_family,
            observed_at=observed_at or datetime.now(UTC).isoformat(),
        )
        universe = CandidateUniverse()
        universe.seed(document)
        _, resolved = resolve_document(
            document,
            candidates=universe.candidates(),
            investigation_id=investigation_id,
            tenant_id=self._store.tenant_id,
        )

        result = InterpretationResult(
            observation_id=observation_id_for(digest, self._store.tenant_id),
            content_hash=digest,
            content_type=content_type,
            artifact_kind=kind_of_media_type(content_type).value,
            mentions=len(document.mentions),
            entities=tuple(entity.entity_id for entity in resolved),
            relations=len(document.relations),
            dropped_kinds=document.dropped_unknown_kinds,
            reason="" if resolved else "every mention was refused an identity",
        )

        persisted = await self.persist(
            body,
            result,
            document=document,
            resolved=resolved,
            investigation_id=investigation_id,
            source_id=source_id,
            uri=uri,
            task_id=task_id,
        )
        await self.append_stream(result, resolved)
        result = replace(result, persisted=persisted)

        membership = await self.membership_for([result.observation_id])
        return result, membership

    async def membership_for(
        self, observation_ids: Sequence[str]
    ) -> dict[str, tuple[str, ...]]:
        """``observation_id -> entities``, read through the same reader the cycle uses."""
        from db.entity_stream import SqlEntityStreamRepository

        session = self._store.session_factory()
        try:
            repository = SqlEntityStreamRepository(session)
            return await repository.entities_for_observations(
                tenant_id=self._store.tenant_id, observation_ids=observation_ids
            )
        finally:
            await session.close()

    async def invariant_for(self, entity_id: str) -> dict[str, Any] | None:
        """Materialise the dynamic invariant for one entity from its stream.

        The reader path ``GET /entities/{id}/invariant`` never had: it looked in a
        process-local dict that the fallback path wrote as ``{}``.
        """
        from domain.dynamics import StreamRecord
        from domain.graph_invariant import from_entity_stream
        from sqlalchemy import select

        from db.schema import EntityStreamRow

        session = self._store.session_factory()
        try:
            rows = await session.execute(
                select(EntityStreamRow)
                .where(
                    EntityStreamRow.tenant_id == self._store.tenant_id,
                    EntityStreamRow.entity_id == entity_id,
                )
                .order_by(EntityStreamRow.sequence)
            )
            records = [
                StreamRecord(
                    tenant_id=row.tenant_id,
                    entity_id=row.entity_id,
                    sequence=row.sequence,
                    ts=row.ts,
                    kind=row.kind,
                    payload=row.payload if isinstance(row.payload, dict) else {},
                    observation_id=row.observation_id,
                )
                for row in rows.scalars().all()
            ]
            if not records:
                return None
            invariant = from_entity_stream(
                records,
                tenant_id=self._store.tenant_id,
                type_label=entity_id,
            )
            # ``GraphInvariant`` serialises through ``as_dict``; there is no ``to_dict``.
            return invariant.as_dict()
        except Exception as exc:  # noqa: BLE001
            log.warning("invariant failed for %s: %s", entity_id, exc)
            return None
        finally:
            await session.close()


def observation_id_for(digest: str, tenant_id: str) -> str:
    """A tenant-scoped observation id.

    ``observations_pkey`` is on ``observation_id`` alone while the platform is multi-tenant,
    so a content-addressed id derived from the body alone collides across tenants: the same
    public page fetched for tenant A blocks tenant B with a primary-key violation, and the
    existence probe -- which filters by tenant -- never finds the row to recognise it as a
    retry. Including the tenant makes the id agree with the key that constrains it.
    """
    material = f"{tenant_id}|{digest}"
    return "OBS-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


def referent_id_for(kind: str, canonical: str, *, tenant_id: str, scope_id: str) -> str:
    """A stable id for *what a mention points at*, not for an admitted identity.

    The resolver deliberately mints no ``entity_id`` for an unresolved mention: it has
    decided nothing, and admitting an entity it has not resolved would be exactly the
    name-derived-identity defect ``semantic/resolution.py`` exists to prevent. The
    consequence, unhandled until now, is that **nothing is storable at all** -- no entity
    row, no ``entity_stream`` row, no invariant, and a graph that is empty no matter how much
    real evidence arrives.

    This mints a *referent* instead: a claim that mentions of this kind and canonical form
    point at the same thing. It is an admission of nothing and an aggregation of everything,
    which is what makes corroboration measurable -- two documents mentioning the same
    ``org``/``google`` produce one referent with two independence groups, and that count is
    what an invariant is built from.

    Keyed on the extractor-normalized canonical form, never on the raw surface, so
    ``Gazprom`` and ``Газпром`` with the same normalization land on one referent.
    """
    material = f"{tenant_id}|{scope_id}|{kind}|{canonical}"
    return "REF-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


#: Resolver verdict -> the candidate table's closed vocabulary. See the note at the write
#: site: these are two different vocabularies for adjacent ideas, and copying one into the
#: other is what produced an enum violation on every document.
_EPISTEMIC_BY_VERDICT: dict[str, str] = {
    "unresolved": "PROVISIONAL",
    "deferred": "DEFERRED",
    "quarantined": "QUARANTINED",
    "resolved": "ACCEPTED",
    "rejected": "REJECTED",
    "conflict": "DEFERRED",
}


def _relation_id(relation: Any) -> str:
    """A stable id for one extracted relation.

    Derived from its three parts rather than minted, so re-interpreting the same document
    produces the same row and the upsert is a retry instead of a duplicate claim. Length is
    trimmed to the column: ``relation_id`` is ``VARCHAR(64)`` and three mention ids
    concatenated exceed it, which is a truncation error rather than a hash collision.
    """
    material = "|".join(
        (
            str(getattr(relation, "subject_mention_id", "")),
            str(getattr(relation, "relation_type", "")),
            str(getattr(relation, "object_mention_id", "")),
        )
    )
    return "REL-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:40]


def entity_types_in_use(entities: Iterable[Any]) -> dict[str, int]:
    """Count entity types in a batch, for a coverage report.

    Reported per tick because an extraction pipeline whose types are all ``unknown`` is
    producing structure with no semantics, and nothing else in the platform shows that.
    """
    counts: dict[str, int] = {}
    for entity in entities:
        kind = str(getattr(entity, "kind", "") or "unknown")
        counts[kind] = counts.get(kind, 0) + 1
    return counts


def membership_mapping(result: InterpretationResult) -> Mapping[str, tuple[str, ...]]:
    """The handoff shape, from a result that already carries its entities."""
    return {result.observation_id: tuple(result.entities)}
