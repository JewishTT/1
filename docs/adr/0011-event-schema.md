# ADR-0011: Event schema

Status: Accepted
Date: 2026-09-07

## Context

Events flow acquisition → interpretation → admission → projection. We must have
an immutable, versioned, provenance-carrying event schema so projections are
rebuildable and cross-app domain types stay consistent.

## Decision

Define **immutable, versioned events** with mandatory provenance and
`event_id`/offsets, shared across apps via the shared domain layer
(`apps/shared/domain`, I-1/ObservationImmutable; T038–T043 projections).

## Rationale

- Immutability (I-1) is the foundation of projection rebuildability (I-12);
  events are never edited in place, only superseded/retracted (FR-016).
- Versioned schema with `schema_version` allows deterministic re-materialization.
- Provenance fields (source, extractor_version, offsets) satisfy FR-011/FR-014.
- Event IDs enable idempotent projection (I-11).

## Consequences

- Any schema change requires version bump + backfill/re-projection.
- New extractors must emit versioned, backward-compatible events.
- Transport never carries raw blobs (I-5); only metadata + object keys.
