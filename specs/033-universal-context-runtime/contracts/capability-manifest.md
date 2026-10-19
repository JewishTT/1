# Contract 04 — `CapabilityManifest`

**Feature**: `033-universal-context-runtime`
**Governs**: how a function becomes available to the system.
**Enforces**: FR-030…FR-036; blueprint §20.

---

## Why this contract exists

§20.1 gives the reason in its title: *"Capability вместо hard-coded tool names."* A planner that
knows tool names cannot be extended without editing the planner. A planner that knows capabilities
can accept a new provider by registering it.

The manifest is also the permission boundary. An operator declares one permission class and receives
only that. This is what prevents a universal runtime from becoming a universal privilege.

---

## Shape

```text
CapabilityManifest
├── id                        REQUIRED   e.g. semantic.relation.extract
├── version                   REQUIRED   semantic version
├── input_schema              REQUIRED   schema id + version
├── output_schema             REQUIRED   schema id + version
├── accepts[]                 REQUIRED   typed input kinds
├── emits[]                   REQUIRED   typed output kinds
├── preconditions[]           REQUIRED   e.g. evidence_is_available, tenant_policy_allows
├── constraints
│   ├── deterministic         REQUIRED   deterministic | seeded | non_deterministic | partial
│   ├── network_access        REQUIRED   none | allowlisted | controlled
│   ├── max_payload_bytes     REQUIRED
│   └── limitations[]         OPTIONAL   languages, formats, sizes
├── quality
│   ├── eval_suite            REQUIRED
│   └── minimum_gate          REQUIRED   a threshold, or `null` with a reason
├── execution
│   ├── runtime               REQUIRED
│   ├── timeout               REQUIRED
│   └── retry_policy          REQUIRED
├── governance
│   ├── owner                 REQUIRED
│   ├── license_ref           REQUIRED
│   ├── model_data_manifest   OPTIONAL
│   └── enabled_by_default    REQUIRED   default false for anything new
├── observability
│   └── metrics[]             REQUIRED   at least latency, failure rate, coverage
└── permission_class          REQUIRED   READ | DERIVE | PROPOSE | DECIDE |
│                                        WRITE_EXTERNAL | ADMIN
```

## Shape — the invocation

```text
OperatorRequest
├── typed input refs          REQUIRED
├── context_snapshot_ref      REQUIRED   frame id + revision
├── effective_policy          REQUIRED   the resolved policy, not a policy id alone
├── budget + deadline         REQUIRED
├── idempotency_key           REQUIRED
└── requested_output_contract REQUIRED

OperatorResult
├── status                    REQUIRED
├── typed outputs             REQUIRED
├── provenance                REQUIRED
├── input_digests[]           REQUIRED
├── output_digest             REQUIRED
├── operator_version          REQUIRED
├── runtime_version           REQUIRED
├── model_version             CONDITIONAL
├── warnings[]                OPTIONAL
├── coverage                  REQUIRED
├── resource_costs            REQUIRED
├── emitted_candidates[]      OPTIONAL
└── continuation_ref          OPTIONAL
```

---

## The six permission classes

| Class | May do | May never do |
|---|---|---|
| `READ` | retrieve within authorised scope | write anything |
| `DERIVE` | create a derived artifact | write canonical state |
| `PROPOSE` | emit a proposal | commit a decision |
| `DECIDE` | commit within its authority | exceed that authority |
| `WRITE_EXTERNAL` | act outside the platform | act without grant, confirmation and idempotency |
| `ADMIN` | change runtime, access, migrations, policy | run in the same plane as everything else |

An operator declares exactly one. A plugin that "needs" two is two plugins.

---

## Normative rules

### R1 — Selection by capability, then provider

The planner resolves `accepts`/`emits`/constraints first, then picks a provider. Replacing a provider
does not change the `ContextDefinition` or the downstream contract (FR-031, SC-004).

### R2 — Hard filters precede scoring

Policy, purpose, scope, tenant and compatibility are filters. Only after them does cost and quality
optimise. An LLM score alone never selects a capability (FR-036).

### R3 — The gate is real

A capability below its quality gate is either refused or explicitly flagged as degraded. A gate that
is recorded but never consulted is decoration.

### R4 — Default off

`enabled_by_default: false` is the default for new capabilities. Enabling is a policy decision with
an owner, not a convenience.

### R5 — No ambient write privilege

The invocation carries references and a policy, never a database handle or a writable store. This is
enforced by the runtime, not by convention (FR-033).

### R6 — Nothing is loaded by name alone

A capability is resolved by manifest, version and schema compatibility. A call by string name against
an unregistered implementation is refused.

### R7 — The gap is a result

If no capability satisfies the requirement, the planner emits a durable **capability gap**: what was
needed, which contract it would have to satisfy, and what is missing. Substituting a weaker tool
silently is forbidden.

### R8 — Health is a first-class signal

`health()` reports availability, latency and error class. A capability that is registered but
unhealthy is not selected as if healthy.

---

## Prohibitions

- A tool called by hard-coded name.
- A provider swap that changes the context or output contract.
- A capability with two permission classes.
- A capability enabled by default without an owner decision.
- A missing capability silently satisfied by a worse one.
- A quality gate recorded but not enforced.

---

## Tests

| Test | Asserts |
|---|---|
| `tests/contract/test_capability_manifest.py::test_single_permission_class` | R4 |
| `tests/integration/test_provider_swap_invariance.py` | R1, SC-004 |
| `tests/security/test_derive_cannot_write.py` | R5 |
| `tests/integration/test_capability_gap.py` | R7 |
| `tests/integration/test_policy_before_score.py` | R2 |
