# Platform audit

A verified snapshot of the platform's true state. Every number is derived from the tree; the section pages hold the detail. **Read this with its caveats**: the model proves *structure, reachability and maturity* -- not correctness, not runtime behaviour.

## Scale

| Metric | Value |
|---|---|
| Components | 17 |
| Python / TypeScript / Rust modules | 1017 / 266 / 16 |
| Resolved import edges | 2819 |
| HTTP routes / routers | 182 / 33 |
| Test files / functions | 344 / 5316 |
| Evidence facts (static) | 4382 |

## Implementation maturity

| Status | Modules |
|---|---|
| IMPLEMENTED | 548 |
| PRIMITIVE | 0 |
| STUB | 0 |
| NOT_IMPLEMENTED | 0 |
| DECLARATION_ONLY | 18 |
| PACKAGE_INIT | 91 |
| MIGRATION | 19 |
| TEST | 341 |

See [maturity.md](maturity.md).

## Reachability

| Status | Modules |
|---|---|
| PRODUCTION | 408 |
| TEST_ONLY | 146 |
| ORPHAN | 122 |
| TEST | 341 |

See [reachability.md](reachability.md) for the entrypoints and the test-only/orphan lists.

## Golden path readiness

| Status | Capabilities |
|---|---|
| READY | 34 |
| PARTIAL | 0 |
| STUB | 0 |
| TEST_ONLY | 7 |
| ORPHAN | 3 |
| MISSING | 0 |

See [golden-path.md](golden-path.md) for the capability map and the build plan.

## Gaps (machine-checked)

**9** open, machine-checked gaps. See [gaps.md](gaps.md).

## Event coverage

100 catalogued event types across 30 lanes; 26 have a likely producer line; **29** are referenced by no file outside the catalog.

Unreferenced event types (catalogued, but no producer or consumer string):

- `acquisition.failed`, `analytics.projected`, `audit.access`, `cc.capture.series`, `cc.captures_pulled`, `cc.observations_extracted`
- `cc.plan_ready`, `cc.series_projected`, `claim.assessed`, `discovery.seed`, `entity.version_created`, `evidence.independence_fused`
- `evidence.link_created`, `feedback.entity`, `feedback.system`, `governance.replayed`, `graph.snapshot_created`, `graph.snapshot_rebuilt`
- `investigation.resumed`, `observation.changed`, `observation.duplicate`, `ontology.registered`, `policy.budget_exceeded`, `projection.completed`
- `replay.stream`, `review.replayed`, `tda.feature.series`, `temporal.materialization.progress`, `zero_layer.enrichment`

## Rust crates

9 crates, **0 runnable** (has a `[[bin]]` or `src/main.rs`). A crate with neither builds only an rlib: nothing outside its own tests can run it, so it is not a worker.

| Crate | Runnable | Bin | main.rs |
|---|---|---|---|
| `acquisition` | **no** | False | False |
| `cognitive-acq-content-router` | **no** | False | False |
| `cognitive-acq-contracts` | **no** | False | False |
| `cognitive-acq-discovery` | **no** | False | False |
| `cognitive-acq-dispatcher` | **no** | False | False |
| `cognitive-acq-frontier` | **no** | False | False |
| `cognitive-acq-observation-gate` | **no** | False | False |
| `cognitive-acq-worker-browser` | **no** | False | False |
| `cognitive-acq-worker-http` | **no** | False | False |

## Spec ↔ capability traceability

Capabilities linked to a spec when the capability's module is cited by that spec's (spec-numbered) modules. A spec with no linked capability is either unmapped or has no capability behind it.

| Spec | Capabilities |
|---|---|
| `005-donor-core-subsystems` | `identity-resolution` |
| `007-deterministic-entity-extraction-stack` | `interpretation-lane` |
| `010-zero-layer-contact-harvesting` | `websearch` |
| `012-dynamic-entity-invariant` | `graph-invariant` |
| `016-relation-evidence-graph-fabric` | `evidence-context`, `projection-graph` |
| `024-context-driven-continuous-intelligence` | `durable-dlq`, `layer-boundaries` |
| `030-global-platform-upgrade` | `canonical-serialisation` |

## Test-only capabilities

Declared capabilities that only tests reach -- a live risk if production is believed to use them.

| Capability | Module |
|---|---|
| `durable-dlq` | `apps/shared/events/dlq_durable.py` |
| `admission-decisions` | `apps/admission/resolution/decision_store.py` |
| `temporal-filter` | `apps/science/context/temporal_filter.py` |
| `donor-registry` | `donors/registry.yaml` |
| `layer-boundaries` | `apps/shared/tools/layer_boundaries.py` |

## Ownership (heuristic — competing writers are candidates, not verdicts)

`6` objects have competing writers and `8` have no writer found. The owner map is built from textual write-site heuristics (reads and ORM imports are counted), so each row is a candidate to verify, not a proven defect. See [ownership.md](ownership.md).

## Spec bookkeeping behind the code

Specs whose task list shows 0 checked but whose number is cited by real modules -- the file understates the code.

| Spec | Tasks | Modules citing it |
|---|---|---|
| `008-discovery-search-fabric` | 0/40 | 2 |
| `017-semantic-fabric` | 0/30 | 1 |
| `018-world-substrate` | 0/30 | 4 |
| `021-entity-relation-extraction-finalization` | 0/94 | 1 |
| `023-acquisition-integration-searxng` | 0/214 | 3 |
| `024-context-driven-continuous-intelligence` | 0/168 | 24 |
| `030-global-platform-upgrade` | 0/152 | 24 |
| `032-global-upgrade-execution` | 0/84 | 8 |
| `034-person-research-case` | 0/76 | 18 |
