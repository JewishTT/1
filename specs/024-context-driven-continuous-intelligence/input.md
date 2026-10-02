# Feature 024: Context-Driven Continuous Intelligence Fabric

**Source**: full platform convergence ТЗ (534 sections), verbatim-fidelity normative digest.
**Companion document**: `ui-upgrade.md` (UI 2.0 global upgrade, 220+ sections).
**Status of source**: Wave 0 MUST reconcile the spec/code discrepancy described in §0.

---

## 0. WAVE 0 — CODE BEFORE SPEC (§0.1–0.6)

### 0.1 Status of this document
This document is a **source of requirements, not a verified audit**. It contains claims about the repository that are believed stale. No claim here is accepted until Wave 0 verifies it against the actual current main branch. Wave 0 produces a verified current-state map; all later waves are planned from that map, not from this document.

### 0.2 Verified claims status
Statements believed TRUE as of the source of this document:

- §1.3 `apps/acquisition/runtime/` exists on current main with 7 modules: `__init__.py`, `airbyte.py`, `bbot.py`, `external_tool.py`, `primproc.py`, `record_stream.py`, `searxng.py`.
- `specs/023-acquisition-integration-searxng/` exists.
- `specs/021-entity-relation-extraction-finalization/` exists.
- `specs/018-*` exists.

Wave 0 MUST re-verify all of the above and record actual file inventories.

### 0.3 Claims believed STALE (Wave 0 MUST verify or correct)

- §2.3: "offset schema by `content_digest`" and §2.4: "by `artifact_id`" — an `ObservationRecordRef` may exist with an offset schema. These are **two claims of the same mechanism**; only one offset schema can exist. Wave 0 determines which, and whether both exist under different names.
- §3.1: `capture_locator` naming — actual implementation uses `record_locator` and/or `record_index` and/or `ordinal`. Wave 0 determines the real field names.
- §3.4: "Message framing: per-observation one Kafka message" — several schemas claim per-observation message granularity. Wave 0 determines actual framing.
- §4.1: "`record-hash` / `artifact-hash` derivation" — Wave 0 determines the real digest fields.
- §4.2: "`nmap` / `whatweb` capability declared in `apps/acquisition/runtime/__init__.py`" — Wave 0 verifies whether such capability declarations exist and whether they are true.
- §4.4: "real finders at `apps/shared/skills/interpret/record_finder.py` and `digest_finder.py`" — Wave 0 verifies path, existence, and that they are "real" rather than stubs.
- §4.5: "`record-hash` / `artifact-hash` derivation" duplicates §4.1. Wave 0 resolves the duplication.
- §5.1: "record lineage exists" — Wave 0 verifies which lineage is implemented and which is planned.
- §5.2–5.3: `AssemblyBatch` and `A`/`R` (`admission_state`/`record_state`) defined via `DefinitionLifecycle` — Wave 0 verifies.
- §5.4: "graph invariant" — Wave 0 verifies existence of `apps/shared/domain/graph_invariant.py` and its actual guarantees.
- §5.5: "`EvidenceContext` exists as core domain object" — Wave 0 verifies and, critically, determines **what it actually is** (see §3.4 of the convergence analysis: it is likely an evidence/provenance frame, not a research-scope context).
- §5.6: "`EntityResolver` exists" — Wave 0 verifies.
- §5.7: "context formation" — Wave 0 verifies.
- §6.2: "stable `fulltext` / `lemmatized` columns" — Wave 0 verifies existence and whether they are used.
- §6.3: "hypothesis generation" — Wave 0 determines whether the code path is live, inert, or a second normalizer.
- §6.4: "evidence and link endpoints" — Wave 0 verifies.
- §6.5: "no knowledge graph in PostgreSQL" — Wave 0 verifies actual current storage.
- §7.1: "19 builder files" — Wave 0 counts actual files.
- §7.2: "25 pipeline files" — Wave 0 counts actual files.
- §7.3: "`registry.py` mapping `SKILL.md` files" — Wave 0 verifies mechanism.
- §7.4: "`primproc.py`" — Wave 0 determines whether it is the acquisition content filter (§4.3 duplicate reference) or a separate `stdlib` HTML parser. **The source contains two contradictory descriptions of `primproc.py` and Wave 0 MUST resolve which is true.**
- §7.5: "`scientific_method.py`" — Wave 0 verifies.
- §7.6: "`tool_spec.py` / `scientific_method_spec.py`" — Wave 0 verifies.
- §8.1–8.4: counts of rules, tests, and features — Wave 0 re-counts all of them.
- §9.1–9.3: `CONTEXT.md` and `README.md` contents — Wave 0 verifies.
- §11.2: "**Layer 0 HTTP endpoint implements the entire pipeline**" — Wave 0 verifies whether Layer 0 is a legacy direct path that must yield to an event-driven path. **If Layer 0 is a real production path, this entire plan is a rewrite rather than a wiring change.**

### 0.4 Interpretation rules
1. Where this document says a mechanism exists, the default reading is: **it is believed to exist but is unverified**.
2. Where this document says a mechanism is missing, the default reading is: **it is believed missing; absence of mention is not proof of absence**.
3. The normative requirements in §20–§32 are binding regardless of Wave 0 findings, because they describe the target state, not the current state.
4. Wave 0 output MUST include a per-claim verdict table: `claim / verdict (TRUE|FALSE|PARTIAL|UNVERIFIABLE) / evidence path / corrected statement`.

### 0.5 Wave 0 output artifact
A single markdown document in the feature directory, e.g. `wave0-verified-state.md`, containing:
- the per-claim verdict table;
- the actual current file inventory of the claimed paths;
- the actual current dependency and wiring graph;
- the actual current event and store inventory;
- the list of claims that are false and the corrected facts.

### 0.6 Wave 0 discipline
- Wave 0 MUST NOT design the target architecture. It establishes facts only.
- Wave 0 MUST NOT guess. An unverifiable claim is recorded as `UNVERIFIABLE` with the reason.
- Wave 0 MUST NOT delete or rewrite existing functionality in order to make a claim true.

---

## 1. PRODUCT PURPOSE (§1.1–1.9)

### 1.1
COGNITIVE is a local-first evidence-centric investigation platform. It ingests heterogeneous sources, transforms them into structured evidence, builds and tests hypotheses, and maintains a persistent worldline model of the investigated reality.

### 1.2
The platform is designed for long-horizon research over adversarial and high-volume evidence. The real value is not a single classification result. The value is that a researcher can repeatedly pose a question, accumulate relevant evidence, see what the evidence implies, learn what remains unknown, direct new acquisition at that unknown, and retain the ability to replay, audit, and revise every step.

### 1.3
The platform has five primary modes:
1. **ACQUISITION** — get source material.
2. **INTERPRETATION** — turn source material into structured evidence.
3. **INVESTIGATION** — decide what matters, test hypotheses, maintain the worldline model.
4. **SCIENCE** — evaluate whether the world's model is statistically, causally, and epistemically sound.
5. **SYSTEM** — operate and evolve the platform itself.

### 1.4
A single operator may work in all five modes. The platform is not a pipeline with a fixed order. The operator may loop, backtrack, re-interpret, re-acquire, revise the worldline, and audit prior conclusions.

### 1.5
The primary unit of work is the **investigation**: a durable scope with its own sources, evidence, hypotheses, tasks, and revision history. The platform is investigation-first, not source-first.

### 1.6
The platform must be able to accumulate knowledge across investigations without silently merging incompatible scopes. Cross-investigation knowledge reuse is allowed only with explicit provenance and explicit scope.

### 1.7
The platform is local-first. It must be fully operable on a single machine with local services, without depending on external SaaS for correctness.

### 1.8
Determinism and replay are first-class. Every derived artifact must be reconstructible from immutable inputs, declared dependency versions, and recorded parameters.

### 1.9
The platform is honest about uncertainty. It must be able to represent contradiction, incompleteness, contested claims, low confidence, and "unknown" as first-class states, not as absence of data.

---

## 2. SYSTEM ARCHITECTURE (§2.1–2.9)

### 2.1
The platform consists of six architectural layers:
1. Source layer — external and internal sources.
2. Capture layer — how source content is acquired, versioned, and addressed.
3. Interpretation layer — how raw content becomes typed observations and signals.
4. Context layer — the durable research scope that binds sources, evidence, hypotheses, and tasks.
5. Worldline layer — the persistent, versioned model of the investigated reality.
6. Science layer — statistical, causal, and epistemological evaluation of the model.

Each layer has a strict responsibility boundary. Data may flow forward through the canonical event path. Direct, undocumented cross-layer writes are defects.

### 2.2
Layers communicate through a canonical event path and durable stores. A layer MUST NOT reach into another layer's store to write.

### 2.3
Observation records are addressed by an offset schema `content_digest`.
*Wave 0: verify against §0.3.*

### 2.4
Observation records are addressed by an offset schema `artifact_id`.
*Wave 0: reconcile with §2.3.*

### 2.5
`apps/acquisition/runtime/` contains runtimes for acquisition sources. The current runtime set includes SearXNG, Airbyte, BBOT, and an external-tool runtime.
*Wave 0: verify actual module list.*

### 2.6
`apps/shared` contains the shared domain substrate: identity, events, contracts, stores, and skills.

### 2.7
`apps/interpretation` transforms captures into observations, signals, and hypotheses.

### 2.8
`apps/investigation` owns investigation scope, tasks, and worldline maintenance.

### 2.9
`apps/science` owns statistical, causal, and epistemic evaluation.

---

## 3. CONTEXT GRAPH (§3.1–3.8)

### 3.1
The Context Graph is a first-class graph, not a derived view. It must be independently queryable and independently writable by the context layer only.
*Wave 0: verify the real record-locator field names — `record_locator` / `record_index` / `ordinal`.*

### 3.2
The Context Graph contains the following node types at minimum:
- `Investigation`
- `Question`
- `Scope`
- `Hypothesis`
- `Task`
- `EvidenceSet`
- `Claim`
- `Contradiction`
- `Unknown`
- `Revision`

### 3.3
The Context Graph contains the following edge types at minimum:
- `asks`
- `scopes`
- `supports`
- `contradicts`
- `refines`
- `delegates`
- `observes`
- `revises`
- `derived_from`
- `supersedes`

### 3.4
`EvidenceContext` already exists as a core domain object. It is a valid object, but its actual semantics must be verified before the Context Graph is designed around it. If it is an evidence/provenance frame rather than a research-scope context, then a **new, distinct `InvestigationContext` is required**, and `EvidenceContext` must not be overloaded.
*Wave 0: determine what `EvidenceContext` actually is.*

### 3.5
`EvidenceContext` is versioned. The version identity MUST be defined in this specification, not inherited implicitly.

### 3.6
The Context Graph MUST be durable. It MUST survive process restart and MUST support transactional updates.

### 3.7
The Context Graph MUST NOT be derived by re-deriving the knowledge graph on every query.

### 3.8
The Context Graph MUST distinguish between a graph that is *unknown* and a graph that is *empty*. "We have not investigated this" and "we investigated and found nothing" are different states.

---

## 4. ACQUISITION LAYER (§4.1–4.8)

### 4.1
Acquisition produces `Record` and `Artifact` derivation inputs. Record-level and artifact-level hash derivation MUST be defined precisely.
*Wave 0: verify real digest fields.*

### 4.2
`apps/acquisition/runtime/__init__.py` declares acquisition capabilities including `nmap` and `whatweb`.
*Wave 0: verify these capability declarations exist and are truthful.*

### 4.3
Acquisition includes a content filter (`primproc.py`) that removes unwanted content before interpretation.
*Contradicts §7.4. Wave 0 MUST resolve what `primproc.py` actually is.*

### 4.4
Real finders exist at `apps/shared/skills/interpret/record_finder.py` and `apps/shared/skills/interpret/digest_finder.py`.
*Wave 0: verify path, existence, and that they are real rather than stubs.*

### 4.5
Record-level and artifact-level hash derivation.
*Duplicate of §4.1. Wave 0 resolves.*

### 4.6
Acquisition is a runtime concern. The acquisition layer MUST NOT write to the knowledge graph, the worldline, or the context graph. It emits captures and records only.

### 4.7
Acquisition capabilities MUST be declared as data, discoverable at runtime, so the context layer can route obligations to capabilities without hardcoded source knowledge.

### 4.8
Acquisition is at-least-once. The platform MUST be idempotent under duplicate acquisition.

---

## 5. INTERPRETATION LAYER (§5.1–5.8)

### 5.1
Record lineage exists.
*Wave 0: verify which of the three lineages is implemented and which are planned.*

### 5.2
`AssemblyBatch` is the unit of interpretation.
*Wave 0: verify.*

### 5.3
Records carry lifecycle states `A` and `R` (`admission_state` / `record_state`) defined through `DefinitionLifecycle`.
*Wave 0: verify.*

### 5.4
A graph invariant exists (`apps/shared/domain/graph_invariant.py`).
*Wave 0: verify existence and actual guarantees.*

### 5.5
`EvidenceContext` exists as a core domain object.
*See §3.4 — Wave 0 determines its real semantics.*

### 5.6
`EntityResolver` exists.
*Wave 0: verify.*

### 5.7
Context formation exists.
*Wave 0: verify.*

### 5.8
Interpretation produces observations and signals. It MUST NOT decide investigation scope. Choosing what to investigate is a context-layer responsibility.

---

## 6. INVESTIGATION LAYER (§6.1–6.6)

### 6.1
Investigation is the primary unit of work.

### 6.2
`apps/investigation` has stable `fulltext` and `lemmatized` columns.
*Wave 0: verify existence and usage.*

### 6.3
`apps/investigation` contains hypothesis generation.
*Wave 0: determine whether this path is live, inert, or a second normalizer.*

### 6.4
Evidence and link endpoints exist.
*Wave 0: verify.*

### 6.5
There is no knowledge graph in PostgreSQL.
*Wave 0: verify actual current storage. If a graph IS stored in PostgreSQL, the migration plan changes materially.*

### 6.6
Investigation MUST own hypothesis lifecycle, task lifecycle, scope revision, and worldline contribution.

---

## 7. SCIENCE LAYER (§7.1–7.7)

### 7.1
`apps/science` has 19 builder files.
*Wave 0: count actual files.*

### 7.2
`apps/science` has 25 pipeline files.
*Wave 0: count actual files.*

### 7.3
`apps/science` has a `registry.py` mapping `SKILL.md` files.
*Wave 0: verify mechanism.*

### 7.4
`apps/science` has `primproc.py`.
*Directly contradicts §4.3. Wave 0 MUST resolve. The source asserts `primproc.py` exists in BOTH `apps/acquisition/runtime/` AND `apps/science/`.*

### 7.5
`apps/science` has `scientific_method.py`.
*Wave 0: verify.*

### 7.6
`apps/science` has `tool_spec.py` and `scientific_method_spec.py`.
*Wave 0: verify.*

### 7.7
Science MUST evaluate the worldline, not a private toy state. Every scientific evaluation MUST be anchored to a durable, versioned snapshot of the worldline.

---

## 8. PLATFORM CODE (§8.1–8.5)

### 8.1
The platform contains 257 rules.
*Wave 0: re-count.*

### 8.2
The platform contains 5 323 tests.
*Wave 0: re-count, and separate passing from failing.*

### 8.3
The platform contains 11 features.
*Wave 0: re-count.*

### 8.4
Test counts and rule counts are evidence of volume, not of quality. Wave 0 MUST report pass/fail distribution, not totals alone.

### 8.5
A rule that cannot be executed by any test is documentation, not a rule. Wave 0 MUST report the count of unenforced rules.

---

## 9. DOCUMENTATION AND PROCESS (§9.1–9.3)

### 9.1
`CONTEXT.md` contains full project context.
*Wave 0: verify.*

### 9.2
`README.md` contains the operator guide.
*Wave 0: verify.*

### 9.3
Documentation MUST be verified against code before it is treated as a specification.

---

## 10. WHAT THE PLATFORM CURRENTLY LACKS (§10.1–10.9)

### 10.1
There is no continuous intelligence loop. The platform processes sources but does not autonomously decide what to investigate next.

### 10.2
There is no durable research obligation model. "What do I need to find out?" is implicit in operator memory.

### 10.3
There is no context revision mechanism. Conclusions cannot be revised as a first-class, auditable operation.

### 10.4
There is no saturation model. The platform cannot distinguish "I have enough" from "I have not looked hard enough".

### 10.5
There is no action memory. The platform does not remember what acquisition was already attempted for which obligation.

### 10.6
There is no autonomous hypothesis proposal. Hypotheses are operator-authored only.

### 10.7
There is no durable frontier. Investigation progress is not a queryable object.

### 10.8
There is no connection between context revision and the worldline model. Conclusions and the world model evolve independently.

### 10.9
There is no coverage/saturation-based termination. Investigation never formally ends.

---

## 11. STRATEGIC TARGET (§11.1–11.5)

### 11.1
The target is a **context-driven continuous intelligence system**: a system in which the durable research context is the primary driver of acquisition, interpretation, hypothesis, and revision.

### 11.2
The system MUST close a loop:
```
Context → obligations → actions → acquisition → capture/observation
       → Redpanda → interpretation → resolution/admission
       → entity stream → worldline → science
       → context feedback (obligations, priorities, confidence, contradictions)
```
*Wave 0: verify whether "Layer 0 HTTP endpoint implements the entire pipeline" (§16.1). If Layer 0 is a real production path, closing this loop is a rewrite, not a wiring change.*

### 11.3
The loop MUST be continuous: it runs whenever the context has unresolved obligations, and it stops only when the context is saturated, closed, or explicitly suspended.

### 11.4
The system MUST remain operator-supervised. Continuous does not mean autonomous-without-approval. The system MUST propose; the operator MUST be able to accept, reject, modify, and prioritize at every stage.

### 11.5
The system MUST be explainable: for any decision it makes, the system MUST be able to state which context, which obligation, which evidence, and which rule produced it.

---

## 12. RESEARCH CONTEXT (§12.1–12.10)

### 12.1
An `InvestigationContext` is a durable, versioned object that defines: the investigation scope, the research questions, the active hypotheses, the known sources, the collected evidence, the current obligations, the decision history, and the revision history.

### 12.2
`InvestigationContext` is NOT the same object as `EvidenceContext`.
*Per Wave 0 (§3.4): if `EvidenceContext` is an evidence/provenance frame, `InvestigationContext` MUST be a new, separate object and MUST NOT be implemented by renaming or overloading `EvidenceContext`.*

### 12.3
`InvestigationContext` identity MUST be content-derived and stable:
`context_id = CXI-{digest128(canonical_context_material)}`
where `canonical_context_material` is a canonical serialization of the identifying fields. The digest MUST NOT depend on mutable revision state.

### 12.4
`InvestigationContext` MUST have an explicit revision identity, separate from `context_id`:
- `context_id` — stable identity of the investigation;
- `revision` — monotonically increasing revision number of the context state;
- `parent_revision` — the revision this one supersedes.

### 12.5
Context snapshots are append-only. A revision MUST NOT mutate a prior snapshot. `context_history` is a durable append-only log of context states, so that the system can answer "what did we believe at revision N, and why".

### 12.6
Context state MUST be durable in a transactional store, and MUST survive process restart. The Context Engine MUST NOT hold context state only in memory.

### 12.7
Context state MUST be reconstructible: given the context definition, the decision history, and the event log, the current context state MUST be reconstructible by replay.

### 12.8
Context MUST be explicitly scoped. An investigation MUST NOT silently absorb evidence from another investigation. Cross-investigation linkage MUST be explicit and recorded as a scope decision.

### 12.9
Context MUST record provenance: every context revision MUST record which events, which decisions, and which operator actions caused it.

### 12.10
Context MUST support partial and unknown states. A context in which nothing has been investigated MUST be distinguishable from a context in which investigation was performed and produced nothing.

---

## 13. RESEARCH OBLIGATIONS (§13.1–13.12)

### 13.1
A `ResearchObligation` is a durable, first-class statement of what MUST be learned, why it matters, and what would count as an answer.

### 13.2
A `ResearchObligation` MUST have:
- `obligation_id` — stable identity;
- `context_id` — owning context;
- `question` — what must be learned;
- `rationale` — why it matters to the investigation;
- `target_knowledge_type` — what kind of knowledge would answer it (entity, relation, event, attribute, absence, contradiction, boundary);
- `priority` — relative importance;
- `status` — one of `open`, `partially_satisfied`, `satisfied`, `abandoned`, `blocked`;
- `created_by` — event, rule, or operator action;
- `satisfaction_criteria` — what counts as an answer;
- `confidence` — current confidence that the obligation is satisfied;
- `related_hypothesis_ids`;
- `blocking_dependencies`.

### 13.3
Obligations MUST be generated by the Context Engine from: operator intent, unresolved questions, evidence contradictions, coverage gaps, low-confidence claims, saturation shortfalls, and anomaly-driven follow-up.

### 13.4
Obligation generation MUST be rule-based, versioned, and inspectable. The rules MUST be recorded so the operator can see why an obligation exists.

### 13.5
Obligations MUST NOT be silently dropped. Every obligation MUST reach a terminal state (`satisfied` or `abandoned`) with a recorded reason, or the system MUST report the obligation set as non-closed.

### 13.6
A `ResearchAction` is a candidate means of satisfying an obligation: a concrete plan combining capabilities, sources, methods, and expected information gain.

### 13.7
A `ResearchAction` MUST have: `action_id`, `target_obligation_id`, `proposed_method`, `capability_requirements`, `expected_information_gain`, `estimated_cost`, `priority`, `requires_operator_approval`, `status`.

### 13.8
Actions MUST NOT be executed directly. Actions MUST be realized as concrete tasks with explicit runtime routing, and the mapping MUST be recorded.

### 13.9
The Context Engine MUST prefer routing to existing capabilities. It MUST propose an action only if no existing capability satisfies the obligation, and it MUST then record the new capability as a proposed capability requirement rather than implementing it implicitly.

### 13.10
Obligation satisfaction MUST be evaluated by rules, not by operator assertion alone. The rules MUST consider: evidence coverage for the obligation's question, saturation of the relevant source space, presence of contradicting evidence, and confidence thresholds.

### 13.11
Contradictory evidence MUST create a new obligation or a contradiction record, not a silent overwrite of a claim.

### 13.12
Obligation lifecycle MUST be a durable append-only history, so the system can answer "why did we stop investigating this, and when".

---

## 14. CONTEXT ENGINE (§14.1–14.14)

### 14.1
The Context Engine is a service that owns: context state, obligation generation, obligation satisfaction evaluation, action proposal, decision recording, and context revision.

### 14.2
The Context Engine MUST be a separate concern from acquisition, from interpretation, and from the worldline. It MUST consume their outputs and MUST NOT embed their logic.

### 14.3
The Context Engine MUST be incremental. On each update it MUST process only what changed, MUST NOT recompute the whole context from scratch, and MUST be able to explain which change caused which context update.

### 14.4
The Context Engine MUST NOT be a god object. It MUST be decomposed into: an obligation generator, a satisfaction evaluator, an action proposer, a decision recorder, and a revision manager.

### 14.5
Context updates MUST be deterministic given the same event sequence, the same rules version, and the same parameters. Non-determinism from wall-clock time or unseeded randomness is forbidden in context state, except where an explicit `observed_at` field is recorded.

### 14.6
Every context update MUST be explainable: the system MUST be able to state which input event, which rule, and which previous state produced the new state.

### 14.7
The Context Engine MUST enforce separation between the constitutional core (deterministic, versioned, inspectable rules) and the optional adaptive layer (statistical scoring, heuristics, learned prioritization). The constitutional core MUST remain functional and correct with the adaptive layer fully disabled.

### 14.8
The Context Engine MUST be able to run in a strictly deterministic mode for replay and audit, and in an adaptive mode for operation. The mode MUST be explicit in the decision record.

### 14.9
Obligation satisfaction evaluation MUST be a pure, versioned function of (obligation, evidence index, saturation state, contradiction state). It MUST be unit-testable in isolation.

### 14.10
Context revisions MUST be committed transactionally with their decision records, so a revision and its justification cannot diverge.

### 14.11
The Context Engine MUST handle missing, late, and out-of-order events without corrupting context state. It MUST define an explicit policy for each.

### 14.12
The Context Engine MUST NOT depend on a specific UI, a specific transport, or a specific storage engine for its core logic.

### 14.13
The Context Engine MUST expose a query interface for: current context state, open obligations, satisfied obligations, contradictions, decisions, and revision history.

### 14.14
The Context Engine MUST be operable without the rest of the platform, so that context logic can be tested and evolved independently.

---

## 15. SATURATION AND CONTINUITY (§15.1–15.11)

### 15.1
Saturation is a first-class concept: a source space is saturated for an obligation when further acquisition from that space is not expected to change the answer.

### 15.2
Saturation MUST be estimated from evidence, and MUST account for: number of distinct sources consulted, source diversity, marginal information gain per acquisition, and stopping conditions.

### 15.3
An obligation MUST NOT be marked `satisfied` on acquisition count alone. Acquisition count is evidence of effort, not of sufficiency. Saturation and coverage are the sufficiency criteria.

### 15.4
The system MUST be able to state: "this obligation is satisfied because the source space is saturated at coverage 0.92 with marginal gain below 0.03".

### 15.5
The system MUST distinguish: saturated-and-satisfied, saturated-and-contradicted, saturated-and-insufficient, not-saturated.

### 15.6
Marginal information gain MUST be computable and observable. The system MUST record the expected and realised information gain of each action.

### 15.7
The system MUST support budget-bounded investigation: an investigation MAY have a budget, and the system MUST respect it and report budget consumption against obligation satisfaction.

### 15.8
The system MUST support source exhaustion as an explicit terminal condition: the source space is exhausted, not merely unvisited.

### 15.9
An investigation MUST be formally closable: the system MUST be able to report "all obligations resolved or explicitly abandoned, with reasons".

### 15.10
The system MUST support re-opening: a closed investigation MUST be re-openable when new events contradict a satisfied obligation.

### 15.11
Termination MUST never be silent. The system MUST record why it stopped, what remains unknown, and what would re-open the investigation.

---

## 16. CANONICAL EVENT PATH AND STREAM-FIRST ARCHITECTURE (§16.1–16.9)

### 16.1
Layer 0 currently implements the entire pipeline over HTTP.
*This is a CRITICAL Wave 0 claim. If Layer 0 is a real production path, then establishing a canonical event path is a REWRITE of Layer 0, not a wiring change. Wave 0 MUST determine Layer 0's real role and status, and MUST report whether it is live production, a legacy path, a test harness, or dead code.*

### 16.2
Layer 0 MUST NOT be the production orchestration path. Layer 0 MAY remain as a test harness or a thin façade over the canonical path, but it MUST NOT contain business orchestration that bypasses the event-driven path.

### 16.3
The canonical path MUST be event-driven and stream-first: Redpanda as the transport, durable stores as the source of truth, and consumers that are independently deployable and independently replayable.

### 16.4
Every cross-layer communication MUST go through the canonical event path. A layer MUST NOT write directly into another layer's store.

### 16.5
Acquisition MUST NOT write to the knowledge graph, the worldline, or the context graph. Acquisition emits captures and records; interpretation and admission own everything downstream.

### 16.6
Every event MUST carry a stable identity, a schema version, a producer identity, a logical timestamp, an observed timestamp, a trace correlation, and a causation reference.

### 16.7
Every event MUST be idempotent under redelivery. Consumers MUST be able to deduplicate by event identity.

### 16.8
The event transport MUST be replaceable. The canonical contract MUST be defined in terms of the event schema, not in terms of a specific broker.

### 16.9
Layer 0's existing behaviour MUST be preserved as a regression baseline: whatever Layer 0 does today, the canonical path MUST be able to reproduce, and any divergence MUST be explicit and justified.

---

## 17. TRACEABILITY (§17.1–17.7)

### 17.1
Every output artifact MUST declare its inputs by stable identity, its dependency versions, its parameters, and its producing code version.

### 17.2
Every derived artifact MUST be reconstructible from its declared inputs and versions.

### 17.3
The platform MUST maintain a dependency graph over artifacts, so that a change in an input can be traced to every affected output.

### 17.4
Every hypothesis test MUST record which observations it used, which interpretation version produced them, and which parameters were applied.

### 17.5
Every claim MUST record its evidence, its derivation path, and its confidence.

### 17.6
Every worldline state MUST record the events that produced it.

### 17.7
The platform MUST be able to answer, for any conclusion: "which raw evidence, which parser version, which rules version, and which decisions produced this?".

---

## 18. ACCEPTANCE CRITERIA (§18.1–18.10)

### 18.1
The primary metric: **the number of real observations that complete the canonical loop and produce durable downstream state**.

### 18.2
A single real observation MUST be demonstrable end-to-end: from a real source, through capture, through Redpanda, through interpretation, through resolution, through admission, into the knowledge graph, into the worldline, and into a durable projection.

### 18.3
The loop MUST be demonstrably continuous: a context with unresolved obligations MUST generate actions; those actions MUST produce observations; those observations MUST update the context.

### 18.4
The system MUST be able to state, for any investigation: which obligations are open, which are satisfied, which are contradicted, and why.

### 18.5
The system MUST be able to close an investigation with a formal termination report.

### 18.6
The system MUST be able to re-open a closed investigation when new contradicting evidence arrives.

### 18.7
Every conclusion MUST be traceable to raw evidence through the full chain.

### 18.8
The system MUST run locally with no external SaaS dependency for correctness.

### 18.9
The system MUST pass its own test suite deterministically, and MUST report failures honestly rather than suppressing them.

### 18.10
The system MUST be operable by one person on one machine for a real investigation lasting days.

---

## 19. FULL END-TO-END DEMO (§19.1–19.4)

### 19.1
The full demonstration MUST use real sources: SearXNG (web search), Airbyte (structured data sources), and an external tool.
*Note: the current acquisition layer already proves SearXNG, Airbyte, Maigret, BBOT, and SpiderFoot. Wave 0 MUST reconcile this list with what actually exists.*

### 19.2
The demonstration MUST use Common Crawl as an additional real source.
*Wave 0: verify whether Common Crawl acquisition exists. If not, this is new work in a later wave, not a claim about the current state.*

### 19.3
The demonstration MUST show the loop running for a substantial period, not for a single scripted pass.

### 19.4
The demonstration MUST produce a durable, inspectable worldline and a context history that shows the investigation evolving.

---

## 20–32. IMPLEMENTATION WAVES (§20–§32)

*This section is normative. It describes the target state, and it is binding regardless of Wave 0 findings, because it describes where the system must go, not where it currently is.*

### §20 WAVE 0 — VERIFICATION
Verify the current state. Produce the per-claim verdict table (§0.4–0.5). Correct the false claims. Do not design. Do not guess.

### §21 WAVE 1 — CANONICAL EVENT PATH
Establish the canonical event path end-to-end with Redpanda. Ensure every cross-layer communication flows through it. Determine and resolve the Layer 0 status (§16.1). Enforce §16.4–16.8: stable identity, schema version, producer identity, timestamps, trace and causation, idempotency.

### §22 WAVE 2 — CONTEXT ENGINE FOUNDATION
Implement `InvestigationContext`, `ContextSnapshot`, `ContextRevision`, `ResearchObligation`, `ResearchAction`, `ContextFrontier`, `ContextDecision`, and the coverage/saturation model. Persist durably in a transactional store. Implement reconstruction by replay (§12.7). Enforce §12.3–12.5 identity and revision semantics.

### §23 WAVE 3 — OBLIGATION LIFECYCLE
Implement obligation generation rules (§13.3–13.4), satisfaction evaluation (§13.9, §14.9), contradiction handling (§13.11), and the append-only obligation history (§13.12). Enforce the prohibition on silent dropping (§13.5).

### §24 WAVE 4 — ACTION PROPOSAL AND ROUTING
Implement `ResearchAction` proposal, expected information gain (§15.6), cost estimation, capability requirement matching (§13.9), operator approval, and realization of actions as concrete tasks with explicit runtime routing. Implement action memory (§10.5).

### §25 WAVE 5 — AUTONOMOUS HYPOTHESIS AND QUESTION GENERATION
Implement autonomous hypothesis and question proposal from context state: from contradictions, from coverage gaps, from low-confidence claims, and from saturation shortfalls. Implement durable frontier (§10.7).

### §26 WAVE 6 — WORLDLINE MATERIALIZATION
Implement the worldline materializer: canonical entity stream, life events, state transitions, durable snapshots, and a registry with method and dependency fingerprints. Ensure the worldline is derived from the canonical event path, not from a private path.

### §27 WAVE 7 — SCIENCE CONVERGENCE
Implement: causal model plus identification/estimate/refute; topology analysis from real worldline windows; change-point detection; calibration as `abs(drift) <= tolerance`; robustness and replay; method registry with dependency fingerprints; separation of statistical, causal, and epistemic layers.

### §28 WAVE 8 — COGNITIVE LOOP CLOSURE
Close the loop. Context drives acquisition; acquisition produces observations; observations update the worldline; the worldline is evaluated by science; science and worldline feed back into the context: obligations, priorities, confidence, contradictions. The loop runs continuously and stops only on saturation, closure, or suspension.

### §29 DEPENDENCY DAG AND ORDERING
Dependencies between waves are strict. A wave MUST NOT start before its dependencies are complete. The dependency graph MUST be recorded explicitly in the plan, and the plan MUST state the critical path.

### §30 INDEPENDENT PARALLELISM
Waves that are not causally dependent MAY be executed in parallel. Independence MUST be determined by the dependency graph, not by convenience.

### §31 AGGRESSIVE PARALLEL EXECUTION
Within a wave, independent work items SHOULD be executed in parallel. The plan MUST identify which items are independent.

### §32 UNIFIED ORCHESTRATION
All waves MUST be executed under one orchestrator, with a single source of truth for status, and with a single definition of done.

---

## 33. NON-FUNCTIONAL REQUIREMENTS (§33.1–33.10)

### 33.1 Determinism
The same input, the same rules version, and the same parameters MUST produce the same output.

### 33.2 Replayability
Every derived artifact MUST be reconstructible without re-acquiring from the network.

### 33.3 Idempotency
Every consumer MUST be idempotent under at-least-once delivery.

### 33.4 Local-first
The platform MUST be fully operable on one machine with local services, without external SaaS for correctness.

### 33.5 Durability
Every state transition MUST be durably committed before it is observable.

### 33.6 Auditability
Every decision MUST be explainable by which context, which obligation, which evidence, and which rule produced it.

### 33.7 Honesty about uncertainty
The system MUST represent contradiction, incompleteness, contested claims, low confidence, and unknown as first-class states.

### 33.8 Separation of concerns
Each layer MUST own its responsibility strictly. Cross-layer writes are defects.

### 33.9 Composability
Each component MUST be independently testable and independently replaceable.

### 33.10 Resource discipline
The platform MUST bound its own resource use: memory, storage, and computation per investigation MUST be observable and MUST be budgetable.

---

## 34. EXPLICITLY OUT OF SCOPE (§34.1–34.8)

### 34.1
A distributed multi-region deployment. Local-first is the requirement; distribution is a later concern.

### 34.2
A general-purpose LLM agent framework. The Context Engine's constitutional core is deterministic and rule-based; LLM-based assistance is optional and MUST NOT be in the constitutional core (§14.7).

### 34.3
A GUI-first product. The UI is subordinate to the platform's correctness; the loop must be demonstrable headless.

### 34.4
A hosted SaaS offering.

### 34.5
Real-time collaborative multi-user editing.

### 34.6
A general web crawler replacing existing acquisition runtimes. Existing runtimes are reused (§13.9).

### 34.7
Replacing Redpanda or the existing event contract with a different transport. The contract is defined in terms of the schema, not the broker (§16.8).

### 34.8
A rewrite of acquisition. Acquisition runtimes already work and MUST be reused, not replaced.

---

## 35. DELIVERABLE ACCEPTANCE (§35.1–35.5)

### 35.1
The platform MUST demonstrably close the cognitive loop with real sources, and the loop MUST run for a substantial period (§19.3), not as a single scripted pass.

### 35.2
Every conclusion MUST be traceable to raw evidence through the full chain (§17.7).

### 35.3
The system MUST be able to report, for any investigation: open obligations, satisfied obligations, contradictions, decisions, and revision history.

### 35.4
The system MUST be able to close an investigation with a formal termination report, and re-open it on contradicting evidence (§18.5–18.6).

### 35.5
The system MUST run locally and MUST pass its own test suite deterministically, reporting failures honestly (§18.8–18.9).

---

## 36. STRATEGIC PRINCIPLES (§36.1–36.5)

### 36.1
Durable research context is the primary driver of the system. Data does not drive research; context does.

### 36.2
The system MUST run indefinitely, with the context as the durable reason to continue.

### 36.3
Human oversight is a feature, not a limitation. The system proposes; the operator decides.

### 36.4
Data and knowledge accumulate; context is what makes accumulation meaningful. The context is the durable reason the system continues to run.

### 36.5
The system MUST be honest, and MUST model unknown explicitly. The primary risk of an intelligence system is confident error, not absence of output.

---

## CROSS-REFERENCE TO COMPANION DOCUMENT
The UI requirements for this feature are in `ui-upgrade.md`. The two documents are one contract: the UI is the operator surface for the context-driven continuous intelligence fabric, and the platform's correctness requirements are binding on the UI implementation.
