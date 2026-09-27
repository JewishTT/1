# Quickstart: Relation & Evidence Graph Fabric

**Feature**: `016-relation-evidence-graph-fabric`
**Status**: Worked, runnable guide. The modules and names below are the *required*
implementation surface from [data-model.md](./data-model.md) and
[contracts/service-contracts.md](./contracts/service-contracts.md). Where they do not exist
yet, the snippet fails — that failure is the point.

Every numbered section is a short, self-contained Python block. The blocks are meant to be
pasted into a REPL or a scratch file, not to be run as a suite.

**How to run them.** `apps/shared/domain` is importable as the top-level `domain` package
from any app that depends on `cognitive-shared`:

```bash
# domain.* snippets (sections 1-7)
uv run --project apps/shared python your_scratch.py

# graph.* snippets (section 8) — apps/projection ships the path_shim that puts
# apps/shared ahead of the conflicting top-level `domain` in control-plane
uv run --project apps/projection python your_scratch.py
```

Inside a projection module the shim is imported explicitly, mirroring the existing files
(`abstraction.py`, `neo4j.py`, `snapshot.py`):

```python
import path_shim  # noqa: F401 - ensure apps/shared precedes conflicting dirs
```

A scratch script run from the repo root does **not** need it; add
`import path_shim  # noqa: F401` at the top if a `domain` import resolves to the wrong
package.

---

## Prerequisites

- Windows PowerShell 7+, Git, Python 3.11+, `uv`, Node.js 20+.
- A feature branch `016-relation-evidence-graph-fabric`.
- Accepted ADRs: `docs/adr/0023-relation-identity-and-arity.md` and
  `docs/adr/0024-claim-and-context-persistence.md`. The identity scheme and the
  identity/revision split are governance-gated; the code does not land before them.
- For section 9 only: no network, no PostgreSQL, no Docker. Every offline suite runs with
  the stack stopped. Section 9's migration test is the one exception, and it self-skips
  without a reachable database — a skip there is expected, not a pass.
- Local, non-production credentials only.

## 1. Verify the identity scheme

128-bit truncated SHA-256, arity-aware canonicalisation. A directed relation and its
inverse must not share an id; an undirected pair must.

```python
from domain.relation_identity import (
    RelationArityMode,
    digest128,
    logical_relation_id,
)

DIRECTED = RelationArityMode.DIRECTED
UNDIRECTED = RelationArityMode.UNDIRECTED

ab = logical_relation_id(DIRECTED, "works_for", ["P1", "O1"])
ba = logical_relation_id(DIRECTED, "works_for", ["O1", "P1"])
assert ab != ba, "directed relation collapsed with its inverse"

u1 = logical_relation_id(UNDIRECTED, "co_occurs_with", ["P1", "O1"])
u2 = logical_relation_id(UNDIRECTED, "co_occurs_with", ["O1", "P1"])
assert u1 == u2, "undirected relation did not collapse"

assert len(digest128("x")) == 32, "identity is not 128-bit truncated SHA-256"
print(ab, u1)
```

## 2. Build a relation claim

`RelationClaimService` is the only thing that mints ids. It refuses to mint a claim with no
evidence context.

```python
from datetime import datetime, timezone

from domain.relation_claim import (
    EvidenceGrade,
    RelationClaim,
    RelationClaimService,
    RelationContractError,
    RelationStatus,
)
from domain.relation_identity import RelationArityMode

svc = RelationClaimService()
claim = svc.claim(
    tenant_id="t1",
    relation_type="works_for",
    arity_mode=RelationArityMode.DIRECTED,
    participants=("P1", "O1"),
    context_ref="CX-" + "a" * 32,
    evidence_refs=("ev-1",),
    observation_refs=("obs-1",),
    valid_from=datetime(2017, 1, 1, tzinfo=timezone.utc),
    extraction_version="ext-1",
    ontology_version="onto-1",
)

print(claim.relation_id, claim.logical_relation_id, claim.revision_number)
assert claim.revision_number == 1
assert claim.status is RelationStatus.ACTIVE
assert claim.evidence_grade in tuple(EvidenceGrade)

# publication count and independent source count are separate, never one number
assert claim.publication_count == 1
assert claim.independent_source_count == 0

try:
    svc.claim(
        tenant_id="t1",
        relation_type="works_for",
        arity_mode=RelationArityMode.DIRECTED,
        participants=("P1", "O1"),
        context_ref="",
    )
except RelationContractError as exc:
    print("refused, as required by I-12:", exc)
```

## 3. Revise it (identity vs revision)

A corrected validity window is a **new revision of the same relation**, not a second
unrelated relation. Same `logical_relation_id`, new `relation_id`.

```python
rev2 = svc.next_revision(
    claim,
    valid_to=datetime(2022, 12, 31, tzinfo=timezone.utc),
    observation_refs=("obs-1", "obs-2"),
)

assert rev2.logical_relation_id == claim.logical_relation_id
assert rev2.relation_id != claim.relation_id
assert rev2.revision_number == claim.revision_number + 1
assert rev2.supersedes == claim.relation_id
assert rev2.publication_count == 2

# the prior revision is untouched and still queryable (I-3)
assert claim.valid_to is None
print(claim.relation_id, "->", rev2.relation_id, "under", claim.logical_relation_id)
```

## 3b. Prove direction matters

The frontend currently normalises every edge through `min`/`max`, which is correct for
`co_occurrence` and wrong for `works_for`. This shows the collapse the identity scheme is
built to prevent.

```python
AB = ("P1", "O1")
BA = ("O1", "P1")

# what the identity scheme does
assert logical_relation_id(DIRECTED, "works_for", AB) != logical_relation_id(DIRECTED, "works_for", BA)
assert logical_relation_id(UNDIRECTED, "co_occurs_with", AB) == logical_relation_id(UNDIRECTED, "co_occurs_with", BA)

# what the current frontend edge builder does — the defect
current_frontend_id = lambda a, b, kind: f"e:{min(a, b)}|{max(a, b)}|{kind}"
assert current_frontend_id(*AB, "works_for") == current_frontend_id(*BA, "works_for")

# what the read path does today — InMemoryGraphStore.neighbors unions both directions
# and therefore discards direction even though it is stored on write
from graph.abstraction import GraphEdge, InMemoryGraphStore

store = InMemoryGraphStore()
for ref in ("P1", "O1"):
    store.write_node(GraphNode(node_id=ref, node_type="Entity"), {"event_id": "e1", "observation_id": "obs-1"})
store.write_edge(
    GraphEdge(edge_type="works_for", source="P1", target="O1"),
    {"event_id": "e1", "observation_id": "obs-1"},
)
assert "O1" in store.neighbors("P1", "works_for")   # direction must be explicit now
```

## 4. Build an evidence context

The frame is frozen and content-addressed, so two independently constructed identical
frames share a `context_id`.

```python
from domain.evidence_context import (
    ContextCompleteness,
    ContextTrustState,
    EvidenceContext,
    InMemoryContextResolver,
)

frame = EvidenceContext(
    tenant_id="t1",
    investigation_id="inv-1",
    observation_id="obs-1",
    source_id="src-1",
    document_id="doc-1",
    segment_id="seg-1",
    source_family="wire-uk",
    independence_group="wire-uk-2024",
    extraction_version="ext-1",
    ontology_version="onto-1",
    completeness=ContextCompleteness.COMPLETE,
    trust_state=ContextTrustState.ATTESTED,
)

# a different construction path, identical content
same = EvidenceContext(
    source_id="src-1",
    source_family="wire-uk",
    independence_group="wire-uk-2024",
    observation_id="obs-1",
    document_id="doc-1",
    segment_id="seg-1",
    extraction_version="ext-1",
    ontology_version="onto-1",
    tenant_id="t1",
    investigation_id="inv-1",
    completeness=ContextCompleteness.COMPLETE,
    trust_state=ContextTrustState.ATTESTED,
)
assert frame.context_id == same.context_id, "content address is not deterministic"

try:
    frame.tenant_id = "t2"          # frozen: mutation raises, it does not alter
except Exception as exc:
    print("frame is frozen:", type(exc).__name__)

registry = InMemoryContextResolver()
context_id = registry.register(frame)
assert registry.register(frame) == context_id          # idempotent on context_id
assert registry.resolve(context_id) == frame
assert registry.resolve("CX-unknown") is None          # no default substitution
```

## 5. Validate: one failure per layer

Seven layers, always reported, graded verdict, never a boolean.

```python
import dataclasses

from domain.context_validation import ValidationLayer, ValidationVerdict, ValidationWorld, validate
from domain.relation_claim import RelationClaim
from domain.relation_identity import RelationArityMode
from domain.relation_schema import RelationSchema, RelationSchemaRegistry, TemporalSemantics

schemas = RelationSchemaRegistry()
schemas.register(
    RelationSchema(
        relation_type="works_for",
        arity_mode=RelationArityMode.DIRECTED,
        allowed_subject_classes=frozenset({"PERSON"}),
        allowed_object_classes=frozenset({"ORGANIZATION"}),
        temporal_semantics=TemporalSemantics.REQUIRED_INTERVAL,
        admission_rule_id="default-assert",
        schema_version="1",
    )
)
world = ValidationWorld(
    schemas=schemas,
    contexts=registry,
    admitted_entity_ids=frozenset({"P1", "O1", "DOC1"}),
    known_entity_ids=frozenset({"P1", "O1", "DOC1"}),
    active_ontology_versions=frozenset({"onto-1"}),
    known_ontology_versions=frozenset({"onto-1"}),
)

ok = validate(frame, claim, world)
assert len(ok.layers) == 7, "not all seven layers reported"
assert all(isinstance(layer, ValidationLayer) for layer in ok.layers)
print(ok.verdict, [f"{k}={v}" for k, v in ok.layers.items()])

# a schema violation, citable and reported
wrong_class = svc.claim(
    tenant_id="t1",
    relation_type="works_for",
    arity_mode=RelationArityMode.DIRECTED,
    participants=("DOC1", "O1"),
    context_ref=context_id,
    extraction_version="ext-1",
    ontology_version="onto-1",
    valid_from=datetime(2020, 1, 1, tzinfo=timezone.utc),
)
bad = validate(frame, wrong_class, world)
codes = {r.code for r in bad.reasons}
assert bad.verdict is ValidationVerdict.INVALID
assert "schema_subject_class_not_allowed" in codes, codes
assert bad.layers[ValidationLayer.STRUCTURAL].value == "passed"
assert len(bad.layers) == 7            # the earlier pass is still visible

# an unregistered relation type is UNDERDETERMINED, never INVALID, and is preserved
unregistered = svc.claim(
    tenant_id="t1",
    relation_type="knows_secretly",
    arity_mode=RelationArityMode.DIRECTED,
    participants=("P1", "O1"),
    context_ref=context_id,
    extraction_version="ext-1",
)
res = validate(frame, unregistered, world)
assert res.verdict is ValidationVerdict.UNDERDETERMINED
assert "schema_unregistered" in {r.code for r in res.reasons}

# an inverted interval is refused at construction, and reported by the temporal
# layer for claims arriving from persistence
try:
    dataclasses.replace(claim, valid_to=datetime(2015, 1, 1, tzinfo=timezone.utc))
except RelationContractError as exc:
    print("inverted interval refused at construction:", exc)
```

`grade_components` holds five separate keys — `independent_source_count`,
`publication_count`, `completeness`, `trust_state`, `confidence` — and there is no
aggregate key. That is constitution IV, and a test asserts the key set.

## 6. Register a relation schema

The registry is the single read path for the relation vocabulary.

```python
from domain.relation_schema import RelationSchema, RelationSchemaRegistry

registry_of_schemas = RelationSchemaRegistry()
registry_of_schemas.register(
    RelationSchema(
        relation_type="co_occurs_with",
        arity_mode=RelationArityMode.UNDIRECTED,
        allowed_subject_classes=frozenset({"ENTITY"}),
        allowed_object_classes=frozenset({"ENTITY"}),
        temporal_semantics=TemporalSemantics.POINT,
        schema_version="1",
    )
)

# the same declaration is what the proposer, the validator and admission read
assert registry_of_schemas.arity_of("works_for") is RelationArityMode.DIRECTED
assert registry_of_schemas.arity_of("co_occurs_with") is RelationArityMode.UNDIRECTED
assert registry_of_schemas.get("nope") is None
print([s.relation_type for s in registry_of_schemas.vocabulary()])   # deterministic order

try:
    registry_of_schemas.register(
        RelationSchema(
            relation_type="broken",
            arity_mode=RelationArityMode.DIRECTED,
            allowed_role_bindings=(RelationRoleBinding(role="person", member_ref="P1"),),
            schema_version="1",
        )
    )
except Exception as exc:
    print("arity/shape conflict refused:", exc)
```

Import `RelationRoleBinding` from `domain.relation_identity` in the block above. No
extractor, validator, admission rule, API route or UI constant may carry its own copy of the
relation list; a repository scan test enforces that (FR-028).

## 7. Walk evidence lineage

Backward from a relation to the source, and forward from a source to what it produced.
Incompleteness is a result, not an empty list.

```python
from domain.evidence_lineage import EvidenceGraph, EvidenceHop, HopKind, independence_groups

graph = EvidenceGraph()
for hop, derived_from, derives in [
    (EvidenceHop(kind=HopKind.RELATION, node_id="rel-1", relation_id="rel-1"), "as-1", ""),
    (EvidenceHop(kind=HopKind.ASSERTION, node_id="as-1"), "mn-1", "rel-1"),
    (EvidenceHop(kind=HopKind.MENTION, node_id="mn-1"), "sg-1", "as-1"),
    (EvidenceHop(kind=HopKind.SEGMENT, node_id="sg-1"), "ob-1", "mn-1"),
    (EvidenceHop(kind=HopKind.OBSERVATION, node_id="ob-1"), "cp-1", "sg-1"),
    (EvidenceHop(kind=HopKind.CAPTURE, node_id="cp-1"), "sr-1", "ob-1"),
    (EvidenceHop(kind=HopKind.SOURCE, node_id="sr-1"), "", "cp-1"),
]:
    graph.add_hop(hop, forward=derived_from, backward=derives)

back = graph.backward("rel-1")
assert back.complete
assert [h.kind for h in back.hops] == [
    HopKind.ASSERTION, HopKind.MENTION, HopKind.SEGMENT,
    HopKind.OBSERVATION, HopKind.CAPTURE, HopKind.SOURCE,
]

fwd = graph.forward("sr-1")
assert fwd.complete and any(h.node_id == "rel-1" for h in fwd.hops)

# a chain missing the segment hop reports exactly where it stops
broken = EvidenceGraph()
broken.add_hop(EvidenceHop(kind=HopKind.ASSERTION, node_id="as-1"), forward="mn-1", backward="rel-1")
gap = broken.backward("rel-1")
assert gap.complete is False
assert gap.first_unresolved_hop is HopKind.SEGMENT
assert gap.hops, "an incomplete trace is never an empty list"

# two captures of one wire story are one independent source, two publications
groups = independence_groups(
    ("ob-1", "ob-2", "ob-3"),
    {"ob-1": "wire-uk", "ob-2": "wire-uk", "ob-3": "wire-us"},
)
assert groups == (("ob-1", "ob-2"), ("ob-3",))
print(groups)
```

## 8. Verify store idempotency and rebuild

The store never invents an id, enforces provenance on every write, and is idempotent on
`relation_id`.

```python
import path_shim  # noqa: F401

from graph.abstraction import GraphEdge, GraphNode, InMemoryGraphStore
from graph.relation_store import InMemoryGraphProjectionBridge, InMemoryRelationStore
from graph.snapshot import RebuildableGraphStore

PROV = {"event_id": "e1", "observation_id": "obs-1"}

store = InMemoryRelationStore()
assert store.write(claim, provenance=PROV) == claim.relation_id   # the id is the caller's
assert store.write(rev2, provenance=PROV) == rev2.relation_id

store.write(claim, provenance=PROV)
first = store.checksum()
store.write(claim, provenance=PROV)
assert store.checksum() == first, "replay was not idempotent"

assert [c.relation_id for c in store.revisions(claim.logical_relation_id)] == [
    claim.relation_id, rev2.relation_id
]

from domain import ProjectionRebuildableError
try:
    store.write(claim, provenance={"event_id": "e1"})
except ProjectionRebuildableError as exc:
    print("write without provenance refused:", exc)   # I-12, state unchanged

# rebuild, then compare the checksum — never "the rebuild ran"
rebuildable = RebuildableGraphStore()
bridge = InMemoryGraphProjectionBridge(rebuildable)
bridge.project_claim(claim, provenance=PROV)
bridge.project_claim(rev2, provenance=PROV)

before = rebuildable.snapshot()
rebuilt = RebuildableGraphStore(rebuildable.rebuild(before.projection_id, from_offset=0))
assert rebuilt.snapshot().checksum == before.checksum          # FR-040, SC-011
assert rebuilt.snapshot().projection_id == before.projection_id # FR-041
assert rebuilt.store.neighbors("P1", "works_for", direction="out") == ["O1"]  # direction honoured
```

Two things above are **expected to fail on the current tree** and are the point of the
feature: `snapshot()` currently mints a fresh random `projection_id` on every call, and
`rebuild()` currently ignores both `projection_id` and `from_offset`. Section 4 of
[contracts/operations.md](./contracts/operations.md) lists every fix in
`RebuildableGraphStore` and `_checksum`.

## 9. Run the test suites

```bash
uv run --project apps/shared pytest apps/shared/tests -q
uv run --project apps/projection pytest apps/projection/tests -q
uv run --project apps/control-plane pytest apps/control-plane/tests -q
uv run ruff check apps/shared apps/projection apps/control-plane
cd apps/webapp && npx vitest run && npx tsc -b
```

**The pre-existing baseline.** The exit gate for this feature is **no new failures**, not
all green. The following was recorded before any implementation landed:

| Suite | Baseline | What "no new failures" means |
| --- | --- | --- |
| `apps/shared` | 3 failures, 344 passed, 3 skipped | still exactly 3 failures, with the same test ids; 344+ passed |
| `apps/projection` | 3 failures **and** 2 collection errors — `test_bm25s_backend.py` and `test_relevance.py` fail to import — 102 passed, 1 skipped | still exactly 3 failures and 2 collection errors; the two import failures are unchanged |
| `apps/admission` | 96 passed | 96 passed |
| `apps/interpretation` | 184 passed | 184 passed |
| `apps/webapp` | 232 tests passed across 37 files | 232 passed across 37 files |
| `ruff` on the scoped app dirs | pre-existing findings already reported | no **new** finding attributable to this feature; the existing set must not grow |

The two `apps/projection` collection errors are the reason "3 failures" is not 5: two test
files never execute at all, so their contents are outside the counted baseline. A change
that makes one of them importable is an improvement, not a regression — record it.

Any new failure is a release blocker even though the baseline is red. A pre-existing failure
that starts failing *differently* also counts as new.

## 10. Where to look next

| Question | File |
| --- | --- |
| What exactly is being built, and why | [spec.md](./spec.md) — the five defects D1-D5, FR-001..FR-050, SC-001..SC-017 |
| Field-by-field definitions and derivation rules | [data-model.md](./data-model.md) — identity material per arity mode, the seven validation layers, the five tables |
| Protocol signatures, invariants and failure modes | [contracts/service-contracts.md](./contracts/service-contracts.md) |
| Read endpoints and event payloads | `contracts/api.md`, `contracts/events.md` |
| Migration, rollback, rebuild, metrics, runbook | [contracts/operations.md](./contracts/operations.md) |
| Implementation order and concurrency groups | [plan.md](./plan.md) |
| Governance for the identity scheme and the identity/revision split | `docs/adr/0023-relation-identity-and-arity.md`, `docs/adr/0024-claim-and-context-persistence.md` |
| The identity/revision split precedent this feature follows | `apps/shared/domain/hypergraph.py` — `hyperedge_id` / `hyperedge_version_id` |
| The graph contract being adapted, not replaced | `apps/shared/contracts/graph.md`, `apps/projection/graph/abstraction.py` |
| The constitution invariants cited throughout | `.specify/memory/constitution.md` — I-1, I-3, I-4, I-11, I-12, and principle IV on source independence |
