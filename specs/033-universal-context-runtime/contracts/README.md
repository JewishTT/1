# Contracts — Feature 033

**Feature**: `033-universal-context-runtime`

These contracts define the runtime's own typed boundaries. They sit **above** the evidence and claim
contracts owned by Features 030 and 032, and they must not duplicate them: a context layer that
redefines what a claim is has created a second authority.

## Precedence

1. `specs/030-global-platform-upgrade/contracts/` and `specs/032-global-upgrade-execution/contracts/`
   — the evidence, span, conflict, identity and projection boundaries.
2. This directory — the context, abstraction, capability, assembly, memory, API and completion
   boundaries.
3. Where a rule here tightens a rule below it, the tighter rule governs.

## Index

| # | Contract | Governs | Primary requirements |
|---|---|---|---|
| 01 | [`context-frame.md`](./context-frame.md) | The versioned snapshot of what is being understood | FR-003, FR-004, FR-005, FR-009 |
| 02 | [`context-element.md`](./context-element.md) | The open-typed content envelope and its relations | FR-006, FR-007, FR-008 |
| 03 | [`abstraction-manifest.md`](./abstraction-manifest.md) | Accountability for every upward representational step | FR-010…FR-014 |
| 04 | [`capability-manifest.md`](./capability-manifest.md) | The registry that replaces hard-coded tool names | FR-030…FR-036 |
| 05 | [`context-assembly-manifest.md`](./context-assembly-manifest.md) | The inspectable snapshot given to a model or solver | FR-040…FR-045 |
| 06 | [`completion-report.md`](./completion-report.md) | The terminal accounting of an investigation | FR-055…FR-058 |
| 07 | [`memory-layers.md`](./memory-layers.md) | Nine scoped memories with independent rules | FR-052…FR-054 |
| 08 | [`api-and-events.md`](./api-and-events.md) | Typed resources, honest long-running work, canonical envelopes | FR-059…FR-065 |
| 09 | [`model-gateway.md`](./model-gateway.md) | The common contract over every model provider | FR-066…FR-069 |

## Universal rules

Inherited from 030 and 032 and binding here:

- tenant scope in every key, no cross-tenant reference;
- logical identity, content digest, event identity and revision sequence are four separate fields;
- unknown is `null`, never a default;
- closed for this platform's workflow states, open for the world's types and predicates;
- no contract may be satisfied by a fabricated value;
- every status is distinguishable from every other status.

Additional to the context layer:

- **a manifest is not optional** — an abstraction, an assembly, a completion and a capability all
  carry one, and a missing manifest is a contract violation, not a missing nicety;
- **a reference is not a copy** — frames, elements and assemblies refer to state by id and revision,
  so a stale copy cannot become a second truth;
- **a permission class is singular** — an operator declares one class and receives only that.

## Versioning

`MAJOR.MINOR`, as in 030/032. Consumers tolerate unknown fields. An unknown enum value is
*unrecognised — preserve, do not reject* unless the consumer is the designated authority for that
vocabulary. A schema change without a compatibility check fails CI. A contract here may tighten a
lower-layer contract; it may never relax one.
