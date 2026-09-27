# API Contract: Relation & Evidence Graph Fabric

**Feature**: [016-relation-evidence-graph-fabric](../spec.md) | **Date**: 2026-09-26
**Base path**: `/api/v1` | **Auth**: existing tenant resolution (`api.auth.resolve_tenant`);
no new authentication path is introduced

---

## Conventions

**Router.** One new module, `apps/control-plane/api/relations.py`, declaring three routers
that are mounted in `apps/control-plane/api/main.py` with the existing loop
(`app.include_router(_router, prefix="/api/v1")`):

| Router | Prefix | Tags | Endpoints |
| --- | --- | --- | --- |
| `relations_router` | `/relations` | `relations` | claim read, list, revisions, context, validate, backward lineage |
| `contexts_router` | `/contexts` | `relations` | `GET /contexts/{context_id}` |
| `lineage_router` | `/lineage` | `relations` | `GET /lineage/source/{source_id}` |

**Tenant dependency.** Every handler takes
`ctx: Annotated[TenantContext, Depends(resolve_tenant)]` and issues exactly one
tenant-scoped query per request. `ctx.tenant_id` is never taken from the request body, a
query parameter or a path segment.

**Serialisation.** `application/json` throughout. All instants are RFC 3339 with an
explicit offset, serialised with a `+00:00` suffix (`2026-09-24T08:12:03+00:00`).
`null` is emitted for an absent optional timestamp; an empty tuple is `[]` and an empty
string is `""`. Enum values are the lowercase `StrEnum` values from
[data-model.md](../data-model.md) (`"directed"`, `"active"`, `"strong"`, `"valid"`,
`"cross_source"`).

**Identifiers.** `RC-` + 32 hex characters (`relation_id`), `RL-` + 32 hex
(`logical_relation_id`), `CX-` + 32 hex (`context_id`), all produced by
`digest128` — a 128-bit truncated SHA-256 (FR-004). No identifier in this API is derived
from the 32-bit FNV-1a helper. Identifiers appearing in the examples below are
illustrative digests: the identity material and derivation rules are normative in
data-model.md §4.1, and **these examples are not golden vectors** and are not asserted
byte-for-byte by any test.

**The claim object.** One representation is used everywhere a claim appears
(`GET /relations/{id}` → `relation`, `GET /relations` → `relations[]`,
`GET /relations/by-logical/{id}` → `revisions[]`). It carries every `RelationClaim` field
from data-model.md §4.2 plus the three derived fields:

```json
{
  "relation_id": "RC-4c1f9ab27d5e8036b14ac95f2e7d3068",
  "logical_relation_id": "RL-8b2d5f0a71c34e96a4d80b53f2c7e119",
  "revision_number": 1,
  "relation_type": "works_for",
  "arity_mode": "directed",
  "subject_ref": "ENT-1042",
  "object_ref": "ENT-2087",
  "role_bindings": [],
  "valid_from": "2017-01-01T00:00:00+00:00",
  "valid_to": null,
  "observed_at": "2026-09-24T08:12:03+00:00",
  "published_at": "2026-09-24T09:40:00+00:00",
  "known_from": "2026-09-24T08:12:03+00:00",
  "known_until": null,
  "assertion_refs": ["ASR-77c1e04b"],
  "observation_refs": ["OBS-CC-7f31c0", "OBS-CC-b2048e", "OBS-WB-4a90de"],
  "context_ref": "CX-6e0a41c8b93d27f5a4c68e0b1d7f9235",
  "source_independence_groups": [
    ["OBS-CC-7f31c0", "OBS-CC-b2048e"],
    ["OBS-WB-4a90de"]
  ],
  "extraction_version": "rel-extract-2.4.0",
  "normalization_version": "norm-1.9.2",
  "ontology_version": "ontology-v3",
  "schema_version": "3",
  "status": "active",
  "confidence": 0.81,
  "evidence_grade": "strong",
  "tenant_id": "t-acme",
  "investigation_id": "INV-77",
  "created_by": "interp-rel-extract-2.4.0",
  "supersedes": "",
  "contradicts": [],
  "created_at": "2026-09-24T08:12:07+00:00",
  "content_hash": "0b91c7d4e6a2f83045b19d7c8e2a6f53",
  "independent_source_count": 2,
  "publication_count": 3
}
```

**Independence is never collapsed (constitution IV).** `independent_source_count` and
`publication_count` are two separate fields and are never combined into one score, ratio or
weight. In the example above three observations were published but only two are
independent: the two Common Crawl captures share `source_family: "common_crawl"` and
collapse into one `IndependenceGroup`. A client that wants a single number must compute it
itself; the API never supplies one (FR-034, FR-025, SC-004).

**No truth, no boolean.** `status`, `evidence_grade` and `grade_components` are returned
separately and a superseded, retracted or contradicted claim is as queryable as an active
one — this API has no delete path and no endpoint that mutates a claim (FR-006,
constitution invariant I-3).

**Refs only.** No response carries document text, a segment body, a WARC record or any
other raw blob. `observation_id`, `source_id`, `document_id`, `segment_id` and
`evidence_ref` values are references into the content-addressed object store
(constitution I-5 / III).

---

## Endpoints

### GET /api/v1/relations/{relation_id}

One claim revision, with its identity, version and support separated.

**Request body**: none.

**Path parameters**

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `relation_id` | string | yes | — | `RC-` + 32 hex. A `logical_relation_id` is **not** accepted here; use `/relations/by-logical/{id}`. |

**Response `200`**

```json
{
  "tenant_id": "t-acme",
  "relation": { "…": "the claim object shown in Conventions" },
  "logical_relation_id": "RL-8b2d5f0a71c34e96a4d80b53f2c7e119",
  "revision_number": 1,
  "content_hash": "0b91c7d4e6a2f83045b19d7c8e2a6f53",
  "independent_source_count": 2,
  "publication_count": 3
}
```

`logical_relation_id`, `revision_number`, `content_hash`, `independent_source_count` and
`publication_count` are lifted out of `relation` so a list client can index a claim without
walking the object. **Invariant**: each lifted value MUST equal the corresponding
`relation.<field>`. There is no `evidence_score`, `confidence_total` or equivalent field,
and there never will be: support is reported as these separate components (constitution IV,
FR-025).

A claim with `status` `superseded`, `retracted`, `contradicted` or `quarantined` is
returned with `200` and its status intact; such a claim is never hidden and never deleted
(FR-006).

**Errors**: `404 relation_not_found`; `403 cross_tenant_access`; `422 validation_request_invalid`
(malformed `relation_id`, not `RC-` + 32 hex).

**Satisfies**: FR-001, FR-003, FR-005, FR-006, FR-025, FR-034, FR-047, FR-048.

---

### GET /api/v1/relations/by-logical/{logical_relation_id}

The revision chain of one relation, oldest first — the answer to "what did we believe
about this relation, and when did we change our mind".

**Request body**: none.

**Path parameters**

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `logical_relation_id` | string | yes | — | `RL-` + 32 hex. Must match `RL-` + 32 hex. |

**Response `200`**

```json
{
  "tenant_id": "t-acme",
  "logical_relation_id": "RL-8b2d5f0a71c34e96a4d80b53f2c7e119",
  "revisions": [
    {
      "relation_id": "RC-4c1f9ab27d5e8036b14ac95f2e7d3068",
      "revision_number": 1,
      "valid_from": "2017-01-01T00:00:00+00:00",
      "valid_to": null,
      "status": "superseded",
      "content_hash": "0b91c7d4e6a2f83045b19d7c8e2a6f53",
      "context_ref": "CX-6e0a41c8b93d27f5a4c68e0b1d7f9235",
      "independent_source_count": 2,
      "publication_count": 3,
      "evidence_grade": "strong",
      "supersedes": "",
      "superseded_by": "RC-91d7c0e45a2b6f38c07e15b9da3f2846",
      "created_at": "2026-09-24T08:12:07+00:00"
    },
    {
      "relation_id": "RC-91d7c0e45a2b6f38c07e15b9da3f2846",
      "revision_number": 2,
      "valid_from": "2017-01-01T00:00:00+00:00",
      "valid_to": "2022-12-31T00:00:00+00:00",
      "status": "active",
      "content_hash": "5c72e1a0b48d63f9a2e05c7b13d8f6a4",
      "context_ref": "CX-2f6c8b1d47a0e935c218b74da60f5e83",
      "independent_source_count": 2,
      "publication_count": 3,
      "evidence_grade": "strong",
      "supersedes": "RC-4c1f9ab27d5e8036b14ac95f2e7d3068",
      "superseded_by": "",
      "created_at": "2026-09-24T16:05:41+00:00"
    }
  ],
  "current_relation_id": "RC-91d7c0e45a2b6f38c07e15b9da3f2846"
}
```

`revisions` is ordered strictly ascending by `revision_number`, contiguously numbered
from `1`, with no gaps and no duplicates. Each element is the **revision summary** — the
full claim object minus the evidence-list fields (`assertion_refs`, `observation_refs`,
`source_independence_groups`), plus `superseded_by`, so the chain stays readable; use
`GET /relations/{relation_id}` for the full object. `current_relation_id` is the
`relation_id` of the highest `revision_number`; the chain is returned in full even when the
current revision is `retracted` or `quarantined`.

**Errors**: `404 relation_not_found` (no revision of that logical id in the tenant);
`403 cross_tenant_access`; `422 validation_request_invalid` (malformed
`logical_relation_id`).

**Satisfies**: FR-001, FR-003, FR-006, FR-047.

---

### GET /api/v1/relations

Tenant-scoped relation search with optional type, participant, interval and status
filters.

**Request body**: none.

**Query parameters**

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `relation_type` | string | no | — | Exact match on `relation_type`, e.g. `works_for`. |
| `subject_ref` | string | no | — | For `directed`/`temporal` arity, matches claims whose `subject_ref` equals the value. For `undirected`/`nary` arity, matches a claim in which the value occupies **any** role (`participants()` semantics, data-model.md §9). |
| `object_ref` | string | no | — | Same rule, mirrored onto the object slot. A value that is both `subject_ref` and `object_ref` on one `DIRECTED` claim matches that claim twice-over only as a single row. |
| `active_at` | string (ISO 8601) | no | — | Restricts to claims where `is_active_at(active_at)` is true, i.e. `valid_from <= t <= valid_to` treating a null bound as open. A claim with both bounds null matches no instant. |
| `status` | string | no | — | One of `active`, `superseded`, `retracted`, `contradicted`, `quarantined`. Omitted means **all** statuses, so superseded knowledge stays visible (FR-006). Repeating the parameter is not supported; use `status` once. |
| `limit` | integer | no | `100` | Page size. `1 <= limit <= 1000`; a value outside the range is `400 invalid_request`. |
| `offset` | integer | no | `0` | Rows to skip, `>= 0`. |

No filter at all is a valid request and returns the tenant's most recent claims first.
Ordering is deterministic: `created_at` descending, `relation_id` ascending as the
tie-break, so paging is stable.

**Response `200`**

```json
{
  "tenant_id": "t-acme",
  "relations": [
    { "…": "claim object — RC-91d7c0e4…, revision_number 2, status active" },
    { "…": "claim object — RC-4c1f9ab2…, revision_number 1, status superseded" }
  ],
  "total": 2,
  "limit": 100,
  "offset": 0
}
```

`total` is the tenant-scoped count matching the filters **ignoring** `limit`/`offset`, so a
client can page without over-fetching. `relations` may be shorter than `limit` on the last
page and is `[]` — never `null` — when the page is past the end.

**Errors**: `400 invalid_request` (`limit`/`offset` out of range, unparseable `active_at`,
unknown `status` value); `403 cross_tenant_access`; `422 validation_request_invalid`
(non-integer `limit`/`offset`).

**Satisfies**: FR-001, FR-006, FR-010, FR-047, FR-048.

---

### GET /api/v1/relations/{relation_id}/context

The immutable `EvidenceContext` frame a claim was permitted to be interpreted in. The frame
is shared by reference; the response is the frame itself, not a copy embedded in the claim
(FR-018).

**Request body**: none.

**Path parameters**

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `relation_id` | string | yes | — | `RC-` + 32 hex. |

**Response `200`**

```json
{
  "tenant_id": "t-acme",
  "relation_id": "RC-4c1f9ab27d5e8036b14ac95f2e7d3068",
  "context_id": "CX-6e0a41c8b93d27f5a4c68e0b1d7f9235",
  "resolved": true,
  "context": {
    "context_id": "CX-6e0a41c8b93d27f5a4c68e0b1d7f9235",
    "tenant_id": "t-acme",
    "investigation_id": "INV-77",
    "entity_anchor": "ENT-1042",
    "observation_id": "OBS-CC-7f31c0",
    "source_id": "SRC-cc-main-2025-30",
    "document_id": "DOC-4f1c9ab2",
    "segment_id": "SEG-4f1c9ab2-p3-s18",
    "subject_candidate_ids": ["CAN-9d2f10"],
    "object_candidate_ids": ["CAN-5b71ae"],
    "observed_at": "2026-09-24T08:11:58+00:00",
    "published_at": "2026-09-24T09:39:12+00:00",
    "valid_from": "2017-01-01T00:00:00+00:00",
    "valid_to": null,
    "source_family": "common_crawl",
    "independence_group": "ig-cc-7f31c0",
    "language": "en",
    "location_context": "GB-LND",
    "extraction_version": "rel-extract-2.4.0",
    "normalization_version": "norm-1.9.2",
    "ontology_version": "ontology-v3",
    "completeness": "complete",
    "trust_state": "verified",
    "policy_snapshot_ref": "pol-2026-09-20T00:00Z",
    "parent_context_id": "",
    "frame_fingerprint": "6e0a41c8b93d27f5a4c68e0b1d7f9235",
    "created_at": "2026-09-24T08:11:59+00:00"
  }
}
```

`frame_fingerprint` is the unprefixed `digest128` over the canonical frame content — the
same material as `context_id`, retained so the unique index on
`(tenant_id, frame_fingerprint)` does not depend on the id prefix. The frame is frozen:
there is no write, patch or delete verb for a context anywhere in this API, and a frozen
frame cannot be mutated in process (FR-015). `completeness` and `trust_state` are reported
as stored; they are *not* corrected upward on read, and a `partial` frame is never
presented as `complete` (US3 AS-4).

**Errors**: `404 relation_not_found` (claim absent); `404 context_not_found` (claim absent
from the context registry, e.g. garbage-collected — the claim is still readable through
`GET /relations/{relation_id}`, which is how the discrepancy becomes visible);
`400 context_unresolved` (the claim's `context_ref` is present but does not resolve);
`400 context_parent_cycle` (the `parent_context_id` chain is cyclic — the resolver
refuses to return a frame whose ancestry cannot be walked, and the cycle is preserved in
the store for inspection, never resolved to a default frame); `403 cross_tenant_access`.

**Satisfies**: FR-013, FR-014, FR-015, FR-016, FR-017, FR-018, FR-047, FR-048.

---

### POST /api/v1/relations/{relation_id}/validate

Runs the seven-layer `ContextValidator` over one claim and returns the graded
`ValidationResult`. The verdict is computed on demand from the claim, its frame, the
registered `RelationSchema` and the injected `ValidationWorld`.

**Request body**: optional, and an empty object is valid. Omitting the body entirely is
equivalent to `{}`. The body is reserved; a non-empty object is rejected.

```json
{}
```

**Path parameters**

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `relation_id` | string | yes | — | `RC-` + 32 hex. |

**Side effects**: none on the claim and none on the frame — `validate()` is pure and does
not mutate its inputs (FR-021). The only permitted side effect is the durable
`context.validation.recorded` record emitted through the same outbox as the event
contract, so the verdict is replayable (FR-050). The endpoint returns `200`, never `201`:
the claim's status, grade and versions are not changed by a validation run.

**Response `200`** — the full `ValidationResult`:

```json
{
  "tenant_id": "t-acme",
  "verdict": "invalid",
  "layers": {
    "structural": "passed",
    "semantic": "passed",
    "temporal": "failed",
    "provenance": "passed",
    "identity": "passed",
    "cross_source": "passed",
    "graph_constraints": "passed"
  },
  "reasons": [
    {
      "code": "temporal_interval_inverted",
      "layer": "temporal",
      "detail": "valid_from 2025-01-01T00:00:00+00:00 is after valid_to 2020-12-31T00:00:00+00:00",
      "evidence": ["RC-7d10b8e2c4f6a1903b5e8d7c2a6f4e13"]
    }
  ],
  "evidence_grade": "moderate",
  "grade_components": {
    "independent_source_count": 1,
    "publication_count": 2,
    "completeness": "partial",
    "trust_state": "attested",
    "confidence": 0.62
  },
  "claim_id": "RC-7d10b8e2c4f6a1903b5e8d7c2a6f4e13",
  "context_id": "CX-0a3f6d19c7b24e85f61a0c93b8d47e2",
  "evaluated_versions": {
    "extraction_version": "rel-extract-2.4.0",
    "normalization_version": "norm-1.9.2",
    "ontology_version": "ontology-v3",
    "schema_version": "3"
  }
}
```

Contract rules on this response:

1. **Never a boolean.** There is no `valid`, `ok`, `passed` or `is_valid` field anywhere in
   the body, at any nesting level. A caller receives a graded verdict plus structured
   reasons, never a truth value (FR-021, SC-004).
2. **All seven layers, always.** `layers` contains every one of `structural`, `semantic`,
   `temporal`, `provenance`, `identity`, `cross_source`, `graph_constraints` — all seven
   keys are present even when an earlier layer has already failed, each with one of
   `passed`, `failed`, `indeterminate`, `noted`. A missing key is a contract violation, not
   a shorthand for "passed" (FR-019).
3. **`reasons` is non-empty whenever `verdict != "valid"`.** An empty `reasons` list with
   any verdict other than `valid` is a contract violation. `reasons` **may** be non-empty
   when `verdict == "valid"` — a `valid` verdict with a `temporal_non_overlap` note is the
   normal shape for two disjoint revisions of one relation (FR-024).
4. **`verdict` is one of** `valid`, `invalid`, `underdetermined`, `incomplete`,
   `conflicting`, `stale`, chosen by the fixed precedence
   `invalid > conflicting > stale > incomplete > underdetermined > valid`.
5. **`grade_components` are components, not a score.** The five keys are returned
   individually; the API never emits a combined grade number, and `evidence_grade` is the
   enumerated label (`strong` / `moderate` / `weak` / `ungraded`) from the data-model table,
   never a float (constitution IV, FR-025).

Fixture matrix — one row per scenario, all seven layers evaluated in every row:

| Claim | Verdict | Failing/noting layer | Reason code |
| --- | --- | --- | --- |
| `RC-4c1f9ab2…` (rev 1, three observations / two independent) | `valid` | `temporal: noted` | `temporal_non_overlap` |
| `RC-7d10b8e2…` (`valid_from` 2025 > `valid_to` 2020) | `invalid` | `temporal: failed` (structural still `passed`) | `temporal_interval_inverted` |
| `RC-3a5e0d91…` (`DOCUMENT --works_for--> ORGANIZATION`) | `invalid` | `semantic: failed` | `schema_subject_class_not_allowed` |
| `RC-5c82f4ae…` (evidence observation in another tenant) | `invalid` | `provenance: failed` | `provenance_tenant_mismatch` |
| `RC-9b47c0d2…` (relation type absent from the registry) | `underdetermined` | `semantic: indeterminate` | `schema_unregistered` |
| `RC-1f6d3b85…` (no declared extractor version) | `underdetermined` | `provenance: indeterminate` | `extraction_version_undeclared` |
| `RC-8d20a7f4…` (context declares `ontology-v2`, active pack is `ontology-v3`) | `stale` | `provenance: failed` | `ontology_version_stale` |
| `RC-6e51f3c7…` (`context_ref` does not resolve) | `invalid` | `provenance: failed` | `context_unresolved` |
| `RC-2c90b8d4…` (overlapping interval, conflicting `object_ref`) | `conflicting` | `temporal: failed` | `temporal_interval_conflict` |
| `RC-40b7e1a6…` (`graph_constraints`: endpoint not an admitted entity) | `invalid` | `graph_constraints: failed` | `graph_endpoint_unknown` |
| `RC-e71c4b90…` (endpoint known but unadmitted) | `underdetermined` | `graph_constraints: indeterminate` | `graph_endpoint_unadmitted` |

`schema_subject_class_not_allowed` states both the offending class and the allowed set in
`detail`, e.g. `subject class DOCUMENT is not in {PERSON, ORGANIZATION} for relation
works_for (schema_version 3)`. `schema_unregistered` is `underdetermined`, never `invalid`:
an unknown relation is not a false relation (FR-023, SC-008). A `STALE` verdict leaves the
claim unchanged — staleness is a property of the ontology pack in force, not a retraction.

**Errors**: `404 relation_not_found`; `400 invalid_request` (a validator invariant was
violated and the run could not be completed — the partial `layers` map is discarded, never
returned half-filled); `422 validation_request_invalid` (body present and not an empty
object, or a malformed `relation_id`); `403 cross_tenant_access`.

**Satisfies**: FR-019, FR-020, FR-021, FR-022, FR-023, FR-024, FR-025, FR-047, FR-050.

---

### GET /api/v1/relations/{relation_id}/lineage

Backward evidence lineage for one claim: every hop from the relation down to the raw
source, each labelled with its hop kind.

**Request body**: none.

**Path parameters**

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `relation_id` | string | yes | — | `RC-` + 32 hex. |

**Response `200`**

```json
{
  "tenant_id": "t-acme",
  "subject_id": "RC-4c1f9ab27d5e8036b14ac95f2e7d3068",
  "direction": "backward",
  "hops": [
    { "kind": "relation",    "node_id": "RC-4c1f9ab27d5e8036b14ac95f2e7d3068", "label": "works_for",  "relation_id": "", "tenant_id": "t-acme" },
    { "kind": "assertion",   "node_id": "ASR-77c1e04b", "label": "ASR-77c1e04b", "relation_id": "", "tenant_id": "t-acme" },
    { "kind": "mention",     "node_id": "MNT-5b20ad91", "label": "\"Ivan Petrov, Chief Executive Officer of Acme\"", "relation_id": "", "tenant_id": "t-acme" },
    { "kind": "segment",     "node_id": "SEG-4f1c9ab2-p3-s18", "label": "segment 18, paragraph 3", "relation_id": "", "tenant_id": "t-acme" },
    { "kind": "observation", "node_id": "OBS-CC-7f31c0", "label": "CC-MAIN-2025-30 @ 1234,5678", "relation_id": "", "tenant_id": "t-acme" },
    { "kind": "capture",     "node_id": "CAP-9d41c07e", "label": "2026-09-24T08:11:58Z", "relation_id": "", "tenant_id": "t-acme" },
    { "kind": "source",      "node_id": "SRC-cc-main-2025-30", "label": "Common Crawl CC-MAIN-2025-30", "relation_id": "", "tenant_id": "t-acme" }
  ],
  "complete": true,
  "first_unresolved_hop": null,
  "unresolved_node_id": ""
}
```

Contract rules on this response:

1. `hops` is the **full trace in canonical chain order, starting with the origin hop**:
   `relation → assertion → mention → segment → observation → capture → source`. For a
   backward trace `hops[0].kind == "relation"` and `hops[0].node_id == subject_id`.
2. `direction` is always `"backward"` on this endpoint. There is no query parameter that
   flips it; forward lineage is `GET /api/v1/lineage/source/{source_id}`.
3. **`complete: false` always names the first unresolved hop.** When the traversal cannot
   finish, the response carries `complete: false`, a non-null `first_unresolved_hop` naming
   the `HopKind` that could not be resolved, and `unresolved_node_id` naming the node id
   that was being resolved:

```json
{
  "tenant_id": "t-acme",
  "subject_id": "RC-4c1f9ab27d5e8036b14ac95f2e7d3068",
  "direction": "backward",
  "hops": [
    { "kind": "relation",  "node_id": "RC-4c1f9ab27d5e8036b14ac95f2e7d3068", "label": "works_for", "relation_id": "", "tenant_id": "t-acme" },
    { "kind": "assertion", "node_id": "ASR-77c1e04b", "label": "ASR-77c1e04b", "relation_id": "", "tenant_id": "t-acme" },
    { "kind": "mention",   "node_id": "MNT-5b20ad91", "label": "MNT-5b20ad91", "relation_id": "", "tenant_id": "t-acme" }
  ],
  "complete": false,
  "first_unresolved_hop": "segment",
  "unresolved_node_id": "SEG-4f1c9ab2-p3-s18"
}
```

4. **A stopped traversal is never an unlabelled empty list.** The resolved prefix is always
   returned, so the only way `hops` is `[]` is a trace that failed at its very first hop —
   and that case is labelled: `hops: []` with `first_unresolved_hop: "assertion"` and the
   `unresolved_node_id` that was missing. `hops: []` **with** `complete: true` is
   impossible, and `hops: []` with `complete: false` and a null `first_unresolved_hop` is a
   contract violation. There is no `limit`/`offset` on this endpoint and no silent
   truncation (FR-031, FR-033, SC-003).
5. A hop is emitted only when every one of its `kind`, `node_id`, `label`, `relation_id`
   and `tenant_id` fields is present; `relation_id` is `""` on a backward trace and set on
   a forward trace (data-model.md §8).

**Errors**: `404 relation_not_found`; `403 cross_tenant_access`; `422 validation_request_invalid`
(malformed `relation_id`).

**Satisfies**: FR-030, FR-031, FR-033, FR-047, FR-048.

---

### GET /api/v1/contexts/{context_id}

One immutable frame by its content address. Two independently constructed frames with
identical content share this id, so this endpoint is the canonical way to prove that
(SC-009).

**Request body**: none.

**Path parameters**

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `context_id` | string | yes | — | `CX-` + 32 hex. |

**Response `200`**

```json
{
  "tenant_id": "t-acme",
  "context_id": "CX-2f6c8b1d47a0e935c218b74da60f5e83",
  "resolved": true,
  "parent_context": {
    "context_id": "CX-6e0a41c8b93d27f5a4c68e0b1d7f9235",
    "source_family": "common_crawl",
    "completeness": "complete",
    "trust_state": "verified"
  },
  "context": {
    "context_id": "CX-2f6c8b1d47a0e935c218b74da60f5e83",
    "tenant_id": "t-acme",
    "investigation_id": "INV-77",
    "entity_anchor": "ENT-1042",
    "observation_id": "OBS-REG-3c77a0",
    "source_id": "SRC-uk-registry",
    "document_id": "DOC-9b22e0d1",
    "segment_id": "SEG-9b22e0d1-p1-s04",
    "subject_candidate_ids": ["CAN-9d2f10"],
    "object_candidate_ids": ["CAN-5b71ae", "CAN-77a1c4"],
    "observed_at": "2026-09-24T15:58:11+00:00",
    "published_at": "2026-09-24T16:02:00+00:00",
    "valid_from": "2017-01-01T00:00:00+00:00",
    "valid_to": "2022-12-31T00:00:00+00:00",
    "source_family": "registry",
    "independence_group": "ig-reg-3c77a0",
    "language": "en",
    "location_context": "GB-LND",
    "extraction_version": "rel-extract-2.4.0",
    "normalization_version": "norm-1.9.2",
    "ontology_version": "ontology-v3",
    "completeness": "partial",
    "trust_state": "attested",
    "policy_snapshot_ref": "pol-2026-09-20T00:00Z",
    "parent_context_id": "CX-6e0a41c8b93d27f5a4c68e0b1d7f9235",
    "frame_fingerprint": "2f6c8b1d47a0e935c218b74da60f5e83",
    "created_at": "2026-09-24T15:58:12+00:00"
  }
}
```

`context` is the full frame, identical to the shape returned by
`GET /relations/{relation_id}/context`. `parent_context` is a **summary of the immediate
parent only** — one level, never the whole ancestry — and is `null` when
`parent_context_id` is `""`. The full ancestry is walked by the validator and by the
resolver, not serialized into this response. A frame with `completeness: "partial"` and a
`parent_context_id` set is served as stored; the endpoint does not upgrade it and does not
fail it (US3 AS-3: the frame is evidence, not a verdict).

**Errors**: `404 context_not_found`; `400 context_parent_cycle`; `403 cross_tenant_access`;
`422 validation_request_invalid` (malformed `context_id`).

**Satisfies**: FR-013, FR-014, FR-015, FR-017, FR-018, FR-047, FR-048.

---

### GET /api/v1/lineage/source/{source_id}

Forward evidence lineage from a source: every capture, observation, segment, mention,
candidate, assertion, relation and entity that the source produced.

**Request body**: none.

**Path parameters**

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `source_id` | string | yes | — | The `source_id` of the frame, e.g. `SRC-cc-main-2025-30`. Not a Kafka `source_id`; this is the evidence-source reference carried on `EvidenceContext`. |

**Response `200`**

```json
{
  "tenant_id": "t-acme",
  "subject_id": "SRC-cc-main-2025-30",
  "direction": "forward",
  "hops": [
    { "kind": "source",      "node_id": "SRC-cc-main-2025-30", "label": "Common Crawl CC-MAIN-2025-30", "relation_id": "", "tenant_id": "t-acme" },
    { "kind": "capture",     "node_id": "CAP-9d41c07e", "label": "2026-09-24T08:11:58Z", "relation_id": "", "tenant_id": "t-acme" },
    { "kind": "observation", "node_id": "OBS-CC-7f31c0", "label": "CC-MAIN-2025-30 @ 1234,5678", "relation_id": "", "tenant_id": "t-acme" },
    { "kind": "segment",     "node_id": "SEG-4f1c9ab2-p3-s18", "label": "segment 18, paragraph 3", "relation_id": "", "tenant_id": "t-acme" },
    { "kind": "mention",     "node_id": "MNT-5b20ad91", "label": "MNT-5b20ad91", "relation_id": "", "tenant_id": "t-acme" },
    { "kind": "candidate",   "node_id": "CAN-9d2f10", "label": "Ivan Petrov", "relation_id": "", "tenant_id": "t-acme" },
    { "kind": "assertion",   "node_id": "ASR-77c1e04b", "label": "ASR-77c1e04b", "relation_id": "", "tenant_id": "t-acme" },
    { "kind": "relation",    "node_id": "RC-4c1f9ab27d5e8036b14ac95f2e7d3068", "label": "works_for", "relation_id": "RC-4c1f9ab27d5e8036b14ac95f2e7d3068", "tenant_id": "t-acme" },
    { "kind": "entity",      "node_id": "ENT-2087", "label": "Acme Industrial Group", "relation_id": "RC-4c1f9ab27d5e8036b14ac95f2e7d3068", "tenant_id": "t-acme" }
  ],
  "complete": true,
  "first_unresolved_hop": null,
  "unresolved_node_id": "",
  "relations": [
    {
      "relation_id": "RC-4c1f9ab27d5e8036b14ac95f2e7d3068",
      "logical_relation_id": "RL-8b2d5f0a71c34e96a4d80b53f2c7e119",
      "revision_number": 1,
      "relation_type": "works_for",
      "assertion_ref": "ASR-77c1e04b",
      "observation_ref": "OBS-CC-7f31c0",
      "status": "superseded",
      "independent_source_count": 2,
      "publication_count": 3
    },
    {
      "relation_id": "RC-91d7c0e45a2b6f38c07e15b9da3f2846",
      "logical_relation_id": "RL-8b2d5f0a71c34e96a4d80b53f2c7e119",
      "revision_number": 2,
      "relation_type": "works_for",
      "assertion_ref": "ASR-91c8d07e",
      "observation_ref": "OBS-REG-3c77a0",
      "status": "active",
      "independent_source_count": 2,
      "publication_count": 3
    }
  ]
}
```

Contract rules on this response:

1. `hops` is in canonical forward order `source → capture → observation → segment →
   mention → candidate → assertion → relation → entity`, starting with the origin hop;
   `hops[0].kind == "source"` and `hops[0].node_id == subject_id`.
2. **Every relation-bearing hop carries its `relation_id`** in the hop's own `relation_id`
   field, so a consumer can attribute each derived relation to the exact source hop that
   produced it without re-walking the trace (FR-032). The same `relation_id` also appears
   in `hops[kind=relation].node_id`.
3. `relations` is the flattened, de-duplicated, deterministically ordered set of the claims
   the source contributed to, **each with the assertion that grounds it** (`assertion_ref`).
   Ordered by `relation_id` ascending. A relation that two observations of the same source
   both support appears **once**, with its `publication_count` reporting 2 and its
   `independent_source_count` reporting 1 — a source never inflates its own independence
   (FR-034).
4. A superseded revision is listed with `status: "superseded"`; the source's forward trace
   returns every revision it contributed to, not only the current one (FR-006).
5. `complete`, `first_unresolved_hop` and `unresolved_node_id` obey the same rules as the
   backward trace: `complete: false` always names the first unresolved hop, the resolved
   prefix is always returned, and there is no silent truncation. `complete: false` here
   means at least one branch stopped; the branches that did resolve are still returned in
   full, and `first_unresolved_hop` names the earliest `HopKind` that did not resolve
   across the whole trace.

**Errors**: `404 context_not_found` (no `EvidenceContext` in the tenant names that
`source_id` — the source has no registered frame, so there is nothing to trace);
`403 cross_tenant_access`; `422 validation_request_invalid` (empty or over-long
`source_id`).

**Satisfies**: FR-030, FR-032, FR-033, FR-034, FR-047, FR-048.

---

## Error model

Every non-2xx response uses one envelope. `detail` is retained as a string because the
repository's existing clients read `HTTPException(status_code, detail)` output; new clients
read the structured `error` object.

```json
{
  "error": {
    "code": "relation_not_found",
    "message": "no relation with relation_id 'RC-0f1a2b3c4d5e6f708192a3b4c5d6e7f8' in tenant 't-acme'",
    "tenant_id": "t-acme",
    "trace_id": "0af7651916cd43dd8448eb211c80319c",
    "details": {
      "relation_id": "RC-0f1a2b3c4d5e6f708192a3b4c5d6e7f8"
    }
  },
  "detail": "relation_not_found: no relation with relation_id 'RC-0f1a2b3c4d5e6f708192a3b4c5d6e7f8' in tenant 't-acme'"
}
```

`error.code` is the stable, machine-readable identifier and is never localised or
reworded; `error.message` is prose for a human. `error.trace_id` equals the
`correlation_id` of the emitted envelope, so a support report maps to a trace.

| Code | Status | Raised when | Endpoints |
| --- | --- | --- | --- |
| `relation_not_found` | `404` | No claim with that `relation_id`, or no revision chain for that `logical_relation_id`, is visible in the caller's tenant. | all relation endpoints |
| `context_not_found` | `404` | No frame with that `context_id` is registered, or no registered frame names that `source_id`. | `/relations/{id}/context`, `/contexts/{id}`, `/lineage/source/{id}` |
| `context_unresolved` | `400` | The claim's `context_ref` is present and non-empty but resolves to no frame (garbage-collected, or never registered). The system never substitutes a default frame and never returns a partial frame. | `/relations/{id}/context`, `/relations/{id}/validate` |
| `context_parent_cycle` | `400` | The `parent_context_id` chain from the requested frame is cyclic. The cycle is preserved in the store for inspection; it is never broken by silently dropping a link. | `/relations/{id}/context`, `/contexts/{id}` |
| `invalid_request` | `400` | A query parameter is present but outside its contract: `limit`/`offset` out of range, `active_at` present but not RFC 3339, unknown `status` value, or a validator invariant that prevented completing the run. | `/relations`, `/relations/{id}/validate` |
| `cross_tenant_access` | `403` | The identifier exists but belongs to a different tenant than the request principal. The response carries no data from the other tenant. | every endpoint |
| `validation_request_invalid` | `422` | The request itself is structurally wrong: a malformed identifier (`RC-`/`RL-`/`CX-` + 32 hex not matched), a non-integer `limit`/`offset`, or a `POST /validate` body that is present and not an empty object. | all endpoints with parameters; `/relations/{id}/validate` |

Notes:

- `404 relation_not_found` and `404 context_not_found` never disclose whether the
  identifier exists in another tenant; a cross-tenant request is refused with `403
  cross_tenant_access` **before** the existence check is answered, so a probe cannot
  distinguish "absent" from "another tenant's".
- There is no `500` contract for a validation outcome. A non-`valid` verdict is a
  successful `200` with a graded body, never an HTTP error — a claim that fails validation
  is knowledge that must be preserved and inspectable, not an API failure (FR-050,
  constitution I-3).
- Every error is emitted on the event bus as `audit.access` with the code, the principal and
  the refused identifier, so a refusal is reconstructable after the fact.

---

## Tenancy and access

**Scope resolution.** `ctx.tenant_id` from `resolve_tenant` is the only tenant source. Each
handler performs exactly one tenant-scoped read: `WHERE tenant_id = :tenant` is part of the
query, never a post-filter. A handler that cannot express its filter with the tenant
predicate does not serve the request. There is no `tenant_id` query parameter, body field
or path segment on any endpoint in this contract.

**Refusal.** A cross-tenant read returns `403 cross_tenant_access` with an `error.details`
object naming only the identifier that was requested — never a field, count or existence
signal from the owning tenant. This is a deliberate difference from the 015 surface, which
answers a cross-tenant identifier with `404`: here the refusal must be *observable to
operators*, and a silent `404` would make a mis-scoped integration indistinguishable from a
missing row. The row itself is still never disclosed, so no information leaks; the
difference is only in the status code and the audit record.

**Audit.** Every refusal emits `audit.access` with `outcome: "refused"`, the reason code
`cross_tenant_access`, the principal (`ctx.user_id`), the requesting tenant, the owning
tenant of the resolved row, the endpoint, the identifier and the `trace_id`. An audit record
is written for `403`, for `400 context_unresolved`, for `400 context_parent_cycle` and for
every `404`; a successful read is not audited by this API.

**Context resolution never defaults.** A claim whose `context_ref` does not resolve returns
`400 context_unresolved` on `/relations/{id}/context` and an
`INVALID` / `provenance: failed` / `context_unresolved` result on
`POST /relations/{id}/validate`. The system never substitutes a default frame, never
reinterprets the claim under a synthetic context, and never omits the `provenance` layer to
make the run succeed. The same claim remains readable through `GET /relations/{relation_id}`,
which is deliberate: an unresolvable context must be visible as a defect rather than hidden
by a read failure.

**Write surface.** This API is read-only apart from `POST /relations/{relation_id}/validate`,
which is a pure evaluation. Claims are written by the interpretation/admission path and
registered through `RelationStore` and the `ContextResolver`, both of which enforce
provenance on every write (I-12, FR-007, FR-036). No endpoint here can create, mutate,
supersede, retract or delete a claim or a frame.
