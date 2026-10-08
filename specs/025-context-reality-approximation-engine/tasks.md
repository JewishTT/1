# Tasks — Context & Dialectical Reality Approximation Engine (025) **v2**

**Feature**: `025-context-reality-approximation-engine` | **Date**: 2026-10-04
**Spec**: [spec.md](spec.md) · **Plan**: [plan.md](plan.md) · **Baseline v2**: [input.md](input.md) · **Decisions**: [decisions.md](decisions.md)

154 задачи извлечены из §56 baseline v2. Критический путь — §57 v2, включая
**Wave 2S vertical slice** после Persistence и до Locality.

## Tag legend (research R2)

| Tag | Meaning |
|---|---|
| `NEW` | Не существует. Строить. |
| `EXTEND` | Существует в 024/платформе. Только аддитивно. |
| `REUSE` | Существует и уже удовлетворяет. Потреблять, не менять. |

## Критический путь (§57 v2)

```text
Wave 0 → A → B → 2S → C → D → E → G → F → H → I → J → K → L → M → N(+O вплетается)
```

---

## Wave 0 — Contract freeze (GATE)

12 ADR, не 7. Выход: ни одного противоречия с 024 в терминах и жизненных циклах;
цели §47.4 ратифицированы.

| ADR | Deliverable | Статус |
|---|---|---|
| ADR-025-01 | Context Engine placement | **DONE** — ADR-0028 |
| ADR-025-02 | Epistemic algebra (Belnap ops, truth vs score) | OPEN |
| ADR-025-03 | Revision/replay contract (determinism classes, sequencer, batches, manifests) | OPEN |
| ADR-025-04 | Sheaf-inspired locality boundary (pair+triple, honest terminology) | OPEN |
| ADR-025-05 | Hypothesis lifecycle and hypothesis space (H_OTHER, trend vs status) | OPEN |
| ADR-025-06 | Reasoning operator contract (numeric modes, seeds, cache keys) | OPEN |
| ADR-025-07 | Global search completeness semantics | OPEN |
| ADR-025-08 | Temporal algebra (13 Allen, disjunctive sets) | OPEN |
| ADR-025-09 | Evidence independence and coverage-qualified absence | OPEN |
| ADR-025-10 | Ranking policy and ReasoningProfile (no multiplicative utility) | OPEN |
| ADR-025-11 | Branches, scenarios, analyst-in-the-loop | OPEN |
| ADR-025-12 | Retention, erasure and permissible-inference policy | OPEN |

**R1 (config-scope)** — tool-конфигурация каждого пакета проверяется из корня репо.
**T025-154** закрывает ADR-025-08…12.

---

## Phase A — Shared domain kernel

**Exit gate**: Wave 1 — core objects exist; canonicalization (incl. numeric modes) property tests pass; truth algebra truth tables + lattice laws; >=10 corpus cases

**v2 additions**: T130 T133 T135 T136 T149 + corpus seed

| Task | Описание | Tag |
|---|---|---|
| `T025-001` | ContextCell model | `NEW` |
| `T025-002` | ContextOverlap model (pair/triple) | `NEW` |
| `T025-003` | RestrictionMap model | `NEW` |
| `T025-004` | CompatibilityAssessment model | `NEW` |
| `T025-005` | GluingResult model | `NEW` |
| `T025-006` | StateVariable model | `NEW` |
| `T025-007` | StateEstimate model | `NEW` |
| `T025-008` | Hypothesis + logical/revision ids + status/trend | `NEW` |
| `T025-009` | Assumption model | `NEW` |
| `T025-010` | DialecticalPair model | `NEW` |
| `T025-011` | Prediction model | `NEW` |
| `T025-012` | DiscriminatingTest model | `NEW` |
| `T025-013` | Contradiction model | `NEW` |
| `T025-014` | Obstruction model | `NEW` |
| `T025-015` | Regime model | `NEW` |
| `T025-016` | TransitionWindow model | `NEW` |
| `T025-017` | Completeness/saturation models | `NEW` |
| `T025-018` | Compute-budget model | `NEW` |
| `T025-019` | Deterministic canonicalization utilities | `NEW` |
| `T025-020` | Shared TruthState algebra (all five operations) | `NEW` |

## Phase B — Persistence

**Exit gate**: Wave 2 — restart preserves state; append-only enforced; historical lookup; sequencer + optimistic concurrency; artifact store + manifests

**v2 additions**: T137 T138

| Task | Описание | Tag |
|---|---|---|
| `T025-021` | Context cell storage migrations | `NEW` |
| `T025-022` | Overlap/compatibility migrations | `NEW` |
| `T025-023` | Gluing/obstruction migrations | `NEW` |
| `T025-024` | State estimate migrations | `NEW` |
| `T025-025` | Hypotheses and revisions migrations | `NEW` |
| `T025-026` | Assumptions/predictions/tests migrations | `NEW` |
| `T025-027` | Contradiction migrations | `NEW` |
| `T025-028` | Regime/transition migrations | `NEW` |
| `T025-029` | Reasoning-run migrations | `NEW` |
| `T025-030` | Tenant-scoped indexes | `NEW` |
| `T025-031` | Revision uniqueness guards `(context, branch, revision)` | `EXTEND` |
| `T025-032` | Append-only write guards | `EXTEND` |
| `T025-033` | Foreign-key integrity checks | `EXTEND` |

## Phase 2S — Vertical slice (Slice-0)

**Exit gate**: Wave 2S — Slice-0 green in dev-lite and dev-full with replay of every intermediate artifact

**v2 additions**: после B

| Task | Описание | Tag |
|---|---|---|
| `T025-152` | Slice-0 end-to-end scenario | `NEW` |

## Phase C — Compatibility / locality

**Exit gate**: Wave 3 — bounded overlaps; conflicts survive gluing; obstructions queryable; triple coherence; GLUED never with unchecked triples

**v2 additions**: T141

| Task | Описание | Tag |
|---|---|---|
| `T025-034` | Bounded cell blocking (bucket overflow reporting) | `NEW` |
| `T025-035` | Scope intersection | `NEW` |
| `T025-036` | Restriction projection | `NEW` |
| `T025-037` | Pairwise compatibility operators | `NEW` |
| `T025-038` | Multi-cell compatibility aggregation | `NEW` |
| `T025-039` | Obstruction generation | `NEW` |
| `T025-040` | Gluing candidate construction | `NEW` |
| `T025-041` | Partial-gluing state | `NEW` |
| `T025-042` | Obligations from persistent obstructions | `NEW` |

## Phase D — State / dynamics

**Exit gate**: Wave 4 — worldline binding; late-event re-evaluation; regime != transition; full Allen algebra; ICP estimator with residuals

**v2 additions**: T140 T148

| Task | Описание | Tag |
|---|---|---|
| `T025-043` | State-variable registry | `NEW` |
| `T025-044` | Observation-model contract | `NEW` |
| `T025-045` | Deterministic baseline estimator (see T025-148) | `NEW` |
| `T025-046` | Residual tracking | `NEW` |
| `T025-047` | Temporal interval algebra (see T025-140) | `NEW` |
| `T025-048` | Window materialization | `EXTEND` |
| `T025-049` | Change-point operator interface | `NEW` |
| `T025-050` | Regime descriptor | `NEW` |
| `T025-051` | Regime-shift candidate | `NEW` |
| `T025-052` | Worldline snapshot integration | `EXTEND` |

## Phase E — Abduction

**Exit gate**: Wave 5 — multiple explanations coexist; pruning explainable; predictions generated; H_OTHER handled; material-difference reproducible

**v2 additions**: T143

| Task | Описание | Tag |
|---|---|---|
| `T025-053` | Hypothesis canonicalization | `NEW` |
| `T025-054` | Bounded abductive search with auditable pruning | `NEW` |
| `T025-055` | Explanation materialization | `NEW` |
| `T025-056` | Support/refutation ledger | `NEW` |
| `T025-057` | Complexity scoring | `NEW` |
| `T025-058` | Assumption penalties | `NEW` |
| `T025-059` | Diversity-preserving top-k | `NEW` |
| `T025-060` | Prediction generation | `NEW` |
| `T025-061` | Discriminating-test generation | `NEW` |

## Phase G — Epistemic / contradictions

**Exit gate**: RELEASE GATE — truth lattice laws; BOTH always implies Contradiction; no cross-kind ranking

**v2 additions**: T131 T132

| Task | Описание | Tag |
|---|---|---|
| `T025-067` | Paraconsistent truth-state integration | `NEW` |
| `T025-068` | Contradiction detection (BOTH ⇒ Contradiction) | `NEW` |
| `T025-069` | Contradiction independence assessment (via dependency groups) | `NEW` |
| `T025-070` | Persistent contradiction lifecycle | `NEW` |
| `T025-071` | Contradiction → obligation generation | `NEW` |

## Phase F — Dialectics

**Exit gate**: Wave 6 — counter-hypothesis generation; differential tests; inconclusive stays open; parity audit

**v2 additions**: T143

| Task | Описание | Tag |
|---|---|---|
| `T025-062` | Dialectical pairing | `NEW` |
| `T025-063` | Counter-hypothesis generators | `NEW` |
| `T025-064` | Shared-premise extraction | `NEW` |
| `T025-065` | Differential-prediction calculation | `NEW` |
| `T025-066` | Dialectical revision events | `NEW` |

## Phase H — Information gain / frontier

**Exit gate**: Wave 7 — obligation->action->task; ranking tier-respecting; prediction outcomes feed hypotheses; saturation/closure durable

**v2 additions**: T134 T139

| Task | Описание | Tag |
|---|---|---|
| `T025-072` | Information-gain operator contract (tiers) | `NEW` |
| `T025-073` | Hypothesis discrimination matrix | `NEW` |
| `T025-074` | Action utility decomposition (no multiplicative form) | `NEW` |
| `T025-075` | Frontier ranking (profile modes) | `EXTEND` |
| `T025-076` | Action memory | `REUSE` |
| `T025-077` | Saturation state | `EXTEND` |
| `T025-078` | Termination report | `EXTEND` |
| `T025-079` | Reopen-on-contradiction | `EXTEND` |

## Phase I — Science integration

**Exit gate**: Wave 8 — TDA bound to snapshot; causal staged; calibration durable from outcome cohorts

**v2 additions**: T083 cohort

| Task | Описание | Tag |
|---|---|---|
| `T025-080` | Evaluation anchored to worldline snapshots | `EXTEND` |
| `T025-081` | TDA feature series | `REUSE` |
| `T025-082` | Change-point analysis | `NEW` |
| `T025-083` | Calibration results (cohorts from PredictionOutcome) | `NEW` |
| `T025-084` | Causal identification/estimation/refutation | `NEW` |
| `T025-085` | Null-model outputs | `NEW` |
| `T025-086` | Method/dependency fingerprints | `NEW` |

## Phase J — Operator registry

**Exit gate**: Wave 8b — registry; validation; resource metadata; donor adapters; selection profiles; tenant-keyed cache

**v2 additions**: T147

| Task | Описание | Tag |
|---|---|---|
| `T025-087` | Registry contract | `NEW` |
| `T025-088` | Operator compatibility validation | `NEW` |
| `T025-089` | Resource metadata | `NEW` |
| `T025-090` | Operator provenance | `NEW` |
| `T025-091` | Donor adapters | `NEW` |
| `T025-092` | Deterministic selection profile | `NEW` |
| `T025-093` | Adaptive selection profile | `NEW` |

## Phase K — Query compiler

**Exit gate**: Wave 9 — structured path works; NL adapter equivalent AST; completeness mode explicit; inference policy enforced

**v2 additions**: T146

| Task | Описание | Tag |
|---|---|---|
| `T025-094` | Query intent AST | `NEW` |
| `T025-095` | Deterministic structured grammar | `NEW` |
| `T025-096` | Optional LLM parser adapter (recorded-proposal replay) | `NEW` |
| `T025-097` | Semantic binding | `NEW` |
| `T025-098` | Constraint → planner compilation | `NEW` |
| `T025-099` | Completeness-mode compilation | `NEW` |
| `T025-100` | Aggregation requirements | `NEW` |

## Phase L — Read models / API

**Exit gate**: Wave 9b — endpoints serve epistemic context, never a bare confident array; branch-aware

**v2 additions**: T142 T144

| Task | Описание | Tag |
|---|---|---|
| `T025-101` | Context state endpoint | `EXTEND` |
| `T025-102` | Revision endpoint (branch-aware) | `EXTEND` |
| `T025-103` | Hypothesis endpoint (spaces, predictions) | `NEW` |
| `T025-104` | Contradiction endpoint | `NEW` |
| `T025-105` | Dynamics endpoint | `NEW` |
| `T025-106` | Frontier endpoint | `EXTEND` |
| `T025-107` | Provenance endpoint | `EXTEND` |
| `T025-108` | Completeness endpoint/data shape | `NEW` |

## Phase M — UI

**Exit gate**: Wave 10 — state/hypothesis matrix (H_OTHER, n_eff)/analyst/branches inspectable; provenance clickable

| Task | Описание | Tag |
|---|---|---|
| `T025-109` | Workspace shell | `NEW` |
| `T025-110` | Hypothesis matrix (with H_OTHER, n_eff) | `NEW` |
| `T025-111` | Contradiction inspector | `NEW` |
| `T025-112` | Context-cell map (triple inconsistencies) | `NEW` |
| `T025-113` | Dynamics/regime view | `NEW` |
| `T025-114` | Evidence ladder | `NEW` |
| `T025-115` | Frontier panel | `NEW` |
| `T025-116` | Provenance/reasoning trace | `NEW` |
| `T025-117` | Completeness/saturation indicator | `NEW` |

## Phase N — Benchmarks hardening

**Exit gate**: Wave 11/12 — replay fixed-point; budgets enforced; no silent truncation; no cross-tenant leakage; §54 A-Q green

**v2 additions**: T145 T150 T151 T153

| Task | Описание | Tag |
|---|---|---|
| `T025-118` | Determinism corpus | `NEW` |
| `T025-119` | Locality corpus | `NEW` |
| `T025-120` | Abduction corpus | `NEW` |
| `T025-121` | Dialectical corpus | `NEW` |
| `T025-122` | Temporal corpus | `NEW` |
| `T025-123` | Dynamics corpus | `NEW` |
| `T025-124` | TDA corpus | `NEW` |
| `T025-125` | Causal corpus | `NEW` |
| `T025-126` | Information-gain corpus | `NEW` |
| `T025-127` | Global-query corpus | `NEW` |
| `T025-128` | Replay benchmark | `NEW` |
| `T025-129` | Resource-budget benchmark | `NEW` |

## Phase O — v2 additions

**Exit gate**: Каждая задача Phase O привязана к фазе из §57; здесь — полный перечень

**v2 additions**: T154 ADRs 08-12

| Task | Описание | Tag |
|---|---|---|
| `T025-130` | EvidenceDependencyGroup model and deterministic derivation from lineage | `NEW` |
| `T025-131` | Independence operator (class `INDEPENDENCE`) | `NEW` |
| `T025-132` | `n_eff` and group-based consumption in update rules and saturation | `NEW` |
| `T025-133` | HypothesisSpace model, exclusivity groups, `H_OTHER` mass handling | `NEW` |
| `T025-134` | PredictionOutcome model/ingestion; realized information gain | `NEW` |
| `T025-135` | CoverageQualifiedAbsence model and admissibility rule | `NEW` |
| `T025-136` | Numeric modes, quantization utilities, seed derivation | `NEW` |
| `T025-137` | Single sequencer, recorded batch boundaries, optimistic concurrency | `NEW` |
| `T025-138` | Content-addressed artifact store and revision manifests | `NEW` |
| `T025-139` | ReasoningProfile model; ranking modes; tier interleave; exploration quota | `NEW` |
| `T025-140` | 13-relation Allen algebra with disjunctive sets, converse/intersection/composition, bounded path consistency | `NEW` |
| `T025-141` | Triple-coherence check with `max_triples` and unchecked reporting | `NEW` |
| `T025-142` | Branch model and mainline-isolation guard | `NEW` |
| `T025-143` | Material-difference metric and steelman parity audit | `NEW` |
| `T025-144` | AnalystAssertion/AnalystDecision objects and endpoints | `NEW` |
| `T025-145` | Retention policy, crypto-shredding, legal hold, `REPLAY_DEGRADED` | `NEW` |
| `T025-146` | Inference-policy gate (compiler + generators) | `NEW` |
| `T025-147` | Tenant-keyed operator cache | `NEW` |
| `T025-148` | Interval constraint propagation estimator | `NEW` |
| `T025-149` | Truth-lattice property-test suite (laws + truth tables) | `NEW` |
| `T025-150` | Quantitative-target benchmark harness (§47.4) | `NEW` |
| `T025-151` | Honesty-metric denominators (App. K) | `NEW` |
| `T025-152` | Slice-0 end-to-end scenario | `NEW` |
| `T025-153` | CI check: every FR maps to ≥1 task and ≥1 test (App. Y) | `NEW` |
| `T025-154` | ADR-025-08 … ADR-025-12 | `NEW` |

---

## Учёт

- `NEW`   : 138
- `EXTEND`: 14
- `REUSE` : 2
- ADR     : 12 (1 закрыт, 11 открыты)
- **Итого : 154 задач + 12 ADR**

## Правила исполнения

1. Ни одна фаза не начинается до зелёного гейта предыдущей. Гейт — релизный, не чекпоинт.
2. Оценка reuse **предшествует** оценке трудозатрат: T025-053…066 (`BeliefLandscapeFramework`), T025-049…052 (`cognitive_phase_transitions`, `ABa-KiTo`) — `AGENTS.md` §1.
3. Четырёхзначная истина (T025-020, T025-149) проверяется на каждом пути сериализации: storage → API → projection → UI. Release gate (R3).
4. Причинность (T025-084) хранит IDENTIFICATION/ESTIMATION/REFUTATION раздельно с первого коммита. Поля `causal_confidence` не существует (R4).
5. **T025-153** — CI-падалка: любое `FR-025-*` без задачи и без теста валит сборку.
6. Каждый отчёт о выполнении указывает: взято из 024 / взято из доноров / написано здесь.