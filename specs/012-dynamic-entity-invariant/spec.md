# Feature Specification: Dynamic Entity Invariant

**Feature Branch**: `012-dynamic-entity-invariant`

**Created**: 2026-09-23

**Status**: Implemented — domain model + deterministic builder + unit/contract tests
(`apps/shared/domain/graph_invariant.py`, `apps/shared/tests/unit/domain/test_graph_invariant.py`).
Stream bindings and documentation: `docs/architecture/stream-processing.md`,
`docs/architecture/dynamic-entity-invariant.md`.

## Context & Scope

This feature answers the product question: *what exactly IS an atomic entity, what
does its graph-invariant contain, and what is linked instead of embedded?*

The answer is product-locked to **exactly two kinds** of graph objects:

1. **DYNAMIC INVARIANT** (`GraphInvariant`) — a person, company, domain, channel or
   event: the *center of analysis*. Stream-anchored identity, temporality/lifecycle
   (windowed, deterministic), versions (revision), topology (per-window neighbor
   signature + structural TDA proxies). The invariant is a **relational function of
   the append-only event log**: same events ⇒ byte-identical projection
   (`integrity_digest`), and `state_at(T)` is replayable.
2. **STATIC OBJECT** (`StaticObject`) — a document, photo or conversation: a
   content-addressed, immutable **evidence leaf** (I-1). It is never a dynamic
   center and has no own dynamics beyond its descriptor. Invariants reach it only
   through **typed links** (`hasEvidence` / `depicts` / `inConversation`).

**Out of scope**: identity/merge decisions (admission + entity resolution own those,
I-6), full L2 adjacency maintenance (Neo4j projection), live Flink bindings.

## User Scenarios & Testing

### User Story 1 — One entity, one invariant (P1)

An analyst inspects an entity: sees its canonical anchors, its windowed lifecycle
(NASCENT → GROWING → STABLE → DECAYING → DORMANT), its topology signature, and its
evidence anchors — all rebuilt deterministically from the entity's life-stream.

**Independent test**: feed `entity.stream.appended` records (any order, with exact
duplicates); assert byte-identical `as_dict()`/`integrity_digest`, correct slice
bucketing and an explicit DORMANT slice for a mid-stream gap.

### User Story 2 — TDA-ready per-window inputs (P1)

L3 (TDA) consumes `to_tda_input` (ego-star triples `(node_ids, [(i, j, w)])`) and
`to_multiplex` (lossless per-window layers aligned 1:1 with lifecycle slices) and
stores only **feature series** (barcodes/landscapes/PH0DM) — never "a TDA graph".

**Independent test**: multi-window stream with neighbor hints; assert shape,
weight merge across windows, dormant window ⇒ self-node with no edges.

### User Story 3 — Evidence stays linked, never embedded (P2)

The invariant carries only `SO-…` refs, digests, observation counts and assertion
ids; document/photo/conversation **content never enters the model** (I-5), and the
serialized projection never contains the raw text.

**Independent test**: attach a secret-bearing document; assert the secret is absent
from `as_dict()`, the descriptor key set is fixed, and the link appears as a typed
edge with the `SO-` target id.

## Requirements

- **FR-001** Two-kind boundary: `dynamic_invariant` vs `static_object`; no third kind.
- **FR-002** Identity stability: identity block (entity_id, genesis `stream_anchor`
  = `evt-<record_hash>`, type label) never changes as events append; only `revision`
  and the provenance head move.
- **FR-003** Epoch-aligned, half-open windows `[start, end)`; empty windows in the
  middle of a life are explicit DORMANT slices (never skipped, never interpolated).
- **FR-004** Lifecycle states derived deterministically: NASCENT / GROWING / STABLE /
  DECAYING / DORMANT, with a ±10% band around the previous slice's count.
- **FR-005** Honest cadence: `events_per_period` is count/window; `burstiness`
  follows B = (σ/μ − 1)/(σ/μ + 1) and is `None` below two events — no fabricated numbers (I-3).
- **FR-006** Topology: sorted neighbor signature, per-window weighted adjacency, and
  structural-only TDA proxies (h0_classes, ph0dm, weight_sum) with
  `structural_only = True` (I-6).
- **FR-007** Evidence block: refs only — observation count/anchors, content digests,
  assertion ids (I-1/I-5).
- **FR-008** Typed links are the ONLY path from an invariant to a static object.
- **FR-009** Provenance block on every projection: tenant_id, stream_head (sha256 over
  ordered source hashes), source_hashes, builder/schema, content-addressed event_id
  (`evt-<hash>`) — rebuildability proof (I-12).
- **FR-010** Determinism & idempotency: any input order (plus exact duplicates)
  replays to a byte-identical digest; duplicate records are deduped (I-11).
- **FR-011** Honest emptiness: an empty stream is rejected — an identity must come
  from somewhere (I-3); tz-naive timestamps and tenant/entity mixing are rejected.
- **FR-012** TDA input shapes reproduce `AdjacencyView.to_tda_input` without
  importing projection code; per-window form is lossless (`to_multiplex`).

## Acceptance

`apps/shared/tests/unit/domain/test_graph_invariant.py` — determinism under reorder
and duplicates, epoch-aligned window arithmetic, lifecycle derivation across a
dormant gap, content-addressed static objects with fixed descriptor keys,
embedded-vs-linked boundary (secret text never serialized), TDA triple shape and
multiplex alignment. Full suite green (28 tests).

## Constitution alignment

I-1 (immutable leaves), I-3 (no fabrication: empty ⇒ empty/`None`/DORMANT), I-5
(refs-only; blobs stay in object storage), I-6 (identity only from resolution; TDA
is structural), I-11/I-12 (idempotent, content-addressed, rebuildable). L2 stores
current relational state; L3 stores feature time series — this module is the domain
shape both consume.
