# Operations Contract: Relation & Evidence Graph Fabric

**Feature**: [016-relation-evidence-graph-fabric](../spec.md) | **Date**: 2026-09-26

Operational procedures for the new persistence revision, the relation projections, and the
new observability surface. Every claim here is checkable by a command in
[quickstart.md](../quickstart.md) §9 or by a query in the runbook below.

---

## Migration procedure

Revision `016_relation_evidence_graph`, `down_revision = "015_worldline_reconstruction"`.
The order inside `upgrade()` is fixed and is asserted by test: **tables → columns →
backfill → indexes**. No index is ever created against a column that does not exist yet,
and no unique index is created while rows that would collide inside it are unbackfilled.
Revision 015 uses the same discipline and is the model
(`apps/control-plane/db/migrations/versions/015_worldline_reconstruction.py`).

### Preconditions

| Check | Command | Required result |
| --- | --- | --- |
| Single revision head | `uv run --project apps/control-plane alembic heads` | exactly one head, `016_relation_evidence_graph` |
| Linear history | `uv run --project apps/control-plane alembic history` | no branch; `016`'s parent is `015_worldline_reconstruction` |
| 015 is unmodified | `uv run --project apps/control-plane pytest apps/control-plane/tests/unit/test_migration_forward_only.py -q` | pass; the SHA-256 of `015_worldline_reconstruction.py` matches the pinned digest |
| Migration order | same test file | pass; `add_column < backfill < create_index` holds in the `upgrade()` body |

Revision 015 is **immutable** and pinned by SHA-256 in
`apps/control-plane/tests/unit/test_migration_forward_only.py::RELEASED_DIGESTS`. Revision
016 is added to that same pin set in the same file at the moment it is merged. Editing
either file after release is a hard stop, not a rebase problem.

### Objects created by revision 016

Five tables, in this order: `evidence_context`, `relation_claim`,
`relation_claim_revision`, `relation_schema_version`, `claim_context_lineage`. Column
definitions are those in [data-model.md](../data-model.md) §10.1. `downgrade()` drops in
strict reverse: indexes, then tables.

The backfill step is recorded as an explicit no-op for this revision (all five tables are
new, so no pre-existing row needs a value filled in). It is still present as a labelled call
so the ordering invariant is structurally enforced for this revision and inherited by 017.

### Both-path equivalence proof (FR-042, SC-010)

Two disposable databases, so neither path contaminates the other.

```powershell
# Path A - fresh install: every revision in order
docker compose -f apps/deploy/docker-compose.yml --profile core exec -T postgres createdb -U cognitive cognitive_fresh_016
Push-Location apps/control-plane
$env:POSTGRES_DB = "cognitive_fresh_016"
uv run alembic upgrade head
uv run alembic current          # must report 016_relation_evidence_graph
Pop-Location
```

```powershell
# Path B - upgrade from the already-released 015
docker compose -f apps/deploy/docker-compose.yml --profile core exec -T postgres createdb -U cognitive cognitive_upgrade_016
Push-Location apps/control-plane
$env:POSTGRES_DB = "cognitive_upgrade_016"
uv run alembic upgrade 015_worldline_reconstruction   # stop at the released revision
uv run alembic current                                # must report 015
uv run alembic upgrade head                           # 015 -> 016 only
Pop-Location
```

The comparison is **programmatic, not visual**:

```powershell
docker compose -f apps/deploy/docker-compose.yml --profile core exec -T postgres psql -U cognitive -d cognitive_fresh_016  -t -A -c "SELECT table_name||'.'||column_name||':'||data_type||':'||is_nullable FROM information_schema.columns WHERE table_schema='public' ORDER BY 1;" | Out-File -Encoding ascii cognitive_fresh_016.columns
docker compose -f apps/deploy/docker-compose.yml --profile core exec -T postgres psql -U cognitive -d cognitive_upgrade_016 -t -A -c "SELECT table_name||'.'||column_name||':'||data_type||':'||is_nullable FROM information_schema.columns WHERE table_schema='public' ORDER BY 1;" | Out-File -Encoding ascii cognitive_upgrade_016.columns
Compare-Object (Get-Content cognitive_fresh_016.columns) (Get-Content cognitive_upgrade_016.columns)
```

The same `pg_indexes` comparison runs over `ix_%` and `uq_%` index names, and the resulting
sorted line sets are compared again. `Compare-Object` must return **nothing** for columns
and **nothing** for indexes. The same comparison runs unattended in
`apps/control-plane/tests/unit/test_migration_016_forward_only.py`, which asserts the two
schemas equal and that `alembic_version.version_num` is identical on both. A `pg_dump
--schema-only` diff is a useful cross-check but is not the assertion; a text diff that
passes while a column differs in nullability is a false pass.

Re-running `uv run alembic upgrade head` on both databases must be a no-op, and
`alembic downgrade 015_worldline_reconstruction` followed by `alembic upgrade head` must
round-trip to an identical schema.

**Gate**: SC-010 is not satisfied until this test passes against a live PostgreSQL. A
digest-only check of file contents is not a substitute, which is why the existing pin test
carries that caveat in its own docstring.

---

## Rollback posture

**The schema chain is forward-only.** That is a policy decision recorded in
[plan.md](../plan.md) and constitution III, not a limitation.

- Editing `015_worldline_reconstruction.py` or `016_relation_evidence_graph.py` after
  release is **forbidden**. It silently prevents deployed databases from ever receiving the
  tables and columns, which is exactly the failure revision 014 had.
- A corrective change is a **new revision 017** with `down_revision =
  "016_relation_evidence_graph"`, and the same tables → columns → backfill → indexes order.
- `016.downgrade()` exists and drops indexes then tables in strict reverse order. It is for
  local and CI teardown only.
- The **operational recommendation is forward-fix**, not `downgrade`. A `downgrade` of 016
  drops the claim, context, schema-version and lineage tables and therefore destroys every
  relation claim written under this feature. Under constitution III the durable substrate
  is the event log; a `downgrade` loses the projection's source, not merely the projection.
  If a `downgrade` is unavoidable in a non-production environment, take a `pg_dump` of the
  five tables first and treat the run as destructive to `RelationStore` contents.
- Application rollback without a schema rollback is the normal response to a bad release:
  deploy the previous application revision while leaving 016 applied. Because 016 only
  adds tables, an older application that does not know about them continues to work.
- Claims written under a withdrawn feature version are not deleted. They become
  `QUARANTINED` or `SUPERSEDED` and remain queryable (I-3, FR-006).

| Situation | Action |
| --- | --- |
| Bad application code, schema correct | Roll back the application only. |
| Wrong index or column type in 016 | Ship 017 to correct it. Do not edit 016. |
| 016 failed to apply on a fresh database | Fix 016 while it is unreleased; if it has been applied anywhere, ship 017. |
| Need to drop the feature entirely | `downgrade()` to 015 **only** with a verified backup, and only in non-production. |

---

## Projection rebuild procedure

`RebuildableGraphStore` is the existing wrapper in `apps/projection/graph/snapshot.py`. This
feature fixes four defects in it and adds a claim-level path.

### The FIX (FR-039, FR-040, FR-041)

| Defect on the current tree | Required behaviour |
| --- | --- |
| `rebuild(projection_id, from_offset=0)` accepts `projection_id` and `from_offset` and then **ignores both**, always replaying the whole log from offset 0 | The wrapper records its own `projection_id`; `rebuild(projection_id, from_offset=k)` replays only events with `offset >= k` and returns the fresh store. `projection_id` is validated against the recorded id and a mismatch raises rather than silently rebuilding the wrong projection. |
| `write_hyperedge` is not forwarded, so N-ary writes never reach the durable log and a rebuild loses them | The wrapper forwards `write_hyperedge` and appends the corresponding `ReplayEvent` with `kind="hyperedge"`. |
| `snapshot()` constructs a fresh `GraphSnapshot()`, whose `projection_id` defaults to `"PROJ-" + uuid4().hex[:12]`, so two snapshots of one projection get different ids | `snapshot()` records the `projection_id` of the projection it snapshotted. A second snapshot over an unchanged store returns the same `projection_id` and the same `checksum`. |
| `_checksum` sorts edges by `str(edge)`, which is the dataclass `repr` and therefore embeds the `properties` dict ordering | `_checksum` sorts by `edge_id` and hashes the joined `edge_id` sequence, so it is stable under property reordering. |

### Verification step (FR-040, SC-011)

Rebuild, then compare the checksum. Never accept "the rebuild ran" as evidence.

```python
# claim level: the RelationStore is the oracle
first  = source_store.checksum()
... replay every durable event into a fresh InMemoryRelationStore ...
assert fresh_store.checksum() == first          # FR-040

# graph level: the graph checksum is GraphSnapshot.checksum, not RelationStore.checksum
snapshot_before = rebuildable.snapshot()
fresh_graph     = rebuildable.rebuild(snapshot_before.projection_id, from_offset=0)
rebuilt = RebuildableGraphStore(fresh_graph)
assert rebuilt.snapshot().checksum == snapshot_before.checksum   # SC-011
assert rebuilt.snapshot().projection_id == snapshot_before.projection_id
assert fresh_graph.neighbors("P1", "works_for", "out") == ["O1"]
```

Two snapshots over an unchanged store must produce an equal checksum **and** a stable
projection id (FR-041). A rebuild that produces the right edge count but a different
checksum has lost or altered a field, and the graph is not rebuildable.

`graph_projection_checksum_mismatch_total` increments on every inequality above, and a
mismatch is an alert, not a warning. A projection that cannot reproduce its own state is
not a projection (constitution III).

---

## Snapshot and checksum verification

Two independent checksums exist, and conflating them is a defect:

| Checksum | Belongs to | Built from | Answers |
| --- | --- | --- | --- |
| `RelationStore.checksum()` | the claim set (durable) | claims sorted by `relation_id`, then `digest128` over the joined `content_hash` list | did any claim's content change? |
| `GraphSnapshot.checksum` | the projected graph | edges sorted by `edge_id`, then `digest128` over the joined `edge_id` sequence | did the projection reproduce exactly? |

`GraphSnapshot.checksum` is what `snapshot()` records. It is **not** `RelationStore.checksum`
and neither substitutes for the other. A projection can have a matching checksum while the
underlying claim set has drifted, if the bridge dropped a field; that is why the claim-level
oracle is checked separately in the rebuild procedure above.

**Double-snapshot procedure**

1. `snapshot()` → record `projection_id`, `last_offset`, `edge_count`, `node_count`, `checksum`.
2. Perform no writes.
3. `snapshot()` again.
4. All five fields must be equal. A differing `projection_id` means the `uuid4` default is
   still in play (FR-041 unfixed). A differing `checksum` means `_checksum` still depends on
   property ordering.

**Where snapshots are recorded**: `claim_context_lineage` stores the trace
(`direction`, `hops`, `complete`, `first_unresolved_hop`) keyed by `lineage_id`; the
projection head (`projection_id`, `last_offset`, `checksum`) is the wrapper's snapshot
record. Neither carries raw content (constitution I-5, I-12).

---

## Identity collision monitoring

Relation identity is a **128-bit truncated SHA-256** (32 hex characters). A collision is
possible in principle — at 2^64 relations the birthday probability reaches ~50% — which is
why a collision must be **recorded and surfaced, never silently treated as an identity
merge** (FR-011, spec edge cases).

The 32-bit FNV-1a scheme being retired had a birthday threshold near 77k edges, which is
inside the platform's operating range; that is the reason for the change, not a claim that
collisions are impossible (SC-002, SC-015).

### Detection algorithm

A collision is any `relation_id` bucket in a claim set holding more than one claim. A
bucket of size > 1 whose members all share the same `content_hash` is an idempotent
replay and is **not** a collision. A bucket of size > 1 with differing `content_hash` is a
true identity collision.

```python
def detect_identity_collisions(
    claims: Sequence[RelationClaim],
) -> tuple[IdentityCollision, ...]:
    buckets: dict[str, list[RelationClaim]] = {}
    for claim in claims:
        buckets.setdefault(claim.relation_id, []).append(claim)
    found = [
        IdentityCollision(
            relation_id=relation_id,
            claims=tuple(sorted(members, key=lambda c: c.content_hash)),
        )
        for relation_id, members in sorted(buckets.items())
        if len(members) > 1 and len({c.content_hash for c in members}) > 1
    ]
    return tuple(found)
```

`IdentityCollision` carries `relation_id`, the colliding claims, their distinct
`logical_relation_id` values, and their `content_hash` values. The scanner runs on every
ingest batch, on every snapshot, and on demand via the read API.

**On detection**: increment `relation_identity_collisions_total`; write an audit record
with actor, the colliding `relation_id`, and the claims involved; **quarantine** the later
arrival rather than overwriting the stored claim; leave both claims readable. `RelationStore.write`
refuses the second write with `IdentityCollisionError` and the existing row is preserved
untouched. Nothing is auto-merged and nothing is auto-deleted.

### Metric and alert

| Signal | Definition |
| --- | --- |
| Metric | `relation_identity_collisions_total` — Counter, labels `{"tenant_id"}` |
| Page threshold | `increase(relation_identity_collisions_total[10m]) > 0` — any occurrence pages. One collision at 128 bits means either corrupted input or a broken id derivation, and either is a stop-the-line defect. |
| Ticket threshold | `increase(relation_identity_collisions_total[1h]) > 3` across all tenants — treat as systemic id-scheme corruption rather than a single bad input. |
| Baseline | must remain exactly `0`. There is no accepted rate. |
| Companion check | SC-002 asserts 1,000,000 deterministically generated claims produce exactly 1,000,000 distinct ids with zero collisions; a nonzero collision counter in that fixture is a failure of the test, not an expected result. |

---

## Validation failure handling

A verdict other than `VALID` is **preserved** with its decision, reasons, grade components,
evaluated versions and timestamps, and is **replayable** (FR-050). Rejected, retracted and
superseded claims are never deleted (FR-006, constitution "rejected candidates are never
auto-deleted").

| Verdict | Storage action | Replay action |
| --- | --- | --- |
| `VALID` | claim stored with `status=ACTIVE`; validation record stored with all seven layer outcomes and `grade_components` | re-validatable on demand after a schema or context change; no automatic re-run |
| `INVALID` | claim stored unchanged; `status` set to `QUARANTINED` **only** when the reason is `context_unresolved`; otherwise the claim keeps its submitted status. Validation record stores the failing layer, reason code and detail. Never deleted. | re-run after the specific defect is fixed (schema registered, tenant corrected, identity restored). A corrected claim is a **new revision** of the same `logical_relation_id`, not an in-place edit. |
| `CONFLICTING` | both claims stored; the `contradicts` links are recorded on both sides; no ranking is applied (out of scope) | re-run when either interval or evidence set changes; the conflict is re-derived, never remembered as a verdict |
| `STALE` | claim stored byte-unchanged, including its original `ontology_version` and `schema_version` | re-run when the named ontology version is re-activated or the claim is re-extracted; a stale claim is never silently upgraded |
| `INCOMPLETE` | claim stored; `evidence_grade` recorded as degraded with its components | re-run when the context's `completeness` improves or the missing `parent_context_id` is registered |
| `UNDERDETERMINED` | claim stored; no state transition; reason code names what is undeclared | re-run when the missing declaration exists — an undeclared extractor version, an unregistered relation type, an undeclared independence group |

**Preserved fields on every validation record** (FR-050): `relation_id`, `context_id`,
`verdict`, the full `layers` mapping, the `reasons` tuple with codes and layers,
`grade_components`, `evaluated_versions` (`extraction_version`, `normalization_version`,
`ontology_version`, `schema_version`), `created_at`, and the evaluated-at timestamp. A
validation record with a verdict but without reasons and versions is an incomplete record
and is a defect.

**Event on record**: `context.validation.recorded` is emitted for every validation run,
including `VALID`, so a rebuild reproduces the verdict history and not only the claims.

**Never**: convert a non-`VALID` verdict into a `False` boolean at a call site, drop a
layer, or delete the claim because it failed.

---

## Quarantine and replay

A claim whose `context_ref` does not resolve goes to quarantine. It is **never
auto-deleted** and is never reinterpreted under a default context (FR-016).

| Property | Rule |
| --- | --- |
| Trigger | `RelationStore.write` refuses a claim with an empty `context_ref` (construction already rejects it, and the write path re-checks). A claim whose `context_ref` is syntactically valid but unknown to the `ContextRegistry` is stored with `status=QUARANTINED` and reason `context_unresolved`. |
| Storage | Stored, never dropped. Fully retrievable via `RelationStore.get(relation_id)`. |
| Metric | `context_unresolved_total` — Counter, labels `{"tenant_id"}` |
| Replay trigger | The `context.registered` event. A quarantined claim is re-validated when the frame it references is registered. |
| Replay scope | Replay is scoped to the quarantined set, not a full re-ingest. The claim is re-read, re-validated, and its `status` moved to `ACTIVE` only on `VALID`. A still-non-`VALID` replay leaves it quarantined and records the new verdict. |
| Idempotency | Replay is idempotent: replaying a set containing a `VALID` claim leaves it unchanged. |
| Manual trigger | The read API exposes the quarantined set for an operator, with the reason code and the referenced `context_id` on every row. |
| Boundedness | No automatic retry storm. Replay is event-driven plus operator-driven, never a polling loop (constitution backpressure and retry budgets). |

Other quarantine lanes already in force (`cognitive_dlq_routed_total`, `lane` label) carry
malformed claims and parse failures. A claim rejected by *validation* is not a DLQ event: it
is preserved knowledge with a verdict, and it belongs in `relation_claim` with its
validation record.

---

## Observability: metrics

Registered in `apps/shared/observability/__init__.py` alongside the existing
`cognitive_*` series, using `prometheus_client` `Counter`/`Histogram`/`Gauge`. The
contractual names are below; the deployed names carry the `cognitive_` prefix that the
existing registry already uses (for example `cognitive_relation_claims_written_total`).

| Metric | Type | Labels | Detects |
| --- | --- | --- | --- |
| `relation_claims_written_total` | Counter | `tenant_id`, `relation_type`, `status` | claim write volume and status mix; a collapse in `active` with a spike in `quarantined` or `superseded` is a regression signal |
| `relation_identity_collisions_total` | Counter | `tenant_id` | a 128-bit identity collision; must stay at `0` (FR-011) |
| `relation_revisions_total` | Counter | `tenant_id`, `relation_type` | revision rate; a rise means claims are being corrected rather than created, which is a data-quality signal in its own right (I-4) |
| `context_registrations_total` | Counter | `tenant_id`, `completeness`, `trust_state` | evidence-context throughput and the completeness/trust mix of the substrate |
| `context_unresolved_total` | Counter | `tenant_id` | claims referencing a context that does not resolve; the quarantine trigger (FR-016) |
| `context_validation_total` | Counter | `verdict`, `failing_layer` | verdict distribution across the six verdicts and which layer produced the failure; `failing_layer` is `none` for `VALID` |
| `relation_lineage_incomplete_total` | Counter | `hop` | how often a lineage traversal stops, and at which `HopKind`; `relation_lineage_incomplete_total{hop="segment"}` rising means the segment stage is dropping hops (SC-003, FR-033) |
| `relation_schema_unregistered_total` | Counter | `relation_type` | claims citing a relation type with no registered schema; the correct `UNDERDETERMINED` path, and a signal that extraction is proposing types nobody declared (FR-023, FR-028) |
| `graph_projection_rebuild_duration_seconds` | Histogram | `projection_type` | rebuild cost; a p95 above the configured budget means the projection is falling behind the durable log |
| `graph_projection_checksum_mismatch_total` | Counter | `projection_type` | a rebuild or double-snapshot whose checksum did not match; **alert**, never a warning (FR-040, SC-011) |

Supporting series already in the module and reused unchanged:
`cognitive_projections_total{projection_type}` for write volume, `cognitive_dlq_routed_total{lane}`
for malformed data, and `cognitive_latency_seconds{operation}` for request latency.

`relation_validation_duration_seconds{stage}` (Histogram over the seven layers) is a
non-gating addition: it exists so a slow `cross_source` or `graph_constraints` layer is
visible before it becomes a pipeline bottleneck. It has no alert.

---

## Observability: audit log

Constitution VII requires audit logs. The following are recorded, each with **actor**,
**resource** and **context**, plus tenant, timestamp and request id.

| Event | Actor | Resource | Context recorded |
| --- | --- | --- | --- |
| Cross-tenant read refused | the requesting principal | the requested `relation_id` / `context_id` / `logical_relation_id` | the tenant the resource belongs to, **not** its contents; no field values are logged, because a refusal must not leak what it refused |
| Context registered | the registering principal or service | `context_id` | `tenant_id`, `investigation_id`, `observation_id`, `source_id`, `source_family`, `completeness`, `trust_state`, the three versions, and `parent_context_id` |
| Claim superseded | the superseding principal or service | `relation_id` of the new revision | `logical_relation_id`, prior `relation_id`, `revision_number`, the reason for the revision |
| Claim contradicted | the contradicting principal or service | `relation_id` | the contradicting claim's `relation_id`, the overlapping interval, and the evidence refs on both sides |
| Identity collision detected | the detecting scanner or principal | the colliding `relation_id` | both claims' `content_hash` and `logical_relation_id`; the later arrival is quarantined, never merged |
| Quarantine entered / replayed | the validator or the replay operator | `relation_id` | the reason code, the `context_ref` that failed to resolve, and the replay verdict |
| Schema registered / re-versioned | the schema author | `relation_type` + `schema_version` | `arity_mode`, `temporal_semantics`, `admission_rule_id`, the full definition, the prior version superseded |

Audit records are append-only. A retracted or rejected claim is never deleted and neither
is its audit trail (I-3).

---

## Capacity and performance

| Dimension | Requirement | Why |
| --- | --- | --- |
| Identity computation | Pure hashing: one `json.dumps` canonicalisation plus one `sha256` truncated to 128 bits per id. No I/O, no allocation proportional to the relation set, no index. Must handle 10^7 relations, and 1,000,000 deterministically generated claims must yield 1,000,000 distinct ids in a single pass (SC-002). | Identity is on the hot path of every claim write; anything that scales with the total relation count would cap the platform. |
| Validator purity and statelessness | One call, no session, no socket, no clock read. Two calls on the same arguments are byte-equal apart from the recorded timestamp. | Makes the validator testable offline and safe to call concurrently (plan risk register). |
| Expensive layers | `cross_source` and `graph_constraints` accept **pre-computed inputs** via `ValidationWorld`: independence groups and `admitted_entity_ids` / `known_entity_ids` sets. Neither layer traverses or queries. | Validation runs inline with claim production; a layer that resolves endpoints itself becomes the pipeline bottleneck. |
| Layer short-circuiting | Affects only the collapsed verdict. All seven layer outcomes are still computed, so a failure is never masked by an earlier pass and never hidden by an earlier failure. | FR-019; callers need to see that identity passed even when cross-source failed. |
| Store residency | In production no store holds the whole relation set in memory. `InMemoryRelationStore` is the test oracle and rebuild target only. The production store is PostgreSQL, addressed through the same protocol with tenant-scoped indexes. | 10^7 relations × ~35-char ids plus JSONB columns does not fit in one process; constitution IV forbids a single store becoming the authority. |
| Checksum cost | `RelationStore.checksum()` and `GraphSnapshot.checksum` are streaming sorts over `relation_id` / `edge_id` and are not called on the write path. | A per-write checksum turns O(1) idempotent writes into O(n). |
| Claim size | 35-char `relation_id` / `logical_relation_id`, 35-char `context_id`, JSONB for ref tuples and role bindings. Index and storage cost rises versus 8-char FNV ids; this is accepted, against a birthday threshold moving from ~77k to ~10^19 relations. | Correctness dominates; the cost is bounded and known. |
| Storage growth | Five tables, append-heavy. `relation_claim_revision` is an append-only ledger and `claim_context_lineage` stores traces; both are expected to grow faster than `relation_claim` and must be retention-scoped, never silently pruned. | I-3: a deleted revision is a deleted version of history. |

---

## Runbook: verifying the fabric after deploy

Ordered. Each step is a gate for the next; a failure stops the deploy.

```powershell
# 1. Migration topology and the released-revision pin
uv run --project apps/control-plane pytest apps/control-plane/tests/unit/test_migration_forward_only.py -q
uv run --project apps/control-plane pytest apps/control-plane/tests/unit/test_migration_016_forward_only.py -q
uv run --project apps/control-plane alembic current      # must report 016_relation_evidence_graph
uv run --project apps/control-plane alembic heads        # must print exactly one head
```

```powershell
# 2. Domain contracts
uv run --project apps/shared pytest apps/shared/tests/unit/domain/test_relation_identity.py -q
uv run --project apps/shared pytest apps/shared/tests/unit/domain/test_relation_claim.py -q
uv run --project apps/shared pytest apps/shared/tests/unit/domain/test_evidence_context.py -q
uv run --project apps/shared pytest apps/shared/tests/unit/domain/test_relation_schema.py -q
uv run --project apps/shared pytest apps/shared/tests/unit/domain/test_context_validation.py -q
uv run --project apps/shared pytest apps/shared/tests/unit/domain/test_evidence_lineage.py -q
```

```powershell
# 3. Projection contracts
uv run --project apps/projection pytest apps/projection/tests/unit/test_relation_store.py -q
uv run --project apps/projection pytest apps/projection/tests/unit/test_relation_projection_bridge.py -q
uv run --project apps/projection pytest apps/projection/tests/unit/test_graph_store_semantics.py -q
uv run --project apps/projection pytest apps/projection/tests/unit/test_graph_snapshot_rebuild.py -q
uv run --project apps/projection pytest apps/projection/tests/unit/test_neo4j_relation_payload.py -q
```

```powershell
# 4. Full per-app suites - compare against the recorded baseline, not against zero
uv run --project apps/shared pytest apps/shared/tests -q
uv run --project apps/projection pytest apps/projection/tests -q
uv run --project apps/control-plane pytest apps/control-plane/tests -q
uv run --project apps/admission pytest apps/admission/tests -q
uv run --project apps/interpretation pytest apps/interpretation/tests -q
```

```powershell
# 5. Frontend
Push-Location apps/webapp
npx vitest run
npx tsc -b
Pop-Location
```

```powershell
# 6. Static gates
uv run ruff check apps/shared apps/projection apps/control-plane
uv run ruff format --check apps/shared apps/projection apps/control-plane
uv run python -m compileall -q apps/shared apps/projection apps/control-plane
```

```powershell
# 7. Post-deploy data checks
docker compose -f apps/deploy/docker-compose.yml --profile core exec -T postgres psql -U cognitive -d cognitive -c "SELECT count(*) AS claims, count(DISTINCT relation_id) AS distinct_ids FROM relation_claim;" -c "SELECT count(*) AS contexts FROM evidence_context;" -c "SELECT count(*) AS incomplete_traces FROM claim_context_lineage WHERE complete = false;"
```

```powershell
# 8. Runtime signals - all must be flat over the observation window
# relation_identity_collisions_total        == 0        (page on any increase)
# graph_projection_checksum_mismatch_total  == 0        (alert on any increase)
# context_unresolved_total                  steady
# context_validation_total{verdict="valid"} dominant
# relation_schema_unregistered_total        steady
```

## Post-deploy checklist

- [ ] `alembic current` reports `016_relation_evidence_graph` and `alembic heads` prints one head.
- [ ] `test_migration_forward_only.py` passes, so revisions 014 and 015 are byte-identical to their released digests.
- [ ] `test_migration_016_forward_only.py` passes: fresh install and 015-upgrade yield an identical schema by programmatic comparison.
- [ ] `count(*) == count(DISTINCT relation_id)` in `relation_claim` — the store is id-keyed and nothing was merged.
- [ ] No `SUPERSEDED`, `RETRACTED` or `CONTRADICTED` claim is missing from the table; a falling count is a deletion defect, not a cleanup.
- [ ] `relation_identity_collisions_total` is zero.
- [ ] `graph_projection_checksum_mismatch_total` is zero and a manual double-snapshot returns an equal checksum with a stable `projection_id`.
- [ ] `context_validation_total` shows a verdict distribution, not a boolean; `failing_layer` is populated for every non-`VALID` verdict.
- [ ] A cross-tenant read probe returns the same not-found surface as a nonexistent id, with no differing status, count or error text, and is present in the audit log.
- [ ] Per-app suites and the frontend gates show no new failures against the baseline in [quickstart.md](../quickstart.md) §9.
- [ ] Ruff reports no finding introduced by this feature; the pre-existing findings are recorded, not silently absorbed.
