# ADR-0012: Provenance

Status: Accepted
Date: 2026-09-07

## Context

Every claim, observation, candidate, and assertion must be traceable to its
source artifact and transform chain so we can measure source independence
(FR-015, T087), audit decisions (FR-029, T062), and rebuild projections (I-12).

## Decision

Make **provenance a first-class, mandatory field** on every domain object:
`source_id`/`artifact` → extractor + version → normalized form → candidate →
evidence link (with offsets) → assertion, carried immutably.

## Rationale

- Source Independence Engine (T087) operates on the citation/derivation graph
  that provenance materializes.
- Audit log (T062) and knowledge-quality gates (T085) require provenance to be
  attributable.
- Rebuildable projections (I-12) need exact transform provenance to re-derive
  state deterministically.
- FR-011/FR-014 mandate surface_form + offsets and extractor_version.

## Consequences

- Provenance is never dropped/mutated once an observation is committed (I-1).
- Adds storage cost; mitigations include compact stable ids + object-key refs.
- Downstream consumers must not fabricate provenance they didn't observe.
