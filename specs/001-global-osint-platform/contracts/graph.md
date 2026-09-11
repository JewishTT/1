# Graph Abstraction Contract

Application/domain code interacts with graphs only through these interfaces (Constitution C-5, Spec FR-018 / §73). Backends (Neo4j dev, Memgraph, custom analytical representation) are adapters chosen by benchmark (R-2). No vendor-specific imports in application logic.

## Interfaces

```text
GraphProjector            // materialize/refresh a projection from evidence/events
   project_kind(kind, as_of, source_refs) -> ProjectionRun
   rebuild(projection_id) -> ProjectionRun           // from durable events (I-10)
   snapshot(snapshot_id) -> GraphSnapshot

GraphReader
   get_entity(entity_id) -> EntityView
   get_relation(edge_id) -> RelationView
   query(pattern) -> ResultSet                        // pattern = node/edge pattern

GraphTraversal
   neighbors(entity_id, hops, filters) -> Subgraph
   path(subject_id, object_id, predicates) -> Paths

GraphSnapshot
   snapshot_id, as_of, node_count, edge_count, uri, checksum

GraphExporter
   export_snapshot(snapshot_id, format) -> artifact uri
```

## Node / Edge shapes (Spec §40)

- Node: entity_id, type, confidence, embedding, first_seen, last_seen, provenance_summary.
- Edge: source, target, predicate, confidence, weight, valid_from, valid_to, support_count, independent_support, provenance.

## Rules

- Projections are rebuildable: `rebuild(projection_id)` must recreate content from Kafka event offsets (R-7) without reading the live graph.
- Graph failure must never break evidence availability (I-4).
- Analytics/OLAP workloads never hit the graph — ClickHouse only (Spec FR-020).
- Candidate Graph (noisy), Evidence Graph, Semantic Graph, Temporal Graph, Infrastructure Graph are distinct projections (No-Single-Graph).