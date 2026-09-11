# Contract: Projection Graph (T038, T041)

## Scope

Stores the knowledge graph: node/edge projection of observations, mentions,
candidates, entities, assertions, and findings. The app code must not import
vendor drivers (Neo4j/OpenSearch/ClickHouse) directly — vendor interaction lives
behind adapters in this app.

## Nodes

- `Observation`: raw or normalized observation (immutable; I-1). Key:
  observation_id.
- `Mention`: surface mention with offsets. Belongs to an Observation.
- `Candidate`: unresolved identity hypothesis (I-2).
- `Entity`: resolved identity from resolution only (I-2, I-6). TDA never
  produces Entities.
- `Assertion`: subject → relation → object claim admitted by Admission (I-3).
  Carries evidence_refs.
- `Finding`: a validated knowledge product derived from evidence.

## Edges (typed, directional)

- `observation_contains_mention`, `mention_mentions_candidate`,
  `candidate_resolves_to_entity`, `entity_assertion`,
  `assertion_references_observation` (evidence), `observation_derives_from`
  (T087), `finding_supports_*`.

## Behaviors

- Idempotent projection: applying the same (node/edge, provenance) twice yields
  one edge, not two (I-11).
- Rebuildable: `GraphSnapshot` records a projection_id + Kafka/event offset;
  `rebuild(projection_id)` replays the durable event log from the recorded
  offset and reconstructs the graph (I-12). A snapshot always carries
  provenance (event_id, observation_id).
- Immutability: node identity is immutable once written; only structural links
  may be added.

## Implementation notes

- `graph/abstraction.py`: `GraphStore` protocol + in-memory store.
- `graph/neo4j.py`: vendor adapter; contains the only Neo4j driver import.
- `graph/snapshot.py`: `GraphSnapshot` + `RebuildableProjection`.