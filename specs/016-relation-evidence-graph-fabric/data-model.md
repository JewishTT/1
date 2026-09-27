# Data Model: Relation & Evidence Graph Fabric

**Feature**: 016-relation-evidence-graph-fabric

All Python types are frozen dataclasses living in `apps/shared/domain/`. All hashing is
SHA-256 truncated to 128 bits and hex-encoded (32 hex characters). All canonical
serialisation uses `json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=False,
default=str)`.

---

## 1. Canonical serialisation and digest primitives

```python
# apps/shared/domain/relation_identity.py

DIGEST_BITS = 128

def canonical_material(value: object) -> str:
    """Deterministic, order-independent serialisation of identity material."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)

def digest128(material: str) -> str:
    """128-bit truncated SHA-256 as 32 lowercase hex characters."""
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[: DIGEST_BITS // 4]
```

`digest128` is the **only** id-producing primitive in this feature. `fnv1a` remains in the
frontend for layout seeds and UI checksums only and is never used for relation identity.

---

## 2. RelationArityMode

```python
class RelationArityMode(StrEnum):
    UNDIRECTED = "undirected"
    DIRECTED   = "directed"
    NARY       = "nary"
    TEMPORAL   = "temporal"
```

| Mode | Participant order for identity | `neighbors` default direction | Window in identity? |
|---|---|---|---|
| `UNDIRECTED` | sorted ascending | `both` | no |
| `DIRECTED` | `(subject, object)` preserved | `out` | no |
| `NARY` | sorted `(role, member)` pairs | `both` | no |
| `TEMPORAL` | ordered participants preserved | `out` | **yes** |

Arity mode is **part of the identity material**, so `Employment{person=P1, org=O1}` declared
`NARY` and the pair `P1 employed_by O1` declared `DIRECTED` produce different ids even for
the same participants.

---

## 3. RelationRoleBinding

```python
@dataclass(frozen=True)
class RelationRoleBinding:
    role: str            # "person", "organization", "role", "location"
    member_ref: str      # entity / candidate / node id
    member_class: str = ""   # declared class, validated by the semantic layer
```

Rejection rules at construction:
- a role name must be non-empty;
- the same role may not bind two members;
- the same member may not occupy two roles **unless** the schema sets
  `allow_repeated_member=True`.

---

## 4. RelationIdentity and RelationClaim

### 4.1 Identity derivation

```python
def logical_material(
    arity_mode: RelationArityMode,
    relation_type: str,
    participants: Sequence[str],
    role_bindings: Sequence[RelationRoleBinding] = (),
) -> dict: ...

def logical_relation_id(...) -> str:      # "RL-" + digest128(canonical(logical_material))
def relation_id(logical_id: str, revision_material: dict) -> str:   # "RC-" + digest128(...)
```

`logical_material` shape per mode:

| Mode | Material |
|---|---|
| `UNDIRECTED` | `{"mode","type","members": sorted(set(participants))}` |
| `DIRECTED` | `{"mode","type","subject","object"}` |
| `NARY` | `{"mode","type","roles": [[role, member], …] sorted by role}` |
| `TEMPORAL` | `{"mode","type","members": ordered, "valid_from", "valid_to"}` |

`relation_id` material: `{"logical_id", "valid_from", "valid_to", "observed_at",
"published_at", "context_ref", "observation_refs": sorted, "assertion_refs": sorted,
"revision_number"}`.

Two claims with identical `relation_id` are byte-identical in content (idempotency, I-11).
A revised claim gets a new `relation_id` and the same `logical_relation_id`.

### 4.2 RelationClaim

```python
class RelationStatus(StrEnum):
    ACTIVE      = "active"
    SUPERSEDED  = "superseded"
    RETRACTED   = "retracted"
    CONTRADICTED = "contradicted"
    QUARANTINED = "quarantined"

class EvidenceGrade(StrEnum):
    STRONG = "strong"        # >= 2 independent sources, complete context
    MODERATE = "moderate"    # 1 independent source or degraded completeness
    WEAK = "weak"            # single observation, partial context
    UNGRADED = "ungraded"    # no evidence grade could be computed

@dataclass(frozen=True)
class RelationClaim:
    relation_id: str
    logical_relation_id: str
    revision_number: int
    relation_type: str
    arity_mode: RelationArityMode
    subject_ref: str
    object_ref: str
    role_bindings: tuple[RelationRoleBinding, ...] = ()

    valid_from: datetime | None = None
    valid_to: datetime | None = None
    observed_at: datetime | None = None
    published_at: datetime | None = None
    known_from: datetime | None = None
    known_until: datetime | None = None

    assertion_refs: tuple[str, ...] = ()
    observation_refs: tuple[str, ...] = ()
    context_ref: str = ""                       # required, non-empty (FR-007)

    source_independence_groups: tuple[tuple[str, ...], ...] = ()
    extraction_version: str = ""
    normalization_version: str = ""
    ontology_version: str = ""
    schema_version: str = ""

    status: RelationStatus = RelationStatus.ACTIVE
    confidence: float = DEFAULT_CONFIDENCE
    evidence_grade: EvidenceGrade = EvidenceGrade.UNGRADED
    tenant_id: str = "default-tenant"
    investigation_id: str = ""

    created_by: str = ""
    supersedes: str = ""
    contradicts: tuple[str, ...] = ()
    created_at: datetime | None = None
```

`__post_init__` rejections (each raises `RelationContractError`, a `ValueError` subclass):
1. `subject_ref == object_ref` → self-loop.
2. `relation_type` empty.
3. `context_ref` empty → missing context (I-12).
4. `arity_mode is NARY` and `len(role_bindings) < 2` → too few members.
5. `arity_mode is NARY` and duplicate members across bindings → duplicate member.
6. `arity_mode is DIRECTED` and `role_bindings` non-empty → directed relations take no roles.
7. `valid_to < valid_from` → inverted interval. (Rejected at construction; the validator
   also reports it for claims arriving from persistence, where construction already happened.)
8. `0.0 <= confidence <= 1.0`.
9. `revision_number < 1`.
10. `supersedes == relation_id` → self-supersession.

Derived:
- `content_hash` — `digest128` over the full serialised field set.
- `independent_source_count` — number of `source_independence_groups`.
- `publication_count` — `len(observation_refs)`; stored **separately** from the independent
  count, never conflated (constitution IV).
- `is_active_at(ts)`.
- `to_dict()` / `from_dict()` — round-trip stable.

### 4.3 RelationRevision view

```python
@dataclass(frozen=True)
class RelationRevision:
    logical_relation_id: str
    revisions: tuple[RelationClaim, ...]   # ordered by revision_number
```

`revisions_of(logical_id)` returns the ordered revision chain; the last element is current.

---

## 5. EvidenceContext

```python
class ContextCompleteness(StrEnum):
    COMPLETE = "complete"
    PARTIAL  = "partial"
    FRAGMENT = "fragment"

class ContextTrustState(StrEnum):
    VERIFIED  = "verified"
    ATTESTED  = "attested"
    UNVERIFIED = "unverified"
    DISPUTED  = "disputed"

@dataclass(frozen=True)
class EvidenceContext:
    context_id: str = ""            # derived when empty
    tenant_id: str = "default-tenant"
    investigation_id: str = ""
    entity_anchor: str = ""

    observation_id: str = ""
    source_id: str = ""
    document_id: str = ""
    segment_id: str = ""

    subject_candidate_ids: tuple[str, ...] = ()
    object_candidate_ids: tuple[str, ...] = ()

    observed_at: datetime | None = None
    published_at: datetime | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None

    source_family: str = ""
    independence_group: str = ""
    language: str = ""
    location_context: str = ""

    extraction_version: str = ""
    normalization_version: str = ""
    ontology_version: str = ""

    completeness: ContextCompleteness = ContextCompleteness.COMPLETE
    trust_state: ContextTrustState = ContextTrustState.UNVERIFIED
    policy_snapshot_ref: str = ""
    parent_context_id: str = ""

    def __post_init__(self):
        # frozen: object.__setattr__ only to fill the derived context_id
```

Derivation: `context_id = "CX-" + digest128(canonical(fields minus context_id))`.
`__post_init__` additionally rejects `valid_to < valid_from`.

Cycle detection lives in the resolver, not the frame: `detect_context_cycle(frames)` returns
the cycle path, and the validator reports `context_parent_cycle`.

`ContextResolver` protocol:

```python
class ContextResolver(Protocol):
    def resolve(self, context_id: str) -> EvidenceContext | None: ...
    def register(self, frame: EvidenceContext) -> str: ...   # idempotent, returns context_id
```

`InMemoryContextResolver` is the reference implementation and the test oracle.
Resolution failure yields reason code `context_unresolved`; the validator **never**
substitutes a default frame.

---

## 6. RelationSchema registry

```python
class TemporalSemantics(StrEnum):
    POINT            = "point"
    REQUIRED_INTERVAL = "required_interval"
    OPTIONAL_INTERVAL = "optional_interval"
    OPEN_ENDED       = "open_ended"

@dataclass(frozen=True)
class RelationSchema:
    relation_type: str
    arity_mode: RelationArityMode
    allowed_subject_classes: frozenset[str] = frozenset()
    allowed_object_classes: frozenset[str] = frozenset()
    allowed_role_bindings: tuple[RelationRoleBinding, ...] = ()
    allowed_role_classes: Mapping[str, frozenset[str]] = field(default_factory=dict)
    admissible_evidence_patterns: tuple[str, ...] = ()
    temporal_semantics: TemporalSemantics = TemporalSemantics.OPTIONAL_INTERVAL
    admission_rule_id: str = "default-assert"
    schema_version: str = "1"
    allow_repeated_member: bool = False
    required: bool = True
```

```python
class RelationSchemaRegistry:
    def register(self, schema: RelationSchema) -> RelationSchema      # raises on conflicting redefinition
    def get(self, relation_type: str) -> RelationSchema | None
    def vocabulary(self) -> tuple[RelationSchema, ...]                 # deterministic order
    def arity_of(self, relation_type: str) -> RelationArityMode | None
```

Registration rejects a schema whose declared `arity_mode` conflicts with its participant
shape: `DIRECTED` with role bindings, or `NARY` with fewer than two role bindings (FR-012).

Re-definition of an existing `relation_type` with a *different* `schema_version` is allowed
(a new version); re-definition with the *same* version and different content is rejected.

---

## 7. ContextValidator

```python
class ValidationLayer(StrEnum):
    STRUCTURAL       = "structural"
    SEMANTIC         = "semantic"
    TEMPORAL         = "temporal"
    PROVENANCE       = "provenance"
    IDENTITY         = "identity"
    CROSS_SOURCE     = "cross_source"
    GRAPH_CONSTRAINTS = "graph_constraints"

class ValidationVerdict(StrEnum):
    VALID            = "valid"
    INVALID          = "invalid"
    UNDERDETERMINED  = "underdetermined"
    INCOMPLETE       = "incomplete"
    CONFLICTING      = "conflicting"
    STALE            = "stale"

class LayerOutcome(StrEnum):
    PASSED     = "passed"
    FAILED     = "failed"
    INDETERMINATE = "indeterminate"
    NOTED      = "noted"

@dataclass(frozen=True)
class ValidationReason:
    code: str          # stable, snake_case, e.g. "temporal_interval_inverted"
    layer: ValidationLayer
    detail: str
    evidence: tuple[str, ...] = ()

@dataclass(frozen=True)
class ValidationResult:
    verdict: ValidationVerdict
    layers: Mapping[ValidationLayer, LayerOutcome]     # all seven, always
    reasons: tuple[ValidationReason, ...]
    evidence_grade: EvidenceGrade
    grade_components: Mapping[str, float | int | str]  # stored separately, never summed
    claim_id: str
    context_id: str
    evaluated_versions: Mapping[str, str]              # extractor/normalization/ontology/schema
```

Verdict precedence (first match wins when several layers produce reasons):

```text
INVALID  >  CONFLICTING  >  STALE  >  INCOMPLETE  >  UNDERDETERMINED  >  VALID
```

### 7.1 Layer contracts

| Layer | PASSES when | FAILED reasons | INDETERMINATE reasons | NOTED |
|---|---|---|---|---|
| `structural` | required fields present, no self-loop, refs non-empty, identity recomputable | `missing_required_field`, `self_loop_relation`, `context_ref_missing` | — | — |
| `semantic` | schema exists and subject/object classes are permitted | `schema_unregistered`→INDET, `schema_subject_class_not_allowed`, `schema_object_class_not_allowed`, `schema_role_class_not_allowed`, `schema_role_undeclared` | `schema_unregistered` | — |
| `temporal` | `valid_to >= valid_from`; interval satisfies declared temporal semantics | `temporal_interval_inverted`, `temporal_interval_required` | — | `temporal_publication_before_observation` (→UNDERDETERMINED), `temporal_non_overlap` |
| `provenance` | context resolves, tenant matches, evidence present | `context_unresolved`, `provenance_tenant_mismatch`, `provenance_context_parent_missing`, `context_parent_cycle` | `extraction_version_undeclared`, `normalization_version_undeclared` | `evidence_refs_empty` |
| `identity` | recomputed `logical_relation_id` and `relation_id` match the claim's own | `identity_logical_mismatch`, `identity_revision_mismatch` | — | — |
| `cross_source` | independence groups are internally consistent (one `source_family` per group) | `cross_source_family_conflict` | `independence_group_undeclared` (when >1 observation and no group) | `publication_count_exceeds_independent_count` |
| `graph_constraints` | every participant ref resolves to an admitted entity | `graph_endpoint_unknown` | `graph_endpoint_unadmitted`, `graph_endpoint_unresolved` | — |

### 7.2 `ValidationWorld`

The validator is pure; everything external is injected so no layer performs I/O.

```python
@dataclass(frozen=True)
class ValidationWorld:
    schemas: RelationSchemaRegistry
    contexts: ContextResolver
    admitted_entity_ids: frozenset[str] = frozenset()
    known_entity_ids: frozenset[str] = frozenset()
    active_ontology_versions: frozenset[str] = frozenset()
    known_ontology_versions: frozenset[str] = frozenset()
    sibling_claims: tuple[RelationClaim, ...] = ()   # for interval-conflict detection
```

`validate(context, claim, world) -> ValidationResult`. A `null` `context` short-circuits to an
`INVALID/provenance_context_missing` result with all seven layers reported.

### 7.3 Evidence grade computation (FR-025)

```python
grade_components = {
    "independent_source_count": int,     # len(source_independence_groups)
    "publication_count": int,             # len(observation_refs)
    "completeness": str,                  # context.completeness
    "trust_state": str,                   # context.trust_state
    "confidence": float,                  # claim.confidence
}
```

| independent sources | completeness | trust | grade |
|---|---|---|---|
| >= 2 | `complete` | `verified`/`attested` | `strong` |
| >= 1 | `complete` or `partial` | not `disputed` | `moderate` |
| 1 | `fragment` / any | any | `weak` |
| 0 | any | any | `ungraded` |
| any | any | `disputed` | capped at `weak` |

Components are stored individually. No single number is computed from them (constitution IV).

---

## 8. EvidenceGraph and lineage

```python
class HopKind(StrEnum):
    SOURCE      = "source"
    CAPTURE     = "capture"
    OBSERVATION = "observation"
    SEGMENT     = "segment"
    MENTION     = "mention"
    CANDIDATE   = "candidate"
    ASSERTION   = "assertion"
    RELATION    = "relation"
    ENTITY      = "entity"

@dataclass(frozen=True)
class EvidenceHop:
    kind: HopKind
    node_id: str
    label: str = ""
    relation_id: str = ""
    tenant_id: str = "default-tenant"

@dataclass(frozen=True)
class LineageTrace:
    subject_id: str
    direction: Literal["backward", "forward"]
    hops: tuple[EvidenceHop, ...]
    complete: bool
    first_unresolved_hop: HopKind | None = None
    unresolved_node_id: str = ""
```

Canonical chain order for backward traversal:

```text
RELATION → ASSERTION → MENTION → SEGMENT → OBSERVATION → CAPTURE → SOURCE
```

`EvidenceGraph`:

```python
class EvidenceGraph:
    def add_hop(self, hop: EvidenceHop, *, forward: str, backward: str) -> None
        # forward: id this hop is derived FROM; backward: id this hop derives

    def backward(self, node_id: str) -> LineageTrace     # relation → source
    def forward(self, node_id: str) -> LineageTrace      # source → relation
```

Traversal is depth-limited by the canonical chain order and **stops at the first missing
hop**, returning `complete=False` with `first_unresolved_hop` set — never an empty list
(FR-033). A hop whose `relation_id` is set appears on forward traces so each derived relation
is returned with the assertion that grounds it (FR-032).

`independence_groups(observation_refs, source_family_of) -> tuple[tuple[str, ...], ...]`
groups refs by resolved source family so copied/derived sources collapse into one group
(FR-034).

---

## 9. Store contracts

```python
class RelationStore(Protocol):
    def write(self, claim: RelationClaim, *, provenance: Mapping[str, Any]) -> str: ...
    def get(self, relation_id: str) -> RelationClaim | None: ...
    def revisions(self, logical_relation_id: str) -> tuple[RelationClaim, ...]: ...
    def by_type(self, relation_type: str, *, active_at: datetime | None = None) -> list[RelationClaim]: ...
    def participants(self, ref: str) -> list[RelationClaim]: ...
    def checksum(self) -> str: ...
```

- `write` enforces provenance (I-12) and is idempotent on `relation_id` (I-11).
- `by_type(..., active_at=...)` filters on `is_active_at`.
- `participants` is directional: for a `DIRECTED`/`TEMPORAL` claim, `ref == subject_ref`
  matches; for `UNDIRECTED`/`NARY`, either endpoint matches.
- `checksum` is order-independent: claims sorted by `relation_id`, then
  `digest128` over the joined `content_hash` list.

`InMemoryRelationStore` is the reference implementation and the rebuild oracle.

### 9.1 Existing `GraphEdge` changes

```python
@dataclass(frozen=True)
class GraphEdge:
    edge_id: str                     # NEW, required
    edge_type: str
    source: str
    target: str
    properties: dict[str, Any] = field(default_factory=dict)
```

`__hash__` and `__eq__` both key on `(edge_id,)` so two edges with the same endpoints but
different ids are distinct entries and idempotency is by id, not by triple. `edge_id` is
supplied by the caller (the relation layer), not invented by the store.

`InMemoryGraphStore.neighbors(node_id, edge_type=None, direction="out")`:

- `direction` in `{"in", "out", "both"}`;
- default resolved from the stored edge's arity mode when the caller omits it:
  `out` for `DIRECTED`/`TEMPORAL`, `both` for `UNDIRECTED`/`NARY`;
- `out` returns `target`, `in` returns `source`, `both` returns the union;
- backwards-compatible with the existing two-positional-argument call form.

`write_hyperedge` idempotency fix: `if edge.edge_id in self._hyperedges: return edge.edge_id`
(the current `if edge in self._hyperedges` tests a `HyperEdge` against `str` keys and is
always false).

### 9.2 Neo4j adapter changes

`write_edge` emits a `MERGE` on `rel_id` and sets the full property payload:

```cypher
MATCH (a {node_id:$source}), (b {node_id:$target})
MERGE (a)-[r:TYPE {rel_id:$rel_id}]->(b)
SET r += $props
RETURN r
```

`write_hyperedge` additionally sets `rel_id`. Label sanitisation additionally rejects
non-ASCII alphanumerics so a Cyrillic-derived relation type cannot produce an invalid label.

### 9.3 Rebuildable wrapper changes

- forwards `write_hyperedge`;
- `snapshot()` records the `projection_id` it snapshotted instead of generating a fresh one;
- `checksum` sorts by `(edge_id,)` not `str(edge)`, so it is stable under property
  reordering;
- `rebuild(projection_id, from_offset=0)` honours the supplied offset.

---

## 10. Persistence

### 10.1 New tables (migration `016_relation_evidence_graph`)

**`evidence_context`**

| column | type | notes |
|---|---|---|
| `context_id` | `String(64)` PK | `CX-` + 32 hex = 35 chars |
| `tenant_id` | `String(36)` | not null |
| `investigation_id` | `String(36)` | not null, default `''` |
| `entity_anchor` | `String(64)` | not null, default `''` |
| `observation_id` | `String(64)` | not null, default `''` |
| `source_id` | `String(64)` | not null, default `''` |
| `document_id` | `String(96)` | not null, default `''` |
| `segment_id` | `String(96)` | not null, default `''` |
| `subject_candidate_ids` | `JSONB` | not null |
| `object_candidate_ids` | `JSONB` | not null |
| `observed_at` | `DateTime(timezone=True)` | nullable |
| `published_at` | `DateTime(timezone=True)` | nullable |
| `valid_from` | `DateTime(timezone=True)` | nullable |
| `valid_to` | `DateTime(timezone=True)` | nullable |
| `source_family` | `String(64)` | not null, default `''` |
| `independence_group` | `String(64)` | not null, default `''` |
| `language` | `String(8)` | not null, default `''` |
| `location_context` | `String(128)` | not null, default `''` |
| `extraction_version` | `String(32)` | not null, default `''` |
| `normalization_version` | `String(32)` | not null, default `''` |
| `ontology_version` | `String(64)` | not null, default `''` |
| `completeness` | `String(16)` | not null, server_default `'complete'` |
| `trust_state` | `String(16)` | not null, server_default `'unverified'` |
| `policy_snapshot_ref` | `String(96)` | not null, default `''` |
| `parent_context_id` | `String(64)` | not null, default `''` |
| `frame_fingerprint` | `String(64)` | not null |
| `created_at` | `DateTime(timezone=True)` | `server_default=now()` |

Indexes: `ix_evidence_context_tenant`, `ix_evidence_context_observation`,
`ix_evidence_context_source`, `ix_evidence_context_investigation`,
`uq_evidence_context_fingerprint` on `(tenant_id, frame_fingerprint)` unique.

**`relation_claim`**

| column | type | notes |
|---|---|---|
| `relation_id` | `String(64)` PK | `RC-` + 32 hex = 35 chars |
| `logical_relation_id` | `String(64)` | not null, indexed |
| `revision_number` | `Integer()` | not null, server_default `1` |
| `tenant_id` | `String(36)` | not null |
| `investigation_id` | `String(36)` | not null, default `''` |
| `relation_type` | `String(128)` | not null |
| `arity_mode` | `String(16)` | not null |
| `subject_ref` | `String(64)` | not null |
| `object_ref` | `String(64)` | not null |
| `role_bindings` | `JSONB` | not null |
| `valid_from` | `DateTime(timezone=True)` | nullable |
| `valid_to` | `DateTime(timezone=True)` | nullable |
| `observed_at` | `DateTime(timezone=True)` | nullable |
| `published_at` | `DateTime(timezone=True)` | nullable |
| `known_from` | `DateTime(timezone=True)` | nullable |
| `known_until` | `DateTime(timezone=True)` | nullable |
| `assertion_refs` | `JSONB` | not null |
| `observation_refs` | `JSONB` | not null |
| `context_ref` | `String(64)` | not null |
| `source_independence_groups` | `JSONB` | not null |
| `extraction_version` | `String(32)` | not null, default `''` |
| `normalization_version` | `String(32)` | not null, default `''` |
| `ontology_version` | `String(64)` | not null, default `''` |
| `schema_version` | `String(32)` | not null, default `''` |
| `status` | `String(24)` | not null, server_default `'active'` |
| `confidence` | `Float()` | not null, server_default `0.5` |
| `evidence_grade` | `String(16)` | not null, server_default `'ungraded'` |
| `created_by` | `String(128)` | not null, default `''` |
| `supersedes` | `String(64)` | not null, default `''` |
| `contradicts` | `JSONB` | not null |
| `content_hash` | `String(64)` | not null |
| `created_at` | `DateTime(timezone=True)` | `server_default=now()` |

Indexes: `ix_relation_claim_tenant`, `ix_relation_claim_logical` on
`(tenant_id, logical_relation_id)`, `ix_relation_claim_type` on
`(tenant_id, relation_type)`, `ix_relation_claim_subject` on
`(tenant_id, subject_ref)`, `ix_relation_claim_object` on `(tenant_id, object_ref)`,
`ix_relation_claim_context` on `context_ref`,
`uq_relation_claim_content` on `(tenant_id, content_hash)` unique.

**`relation_claim_revision`** — append-only revision ledger.

| column | type | notes |
|---|---|---|
| `revision_row_id` | `String(96)` PK | `logical_id` + `-r` + revision number |
| `relation_id` | `String(64)` | not null |
| `logical_relation_id` | `String(64)` | not null |
| `revision_number` | `Integer()` | not null |
| `tenant_id` | `String(36)` | not null |
| `valid_from` / `valid_to` | `DateTime(timezone=True)` | nullable |
| `context_ref` | `String(64)` | not null |
| `status` | `String(24)` | not null |
| `evidence_grade` | `String(16)` | not null |
| `recorded_at` | `DateTime(timezone=True)` | `server_default=now()` |

Indexes: `ix_relation_claim_revision_logical` on `(tenant_id, logical_relation_id,
revision_number)` unique, `ix_relation_claim_revision_relation` on `relation_id`.

**`relation_schema_version`**

| column | type | notes |
|---|---|---|
| `schema_row_id` | `String(96)` PK | |
| `relation_type` | `String(128)` | not null |
| `schema_version` | `String(32)` | not null |
| `arity_mode` | `String(16)` | not null |
| `temporal_semantics` | `String(24)` | not null |
| `admission_rule_id` | `String(64)` | not null |
| `definition` | `JSONB` | not null |
| `tenant_id` | `String(36)` | not null |
| `registered_at` | `DateTime(timezone=True)` | `server_default=now()` |

Indexes: `uq_relation_schema_version` on `(tenant_id, relation_type, schema_version)` unique,
`ix_relation_schema_version_type` on `(tenant_id, relation_type)`.

**`claim_context_lineage`**

| column | type | notes |
|---|---|---|
| `lineage_id` | `String(128)` PK | content-addressed |
| `tenant_id` | `String(36)` | not null |
| `relation_id` | `String(64)` | not null |
| `direction` | `String(16)` | not null, `backward` \| `forward` |
| `hops` | `JSONB` | not null |
| `complete` | `Boolean()` | not null |
| `first_unresolved_hop` | `String(24)` | nullable |
| `unresolved_node_id` | `String(64)` | not null, default `''` |
| `created_at` | `DateTime(timezone=True)` | `server_default=now()` |

Indexes: `ix_claim_context_lineage_relation` on `(tenant_id, relation_id, direction)`.

### 10.2 Migration order (enforced by test)

1. Create the five tables.
2. Add columns (none — all new tables).
3. Backfill (none required; recorded as a no-op assertion for future revisions).
4. Create indexes — including the unique ones, only after any backfill.
5. `downgrade()` in strict reverse: indexes → tables.

Revision id `016_relation_evidence_graph`, `down_revision = "015_worldline_reconstruction"`.
Revision `015` is treated as immutable; `test_migration_016_forward_only.py` pins it by
SHA-256 and asserts exactly one root and one head.

---

## 11. Event vocabulary

New event types on the existing envelope, keys as noted:

| event | key | payload |
|---|---|---|
| `relation.claim.created` | `relation_id` | full claim dict |
| `relation.claim.revised` | `logical_relation_id` | `{logical_relation_id, relation_id, revision_number, supersedes}` |
| `relation.claim.superseded` | `relation_id` | `{relation_id, superseded_by}` |
| `relation.claim.contradicted` | `relation_id` | `{relation_id, contradicts[]}` |
| `context.registered` | `context_id` | full frame dict |
| `context.validation.recorded` | `relation_id` | `{relation_id, context_id, verdict, layers, reasons, grade_components, evaluated_versions}` |

Every payload carries refs and versions, never blobs (constitution III).
