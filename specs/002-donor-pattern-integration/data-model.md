# Data Model: Donor Pattern Integration

**Phase 1 output** — entities, fields, relationships, validation, state transitions, invariants. Derived from `spec.md` (feature 002). Reuses feature 001 entities (Investigation, Observation, Mention, Candidate, Assertion, EvidenceLink, Finding) and extends them with donor-pattern fields/tables.

Plane keywords: **[C]** = Control, **[D]** = Data. Storage annotations: `pg` = PostgreSQL, `s3` = S3/MinIO, `kafka` = event, `graph` = graph projection, `os` = OpenSearch, `ch` = ClickHouse.

## Invariants (from Constitution, mirrored here as data constraints)

- **I-1** Observation immutable (unchanged from feature 001).
- **I-2** Mention != Candidate != Entity; correlation edges never collapse Candidates into Entities.
- **I-3** Assertion != truth; statements carry confidence + provenance.
- **I-4** Graph != source of truth; correlation/review/timeline are projection artifacts.
- **I-5** Kafka != object store; ontology packs and events carry refs, not blobs.
- **I-7** Admission != Priority; claim verdict / corroboration stored as separate typed signals.
- **I-12** All downstream projections rebuildable from durable evidence/events.

## 1. Statement [D] `pg` + `os`

Extends Assertion with FTM-style statement record (FR-001).

| field | type | notes |
|---|---|---|
| statement_id | uuid/`ST-` | PK |
| assertion_id | fk | backing assertion (feature 001) |
| dataset_id | text | provenance boundary (dataset/source lineage) |
| first_seen / last_seen | timestamptz | observation window |
| original_value | text | literal value from source (never replaced) |
| extraction_version | text | extractor version tag |
| valid_from / valid_until | timestamptz | optional temporal validity window (FR-003) |
| provenance | jsonb | producer, causation, observation refs |
| tenant_id | fk | |

**Validation**: every assertion MUST have a Statement row with non-null dataset_id + extraction_version; original_value immutable (I-1).

## 2. CorrelationEdge [D] `pg` + `graph`

OpenOSINT-style possible_match edges between Candidates (FR-004).

| field | type | notes |
|---|---|---|
| edge_id | uuid/`CE-` | PK |
| candidate_a / candidate_b | fk | Candidate pair |
| kind | enum | `possible_match` / `similar` / `derivation` |
| raw_pair_score | float | blocking/pairwise score |
| reasons | text[] | blocking keys used |
| collective_score | float | nullable; post-collective propagation |
| state | enum | OPEN → REVIEWED → RESOLVED |
| created_at | timestamptz | |
| tenant_id | fk | |

**Validation**: edge creation never triggers entity merge; merge only via admitted assertion (I-2). No all-pairs generation (blocking only).

## 3. IndependenceChain [D] `pg`

investigator/FTM dataset boundary (FR-002).

| field | type | notes |
|---|---|---|
| chain_id | uuid/`IC-` | PK |
| root_observation_id | fk | original document |
| member_observation_ids | uuid[] | reprints/derivations |
| edge_kinds | jsonb | cites/copies/references/rewrites |
| independent_sources | int | distinct chains (never == publication_count) |
| publication_count | int | distinct documents (may be > independent_sources) |
| created_at | timestamptz | |

## 4. ReviewDecision [D] `pg` + `kafka`

Vitni review-as-provenance (FR-006).

| field | type | notes |
|---|---|---|
| review_id | uuid/`RV-` | PK |
| target_type | enum | candidate / assertion / correlation_edge / finding |
| target_id | fk | |
| decision | enum | ACCEPT / REJECT / UNCERTAIN |
| analyst_id | text | RBAC subject |
| reasoning | text | optional |
| reviewed_at | timestamptz | |
| provenance | jsonb | immutable; replayable via kafka event |
| tenant_id | fk | |

**Validation**: review rows are append-only; a review changes projections only via events (I-12).

## 5. Connector [C] `pg`

SpiderFoot connector registry (FR-008).

| field | type | notes |
|---|---|---|
| connector_id | uuid/`CN-` | PK |
| name | text | unique |
| source_types | text[] | HTTP/API/Feed/Dataset/… |
| capabilities | jsonb | capabilities() output |
| policy_id | fk | |
| status | enum | REGISTERED → ACTIVE → DISABLED |
| version | text | connector version |
| tenant_id | fk | |

**Validation**: connector MUST satisfy AcquisitionWorker contract (capabilities/estimate/acquire) before ACTIVE.

## 6. ReconPlan [C] `pg`

reNgine recon orchestration (FR-009).

| field | type | notes |
|---|---|---|
| plan_id | uuid/`RP-` | PK |
| investigation_id | fk | |
| strategy | jsonb | task groups, priorities, budgets |
| status | enum | PLANNED → RUNNING → COMPLETED → FAILED |
| task_ids | uuid[] | frontier/acquisition tasks |
| started_at / finished_at | timestamptz | |
| tenant_id | fk | |

**Validation**: plan status transitions enforced; tasks flow through Kafka to collectors (no custom plumbing).

## 7. OntologyPack [D] `pg` + `kafka`

kafSIEM ontology/schema pack (FR-012).

| field | type | notes |
|---|---|---|
| pack_id | uuid/`OP-` | PK |
| pack_version | text | e.g. `ontology-v3` |
| entity_types | jsonb | PERSON/ORG/LOCATION/EMAIL/PHONE/DOMAIN/USERNAME/DOCUMENT/… |
| properties | jsonb | admissible properties per type |
| relations | jsonb | admissible relations |
| status | enum | DRAFT → REGISTERED → ACTIVE |
| registered_at | timestamptz | |
| tenant_id | fk | |

## 8. Claim / Storyline [D] `pg` + `ch`

investigator evidence reasoning (FR-011).

| field | type | notes |
|---|---|---|
| claim_id | uuid/`CL-` | PK |
| assertion_refs | jsonb | supporting/contradicting assertions |
| verdict | enum | SUPPORTED / CONTRADICTED / UNCERTAIN |
| corroboration | float | independent-chain weighted |
| triangulation | jsonb | how chains triangulate |
| storyline_id | uuid | consolidated narrative cluster |
| created_at | timestamptz | |
| tenant_id | fk | |

**Validation**: verdict derived from independence chains, never raw publication count.

## 9. ParserAdapter [D] `pg` (registry)

NetForensicAI parser interface (FR-010).

| field | type | notes |
|---|---|---|
| adapter_id | uuid/`PA-` | PK |
| name | text | e.g. `pdf-parser`, `html-parser` |
| content_types | text[] | can_parse targets |
| deterministic | bool | findings reproducible |
| isolated | bool | runs in isolated worker class |
| version | text | |
| status | enum | REGISTERED → ACTIVE → DISABLED |

**Validation**: adapter MUST implement `can_parse`/`parse`; findings deterministic (same input → same output).

## Relations summary

```
Statement 1—1 Assertion (extends)
Candidate *—* Candidate via CorrelationEdge (possible_match, no auto-merge)
Observation *—* IndependenceChain (publication vs independent counts)
ReviewDecision *—> {Candidate|Assertion|CorrelationEdge|Finding}
Connector 1—* ReconPlan 1—* AcquisitionTask (frontier)
OntologyPack *—> {ExtractorRegistry, AdmissionEngine}
Claim 1—* Assertion; Claim *—* Storyline
ParserAdapter *—> ParserRegistry (can_parse/parse)
```

## Validation rules (from spec requirements)

- FR-001/statement: non-null dataset_id + extraction_version + original_value on every assertion.
- FR-002: publication_count and independent_sources stored separately; never equal unless fully independent.
- FR-003: valid_from/valid_until enforced per temporal policy (feature 001 FR-016); originals retained on retraction/supersession.
- FR-004: CorrelationEdge never auto-merges; merge only via admitted assertion.
- FR-005: DEFER default for uncertain; rejected candidates replayable (feature 001 FR-013/014).
- FR-006: ReviewDecision append-only, replayable as provenance.
- FR-008: Connector must pass AcquisitionWorker contract before ACTIVE.
- FR-010: ParserAdapter must implement can_parse/parse deterministically.
- FR-012: OntologyPack versioned, never overwritten; events carry refs not blobs (I-5).