# Data Model: Global OSINT Intelligence Platform

**Phase 1 output** — entities, fields, relationships, validation, state transitions, invariants. Derived from `spec.md` Key Entities + master document §6–§40.

Plane keywords: **[C]** = Control, **[D]** = Data, **[B]** = Feedback. Storage annotations: `pg` = PostgreSQL, `s3` = S3/MinIO, `kafka` = event, `redis` = lease/lock, `graph` = graph projection, `os` = OpenSearch, `ch` = ClickHouse, `tda` = TDA artifacts.

## Invariants (from Constitution, mirrored here as data constraints)

- **I-1** Observation immutable: raw row and raw object are append-only; sha256 / content-address stable.
- **I-2** Mention != Candidate != Entity: three distinct tables; only Candidates link to Mentions, only Entities derive from admitted Candidates.
- **I-3** Assertion != truth: assertions carry confidence + provenance; never a "fact" source of truth.
- **I-4** Graph != source of truth: graph tables are projection snapshots with projection metadata, rebuildable from events.
- **I-5** Kafka != object store: raw objects only in S3; Kafka carries events + lineage, not payload blobs.
- **I-6** TDA != truth oracle: TopologicalFeature feeds Candidate/Findings only.
- **I-7** Admission != Priority: scores stored separately by type (never a single confidence == priority).
- **I-8** Novelty families are distinct (entity/evidence/structural) — three separate signals.
- **I-9** Search/Graph/OLAP planes separate.
- **I-10** Downstream projections rebuildable from durable evidence/events.

## 1. Investigation [C] `pg`

| field | type | notes |
|---|---|---|
| investigation_id | uuid/`INV-` | PK |
| name | text | |
| objective.type | text enum | |
| objective.description | text | |
| seeds | jsonb | initial seeds (urls, entities, queries) |
| scope.entity_types | text[] | |
| scope.source_classes | text[] | |
| scope.time_range | tsrange | valid_time window of interest |
| policy_id | fk->policy | |
| budget_network | numeric | network budget units |
| budget_compute | numeric | |
| budget_storage | numeric | |
| freshness | jsonb | freshness requirements per class |
| status | enum | DRAFT→PLANNING→RUNNING→PAUSED→COMPLETED→ARCHIVED |
| tenant_id | fk | tenancy key |
| created_at / updated_at | timestamptz | |

**State machine**: DRAFT→PLANNING→RUNNING; RUNNING↔PAUSED; RUNNING/PAUSED→COMPLETED; COMPLETED→ARCHIVED. Illegal: ARCHIVED→anything; PAUSED→PLANNING.

## 2. Policy / Budget [C] `pg`

| field | type | notes |
|---|---|---|
| policy_id | uuid | PK; versioned via policy_version on consumers |
| tenant_id | fk | |
| allowed_source_classes | text[] | |
| robots / permission rules | jsonb | robots policy, permission profile |
| rate_limits | jsonb | per-class global/tenant/investigation |
| retention | jsonb | per-source-class retention |
| version | int | immutable policy snapshot ref |

Budget attached to investigation; enforcement logs budget consumption (link to acquisition.* cost events in ClickHouse).

## 3. Source / SourceProfile [C] `pg`

| field | type | notes |
|---|---|---|
| source_id | uuid/`SRC-` | PK |
| source_type | enum | HTTP/API/Sitemap/RSS/Atom/Dataset/Document/Browser/Search/Archive |
| capabilities | text[] | capability declarations (drives AcquisitionWorker choice) |
| policy_id | fk | |
| quality_profile | jsonb | |
| historical_yield | jsonb | rolling aggregates (fed from analytics) |
| change_rate | jsonb | EWMA (change detection) |
| discovery_yield | jsonb | discovery potential stats |
| average_cost | jsonb | measured per-class cost (from bench/analytics) |
| freshness_characteristics | jsonb | |
| tenant_id | fk | |

## 4. FrontierItem [D] `pg` + `redis`

| field | type | notes |
|---|---|---|
| frontier_id | uuid/`F-` | PK |
| target.kind | enum | url / domain / query / dataset … |
| target.value | text | |
| canonical_key | text | canonicalization key (dedup) |
| source_id | fk | |
| investigation_ids | uuid[] | fan-out/coalescing |
| discovery_refs | jsonb | discovery events backing |
| priority | float | utility-derived (I-7: separate from score vectors) |
| expected_novelty | float | |
| expected_cost | float | from UtilityScorer |
| strategy | enum | HTTP / Browser / API / Feed / Dataset / Document |
| host_key | text | HOST/DOMAIN level key |
| state | enum | READY→SCHEDULED→IN_FLIGHT→RETRY→COOLDOWN→DONE→DEAD; lease via Redis |
| attempt | int | |
| next_attempt_at / lease_until | timestamptz | Lease/cooldown |

Hierarchy fields: `tenant_id → investigation_ids → source_id → host_key`. Quotas: per source/investigation enforced by scheduler reading counters.

## 5. AcquisitionTask [D] `pg`

| field | type | notes |
|---|---|---|
| task_id | uuid/`T-` | PK (idempotency key on dispatch) |
| investigation_ids | uuid[] | |
| source_id | fk | |
| target | jsonb | |
| strategy | enum | |
| priority | float | |
| attempt | int | bounded by task/source/investigation/global retry budgets |
| constraints.timeout_ms | int | |
| constraints.max_bytes | int | |
| policy_version | text | consumed policy snapshot |
| cost_estimate | jsonb | network/compute/dedup-risk from UtilityScorer |

## 6. Observation [D] `pg` + `s3` + `kafka` — IMMUTABLE

| field | type | notes |
|---|---|---|
| observation_id | uuid/`OBS-` | PK; idempotency key for consumers |
| source_id | fk | |
| target | text | canonical target |
| retrieved_at | timestamptz | HTTP fetch time |
| observed_at | timestamptz | content observation semantics |
| raw_object_uri | text | `s3://knowledge/raw/{prefix}/{sha256}` — content address |
| sha256 | text | |
| content_hash | text | normalized hash for dedup |
| mime | text | |
| size | int | |
| collector | text | e.g. `rust-http` |
| collector_version | text | |
| policy_version | text | |
| timing | jsonb | dns/tls/ttfb/total |
| provenance | jsonb | producer, producer_version, causation |
| state | enum | NEW → PARSING → ANALYZED → (immutable thereafter) |
| tenant_id | fk | |

**Immutable**: no UPDATE on content fields after write; projection processes only read + create downstream rows. Note: `observation.created/ changed/ unchanged/ duplicate` events emitted.

## 7. Mention [D] `pg` + `os`

| field | type | notes |
|---|---|---|
| mention_id | uuid/`M-` | PK |
| observation_id | fk | |
| surface_form | text | literal span — NEVER replaced by normalization |
| offsets | jsonb | byte/char offsets in raw normalized doc |
| normalized_form | text | lowercase/diacritic-folded form used by blocking/resolution |
| transliteration_variants | text[] | e.g. `["abdul aziz al-rantisi", "abdul aziz ar-rantisi", "abdul aziz rantisi"]` |
| script | enum | e.g. cyrillic / latin / arabic … |
| language | text | detected / tagged language |
| normalization_version | text | version of normalize stage producing the variants |
| type_hypothesis | enum | PERSON/ORG/LOC/DATE/… + custom + deterministic (URL/email/IP/CIDR/hash/date/doc-number/domain/crypto-address) |
| confidence | float | extractor confidence |
| extractor_version | text | NER version tag |
| tenant_id | fk | |

## 8. Candidate [D] `pg` + `os`

| field | type | notes |
|---|---|---|
| candidate_id | uuid/`C-` | PK |
| mention_ids | uuid[] | aggregated mentions |
| type | enum | |
| attributes | jsonb | |
| confidence | float | |
| state | enum | OPEN → MATCHED → SUPERSEDED → REJECTED → QUARANTINED (resolution lifecycle) |
| epistemic_status | enum | PROVISIONAL / DEFERRED / QUARANTINED / ACCEPTED / REJECTED (epistemic standing — kept SEPARATE from resolution state, FR-013) |
| tenant_id | fk | |

Candidate graph (noisy) kept separate: candidate_edges (related/possible_match/extracted_from).

## 9. Entity / EntityVersion [D] `pg` + `os` + `graph`

| field | type | notes |
|---|---|---|
| entity_id | uuid/`E-` | PK (stable identity) |
| type | enum | |
| current_version | int | |
| aliases | text[] | |
| first_seen / last_seen | timestamptz | |
| provenance_summary | text | |
| tenant_id | fk | |

EntityVersion: `entity_id, version, attributes, name, resolution_decision ref, created_at, superseded_at`. History of resolution decisions preserved (FR-016).

## 10. Assertion [D] `pg` + `os` + `graph`

| field | type | notes |
|---|---|---|
| assertion_id | uuid/`A-` | PK |
| subject | fk entity | |
| predicate | text | typed predicate |
| object | fk entity | |
| evidence_refs | jsonb | evidence link ids |
| confidence | float | |
| valid_time | tsrange | |
| observed_time | tsrange | |
| extractor_version | text | |
| provenance | jsonb | |
| state | enum | ASSERTED → SUPERSEDED \| RETRACTED \| CONTRADICTED \| EXPIRED (assertion life-cycle, FR-016) |
| temporal_policy | enum | single-valued / multi-valued / interval-valued / append-only / supersedable / contradictory (relation-specific) |
| supersedes_id / replacement_id | fk | linked replacement on SUPERSEDED/RETRACTED (original never deleted) |
| tenant_id | fk | |

## 11. EvidenceLink / Resolution [D] `pg`

| field | type | notes |
|---|---|---|
| evidence_link_id | uuid | PK |
| assertion_id / candidate_id | fk | link owner |
| observation_ids | uuid[] | backing evidence |
| publication_count | int | raw page/doc count |
| independent_sources | int | fused independence count (I: copied/derived not summed) |
| independent_evidence_chains | int | chains from Source Independence Engine (FR-015) |
| source_independence_refs | jsonb | citation/derivation-graph edge refs (cites/copies/references/rewrites) |
| provenance | jsonb | |

Resolution: `candidate_id, entity_id, match_rank, confidence, raw_pair_score, collective_score, reasons[], threshold_used, algorithm_version, blocking_keys_used, created_at` — ranked matches from the blocking→pairwise→collective pipeline (FR-012), per-type thresholds, raw + collective scores and reasons preserved (no opaque graph magic).

## 12. AdmissionDecision [D] `pg`

| field | type | notes |
|---|---|---|
| decision_id | uuid | PK |
| candidate_id / assertion_id | fk | |
| decision | enum | ACCEPT_NEW / ACCEPT_EXISTING / DEFER / REJECT / QUARANTINE |
| score_vector | jsonb | validity, relevance, novelty, resolution_confidence, source_quality, evidence_support, structural_significance (I-7) |
| reasons | text[] | |
| evidence_refs | jsonb | |
| model_version / policy_version | text | |
| created_at | timestamptz | |
| tenant_id | fk | |

Rejected candidates never auto-deleted; replay preserved (decision rows + candidate rows retained).

## 13. Projection / GraphSnapshot [D] `pg` (metadata) + `graph`/`os`/`ch`/`tda` (content)

| field | type | notes |
|---|---|---|
| projection_id | uuid | PK |
| kind | enum | SEMANTIC / EVIDENCE / CANDIDATE / TEMPORAL / INFRASTRUCTURE / SEARCH / ANALYTICAL / TDA |
| snapshot_id | uuid | rebuildable snapshot |
| base_offset / as_of | jsonb | projection offset for rebuild (I-10) |
| status | enum | IN_PROGRESS → READY → FAILED |
| rebuilt_from_version | text | evidence/event version marker |
| started_at / finished_at | timestamptz | |

## 14. TopologicalFeature [D] `pg` + `tda`

| field | type | notes |
|---|---|---|
| feature_id | uuid/`TF-` | PK |
| projection_id / snapshot_id | fk | |
| dimension | int | H0/H1/H2 (budget-bounded) |
| birth / death | float | |
| persistence | float | |
| supporting_nodes / supporting_edges | uuid[] / jsonb | |
| algorithm_version | text | e.g. `TDA-v1.2` |
| provenance | jsonb | |
| tenant_id | fk | |

Output consumed as Finding/structural signal, fed to Candidate/admission (I-6).

## 15. Finding [D] `pg` + `os`

| field | type | notes |
|---|---|---|
| finding_id | uuid | PK |
| finding_type | enum | structural/anomaly/persistence/high-info-gain… |
| why_detected | text | explanation |
| supporting feature refs | jsonb | TDA + analytics refs |
| supporting graph region | jsonb | snapshot id + subgraph ref |
| assertion refs / observation refs | jsonb | lineage |
| created_at | timestamptz | |
| tenant_id | fk | |

Full lineage walk: Finding → feature → graph/assertion → evidence → observation → raw object → source (Spec FR-032).

## 16. ModelVersion / DecisionLog [C] `pg` + `kafka` (audit)

| field | type | notes |
|---|---|---|
| model_version | text | extractor/resolver/admission/tda version tags |
| author / checksum / config | jsonb | reproducibility of outputs |
| decision_log_id | uuid | audit row per admission/projection decision |

Audit log entries in `kafka` audit topic + Postgres copy (spec: audit logs mandatory).

## 17. HostState / resource state [D] `pg` + `redis`

| field | type | notes |
|---|---|---|
| host_key | text | PK |
| etag / last_modified | text/timestamptz | conditional acquisition |
| content_hash | text | |
| last_seen / last_changed | timestamptz | |
| change_probability | float | EWMA |
| next_recrawl | timestamptz | |
| ewma_latency / error_rate / payload_size | float | adaptive schedule |
| success / retry / concurrency / cooldown | counters | scheduler state |

## 18. Coalescing / Dedup [D] `redis` + `pg`

| field | type | notes |
|---|---|---|
| canonical_key | text | request dedup key |
| observation_ids | uuid[] | coalesced fan-out targets |
| dedup layer | enum | REQUEST / CANONICAL_URL / EXACT_HASH / NEAR / SEMANTIC |
| created_at | timestamptz | |

Near/semantic dedup runs downstream (Layer 1 after parse) as separate jobs, feeding `observation.duplicate` events + duplicates KPIs.

## 19. CalibrationProfile [D] `pg`

Immutable, versioned decision profile consumed by the admission engine (FR-013, research R-9 / T086/T085). Bootstrap v1 is provisional (UNCALIBRATED, source=bootstrap_policy); later profiles are empirically CALIBRATED. Profiles are never overwritten — a new version is appended, old ones retained for reproducibility/replay.

| field | type | notes |
|---|---|---|
| profile_id | uuid/`CAL-` | PK |
| entity_type | enum | PERSON / ORGANIZATION / LOCATION / DOMAIN / … |
| language | text | if data supports per-language calibration |
| script | text | if data supports per-script calibration |
| resolver_version | text | e.g. `resolver-v7` |
| calibration_version | text | e.g. `cal-12` |
| feature_schema_version | text | feature inputs contract version |
| policy_version | text | decision policy snapshot |
| calibration_status | enum | UNCALIBRATED / CALIBRATED |
| source | text | `bootstrap_policy` or corpus/date reference |
| auto_accept_threshold | float | score at/above → ACCEPT (per-type) |
| defer_threshold | float | score at/above → DEFER band start |
| reject_threshold | float | nullable; score floor for score-driven REJECT (categorical rules take priority) |
| hard_reject_rules | jsonb | invalid identifier → REJECT; explicit contradiction → QUARANTINE/REJECT (policy); priority over scores (FR-013) |
| provenance | jsonb | how profile was produced, corpus used, author |
| effective_from / effective_to | timestamptz | activation window |
| created_at | timestamptz | |
| tenant_id | fk | |
| tagged_provisional | bool | true while UNCALIBRATED — never presented as empirical |

Bootstrap v1 (provisional, conservative) per user sign-off:

```text
PERSON:       auto_accept 0.995, defer 0.80
ORGANIZATION: auto_accept 0.98,  defer 0.75
LOCATION:     auto_accept 0.995, defer 0.85
DOMAIN:       auto_accept 0.995, defer 0.85   (deterministic path preferred)
```

## Relations summary

```
Investigation 1—* FrontierItem 1—* AcquisitionTask 1—* Observation 1—* Mention *—* Candidate *—* Entity
Candidate 1—* Assertion (subject/object→Entity) *—* EvidenceLink *—* Observation
Observation → (immutable) → Interpretation → Admission → Entity/Assertion → Projections → TDA → Findings → Feedback → FrontierItem
```

## Validation rules (from spec requirements)

- FR-001/investigation: status transitions enforced; budgets non-negative; scope time_range sane.
- FR-002/observation: non-empty sha256 + raw_object_uri before commit; no UPDATE after commit.
- FR-011: Mention rows only link to Observation; Candidate rows only to Mentions; Entity only from admitted Candidates. Mention normalization/transliteration never replaces surface_form.
- FR-012: resolution stored with raw_pair_score + collective_score + reasons + blocking_keys_used; no all-pairs candidate generation.
- FR-013: admission decision requires non-empty score_vector + reasons; categorical hard-reject rules take priority over score thresholds; DEFER is the default for insufficient evidence (epistemic conservatism).
- FR-015: valid_time/observed_time/system_time separate columns; publication_count stored separately from independent_sources / independent_evidence_chains (never equal).
- FR-016: entity versions monotonic; assertion life-cycle enforced (ASSERTED→SUPERSEDED|RETRACTED|CONTRADICTED|EXPIRED); originals and their replacement links retained.
- FR-023: every event conforms to EventEnvelope; payload matches registered proto version.
- FR-025: TDA features bounded by dimension/universe budget; never directly create Entity.
- Idempotency keys: task_id (dispatch), observation_id (consumers), event_id (event consumers).