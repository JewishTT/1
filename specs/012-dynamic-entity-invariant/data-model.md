# Data Model: Dynamic Entity Invariant (spec 012)

Source of truth: `apps/shared/domain/graph_invariant.py` (pure stdlib, frozen
dataclasses, canonical JSON hashes). Field names below are the implemented ones.

## Kind 1 — `GraphInvariant` (`kind = "dynamic_invariant"`)

| Block | Type | Fields | Notes |
| --- | --- | --- | --- |
| identity | `InvariantIdentity` | `entity_id`, `stream_anchor`, `type_label`, `revision` | Anchor = genesis content address `evt-<record_hash>`; stable across re-versioning |
| lifecycle | `TemporalLifecycle` | `slices: tuple[TemporalSlice, ...]`, `state`, `active_slices` | Ordered, epoch-aligned; state = last slice's state |
| topology | `TopologicalState` | `degree`, `community`, `neighbor_signature`, `window_topology`, `tda_proxy` | Structural only (I-6); community `""` = honestly unknown |
| evidence | `EvidenceBlock` | `observation_count`, `observation_anchors`, `content_digests`, `assertion_ids` | Refs only (I-1/I-5) |
| links | `tuple[TypedLink, ...]` | `target_id` (`SO-…`), `relation`, `target_kind` | Sorted by `(relation, target_id, target_kind)`; ONLY path to static objects |
| provenance | `ProvenanceBlock` | `tenant_id`, `event_id`, `observation_id`, `stream_head`, `source_hashes`, `builder`, `schema` | I-12; `event_id = evt-<stream_head>` |
| derived | properties | `content_id` (`GI-<digest[:32]>`), `integrity_digest` | sha256 over canonical JSON; any input order ⇒ identical digest |

### `TemporalSlice` (one window of the life)

| Field | Meaning |
| --- | --- |
| `window_start` / `window_end` | Half-open `[start, end)`, epoch-aligned (`window_bounds`, UTC epoch anchor) |
| `state` | `LifecycleState`: NASCENT / GROWING / STABLE / DECAYING / DORMANT |
| `event_count` | Events in the window (0 for DORMANT) |
| `events_per_period` | count / window-days (0.0 for an empty slice — never fabricated) |
| `burstiness` | B = (σ/μ − 1)/(σ/μ + 1); `None` when < 2 events |
| `first_seen` / `last_seen` | `None` for dormant slices |

Lifecycle derivation (±10% band around previous count; deterministic):
`count == 0 → DORMANT`; `index == 0 → NASCENT`; `count > prev·1.1 → GROWING`;
`count < prev·0.9 → DECAYING`; else `STABLE`.

### Topology blocks

| Type | Fields | Notes |
| --- | --- | --- |
| `WindowTopology` | `window_start/end`, `neighbor_weights: ((id, w), …)` sorted by id, `community` | Lossless per-window weighted adjacency (ego-star) |
| `TDAProxy` | `window_start/end`, `h0_classes`, `ph0dm`, `weight_sum`, `structural_only=True` | Edge filtration `1/(1 + w)`; PH0 of the ego-star only |
| `TopologicalState` | `degree`, `community`, `neighbor_signature` (sorted union), `window_topology`, `tda_proxy` | Proxies align 1:1 with lifecycle slices |

### TDA input shapes (L3 contract)

- `to_tda_input(invariant) -> (node_ids: list[str], triples: [(i, j, w), …])` —
  ego-star, weights summed across windows (documented aggregation); node ids sorted.
- `window_tda_input(invariant, window_start)` — lossless per-window triples.
- `to_multiplex(invariant) -> tuple[MultiplexLayer, ...]` — one layer per lifecycle
  slice (dormant window ⇒ self-node, no edges), aligned 1:1 with `lifecycle.slices`.

## Kind 2 — `StaticObject` (`kind = "static_object"`)

| Field | Meaning |
| --- | --- |
| `object_id` | `SO-<content_sha256[:32]>` — identical bytes ⇒ identical id (I-11) |
| `media_type` | Descriptor media type (e.g. `text/plain`) — not content |
| `content_sha256` | Bare sha256 of the bytes (content address) |
| `byte_length` | Size in bytes |
| `captured_at` | Honest capture instant (tz-aware) or `None` — never fabricated |
| `source_uri` | Object-storage/S3 pointer where the bytes actually live (I-5) |

Descriptor key set is fixed (`kind, object_id, media_type, content_sha256,
byte_length, captured_at, source_uri`): **no payload field exists**, so content can
never leak into a projection. `integrity_digest` = sha256 over the canonical
descriptor JSON.

## Embedded vs linked (the ruling)

- **Embedded (flat blocks)**: identity anchors, windowed temporal slices + lifecycle,
  topology signature/proxies, evidence refs (counts, anchors, digests, assertion
  ids), provenance.
- **Linked (never embedded)**: static-object content (stays in object storage),
  co-mention facts (N-ary hyperedges — `domain.hypergraph`, never identity),
  evidence-dependent attribute values (versioned typed `Property`/valuation records
  referenced by the stream anchor; rebuildable I-12), the full relational graph
  (L2/Neo4j adjacency is the owner).

## Builder contract — `from_entity_stream`

Input: any sequence of mappings/objects exposing
`ts` (tz-aware), `kind`, `sequence`, `record_hash`, `observation_id`, `tenant_id`,
`payload` (e.g. `domain.dynamics.StreamRecord`). Behavior:

- rejects empty streams, tz-naive timestamps, tenant mismatch, mixed `entity_id` (I-6/I-12);
- dedups by stream hash (idempotent, I-11), sorts by `(ts, sequence, stream_hash)`;
- windows: `window` (default 7 days) epoch-aligned; middle gaps become DORMANT slices;
- neighbor/community hints read from `payload["neighbors"]` (`{id: weight}` or id
  list) and `payload["community"]`; first asserted community wins per window;
- type label from `payload["schema_name"]` when not passed explicitly.
