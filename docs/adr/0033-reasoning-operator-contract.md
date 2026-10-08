# ADR-0033 — Reasoning operator contract

**Status**: Accepted (Wave 0, ADR-025-06)
**Feature**: `025-context-reality-approximation-engine`
**Baseline**: v2 §30, Appendix H

## Context

025 computes with donated code (baseline §30.4) and with operators whose cost and failure
modes differ by orders of magnitude. Without a registration contract, three things rot
quietly:

1. **Replay breaks.** An operator whose output depends on an unversioned dependency cannot be
   reproduced, and the failure appears as a diff nobody can explain.
2. **Budgets are fiction.** An operator with no declared complexity or memory class cannot be
   scheduled against a 20 GB machine, so "bounded" becomes a hope.
3. **Donor code enters unexamined.** A donor's license, its isolation needs and its
   `confidence = 0.5`-style defaults arrive silently. `AGENTS.md` §2 requires a donor defect to
   be treated on transfer; that is impossible without a declared metadata surface.

## Decision

**1. Registration is the gate.** An operator may not run until it is registered with the full
metadata set. Registration validates: input/output contracts, `determinism_mode`,
`numeric_mode`, `complexity_class`, `memory_class`, `supports_incremental`, `supports_replay`,
`provenance_contract`, `license`, `isolation_requirements`, `safety_policy`, `cache_policy`.

`license` and `isolation_requirements` are **load-bearing**, not paperwork: they are the
mechanism by which donor code is cleared for entry.

**2. Determinism and numeric modes are declared, not assumed.**

```text
determinism_mode ∈ { EXACT, FIXED_POINT, FLOAT_QUANTIZED, NON_DETERMINISTIC(reason) }
numeric_mode     ∈ { EXACT, FIXED_POINT, FLOAT_QUANTIZED }
```

`NON_DETERMINISTIC` requires a reason string and forces the run to be recorded as
non-reproducible, which the acceptance gates treat as a defect, not a style.

**3. Seeds are arguments.** `run(input_view, parameters, seed)` takes a seed. It is derived per
ADR-0030, carried in the parameter fingerprint, and stored on the `ReasoningRun`. There is no
ambient RNG in the reasoning path.

**4. Fourteen-step execution protocol, normative.** From ADR-0029/0030, condensed:

```text
1  validate registration        8  allocate resource budget
2  validate input contract      9  execute operator
3  check inference policy      10  validate output contract
4  load declared dependencies  11  generate explanation trace
5  bind revision and branch    12  persist result + run record
6  bind regime + profile       13  emit event
7  bind policy, derive seed    14  expose result only after commit
```

Step 10 failure ⇒ `QUARANTINED`, **no world-model mutation**, run `FAILED`, error artifact
persisted, input stays replayable. Quarantine rather than partial-apply: a half-applied
operator result is how corrupt state enters a durable system.

**5. Explanation trace is mandatory.** `explain(result)` returns a structured trace, not a log
dump. An operator that cannot explain its output is not registrable — an unexplainable
inference cannot be audited, and an unauditable inference cannot be trusted at L3.

**6. Cache keys are tenant-scoped and complete.**

```text
(tenant_id, context_id, branch_id, operator_id, operator_version,
 input_digest, parameter_fingerprint, seed, policy_fingerprint)
```

A key without `tenant_id` is rejected at registration. Cache reads fail closed on tenant
mismatch exactly like storage. A cache that leaks across tenants leaks the exact content that
must not leak.

**7. Budget is an input.** Operators receive `ComputeBudget` and must report consumption.
Exhaustion returns partial results plus what was processed, what was not, what was truncated,
which candidates were pruned and why pruning was allowed. Silent truncation is forbidden.

**8. Failure taxonomy is preserved.** Operators distinguish the thirteen states of §44.
Converting everything to `UNKNOWN` is a contract violation.

**9. Operator classes are fixed.** The 21 classes of §30.3 including `INDEPENDENCE` (ADR-0036).
An operator that fits none of them is a modelling error, not a new class.

## Consequences

**Positive**

- Replay is enforceable by registration, not by discipline.
- Scheduling against a 20 GB machine becomes possible because memory class is known.
- Donor code is cleared before it runs, and its defects have somewhere to be recorded.

**Costs, accepted**

- Registration is boilerplate for every operator, including trivial ones. Accepted: the
  alternative is an untraceable inference.
- `NON_DETERMINISTIC` operators will fail acceptance gates. That is the intended pressure.

**Not changed**

- The tier structure (§31). Registration does not pick an operator; the planner does.

## Verification

- [ ] Unregistered operator cannot run; incomplete metadata is rejected with the missing
      field named.
- [ ] Operator with a floating dependency is refused a `MethodFingerprint`.
- [ ] `NON_DETERMINISTIC` requires a reason and is flagged in acceptance reporting.
- [ ] Step-10 failure leaves world state byte-identical to pre-run state.
- [ ] Two runs with the same seed and inputs produce identical output; different seeds
      produce a recorded difference.
- [ ] Cache key without `tenant_id` is rejected; cross-tenant cache read returns nothing.
- [ ] Budget exhaustion returns the five-part disclosure.
- [ ] Every operator returns a populated explanation trace.
- [ ] Donor adapters are registered, including license and isolation metadata.