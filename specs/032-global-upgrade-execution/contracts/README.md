# Contracts Index — Feature 032

**Feature**: `032-global-upgrade-execution`

This directory holds the **delta contracts** that this feature adds or constrains. It is
deliberately not a second contract set: Feature `030-global-platform-upgrade` already owns the
canonical definitions of `OperatorResult`, `EvidenceSpanRef`, `stage-outcome`, `obligation`,
`context-revision`, `projection-manifest` and `errors`. Duplicating them here would create exactly
the second authority the blueprint forbids.

## Precedence

1. `specs/030-global-platform-upgrade/contracts/` — **canonical definitions** of the shared typed
   boundaries. Unchanged by this feature.
2. This directory — **constraints and new contracts** that this feature adds on top of those
   definitions, or contracts that 030 does not define at all.
3. Where a rule below tightens a rule in 030, the tighter rule governs and the difference is stated
   in the contract's "Delta against 030" section.

## Index

| # | Contract | Status | Governs | Primary requirements |
|---|---|---|---|---|
| 01 | [`evidence-seam.md`](./evidence-seam.md) | **new** | The one `ArtifactSink` / Observation Gate path every executor crosses | FR-001…FR-005, SC-002, SC-004 |
| 02 | [`acquisition-task.md`](./acquisition-task.md) | **new** | The durable work order binding context, obligation, capability, policy and budget | FR-008, FR-009 |
| 03 | [`operator-result.md`](./operator-result.md) | delta | The mandatory fields 032 adds to 030's envelope | FR-014, FR-015 |
| 04 | [`evidence-span.md`](./evidence-span.md) | delta | Producer-side typing and the no-synthetic-offset rule | FR-016…FR-018 |
| 05 | [`conflict-record.md`](./conflict-record.md) | **new** | Contradiction as a first-class record with status and reasons | FR-029…FR-032 |
| 06 | [`resolution-decision.md`](./resolution-decision.md) | **new** | Append-only identity and conflict decisions, and their proposals | FR-033, FR-034, FR-028 |
| 07 | [`research-obligation.md`](./research-obligation.md) | delta | Obligation ≠ task, acceptance predicates, satisfaction evidence | FR-048, FR-049, FR-053 |
| 08 | [`projection-manifest.md`](./projection-manifest.md) | delta | The fields every projection must expose to be trustworthy | FR-006, SC-009 |
| 09 | [`donor-registry.md`](./donor-registry.md) | **new** | The registry entry and the ten-condition promotion gate | FR-038…FR-045, SC-010 |

## Universal rules

These are inherited from 030 and are not restated in each file:

- tenant scope is part of every key; no cross-tenant reference is admissible;
- logical identity, content digest, event identity and revision sequence are four separate fields;
- content-derived ids are stable for equivalent canonical content;
- unknown is `null`, never a default — a missing timestamp is not `now()`, a missing estimate is not `0`;
- enums are closed for this platform's workflow states and open for the world's types and predicates;
- no contract may be satisfied by a fabricated value;
- every status is distinguishable from every other status.

## Versioning

Contract version is `MAJOR.MINOR`. A MAJOR change removes a field, narrows a type, changes a value's
meaning, or makes an optional field required. A MINOR change is additive. Consumers must tolerate
unknown fields and treat an unknown enum value as *unrecognised — preserve, do not reject* unless
they are the designated authority for that vocabulary.

A schema change without a compatibility check fails CI. A delta contract may not relax a canonical
contract from 030; it may only tighten it.
