# ADR-0039 — Retention, erasure and permissible inference

**Status**: Accepted (Wave 0, ADR-025-12)
**Feature**: `025-context-reality-approximation-engine`
**Baseline**: v2 §39.3, §49.2, §49.3, §36.3, Appendix L, P.2

## Context

Two constraints that the platform has never had to satisfy together.

**Append-only vs erasure.** The whole epistemic design depends on history being immutable:
contradictions persist, revisions are superseded, replay reproduces intermediate state. Legal
and privacy obligations require the opposite — that some payloads stop existing. Those cannot
both be satisfied by deleting rows, because deleting a row that a revision manifest references
breaks integrity, and deleting the manifest breaks replay.

**Outbound control vs inference control.** §49.2 already forbids the engine from sending
messages or executing payloads. That is the wrong half. An engine that cannot send anything
can still *conclude* that a named natural person controls an address, and that conclusion
propagates through every downstream surface regardless of network controls. Control over
outbound actions does not constrain what is asserted.

## Decision

**1. Append-only is logical; erasure is physical, by crypto-shredding.**

```yaml
RetentionPolicy:
  policy_id: RET-...
  data_classes: {...}
  retention_periods: {...}
  legal_hold: bool/scope
  erasure_method: CRYPTO_SHRED | TOMBSTONE
```

Sensitive-class payloads are encrypted under per-subject / per-class keys. Erasure deletes the
key and leaves a tombstone: `id, digest, class, erasure decision ref, timestamp`. The digest
survives, so integrity stays verifiable.

**2. Digests and manifests survive erasure.** Revisions, manifests and artifact digests remain.
Derived artifacts that depended on erased inputs are marked `INPUT_ERASED` and flagged for
recomputation **on a new revision** — never recomputed in place, which would mutate history.

**3. Replay degrades explicitly.** After erasure, replay returns `REPLAY_DEGRADED` with the
list of unreadable inputs. Integrity of everything else remains checkable. Silent degradation
is forbidden: a replay that quietly skips missing inputs and reports success is worse than one
that fails.

**4. Garbage collection respects retention and hold.** Only artifacts unreachable from any
non-expired revision and not under hold are removed.

**5. Legal hold blocks erasure and expiry for its scope**, and holds are themselves auditable
decisions. A hold is not an administrative setting; it is an accountable act with a principal.

**6. Retention applies identically to branches and caches.** A cache that outlives a hold or an
erasure is a copy the policy cannot reach.

**7. Inference policy is a first-class, versioned object.**

```yaml
InferencePolicy:
  sensitive_inference_classes:
    - ATTRIBUTION_OF_CONTROL_TO_NATURAL_PERSON
    - LINKING_PSEUDONYMOUS_IDENTITIES
    - INFERRING_PROTECTED_ATTRIBUTES
    - BEHAVIOURAL_PROFILING_OF_INDIVIDUALS
  purpose_limitation: allowed objectives per context
  required_controls: [APPROVAL, MINIMUM_EVIDENCE_THRESHOLD, REVIEW_LABEL, RESTRICTED_VISIBILITY]
  disclosure: how such results are labelled and who may see them
```

**8. The gate runs before generation, not before publication.** The query compiler and the
abduction/dialectics generators check the policy **before** producing a hypothesis in a
sensitive class. Blocked cases return `POLICY_BLOCKED`. Checking at publication time would let
the hypothesis exist internally, enter caches and influence neighbouring inferences.

**9. Permitted sensitive hypotheses are always hypotheses** — labelled with their evidence,
their assumptions and false-positive caveats. They can never be rendered as findings, and they
carry the required controls from the policy.

**10. Governance chain unchanged.**

```text
Reasoning → ResearchAction → Approval/Policy → Task/Capability → Controlled execution → Observation
```

## Consequences

**Positive**

- History stays immutable while personal payloads can actually be destroyed.
- Replay integrity is preserved and its degradation is visible.
- The engine can be prevented from *asserting* sensitive attributions, not merely from acting
  on them.

**Costs, accepted**

- Per-subject encryption keys are real operational complexity.
- Sensitive-class hypotheses will be blocked more often than not, which is the intent.
- `REPLAY_DEGRADED` must be surfaced in the UI; a degraded replay is not a passing replay.

**Not changed**

- Evidence is never deleted by ordinary operation.
- The world substrate's own retention rules are untouched by this ADR.

## Verification

- [ ] Erasure drill: payload unreadable, tombstone present, digest intact, replay reports
      `REPLAY_DEGRADED` with the unreadable list.
- [ ] Non-erased artifacts remain byte-identical after an erasure drill.
- [ ] Dependent artifacts are marked `INPUT_ERASED` and recomputed only on a new revision;
      the prior revision is unchanged.
- [ ] Legal hold blocks erasure for its scope; the hold is recorded as a decision with a
      principal.
- [ ] Cache entries are removed by the same erasure and hold rules as storage.
- [ ] GC removes only unreachable, non-expired, non-held artifacts.
- [ ] Sensitive-class generation without the required controls returns `POLICY_BLOCKED`
      *before* any hypothesis is written.
- [ ] A permitted sensitive hypothesis is labelled as a hypothesis everywhere it appears.
- [ ] The wallet-cluster example (Appendix C) passes the policy gate or is blocked.