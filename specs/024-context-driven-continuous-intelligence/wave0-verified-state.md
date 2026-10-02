# WAVE 0 — VERIFIED CURRENT STATE

Feature: 024-context-driven-continuous-intelligence
Method: read-only audit of 33 claims in `input.md` + full frontend inventory of `ui-upgrade.md`.
Verdict totals: **8 TRUE, 6 PARTIAL, 15 FALSE, 4 UNVERIFIABLE.**

This document supersedes every claim in `input.md` §0.2–§11.1. The normative target-state requirements (§12–§36) are unaffected.

---

## 1. VERDICT TABLE

### Architecture (§2)

| § | Claim | Verdict | Evidence | Corrected |
|---|---|---|---|---|
| 2.3 | Offset schema `content_digest` | FALSE | `apps/shared/domain/observation_identity.py:59-136` | Real identity: `identity_schema \| tenant_id \| capture_id \| locator \| record_digest` → digest128. `content_digest` exists only as a *Capture* input and as an alias of `record_digest()`. |
| 2.4 | Offset schema `artifact_id` | FALSE | `rg artifact_id` → only `hypergraph.py`, `co_mention.py`, specs | `artifact_id` does not exist as an addressing field. §2.3 and §2.4 describe the same mechanism; §2.3 is closer. |
| 2.5 | `runtime/` has SearXNG, Airbyte, BBOT, external-tool | TRUE | 7 files: `__init__.py`, `airbyte.py`, `bbot.py`, `external_tool.py`, `record_stream.py`, `primproc.py`, `searxng.py` | Also has `record_stream.py` (shared NDJSON framing) and `primproc.py` (decorator). TZ omitted both. |
| 2.6 | `apps/shared` has identity, events, contracts, stores, skills | PARTIAL | 15 dirs: config contracts datasets domain donor events ids network observability scoring semantic storage tests websearch workflow | Has `ids` (not `identity`), `storage` (not `stores`). `contracts/` is a **0-line stub**. **`skills/` does not exist.** |
| 2.7 | `interpretation` turns captures into observations/signals/hypotheses | PARTIAL | `interpretation/observation_consumer/`, `extractors/signals/`, `extractors/payload/hypotheses.py` | Consumes observations via `raw_ref`, not `Capture` directly. Consumer docstring: "writes no entity, no claim, no graph edge". |
| 2.8 | `apps/investigation` owns scope/tasks/worldline | FALSE | `Test-Path apps/investigation` → False | **No such app.** Investigation lives in control-plane: `investigations`, `frontier_items`, `acquisition_tasks` (`db/schema.py:121/184/227`) + `cp_domain/investigation.py` + `workflows/investigation.py`. Worldline: `apps/shared/domain/temporal_worldline*.py`. |
| 2.9 | `apps/science` owns statistical/causal/epistemic | TRUE | 14 domain subpackages, 40 src files | Confirmed. But state is in-memory only — see §7.7. |

### Context Graph (§3)

| § | Claim | Verdict | Evidence |
|---|---|---|---|
| 3.1 | Context Graph is first-class | **FALSE — does not exist** | `rg -il "context_graph"` over the whole repo returns **exactly one hit: this feature's `input.md`**. No module, no table, no migration, no route, no test. |
| 3.2 | 10 node types | FALSE | No Context Graph. Nearest existing: `investigations` (row), `relation_claim`/`relation_candidate` (claim graph), `evidence_context` (frame). `Question`, `Scope`, `EvidenceSet`, `Contradiction`, `Unknown`, `Revision` do not exist as graph nodes. |
| 3.3 | 10 edge types | FALSE | No Context Graph. Real dictionaries: `graph_invariant.py:69 TYPED_RELATIONS = {hasEvidence, depicts, inConversation}`; `HopKind` in `evidence_lineage.py:50`; `EdgeDirection` in `projection/graph/abstraction.py:26`. `supersedes`/`contradicts` are **fields on `RelationClaim`**, not edge types. |
| 3.4 | `EvidenceContext` exists as core domain | PARTIAL | `apps/shared/domain/evidence_context.py` (384 ln), table `evidence_context` (`schema.py:1112`) | Exists, but is an **evidence/provenance frame**, not a research-scope context. See §5 below. |
| 3.5 | `EvidenceContext` versioned | PARTIAL | `evidence_context.py:169-186` | **Not versioned** — no `version`, `revision`, or `superseded_by`. Addressing is content-addressed (`CX-` + digest128). `RelationClaim` has versioning (`logical_relation_id` + `revision_number`); the context does not. |
| 3.6 | Context Graph durable | FALSE | Object absent |
| 3.8 | Context Graph distinguishes unknown vs empty | FALSE | Object absent. Related honesty exists at value level: `ContextTrustState.UNVERIFIED`, `ContextCompleteness.PARTIAL/FRAGMENT`, `TemporalSlice.burstiness=None`, `graph_invariant.py:227` DORMANT. Platform expresses "unknown" as `None`. |

### Acquisition (§4)

| § | Claim | Verdict | Evidence | Corrected |
|---|---|---|---|---|
| 4.1 | Record/Artifact hash derivation | PARTIAL | `acquisition_artifact.py:92,123,158-169`; `capture.py:264,353-359` | **Three** digests: record = `sha256(body)`; artifact = `locator` + optional `capture_locator`; capture = `CAP-` + digest128 over tenant/source/target_uri/locator/content_digest. TZ's two-level framing is wrong. |
| 4.2 | `runtime/__init__.py` declares `nmap`/`whatweb` | **FALSE** | 164 ln, **zero** capability literals. `nmap` = **0 occurrences repo-wide**. `whatweb` = one YAML (`20_system_tools/kali_whatweb.yaml`) | File declares the `AcquisitionWorker` Protocol only. Real capabilities are hardcoded per class: searxng `http/search/json-output/paged`, airbyte `connector-protocol/stdio/streaming/stateful/discover`, bbot `recon/event-stream/passive/dns/subdomains/streaming`, external_tool `process/container-isolated/streaming/resource-bounded`. |
| 4.3 | `primproc.py` is a content filter | PARTIAL | `acquisition/runtime/primproc.py` (464 ln) | It is a **decorator** around any worker that emits a *second*, cleaned artifact alongside untouched raw. Raw always survives. Real cleaner: `interpretation/parsers/primproc/` (6 modules, 129 KB) — `is_cleaning_route` is True for **only** `text/html` and `application/xml`. |
| 4.4 | Finders at `shared/skills/interpret/{record,digest}_finder.py` | **FALSE** | `apps/shared/skills/` does not exist; both filenames: 0 occurrences | The path was never built. No "skills" concept in the platform. |
| 4.5 | Duplicate of §4.1 | TRUE (dup confirmed) | `input.md:205` ≡ `input.md:221` | Resolved by §4.1. |
| 4.6 | Acquisition writes no graph/worldline/context | **TRUE** | 0 matches for `sqlalchemy\|psycopg\|neo4j\|INSERT` in `apps/acquisition/**`; 0 upward imports | Verified clean. Writes only via `artifact_sink.py` → ObjectStore + ObservationGate. |
| 4.7 | Capabilities are data, discoverable at runtime | PARTIAL | `sources/catalogue.py:55`, 146 YAML in `sources/estorides/`, `GET /api/v1/connectors`, `/api/v1/tools` | **True at source level** (146 definitions, 20 categories). **False at runtime level** — `capabilities()` is a hardcoded method. **Tension:** `runtime/__init__.py:10-14` explicitly forbids capability-first routing by name. |
| 4.8 | At-least-once + idempotent | TRUE | `observation_identity.py` `require_deterministic_event_id`; `observation_gate.py` | Implemented: lifecycle ∈ {new, changed, duplicate, unchanged}; duplicates short-circuit. **But** `test_idempotency.py` does not collect (§8). |

### Interpretation (§5)

| § | Claim | Verdict | Evidence | Corrected |
|---|---|---|---|---|
| 5.1 | Record lineage exists | PARTIAL | `evidence_lineage.py:81 EVIDENCE_BACKWARD_CHAIN`, `:102 DERIVATION_FORWARD_CHAIN` | **2 of 3.** evidence ✅, derivation ✅. **research ❌** — word "research" absent from the module; no obligation/action tables. |
| 5.2 | `AssemblyBatch` is the unit of interpretation | **FALSE** | `rg AssemblyBatch` → 0 repo-wide | Nearest: `ResolutionBatch` (`semantic/resolution.py:1984`), `RegimeBatch`, `IngestBatchRow`. |
| 5.3 | States `A`/`R` via `DefinitionLifecycle` | **FALSE** | `rg "admission_state\|record_state\|DefinitionLifecycle"` → 3 hits, all in the TZ itself | Real enums: `Observation.status` = created/changed/unchanged/duplicate; `RelationStatus` = active/superseded/retracted/contradicted/quarantined; `CandidateStatus`; `InvestigationState` = DRAFT…ARCHIVED. |
| 5.4 | Graph invariant in `graph_invariant.py` | TRUE | 1084 ln, pure stdlib, no IO | Real, but it is a **2-identity domain model**, not a graph-integrity checker. Guarantees purity, determinism (`integrity_digest` = sha256 of canonical JSON, order-independent), tz-aware, dedup, `from_entity_stream` rejects empty/mixed input. Checks **no** graph invariants (no acyclicity, no referential, no cardinality). |
| 5.6 | `EntityResolver` exists | **FALSE by name** | `rg "class \w*Resolv\w*"` | No such class. Split three ways: `admission/resolution/resolver.py` (pairwise), `shared/domain/entity_identity.py` (long-lived `ENT-` binding), `shared/semantic/resolution.py` (`MentionResolver`). |
| 5.7 | Context formation exists | **FALSE** | `rg -in "formation" apps/**` → nothing | Closest: `SemanticRegime` (`semantic/regime.py`), which *references* `context_ref` and extends the evidence frame. |

### Investigation (§6)

| § | Claim | Verdict | Evidence | Corrected |
|---|---|---|---|---|
| 6.1 | Investigation is primary unit | PARTIAL | `schema.py` `investigations`; 10-state lifecycle; 7 `investigation.*` events; 8 HTTP endpoints | Domain is primary, but **lifecycle is not registered with Temporal** — `workflows/worker.py:20-25` registers only `TemporalEntityMaterializationWorkflow`. `InvestigationWorkflow` is imported only by a test. |
| 6.2 | `fulltext`/`lemmatized` columns | **FALSE** | 57 `__tablename__` in schema; no such column string anywhere in `apps/` | No such columns. Lemmatization is in-memory in interpretation (`extractors/normalize.py:52-98`, pymorphy3). |
| 6.3 | Hypothesis generation in investigation | FALSE (path) / misidentified | `shared/domain/predicate_hypothesis.py` — **11+ production import sites** | It is **live and load-bearing**, but it is a **predicate resolver** (surface form → typed `RelationRef`), not hypothesis generation. Real hypothesis generation: `science/hypotheses/model.py::propose_hypothesis`, `gain.py::plan_collection` — live, event-emitting, but **operator-triggered only** (`POST /api/science/hypotheses`). Confirms §10.6. |
| 6.4 | Evidence and link endpoints exist | PARTIAL | `evidence_links` table, `EvidenceLink` model, `evidence.link_created` event | Data model yes. **No dedicated `/evidence` or `/links` router.** Exists: `POST/GET /entities/{id}/correlations`, `GET /entities/graph`, `GET /findings/{id}/lineage`, `POST /modifier/dedupe-links`. |
| 6.5 | **No knowledge graph in PostgreSQL** | **FALSE — inverted** | 57 tables / 55 models incl. `entities`, `entity_versions`, `entity_identity`, `relation_candidate`, `relation_claim`, `relation_claim_revision`, `relation_signal`, `correlation_edges`, `type_assertions`, `temporal_history_*`, `topological_features` | PG holds a **full relational graph**. A **second** graph exists in Neo4j (`projection/graph/neo4j.py`, `relation_store.py`, profile `analytics`). **The graph is duplicated across two engines.** |
| 6.6 | Investigation owns hypothesis/task/scope/worldline lifecycle | PARTIAL | — | Hypothesis lifecycle → owned by **science**. Task lifecycle → `acquisition_tasks` + `frontier_items`, no investigation-scoped API. **Scope revision → absent.** Worldline contribution → exists. |

### Science (§7)

| § | Claim | Verdict | Corrected |
|---|---|---|---|
| 7.1 | 19 builder files | **FALSE** | 65 `.py` (43 src + 22 test). **Zero** files matching "builder". |
| 7.2 | 25 pipeline files | **FALSE** | **Zero** files matching "pipeline". |
| 7.3 | `registry.py` mapping `SKILL.md` | **FALSE** | No top-level registry. `claims/registry.py` and `experiments/registry.py` are type registries. **`SKILL.md` does not exist in the platform** (only `donors/*/skills/`). |
| 7.4 | `apps/science/primproc.py` | **FALSE** | Does not exist. Exactly one `primproc.py` repo-wide: the acquisition decorator. |
| 7.5 | `scientific_method.py` | **FALSE** | Not found anywhere. |
| 7.6 | `tool_spec.py`, `scientific_method_spec.py` | **FALSE** | Neither exists. Closest: `control-plane/services/tool_catalog.py` (unrelated). |
| 7.7 | Science evaluates the worldline | **FALSE** | `rg worldline apps/science/**` → **0 hits**. `science/store.py:1-12`: "In-memory, event-replayable state store… projects its current state purely from `science.*` envelopes." This is **precisely the private toy state §7.7 forbids.** Not durable, not worldline-anchored. |

### Platform (§8–9)

| § | Claim | Verdict | Corrected |
|---|---|---|---|
| 8.1 | 257 rules | UNVERIFIABLE | **No rule registry exists anywhere.** "257" appears once in the repo — the TZ itself. Enumerable substitutes: constitution 7 principles + 12 invariants = 19; mutation-verified = 8; distinct `FR-###` across specs = 215; distinct `T###` = 351. |
| 8.2 | 5 323 tests | **FALSE** | Real run: **2 620 collected → 2 491 passed, 121 failed, 9 skipped, 24 collection errors** (238 s). Plus 67 Rust tests (15 `.rs`, not run). Pass rate 95.0 %. TZ is ~2× overstated. |
| 8.3 | 11 features | **FALSE** | `specs/` has **22** directories (001–012, 014–019, 021–024; 013 and 020 absent). README's spec table lists 12 — stale. |
| 8.5 | Count unenforced rules | UNVERIFIABLE by construction | No rule inventory exists. Reportable instead: **8 of 19** constitutional items are mutation-proven enforceable (`shared/tests/constitution/test_constitution_has_teeth.py`). The other 11 are documentation by the TZ's own criterion. |
| 9.1 | `CONTEXT.md` holds project context | **FALSE** | Does not exist at repo root. Only `tmp/theharvester/CONTEXT.md` (vendored donor). Context is split across `README.md`, `docs/architecture/overview.md`, 24 ADRs, `.specify/memory/constitution.md`. |
| 9.2 | `README.md` is the operator guide | PARTIAL | 74 lines: quick start, layout table, stale spec table. A **bootstrap reference**, not an operator guide — no config reference, no failure modes, no recovery. |
| 9.3 | Docs must be verified against code | TRUE | Necessary: **§4.2, 4.4, 6.2, 6.3, 6.5, 7.1–7.7, 8.1–8.3, 9.1 were all false.** |

---

## 2. `EvidenceContext` — WHAT IT ACTUALLY IS

`apps/shared/domain/evidence_context.py` (384 ln), table `evidence_context` (`schema.py:1112-1165`).

An **immutable, content-addressed evidence/provenance frame** — the frame in which a claim was read. Its own docstring: *"A context is evidence, not a verdict."*

Real fields, grouped by purpose:

- **Provenance**: `observation_id`, `source_id`, `document_id`, `segment_id`
- **Temporal framing**: `observed_at`, `published_at`, `valid_from`, `valid_to` (with `validity_interval_inverted` check)
- **Source independence**: `source_family`, `independence_group`
- **Rule versions**: `extraction_version`, `normalization_version`, `ontology_version`, `policy_snapshot_ref`
- **Self-assessment**: `completeness` (complete/partial/fragment), `trust_state` (verified/attested/unverified/disputed)
- **Identity**: `context_id` = `"CX-" + digest128(canonical_material(frame))`, verified at construction (`context_id_mismatch`); `frame_fingerprint`; `parent_context_id` with cycle detection

**Absent**: questions, obligations, scope, tasks, hypotheses, decisions, revisions, coverage/saturation, actions. The only scope-like fields are `investigation_id` and `entity_anchor`, and both are **references, not structures**.

**Verdict: a new `InvestigationContext` is mandatory, and overloading is not merely bad style — it is technically impossible.** Adding any field to `EvidenceContext` changes the material that `context_id` is cut from, which invalidates every stored `context_id`, the `uq_evidence_context_fingerprint` unique index, every `context_ref` in claims, and every event payload carrying a frame. A persisted frame then fails `context_id_mismatch` on load — it does not degrade, it becomes **unreadable**. The bypass pattern already exists in the codebase: `SemanticRegime` is a separate content-addressed object referencing `context_ref` one-way. That is the template for `InvestigationContext`.

---

## 3. THE THREE LINEAGES

| Lineage | Status | Evidence |
|---|---|---|
| **evidence** (`relation → assertion → mention → segment → observation → capture → source`) | **implemented** | `evidence_lineage.py:81`; `EvidenceGraph.backward()`; `claim_context_lineage` table; `GET /findings/{id}/lineage` |
| **derivation** (`source → capture → observation → … → relation → entity`) | **implemented** | `evidence_lineage.py:102`; `EvidenceGraph.forward()`; `LineageTracePair` returns both dimensions at once |
| **research** (`obligation → action → source → what was learned`) | **absent** | No `obligation`/`action` in `HopKind`; no obligations or actions table in schema |

Both existing dimensions are **pure in-memory walks over injected data — no persistence, no store behind them**. `LineageTrace` reports its own incompleteness (`complete=False` + the name of the first break) rather than truncating silently. Independence is counted by source family, not by document.

---

## 4. CONTEXT GRAPH — DOES NOT EXIST

Unambiguous. `rg -il "context_graph|contextgraph"` across the repo (including donors, tmp, specs, docs, bench, tools) returns **one hit: `input.md` itself**.

The platform has `investigations` (a row), `relation_claim`/`relation_candidate` (a claim graph), `evidence_context` (a frame), and `claim_context_lineage` (a lineage table) — but **nothing that binds them into one managed research graph**. The Context Graph is greenfield, and the absence of the *structure* is not listed in input.md §10 (which enumerates functional gaps only).

---

## 5. LAYER 0 — DEAD TEST HARNESS, NOT A PRODUCTION PATH

`apps/control-plane/services/layer0_pipeline.py`, 355 ln, `class Layer0Pipeline` at `:155`.

Evidence it is dead:

1. **Its only importer is a test file.** Repo-wide search for `layer0_pipeline|Layer0Pipeline` yields one non-donor, non-spec import: `tests/integration/test_layer0_direct_pipeline.py:34` — **and 4 of those tests currently fail.**
2. **Its only dependency is also test-only.** `AcquisitionLoop` is instantiated only in tests.
3. **No HTTP route.** `api/main.py:75-87` includes 12 routers; none mounts Layer 0.
4. **No Temporal registration.**
5. **It self-declares unwired** — its own docstring `:10-11`: *"every acquisition-stage organ exists… but nothing assembles them… This module is the missing composition root."* An unmounted composition root is not a composition root.
6. **Spec 021 already ordered its deletion** — `specs/021…/spec.md:1792` ("orchestrator MUST be deleted"), `plan.md:798` marked `DELETED (FR-172)`, `research.md:256` ("zero production instantiations").
7. **It is a constitutional liability.** `seed(take investigation_id: str = "")` at `:301` violates Principle VI. `acquisition_loop.py:51-53` uses `follow_redirects=True` on untrusted URLs with no allowlist and no DNS-rebinding protection — **SSRF by construction** under Principle VII.

Its one genuinely good idea, and the only part worth keeping: the four hook `Protocol`s (`InterpretHook :121`, `FabricHook :135`, `SearchHook :143`, `LakeHook :149`).

**Consequence: input.md §16.1 is FALSE. The canonical event path is a greenfield build on real primitives, not a refactor.** It must be built *around* Layer 0, never by reviving it.

---

## 6. PRIMITIVES THAT ALREADY EXIST AND MUST BE WIRED, NOT REWRITTEN

Per AGENTS.md §1 (donor reuse is the default) and Constitution III (projection-first, all projections rebuildable), these are load-bearing and already work:

| Primitive | Path | State |
|---|---|---|
| 4 acquisition runtimes | `apps/acquisition/runtime/{searxng,airbyte,bbot,external_tool}.py` | Live-proven: SearXNG, Airbyte (12 records + 1 state), Maigret, BBOT, SpiderFoot; 29/29 observations read back |
| 146 source definitions | `apps/acquisition/sources/estorides/` (20 categories) | Loaded by `catalogue.py`; exposed via `/api/v1/connectors`, `/api/v1/tools` |
| Primary processing | `apps/interpretation/parsers/primproc/` (6 modules, 129 KB) | Real: `processor.py`, `markup.py`, `decode.py`, `reasons.py`, `result.py` |
| **Common Crawl — full chain** | `shared/network/{commoncrawl,cc_session,range_pull}.py`, `zero/zero/cc_capture.py`, `acquisition/cc_plan.py`, `cc_extract.py`, `adapters/{commoncrawl,warc}/`, `interpretation/parsers/warc.py` (662 ln), `control-plane/services/cc_temporality.py` | **input.md §19.2 is NOT new work.** 5 events on topic `cc_temporality`, all tests passing, spec 011. Its layer contract is already documented in `topics.py:117-120`. What is missing is only that this chain is not on the canonical event path. |
| Deterministic identity | `shared/domain/observation_identity.py` | Single writer, protected by `require_deterministic_event_id` |
| Observation gate | `shared/events/observation_gate.py` (350 ln) | lifecycle {new, changed, duplicate, unchanged} |
| WARC parser | `interpretation/parsers/warc.py` | Typed error reasons: `warc.missing_content_length`, `warc.bad_content_length`, `warc.record_too_large`, `warc.too_many_records`, `warc.gzip.*` |
| Object store | `shared/storage/s3.py` | Content-addressed, immutable. **Sole writer: `acquisition/artifact_sink.py`** — raw lands *first*, because capture identity is built from the stored ref + digest. |
| Event contract | `shared/events/event_envelope.proto` + `topics.py` (116 event types → 43 topics) | See §8 below |
| Graph projection | `projection/graph/{neo4j,relation_store,abstraction,snapshot,adjacency}.py` | Constitution V `GraphProjection`/`GraphReader`/`GraphSnapshot`/`GraphTraversal` |

---

## 7. FRONTEND — FACTUAL MAP

Inventory: **243 files, 43 924 lines, 58 test files, 759 tests → 750 passed, 9 failed.**

| Dir | Files | Lines | Tests | Status |
|---|---|---|---|---|
| `src/` root | 15 | 2 218 | 70 | components + harness |
| `src/components/` | 19 | 2 177 | 29 | legacy (donor ports) |
| `src/containers/` | 24 | 2 954 | 51 | legacy, all in `App.tsx` |
| `src/evidence/` | 13 | 4 453 | 91 | **complete** |
| `src/graph/` | 19 | 5 626 | 97 | **complete** |
| `src/lib/` | 34 | 4 987 | 97 | models only, 1 component |
| `src/objects/` | 7 | 2 327 | **0** | **models only — 0 components, 0 imports** |
| `src/ops/` | 11 | 3 462 | 54 | **complete but not mounted** |
| `src/pages/` | 23 | 3 103 | 38 | legacy |
| `src/quality/` | 2 | 612 | 35 | 1 hook + harness, **not connected** |
| `src/styles/` | 36 | 6 309 | 0 | tokens + legacy + donors |
| `src/timeline/` | 9 | 2 356 | 58 | **complete** |
| `src/ui/` | 11 | 1 428 | 39 | primitives, complete |
| `src/workspace/` | 15 | 3 400 | 66 | core, complete |

**UI 2.0 exists on exactly one route**: `/investigations/:id`. Everything else is legacy containers. The default `/` redirects to `/intel`.

Mounted tree under `/investigations/:id`: `Workbench.InvestigationWorkspaceRoute` → `InvestigationRoute` → `Workbench` → `AppShell` (→ `WorkStateBar`, `PaletteButton`, `AppearanceMenu`, panel toggles) → `LeftRail`/`ContextRail` + `InvestigationWorkspace` + `RightInspector`/`ContextInspector` → `CommandPalette`, `CanvasContextMenu`, `KeyboardLayer`.

**Of 8 views, 4 mount real content** (overview=legacy page, graph, timeline, evidence) and **4 render `StagePlaceholder`** (objects, acquisition, findings, analysis). `src/acquisition/` does not exist. `src/ops/` and `src/quality/` are fully written and **not imported by any route**.

### 7.1 Palette — 0 of 15 tokens match

`src/styles/tokens/color.css` uses a different naming system (`--ui-*`) and **different values**. Critically, the accent is a pure green where the spec calls for a yellow-green phosphor:

| Required | Actual | Required value | Actual value |
|---|---|---|---|
| `--bg-0` | `--ui-bg-sunken` | `#070909` | `#070908` |
| `--bg-1` | `--ui-bg` | `#0B0E0D` | `#0a0c0b` |
| `--surface-0` | `--ui-surface-1` | `#121715` | `#101312` |
| `--surface-1` | `--ui-surface-2` | `#161B18` | `#161a18` |
| `--surface-2` | `--ui-surface-3` | `#1C221E` | `#1d221f` |
| `--border-0` | `--ui-border` | `#252C28` | `#232825` |
| `--border-1` | `--ui-border-strong` | `#323B35` | `#333b36` |
| `--text-primary` | `--ui-text` | `#E5EAE7` | `#e7ece8` |
| `--text-secondary` | `--ui-text-secondary` | `#A5AEA9` | `#a6b0a8` |
| `--text-muted` | `--ui-text-muted` | `#6E7873` | `#7d877f` |
| `--accent-green` | `--ui-accent` | `#8FCB64` | `#46c07a` |
| `--accent-green-bright` | `--ui-accent-bright` | `#A7E477` | `#6fe0a3` |
| `--accent-amber` | `--ui-gold` | `#B99A66` | `#c9a249` |
| `--accent-red` | `--ui-danger` | `#BF5B57` | `#d4574c` |
| `--accent-blue` | `--ui-analytical` | `#718D9B` | `#4f9cb8` |

Also: `color.css` states "no component stylesheet may hard-code a hex value" — violated at `IntelligencePage.tsx:748`.

### 7.2 Density and theme switches that switch nothing

`data-density` and `data-theme`: **0 occurrences in any `.ts`/`.tsx`**. The tokens are declared under `:root, [data-density="compact"]` / `[data-density="comfortable"]`, but nothing writes the attribute to the DOM. So `toggleDensity()` mutates a Zustand field and changes **zero pixels**, and the light theme is unreachable. Additionally `STANDARD` does not exist — only `compact` (default) and `comfortable`. And `graph.css`, `timeline.css`, `evidence.css` reference **zero** density tokens.

### 7.3 Breakpoints — 0

All 5 media queries in app-owned CSS are `prefers-reduced-motion`. **No width-based media query, no `matchMedia`, no container query, no `ResizeObserver` layout.** All three panes use fixed px widths (`rail 264 / inspector 340 / activity 168`).

### 7.4 SelectionState — 4 of 9 fields, and the split is violated

Present: `investigationId`, `objectType` (as typed `selection.kind`), `objectId` (as `selection.id`), `timeRange`, and part of `filters`.
**Missing**: `evidenceIds`, `graphMode`, `lineageMode`, `focusedPath`.
**Critically**, `graphMode` (`GraphCanvas.tsx:93`), `focusedPath` (`:96`), `expandedIds`/`temporalActive`/`filterDrawerOpen` (`:94,102,103`), and the graph facets (`useGraphFacets`) all live in component `useState` — so they are **lost on view switch**, while `store.test.ts` and `Selection.performance.test.tsx` assert a structural guarantee that they hold.

Other split issues: the same `entity-projection` payload is fetched under 4 different query keys (`graph`/`evidence`/`timeline`/`objects`), so invalidating one does not update the others; Investigation is queried under 3 keys; `QueryClient` has no `defaultOptions`, so there is no `staleTime` in production. Server data is *not* in Zustand and selection is *not* in the query cache — those two rules are respected.

### 7.5 URL state — 6 keys

`view`, one param per selection kind (`entity`/`observation`/`capture`/`claim`/`finding`/`task`/`run`/`source`), `q`, `from`, `to`. Investigation is in the **path** by design. Round-trip verified. Not encoded: pane widths/visibility, density, theme, palette/menu state, `railQuery`/`railKinds`, `secondarySelection`, `evidenceFilter.sourceIds`/`hideRejected`, `graphMode`, `focusedPath`, graph facets.

### 7.6 Performance — 0 of 4 techniques applied

No `React.lazy`, no `Suspense`, no `Offscreen`, no Web Worker, no `useDeferredValue`/`useTransition`/`requestIdleCallback`. The only code splitting is 5 dynamic imports of heavy vendors (`cytoscape`, `echarts`). `objects/virtualization.ts` (178 ln, `OVERSCAN=8`, `ROW_HEIGHT` by density) is **fully written and imported by nothing**.

### 7.7 The 9 failing tests — one cause

All 9 fail because tests were written against the Stage-2 placeholder contract (`data-testid="canvas-{view}"`, `placeholder-{view}`, `canvas-{view}-selection`), which Stages 3–4 replaced with `graph-canvas`, `timeline-canvas`, `evidence-workspace`.

| # | File:line | Test |
|---|---|---|
| 1 | `Selection.performance.test.tsx:188` | selection is genuinely global across views |
| 2 | `Shell.keyboard.test.tsx:63` (`"g"`) | chord switches canvas to graph |
| 3 | `Shell.keyboard.test.tsx:63` (`"e"`) | chord switches canvas to evidence |
| 4 | `Shell.keyboard.test.tsx:63` (`"t"`) | chord switches canvas to timeline |
| 5 | `Workspace.integration.test.tsx:142` | renders each of the eight documented views |
| 6 | `Workspace.integration.test.tsx:167` | labels unbuilt views with the owning stage |
| 7 | `Workspace.integration.test.tsx:176` | shows preserved selection inside the placeholder |
| 8 | `Workspace.integration.test.tsx:192` | moves the canvas when a tab is activated |
| 9 | `Workspace.url.test.tsx:108` | inbound URL hydrates the workspace |

Six are pure testid drift. In all of them the *logic* passes — `useWorkspace.getState().view` is set correctly; only the node lookup fails. Additionally there is 1 unhandled rejection: cytoscape `Could not create canvas of type 2d` under jsdom during `IntelligenceContainer.test.tsx`.

---

## 8. EVENT CONTRACT AND STORES

### 8.1 Envelope

`apps/shared/events/event_envelope.proto` (31 ln), proto3, package `cognitive.events.v1`, 16 fields. Serialization is **Protocol Buffers**, not a self-describing envelope: `payload` is `bytes`, validated per `event_type` by the Schema Registry.

`topic_for(event_type)` raises `UnknownEventTypeError` on unknown types. **116 event types → 43 topics.** DLQ lanes: `events.dlq`, `events.quarantine`. `NERVOUS_SYSTEM_EVENT_TYPES` (`:145-154`) — 8 types the hermetic bus replays for deterministic rebuild.

**Gap vs input.md §16.6:** the envelope has `produced_at` (field 9) but **no `observed_at`**. §16.6 as written is unsatisfiable without a schema change (add field 17).

### 8.2 Stores

| Store | Reality |
|---|---|
| **MinIO/S3** | Load-bearing, immutable, content-addressed at sha256. **Sole writer path `acquisition/artifact_sink.py`.** `aioboto3` optional-at-import so hermetic tests still run. |
| **PostgreSQL** | 57 tables / 55 models. Largest store. **Holds a full relational graph** (§6.5). |
| **Kafka** | **This is the default transport.** Confluent 7.7.0 KRaft, `localhost:9092`, profile `core`. `KafkaSettings.bootstrap_servers="localhost:9092"`. |
| **Redpanda** | Profile `streaming` **only**, port 19092, **image tag unpinned** (`redpandadata/redpanda:latest`). **Referenced by no default config or settings key.** Not the transport. |
| **Neo4j 5** | Real code, profile `analytics`. **Second copy of the graph.** |
| OpenSearch / ClickHouse | Real code, profile `analytics`; 2 OpenSearch test modules do not import |
| Redis | Frontier leases/cooldowns — config only |
| **Temporal 1.25.2** | Real, but registers **only** `TemporalEntityMaterializationWorkflow` |
| Flink + Nessie | Declared, profile `streaming` |
| `apps/science/store.py` | **In-memory, event-replay, not durable** — the §7.7 violation |

### 8.3 Test baseline — not green

```
pytest apps --continue-on-collection-errors
2 620 collected → 2 491 passed | 121 failed | 9 skipped | 24 collection errors (238 s)
```

| App | Test files | Test fns | Failures |
|---|---|---|---|
| shared | 50 | 703 | 23 |
| interpretation | 26 | 598 | 0 |
| control-plane | 42 | 385 | 45 |
| acquisition | 27 | 313 | 42 |
| projection | 17 | 196 | 8 |
| science | 22 | 156 | 0 |
| zero | 6 | 121 | 0 |
| admission | 6 | 96 | 0 |
| feedback | 3 | 20 | 1 (won't import) |
| bulk-ingestion | 3 | 12 | 6 |

**24 modules fail to import, running zero tests while inflating the pass rate.** The blind spots include `test_idempotency.py`, `test_infra_connectivity.py`, `test_redpanda_emission.py` — i.e. **the very tests that would verify input.md §4.8 idempotency and Redpanda emission do not run.** Also 8 files under `shared/tests/contract/` and 8 projection TDA modules.

Top failure clusters: `test_acquisition_worker.py` 25, `test_query_degradation.py` 17, `test_websearch.py` 13, `test_query_fusion.py` 11, `test_evidence_context.py` 8, `test_lakehouse.py` 8, `test_query_planner`/`test_adapters_gate`/`test_engine_adapters_gate`/`test_historical_replay` 5 each, `test_layer0_direct_pipeline.py` 4, `test_frontier_provenance.py` 4.

---

## 9. FIVE FACTS THAT CHANGE THE PLAN

1. **The canonical event path is greenfield, not a refactor.** Layer 0 is dead code already slated for deletion by spec 021 FR-172, and reviving it would convert a dormant Principle VI violation (investigation-less `seed()`) and a dormant SSRF vector (`follow_redirects=True`, no allowlist) into live ones. Build around it; reuse only the four hook `Protocol`s.

2. **Two entire claimed subsystems were never built.** `apps/investigation` and `apps/shared/skills/` do not exist. Consequently input.md §2.8, §4.4, §6.2, §6.3 are false, 4 of 8 Acquisition claims are false, and **6 of 6 Science claims (§7.1–7.6) are false**. The described Science layer (builders, pipelines, SKILL.md registry, `tool_spec`, `scientific_method_spec`) is **absent, not partial**; the real Science layer is 14 domain subpackages over an in-memory store. The input.md §22–§26 volume estimate is understated if the plan assumes "finishing what exists."

3. **§6.5 is inverted — the graph is already duplicated.** PG holds a full relational graph *and* Neo4j holds a second one. A migration premised on "no graph in PG, therefore add one elsewhere" would produce a *triple* graph. Which engine is authoritative is a decision, not an assumption.

4. **Redpanda is not the transport, and the envelope cannot express §16.6.** Default is Confluent Kafka on :9092; Redpanda is `streaming`-profile-only with an unpinned tag and no config reference. And `EventEnvelope` has no `observed_at` field, so §16.6 requires a schema change. Both also collide with the Constitution Technology Baseline ("Apache Kafka (KRaft)") and 24 ADRs that assume Kafka.

5. **Science is an in-memory toy and the suite is not green.** `rg worldline apps/science/**` → 0 hits; `science/store.py` self-describes as a `science.*`-only replay projection. Meanwhile 121 failures and 24 non-importing modules form the inherited baseline, and `test_acquisition_worker.py`'s 25 failures sit directly under the acquisition stage the loop depends on.

---

## 10. OWNER DECISIONS REQUIRED BEFORE spec/plan

Per `AGENTS.md` §1.1 these are conceptual contradictions, not engineering preferences. Each one changes Constitution III/IV/VI or the transport baseline, and none is the implementer's call.

| # | Contradiction | Invariant at stake | Options |
|---|---|---|---|
| D1 | §16.3 says "Redpanda as transport"; the real default is Confluent Kafka on :9092 and the Constitution baseline names Kafka (KRaft). Redpanda is `streaming`-profile-only, unpinned, and unreferenced by any config. 24 ADRs assume Kafka. | Technology Baseline; Principle III | (a) Redpanda becomes the single dev/live transport, Kafka ADR baseline amended; (b) keep Kafka as declared transport, Redpanda only a compatible dev substitute; (c) both, with an explicit profile matrix |
| D2 | §6.5 assumes no graph in PG. PG already holds a full relational graph, and Neo4j holds a second. Where does the Context Graph live? | Principle IV "no universal graph as source of truth"; "No MVP/mini-architecture" | (a) Context Graph as relational tables in the existing PG schema; (b) Context Graph in Neo4j via the existing `GraphProjection` contract; (c) PG authoritative and Neo4j demoted to a serving projection (collapses the duplication) |
| D3 | §2.8/§6.x assume `apps/investigation` is an app. It does not exist; the domain lives in control-plane and the lifecycle is **not registered with Temporal**. | Principle VI; "No MVP/mini-architecture" | (a) new `apps/investigation` app with all 8 plane contracts up front; (b) extend `cp_domain/investigation.py` + register `InvestigationWorkflow` with Temporal; (c) new app but incrementally, with final domain/event contracts fixed up front |
| D4 | §4.7 wants obligations routed to capabilities; `runtime/__init__.py:10-14` explicitly forbids capability-first routing by name. Feature 023's O-2 already decided: route by `runtime_ref` first, capabilities only as a check. | Principle V; prior 023 decision O-2 | (a) keep O-2 and satisfy §4.7 from the **146-source catalogue** (declarative capabilities) rather than from runtime method returns; (b) amend `runtime/__init__.py` to permit capability-first routing |
| D5 | §16.6 requires a logical **and** an observed timestamp; `EventEnvelope` has only `produced_at`. Adding field 17 is a contract change touching every producer and consumer. | Principle III; Technology Baseline (Protobuf) | (a) add `observed_at` as field 17, version the contract, migrate producers; (b) keep 16 fields and define "observed" inside typed payloads per event type |
