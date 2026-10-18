# ADR-030-11 — Retention classes are distinct, erasure is physical, lineage survives as tombstones

- **Status**: Proposed
- **Date**: 2026-10-17
- **Feature**: `030-global-platform-upgrade`
- **Implements**: T026 ("fill from T010")
- **Cites**: FR-096, Constitution P1, P10, P14, ADR-0039, ADR-0002
- **BLOCKED ON**: T010, which has not run — see `## Open`

## Context

Two constraints collide, and ADR-0039 named the collision precisely.

**Append-only vs erasure.** The epistemic design depends on history being immutable: contradictions
persist, revisions are superseded, replay reproduces intermediate state. Legal and privacy obligations
require the opposite — some payloads must stop existing. ADR-0039 §Context states it: *"Those cannot
both be satisfied by deleting rows, because deleting a row that a revision manifest references breaks
integrity, and deleting the manifest breaks replay."*

**Outbound control vs inference control.** ADR-0039 §Context is equally pointed: *"§49.2 already forbids
the engine from sending messages or executing payloads. That is the wrong half. An engine that cannot
send anything can still **conclude** that a named natural person controls an address, and that
conclusion propagates through every downstream surface regardless of network controls."*

`research.md §2.12` adopted the principle and deferred the detail: *"the* policy *is a deliverable, not
a constant. Raw objects, derived artifacts, decision records and audit entries have **different**
retention classes."* It also named the blocker: *"`apps/shared/isolation.py` exists **[MEASURED]**; a
policy file must be located in WP-0 before this decision can be finalised."* That is U-06
(`research.md §8`): *"Where is the retention/erasure policy?"* — *"the policy document was not
located."* T010 is the task. It has not run: `current-state-audit.md` records T010 as `[ ]`.

### What is measured, and it changes the framing

T010 asks where the retention/erasure policy lives. Measuring for this ADR produced a sharper answer
than the question anticipated.

**[MEASURED] `apps/shared/isolation.py` contains no retention logic.** Its docstring (`:1-6`) scopes
it entirely to tenancy: *"Tenant isolation hardening (T061, FR-029, US3). Deterministic per-tenant
scoping across layered backends so two tenants can never share a partition, index alias, object prefix,
graph namespace, or budget scope."* It declares `_slug()` (`:14`), `TenantIsolation` (`:19`),
`TenantIsolationViolation` (`:59`) and `is_valid_tenant_id()` (`:63`). Every one of those is a
**scoping** concern. `plan.md §Project Structure` calls this file the *"existing isolation control —
retention policy target"*. It is the **target**, not the current location. Nothing in it retains or
erases anything.

**[MEASURED] No `RetentionPolicy`, `InferencePolicy`, legal-hold, or crypto-shredding construct exists
anywhere in `apps/`.** A search for `RetentionPolicy`, `InferencePolicy`, `legal_hold`, `CRYPTO_SHRED`
and `retention_period` across all Python source returns exactly one hit:
`apps/projection/search/mappings.py:133`, an OpenSearch index mapping — `"retention": {"retention_period":
"90 days"}`. That is a search-index TTL, not a data retention policy. It is the only retention duration
declared anywhere in the tree.

**[MEASURED] ADR-0039 is a design record, not an implementation.** It defines the `RetentionPolicy`
shape (`policy_id`, `data_classes`, `retention_periods`, `legal_hold`,
`erasure_method: CRYPTO_SHRED | TOMBSTONE`), the `InferencePolicy` shape, and ten numbered decisions
including gate-before-generation. Every one is normative and none has a corresponding type in code.

So the honest statement is: **the platform has a retention policy on paper and none in code.** That is
a more useful input to T010 than a file path, and it is why this ADR's status is Proposed rather than
Accepted.

## Decision

**D1 — Retention is policy-driven, and the policy is an artifact, not a constant.** No component
hard-codes a retention period. ADR-0039's `RetentionPolicy` (`policy_id`, `data_classes`,
`retention_periods`, `legal_hold`, `erasure_method`) is the shape.

**D2 — Four retention classes, deliberately different.** Raw objects, derived artifacts, decision
records and audit entries are retained on different terms. Collapsing them into one period is rejected
because each has a different failure mode if retained or destroyed wrongly.

**D3 — Append-only is logical; erasure is physical, by crypto-shredding.** Sensitive-class payloads are
encrypted under per-subject / per-class keys. Erasure deletes the key and leaves a tombstone
carrying `id`, `digest`, `class`, the erasure decision reference and a timestamp. **The digest
survives**, so integrity stays verifiable after the content is gone. This is ADR-0039 §1, adopted.

**D4 — Digests and manifests survive erasure.** Revisions, manifests and artifact digests remain.
Derived artifacts that depended on erased inputs are marked `INPUT_ERASED` and flagged for
recomputation **on a new revision** — never recomputed in place, which would mutate history
(ADR-0039 §2).

**D5 — Replay degrades explicitly, never silently.** After erasure, replay returns `REPLAY_DEGRADED`
with the list of unreadable inputs; everything else stays checkable. A replay that quietly skips
missing inputs and reports success is worse than one that fails (ADR-0039 §3; ADR-030-10 D8).

**D6 — Garbage collection respects retention and hold.** Only artifacts unreachable from any
non-expired revision and not under hold are removed (ADR-0039 §4).

**D7 — Legal hold is an accountable act, not a setting.** It blocks erasure and expiry for its scope,
and it is itself an auditable decision with a named principal (ADR-0039 §5).

**D8 — Retention applies identically to branches, caches and projections.** A cache or search index
that outlives a hold or an erasure is a copy the policy cannot reach. `apps/projection/search/`
is explicitly in scope: its 90-day mapping TTL (`:133`) is a **derived index**, and deleting an index
document must never delete the evidence it pointed to.

**D9 — Inference policy is a first-class versioned object, and the gate runs before generation.**
ADR-0039 §7–§8: the query compiler and the abduction/dialectics generators check the policy *before*
producing a hypothesis in a sensitive class; blocked cases return `POLICY_BLOCKED`. Checking at
publication time would let a sensitive hypothesis exist internally, enter caches and influence
neighbouring inferences.

**D10 — Permitted sensitive hypotheses remain hypotheses.** Labelled with evidence, assumptions and
false-positive caveats; never rendered as findings; always carrying the controls the policy requires
(ADR-0039 §9).

**D11 — No raw sensitive payload in any record.** FR-096: secrets and raw sensitive payloads MUST NOT
appear in logs, metrics, traces or decision records. Retention policy governs how long data lives; D11
governs where it may be written at all. A retention class does not create an exception to it.

**D12 — The policy lives in one place, and it is versioned.** T010 must locate or create it. Until it
does, `apps/shared/isolation.py` is **not** it and no component may treat it as such.

## Why not the alternatives

**A — One retention period for everything.** Rejected: it forces the shortest period on all classes
(destroys replay and audit depth) or the longest on all classes (retains personal data that should have
gone). `research.md §2.12`'s four-class split exists because a raw blob, a derived projection of it, a
decision that referenced it and an audit entry about that decision have genuinely different
justifications.

**B — Hard-delete rows on erasure.** Rejected: ADR-0039's opening argument. Deleting a row a revision
manifest references breaks integrity; deleting the manifest breaks replay. The platform would lose the
ability to verify that a replay happened, which is the property that makes replay worth having.

**C — Soft-delete / tombstone the row, keep the payload.** Rejected: a tombstone with the payload still
present is not erasure. It satisfies the appearance of the requirement and none of its purpose.

**D — Delete the derived projections and let lineage break.** Rejected: the redaction must be of
content, not of the fact that content existed. Losing lineage on erasure is what makes a derived claim
unauditable, and unauditable claims are exactly what this platform exists to eliminate.

**E — Enforce the inference policy at publication.** Rejected, explicitly, in ADR-0039 §8: *"Checking at
publication time would let the hypothesis exist internally, enter caches and influence neighbouring
inferences."* A policy that fires one step too late does not constrain the inference; it conceals it.

**F — Put retention in `apps/shared/isolation.py` because that is where T010 was pointed.** Rejected on
measurement: that file is tenant scoping (`:1-6`), and retention is a different concern with a different
lifecycle. Bolting a retention policy onto the isolation module would give one file two responsibilities
and would make the module's docstring false. T010 was pointed at the wrong file; this ADR records that
rather than acting on it.

**G — Adopt the OpenSearch 90-day TTL as *the* retention policy.** Rejected: `mappings.py:133` is an
index-document lifetime for one projection family. It says nothing about raw blobs, decision records or
audit entries, and enforcing it as policy would delete search documents that other projections and
replays still reference — a D8 violation by construction.

**H — Accept this ADR now and let T010 fill the location in.** Rejected for the Status field, adopted
for the content — the same split used in ADR-030-04 and ADR-030-07. The *policy* is fully specified by
ADR-0039 and FR-096; the *location* is not discoverable. Claiming the decision is in force while the
artifact it names does not exist would be the overstatement constitution P15 forbids.

## Consequences

**Positive**

- The hardest part — crypto-shredding so that append-only and erasure coexist — is decided, so
  implementation is mechanical once the policy artifact exists.
- D5 and D8 mean erasure is observable rather than silent, at the two places it is most likely to be
  quietly skipped (replay and search).
- D9 means a sensitive inference can be blocked *before* it contaminates neighbouring results, which is
  the difference between a policy and a disclaimer.

**Costs, accepted**

- Per-subject / per-class encryption keys are real operational complexity: key storage, key backup
  policy, and the question of what happens when a key store is itself unavailable.
- `REPLAY_DEGRADED` must be surfaced in the UI. A degraded replay that looks like a clean replay is
  worse than no replay (ADR-0039, Costs).
- D3–D8 require a per-class data inventory before they can be implemented, and that inventory is T010's
  or T009's, not this ADR's.

**Not changed**

- ADR-0039 stands in full; this ADR adopts it and adds FR-096 (D11) and the search-index case (D8).
- Constitution P1 (immutable evidence) is unchanged: erasure is a declared exception with a decision
  reference and a tombstone, not an ordinary operation. ADR-0039's *"Not changed"* section says the
  same: *"Evidence is never deleted by ordinary operation."*
- `apps/shared/isolation.py` is not modified by this ADR.

## Verification

- [ ] `RetentionPolicy` and `InferencePolicy` exist as typed, versioned artifacts with a single
      authoritative location.
- [ ] No component hard-codes a retention period; the OpenSearch mapping TTL
      (`apps/projection/search/mappings.py:133`) is a derived-index lifetime and is labelled as such.
- [ ] An erasure drill leaves the payload unreadable, the tombstone present, and the digest intact.
- [ ] Dependent artifacts are marked `INPUT_ERASED` and recomputed only on a new revision; the prior
      revision is unchanged.
- [ ] Legal hold blocks erasure for its scope and is recorded as a decision with a principal.
- [ ] Cache and search-index entries are removed under the same erasure and hold rules as storage.
- [ ] GC removes only unreachable, non-expired, non-held artifacts.
- [ ] Sensitive-class generation without required controls returns `POLICY_BLOCKED` **before** any
      hypothesis is written.
- [ ] A permitted sensitive hypothesis is labelled as a hypothesis everywhere it appears.
- [ ] No raw sensitive payload appears in any log, metric, trace or decision record (FR-096).

## Open

- **T010 must land before this ADR can be Accepted.** T010 is *"Identify retention/erasure policy in
  `current-state-audit.md §6`: locate it relative to `apps/shared/isolation.py`."*
  `current-state-audit.md` records T010 as `[ ]`, and its §5 table states §3–§6 are *"Not yet done."*
  The measurement performed while writing this ADR answers the question in part — the policy is **not in
  `apps/shared/isolation.py`** and is **not in code at all** — but the authoritative location, if one
  exists outside `apps/`, has not been established, and this ADR does not guess it.
- **U-06 is open.** `research.md §8`: *"Where is the retention/erasure policy? `apps/shared/isolation.py`
  exists; the policy document was not located."* The measurement narrows U-06 but does not close it.
- **No implementation exists.** `RetentionPolicy`, `InferencePolicy`, crypto-shredding, legal hold and
  the `POLICY_BLOCKED` gate are all ADR-0039 design records with no corresponding code. T126 owns
  migration/backfill tooling; the erasure drill in the verification list has no runner.