# ADR-030-08 — Only the deterministic core decides; the adaptive layer may reorder and is disableable

- **Status**: Accepted
- **Date**: 2026-10-17
- **Feature**: `030-global-platform-upgrade`
- **Implements**: T023
- **Cites**: FR-044, Constitution P8, P10, P11, ADR-0037
- **Recorded absence**: no LLM provider dependency exists in any workspace member — measured below

## Context

FR-044 is written to be permissive about adaptive components and absolute about their limits:

> An adaptive or learned layer MAY influence candidate generation and ranking, and MUST be disableable
> with a deterministic fallback and an explicit degraded-status signal; it MUST NOT redefine whether an
> obligation exists, silently satisfy one, or reclassify knowledge truth.
> — `spec.md:353-355`

The three prohibitions are the point. "MAY influence ranking" is a licence; "MUST NOT redefine whether
an obligation exists" is the boundary. A system that lets a learned component decide *whether the
question has been answered* has handed the loop's central judgement to something whose behaviour no
replay can reproduce and no audit can reconstruct.

**[MEASURED]** There is **no provider dependency in any workspace member.** A search of every member
`pyproject.toml` plus the root `pyproject.toml` and `bench/pyproject.toml` for `anthropic`, `openai`,
`litellm`, `instructor`, `tiktoken`, `cohere`, `ollama` returns **zero hits**. `research.md §1.2`
point 3 records the same and draws the consequence: *"The LLM-routing work package has **no substrate**
and must not be scheduled before an operator-evals contract exists."* `plan.md §What is explicitly not
scheduled` repeats it: *"**[MEASURED]** no provider dependency exists in any workspace member."*

So the question "who decides?" currently has a short answer: nobody model-based. The danger is not that
an adaptive layer overruns its boundary — it is that the boundary is written down and nothing enforces
it, so the first adaptive component lands into an undefined constraint.

**[MEASURED]** The separation is already expressed in the kernel, in the kernel's own module docstring.
`apps/control-plane/context_engine/engine.py:18-21`:

> *Constitutional core vs adaptive layer (FR-045): `DeterministicObligationGenerator` is the
> constitutional core and runs with no adaptive input at all. The adaptive layer only ever **ranks** —
> it can change priority, never whether an obligation exists or whether it is satisfied. That separation
> is what lets the engine be audited.*

And `engine.py:16`: *"One class holding all five would make every one of those changes a change to the
same file, and would make 'disable the adaptive layer' impossible to express."* The structural
precondition for disableability is therefore the same separation P8 requires.

**[MEASURED]** The five responsibilities are separate types at the measured lines: `ObligationGenerator`
(`:100`), `SatisfactionEvaluator` (`:185`), `ActionProposer` (`:264`), `DecisionRecorder` (`:345`),
`RevisionManager` (`:407`). And `engine.py:479` records that the core *"is never touched by the
adaptive layer."*

**[MEASURED]** There is a test. `apps/control-plane/tests/unit/test_context_engine.py:119` —
`test_the_constitutional_core_takes_no_adaptive_input()`, docstring: *"FR-045: the generator must be
correct with the adaptive layer absent."* So "disableable with a deterministic fallback" is already
pinned for the one place it matters today.

**[MEASURED]** An `adaptive` mode string does exist in the ingest path —
`test_context_engine.py:408` calls `e.ingest(c, [], event_ids=["e2"], mode="adaptive")` and `:410`
asserts `adaptive.mode == "adaptive"`. And there is an adaptive feedback plane at
`apps/feedback/feedback/` (`__init__.py:1` — *"Feedback plane: adaptive loop closing (T116-T118)"*;
`branch/finding.py:4` — *"adaptive UtilityScorer (utility = confidence-weighted expected gain)"*;
`branch/source.py:36` — *"Frontier policy for a source given its adaptive state"*). These are
heuristic and policy-driven, not model-driven — and they are exactly the kind of component that will
creep across the line if the line is not enforced.

## Decision

**D1 — Only the deterministic core decides.** `ObligationGenerator` decides whether an obligation
exists. `SatisfactionEvaluator` decides whether it is satisfied. `RevisionManager` decides revision
advance. `DecisionRecorder` decides what is recorded. No adaptive component participates in any of
these four judgements.

**D2 — The adaptive layer may reorder and nothing else.** Its permitted influence is priority and
ordering among candidates and actions. It may not create an obligation, close one, satisfy one, or
reclassify anything as known, true or absent. This is FR-044's list of prohibitions, restated as a
capability grant: reorder only.

**D3 — Every adaptive component is disableable, with a deterministic fallback and an explicit
degraded-status signal.** "Disableable" is a property with three parts, all required: the component can
be switched off; the deterministic path then runs and is correct on its own; and the run reports
`degraded` with the component named. Disabling is not an error path and not a silent downgrade to zero
scores.

**D4 — The degraded-status signal is part of the result, not a log line.** A caller must be able to see
that a component did not run. A run where the adaptive layer was disabled and nothing said so is a
violation.

**D5 — No adaptive component commits a resolution decision.** It may propose; the admission gate
decides (ADR-030-03 D4).

**D6 — An adaptive component never enters an identity-critical hash.** Constitution P10: canonical
serialization only. This keeps `deterministic=true` ⇒ `model_fingerprint=null` (contract 01,
`tasks.md` T035) achievable.

**D7 — The LLM routing vertical is not scheduled as a vertical.** No provider dependency exists
(measured). When one does, it arrives as: an operator-evals contract, then a deterministic-routing
baseline, then an optional provider profile behind a feature flag — in that order, and subject to D1–D6
unchanged. `research.md §2.8` records this as a deliberate narrowing of the source specification's WP10.

**D8 — The structural separation is maintained, not just the behavioural rule.** The five
responsibilities stay separate types. Merging them would make D3 inexpressible, which is why
`engine.py:16` treats it as an architectural cost rather than a style preference.

## Why not the alternatives

**A — Let the adaptive layer close obligations when it is confident.** Rejected: this is FR-044's
second prohibition verbatim. More importantly it is unreplayable — a confidence threshold applied at
run time cannot be re-derived at audit time without the model that produced it, and no such model
exists in this workspace.

**B — Gate the adaptive layer behind a flag and declare the boundary documented.** Rejected: a
documented boundary with no test is a convention. The existing `test_the_constitutional_core_takes_no_adaptive_input`
shows the standard: the prohibition is pinned by a test that fails if the core starts reading adaptive
input. Every D1/D2/D5 prohibition needs the same treatment.

**C — Schedule the LLM routing vertical now to get ahead of the curve.** Rejected on FR-110's logic:
*"a dependency in `pyproject.toml` is not an integration."* Adding a provider SDK to a project with no
provider substrate, no token accounting and no eval harness buys a work package and no evidence, and
puts a licence, a runtime and an operational burden on the dependency surface for nothing
(`research.md §7`).

**D — Collapse the five responsibilities into one engine class with hooks, for cohesion.** Rejected,
and `engine.py:15-16` already records why in the file itself: it would make every change a change to
one file and would make *"disable the adaptive layer"* impossible to express. D3 is not satisfiable
under that design.

**E — Let the adaptive layer reclassify knowledge truth to reduce noise.** Rejected: constitution P6/P15.
An epistemic state that a learned component can reclassify is not an epistemic state, and the audit
trail for a reclassification cannot be reconstructed.

**F — Treat the existing `apps/feedback/` adaptive scorer as a model-driven component and exclude it.**
Rejected: it is `confidence-weighted expected gain` over recorded state — heuristic, inspectable and
policy-driven. Excluding it would be a category error, and excluding it would also be dishonest about
where the real risk lies. The risk is a *model* appearing, not the current heuristic.

## Consequences

**Positive**

- D3 is already partially enforced and pinned: with the adaptive layer absent, the core is correct
  (`test_context_engine.py:119`). The prohibition is testable today, not aspirational.
- The kernel stays auditable, because the things that decide are the things with no adaptive input
  (`engine.py:479`).
- D7 freezes the dependency surface. No provider SDK, licence or operational burden until a substrate
  exists.

**Costs, accepted**

- The LLM-assisted capabilities the source specification imagines are not delivered by this feature.
  `plan.md §Complexity Tracking` records this as a deliberate, reversible narrowing: the design is
  preserved, the substrate is not fabricated.
- Every future adaptive component must ship a disable switch, a fallback and a degraded signal. That
  is real work per component, and it is the point.
- The feedback plane's adaptive scorer sits close to the D2 line. A heuristic that reorders is
  compliant; the same heuristic that closes a branch is not. The distinction needs to stay sharp, and
  the tests in Phase 10 (T167) are where it will be checked.

**Not changed**

- ADR-030-03 D4 stands: nothing commits a resolution decision from a score.
- ADR-0037 (ranking policy, no multiplicative utility) is unaffected.
- The five responsibilities in `engine.py` are untouched by this ADR.

## Verification

- [ ] `test_the_constitutional_core_takes_no_adaptive_input`
      (`apps/control-plane/tests/unit/test_context_engine.py:119`) passes unmodified.
- [ ] `ObligationGenerator` (`engine.py:100`) has no parameter, import or dependency by which adaptive
      state can reach it.
- [ ] `SatisfactionEvaluator` (`engine.py:185`) cannot be influenced by adaptive input.
- [ ] No adaptive component creates, closes or satisfies an obligation.
- [ ] Disabling every adaptive component leaves the deterministic path correct and the run reporting
      a degraded status naming the disabled component.
- [ ] A result marked `deterministic=true` carries `model_fingerprint=null`.
- [ ] No workspace member's `pyproject.toml` declares `anthropic`, `openai`, `litellm`, `instructor`,
      `tiktoken`, `cohere` or `ollama`.
- [ ] `apps/feedback/`'s adaptive scorer reorders and does not close branches or commit decisions.

## Open

- **No provider dependency exists, and this ADR does not change that.** Verified across every member
  manifest. Any future provider profile is D7's three-step sequence and is not scheduled here.
- **The degraded-status signal is not implemented.** D3's third clause has no carrier in the result
  types today; contract 01 (`tasks.md` T029) and T167 own it. This ADR fixes the requirement, not the
  field.
- **`mode="adaptive"` exists in the ingest path** (`test_context_engine.py:408`) with no recorded
  contract for what an adaptive ingest is permitted to change. The ADRs above say it is reorder-only;
  nothing yet enforces it. T029/T035 and the Phase 10 tests are where that gets pinned.