# ADR-0022: Indexed temporal relation derivation

Status: Accepted
Date: 2026-09-25
Feature: 015-worldline-reconstruction (T083-T090, D11)

## Context

`derive_temporal_relations` sorts events and then evaluates a nested loop over all pairs,
guarded by `max_events=512`, raising `WorldlineError` beyond it. Its semantics are
correct and well specified: ordering is decided on occurrence windows, overlapping
windows yield `overlaps`, disjoint windows yield `precedes`/`follows`, and declared
causes are labelled as declared rather than deduced.

The problem is not the semantics but the complexity. At the current bounded volumes it
is invisible; at the volumes exhaustive coverage actually produces — all partitions times
many pages times many URLs — it is a hard wall. Raising `max_events` would leave the
quadratic term intact, which is the actual limit.

## Decision

Keep `derive_temporal_relations` **unchanged and callable** as a reference
implementation, and add an indexed derivation as the production path:

- `precedes` / `follows` follow from a **single sort** by the canonical order key; they
  are produced by walking that sorted list, not by comparing pairs.
- `overlaps` comes from a **sweep line** over interval starts with an active-interval
  structure closed on interval end, so each event is compared only against events that
  actually overlap it.
- Declared causes resolve through a hash index that maps both record ids and event ids
  into event space.

Exceeding a configurable relation budget produces explicit, labelled degradation naming
what was not computed. It never raises and never truncates silently.

## Rationale

- Cost becomes proportional to actual overlap count rather than to `n²`, which is what
  makes honest full-history coverage usable.
- Retaining the pairwise version as a **test oracle** makes the optimization provably
  behaviour-preserving rather than a rewrite of already-proven semantics. Equivalence is
  asserted on randomized interval sets and on the full 10,000-event fixture.
- `max_events` becoming a soft budget removes a size-related failure mode that currently
  masquerades as a data problem.

## Consequences

- The oracle must not be deleted; it is test-only surface and production never calls it.
- Two derivation paths exist in one module, so the oracle is clearly marked as such.
- Interval bounds and the canonical order key must be present on every event for the
  sweep line to work; this constrains the event payload shape.
- Exceeding the budget is a reported, labelled outcome, so consumers must handle
  `degradation` rather than assuming a complete relation set.
