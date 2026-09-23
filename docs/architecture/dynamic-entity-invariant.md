# Dynamic Entity Invariant — the atomic entity as a graph-invariant

Spec: [`specs/012-dynamic-entity-invariant/`](../../specs/012-dynamic-entity-invariant/)
(spec.md, data-model.md). Implementation: `apps/shared/domain/graph_invariant.py`.
Tests: `apps/shared/tests/unit/domain/test_graph_invariant.py`.

## The ruling in one paragraph

Exactly two kinds of graph objects exist. A **dynamic invariant** (person, company,
site, channel, event) is the center of analysis — a *relational function of its
append-only life-stream*; it has temporality (windowed lifecycle), versions and
topology, and it changes only when new events arrive. A **static object** (document,
photo, conversation) is a content-addressed, immutable evidence leaf that carries no
own dynamics; invariants reach it only through typed links (`hasEvidence`, `depicts`,
`inConversation`). Identity comes exclusively from admission/resolution (I-6); the
invariant never decides identity.

## What every invariant contains (and what it does not)

A person-invariant, concretely:

| Block | Contains | Why it belongs here |
| --- | --- | --- |
| Identity | `entity_id`, genesis anchor `evt-<record_hash>`, type label, revision | Stable reference across re-versioning; changing it would break every projection |
| Lifecycle | Ordered epoch-aligned window slices: state (NASCENT/GROWING/STABLE/DECAYING/DORMANT), event counts, cadence (`events_per_period`), honest `burstiness` (None < 2 events), first/last seen | The temporal series itself — what TDA/kinetics consume; gaps are explicit DORMANT, never interpolated |
| Topology | Neighbor signature (sorted ids), per-window weighted adjacency, structural TDA proxies (`h0_classes`, `ph0dm`, `weight_sum`) | The ego-star an analyst sees; proxies are structural-only (I-6) and rebuildable |
| Evidence | Observation count, `obs-…` anchors, content digests, assertion ids | Traceability to raw evidence without moving bytes (I-1/I-5) |
| Provenance | tenant, `stream_head`, source hashes, builder/schema, content-addressed event id | Rebuildability proof (I-12): replay the log, get the same digest |
| Links | `SO-…` typed refs to static objects | The ONLY way to point at documents/photos/conversations |

Never inside the invariant: raw content (bytes live in object storage), co-mention
facts (they are N-ary hyperedges — `domain.hypergraph`), evidence-dependent
attribute values (versioned `Property`/valuation records referenced via the stream
anchor), and the full relational graph (that is the L2/Neo4j adjacency's job).

## Determinism & time

- Windows are epoch-aligned, half-open `[start, end)` — the same slicing for every
  entity, so per-window layers line up for multiplex-over-time analysis.
- `from_entity_stream` sorts by `(ts, sequence, stream_hash)`, dedups exact
  duplicates (I-11); the same event set in *any* order replays to a byte-identical
  `integrity_digest` (I-12).
- Empty streams are rejected; empty windows are DORMANT; missing numbers are `None`
  or `0.0` — never fabricated (I-3).

## TDA readiness

`to_tda_input` emits the documented adjacency shape `(node_ids, [(i, j, weight)])`
without importing projection code; `to_multiplex` emits lossless per-window layers
aligned 1:1 with lifecycle slices; `window_tda_input` gives one layer's triples. L3
computes persistence/features per window and stores **feature time series** in
ClickHouse — never "a TDA graph" (see `apps/projection/tda/`).

## Status

- Domain model, deterministic builder, TDA shapes: implemented, 28 unit tests green.
- Stream side (entities' life-stream → invariant, series projection): see
  [stream-processing.md](./stream-processing.md); CC temporality lane per spec 011.
