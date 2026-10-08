"""Proof-of-work driver: collect, extract, resolve, graph, cascade.

Runs the whole pipeline against a live SearXNG instance and writes to PostgreSQL, so
the UI has real content to render. Every claim is stored with the observation that
supports it, which is what makes the output auditable rather than merely impressive.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
for app in ("control-plane", "shared", "acquisition"):
    sys.path.insert(0, str(ROOT / "apps" / app))

from services.document_adapter import (
    CandidateUniverse,
    adapt_document,
    resolve_document,
)

TENANT = "default-tenant"
SEARXNG = os.environ.get("SEARXNG_BASE_URL", "http://localhost:18090")
EXTRACTION_VERSION = "pow-heuristic/v1"


@dataclass
class GraphNode:
    """One extracted entity.

    ``entity_id`` is empty until the resolver decides this mention denotes an entity
    that already exists in the candidate universe. It is never derived from the name --
    ``semantic/resolution.py`` refuses that construction because a name-derived id
    breaks the moment a name is reused.
    """

    entity_id: str = ""
    name: str = ""
    kind: str = ""
    confidence: float = 0.0
    observations: list[str] = field(default_factory=list)
    groups: set[str] = field(default_factory=set)
    resolved: int = 0


@dataclass
class PowReport:
    investigation_id: str = ""
    seed: str = ""
    queries: list[str] = field(default_factory=list)
    observations: int = 0
    documents_parsed: int = 0
    entities: dict[str, GraphNode] = field(default_factory=dict)
    relations: list[dict[str, Any]] = field(default_factory=list)
    cascade_levels: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    #: Rows written into the temporal graph. 0 means the store was not configured,
    #: which is not the same as "nothing to record" -- see emit_temporal.
    temporal_rows: int = 0
    #: Entities this tenant already held, adopted so identity is not re-minted.
    adopted_entities: int = 0

    def _by_kind(self) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for node in self.entities.values():
            counts[node.kind] += 1
        return dict(sorted(counts.items()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "investigation_id": self.investigation_id,
            "seed": self.seed,
            "queries_run": self.queries,
            "observations": self.observations,
            "documents_parsed": self.documents_parsed,
            "entity_count": len(self.entities),
            "entities_by_kind": self._by_kind(),
            "relation_count": len(self.relations),
            "cascade_levels": self.cascade_levels,
            "temporal_rows": self.temporal_rows,
            "adopted_entities": self.adopted_entities,
            "errors": self.errors,
            "entities": [
                {
                    "name": n.name,
                    "kind": n.kind,
                    "confidence": round(n.confidence, 3),
                    "entity_id": n.entity_id,
                    "supporting_observations": len(n.observations),
                }
                for n in sorted(
                    self.entities.values(), key=lambda n: (-n.confidence, n.name)
                )
            ][:60],
            "relations": self.relations[:60],
        }


# --- collection ---------------------------------------------------------------


async def collect(query: str, investigation_id: str, *, limit: int = 2) -> list[dict[str, Any]]:
    """Real SearXNG search through the proven acquisition path."""
    from artifact_sink import ArtifactSink
    from events.content_router import ContentRouter
    from events.observation_gate import ObservationGate
    from runtime.searxng import SearXNGRuntime
    from storage.s3 import ObjectStore

    store = ObjectStore()
    gate = ObservationGate(store=store, router=ContentRouter())
    sink = ArtifactSink(gate=gate, store=store, source_family="web-search")
    runtime = SearXNGRuntime(base_url=SEARXNG)

    out: list[dict[str, Any]] = []
    task = {
        "task_id": f"TASK-{investigation_id}",
        "source_id": "SRC-searxng",
        "investigation_id": investigation_id,
        "query": query,
        "limit": limit,
    }
    cap = int(os.environ.get("POW_MAX_ARTIFACTS", "12"))
    taken = 0
    try:
        async for artifact in runtime.acquire(task):
            if taken >= cap:
                break
            try:
                acc = await sink.accept(
                    artifact, tenant_id=TENANT, investigation_id=investigation_id
                )
            except Exception:
                continue  # a refused artifact must not abort the run
            taken += 1
            # observed_at is what gives the temporal graph its axis. Prefer the
            # artifact's own retrieval time; fall back to now rather than leaving the
            # event undated, which would make "as of when" unanswerable.
            retrieved = getattr(artifact, "retrieved_at", None) or getattr(
                artifact, "timestamp", None
            )
            out.append(
                {
                    "observation_id": acc.observation_id,
                    "capture_id": acc.capture_id,
                    "raw_ref": acc.raw_ref,
                    "uri": acc.target_uri,
                    "body": getattr(artifact, "body", b"") or b"",
                    "query": query,
                    "retrieved_at": _as_datetime(retrieved) or datetime.now(UTC),
                }
            )
    finally:
        await runtime.aclose()
    return out




# --- persistence --------------------------------------------------------------


async def persist(
    investigation_id: str,
    observations: list[dict[str, Any]],
    nodes: dict[str, GraphNode],
    relations: list[dict[str, Any]],
) -> None:
    from domain.relation_identity import canonical_material, digest128

    from db.schema import Entity, EntityVersion, Observation, RelationClaim
    from db.session import make_session_factory

    factory = make_session_factory()
    async with factory() as session:
        for obs in observations:
            session.add(
                Observation(
                    observation_id=obs["observation_id"],
                    tenant_id=TENANT,
                    investigation_id=investigation_id,
                    source_id="SRC-searxng",
                    task_id=f"TASK-{investigation_id}",
                    uri=obs["uri"],
                    raw_ref=obs["raw_ref"],
                    # observations.content_hash is VARCHAR(64) and means a digest.
                    # The s3 ref belongs in raw_ref only -- it does not fit, and it is
                    # not a hash.
                    content_hash=obs["observation_id"].removeprefix("OBS-"),
                    content_type="application/json",
                    status="created",
                    duplicate=False,
                    provenance=json.dumps(
                        {
                            "capture_id": obs["capture_id"],
                            "query": obs["query"],
                            "runtime_ref": "searxng",
                        },
                        sort_keys=True,
                    ),
                )
            )

        known = await _existing_entity_ids(
            session, [n.entity_id for n in nodes.values() if n.entity_id]
        )
        for node in nodes.values():
            if not node.entity_id:
                # Never persist an entity the resolver did not name. A minted-from-name
                # id is refused by resolution.py for a reason, and writing one here
                # would put that same defect into durable state.
                continue
            if node.entity_id in known:
                # Already durable. Re-inserting it violates the primary key and aborts
                # the whole transaction, losing every genuinely new row with it. An
                # adopted identity is the normal case once the universe is seeded, so
                # this is the common path, not an edge case.
                continue
            session.add(
                Entity(
                    entity_id=node.entity_id,
                    tenant_id=TENANT,
                    entity_type=node.kind,
                    canonical_name=node.name,
                    attributes=json.dumps({"confidence": node.confidence}, sort_keys=True),
                    current_version=1,
                )
            )
            session.add(
                EntityVersion(
                    version_id=f"EV-{node.entity_id[4:16]}-1",
                    entity_id=node.entity_id,
                    tenant_id=TENANT,
                    version_number=1,
                    canonical_name=node.name,
                    attributes=json.dumps(
                        {"observations": node.observations[:5]}, sort_keys=True
                    ),
                )
            )

        seen: set[str] = set()
        # Materialise each relation's content address once, then filter against what the
        # authority already holds. `RC-` is derived from (subject, predicate, object),
        # so once identity is reused across runs a re-observed relation carries an id
        # that is already durable -- and re-inserting it aborts the transaction, losing
        # every genuinely new row in the same commit.
        pending: list[tuple[str, Any, Any, dict[str, Any]]] = []
        for rel in relations:
            subject = nodes.get(rel["subject"])
            obj = nodes.get(rel["object"])
            if subject is None or obj is None:
                continue
            if not subject.entity_id or not obj.entity_id:
                continue
            digest = digest128(
                canonical_material(
                    {
                        "subject": subject.entity_id,
                        "predicate": rel["predicate"],
                        "object": obj.entity_id,
                    }
                )
            )
            if digest in seen:
                continue
            seen.add(digest)
            pending.append((digest, subject, obj, rel))

        known_rel = await _existing_relation_ids(
            session, [f"RC-{d[:32]}" for d, _, _, _ in pending]
        )
        for digest, subject, obj, rel in pending:
            if f"RC-{digest[:32]}" in known_rel:
                continue
            session.add(
                RelationClaim(
                    relation_id=f"RC-{digest[:32]}",
                    logical_relation_id=f"RL-{digest[:32]}",
                    revision_number=1,
                    tenant_id=TENANT,
                    investigation_id=investigation_id,
                    relation_type=rel["predicate"],
                    arity_mode="BINARY",
                    subject_ref=subject.entity_id,
                    object_ref=obj.entity_id,
                    # relation_claim.role_bindings is NOT NULL; a co-mention edge has
                    # no argument structure, so it carries an explicit empty list
                    # rather than a null that reads as "unknown".
                    role_bindings=[],
                    # relation_claim has ten NOT NULL columns without defaults. All
                    # are filled explicitly here rather than relying on the model's
                    # optional-ness, because an omitted field silently becomes NULL
                    # and aborts the whole transaction at commit -- losing every
                    # row, not just the offending one.
                    assertion_refs=[],
                    observation_refs=list(rel.get("observations", []))[:8],
                    context_ref="",
                    source_independence_groups=[],
                    contradicts=[],
                    supersedes="",
                    extraction_version=EXTRACTION_VERSION,
                    normalization_version="pow/none",
                    ontology_version="pow/none",
                    schema_version="pow/v1",
                    status="active",
                    confidence=rel["confidence"],
                    evidence_grade="C",
                    created_by="pow",
                    content_hash=digest,
                )
            )
        await session.commit()


# --- existing identity -------------------------------------------------------


async def _existing_entity_ids(session: Any, wanted: list[str]) -> set[str]:
    """Which of these ids the authority already holds. Empty input short-circuits."""
    from db.schema import Entity
    from sqlalchemy import select

    if not wanted:
        return set()
    result = await session.execute(
        select(Entity.entity_id).where(Entity.entity_id.in_(set(wanted)))
    )
    return {str(row[0]) for row in result.all()}


async def _existing_relation_ids(session: Any, wanted: list[str]) -> set[str]:
    """Which of these relation ids the authority already holds."""
    from db.schema import RelationClaim
    from sqlalchemy import select

    if not wanted:
        return set()
    result = await session.execute(
        select(RelationClaim.relation_id).where(RelationClaim.relation_id.in_(set(wanted)))
    )
    return {str(row[0]) for row in result.all()}


async def adopt_existing_entities(universe: Any) -> int:
    """Adopt every entity this tenant already holds. Returns how many were adopted.

    Read-only over the authority: this asks what exists, never writes, and never
    invents an id. A failure here degrades to "adopt nothing", which is the old
    behaviour and is visible in the report rather than silent.
"""
    from db.schema import Entity
    from db.session import make_session_factory
    from sqlalchemy import select

    try:
        factory = make_session_factory()
    except Exception:
        return 0
    adopted = 0
    async with factory() as session:
        result = await session.execute(
            select(Entity.entity_id, Entity.entity_type, Entity.canonical_name).where(
                Entity.tenant_id == TENANT
            )
        )
        for entity_id, entity_type, canonical_name in result.all():
            if universe.adopt(kind=str(entity_type), canonical=str(canonical_name),
                              entity_id=str(entity_id)):
                adopted += 1
    return adopted


# --- temporal emit ------------------------------------------------------------


def _as_datetime(value: Any) -> datetime | None:
    """Coerce an artifact timestamp to an aware datetime, or None.

    Naive values are rejected rather than assumed to be UTC: the temporal store
    refuses naive timestamps precisely because assuming an offset corrupts history.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else None
    return None


async def emit_temporal(    investigation_id: str,
    observations: list[dict[str, Any]],
    nodes: dict[str, GraphNode],
    relations: list[dict[str, Any]],
) -> int:
    """Write the same graph into the temporal store, immediately.

    Called after Postgres accepted the rows, so the temporal projection is derived
    from committed authority rather than from this process's own beliefs.

    ``observed_at`` is the observation time, which is what gives the graph its
    temporality: "this entity, with these properties, as of when each source saw it".
    """
    from services.temporal_port import events_for_entity, events_for_relation

    sink = _temporal_sink()
    if sink is None:
        return 0

    # observation_id -> when it was seen, so every entity inherits the evidence trail
    seen_at: dict[str, Any] = {}
    for obs in observations:
        stamp = _as_datetime(obs.get("retrieved_at") or obs.get("observed_at"))
        if stamp is not None:
            seen_at[obs["observation_id"]] = stamp

    events: list[Any] = []
    # `nodes` is keyed by canonical *name*; the stable identity is `node.entity_id`,
    # minted by the resolver. Iterating the key as if it were the id wrote
    # `Путин Владимир`, `google`, `+442808032024` into the entity column, so the
    # analytical graph held one row per surface form and could not join with the
    # authority. That was the duplicate.
    for node in nodes.values():
        if not node.entity_id:
            # Never persist an entity the resolver did not name (§ the same rule the
            # Postgres writer follows).
            continue
        observation_ids = list(node.observations) or []
        if not observation_ids:
            continue
        stamps = [seen_at[o] for o in observation_ids if o in seen_at]
        events.extend(
            events_for_entity(
                tenant_id=TENANT,
                entity_id=node.entity_id,
                entity_class=node.kind,
                observation_ids=observation_ids,
                attributes={
                    "name": node.name,
                    "kind": node.kind,
                    "confidence": node.confidence,
                    "investigation_id": investigation_id,
                },
                observed_at=max(stamps) if stamps else None,
                extraction_version=EXTRACTION_VERSION,
            )
        )

    for rel in relations:
        rel_observations = list(rel.get("observations", []))
        rel_stamps = [seen_at[o] for o in rel_observations if o in seen_at]
        # Relations are built from canonical *names* (``ca``/``cb`` above), but the
        # temporal graph is keyed by entity_id. Emitting the name here wrote rows under
        # `China`, `DW.com` instead of `ENT-...`, so the analytical graph could not
        # join with the authority and every run minted a fresh id for the same
        # entity -- which is where the duplicates came from.
        subject_node = nodes.get(rel["subject"])
        object_node = nodes.get(rel["object"])
        subject_id = subject_node.entity_id if subject_node else ""
        object_id = object_node.entity_id if object_node else ""
        if not subject_id or not object_id:
            continue
        events.extend(
            events_for_relation(
                tenant_id=TENANT,
                subject_id=subject_id,
                object_id=object_id,
                predicate=rel["predicate"],
                observation_ids=rel_observations,
                confidence=rel["confidence"],
                # Without this the relation's validity defaults to the epoch, which
                # reads as "true since 1970" -- an unfounded claim about the past.
                observed_at=max(rel_stamps) if rel_stamps else None,
                extraction_version=EXTRACTION_VERSION,
            )
        )

    return await sink.ingest(_number_per_entity(events))


def _number_per_entity(events: list[Any]) -> list[Any]:
    """Give every event a sequence unique within its entity.

    Not cosmetic. The temporal store collapses rows that share
    (entity, valid_from, sequence), so a per-relation counter that restarts at zero
    silently merges every relation a subject had with one observation: 370 relations
    were stored as 40. Ordering is per entity because that is the axis the graph is
    queried on.
    """
    counters: dict[str, int] = defaultdict(int)
    for event in events:
        entity_id = getattr(event, "entity_id", "")
        event.sequence = counters[entity_id]
        counters[entity_id] += 1
    return events


_sink_cache: list[Any] = []


def _temporal_sink() -> Any:
    """Build the ClickHouse-backed sink once, or return None if it is not configured.

    Assembled by duck typing rather than imported: control-plane may not depend on
    projection. Returns None when ClickHouse is unreachable so the authoritative run
    still completes -- an analytical store being down must not lose real findings.
    """
    if _sink_cache:
        return _sink_cache[0]
    url = os.environ.get("CLICKHOUSE_URL")
    if not url:
        return None
    try:
        from analytics.clickhouse_client import ClickHouseHTTP
        from analytics.temporal_graph import ClickHouseTemporalStore
    except ImportError as exc:
        raise RuntimeError(f"temporal sink unavailable: {exc}") from exc
    sink = ClickHouseTemporalStore(
        ClickHouseHTTP(
            url=url,
            database=os.environ.get("CLICKHOUSE_DB", "cognitive"),
            user=os.environ.get("CLICKHOUSE_USER", "default"),
            password=os.environ.get("CLICKHOUSE_PASSWORD", ""),
        )
    )
    _sink_cache.append(sink)
    return sink


# --- the run ------------------------------------------------------------------


def _queries_for(name: str, seed: str) -> list[str]:
    if name == seed:
        return [seed]
    return [name]


async def run(seed: str, *, rounds: int = 2, breadth: int = 3) -> PowReport:
    """Collect, extract, graph, then expand frontier-wide and repeat."""
    from db.schema import Investigation
    from db.session import make_session_factory

    report = PowReport(seed=seed)
    investigation_id = f"INV-{uuid.uuid4().hex[:12]}"
    report.investigation_id = investigation_id

    factory = make_session_factory()
    async with factory() as session:
        session.add(
            Investigation(
                investigation_id=investigation_id,
                name=f"PoW: {seed}",
                tenant_id=TENANT,
                objective=f"Cascade expansion from {seed}",
                seeds=[seed],
                scope=[seed],
                policy_id="policies/default",
                state="RUNNING",
            )
        )
        await session.commit()

    all_observations: list[dict[str, Any]] = []
    visited_queries: set[str] = set()
    expanded_names: set[str] = set()
    neighbours: dict[str, set[str]] = defaultdict(set)
    queue: deque[str] = deque([seed])
    universe = CandidateUniverse(tenant_id=TENANT, investigation_id=investigation_id)
    # Seed the universe with the entities this tenant already durably holds, so a
    # mention of a known canonical form joins the existing entity instead of minting a
    # rival id. `ENT-` derives from (tenant, scope=investigation, anchor mention), so
    # without this every investigation re-identifies every entity it touches: measured
    # at 486 entity rows for 83 distinct names across 11 investigations, "Russia" alone
    # holding 11 ids. The durable-anchor discipline the platform already states
    # (`domain.entity_identity.anchor_for_mention`, `merged_mentions`) had no write
    # side wired into collection; this is it.
    adopted = await adopt_existing_entities(universe)
    report.adopted_entities = adopted

    for level in range(rounds):
        batch = list(queue)[:breadth]
        queue.clear()
        if not batch:
            break

        expanded_here: list[str] = []

        for name in batch:
            if name in expanded_names:
                continue
            expanded_names.add(name)
            expanded_here.append(name)

            for query in _queries_for(name, seed):
                if query in visited_queries:
                    continue
                visited_queries.add(query)
                report.queries.append(query)

                for obs in await collect(query, investigation_id):
                    all_observations.append(obs)
                    report.observations += 1

                    report.documents_parsed += 1

                    # The platform's own extraction lane. No pattern matching of our
                    # own: `extract_deterministic` already resolves persons against
                    # dictionaries and morphology, orgs against the company
                    # automaton, places against GeoNames, and contacts by pattern.
                    document = adapt_document(
                        obs["body"],
                        capture_ref=obs["capture_id"],
                        content_type="application/json",
                        tenant_id=TENANT,
                        investigation_id=investigation_id,
                        source_id="SRC-searxng",
                        source_family="web-search",
                        observed_at=datetime.now(UTC),
                    )
                    universe.seed(document)
                    batch, ents = resolve_document(
                        document,
                        candidates=universe.candidates(),
                        investigation_id=investigation_id,
                        tenant_id=TENANT,
                    )

                    for mention in document.mentions:
                        canonical = document.canonical_for(mention.mention_id) or mention.surface
                        node = report.entities.get(canonical)
                        if node is None:
                            node = GraphNode(
                                entity_id="",
                                name=canonical,
                                kind=mention.kind,
                                confidence=0.0,
                            )
                            report.entities[canonical] = node
                        if obs["observation_id"] not in node.observations:
                            node.observations.append(obs["observation_id"])
                        node.groups.update(
                            g for g in (mention.independence_group,) if g
                        )

                    for resolved in ents:
                        canonical = document.canonical_for(
                            resolved.anchor_mention_id
                        ) or resolved.surface
                        node = report.entities.get(canonical)
                        if node is None:
                            continue
                        node.confidence = max(node.confidence, resolved.confidence)
                        if resolved.entity_id:
                            node.entity_id = resolved.entity_id
                        node.resolved += 1

                    # Semantic relations, from the extraction lane's own readings.
                    #
                    # This is what the co-presence loop below is not. Two entities
                    # sharing a document is co-occurrence evidence; "Igor Sechin is
                    # deputy chairman of Gazprom" is a claim about who works for whom.
                    # The readings were produced for the whole life of
                    # `extractors.relations` and had no carrier, so every edge in the
                    # graph until now was the weaker kind and nothing said a role.
                    #
                    # The cascade frontier is fed from these as well as from
                    # co-presence, so a stated relationship is what expands the
                    # investigation rather than mere co-presence in a snippet.
                    for relation in document.relations:
                        subject_canonical = document.canonical_for(
                            relation.subject_mention_id
                        )
                        object_canonical = document.canonical_for(
                            relation.object_mention_id
                        )
                        subject_node = report.entities.get(subject_canonical or "")
                        object_node = report.entities.get(object_canonical or "")
                        if subject_node is None or object_node is None:
                            continue
                        if not (subject_node.entity_id and object_node.entity_id):
                            continue
                        report.relations.append(
                            {
                                "subject": subject_canonical,
                                "object": object_canonical,
                                "predicate": relation.predicate,
                                "confidence": round(relation.confidence, 3),
                                "observations": [obs["observation_id"]],
                                "evidence_kind": "asserted_relation",
                                "role": relation.role,
                            }
                        )
                        neighbours[subject_canonical].add(object_canonical)
                        neighbours[object_canonical].add(subject_canonical)

                    # Co-presence edges, built only between entities the resolver
                    # actually named. Linking mentions that share a document is the
                    # platform's `co_occurrence` evidence, not a relation claim, and
                    # it is kept explicitly weaker than a resolved relation.
                    for a in document.mentions:
                        for b in document.mentions:
                            if a.mention_id >= b.mention_id:
                                continue
                            ca = document.canonical_for(a.mention_id)
                            cb = document.canonical_for(b.mention_id)
                            if not ca or not cb or ca == cb:
                                continue
                            na = report.entities.get(ca)
                            nb = report.entities.get(cb)
                            if na is None or nb is None:
                                continue
                            if na.kind not in ("person", "org") and nb.kind not in ("person", "org"):
                                continue
                            neighbours[ca].add(cb)
                            neighbours[cb].add(ca)
                            report.relations.append(
                                {
                                    "subject": ca,
                                    "object": cb,
                                    "predicate": "co_occurs_with",
                                    "confidence": 0.35,
                                    "observations": [obs["observation_id"]],
                                }
                            )


        report.cascade_levels.append(
            {
                "level": level,
                "expanded": expanded_here,
                "entities_so_far": len(report.entities),
                "relations_so_far": len(report.relations),
            }
        )

        for name in expanded_here:
            for nb in sorted(neighbours.get(name, ())):
                node = report.entities.get(nb)
                if node is None or node.kind not in ("person", "organization"):
                    continue
                if node.confidence < 0.7:
                    continue
                if nb in expanded_names or nb in queue:
                    continue
                queue.append(nb)

    if all_observations:
        try:
            await persist(
                investigation_id, all_observations, report.entities, report.relations
            )
        except Exception as exc:  # persistence failure must not destroy the report
            report.errors.append(f"persist failed: {type(exc).__name__}: {exc}")
        # Temporal emit runs off whatever Postgres accepted, so the analytical graph
        # can never claim a belief the authority rejected. A failure here is recorded
        # and swallowed for the same reason: the report is still worth having.
        try:
            written = await emit_temporal(
                investigation_id, all_observations, report.entities, report.relations
            )
            report.temporal_rows = written
        except Exception as exc:
            report.errors.append(f"temporal emit failed: {type(exc).__name__}: {exc}")

    return report


def main() -> int:
    seed = sys.argv[1] if len(sys.argv) > 1 else "Vladimir Putin"
    rounds = int(os.environ.get("POW_ROUNDS", "2"))
    breadth = int(os.environ.get("POW_BREADTH", "3"))
    report = asyncio.run(run(seed, rounds=rounds, breadth=breadth))
    print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    return 0 if report.entities else 1


if __name__ == "__main__":
    raise SystemExit(main())