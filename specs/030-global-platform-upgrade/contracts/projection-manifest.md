# Contract 06 — ProjectionManifest

**Feature**: `030-global-platform-upgrade`
**Governs**: every projection — graph, search, temporal, analytics, TDA, spatial.
**Enforces**: FR-070, FR-071, FR-076, FR-077, FR-078, FR-079, P9.

---

## Purpose

A projection is a **rebuildable way of looking at** canonical state. If it is destroyed, nothing is
lost. If it cannot be reproduced, it was never a projection — it was an undeclared authority.

The manifest is what makes that claim checkable.

---

## Shape

```text
ProjectionManifest
├── projection_id, projection_kind, tenant_id
├── source_event_offsets         { topic, partition, offset }
├── input_snapshot_digest
├── builder                     { id, version, container_digest }
├── parameters                  explicit — scale units, metric, window, complex, resolution
├── parameters_fingerprint
├── output_digest
├── status                      succeeded | partial | failed | stale | quarantined
├── rebuildable                 see R2
├── staleness                   { status, lag_events, stale_since }
├── output_derivation           what this projection derived, and from what
├── kill_switch                 operator/version routing pointer
└── created_at
```

---

## The eleven declarations [FR-070]

Every projection MUST state, in the registry and in each manifest:

1. **Purpose** — which query or analytic operation becomes cheaper or becomes possible.
2. **Upstream** — event types or source snapshots consumed.
3. **Source of data** — the canonical authority, plus tenant/scope keys.
4. **Fingerprints** — schema, code, model, config, parameters.
5. **Incremental path** — offset/checkpoint and how deltas are applied.
6. **Rebuild path** — full rebuild procedure and its expected cost.
7. **Deletion/retention/revocation** — what happens when source is deleted or access is revoked.
8. **Staleness** — how freshness is computed and surfaced.
9. **Error state** — partial / degraded behaviour, not just success.
10. **Idempotency and replay** — what happens on replay and on duplicate delivery.
11. **Kill switch** — how the projection is disabled and what falls back.

---

## Rules

### R1 — An unused `projection_id` is a defect

If the id is created and never used, either wire it or remove it. An id that exists only in a
manifest is decoration.

### R2 — `rebuildable: true` requires all three, tested

`rebuildable = true` is permitted **only** when:

- a durable source exists, **and**
- a checkpoint/incremental route exists, **and**
- a rebuild from source reproduces the recorded `output_digest`, **and that has been tested**

Otherwise `rebuildable = false` with the missing piece named.

### R3 — A silent full rebuild is a defect

A `rebuild()` that starts from offset zero while presenting itself as incremental is either fixed or
explicitly documented as the chosen cost model. It is never both.

### R4 — Failure never destroys evidence

A projection failure yields `status = failed` with a reason. It does not delete the source, mutate
canonical claims, or drop rows. Search-index outage does not destroy observations. A topological
worker crash does not delete facts (FR-079, spec §26.2).

### R5 — Stale cannot silently satisfy

A caller may accept staleness **only** through an explicit profile or policy. An obligation requiring
current data is not satisfied by a stale projection; it reports `blocked` / `stale`.

### R6 — Every feature traces to its input snapshot

An analytical feature references the snapshot digest, time window, parameters and derivation chain it
came from. A topological feature with no snapshot reference is not publishable.

---

## Family-specific requirements

### Graph

- Asserted and derived edges remain **distinguishable**. Derived edges carry rule id, derivation
  path, premise refs, interval semantics, invalidation and supersession (FR-072).
- **N-ary is preserved.** An n-ary co-occurrence fact keeps its incidence structure; a pairwise
  (clique) view is **opt-in** and carries an explicit derivation plus a warning about semantic loss
  (FR-073).
- Multi-edges, conflicting claims and open predicates are supported.
- Traversal enforces depth, fan-out, scope, time, tenant and budget, and **returns truncation
  metadata** plus the derivation path explaining why each candidate appeared (FR-074).

### Search

- Response carries: index revision, searched fields, applied filters, staleness, candidate-pool
  truncation state.
- An index document links to its exact observation/segment **and parse version**.
- Rebuild is idempotent. Deletion obeys policy. **Deleting an index document does not lose the
  evidence it pointed to** (FR-075).
- A hit is a candidate pointer, never admitted knowledge.

### Temporal

- Budget exhaustion is a **partial-result envelope** carrying processed counts and residual work —
  not an opaque exception, not a silently dropped tail.
- `CURRENT` / `AS_OF` / `INTERVAL` are three distinct dimensions (contract: data-model §4.2).
- Derived relations keep their source revisions and time conditions.

### TDA [FR-076]

| Required input | Why |
|---|---|
| Exact snapshot / invariant revision digest | reproducibility |
| Node set **including isolated nodes** | isolated vertices are mathematically required in H₀ |
| Edge types, direction and arity treatment | flag vs clique/VR complexes differ |
| Filtration scale **with units** | an unlabelled scale is not interpretable |
| Metric / distance choice and transforms | affects the complex |
| Complex constructor | flag / clique / VR / witness / incidence |
| Time window or sequence embedding | temporal filtration must use a real declared time, **not vertex index by accident** |
| Missingness and mixed-scale policy | refuse or stratify |
| Code + dependency fingerprint + deterministic parameters | reproducibility |

Required outputs: barcode/diagram artifact, Betti curves or supported features, window-level feature
series, robustness/sensitivity metadata, snapshot digest, evidence derivation.

**Explicitly tested behaviours**: edgeless graphs have defined H₀ behaviour; mixed or incomparable
scales are refused or stratified; topology never mutates identity or claim truth.

**A feature has a status and a stability estimate** — not a categorical claim of noise immunity.

### Spatial [FR-077]

Original geometry, geometry source span/ref, CRS, precision/accuracy estimate, valid/known time and
collection footprint are retained. Index version, resolution and geometry-normalisation method are
stored.

**An index cell must not imply precision finer than the source.** Spatial joins state their overlap
tolerance and uncertainty semantics. Changing resolution is a projection rebuild, not a mutation of
source truth.

### Analytics [FR-078]

Estimator + version, sample scope, sample size, confidence interval / uncertainty, missingness.

**Source-health metrics are maintained separately from real-world anomaly candidates.** A source
publishing less data may be a collection failure, not a regime shift. Collapsing the two turns an
operational fault into a world claim.

Online model state is checkpointed, replayable, or explicitly result-replay-only. Model updates are
versioned and auditable. A detection may trigger an obligation; policy and approval still govern
acquisition.

---

## Validation

| Check | On failure |
|---|---|
| All eleven declarations present | reject registration |
| `rebuildable = true` without a tested rebuild route | force `false` + missing piece named |
| Rebuild digest ≠ manifest `output_digest` | fail loudly |
| `staleness` absent | reject |
| `kill_switch` absent | reject |
| Feature without snapshot digest | reject publication |
| Projection failure deleted evidence | **release blocker** |
| Stale projection satisfied a freshness-requiring obligation | reject |
| n-ary fact silently expanded to clique | reject |
| Analytical feature without estimator/sample/uncertainty | reject |
| Source-health and world-anomaly metric merged | reject |