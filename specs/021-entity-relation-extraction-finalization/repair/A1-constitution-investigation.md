# A1 — Constitution Check repair and the Investigation boundary

**Job**: A1 (constitution investigation) | **Feature**: `021-entity-relation-extraction-finalization`
**Repo root**: `C:\Users\tim\Desktop\COGNITIVE\1` (the parent `C:\Users\tim\Desktop\COGNITIVE` is
**not** the repo)
**Governing document**: `.specify/memory/constitution.md`, **v1.0.0 | Ratified 2026-09-07 |
Last Amended 2026-09-07**, 75 lines. (The copy at `C:\Users\tim\Desktop\COGNITIVE\.specify\memory\constitution.md`
is an unfilled template and was not read as authority.)
**Companion jobs**: `A2-identity-subsystem.md` and the other `repair/` files are owned by other
agents and are untouched here.
**Read-only**: this job edited no existing file. It writes exactly this one file.

---

## Findings I verified

Every premise in the job brief was re-derived from the code before being used. Ten are confirmed
verbatim. Six are corrected, and two are materially understated in a way that changes the
remediation. Each disagreement is stated explicitly.

### 1.1 Confirmed, verbatim

**F1 — The Constitution Check in `plan.md` has no row for any of the 7 Core Principles.**
`plan.md:79-87` is the entire table. It contains four numbered rows and one prose row:

| `plan.md` row | Numeral it cites | What that numeral actually is |
|---|---|---|
| `I-2 \`Mention != Candidate != Entity != …\` (7 distinct levels)` | `I-2` | Domain Invariant **2** ("Mention != Candidate != Entity") |
| `I-3 \`Assertion != truth\`` | `I-3` | Domain Invariant **3** ("Assertion != truth") |
| `I-4 \`Graph != source of truth\`; projection-first` | `I-4` | Domain Invariant **4** ("Graph != source of truth") |
| `III projection-first; graph is a projection` | `III` | Core Principle **III** — the *only* correct Core Principle citation in the table |
| `VI determinism` | `VI` | Core Principle **VI** is *Process-Centric* |
| `IV tenancy` | `IV` | Core Principle **IV** is *No Single Store / Graph / Score* |

The `I-2` / `I-3` / `I-4` prefixes are Domain-Invariant numbering, not Core-Principle numbering. So
the table's coverage of the 7 Core Principles is **0 of 7**. `spec.md` uses the same convention
correctly and separately: `spec.md:359-372` labels its five rows `INV-001`…`INV-005` and calls the
section `#### Constitutional invariants` — the right name for them.

**F2 — `plan.md:85` mis-cites Principle VI as a determinism requirement.** Verbatim:

```
| VI determinism | Content-addressed ids re-derived, never trusted; no result may depend on dict iteration order | **GAP** — `signal_refs` is identity material but never sorted, so `candidate_id` depends on caller order; determinism survives only because `assembly.py:338` sorts by hand |
```

The constitution's Principle VI, verbatim and in full, is one sentence:

> `### VI. Process-Centric`
> `The user creates an Investigation — not a graph. Graphs, search indices, analytical structures, and TDA complexes materialize automatically within the investigation lifecycle and its policy/budget/freshness constraints.`
> — `constitution.md:20-21`

There is no determinism clause in it. Determinism is real and load-bearing here, but it is
**unnumbered** — it is not in the Core Principles, not in the 12 Domain Invariants, and not in the
Technology Baseline. Its only constitutional homes are INV-12 and the Additional Constraints'
"Idempotency" clause. The determinism defect the row describes is nonetheless **real**, and I
re-state it under the correct anchor: `relation_candidate.py:826-836` normalises
`supporting_spans`, `observation_refs` and `evidence_refs` in `__post_init__` and **not**
`signal_refs`, which is identity material at `relation_candidate.py:539`. Order-independence
survives only because `assembly.py:253` sorts by hand
(`ordered = tuple(sorted(signals, key=lambda s: s.signal_id))`).

**F3 — the VI-determinism mis-cite is not confined to `plan.md`; it has propagated into a
constitutional test file's name and docstring.** `apps/shared/tests/constitution/test_iv_vi_tenancy_and_determinism.py`
exists, and its own header reads:

> `"""Constitution IV and VI: tenants are fail-closed, and two processes must agree.`
> …
> `**IV — every durable fact is tenant-scoped, and an empty tenant is not a tenant.**`
> …
> `**VI — determinism: the same inputs give the same addresses, in any process, in any order.**`

Both attributions are wrong: tenancy is **VII**, determinism is unnumbered. The consequence is not
cosmetic — this is the *constitution test suite*, the place where the mis-citation should be
prevented, and it contains no test for Principles **I**, **II**, **V**, **VI** or **VII**.

**F4 — `plan.md:86` mis-cites Principle IV for tenancy.** Verbatim:

```
| IV tenancy | No cross-tenant writes or reads | **PASS** — assemblable and `run_producer` both refuse cross-tenant output |
```

`apps/interpretation/extractors/signals/protocol.py:294-300` verbatim — this is the code the
mis-cite was inherited from:

```python
    if signal.tenant_id and signal.tenant_id != scope.tenant_id:
        raise SignalContractError(
            "signal_tenant_mismatch",
            f"producer {declaration.producer_ref!r} was run for tenant "
            f"{scope.tenant_id!r} and emitted a signal belonging to {signal.tenant_id!r}; "
            "cross-tenant output is refused fail-closed (constitution IV)",
        )
```

The same mis-cite is at `apps/control-plane/semantic_path/assembly.py:263-268`
(`"fail-closed (constitution IV)"`). A repo-wide sweep finds the tenancy→IV error at **20 sites**
and the determinism→VI error at **6 sites**, spanning `apps/acquisition/`,
`apps/control-plane/db/schema.py`, four Alembic migrations (`016`, `018`, `019`, `020`),
`apps/shared/domain/temporal_observation.py:267`, `apps/interpretation/extractors/signals/signal.py:342`,
and `apps/shared/tests/constitution/`. A constitutional citation that is wrong in 26 places is not
a typo; it is an uncited convention, and it is why the gate could pass on a mis-cited row.

Note the contrast that proves the codebase already knows the right numeral:
`apps/control-plane/services/query_planner.py:12-15` says

> `* a backend failure **degrades** a query, it never ends it -- a sick backend`
> `  costs the caller the healthy backends' results unless the total outage is`
> `  raised explicitly (:class:\`AllBackendsFailed\`), because \`[]\` means "no`
> `  matches" (Constitution Invariant 9);`
> `* the composite is *derived* from \`relevance\` and \`support\`, both of which`
> `  are retained, so no reader has to take a single score on faith`
> `  (Constitution IV).`

That is Principle IV used correctly. The wrong sites are the ones that reached for a numeral
without the clause text in front of them.

**F5 — the supersession clause is inverted in two places.** Constitution `Governance`, verbatim
(`constitution.md:71`, first eleven words):

> `Constitution supersedes all other practices.`

`plan.md:5-8` states the opposite:

> `**Input**: Feature specification from \`specs/021-entity-relation-extraction-finalization/spec.md\``
> `(102 functional requirements, 5 constitutional invariants, 16 measurable outcomes, 9 user`
> `stories). The unabridged user brief is \`input.md\` in this directory and governs over this`
> `document wherever the two appear to differ.`

`spec.md:16-20` states the opposite, in a blockquote placed at the top of the document where it
reads as a rule of construction:

> `> The complete, unabridged user brief is \`input.md\` in this directory (3411 lines, all`
> `> 115 sections, reproduced verbatim).** This document is the engineering reading of it. Where`
> `> this document appears to compress or interpret something, \`input.md\` governs — in`
> `> particular §0 (working mode), §45 (no majority vote), §51–56 (projection is a`
> `> projection), §72–75 (structural prohibitions) and §110 (development order).`

**F6 — the gate's `PASS` on the supersession clause rests on a worked example where the two
documents agree.** `plan.md:87` verbatim:

```
| "Constitution supersedes all other practices" | Any requirement in this plan that conflicts loses | **PASS** — the brief's §45 (no majority vote) and the constitution agree; where the brief's docstrings disagree with behaviour, behaviour wins and the docstring is corrected |
```

`input.md` §45 is *"no majority vote"*. Constitution INV-3 is *"Assertion != truth"*. A brief that
forbids majority-vote semantic assembly and a constitution that forbids a single score equalling
truth point the same way here. A gate row evaluated only on cases of agreement cannot detect an
inversion, and this one was evaluated only on agreement. The row's second clause — *"where the
brief's docstrings disagree with behaviour, behaviour wins"* — is the constitution's rule applied
to a *third* party (the code), which is the tell: the document knows the rule and applies it
everywhere except to the one question that was asked.

**F7 — Principle VI has no counterpart in the brief, so the constitution plainly wins.** A search of
`input.md` for `investigation` returns nothing. `spec.md` mentions `Investigation` in exactly one
line, and it is the reachability table's dead-code row (`spec.md:809`). The brief's whole
architecture statement is the five-object chain at `spec.md:22-27` — *what was observed* → *what
could it be* → *what our regime calls it* → *what survived validation* → *what graph view do we
project* — which is a **pipeline**, not a lifecycle. The brief never says who starts it or what
bounds it. Principle VI is therefore not in tension with the brief; it is simply unanswered by
it, which is the strongest possible case for the constitution governing.

**F8 — the entity pipeline the plan wires is an unbounded, non-constitutional entry point, and it
is the one currently live.** `services/entity_pipeline.py:38` is

```python
async def run_live_entity_pipeline(*, tenant_id: str, entity_id: str, identity: dict[str, Any], source_records: list[dict[str, Any]], catalog: Catalog, operations: Any) -> None:
```

It takes no `investigation_id`. It reaches straight into `interpret_warc_capture`
(`entity_pipeline.py:75-80`) and then into the graph, and it publishes completion on an in-process
module-level dict and an in-process SSE hub:

```python
        from api.routes.entities import _entity_streams
        _entity_streams[(tenant_id, entity_id)] = list(records)
        …
        from api.sse import hub
        hub.publish("temporal.materialization.ready", {…})
```
— `entity_pipeline.py:87-96`

That is user → extractor → graph with no investigation, no policy/budget/freshness gate, and a
process-lifetime store — the exact shape Principle VI forbids. FR-100 nominates it as
*"THE production seam"* (`plan.md:155`) and makes it mandatory.

**F9 — `workflows/investigation.py` is 291 lines, unregistered, calls two activities that exist
nowhere, and is not runnable as written.** All of it verified:

- **Unregistered.** `apps/control-plane/workflows/worker.py:20-27` is the only Temporal worker and
  registers exactly:

  ```python
      worker = Worker(
          client,
          task_queue=TASK_QUEUE,
          workflows=[TemporalEntityMaterializationWorkflow],
          activities=[reconcile_and_publish],
      )
  ```

  `InvestigationWorkflow` and `RecrawlWorkflow` appear nowhere in it.
- **Two non-existent activities.** `investigation.py:212-216` executes `"acquisition.acquire_batch"`
  and `investigation.py:287-291` executes `"acquisition.recrawl"`. A repo-wide search for
  `acquire_batch` and `acquisition.recrawl` returns those two call sites and **no definition**. The
  only `@activity.defn` in the repository is `temporal_materialization.py:24`
  (`name="temporal_materialization.reconcile_and_publish"`).
- **A third defect the brief did not name.** `investigation.py:286` is
  `workflow.signal(InvestigationWorkflow, "schedule_recrawl")` — a call on the workflow **class**
  from inside a different workflow. Temporal signals address a running workflow by workflow-id;
  they are not a method dispatch. Even with both missing activities supplied, this call cannot
  reach a target.

**F10 — there is no CI.** `Test-Path .github` → `False`. `plan.md:54-55` already records this:
`There is **no CI** (\`.github/\` does not exist), no Makefile, no tox/nox, and no test-runner`
`script — the gate is run by hand.` The constitution requires `Compliance is verified on every
PR/review` (`constitution.md:73`).

### 1.2 Where I disagree with the brief

**D-1 — "omits 5 of 7" understates it; it is 7 of 7.** The brief says the table omits *I, II, V,
VI, VII* and "mis-cites 2 of the 7 it has". As shown in F1, the table's only Core-Principle
citations are `III` (correct), `VI` (wrong) and `IV` (wrong); `I-2`/`I-3`/`I-4` are Domain
Invariants wearing a Principle prefix. The remediation is therefore not "add five rows" — it is
"replace the table", because a reader who trusts the existing rows will believe Principles III and
IV were checked when neither was checked as written. The D1 table supersedes the old one in full;
nothing in it is carried forward except its (correct) verdicts on Domain Invariants 2, 3 and 4,
which are restated and marked as preserved.

**D-2 — "there is no `CANDIDATE` and no `ENTITY` hop" understates the Evidence-First defect by one
whole hop kind.** The brief is right that `EVIDENCE_BACKWARD_CHAIN` has neither.
`evidence_lineage.py:81-89` verbatim:

```python
EVIDENCE_BACKWARD_CHAIN: tuple[HopKind, ...] = (
    HopKind.RELATION,
    HopKind.ASSERTION,
    HopKind.MENTION,
    HopKind.SEGMENT,
    HopKind.OBSERVATION,
    HopKind.CAPTURE,
    HopKind.SOURCE,
)
```

`DERIVATION_FORWARD_CHAIN` (`evidence_lineage.py:102-112`) verbatim:

```python
DERIVATION_FORWARD_CHAIN: tuple[HopKind, ...] = (
    HopKind.SOURCE,
    HopKind.CAPTURE,
    HopKind.OBSERVATION,
    HopKind.SEGMENT,
    HopKind.MENTION,
    HopKind.CANDIDATE,
    HopKind.ASSERTION,
    HopKind.RELATION,
    HopKind.ENTITY,
)
```

`HopKind` (`evidence_lineage.py:50-65`) has nine members, and **`SIGNAL` is not one of them**:

```python
class HopKind(StrEnum):
    SOURCE = "source"
    CAPTURE = "capture"
    OBSERVATION = "observation"
    SEGMENT = "segment"
    MENTION = "mention"
    CANDIDATE = "candidate"
    ASSERTION = "assertion"
    RELATION = "relation"
    ENTITY = "entity"
```

So `SIGNAL` is absent from **both** directions. The consequence is sharper than the brief states:
`spec.md:897-898` (SC-013) requires the round trip `edge → claim → candidate → signals
→ observations → source` and back, and `spec.md:311-313` (US9) requires the same walk. **Neither
chain can traverse to a signal, in either direction.** The missing `CANDIDATE` on the backward
chain makes the walk impossible; the missing `SIGNAL` on *both* chains makes it impossible even if
`CANDIDATE` is restored. Principle II names the required chain and includes a signal-bearing level:
*"Finding → Analytical/Topological Feature → Graph/Assertion → Evidence → Observation → Raw
Object → Source"* — and the repository's nine-hop ladder has no member corresponding to
`Analytical/Topological Feature` either. This is a **type-vocabulary** defect, not a
chain-ordering defect, and no reordering of a tuple fixes it. My FR-109 requires the new hop kind.

**D-3 — the K7 conflict is not only between Principle II and US9; `spec.md` contradicts itself.**
`spec.md:371-372` states, as a constitutional invariant:

> `- **INV-005**: Evidence lineage and derivation lineage stay separate. A candidate is`
> `  derivation, never evidence. (§68, §69)`

and `spec.md:897-898` states, as a success criterion:

> `- **SC-013**: For every projected edge, the round trip \`edge → claim → candidate → signals`
> `  → observations → source\` and back reaches every edge that source fed.`

`evidence_lineage.py:75-80` shows INV-005 is a *deliberate* design with a written argument:

> `#: \`\`CANDIDATE\`\` is deliberately **absent** (T014). A candidate is a hypothesis about a`
> `#: relation, not a carrier of the evidence for one: it holds no observation of its own, it`
> `#: holds *references* to observations. Putting it here would make the evidence walk imply`
> `#: that a reading is itself evidence, and would let a claim be justified by appeal to an`
> `#: inference rather than to anything anybody saw. A candidate appears in the other`
> `#: dimension instead, where it belongs.`

That argument is good and I do not propose to overturn it. What is wrong is that one document
cannot assert both INV-005 and SC-013. The resolution is not to weaken INV-005; it is to recognise
that **the backward chain is not the only admissible walk**. Principle II requires that knowledge
*trace fully* to a raw object; it does not require the trace to be a single linear hop list. A
claim's warrant is the chain to the source *through the evidence records*, and a candidate's
participation in that chain is as a **reference resolvable from** the warrant path, not as an edge
in it. That resolution is a design decision, so it is an **ADR** — D5.2. FR-109 is written so it
does not pre-empt the ADR's outcome.

**D-4 — `services/layer0_pipeline.py` is not merely unwired; it is a second
constitution-shaped pipeline with no Investigation, which makes keeping it a Principle VI
liability rather than a neutral leftover.** `layer0_pipeline.py:296-303` is a `seed()` whose
`investigation_id` is a **defaulted-out optional parameter**:

```python
    async def seed(
        self,
        *,
        identifiers: dict[str, str],
        tenant_id: str,
        investigation_id: str = "",
```

i.e. the primary way to start work has no investigation. Its docstring says so in its own words
(`layer0_pipeline.py:307-310`): `The missing outbound half of the nervous system: an entity created in the UI (FIO/phone/email/domain…) triggers web search`. The class is presented as the composition root
(`layer0_pipeline.py:10-11`: `**nothing**` `assembles them** … `This module is the missing composition root.`). If it is left in
place, Principle VI has two candidate entry points and the next implementer will wire the one with
`pump_one`. D4 deletes the orchestrator and keeps the four hook `Protocol`s.

**D-5 — `plan.md`'s own Complexity Tracking asserts "No constitutional violations are being
accepted" while K1–K7 stand.** `plan.md:204`: `> **Fill ONLY if Constitution Check has violations that must be justified**`
/ `No constitutional violations are being accepted.` That sentence is false as written, and it is
false in the way that matters: it is the sentence that would have surfaced K1. It must be corrected
as part of this repair, and it appears in the line-range list at the end.

**D-6 — the VI-determinism error propagates to two further sites that `phase0-results.md` does not
record.** E13/E14 cover `data-model.md` and `plan.md`. Two more:

- `tasks.md:193` cites the replay harness as `(Constitution VI)`:

  > `- [ ] T065 [P] [US8] Replay harness: the same input MUST produce the same \`signal_id\`, \`candidate_id\` and \`relation_id\` in a second process. (Constitution VI)`

- `apps/control-plane/semantic_path/assembly.py:244` and `:374` both attribute determinism to
  constitution VI in prose.

Neither `plan.md` nor `spec.md` is the only artefact carrying the error, and a repair that edits
only those two leaves the citation wrong in the place a task author's eye lands.

---

## D1 corrected Constitution Check

*Replacement for `plan.md:75-91` in its entirety. Nothing from the old table is carried forward
except its three correct verdicts, which are restated and marked `preserved`.*
*Status vocabulary: `satisfied` / `violated` / `lip service` / `not engaged`.*
*Every row cites the correct numeral. Evidence is a verbatim code quote.*

**Gate verdict: FAIL.** Seven rows are `violated`, two are `lip service`, and the `Re-check after
Phase 1 design` promise in the old table is unsatisfiable as written because the gate it re-runs
does not exist. This feature does not proceed past Phase 0 while any `violated` row is open.

### 1.1 Core Principles (all seven, verbatim names)

| # | Principle (verbatim name and text from `constitution.md`) | Status | Evidence (verbatim) |
|---|---|---|---|
| **I** | `I. Observation-Immutable Evidence Substrate` — `Every observation is immutable once recorded. Raw objects are stored content-addressable (s3://knowledge/raw/{prefix}/{sha256}) and remain available independently of any downstream projection. Nothing downstream may edit an observation.` | **satisfied** | `gate.ingest(… previous_digest=prev_digest …)` — `acquisition_loop.py:79-90` — the re-observation three-way split runs *before* the store write, and `layer0_pipeline.py:219-222` `if res.lifecycle in ("duplicate", "unchanged"): # Three-way split (R-08): fresh bytes only get interpreted/indexed.` Independently enforced by `apps/shared/tests/constitution/test_i1_i3_immutability_and_preservation.py` and `apps/control-plane/tests/test_observation_immutability.py`. **The old table had no row for I.** |
| **II** | `II. Evidence-First` — `Any knowledge must trace fully: Finding → Analytical/Topological Feature → Graph/Assertion → Evidence → Observation → Raw Object → Source. Every analytical result must be reproducible from source observations/evidence. Originals stay accessible regardless of projections.` | **violated** | `EVIDENCE_BACKWARD_CHAIN` (`evidence_lineage.py:81-89`) is `RELATION, ASSERTION, MENTION, SEGMENT, OBSERVATION, CAPTURE, SOURCE`; `DERIVATION_FORWARD_CHAIN` (`evidence_lineage.py:102-112`) is `SOURCE, CAPTURE, OBSERVATION, SEGMENT, MENTION, CANDIDATE, ASSERTION, RELATION, ENTITY`. `HopKind` (`evidence_lineage.py:50-65`) has **no `SIGNAL` member and no member for `Analytical/Topological Feature`**. `spec.md:897-898` SC-013 requires `edge → claim → candidate → signals → observations → source` — unachievable in either direction. See D-2, D-3, FR-109, ADR-0026. |
| **III** | `III. Projection-First Knowledge Architecture` — `Knowledge lives in the durable Event/Evidence Substrate (S3 + Kafka + PostgreSQL). Semantic Graph, Evidence Graph, Candidate Graph, Temporal Graph, Search Index, Analytical Store, and TDA projections are all rebuildable artifacts. Projection failure must never destroy evidence.` | **violated** | Measured by the spec itself at `spec.md:802-806`: `\| \`db/relation_claim_store.py::SqlRelationClaimStore\` \| **none** (558 lines) \| Claim persistence is unwired…`, `\| \`relation_signal\` / \`relation_candidate\` / \`source_temporal_observation\` \| **no repository, writer or reader at all** \| The three tables 020 created are written by nothing`, `\| \`projection/graph/snapshot.py::RebuildableGraphStore\` \| **none** \| There is no wired rebuild-from-store path`. The old table's own `III` row said `**GAP**`; I mark it **violated** rather than `GAP` because *no* store is written, so there is nothing to rebuild from. |
| **IV** | `IV. No Single Store / Graph / Score` — `Different workloads use different storage engines (S3 raw, Kafka events, PostgreSQL state, OpenSearch search, ClickHouse analytics, pluggable graph backend, TDA artifacts). There is no universal graph serving as source of truth, and no single score equates to truth: validity, relevance, novelty, resolution confidence, source quality, evidence support, and structural significance are stored separately.` | **lip service** | *First half holds:* `relation_store.py:353-355` — `The graph is a PROJECTION, not the source of truth (constitution III, I-4): no read path may answer a claim, context or verdict question from a graph store alone`. *Second half does not:* `dispatcher.py:74-86` fabricates the score vector and collapses it to one number — `task_spec = {"expected_gain": 0.6, "relevance": 0.7, "novelty": 0.5, "freshness": 0.5, "discovery_potential": 0.3, "source_quality": 0.7, …}` then `score = self._scorer.score(task_spec, {"downstream_lag_s": 0.0})`, and `dispatcher.py:109` publishes `utility=score.utility` as the sole result field. `relevance` and `source_quality` are **hardcoded constants, not measurements**, so they are not "stored separately" in any meaningful sense. The *correct* treatment already exists at `query_planner.py:14-15`, and `dispatcher.py` is the counter-example. |
| **V-a** | `V. Plugability by Contract` — *acquisition half:* `All acquisition implementations conform to the AcquisitionWorker interface (capabilities() / estimate(task) / acquire(task)).` | **satisfied** | `source_registry.py:4` — `capabilities()/estimate()/acquire() (Constitution V, AcquisitionWorker contract);` and `source_registry.py:145` — `f"connector '{name}' must satisfy AcquisitionWorker "` — the gate is enforced, not asserted. `api/routes/connectors.py:36-45` is a conforming implementation. Split into V-a and V-b because the two halves have different verdicts. |
| **V-b** | `V. Plugability by Contract` — *graph half:* `Application code interacts with graphs only through GraphProjection / GraphReader / GraphSnapshot / GraphTraversal. No vendor-specific classes in domain logic.` **Engines** … `and graph backends (Neo4j/Memgraph/other) are swappable behind contracts.` | **lip service** | The contract exists but under a different name and with two of the four roles unnamed. `abstraction.py:154-167` is a single `class GraphStore(Protocol):` with `write_node` / `write_edge` / `write_hyperedge` / `neighbors` / `node`; there is **no** `GraphReader`, **no** `GraphProjection`, and **no** `GraphTraversal` class anywhere in the repository. Only `snapshot.py:36 class GraphSnapshot:` matches. Worse, the *backend* that would demonstrate swappability is inert: `spec.md:805` — `\| \`projection/graph/neo4j.py::Neo4jGraphStore\` \| **none**; and the module never imports \`neo4j\` |` — and `neo4j>=5.21` is declared in `control-plane` while `projection`, which would need it, does not. Swappability is asserted by a Protocol and never exercised. ADR-0008/0009 exist and neither records that two of the four named roles were never built. |
| **VI** | `VI. Process-Centric` — `The user creates an Investigation — not a graph. Graphs, search indices, analytical structures, and TDA complexes materialize automatically within the investigation lifecycle and its policy/budget/freshness constraints.` | **violated** | `entity_pipeline.py:38` — `async def run_live_entity_pipeline(*, tenant_id: str, entity_id: str, identity: dict[str, Any], source_records: list[dict[str, Any]], catalog: Catalog, operations: Any) -> None:` — **no `investigation_id` parameter**, on the live user-reachable path. `layer0_pipeline.py:296-303` — `investigation_id: str = ""`, i.e. optional on the other candidate entry point. `worker.py:20-27` registers no investigation workflow. `input.md` contains no occurrence of `investigation`. The old table's `VI determinism` row did not check this at all. |
| **VII** | `VII. Security-First` — `All external input is untrusted. Mandatory: SSRF protection, DNS-rebinding protection, sandboxed parsers, browser isolation, network egress policy, CPU/memory/timeout/size limits, archive-depth and file-count limits, tenant isolation at every level, RBAC, audit logs, secret isolation. Tool constraint …` | **violated** | Four distinct failures, each quoted. **(a) No egress policy on the fetch path:** `acquisition_loop.py:51-53` — `self._client = client or httpx.AsyncClient(timeout=10.0, follow_redirects=True, headers={"User-Agent": "cognitive-acquisition/0.1"})` and `acquisition_loop.py:63` — `resp = await self._client.get(item.uri)`. `follow_redirects=True` on an untrusted URL with no allowlist, no DNS-rebinding check, no egress policy. **(b) The audit log is a process-lifetime list:** `audit.py:40-41` — `self._events: list[AuditEvent] = []` / `if self._pg_copy is not None: self._pg_copy(event)` — and `audit.py` has **one** importer repo-wide, a test (`apps/control-plane/tests/unit/test_us3_ops.py:8`). The real table `db/schema.py:596 class AuditLog(Base):` has no writer. **(c) Tenancy is one tenant deep:** `policy_service.py:22-28` hard-codes `tenant_id="default-tenant"` on both the `Policy` and the `Budget`, and `PolicyEngine.check` (`cp_domain/policy.py:84-108`) never compares a request's tenant to the policy's tenant. **(d) The two enforced VII items are cited to the wrong numeral** at 20 sites (F4). |

### 1.2 Domain Invariants (all twelve, verbatim)

| # | Invariant (verbatim) | Status | Evidence (verbatim) |
|---|---|---|---|
| **INV-1** | `Observation is immutable.` | **satisfied** | `apps/shared/tests/constitution/test_i1_i3_immutability_and_preservation.py`; `layer0_pipeline.py:219-222` re-observation split. |
| **INV-2** | `Mention != Candidate != Entity.` | **violated** | `spec.md:70` — `\| \`metadata.py\` uses a *property name* as the signal subject (\`attribute:<key>\`, \`jsonld:<key>\`), and falls back to the literal \`document:current\` when \`document_ref\` is empty` — and `spec.md:45` `Producers address synthetic \`*_mention_ref\` values (\`surface:role:john smith\`, \`document:current\`, \`meta:author:…\`)`. The old table's `I-2` verdict was `**PASS with work**`; I **downgrade it to violated**. A `document:current` fallback collapses every document in a batch onto one participant ref, and that is the invariant failing, not "work remaining". |
| **INV-3** | `Assertion != truth.` | **satisfied** *(preserved from the old `I-3` row)* | `plan.md:82` — `**PASS** — \`PredicateResolutionState.UNKNOWN\` exists and is retained; \`material_requires_resolved_predicate\` is the correct CD-6 line`. UNKNOWN is a retained state, never a drop. |
| **INV-4** | `Graph != source of truth.` | **satisfied** *(preserved from the old `I-4` row)* | `relation_store.py:362` — `def to_node(self, claim: RelationClaim, ref: str = "") -> GraphNode:` — typed on a claim with no overload, so a candidate or signal cannot be projected even by mistake. |
| **INV-5** | `Kafka != object store.` | **not engaged** | No defect found; no 021 requirement touches it. `event_bus.py:8` — `as \`\`events.kafka.IdempotentProducer\`\` and the shared \`\`Producer\`\` protocols —`. |
| **INV-6** | `TDA != truth oracle (topological features are structural signals, not proof of identity).` | **not engaged** | 021 adds no TDA surface; `apps/science/` is untouched by this feature's requirement set. |
| **INV-7** | `Admission != Priority.` | **satisfied** | `admission.py:69-72` — `policy_version: str = "UNCALIBRATED-v1"` … `replayable: bool = True  # FR-013: rejected kept replayable`. The decision and the queue position are separate fields on `AdmissionResult`. |
| **INV-8** | `Entity novelty != evidence novelty != structural novelty.` | **not engaged** | Not asserted in 021's requirement set and not asserted in the code either. Recorded as `not engaged` rather than `satisfied`: nothing enforces it. |
| **INV-9** | `Search != Graph traversal != OLAP.` | **satisfied** | `query_planner.py:12-14` — `a backend failure **degrades** a query, it never ends it -- a sick backend costs the caller the healthy backends' results unless the total outage is raised explicitly (:class:\`AllBackendsFailed\`), because \`[]\` means "no matches" (Constitution Invariant 9)`. |
| **INV-10** | `Acquisition throughput != intelligence throughput.` | **not engaged** | No 021 requirement measures either quantity. `tasks.md:195`'s boundedness report measures `pairs considered`, not throughput. |
| **INV-11** | `The fastest request is the request correctly avoided.` | **satisfied** | `dispatcher.py:104-106` — `if decision.value == "DENY": self._frontier.cooldown(item.frontier_id, time.time() + 60.0)` — a refusal becomes a cooldown, not a retry. |
| **INV-12** | `All downstream projections must be rebuildable from durable evidence/events.` | **violated** | Same evidence as Principle III — the honest reading. The old table's `III` row is the row that should have carried this and did not, because it cited the *principle* and not the *invariant*. Concretely: `spec.md:803` — `\| \`relation_signal\` / \`relation_candidate\` / \`source_temporal_observation\` \| **no repository, writer or reader at all** \| The three tables 020 created are written by nothing`. Rebuildability is not merely unproven; the substrate it would rebuild from is unwritten. FR-097 and `relation_signal_store.py` are the whole remedy; there is no second one. |

### 1.3 Technology Baseline (all fifteen clauses)

| Baseline clause (verbatim) | Status | Evidence (verbatim) |
|---|---|---|
| `Frontend: React + TypeScript` | **not engaged** | `apps/webapp/` is out of scope (`plan.md:184`). |
| `API: FastAPI / Python` | **satisfied** | `plan.md:38-39` — `\`fastapi>=0.111\`, \`uvicorn[standard]>=0.30\``; 24 route modules, ~122 routes (`plan.md:169`). |
| `High-throughput components: Rust` | **not engaged** | No Rust source under `apps/`. Unmet rather than violated; 021 adds none. |
| `Workflow: Temporal` | **violated** | `temporalio>=1.4` is declared (`plan.md:39`) and one workflow is registered (`worker.py:20-27`), but the constitution-named `InvestigationWorkflow` is not, and the two activities it calls do not exist (F9). A baseline technology is present and its central workflow surface is dead. |
| `Event backbone: Apache Kafka (KRaft), Protobuf, Schema Registry` | **satisfied** | `docker-compose.yml:38` `kafka:`, `:66` `schema-registry:`; `events/kafka.py::build_envelope` used at `dispatcher.py:113-122`. |
| `Raw storage: S3-compatible object storage (MinIO for dev/self-hosted)` | **satisfied** | `docker-compose.yml:9` `minio:`, `:24` `minio-init:`; `gate.ingest(…)` at `acquisition_loop.py:79-90` returns `obs["raw_ref"]`. |
| `Operational state: PostgreSQL` | **satisfied** | `docker-compose.yml:81` `postgres:`; `db/session.py::create_tables, make_session_factory` used at `temporal_materialization.py:124-125`. |
| `Search: OpenSearch projection` | **satisfied** | `docker-compose.yml:106` `opensearch:`; `search_backends.py:302 class SearchProjectionStore:`, `:498 class SearchIndexBackendClient(_AuditedClient):`. |
| `Analytical storage: ClickHouse projection` | **satisfied** | `docker-compose.yml:123` `clickhouse:`; `clickhouse-connect>=0.7` (`plan.md:40`). |
| `Stateful stream processing: Apache Flink (only for genuine stateful work, not transport)` | **not engaged** | `docker-compose.yml:201` `flink-jobmanager:`, `:212` `flink-taskmanager:` are provisioned. A repo-wide `flink` search matches only `README.md`, `docs/`, and `docs/adr/0006-flink-role.md` — **no application code**. Provisioned-and-unused is the correct reading: the clause's own test is that it is not used for transport, and it is not used at all. |
| `Graph serving: replaceable abstraction layer` | **satisfied** | `abstraction.py:154-167 class GraphStore(Protocol):` with `InMemoryGraphStore` (`:170`), `Neo4jGraphStore`, `RebuildableGraphStore`. This is the Technology Baseline clause the *no vendor-specific classes* half of V-b rests on. |
| `TDA: Python (GUDHI, giotto-tda, NumPy, SciPy)` | **not engaged** | `apps/science/` untouched by 021. |
| `Runtime: Docker, Kubernetes` | **satisfied** (Docker) / **not engaged** (Kubernetes) | `apps/deploy/docker-compose.yml`; no k8s manifest under `apps/`. |
| `Observability: OpenTelemetry, Prometheus, Grafana` | **not engaged** | Not present in `apps/`. 021 adds no instrumentation — which is itself worth an ADR note, since FR-084 requires honest reporting of production reachability and there is no production telemetry to report from. |
| `Secrets: Vault` | **not engaged** | Not present in `apps/`; a root `.env.example` exists. |

### 1.4 Additional Constraints (all seven, verbatim)

| Constraint (verbatim) | Status | Evidence (verbatim) |
|---|---|---|
| `**No MVP/mini-architecture**: implement contracts of all major planes (Investigation, Acquisition, Evidence, Interpretation, Admission, Projection, Analysis, Feedback) up front; components may be introduced incrementally but must never break final domain/event contracts.` | **violated** | The **Investigation** plane is the one plane in that list with no contract. `worker.py:20-27` registers `TemporalEntityMaterializationWorkflow` only; `InvestigationWorkflow` is unregistered (F9). The clause says "contracts of all major planes … up front", and the investigation contract is the one this repair adds (D3). |
| `**Script type**: PowerShell (ps) for Speckit automation on Windows.` | **not engaged** | No Speckit automation scripts in this feature's deliverable set. |
| `**Backpressure**: downstream queue growth must reduce acquisition rate, not expand Kafka backlog.` | **lip service** | The mechanism exists — `dispatcher.py:125-130` `def pump(self, *, tenant_id: str | None = None, iterations: int = 10, delay_s: float = 0.1)` and `HeuristicUtilityScorer.score`'s `context` parameter — but the only caller passes a **hardcoded** lag: `dispatcher.py:86` `score = self._scorer.score(task_spec, {"downstream_lag_s": 0.0})`. `downstream_lag_s` is a literal `0.0`, so backpressure is structurally present and permanently switched off. |
| `**Retry budgets**: task / source / investigation / global retry budgets to avoid retry storms.` | **violated** | `cp_domain/policy.py:31-41` declares one `Budget` keyed `budget_id="budget/default"` with per-`worker_class` limits. There is **no** task, source, investigation or global tier — `policy_service.py:53` `def commit_usage(self, budget_id: str, worker_class: str, units: float) -> None:` takes a worker class and nothing else. One tier is not four. The new `acquire` activity's idempotency key is `task_id` (D3.4), and no investigation-scoped budget exists to bound its retries. |
| `**Dead letter / quarantine** for malformed data, repeated parser failures, policy uncertainty, resource abuse, unsupported formats; rejected candidates are never auto-deleted (replay/re-evaluation supported).` | **violated** | Quarantine and replay exist and are correct: `dlq.py:41-49` `class QuarantineStore:` / `"""Preserves rejected candidates for replay/re-evaluation."""` / `"""sink: optional durable copy (e.g., MinIO prefix) — production adapter."""`; `dlq.py:69-74` `def replay(self, record_id: str) -> bytes | None:` … `# Replay hands the preserved payload back to the pipeline unchanged.` **But `dlq.py:76-80` is an auto-delete:**<br>`    def purge(self, record_id: str) -> bool:`<br>`        record = self._records.pop(record_id, None)`<br>`        if record is not None:`<br>`            self._by_fingerprint.pop(record.fingerprint(), None)`<br>`        return record is not None`<br>— and it is reachable from a production route: `api/routes/quarantine.py:63-64`<br>`    mark = "rejected" if "malformed" in record.reason else "accepted"`<br>`    _store.purge(record_id)`<br>`POST /dlq/{record_id}/re-evaluate` **deletes the rejected candidate as a side effect of re-evaluating it.** The constitution says `rejected candidates are never auto-deleted`; the route's re-evaluation is exactly an auto-delete. FR-110 closes it. |
| `**Idempotency**: every consumer is idempotent using event_id / task_id / observation_id / projection offsets.` | **violated** | No consumer in the 021 path declares a key. `temporal_materialization.py:24-25` `async def reconcile_and_publish(tenant_id: str, entity_id: str, source_record_ids: list[str], run_id: str, entity_identity: dict[str, str]) -> dict[str, Any]:` — `run_id` is a *label*, and the body's only durability guard is `temporal_materialization.py:38-39` `if source_record_ids: raise RuntimeError("source record resolution requires the durable entity_stream repository")`. `TemporalEntityMaterializationWorkflow.run` (`temporal_materialization.py:152-157`) passes `RetryPolicy(maximum_attempts=3)` and no idempotency key, so Temporal's own retry is a double-write. The two real idempotency implementations in the repo are `dlq.py:50-57` `def quarantine(self, record: DLQRecord) -> str:` / `# Idempotent preserve (I-11): dedupe by payload fingerprint` and the re-observation digest split — neither is in the 021 path. FR-105 specifies keys for every stage. |
| `**HTTP-first acquisition**, browser escalation only on insufficiency; separate browser fabric pool; resource classes priced by expected_value / estimated_cost.` | **lip service** | HTTP-first holds on the one live fetch path (`acquisition_loop.py:89` `collector="worker-http"`). Browser escalation and the separate pool are declared in `docker-compose.yml:231` `browsertrix:` and nowhere in code. Resource classes are priced by a fabricated vector (`dispatcher.py:74-85`), so `expected_value` is the constant `0.6` for every task in the repository. |

### 1.5 Governance (all three clauses)

| Clause (verbatim) | Status | Evidence (verbatim) |
|---|---|---|
| `Constitution supersedes all other practices.` | **violated** | `plan.md:5-8` — `The unabridged user brief is \`input.md\` in this directory and governs over this document wherever the two appear to differ.` `spec.md:18-19` — `this document appears to compress or interpret something, \`input.md\` governs`. Both invert it. The old gate row marked this `**PASS**` on a worked example where the two agree (F6). Replacement text in D2. |
| `Changes to architectural decisions require an ADR (e.g., Kafka vs alternatives, object storage, PostgreSQL role, OpenSearch, ClickHouse, Flink, Temporal, graph abstraction/backend, TDA architecture, event schema, provenance, entity resolution, admission engine, frontier architecture, scheduling, recrawl, multi-region topology).` | **violated** | Four architectural changes are in flight with no ADR. **(a) `Temporal`**: adding the constitution-named investigation workflow is a `Temporal` decision and `docs/adr/0007-temporal.md` already exists and predates it. **(b) `recrawl`**: `InvestigationWorkflow`/`RecrawlWorkflow` implement recrawl scheduling and `docs/adr/0017-recrawl-strategy.md` exists; the code being deleted (`investigation.py:277-291`) and the code being added (D3) must both be reconciled against it. **(c) `entity resolution`**: `phase0-results.md:150` (E1) records the N5 `owns ≡ controls` synonym table as entity-resolution-grade, and `phase0-results.md:174` (K5) records it has no ADR and no slot in `FR-083`'s A–K list. **(d) `provenance`**: the Evidence-First chain repair (D-2/D-3) is a `provenance` decision and `docs/adr/0012-provenance.md` exists. D5 and FR-107 close all four. |
| `Compliance is verified on every PR/review.` | **violated** | `Test-Path .github` → `False`. `plan.md:54-55` — `There is **no CI** (\`.github/\` does not exist), no Makefile, no tox/nox, and no test-runner script — the gate is run by hand.` A 74-task change to a constitutional layer is gated by a person remembering to run `uv run --project apps/<app> pytest apps/<app>/tests -q` (`docs/CONTRIBUTING.md:37`). `plan.md:204`'s `No constitutional violations are being accepted.` is therefore unfalsifiable in practice. FR-108 closes it, and I recommend CI over a documented manual gate. |

### 1.6 Verdict roll-up

| Section | Counts | Failing rows |
|---|---|---|
| Core Principles I–VII | 1 satisfied, 2 lip service, 4 violated | II, III, VI, VII |
| Domain Invariants 1–12 | 5 satisfied, 5 not engaged, 2 violated | INV-2, INV-12 |
| Technology Baseline (15) | 9 satisfied, 5 not engaged, 1 violated | Temporal |
| Additional Constraints (7) | 1 satisfied, 2 lip service, 4 violated | No MVP/mini-architecture, Retry budgets, Dead letter/quarantine, Idempotency |
| Governance (3) | 0 satisfied, 3 violated | all three |

---

## D2 supersession rule (verbatim replacement text)

### 2.1 Why the current text is not merely imprecise

It is not a wording problem. `plan.md` and `spec.md` both grant a *higher* authority to `input.md`
than the constitution grants to itself, and `spec.md` does it in a blockquote at the top of the
document where it functions as a rule of interpretation for the whole spec. A rule of
interpretation that reverses `Constitution supersedes all other practices` is not interpretation; it
is a competing constitution. And it is *unnecessary*: brief and constitution agree far more often
than they disagree, so the clause buys almost nothing while costing the one thing the constitution
insists on.

Two properties the replacement must have, and the old text has neither:

1. **It must name the winner.** "Governs over this document" names a loser. The replacement names
   an ordered list of three.
2. **It must be operational on conflict, not decorative.** It must say what happens to a conflict:
   the constitution wins, and the conflict is *recorded* as an ADR. A rule that only reverses the
   order produces a corrected document and a lost record of why.

### 2.2 Replacement text for `plan.md` (replaces lines 5–8)

```markdown
**Input**: Feature specification from `specs/021-entity-relation-extraction-finalization/spec.md`
(102 functional requirements, 5 constitutional invariants, 16 measurable outcomes, 9 user
stories). The unabridged user brief is `input.md` in this directory (4898 lines, §0–§114).

**Authority order — the constitution wins.** `.specify/memory/constitution.md` v1.0.0 states
verbatim: *"Constitution supersedes all other practices."* The order of authority for this feature
is therefore, highest first:

1. `.specify/memory/constitution.md` — the 7 Core Principles, the 12 Domain Invariants, the
   Technology Baseline, the Additional Constraints, and Governance.
2. `input.md` — the user's brief, authoritative wherever the constitution is **silent**.
3. `spec.md` / `plan.md` / `data-model.md` / `tasks.md` / `research.md` — this feature's artefacts,
   authoritative only where 1 and 2 are both silent.

**Operational rule.** Where `input.md` and the constitution conflict, the constitution wins, this
feature implements the constitution, and the conflict is recorded in `docs/adr/` with a worked
example naming the clause on each side. Where `input.md` fills a silence in the constitution,
`input.md` governs. Where this feature's own artefacts conflict with either, the artefact is wrong
and is corrected. **An artefact MUST NOT state a rule of interpretation that reverses this order**,
and the Constitution Check gate MUST be evaluated on at least one case where the constitution and
`input.md` **disagree** — a gate evaluated only on cases of agreement cannot detect an inversion.
```

### 2.3 Replacement text for `spec.md` (replaces the blockquote at lines 16–20)

```markdown
> **The complete, unabridged user brief is `input.md` in this directory (4898 lines, §0–§114,
> reproduced verbatim).** This document is the engineering reading of it.
>
> **Where this document and the constitution disagree, the constitution wins.**
> `.specify/memory/constitution.md` v1.0.0 states: *"Constitution supersedes all other
> practices."* Concretely, for this document:
>
> - `input.md` is authoritative wherever the constitution is **silent** — including §0 (working
>   mode), §45 (no majority vote), §51–56 (projection is a projection), §72–75 (structural
>   prohibitions) and §110 (development order).
> - The constitution is authoritative wherever `input.md` is **silent or in tension** — most
>   consequentially `VI. Process-Centric` and the `No MVP/mini-architecture` constraint, both of
>   which name an `Investigation` plane that `input.md` never mentions.
> - Where both are silent, this document decides, and says so.
>
> Two worked examples, one of agreement and one of disagreement, are in
> `repair/A1-constitution-investigation.md` §D2.4. The disagreement case is not optional
> reading: `input.md` specifies a pipeline with no owner, and the constitution requires one.
```

Note that the `(3411 lines, all 115 sections` figure in the old text is also wrong —
`phase0-results.md:139` (D10) measured `input.md` at **4898 lines** — so the count is corrected in
the same edit rather than left standing inside a sentence whose authority is being reversed.

### 2.4 Two worked examples — one where they agree, one where they **disagree**

**Example A — agreement (retired as the gate's only evidence).** `input.md` §20, verbatim
(`input.md:1288-1304`):

> `# 20. DO NOT FORCE SEMANTIC EQUIVALENCE WHERE IT IS UNKNOWN`
> …
> `Do not do:`
> ```text
> owns
> controls
> manages
> ```
> `→ same relation`
> `just because they sound similar.`
> `Only unify when deterministic normalization or explicit semantic mapping establishes that configuration.`

Constitution INV-3, verbatim: `Assertion != truth.` Both forbid the same move, from opposite
directions — the brief forbids it at the *predicate*, the constitution at the *assertion*. The
brief's `Only unify when deterministic normalization or explicit semantic mapping establishes that
configuration` is the same operation the constitution's INV-3 permits, so the two compose rather
than compete. **This example is kept, and it is the only reason the old gate row's *conclusion*
was true. It is not evidence about the clause, because a rule cannot be tested on the one input
where both operands already agree.**

**Example B — genuine disagreement, and the constitution wins.** `input.md` contains no
investigation: a search for `investigation` across all 4898 lines returns no occurrence. The brief's
complete architecture statement is a five-stage chain, reproduced at `spec.md:22-27`:

> `> **what was observed** → \`Observation\`/\`Mention\`/\`RelationSignal\`; **what could it be** →`
> `> \`TypeHypothesis\`/\`PredicateHypothesis\`/\`RelationCandidate\`; **what our regime calls it** →`
> `> \`TypeAssertion\`/\`RelationRef\`/mapping; **what survived validation and admission** →`
> `> \`RelationClaim\`; **what graph view do we project** → \`GraphEdge\`/\`HyperEdge\`.`

Five stages, named, in order, with no statement about **who starts it, what bounds it, when it
stops, or what a user creates.** The plan's reading — "the user creates an entity, and the
pipeline runs" — is not in the brief; it is in the code, and the plan imported it.

Constitution VI, verbatim:

> `The user creates an Investigation — not a graph. Graphs, search indices, analytical structures, and TDA complexes materialize automatically within the investigation lifecycle and its policy/budget/freshness constraints.`

This is not a silence the plan may fill. Principle VI asserts a *subject* — the thing a user
creates — and the brief asserts a different subject, or none. The plan currently implements the
brief's silence against the constitution's assertion, and it does so by nominating
`entity_pipeline.py::run_live_entity_pipeline` as the seam, a function whose signature
(`entity_pipeline.py:38`) has no investigation in it at all. Under the corrected authority order
the resolution is forced: **the Investigation becomes the production entry point, the brief's
five-stage chain becomes the workflow's stage sequence inside it, and the entity pipeline becomes a
caller of the workflow rather than its owner.** That is D3, and it is the substance of FR-101.

Two further disagreements fall out of the same clause and are recorded here so they are not
rediscovered:

- **`No MVP/mini-architecture`** names eight planes; `input.md`'s chain names five. The three the
  brief omits — Investigation, Acquisition, Feedback — are constitutional, not optional. FR-101
  supplies Investigation; Acquisition is `acquisition_loop.py`'s job and is subject to D4; Feedback
  is untouched by 021 and is recorded as an open constitutional debt, not a 021 defect.
- **`Rejected analysis outputs … are preserved with decision, reasons, score vectors, versions, and
  timestamps for replay`** (`constitution.md:73`) versus `api/routes/quarantine.py:63-64`, which
  purges the record during re-evaluation. The brief does not address preservation at all, so this
  is a constitution-only requirement and `quarantine.py` loses. FR-110.

---

## D3 InvestigationWorkflow contract

### 3.1 What this is, and what it is deliberately not

It is a **new, minimal, registered** workflow. It is not a resurrection of
`workflows/investigation.py`. Concretely, the new workflow:

- **does not** carry an approval gate (`AWAITING_APPROVAL` / `APPROVED` / `REJECTED` are dropped —
  no FR in 021 requires human approval, and an unexercised gate is a second dead workflow);
- **does not** carry a `RecrawlWorkflow` (recrawl is `docs/adr/0017-recrawl-strategy.md`'s subject
  and is out of 021's scope; see D4 and ADR-0025's `Consequences`);
- **does not** define its own lifecycle enum. It reuses `cp_domain.investigation.InvestigationState`,
  which already exists, already claims the principle, and already validates budget and scope;
- **does not** re-fetch, re-parse or re-decide anything. Every stage is a thin, typed activity call.

The two lifecycles are currently a genuine duplication, and that is the deeper reason the old file
must go rather than be kept as reference. `cp_domain/investigation.py:42-59` declares
`class InvestigationState(enum.StrEnum):` with, at `cp_domain/investigation.py:143-154`:

```python
_TRANSITIONS: dict[InvestigationState, set[InvestigationState]] = {
    InvestigationState.DRAFT: {InvestigationState.PLANNING, InvestigationState.ARCHIVED},
    InvestigationState.PLANNING: {InvestigationState.RUNNING, InvestigationState.DRAFT},
    InvestigationState.RUNNING: {InvestigationState.PAUSED, InvestigationState.COMPLETED},
    InvestigationState.PAUSED: {
        InvestigationState.RUNNING,
        InvestigationState.COMPLETED,
        InvestigationState.ARCHIVED,
    },
    InvestigationState.COMPLETED: {InvestigationState.ARCHIVED},
    InvestigationState.ARCHIVED: set(),
}
```

`workflows/investigation.py:57-66` declares a *second*, conflicting one — `CREATED / QUEUED /
ACQUIRING / AWAITING_APPROVAL / APPROVED / REJECTED / RECRAWL / COMPLETED / PAUSED` — with a
different transition table, a different terminal set, and `PAUSED → QUEUED` where `cp_domain` has
`PAUSED → RUNNING`. Two answers to one question is not a reference implementation; it is a fork
with no arbiter. `cp_domain`'s wins because it is the one that (a) already carries
`I-6 Process-Centric` in its own module docstring (`cp_domain/investigation.py:1`), (b) owns
`InvestigationMonitor` (`:94`) with the "persist once at close" invariant, and (c) is the one
`investigation.py:37` already imports from.

### 3.2 Identity and registration

| Field | Value |
|---|---|
| **Workflow name** | `InvestigationWorkflow` (class); Temporal type name `investigation.lifecycle` via `@workflow.defn(name="investigation.lifecycle")` |
| **Module** | `apps/control-plane/workflows/investigation_lifecycle.py` — a **new** file. It does not replace `workflows/investigation.py` in place; that file is deleted (D4), so the module name cannot be reused. |
| **Task queue** | `TASK_QUEUE = "cognitive-investigations"` — the same queue the dead file declared (`investigation.py:39`), because the queue name is already the event catalog's name for this plane and reusing it costs nothing. |
| **Registration** | `apps/control-plane/workflows/worker.py` adds `InvestigationWorkflow` to `workflows=[…]` and every activity to `activities=[…]`. Registration is **test-enforced**: a test imports `worker.py`'s registry and asserts membership. This is the direct answer to the `No MVP/mini-architecture` violation, and to the fact that "it exists" has been claimed four times in this repository and been true zero times. |
| **Activities** | Eight `@activity.defn`s, all declared on the worker. **Zero** string-only `workflow.execute_activity` calls. The dead file's `"acquisition.acquire_batch"` and `"acquisition.recrawl"` are gone and are not replaced by strings. |
| **Determinism** | No I/O in the workflow body. All network, store and clock access is in activities. `workflow.now()` and `workflow.info().workflow_id` are the only permitted workflow-context reads. |

### 3.3 Stages, activities, and types

The stage sequence is the brief's five-stage chain (`spec.md:22-27`) made executable, wrapped in
acquire and validate.

| # | Stage | Activity name | Input | Output |
|---|---|---|---|---|
| 1 | acquire | `investigation.acquire` | `AcquireInput(tenant_id, investigation_id, seeds: tuple[str, …], policy_id, budget_id, freshness_seconds, max_captures, task_id)` | `AcquireOutput(observation_ids: tuple[str, …], rejected: tuple[RejectedItem, …], degraded: bool)` |
| 2 | interpret — mention binding | `investigation.bind_mentions` | `BindMentionsInput(tenant_id, investigation_id, observation_ids, mention_index_revision)` | `BindMentionsOutput(mention_index_revision, bound: int, unbound: int)` |
| 3 | interpret — type signals | `investigation.extract_type_signals` | `TypeSignalInput(tenant_id, investigation_id, observation_ids, mention_index_revision)` | `TypeSignalOutput(type_signal_ids, type_hypothesis_ids)` |
| 4 | interpret — relation signals | `investigation.extract_relation_signals` | `RelationSignalInput(tenant_id, investigation_id, observation_ids, mention_index_revision, producer_refs)` | `RelationSignalOutput(relation_signal_ids)` |
| 5 | interpret — candidate assembly | `investigation.assemble_candidates` | `AssembleInput(tenant_id, investigation_id, relation_signal_ids, type_hypothesis_ids)` | `AssembleOutput(candidate_ids, conflicted, unknown_retained)` |
| 6 | validate | `investigation.validate_candidates` | `ValidateInput(tenant_id, investigation_id, candidate_ids)` | `ValidateOutput(claim_material_ids, rejected_ids: tuple[str, …], reasons)` |
| 7 | admit | `investigation.admit_claims` | `AdmitInput(tenant_id, investigation_id, claim_material_ids)` | `AdmitOutput(decision_ids, decision_by_candidate, quarantined_ids, preserved_rejections)` |
| 8 | project | `investigation.project` | `ProjectInput(tenant_id, investigation_id, decision_ids, projection_offset)` | `ProjectOutput(projected_edge_ids, projected_hyperedge_ids, projection_offset, skipped)` |

Stage 2 is not folded into stage 4: `plan.md:21` requires mention binding to be a distinct layer
(`Mention binding moves to a pre-resolution mention index so producers cite real \`MN-…\` ids`), and
folding it would re-create the exact defect where a producer fabricates its own mention refs.
"Minimal" here means minimal *logic*, not a merged stage list that hides a required seam.

`RejectedItem` is a first-class type, not a `str`: it carries `(kind, reason_code, ref,
preserved_at, score_vector, policy_version)`, because the constitution requires rejections to be
preserved *"with decision, reasons, score vectors, versions, and timestamps for replay"*
(`constitution.md:73`) and a bare id cannot hold a score vector.

### 3.4 Idempotency keys

The constitution's clause, verbatim (`constitution.md:66`): `every consumer is idempotent using
event_id / task_id / observation_id / projection offsets.`

| Consumer | Key | Where enforced | Behaviour on replay |
|---|---|---|---|
| `investigation.acquire` | `task_id`, content-addressed over `(investigation_id, sorted(seeds), policy_id, freshness_seconds)` | First argument of the activity; written to the activity's idempotency table **before** the fetch | A completed `task_id` returns the stored `AcquireOutput` and issues **no** network call. A *partial* one resumes from the observation gate's digest, not from a refetch. |
| `investigation.bind_mentions` | `observation_id` | The mention index keys on `(tenant_id, capture_ref, kind, value, start_offset, end_offset, extractor_ref)` — **including `capture`**, which `tasks.md` T019 omits (`phase0-results.md:160`, E11) | Re-binding an already-bound occurrence returns the existing `MENTION-…` id. Two captures of one segment therefore produce two mentions, not one. |
| `investigation.extract_type_signals` | `event_id` | `RelationSignal._material()` already includes `producer_ref`, so a producer re-run over the same record derives the same `signal_id`; the check is that the *store write* is keyed on it | Upsert on `signal_id`. Never an append. |
| `investigation.extract_relation_signals` | `event_id` + `task_id` | Same `signal_id` derivation. `task_id` distinguishes two acquisitions of the same bytes at different times, which must be two observations, not one | Upsert on `signal_id`. |
| `investigation.assemble_candidates` | derived `candidate_id` | `assemble()` is already order-independent (`assembly.py:253` `ordered = tuple(sorted(signals, key=lambda s: s.signal_id))`) — but *only* because that sort exists. FR must make `__post_init__` sort `signal_refs` (`relation_candidate.py:826-836` normalises `supporting_spans`, `observation_refs` and `evidence_refs` and **not** `signal_refs`, which is in the identity material at `relation_candidate.py:539`), so the key no longer depends on a call site | Upsert on `candidate_id`. Two orderings MUST give one `candidate_id`. |
| `investigation.validate_candidates` | derived `relation_id` | `relation_claim_material.py:54` re-derives on `build()` | Upsert on `relation_id`. |
| `investigation.admit_claims` | derived `admission_id` | `AdmissionResult.admission_id` is **not** content-addressed — `admission.py:69` `admission_id: str = field(default_factory=lambda: "AD-" + uuid.uuid4().hex[:12])`. It MUST be replaced by a digest of `(candidate_id, policy_version, reason_codes, score_vector)`, or admission is not idempotent and a Temporal retry double-admits | Upsert on the derived `admission_id`. |
| `investigation.project` | `projection_offset` | A monotonic per-`(tenant_id, investigation_id)` watermark in `ProjectInput`. `GraphProjectionBridge` is one-way by construction (`relation_store.py:351` `"""Map a stored claim onto the existing graph types (one way, no back-flow).`) so re-projection cannot back-flow a rejection into the graph | Skip any `relation_id` at or below `projection_offset`; write the new watermark on success only. |

Two of these are **new** and are the substance of FR-105: a content-addressed `admission_id`, and a
`projection_offset` watermark. The other six have an existing derivation to lean on.

### 3.5 How it subsumes rather than duplicates `reconcile_and_publish`

`reconcile_and_publish` is **not** deleted and **not** reimplemented. It becomes the `acquire`
activity's *WARC-pull implementation* for the Common Crawl source class, and nothing more.

| `reconcile_and_publish` today | After |
|---|---|
| `@activity.defn(name="temporal_materialization.reconcile_and_publish")`, args `[tenant_id, entity_id, source_record_ids, run_id, entity_identity]` (`temporal_materialization.py:24-25`, `:154`) | Kept as a **library function**, called by `investigation.acquire`'s Common Crawl path. No longer registered as a workflow activity in its own right. |
| Discovers partitions, pulls WARC ranges, and **builds `StreamRecord`s inline** at `temporal_materialization.py:64-70`, `:81-86`, `:97-102` and `:114-119` | Those four near-duplicate `StreamRecord(...)` literals are collapsed into one helper and reused. The duplication is itself a defect the brief did not name: four copies of the same 6-field record, each with `admission: {"decision": "ACCEPT_NEW", "status": "ACCEPTED", "confidence": 0.91, "policy": "cc-capture-v1"}` hard-coded — a single score, hard-coded, standing in for an admission decision, which is a Principle IV problem in the one place Principle IV is most concrete. |
| Calls `materialize_history(records, …)` and `from_entity_stream(records, …)` and returns `{"run_id", "entity_id", "publication", "records", "invariant", "durable_sql", "status"}` (`temporal_materialization.py:120-142`) | Both calls are **interpretation** and move to stages 5 and 8. `reconcile_and_publish` returns observations only. |
| `TASK_QUEUE = "cognitive-temporal-materialization"`, run by `TemporalEntityMaterializationWorkflow` (`temporal_materialization.py:11`, `:145-159`) | The queue stays and the workflow stays registered, because historical reconstruction is `docs/adr/0019-reconstruction-frontier.md`'s subject and is out of 021's scope. What changes is that it no longer *owns* interpretation. |
| Not called by `entity_pipeline.py`; `entity_pipeline.py:19` imports `temporal_materialization_service`, and `entity_pipeline.py:45-74` duplicates `reconcile_and_publish`'s Common Crawl discovery while `:75-80` calls `interpret_warc_capture` **directly** | That duplication is deleted. `entity_pipeline.py` becomes a thin client that starts an `InvestigationWorkflow` and returns a run id. This is the concrete form of FR-101. |

The non-duplication test is stated as FR-104 and is mechanically checkable: the call-site count of
`materialize_history` must not grow, and the Common Crawl discovery block must exist in exactly one
place.

---

## D4 dead-code dispositions

Importer counts below are **non-test** and exclude `donors/` and `tmp/`.

| File | Lines | Non-test importers | Verdict | Justification |
|---|---|---|---|---|
| `apps/control-plane/workflows/investigation.py` | 291 | **0** | **DELETE** (lifecycle relocated first) | F9. Unregistered; calls two activities with no definition repo-wide; and `investigation.py:286` is a class-level `workflow.signal(...)` that cannot address a target, so the file is not runnable as written. Keeping 291 lines of `@workflow.defn` surface that reads as *the* investigation workflow is the specific trap Principle VI creates. **`InvestigationLifecycle` / `LifecycleState` / `LifecycleConfig` / `InvalidLifecycleTransition` (`:57-186`) are relocated first** into `cp_domain/investigation.py`, beside the `InvestigationMonitor` that `investigation.py:37` already imports — one lifecycle, one home — and `tests/unit/test_workflows.py` is re-pointed there. Its 12 tests must stay green. |
| `apps/control-plane/services/layer0_pipeline.py` | 355 | **0** (`tests/integration/test_layer0_direct_pipeline.py` only) | **DELETE orchestrator; KEEP the four hook `Protocol`s** | D-4. `seed()`'s `investigation_id: str = ""` (`layer0_pipeline.py:301`) makes the primary entry point investigation-less, and the class calls itself `the missing composition root` (`:10-11`) while a constitutional one is being built. Two entry points is a Principle VI violation. The `Protocol`s `InterpretHook` (`:121-132`), `FabricHook` (`:135-140`), `SearchHook` (`:143-146`) and `LakeHook` (`:149-152`) are **kept verbatim**, moved to `workflows/investigation_lifecycle.py`, and become the shape of stages 2–8. They express the one genuinely good idea in the file — `layer0_pipeline.py:117-118` `These are the *only* places the pipeline reaches into the entity plane.` |
| `apps/control-plane/services/acquisition_loop.py` | 117 | **1** — `layer0_pipeline.py:44` (itself 0) | **DELETE** | It is the fetch path the constitution's Security-First list forbids. `acquisition_loop.py:51-53` — `client or httpx.AsyncClient(timeout=10.0, follow_redirects=True, headers={"User-Agent": "cognitive-acquisition/0.1"})` — and `acquisition_loop.py:63` — `resp = await self._client.get(item.uri)`. `follow_redirects=True` on an untrusted URL with no allowlist, no DNS-rebinding protection and no egress policy is SSRF by construction, and Principle VII makes all of those *mandatory*. **Wiring this into the new workflow would convert a dead violation into a live one.** It is replaced by an `AcquisitionWorker`-conformant implementation (Principle V's `capabilities()/estimate()/acquire()`), which is the only shape that can carry the VII controls. `FrontierItem` and `PgFrontier` (from `services/frontier.py`) are kept and used by the replacement. `LoopResult` (`:24-36`) is kept as the activity's output type. |
| `apps/control-plane/services/dispatcher.py` | 211 | **0** | **KEEP-AND-WIRE, narrowly corrected** | Principle VI requires the lifecycle to run *"within its policy/budget/freshness constraints"*, and this is the only in-repo code implementing a policy/budget gate: `dispatcher.py:96-103` `decision = self._policy.check(policy_id="policies/default", source_class=source_class, host=item.host_key or "", worker_class=worker_class, units=0.001, budget_id="budget/default")` → `dispatcher.py:104-106` `if decision.value == "DENY": self._frontier.cooldown(…)`. Deleting it deletes the constitution's only budget gate. **Two corrections are mandatory, and they are Principle IV work, not cleanup:** (i) the fabricated `task_spec` (`dispatcher.py:74-85`) must be replaced by per-investigation state — `relevance=0.7` and `source_quality=0.7` are literals for every task in the repository; (ii) `run_recon_plan` (`:132-199`) is dropped — a second planning path with its own `ReconPlanStatus` lifecycle that the brief never asked for. `DispatchResult` is kept as the `acquire` activity's scheduling result. |
| `apps/control-plane/services/policy_service.py` | 54 | **1** — `dispatcher.py:21` (itself 0) | **KEEP-AND-WIRE, with a tenancy defect fixed** | Same reasoning as `dispatcher.py`, one link closer to dead: it is the only wrapper over `cp_domain.policy.PolicyEngine` and the only consumer of the retry budget the constitution mandates. The defect: `policy_service.py:22-28` hard-codes `tenant_id="default-tenant"` on both the `Policy` and the `Budget`, and `PolicyEngine.check` (`cp_domain/policy.py:84-108`) looks the policy up by id and evaluates it without ever comparing the requesting tenant. A second tenant is therefore evaluated against the first tenant's policy. Fix: the service becomes tenant-keyed and `check()` refuses a tenant that does not own the named policy, failing closed. That is Principle **VII**, cited correctly this time. |
| `apps/control-plane/services/audit.py` | 67 | **0** (`tests/unit/test_us3_ops.py:8` only) | **KEEP-AND-WIRE, as a durable sink** | Principle VII names `audit logs` in its **Mandatory** list, and the durable table already exists: `db/schema.py:596 class AuditLog(Base):`. The defect is the implementation, not the concept: `audit.py:40-41` — `self._events: list[AuditEvent] = []` / `if self._pg_copy is not None: self._pg_copy(event)` — a process-lifetime list with an optional sink that nothing supplies. An audit log that dies with the pod is not an audit log, and 021 changes the admission and projection layers, which is exactly what must be audited. Wire: `investigation.admit_claims` writes `AuditKind.DECISION` and `investigation.project` writes `AuditKind.PROJECTION` to `db/schema.py:596`, with the decision's reason codes and score vector attached per `constitution.md:73`. `AuditEvent.immutable` (`audit.py:33-35`) stays `True`. |

### 4.1 Which of these touch "rejected candidates are never auto-deleted"

The clause, verbatim (`constitution.md:65`): `rejected candidates are never auto-deleted
(replay/re-evaluation supported).`

| File | Touches it? | Why |
|---|---|---|
| `audit.py` | **Yes — the fix *is* the obligation.** | A `REJECT` decision that leaves no durable record *is* an auto-delete in everything but name: the candidate survives in memory and is gone with the process. Governance requires rejections preserved *"with decision, reasons, score vectors, versions, and timestamps for replay"* — a `list[AuditEvent]` preserves none of that across a restart. Wiring `audit.py` to `db/schema.py:596` is what makes the clause true. |
| `investigation.py` | **No, and that is a reason to delete it.** | `LifecycleState.REJECTED` (`:63`, and `:114` `LifecycleState.REJECTED: (LifecycleState.COMPLETED, LifecycleState.QUEUED)`) is an *investigation*-level state with nothing to do with *candidate* preservation. Its `@workflow.defn` surface invites someone to wire it and then add a "reject the investigation, drop its candidates" branch. Deleting removes the temptation. |
| `layer0_pipeline.py` | **No.** | It never rejects anything; it returns `StageOutcome(ok=False, …)` and a tick. Its `seed()` is the relevant part, and that is a Principle VI problem, not a preservation problem. |
| `acquisition_loop.py` | **No — but adjacent.** | `acquisition_loop.py:66` `await self._frontier.fail_retry(item.frontier_id)` on `httpx.HTTPError` and `:78-79` `prev_digest = await self._frontier.last_digest(item.frontier_id, item.uri)` are a retry/degradation path, not a candidate path. The frontier does delete rows: `frontier.py:430` `await session.execute(Row.__table__.delete().where(Row.frontier_id == frontier_id))`. Frontier rows are *work items*, not rejected candidates, so the clause is not engaged — but the new `acquire` activity MUST NOT propagate that delete to any rejected candidate, and FR-110 says so explicitly. |
| `dispatcher.py` | **No.** | `dispatcher.py:105` `self._frontier.cooldown(...)` on `DENY` is a deferral, which is the correct behaviour for a refusal to spend. |
| `policy_service.py` | **No.** | `PolicyEngine.check` returning `PolicyDecision.DENY` (`cp_domain/policy.py:100`, `:106`) is a *refusal to spend*, not a rejection of a consideration. |

### 4.2 The file that actually violates the clause is not in the D4 list

I flag it anyway, because leaving it would make FR-110 unsatisfiable. `apps/shared/events/dlq.py:76-80`:

```python
    def purge(self, record_id: str) -> bool:
        record = self._records.pop(record_id, None)
        if record is not None:
            self._by_fingerprint.pop(record.fingerprint(), None)
        return record is not None
```

reachable from a live route, `apps/control-plane/api/routes/quarantine.py:58-65`:

```python
@router.post("/{record_id}/re-evaluate")
async def re_evaluate(record_id: str, ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None) -> dict:
    record = _store.get(record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="record not found")
    mark = "rejected" if "malformed" in record.reason else "accepted"
    _store.purge(record_id)
    return {"record_id": record_id, "re_evaluated": mark, "tenant_id": ctx.tenant_id}
```

`re_evaluate` **purges the record it just re-evaluated**. The route's own docstring
(`quarantine.py:1-5`) claims the opposite — `Preserved rejected candidates can be listed and`
`replayed; replay keeps the original payload byte-for-byte so re-evaluation is faithful to the poison`
`message that produced the failure.` — and re-evaluation is *less* faithful than replay, because
the record is gone. FR-110 is written against this, and
`tests/integration/test_quarantine.py:49` (`assert store.purge(rid) is True`) currently pins the
violating behaviour and must be inverted.

---

## D5 ADR

Written in the house style of `docs/adr/` — `# ADR-NNNN: Title`, then `## Status` / `Date:` /
`Feature:`, then `## Context` / `## Decision` / `## Rationale` / `## Consequences`, matching
`0019-reconstruction-frontier.md` and `0021-atomic-stream-sequence.md`. Next free number: **0025**
(`0024-claim-and-context-persistence.md` is the highest).

**Four ADRs are required, not one.** The job asks for "the new workflow"; Governance requires an
ADR for `Temporal`, for `recrawl`, for `provenance` (the Evidence-First chain repair) and for
`entity resolution` (the N5 synonym table that `phase0-results.md:174` (K5) flags as ADR-grade with
no ADR). Writing one document and citing it for four decisions would repeat the gate's original
error at a larger scale.

### 5.1 `docs/adr/0025-investigation-lifecycle-entry-point.md` — Principle VI

```markdown
# ADR-0025: The Investigation is the only production entry point

Status: Proposed
Date: 2026-09-27
Feature: 021-entity-relation-extraction-finalization (FR-101…FR-106, FR-112)

## Context

Constitution Principle VI requires that "the user creates an Investigation — not a graph", and
that graphs, search indices, analytical structures and TDA complexes "materialize automatically
within the investigation lifecycle and its policy/budget/freshness constraints". The Additional
Constraints repeat it: "implement contracts of all major planes (Investigation, Acquisition,
Evidence, Interpretation, Admission, Projection, Analysis, Feedback) up front".

The Investigation is the **only** plane in that list with no contract. `cp_domain/investigation.py`
has a domain model (`InvestigationState`, `Investigation`, `InvestigationMonitor`) and
`workflows/investigation.py:190,278` has two `@workflow.defn` classes. Neither is reachable. The
worker (`workflows/worker.py:20-27`) registers one workflow:

    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[TemporalEntityMaterializationWorkflow],
        activities=[reconcile_and_publish],
    )

What is reachable instead is `services/entity_pipeline.py:38`:

    async def run_live_entity_pipeline(*, tenant_id: str, entity_id: str, identity: dict[str, Any], source_records: list[dict[str, Any]], catalog: Catalog, operations: Any) -> None:

No `investigation_id`. It reaches `interpret_warc_capture` directly (`entity_pipeline.py:75-80`),
keeps its projection in a module-level dict (`entity_pipeline.py:87-88`,
`_entity_streams[(tenant_id, entity_id)] = list(records)`) and announces completion on an
in-process hub (`entity_pipeline.py:96`, `hub.publish("temporal.materialization.ready", …)`). This
is user → extractor → graph with no investigation, no policy gate, and a projection that dies with
the process.

The dead workflow cannot simply be registered. It executes `"acquisition.acquire_batch"`
(`investigation.py:213`) and `"acquisition.recrawl"` (`investigation.py:288`), neither of which is
defined anywhere in the repository — the only `@activity.defn` is
`temporal_materialization.reconcile_and_publish` (`temporal_materialization.py:24`). And
`investigation.py:286` is `workflow.signal(InvestigationWorkflow, "schedule_recrawl")`, a call on
the workflow *class* from inside a different workflow; Temporal signals address a running workflow
by id, so even with both activities supplied the file could not run.

The brief does not mention investigations. `input.md` is silent, so the constitution governs.

## Decision

Add **`InvestigationWorkflow`** to a new `apps/control-plane/workflows/investigation_lifecycle.py`,
on task queue `cognitive-investigations`, with eight activities in this order: `acquire` →
`bind_mentions` → `extract_type_signals` → `extract_relation_signals` → `assemble_candidates` →
`validate_candidates` → `admit_claims` → `project`.

It is **new and minimal**, not a resurrection. It carries no approval gate and no recrawl loop; it
reuses `cp_domain.investigation.InvestigationState` rather than declaring a third lifecycle; and
every stage is a thin typed activity call with no logic of its own.

`workflows/investigation.py` is **deleted**, with `InvestigationLifecycle` and its state machine
relocated into `cp_domain/investigation.py` beside the `InvestigationMonitor` that
`investigation.py:37` already imports.

`entity_pipeline.py` becomes a client: it starts the workflow and returns a run id. It no longer
calls `interpret_warc_capture` and no longer holds a projection.

`reconcile_and_publish` is **retained, not reimplemented**. It becomes the Common Crawl
implementation behind the `acquire` activity and loses its inline `materialize_history` and
`from_entity_stream` calls, which are interpretation and move to stages 5 and 8. Its four
duplicated `StreamRecord(...)` literals collapse into one helper, and the hard-coded
`"confidence": 0.91` in each is replaced by a real score vector.

## Rationale

- **A single subject.** Principle VI asserts what the user creates. With two reachable entry
  points, "the user creates an Investigation" is a statement about half the system.
- **The pipeline shape is not lost, it is nested.** The brief's five stages (`spec.md:22-27`)
  become the workflow's stages 2–8. Nothing in the brief requires the user to be the unit of
  work; it simply never says what is.
- **New, not resurrected, because the old file is not runnable.** Registering it would surface two
  missing activities and one broken signal call at first execution rather than at review.
- **`cp_domain`'s lifecycle wins** because it is the one that already claims the principle in its
  own docstring (`cp_domain/investigation.py:1`), already validates budget and scope on
  transitions, and already owns the "persist once at close" monitor invariant. Two lifecycles with
  two transition tables is a fork, not a reference implementation.
- **`reconcile_and_publish` is historical reconstruction**, governed by ADR-0019, and deleting it
  would remove a working path that 021 has no mandate to touch.

## Consequences

- `run_live_entity_pipeline` loses its synchronous result. Callers that needed the projection
  inline must await the workflow or read the rebuilt projection. This is a real interface break
  and is declared, not hidden.
- `_entity_streams` and the in-process `hub.publish` for `temporal.materialization.ready` are
  replaced by a durable publication record and a Kafka `temporal.materialization.ready` event.
- Recrawl is **not** implemented by this workflow. ADR-0017 owns it; this ADR deliberately leaves
  the question open and records it as 021's known limitation rather than quietly inheriting
  `RecrawlWorkflow`.
- Registration is test-enforced, because "the workflow exists" is exactly the claim that has been
  false four times in this repository.
- Extends ADR-0007 (Temporal). It does not revisit the workflow-engine choice.
```

### 5.2 `docs/adr/0026-evidence-warrant-resolution.md` — Principle II (provenance)

```markdown
# ADR-0026: Evidence warrant resolution, and what the backward chain may omit

Status: Proposed
Date: 2026-09-27
Feature: 021-entity-relation-extraction-finalization (FR-109, SC-013, US9, INV-005)

## Context

Constitution Principle II requires that "any knowledge must trace fully: Finding →
Analytical/Topological Feature → Graph/Assertion → Evidence → Observation → Raw Object → Source",
and that "every analytical result must be reproducible from source observations/evidence".

`apps/shared/domain/evidence_lineage.py` implements two chains over a nine-member `HopKind`
(`:50-65`): `EVIDENCE_BACKWARD_CHAIN` (`:81-89`) and `DERIVATION_FORWARD_CHAIN` (`:102-112`).
Two facts about them are in tension with the specification of this feature.

First, `CANDIDATE` is absent from the backward chain **by decision and with a written argument**
(`:75-80`):

    #: ``CANDIDATE`` is deliberately **absent** (T014). A candidate is a hypothesis about a
    #: relation, not a carrier of the evidence for one: it holds no observation of its own, it
    #: holds *references* to observations. Putting it here would make the evidence walk imply
    #: that a reading is itself evidence, and would let a claim be justified by appeal to an
    #: inference rather than to anything anybody saw.

That argument is sound. It is also a direct contradiction of this feature's own INV-005
(`spec.md:371-372`), which is consistent with it, and of its own SC-013 (`spec.md:897-898`), which
is not: "the round trip `edge → claim → candidate → signals → observations → source` and back
reaches every edge that source fed". A document cannot assert both.

Second, and larger: **`SIGNAL` is in neither chain.** `HopKind` has no `SIGNAL` member, so SC-013's
`→ signals` hop is unreachable in **both** directions. Adding `CANDIDATE` to the backward chain
would still not make SC-013 achievable. This is a type-vocabulary defect, not an ordering defect,
and no reordering of a tuple fixes it.

The constitution's own chain names a level the repository has no member for at all:
`Analytical/Topological Feature` (Principle II), which INV-6 describes as "structural signals, not
proof of identity".

## Decision

Add `SIGNAL` to `HopKind` and to both chains, in the position Principle II assigns it — between
the record that carries the evidence and the inference derived from it. `CANDIDATE` **stays out of
`EVIDENCE_BACKWARD_CHAIN`**; the argument at `:75-80` is adopted as written.

Resolve INV-005 vs SC-013 by making the candidate's presence a **resolution** rather than a hop. The
backward walk returns a warrant path of `RELATION → ASSERTION → MENTION → SEGMENT → OBSERVATION →
CAPTURE → SOURCE` plus, for each hop that references candidates, the set of `candidate_id`s
resolvable at that point. `EvidenceGraph.backward` gains an explicit `resolve_references` step. The
candidate is therefore *reachable* from an edge — SC-013 is satisfiable — while never being
*load-bearing as evidence* — INV-005 is preserved. INV-005 is amended to say so explicitly rather
than left to be read as a contradiction of SC-013.

Add a `FINDING`-or-`TOPOLOGY`-level hop **only if** 021 actually produces a TDA or analytical
finding. It does not; `apps/science/` is untouched. Principle II's chain is therefore satisfied
over the levels this platform currently produces, and the remaining gap is recorded as
constitutional debt against `apps/science/` rather than papered over with a hop nothing writes.

## Rationale

- Both requirements are constitutional, and Principle II's "trace fully" is not satisfied by a walk
  that stops before reaching what produced the evidence.
- A hop kind nothing writes is worse than a missing one: it would be a step that silently produces
  `complete=False` on every trace, which `evidence_lineage.py:10-13` is explicit that an incomplete
  chain must report rather than hide.
- Reference resolution is the honest model. A candidate is not *on* the warrant path; it is
  *addressable from* it. Encoding that as a second step rather than a hop keeps INV-005 true in the
  type system instead of in a comment.
- Choosing *not* to add an analytical hop is a decision, and recording it as one is the difference
  between an honest gap and a fabricated level.

## Consequences

- `EVIDENCE_BACKWARD_CHAIN` and `DERIVATION_FORWARD_CHAIN` are no longer inverses of each other by
  exactly one entry. The comment at `:114-124` must be rewritten; it currently states the difference
  is `CANDIDATE`, which will no longer be true.
- `apps/shared/tests/unit/test_evidence_lineage.py` is affected. Note that
  `test_t062_the_api_path_is_reachable_in_both_directions` is **already failing** in the Phase 0
  baseline (`phase0-results.md:43`); this ADR does not assume that failure is caused by the missing
  hop and does not claim to fix it.
- SC-013 becomes achievable and US9's independent test (`spec.md:311-313`) becomes runnable.
- Principle II's `Analytical/Topological Feature` remains unimplemented and is recorded as debt
  against `apps/science/`, not against 021.
- Extends ADR-0012 (provenance).
```

### 5.3 `docs/adr/0027-invocation-boundary-tenant-scoped-policy.md` — Principle VII

```markdown
# ADR-0027: The invocation boundary and tenant-scoped policy

Status: Proposed
Date: 2026-09-27
Feature: 021-entity-relation-extraction-finalization (FR-106, FR-111, FR-112)

## Context

Principle VI requires the investigation lifecycle to run "within its policy/budget/freshness
constraints". Principle VII makes "tenant isolation at every level" and "network egress policy"
mandatory. Neither is met.

**Policy is one tenant deep.** `services/policy_service.py:21-41` constructs exactly one `Policy`
and one `Budget`, both with `tenant_id="default-tenant"`, and `cp_domain/policy.py:84-108` looks
the policy up by id and evaluates it without ever comparing the requesting tenant:

    def check(
        self, *, policy_id: str, source_class: str, host: str, worker_class: str, units: float,
        budget_id: str | None = None,
    ) -> PolicyDecision:
        policy = self._policies.get(policy_id)
        if policy is None:
            return PolicyDecision.DENY

A second tenant is evaluated against the first tenant's policy. The clause is "tenant isolation at
every level"; a policy store keyed on one tenant is the level at which it fails.

**The budget is one tier deep.** The Additional Constraints require "task / source / investigation /
global retry budgets". `policy_service.py:53` is
`def commit_usage(self, budget_id: str, worker_class: str, units: float) -> None:` — a worker class
and an amount. There is no task, source, investigation or global tier.

**Backpressure is switched off.** `services/dispatcher.py:86` is
`score = self._scorer.score(task_spec, {"downstream_lag_s": 0.0})`. `downstream_lag_s` is a literal
`0.0`, so the mechanism the "Backpressure" constraint depends on is present and permanently reports
no lag.

**The fetch path has no egress policy.** `services/acquisition_loop.py:51-53` builds
`httpx.AsyncClient(timeout=10.0, follow_redirects=True, …)` and `:63` does
`resp = await self._client.get(item.uri)` on an untrusted URL, with no allowlist, no DNS-rebinding
protection and no egress policy — every item on Principle VII's mandatory list, absent.

## Decision

Introduce an explicit **invocation boundary** owned by the `investigation.acquire` activity.
Concretely: (1) `PolicyService` becomes tenant-keyed and `check()` refuses any request whose tenant
does not own the named policy, failing closed; (2) `Budget` gains the four declared tiers and a
`commit_usage` that takes the tier; (3) `downstream_lag_s` is read from a real queue-depth and
projection-lag source, and a **missing** reading is treated as maximum lag, not as zero; (4) the
fetch implementation behind `acquire` is `AcquisitionWorker`-conformant and performs DNS resolution
and revalidation after redirect, so `follow_redirects` cannot be used to reach an internal address.

## Rationale

- A constitution clause with no test is not enforced. All four of these are indistinguishable from
  working code by inspection, which is why they survived.
- "Fail closed" is already the house rule at the layer below (`protocol.py:294-300`,
  `assembly.py:263-268`); a policy store that admits an unowned policy would be the one place in
  the path that fails open.
- Treating absent lag as maximum rather than zero inverts the safe default. Zero lag means "no
  backpressure", which maximises acquisition — the opposite of the constraint's requirement.
- The four budget tiers and the tenant key are architectural decisions on the Governance list
  ("PostgreSQL role", "frontier architecture", "scheduling"), and adding them without an ADR would
  extend a pattern the ADR list exists to stop.

## Consequences

- A tenant with no policy of its own is **denied**, not defaulted. This is a behaviour change for
  any deployment relying on the single default policy, and it is the intended one.
- Budget accounting gains three tiers of state that must be persisted, not held in memory as
  `PolicyService` does today.
- Backpressure gains a real input, so a saturated downstream will visibly reduce acquisition rate.
  This is a new failure mode that no test currently covers.
- `acquisition_loop.py` is deleted rather than wired (ADR-0025, FR-112); the boundary is the reason
  it must not be.
```

### 5.4 `docs/adr/0028-structural-predicate-equivalence.md` — entity resolution (the N5 table)

```markdown
# ADR-0028: Structural predicate identity admits no synonym table

Status: Proposed
Date: 2026-09-27
Feature: 021-entity-relation-extraction-finalization (K5, E1, FR-107)

## Context

Governance requires an ADR for "entity resolution". `data-model.md` N5 proposes a worked synonym
example — `owns ≡ controls` — for the `PredicateSignature`'s `normalized_predicate` term. That term
is a term of `logical_candidate_id`.

A synonym table over a term of the logical identity is an identity authority. It would make two
predicates the same relation by fiat, and it would do so silently: no signal was produced, no
evidence recorded, and the two candidate ids would coincide.

This is forbidden four separate times, by the brief (§20, `input.md:1288-1304`: "Only unify when
deterministic normalization or explicit semantic mapping establishes that configuration"), by
FR-004 (`spec.md:387-389`: "MUST NOT unify semantically distinct relations.
`owns`/`controls`/`manages` MUST remain distinct"), by US2's third acceptance scenario, and by
constitution INV-3 (`Assertion != truth`). `phase0-results.md:150` (E1) already records this.

No ADR exists, and the decision has no slot in `FR-083`'s A–K list (`spec.md:822-831`).

## Decision

The N5 synonym table is **not** admitted. `PredicateSignature.normalized_predicate` is a
deterministic normalisation of a *surface realisation* — lemma, voice, preposition and particle
normalisation — and nothing else. `owns` / `controls` / `manages` remain three logical hypotheses
(`SC-007` already requires this). Predicate identity across vocabularies is `TypeMapping`'s job,
carrying `match type, provenance and confidence` (`spec.md:850-852`), and a mapping is evidence, not
identity.

## Rationale

- A synonym table cannot be derived from evidence, so it can be neither replayed nor disputed. Both
  are required by Principle II.
- Governance names "entity resolution" as an ADR-bearing decision. This is one whichever way it is
  decided, and an ADR is cheaper than discovering the decision in a mutation test.
- Recording the rejection is what stops it reappearing. `data-model.md` N5 is a *worked example*,
  and worked examples get copied.

## Consequences

- `data-model.md` N5 must be rewritten, and `FR-083`'s A–K list gains a twelfth entry rather than
  absorbing this one.
- Normalisation rules for the *structural* part of the signature become load-bearing and must be
  specified exactly (`research.md` R-007 Q1). A vague rule here is an identity risk, not a quality
  nicety.
- If external vocabulary mapping is ever to be trusted for identity, that is a **new** ADR, and it
  must be argued on SSSOM match types rather than on a Python dict.
- Extends ADR-0013 (entity resolution).
```

---

## D6 new FR text (FR-101…FR-1xx, verbatim)

Numbering continues from `FR-100` (`spec.md:781-789`). Insert as a new subsection
`### Constitutional requirements (Principle VI, II, VII; Governance)` immediately after FR-100 and
**before** the `### Production reachability, as measured` heading at `spec.md:791`, so that the
reachability table sits under requirements that explain why it exists.

Every FR is independently testable and names its test method. Test paths follow the repo's
existing layout; `tests/constitution/` is the directory the repo already reserves for this purpose
(`apps/shared/tests/constitution/`), and `apps/control-plane/tests/constitution/` is new and
required by FR-101…FR-104, FR-106, FR-108 and FR-112.

```markdown
### Constitutional requirements (Principle VI, II, VII; Governance)

These requirements implement Constitution Principles VI (Process-Centric), II (Evidence-First)
and VII (Security-First), plus the Additional Constraints and the Governance clauses, none of
which any existing FR in this document covers. Authority order: the constitution supersedes
`input.md`, which supersedes this document. Worked examples are in
`repair/A1-constitution-investigation.md` §D2.4.

- **FR-101**: The `Investigation` MUST be the only production entry point for the extraction and
  projection substrate. A production module outside the investigation workflow MUST NOT call
  `interpret_warc_capture`, an extractor, an assembler, an admission engine, or a graph store.
  `services/entity_pipeline.py::run_live_entity_pipeline` MUST become a client that starts an
  `InvestigationWorkflow` and MUST NOT hold a projection itself.
  **Test**: `apps/control-plane/tests/constitution/test_vi_single_entry_point.py::test_no_production_caller_of_interpretation_outside_the_workflow`
  — scans every non-test module under `apps/` for the six forbidden callees and fails on any hit
  outside `workflows/investigation_lifecycle.py`.
  **Rationale**: Principle VI — "The user creates an Investigation — not a graph."

- **FR-102**: The direct `user → extractor → graph` path MUST be prohibited as a *class of
  defect*, not merely as a call site. An extraction request that does not name an
  `investigation_id` MUST be refused at the boundary, and the refusal MUST be a named error code,
  not a `None` return. Stage ordering MUST continue to be validated by
  `cp_domain.investigation._TRANSITIONS`; an out-of-order stage MUST raise
  `InvestigationInvalidTransition`.
  **Test**: `apps/control-plane/tests/constitution/test_vi_single_entry_point.py::test_a_request_without_an_investigation_id_is_refused_with_a_named_code`
  and `::test_stages_may_not_run_out_of_order`.
  **Rationale**: Principle VI; Additional Constraints "No MVP/mini-architecture" — eight planes,
  each of which needs a contract.

- **FR-103**: `InvestigationWorkflow` MUST be registered on the Temporal worker, on task queue
  `cognitive-investigations`, together with every activity it calls. A workflow or activity that is
  not registered MUST NOT be described in a spec, plan or docstring as available.
  **Test**: `apps/control-plane/tests/constitution/test_vi_single_entry_point.py::test_investigation_workflow_and_all_activities_are_registered`
  — imports `workflows.worker`, reads its `workflows=` / `activities=` lists and asserts membership;
  plus `::test_no_workflow_executes_an_activity_by_string_name`, which fails on any
  `workflow.execute_activity` whose first argument is a `str` literal.
  **Rationale**: Principle VI; Additional Constraints "No MVP/mini-architecture". The two string
  activity names at `workflows/investigation.py:213,288` are the reason.

- **FR-104**: The workflow's stages MUST be, in order: `acquire`, `bind_mentions`,
  `extract_type_signals`, `extract_relation_signals`, `assemble_candidates`, `validate_candidates`,
  `admit_claims`, `project`. Mention binding MUST be its own stage and MUST NOT be folded into
  signal extraction. The workflow MUST NOT reimplement
  `temporal_materialization.reconcile_and_publish`; it MUST delegate to it, and the number of call
  sites of `domain.temporal_materialization.materialize_history` and of the Common Crawl discovery
  block MUST NOT increase.
  **Test**: `apps/control-plane/tests/constitution/test_vi_single_entry_point.py::test_stage_order_is_the_declared_order`
  (asserts the recorded activity order from a hermetic `Worker` run) and
  `::test_materialize_history_call_sites_do_not_grow` (a fixed-count assertion, currently 3,
  documented as such).
  **Rationale**: Principle VI; and the four duplicated `StreamRecord` literals at
  `temporal_materialization.py:65,82,98,115`, each hard-coding `"confidence": 0.91`.

- **FR-105**: Every consumer in the investigation path MUST be idempotent on a key drawn from
  `event_id` / `task_id` / `observation_id` / projection offsets, and the key MUST be named in the
  consumer's signature. Specifically: `acquire` on `task_id`; `bind_mentions` on `observation_id`
  **including the capture** in the key, so two captures of one segment are two mentions;
  `extract_type_signals` and `extract_relation_signals` on `event_id`; `assemble_candidates` on
  the derived `candidate_id`; `validate_candidates` on the derived `relation_id`; `admit_claims` on
  an `admission_id` **re-derived** from `(candidate_id, policy_version, reason_codes,
  score_vector)` rather than `uuid.uuid4().hex[:12]`; `project` on a monotonic
  per-`(tenant_id, investigation_id)` `projection_offset` written on success only.
  **Test**: `apps/shared/tests/constitution/test_vi_idempotency_keys.py::test_every_activity_declares_an_idempotency_key`
  (introspects the eight activity signatures), `::test_admission_id_is_content_addressed` (two
  identical admissions derive one id; two differing `reason_codes` derive two), and
  `::test_replaying_a_completed_task_id_issues_no_network_call`.
  **Rationale**: Additional Constraints "Idempotency" — the clause quotes these four keys by name.
  Currently `admission.py:69` mints a fresh `uuid4` and
  `temporal_materialization.py:152-157` retries three times with no key at all.

- **FR-106**: The investigation lifecycle MUST run within a policy, budget and freshness gate
  before `acquire` performs any network call, and the gate MUST be tenant-scoped: a policy or
  budget that does not belong to the requesting tenant MUST be refused fail-closed, not defaulted.
  Budgets MUST exist at the `task`, `source`, `investigation` and `global` tiers. A missing
  downstream-lag reading MUST be treated as **maximum** lag, not as zero.
  **Test**: `apps/control-plane/tests/constitution/test_vii_policy_boundary.py::test_another_tenants_policy_is_refused`,
  `::test_four_budget_tiers_exist`, `::test_absent_lag_reading_is_treated_as_maximum_lag`,
  `::test_no_network_call_occurs_before_the_gate_passes`.
  **Rationale**: Principle VI's "its policy/budget/freshness constraints"; Principle VII's "tenant
  isolation at every level"; Additional Constraints "Backpressure" and "Retry budgets". Currently
  `dispatcher.py:86` passes `{"downstream_lag_s": 0.0}` and `policy_service.py:22-28` hard-codes
  one tenant.

- **FR-107**: A change to an architectural decision on the Governance list MUST ship an ADR before
  the change merges. For this feature that means, at minimum: `Temporal` (the investigation
  workflow), `provenance` (the evidence warrant chain), `entity resolution` (any synonym or
  equivalence table over a term of `logical_candidate_id`), and `recrawl` (any scheduling
  decision). `FR-083`'s A–K list is extended with the entries this feature actually decides. A
  synonym or equivalence table over `PredicateSignature.normalized_predicate` is **forbidden**:
  `owns`, `controls` and `manages` remain three logical hypotheses.
  **Test**: `apps/control-plane/tests/constitution/test_governance_adrs_exist.py::test_each_governance_decision_in_this_feature_has_an_adr`
  — asserts `docs/adr/0025`…`0028` exist, are non-empty and each contains a `## Decision`
  section; plus `::test_no_synonym_table_over_normalized_predicate`, which scans the 021 artefacts
  and `PredicateSignature` for any `owns`–`controls` equivalence.
  **Rationale**: Governance, verbatim: "Changes to architectural decisions require an ADR (e.g., …
  provenance, entity resolution, admission engine, frontier architecture …)".

- **FR-108**: Constitutional compliance MUST be verified automatically on every change, not by
  hand. If no CI is added, the completion report MUST carry a dated, named attestation of who ran
  the gate, on which commit, with the per-suite failure counts from the Phase 0 baseline — and
  `FR-084`'s "verified" MUST NOT be claimed for any check that was not run.
  **Test**: `apps/control-plane/tests/constitution/test_governance_adrs_exist.py::test_constitutional_suite_runs_unattended`
  — runs `pytest apps/shared/tests/constitution apps/control-plane/tests/constitution` in a
  subprocess with no network and asserts exit code 0; plus
  `::test_completion_report_distinguishes_implemented_verified_and_offline`, which greps the report
  for the five required words and fails on a bare "complete".
  **Rationale**: Governance, verbatim: "Compliance is verified on every PR/review." `.github/`
  does not exist.

- **FR-109**: A `SIGNAL` hop kind MUST exist and MUST be traversable in **both** directions, and a
  `candidate_id` MUST be reachable from any projected edge **without** `CANDIDATE` becoming a link
  in `EVIDENCE_BACKWARD_CHAIN`; the resolution is a second step, not a hop. A reference that cannot
  be resolved MUST be reported as an incomplete trace naming the gap, never as an empty hop list.
  **Test**: `apps/shared/tests/unit/test_evidence_lineage.py::test_a_signal_hop_is_traversable_backward_and_forward`,
  `::test_candidate_is_resolvable_from_a_relation_without_joining_the_warrant_chain` (asserts
  `EVIDENCE_BACKWARD_CHAIN` still excludes `CANDIDATE`), and
  `::test_an_unresolvable_reference_names_the_gap`.
  **Rationale**: Principle II — "Any knowledge must trace fully". `HopKind`
  (`evidence_lineage.py:50-65`) has no `SIGNAL` member, so `spec.md:897-898`'s
  `edge → claim → candidate → signals → observations → source` is unreachable in *either*
  direction. The `CANDIDATE` exclusion and its written argument at `:75-80` are preserved.

- **FR-110**: A rejected candidate MUST NOT be deleted by any production path, **including the
  path that handles its re-evaluation**. `POST /dlq/{record_id}/re-evaluate` MUST record the
  re-evaluation outcome **on** the preserved record and leave the payload byte-for-byte intact.
  `QuarantineStore.purge` MUST either be removed or be restricted to records whose payload has
  already been durably copied to the configured `sink`, and MUST be unreachable from any route.
  **Test**: `apps/control-plane/tests/integration/test_quarantine.py::test_re_evaluate_does_not_delete_the_record`,
  `::test_replay_after_re_evaluate_returns_the_original_payload_bytes`, and
  `::test_purge_is_unreachable_from_any_route` (introspects the FastAPI route table for a handler
  that reaches `QuarantineStore.purge`).
  **Rationale**: Additional Constraints, verbatim: "rejected candidates are never auto-deleted
  (replay/re-evaluation supported)"; Governance: "Rejected analysis outputs (admission rejections,
  TDA signals) are preserved with decision, reasons, score vectors, versions, and timestamps for
  replay." Currently `api/routes/quarantine.py:64` calls `_store.purge(record_id)`.

- **FR-111**: `services/audit.py::AuditLog` MUST write to the durable `AuditLog` table at
  `db/schema.py:596` and MUST NOT be satisfiable by an in-memory list alone. An `admit_claims`
  decision and a `project` write MUST each produce an audit record carrying the decision, the
  reason codes, the score vector, the policy version and the timestamp.
  **Test**: `apps/control-plane/tests/constitution/test_vii_audit_is_durable.py::test_an_admission_decision_is_persisted_and_survives_a_new_log_instance`
  and `::test_audit_records_carry_decision_reasons_score_vector_policy_version_and_timestamp`.
  **Rationale**: Principle VII's Mandatory list includes "audit logs". `audit.py:40` is
  `self._events: list[AuditEvent] = []`, `audit.py` has exactly one importer and it is a test, and
  the durable table that already exists has no writer.

- **FR-112**: `workflows/investigation.py` MUST be deleted and its lifecycle state machine
  relocated into `cp_domain/investigation.py`, so that exactly one investigation lifecycle exists.
  `services/layer0_pipeline.py`'s orchestrator MUST be deleted and its `InterpretHook`,
  `FabricHook`, `SearchHook` and `LakeHook` protocols retained on the investigation path.
  `services/acquisition_loop.py` MUST NOT be wired in any form: its fetch is
  `follow_redirects=True` with no egress policy, no DNS-rebinding protection and no host allowlist,
  which Principle VII forbids and which a live registration would turn from a dead violation into a
  live one.
  **Test**: `apps/control-plane/tests/constitution/test_vi_dead_surface_is_gone.py::test_workflows_investigation_py_does_not_exist`,
  `::test_exactly_one_investigation_lifecycle_module_exists` (searches for `class LifecycleState`
  and `class InvestigationState` and asserts one owner),
  `::test_layer0_orchestrator_is_gone_and_its_hooks_survive`, and
  `::test_acquisition_loop_is_not_imported_by_any_production_module`.
  **Rationale**: Principle VI (no single subject); Principle VII (egress). `workflows/worker.py:20-27`
  registers neither workflow and `investigation.py:213,288` name two activities that do not exist.

- **FR-113**: Every constitutional citation in code, tests, migrations and feature artefacts MUST
  name the correct numeral. Tenancy is **VII**, not IV. Determinism is **unnumbered** and MUST be
  cited to INV-12 or to the Additional Constraints' "Idempotency" clause, not to VI. A citation of
  the form "constitution N" MUST be accompanied, on the same line or in the adjacent comment, by
  the clause's title or text.
  **Test**: `apps/shared/tests/constitution/test_citation_numerals_are_correct.py::test_no_citation_attributes_tenancy_to_iv`
  and `::test_no_citation_attributes_determinism_to_vi` — a repository scan of all `.py` and `.md`
  files for the mis-cited patterns, which currently matches 20 sites for tenancy-as-IV and 6 for
  determinism-as-VI.
  **Rationale**: a gate that cites the wrong clause is not a gate. `plan.md:85` and `:86` are two
  of the sites, and `apps/shared/tests/constitution/test_iv_vi_tenancy_and_determinism.py` is a
  third — the constitution test suite's own filename.
```

### 6.1 Traceability

| FR | Principle / clause | Closes | Headline test method |
|---|---|---|---|
| FR-101 | VI | K3; FR-100's `entity_pipeline` seam | `test_no_production_caller_of_interpretation_outside_the_workflow` |
| FR-102 | VI; "No MVP/mini-architecture" | K3; the `Investigation` plane | `test_a_request_without_an_investigation_id_is_refused_with_a_named_code` |
| FR-103 | VI; "No MVP/mini-architecture" | K3; F9 | `test_investigation_workflow_and_all_activities_are_registered` |
| FR-104 | VI | duplication; `temporal_materialization.py` 4× `StreamRecord` | `test_stage_order_is_the_declared_order` |
| FR-105 | "Idempotency" | the clause is unmet in the 021 path | `test_every_activity_declares_an_idempotency_key` |
| FR-106 | VI; VII; "Backpressure"; "Retry budgets" | F8; `dispatcher.py:86`; `policy_service.py:22-28` | `test_four_budget_tiers_exist` |
| FR-107 | Governance (ADR list) | K5; K7's chain decision; recrawl | `test_each_governance_decision_in_this_feature_has_an_adr` |
| FR-108 | Governance ("every PR/review") | K4 | `test_constitutional_suite_runs_unattended` |
| FR-109 | II | K7 (and larger than K7 — see D-2) | `test_a_signal_hop_is_traversable_backward_and_forward` |
| FR-110 | "Dead letter / quarantine"; Governance | the `purge` inside `re_evaluate` | `test_re_evaluate_does_not_delete_the_record` |
| FR-111 | VII ("audit logs") | the in-memory audit log | `test_an_admission_decision_is_persisted_and_survives_a_new_log_instance` |
| FR-112 | VI; VII | D4; the dead surface | `test_exactly_one_investigation_lifecycle_module_exists` |
| FR-113 | all (the gate's own integrity) | K1's root cause; E13/E14 | `test_no_citation_attributes_tenancy_to_iv` |

**Out of scope for this job**, deliberately, and named so the omission is a decision: K6 (migration
`021` must also DROP `ck_relation_signal_asserts_something`,
`ck_relation_candidate_asserts_something` and update `ck_relation_signal_kind`'s whitelist). That is
a persistence requirement and belongs with the identity/persistence work, not with a constitution
check. It is recorded here so it is not lost.

### 6.2 One requirement I considered and rejected

FR-114 would have required `Principle VI` to govern the *brief* — i.e. that a user brief describing
a five-stage pipeline is itself a constitutional violation. It is not. The brief is a legitimate
input that happens to be silent on the subject, and FR-101 achieves the same constitutional result
by nesting the brief's five stages inside the investigation. Requiring the brief to name an
investigation would be inventing a rule the constitution does not contain — the same error as the
old gate, in the other direction.

---

## Line ranges in `plan.md` and `spec.md` that must change

Applied in this order. Ranges are inclusive and were read from the files as of HEAD
`00566655828258485795d58d38b5ebcdafb5ee9a`.

### 7.1 `plan.md`

**1 — lines 5–8: the inverted authority clause.** Replace with the D2.2 block.

OLD (`plan.md:5-8`):
```markdown
**Input**: Feature specification from `specs/021-entity-relation-extraction-finalization/spec.md`
(102 functional requirements, 5 constitutional invariants, 16 measurable outcomes, 9 user
stories). The unabridged user brief is `input.md` in this directory and governs over this
document wherever the two appear to differ.
```

NEW:
```markdown
**Input**: Feature specification from `specs/021-entity-relation-extraction-finalization/spec.md`
(102 functional requirements, 5 constitutional invariants, 16 measurable outcomes, 9 user
stories). The unabridged user brief is `input.md` in this directory (4898 lines, §0–§114).

**Authority order — the constitution wins.** `.specify/memory/constitution.md` v1.0.0 states
verbatim: "Constitution supersedes all other practices." The order of authority is, highest first:
the constitution; then `input.md` wherever the constitution is silent; then this feature's own
artefacts wherever both are silent. Where `input.md` and the constitution conflict, the
constitution wins, this feature implements the constitution, and the conflict is recorded in
`docs/adr/` with a worked example naming the clause on each side. An artefact MUST NOT state a
rule of interpretation that reverses this order, and the Constitution Check gate MUST be evaluated
on at least one case where the constitution and `input.md` **disagree**. Two worked examples — one
of agreement (§20 / INV-3) and one of disagreement (Principle VI, which the brief does not address)
— are in `repair/A1-constitution-investigation.md` §D2.4.
```

**2 — lines 75–91: the entire Constitution Check.** Replace with the D1 table. This is a
whole-block replacement; the old text is quoted in full so the diff is checkable.

OLD (`plan.md:75-91`):
```markdown
## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Gate | Status at plan time |
|---|---|---|
| I-2 `Mention != Candidate != Entity != …` (7 distinct levels) | No type may collapse two levels; `candidate_status` MUST NOT become a `rank()` | **PASS with work** — the levels exist, but `metadata.py` uses a *property name* as a participant and producers fabricate mention ids, which merges "mention" with "field name" |
| I-3 `Assertion != truth` | Unknown must be a retained state, never a drop | **PASS** — `PredicateResolutionState.UNKNOWN` exists and is retained; `material_requires_resolved_predicate` is the correct CD-6 line |
| I-4 `Graph != source of truth`; projection-first | `GraphEdge`/`HyperEdge` MUST be derivable only from admitted claims | **PASS** — `GraphProjectionBridge` is typed `claim: RelationClaim` with no overload, so a candidate or signal cannot be projected even by mistake |
| III projection-first; graph is a projection | Projection MUST be rebuildable from stores | **GAP** — `RebuildableGraphStore` has no production caller; no repository writes the 020 tables at all, so "rebuildable" is currently unproven |
| VI determinism | Content-addressed ids re-derived, never trusted; no result may depend on dict iteration order | **GAP** — `signal_refs` is identity material but never sorted, so `candidate_id` depends on caller order; determinism survives only because `assembly.py:338` sorts by hand |
| IV tenancy | No cross-tenant writes or reads | **PASS** — assemblable and `run_producer` both refuse cross-tenant output |
| "Constitution supersedes all other practices" | Any requirement in this plan that conflicts loses | **PASS** — the brief's §45 (no majority vote) and the constitution agree; where the brief's docstrings disagree with behaviour, behaviour wins and the docstring is corrected |

**Re-check after Phase 1 design**: confirm the `PredicateSignature` in the data model keeps
exactly two identity terms (structural signature + participant identity) and does not
reintroduce a surface-dependent term.
```

NEW: the full D1 table, headed:
```markdown
## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design and after every ADR in
`docs/adr/0025`…`0028` is Accepted.*

**Verdict: FAIL.** 4 Core Principles `violated`, 2 `lip service`; 2 Domain Invariants `violated`;
the `Temporal` baseline clause `violated`; 4 Additional Constraints `violated`; all 3 Governance
clauses `violated`. This feature does not proceed past Phase 0 until every `violated` row is
closed by a named FR.

*Coverage: all 7 Core Principles (verbatim names), all 12 Domain Invariants, all 15 Technology
Baseline clauses, all 7 Additional Constraints, and all 3 Governance clauses. Every row cites the
correct numeral. The previous table's four numbered rows are superseded in full: `I-2`/`I-3`/`I-4`
were Domain Invariants presented as Principles, `VI determinism` cited a Process-Centric principle
for a determinism requirement that does not exist in it, and `IV tenancy` cited "No Single Store /
Graph / Score" for a Security-First requirement. The old `I-2` verdict `PASS with work` is
**downgraded to violated**; the `I-3` and `I-4` verdicts are **preserved**.*

| Section | Verdict |
|---|---|
| Core Principles I–VII | I satisfied; **II violated**; **III violated**; IV lip service; V satisfied (acquisition half) / lip service (graph half); **VI violated**; **VII violated** |
| Domain Invariants 1–12 | 1 ✓, **2 violated**, 3 ✓, 4 ✓, 5 not engaged, 6 not engaged, 7 ✓, 8 not engaged, 9 ✓, 10 not engaged, 11 ✓, **12 violated** |
| Technology Baseline (15) | 9 satisfied, 5 not engaged, **Temporal violated** |
| Additional Constraints (7) | 1 satisfied, 2 lip service, **4 violated** |
| Governance (3) | **3 violated** |

Determinism is real and its defect is real — `signal_refs` is identity material
(`relation_candidate.py:539`) and is not sorted in `__post_init__` while
`observation_refs` and `evidence_refs` are (`relation_candidate.py:826-836`), so order-independence
survives only because `assembly.py:253` sorts by hand. It is anchored to **INV-12** and to the
Additional Constraints' "Idempotency" clause, and **not** to Principle VI, which is
Process-Centric. See `repair/A1-constitution-investigation.md` §D1.

**Re-check after Phase 1 design** has three conditions, not one: (i) the `PredicateSignature` in
the data model keeps exactly two identity terms (structural signature + participant identity) and
does not reintroduce a surface-dependent term; (ii) `relation_candidate.py::__post_init__` sorts
`signal_refs` the way it already sorts `observation_refs` and `evidence_refs`; and (iii) every
constitutional citation in the changed files names the correct numeral (FR-113).
```

**3 — line 155: the "THE production seam" annotation.** This is where FR-100's constitutional
violation is written into the structure listing.

OLD (`plan.md:155`):
```text
│   │   │   ├── capture_interpretation.py# THE production seam (FR-100)
```
NEW:
```text
│   │   │   ├── capture_interpretation.py# an activity of the investigation workflow, not a user entry point (FR-101)
```

**4 — lines 158 and 162: the two dead-code annotations.**

OLD (`plan.md:158`):
```text
│   │   │   ├── layer0_pipeline.py       # InterpretHook seam, unwired
```
NEW:
```text
│   │   │   ├── layer0_pipeline.py       # DELETED (FR-112); the InterpretHook/FabricHook/SearchHook/LakeHook protocols are retained on the investigation path
```

OLD (`plan.md:162`):
```text
│   │   │   ├── investigation.py         # unregistered, calls 2 non-existent activities
```
NEW:
```text
│   │   │   ├── investigation_lifecycle.py# NEW — the Principle VI entry point (FR-101…FR-104, ADR-0025); the 291-line investigation.py is DELETED (FR-112)
```

**5 — lines 66–69: the Constraints paragraph, which cites the constitution nowhere.**

OLD (`plan.md:66-69`):
```markdown
**Constraints**: determinism under replay (content-addressed ids re-derived, never trusted);
tenant isolation; lossless persistence (a digest may identify data but must never be the only
copy); raw predicate surface is evidence, never logical identity; no `ENT-`/`RES-` literals in
producer code; no `TYPE_CHECKING` except in type positions.
```

NEW:
```markdown
**Constraints**, each with its clause: **determinism under replay** (content-addressed ids
re-derived, never trusted) — *unnumbered*; anchored to INV-12 and to the Additional Constraints'
"Idempotency" clause, and **not** to Principle VI, which is Process-Centric. **tenant isolation** —
constitution **VII**; *not* IV, which is "No Single Store / Graph / Score". **lossless
persistence** (a digest may identify data but must never be the only copy) — Principles **I** and
**III**. **raw predicate surface is evidence, never logical identity** — Principle **II**, `input.md`
§19. **no `ENT-`/`RES-` literals in producer code** — Principle **V**, no domain type leaking into a
producer. **no `TYPE_CHECKING` except in type positions** — house rule. **the Investigation is the
only production entry point** — Principle **VI**, and the constraint this plan omitted entirely.
```

**6 — lines 202–205: Complexity Tracking's false opening sentence.**

OLD (`plan.md:202-205`):
```markdown
> **Fill ONLY if Constitution Check has violations that must be justified**

No constitutional violations are being accepted. Two items are recorded because they look like
violations and are not:
```

NEW:
```markdown
> **Fill ONLY if Constitution Check has violations that must be justified**

**Correction (2026-09-27).** The previous text here read "No constitutional violations are being
accepted." That was false, and false in the way that mattered: it is the sentence that would have
surfaced K1. The corrected gate above records four `violated` Core Principles, two `violated`
Invariants, one `violated` baseline clause, four `violated` Additional Constraints and three
`violated` Governance clauses. No `violated` row is *accepted* — each is closed by a named
requirement: FR-101…FR-104 (VI), FR-109 (II), FR-097 + FR-105 (III/INV-12), FR-106 and FR-111
(VII), FR-107 and FR-108 (Governance), FR-110 and FR-113 (the remainder). Two items are recorded
below because they look like violations and are not:
```

**7 — line 216: the risk row that treats FR-100 as sufficient.** The plan knows FR-100 is a wiring
requirement; it does not know FR-100 wires the wrong subject.

OLD (`plan.md:216`):
```markdown
| "Complete" could be claimed on a test-only harness | The 019 lifecycle has **no production caller**; `ExecutionRequest.producers` is never assigned; `lexical_signals` has never run | FR-100 makes the live `interpret_warc_capture` seam mandatory, and FR-084 forbids completion claims that rest on the corpus harness |
```

NEW:
```markdown
| "Complete" could be claimed on a test-only harness | The 019 lifecycle has **no production caller**; `ExecutionRequest.producers` is never assigned; `lexical_signals` has never run | FR-100 makes the live `interpret_warc_capture` seam mandatory, and FR-084 forbids completion claims that rest on the corpus harness |
| FR-100 wires an entry point that is not constitutional | `interpret_warc_capture` is real and is the right seam, but `entity_pipeline.py:38` reaches it from a function with no `investigation_id`, and Principle VI names an Investigation as the subject | FR-101 nests `interpret_warc_capture` inside `InvestigationWorkflow` and makes that workflow the only production entry point; FR-103 test-enforces registration; FR-100 is **superseded in part** for the entry-point question. ADR-0025 records the decision. FR-100 alone is insufficient |
| Registration has been claimed repeatedly and was false every time | `InvestigationWorkflow`, `SqlRelationClaimStore`, `RebuildableGraphStore`, `GraphProjectionBridge`, `InterpretationPipeline` and `Neo4jGraphStore` are all present and unwired; `spec.md:796-810` measures all six | FR-103's `test_investigation_workflow_and_all_activities_are_registered` reads the worker's own `workflows=` / `activities=` lists. A claim of availability that no test reads is not a claim |
| Twenty-six constitutional citations name the wrong numeral | Tenancy-as-IV at 20 sites (`protocol.py:299` is the origin) and determinism-as-VI at 6 sites; one is the constitution test suite's own filename | FR-113 test-enforces the correct numeral everywhere, and renames `test_iv_vi_tenancy_and_determinism.py`. A gate that cites the wrong clause is not a gate |
```

### 7.2 `spec.md`

**8 — lines 16–20: the inverted authority blockquote.** Replace with the D2.3 block.

OLD (`spec.md:16-20`):
```markdown
> **The complete, unabridged user brief is `input.md` in this directory (3411 lines, all
> 115 sections, reproduced verbatim).** This document is the engineering reading of it. Where
> this document appears to compress or interpret something, `input.md` governs — in
> particular §0 (working mode), §45 (no majority vote), §51–56 (projection is a
> projection), §72–75 (structural prohibitions) and §110 (development order).
```

NEW: the D2.3 block. The `(3411 lines, all 115 sections` figure is also wrong —
`phase0-results.md:139` (D10) measured `input.md` at **4898 lines** — so the count is corrected in
the same edit rather than left standing inside a sentence whose authority is being reversed.

**9 — FR-100 (`spec.md:781-789`): the seam is right, the subject is wrong.** The second half is
kept verbatim because it is correct and specific; the first half is annotated as superseded.

OLD (`spec.md:781-789`):
```markdown
- **FR-100**: The semantic path MUST be wired into the live production path, not only into the
  corpus harness. The seam is already built: `POST /api/v1/entities` →
  `services/entity_pipeline.py::run_live_entity_pipeline` / `workflows/temporal_materialization.py::reconcile_and_publish`
  → `services/capture_interpretation.py::interpret_warc_capture`, which both existing
  production branches already funnel through. That function currently runs only the 007-era
  `RelationExtractor`; it MUST additionally run the 019 producers, assembly, admission and
  projection. `ExecutionRequest.producers` — declared, never assigned by anyone — MUST be
  populated with the real producers, which is what makes `run_producer` iterate at all
  (`lexical_signals` has never been called by anything in the repository). (§101, §108, §114)
```

NEW:
```markdown
- **FR-100**: The semantic path MUST be wired into the live production path, not only into the
  corpus harness. The seam is already built: `POST /api/v1/entities` →
  `services/entity_pipeline.py::run_live_entity_pipeline` / `workflows/temporal_materialization.py::reconcile_and_publish`
  → `services/capture_interpretation.py::interpret_warc_capture`, which both existing
  production branches already funnel through. That function currently runs only the 007-era
  `RelationExtractor`; it MUST additionally run the 019 producers, assembly, admission and
  projection. `ExecutionRequest.producers` — declared, never assigned by anyone — MUST be
  populated with the real producers, which is what makes `run_producer` iterate at all
  (`lexical_signals` has never been called by anything in the repository). (§101, §108, §114)
  **Superseded in part by FR-101** for the entry-point question: `run_live_entity_pipeline`
  (`services/entity_pipeline.py:38`) has no `investigation_id` parameter, so promoting it to *the*
  production seam would wire the substrate to a non-constitutional subject — user → extractor →
  graph, with no investigation and no policy gate. The interpretation work FR-100 requires
  remains required; it is reached **through** `InvestigationWorkflow` rather than around it.
```

**10 — insert FR-101…FR-113 after FR-100 and before `### Production reachability, as measured`**
(`spec.md:791`). The verbatim text is in D6 above. The insertion point is exact: after the closing
`**` of FR-100 at line 789, before the blank line and the heading at line 791.

**11 — the reachability table (`spec.md:796-810`): three rows are stale or incomplete, and four
measured facts are missing.** One row must also gain a second line for a defect the brief did not
name.

OLD (`spec.md:808-810`):
```markdown
| `services/layer0_pipeline.py::Layer0Pipeline` + its `InterpretHook` seam | **none** — tests only | The intended binding point for real interpretation is unwired |
| `workflows/investigation.py` (`InvestigationWorkflow`, `RecrawlWorkflow`) | **unregistered**; calls two activities that exist nowhere | Dead workflow surface |
| CI (`.github/`) | **does not exist** | Nothing enforces the gate; `docs/quickstart-validation.md` (2026-09-17) is the only recorded baseline and predates 016–021 |
```

NEW:
```markdown
| `services/layer0_pipeline.py::Layer0Pipeline` + its `InterpretHook` seam | **none** — tests only | A second constitution-shaped entry point with no Investigation — `seed()`'s `investigation_id` is `""` (`layer0_pipeline.py:301`). Deleted by FR-112; the four hook `Protocol`s are retained on the investigation path |
| `workflows/investigation.py` (`InvestigationWorkflow`, `RecrawlWorkflow`) | **unregistered**; calls two activities that exist nowhere; `workflow.signal(InvestigationWorkflow, …)` at `:286` cannot address a target | Dead workflow surface, and unrunnable as written. Deleted by FR-112; replaced by a new, minimal `InvestigationWorkflow` in `workflows/investigation_lifecycle.py` (FR-101…FR-104, ADR-0025) |
| CI (`.github/`) | **does not exist** | Nothing enforces the gate. Governance requires "Compliance is verified on every PR/review"; FR-108 requires either CI or a dated, named attestation, and forbids "verified" for any check that was not run |
| `shared/events/dlq.py::QuarantineStore.purge` | `api/routes/quarantine.py:64` | `POST /dlq/{record_id}/re-evaluate` deletes the record it just re-evaluated, against "rejected candidates are never auto-deleted". FR-110 |
| `control-plane/services/audit.py::AuditLog` | **none** — tests only; `db/schema.py:596` `AuditLog(Base)` has no writer | Principle VII makes audit logs Mandatory and the durable table already exists. FR-111 |
| `control-plane/services/acquisition_loop.py::AcquisitionLoop` | `layer0_pipeline.py:44` only, itself unwired | `follow_redirects=True` with no egress policy and no DNS-rebinding protection. Must not be registered: FR-112 |
| `control-plane/services/dispatcher.py::Dispatcher` | **none** — `bench/collection/bench_collection.py:44` imports a *different* `dispatcher.scheduler.Dispatcher` from `apps/acquisition/` | The only in-repo policy/budget gate, and Principle VI names budget/freshness. Kept and wired, with its fabricated score vector corrected: FR-106, ADR-0027 |
| `shared/domain/evidence_lineage.py` `SIGNAL` hop | **does not exist** — `HopKind` has no `SIGNAL` member | SC-013's `edge → claim → candidate → signals → observations → source` is unreachable in **both** directions. FR-109, ADR-0026 |
```

**12 — INV-005 (`spec.md:371-372`) vs SC-013 (`spec.md:897-898`): the self-contradiction.** Both are
amended rather than one being deleted.

OLD (`spec.md:371-372`):
```markdown
- **INV-005**: Evidence lineage and derivation lineage stay separate. A candidate is
  derivation, never evidence. (§68, §69)
```

NEW:
```markdown
- **INV-005**: Evidence lineage and derivation lineage stay separate. A candidate is
  derivation, never evidence. A candidate is nonetheless **resolvable from** any warrant path, so
  that a projected edge can name the candidate that produced it without a candidate becoming a
  link in `EVIDENCE_BACKWARD_CHAIN`. Resolution is a second step, not a hop; the exclusion at
  `evidence_lineage.py:75-80` and its argument stand unchanged. (§68, §69; ADR-0026, FR-109)
```

OLD (`spec.md:897-898`):
```markdown
- **SC-013**: For every projected edge, the round trip `edge → claim → candidate → signals
  → observations → source` and back reaches every edge that source fed.
```

NEW:
```markdown
- **SC-013**: For every projected edge, the round trip `edge → claim → candidate → signals
  → observations → source` and back reaches every edge that source fed. **Achievable only after
  FR-109**: `HopKind` has no `SIGNAL` member today, so the `signals` hop is unreachable in either
  direction, and the `candidate` hop is reachable only by resolution (INV-005, ADR-0026).
```

**13 — `spec.md:53` and `spec.md:67`, two defect rows whose consequences change under this repair.**

OLD (`spec.md:53`):
```markdown
| `SourceTemporalObservation` is reachable only through a helper no production path calls | `acquisition/stream.py::capture_with_observations` | §61 |
```

NEW:
```markdown
| `SourceTemporalObservation` is reachable only through a helper no production path calls | `acquisition/stream.py::capture_with_observations` | §61. The replacement is the `investigation.acquire` activity, not a direct call: FR-101 |
```

OLD (`spec.md:67`):
```markdown
| The whole `semantic_path` lifecycle has no production caller - `run_until`/`run_golden_path` are reached only from the corpus harness and tests | `semantic_path/execution.py` | Nothing today connects acquisition → producer → graph in production, so "production code" claims must be checked, not assumed |
```

NEW:
```markdown
| The whole `semantic_path` lifecycle has no production caller - `run_until`/`run_golden_path` are reached only from the corpus harness and tests | `semantic_path/execution.py` | Nothing today connects acquisition → producer → graph in production, so "production code" claims must be checked, not assumed. The connection is made by `InvestigationWorkflow` stages 3–8, not by calling `run_until` (FR-104) |
```

### 7.3 Files this job does not edit, and why

| File | Why not |
|---|---|
| `data-model.md` | Its N5 synonym table is forbidden by ADR-0028 and must be rewritten — but that is the identity subsystem's file, and A2 owns it. Recorded, not edited. |
| `tasks.md` | `T065` carries the VI-determinism mis-cite (D-6) and T068 relies on FR-100 being sufficient. Both are recorded; the task graph is another agent's. |
| `research.md` | R-007 Q1 (normalisation rule set) becomes load-bearing under ADR-0028, but the research file is not this job's. |
| `checklists/requirements.md` | Must gain 13 new FR rows (FR-101…FR-113) and, per `phase0-results.md:133` (D5), an FR column that it does not currently have. Recorded. |
| `phase0-results.md` | The review being answered. Not edited. |
| `apps/**` | Read-only under the job's hard rules. Every code change implied above is expressed as an FR, not applied. |

---

## Summary of what this repair asserts

1. **The gate must be replaced, not extended.** Its coverage of the 7 Core Principles is 0 of 7,
   and 2 of its 4 numbered rows cite the wrong clause. Two of its verdicts are preserved and named
   as preserved; one is downgraded.
2. **The supersession rule is inverted in two files** and must be replaced with an ordered authority
   list plus an operational conflict rule, evaluated on at least one case where the constitution
   and the brief **disagree** — §20/INV-3 for agreement, Principle VI for disagreement.
3. **Principle VI is violated, not merely unstated**, and the fix is a new minimal registered
   `InvestigationWorkflow` with eight named activities, named idempotency keys, and a
   `reconcile_and_publish` delegation rather than a second implementation.
4. **The dead investigation code is a liability, not a leftover**: 291 unregistered lines, two
   non-existent activities, one signal call that cannot address a target, and a second competing
   lifecycle. Four of the five named services are deleted, kept-and-wired, or kept with their
   Protocols, each with a stated reason.
5. **Four ADRs, not one**, because Governance names four separate decisions in what this feature
   is doing, and a single document covering four decisions would repeat the gate's own error.
6. **Thirteen new requirements**, FR-101…FR-113, each independently testable and each naming its
   test method, plus a rejection record for the FR I chose not to write.

**Not claimed.** Nothing here is implemented. There is no CI, so none of these tests exists yet.
Per `constitution.md:73` and FR-084, the honest status of this document is `implemented` for the
repair specification and `deferred` for every code change it describes.




