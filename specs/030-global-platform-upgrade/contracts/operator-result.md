# Contract 01 — `OperatorResult`

**Feature**: `030-global-platform-upgrade`
**Governs**: every parser, extractor, matcher, analytics runner, projection builder and donor adapter.
**Enforces**: FR-007, FR-047, FR-065, FR-100, FR-111.

---

## Purpose

One envelope for the result of anything that turns observations into derived artifacts. It exists so
that a result's **provenance, method, cost, uncertainty and failure state** travel with the result
everywhere — and so that a donor component has no path to canonical state that bypasses it.

---

## Shape

```text
OperatorResult
├── identity
│   ├── operator_id                     required
│   ├── operator_version                required
│   └── tenant_id                       required
│   ├── investigation_id                required
│   └── policy_fingerprint              required
├── inputs
│   ├── input_observation_ids[]         required, may be empty for pure-projection operators
│   ├── input_digests[]                 required, parallel to observation ids
│   └── semantic_profile_ref            required — which regime produced this
├── output
│   ├── output_kind                     required — OPEN vocabulary
│   ├── output_schema_version           required
│   ├── output_digest                   required when status = succeeded|partial
│   ├── artifact_refs[]                 required when status = succeeded|partial
│   └── evidence_refs[]                 EvidenceSpanRef — required when the output is derived
│                                       from raw content
├── method
│   ├── method_fingerprint              required
│   ├── parameters_fingerprint          required
│   ├── model_fingerprint               nullable — null for deterministic operators
│   ├── deterministic                   required bool
│   ├── replay_key                      required
│   └── replay_mode                     required: deterministic | result_replay
├── outcome
│   ├── status                          required — see contract 03
│   ├── error_code                      nullable, required when status ∈ {failed, blocked,
│   │                                   quarantined}
│   ├── warnings[]
│   ├── missingness[]                   explicit, not empty-by-default
│   └── uncertainty                     keyed map; may be empty, may be explicit-unknown
├── time
│   ├── started_at                      required
│   ├── completed_at                    nullable while running
│   └── source_times[]                  typed source-time references — NEVER folded into a
│                                       single datetime
└── cost
    └── cost                            vector — network_io, cpu, memory, model_tokens,
                                         latency_ms, storage_bytes, retries, expected_human
                                         review, licensing. A composite may be added by a
                                         versioned policy; the vector is the stored truth.
```

---

## Normative rules

### R1 — An empty output is never a status

`output_digest = null` with `artifact_refs = []` MUST NOT mean *any* of: success, no results,
unsupported, blocked, or error. Those are five different `status` values (contract 03).

> A parser that cannot process a format returns `status = unsupported`. It does not return a
> zero-length document with `status = succeeded`.

### R2 — Two replay modes, declared

| Mode | Meaning | Replay behaviour |
|---|---|---|
| `deterministic` | Pure function of fingerprinted inputs | Recompute; the output digest **must** match |
| `result_replay` | Model-hosted or otherwise non-deterministic | Preserve the exact returned result; state that recomputation is not possible |

`replay_key` is derived from tenant/scope, the logical input digest set, operator + version,
canonical parameters, model version, semantic profile and time scope where relevant.

**It does NOT include the wall-clock execution timestamp** unless that timestamp is semantically
part of the input.

> **[MEASURED]** The pattern this contract generalises already exists in the repository:
> `InvariantReducer.restore(stream, history=)` rebuilds at the recorded position rather than at 1,
> because the reducer advances its revision counter once per `reduce()` call. See contract 05 §5.

### R3 — Unknown is explicit

`uncertainty` and `missingness` are keyed maps that may be empty, but an **unestimated** value is
`null` with the key present — never `0.0`, never silently omitted. This is what separates
"measured as zero" from "not measured".

### R4 — Donors emit; the platform writes

An `OperatorResult` is the **only** way an operator's output enters the platform. The receiving
service performs the write. An adapter that writes canonical evidence, identity, investigation state
or a projection store directly is a contract violation (FR-111), regardless of licence or seniority.

### R5 — Idempotent consumption

Two deliveries of the same `replay_key` produce one semantic effect. Duplicate delivery MUST NOT
increment revisions, evidence independence, coverage, or cost-benefit learning (FR-065).

### R6 — Partial is a first-class outcome

`status = partial` MUST carry, in `missingness`: what was processed, what was not, the limit that
bound it, and whether the residual is resumable. A budget exhaustion is `partial`, never a success.

### R7 — Provenance completeness is declared, not assumed

`evidence_refs` MAY be empty only when `output_kind` genuinely has no source content (e.g. a pure
aggregation over already-derived features). In that case `missingness` MUST carry an explicit reason.
A consumer that cannot resolve a declared span MUST render the result as partial/unsupported, not
grounded (FR-005).

### R8 — Every operator declares its own envelope in the registry

`operator_id` maps to a registry entry carrying: capability set, cost model, resource limits,
concurrency, isolation class, egress destinations, credential scope, whether it executes active
content or loads models, failure/cleanup behaviour, licence metadata, and kill switch.

A registry lookup that cannot satisfy a required capability returns an explicit **capacity gap**
(contract 01 §CapacityGap), never a weaker substitute (CE-I13).

---

## CapacityGap

```text
CapacityGap
├── capability_required
├── capability_available          nullable
├── substitution_attempted        MUST be false
├── status                        unsupported | approximate
├── gap_reason                    required
├── owner
└── next_action                   executable
```

---

## Validation

| Check | On failure |
|---|---|
| `output_digest` present iff `status ∈ {succeeded, partial}` | reject |
| `error_code` present iff `status ∈ {failed, blocked, quarantined}` | reject |
| `completed_at ≥ started_at` when both present | reject |
| `deterministic = true` ⇒ `replay_mode = deterministic` and `model_fingerprint = null` | reject |
| `deterministic = false` ⇒ `replay_mode` declared explicitly | reject |
| `evidence_refs` non-empty when output derives from raw content | flag as ungrounded |
| Every `input_observation_ids[i]` has a matching `input_digests[i]` | reject |
| `tenant_id` present and non-empty | reject |
| Cost fields absent ⇒ present as `null`, not omitted | warn |

---

## Examples

**Parser succeeded, grounded**

```json
{
  "operator_id": "parser.pdf.layout",
  "operator_version": "1.4.2",
  "tenant_id": "t-acme",
  "investigation_id": "INV-7f3a",
  "policy_fingerprint": "sha256:9c1e…",
  "input_observation_ids": ["obs-91c4"],
  "input_digests": ["sha256:3d7b…"],
  "semantic_profile_ref": "semantic/standard/2",
  "output_kind": "document_layout",
  "output_schema_version": "1.2.0",
  "output_digest": "sha256:e81a…",
  "artifact_refs": ["art-layout-004"],
  "evidence_refs": [
    {
      "observation_ref": "obs-91c4",
      "blob_digest": "sha256:3d7b…",
      "selector": { "page_box": { "page": 1, "box": [72.0, 144.0, 540.0, 700.5], "coordinate_system": "pdf_points" } },
      "source_locator": { "uri": "https://example.org/report.pdf" },
      "selector_semantics_version": "page_box/1"
    }
  ],
  "method_fingerprint": "sha256:5aa0…",
  "parameters_fingerprint": "sha256:b71c…",
  "model_fingerprint": null,
  "deterministic": true,
  "replay_key": "sha256:44f2…",
  "replay_mode": "deterministic",
  "status": "succeeded",
  "error_code": null,
  "warnings": ["page 3 has no extractable text layer; OCR required"],
  "missingness": ["page 3 not extracted"],
  "uncertainty": { "segment_confidence": null },
  "started_at": "2026-10-14T09:12:03Z",
  "completed_at": "2026-10-14T09:12:07.412Z",
  "source_times": [
    { "kind": "source_published_at", "value": "2026-09-30T00:00:00Z", "precision": "day" }
  ],
  "cost": { "cpu_seconds": 4.1, "memory_bytes": 812_000_000, "network_io_bytes": 0, "model_tokens": 0, "latency_ms": 4412, "storage_bytes": 2_400_000, "retries": 0, "expected_human_review_minutes": null, "licensing_cost": null }
}
```

**Parser unsupported — five states that are not one**

```json
{
  "operator_id": "parser.pdf.layout",
  "operator_version": "1.4.2",
  "tenant_id": "t-acme",
  "investigation_id": "INV-7f3a",
  "policy_fingerprint": "sha256:9c1e…",
  "input_observation_ids": ["obs-91c5"],
  "input_digests": ["sha256:77aa…"],
  "semantic_profile_ref": "semantic/standard/2",
  "output_kind": "document_layout",
  "output_schema_version": "1.2.0",
  "output_digest": null,
  "artifact_refs": [],
  "evidence_refs": [],
  "method_fingerprint": "sha256:5aa0…",
  "parameters_fingerprint": "sha256:b71c…",
  "model_fingerprint": null,
  "deterministic": true,
  "replay_key": "sha256:0c93…",
  "replay_mode": "deterministic",
  "status": "unsupported",
  "error_code": "CAPABILITY_UNAVAILABLE",
  "warnings": [],
  "missingness": ["encrypted PDF; no text layer and no OCR capability in this profile"],
  "uncertainty": {},
  "started_at": "2026-10-14T09:14:11Z",
  "completed_at": "2026-10-14T09:14:11.006Z",
  "source_times": [],
  "cost": { "cpu_seconds": 0.01, "memory_bytes": 1_100_000, "network_io_bytes": 0, "model_tokens": 0, "latency_ms": 6, "storage_bytes": 0, "retries": 0, "expected_human_review_minutes": null, "licensing_cost": null }
}
```

**Model-hosted — result replay, not recomputation**

```json
{
  "operator_id": "interpretation.extract.schema_v3",
  "operator_version": "0.9.0-rc2",
  "tenant_id": "t-acme",
  "investigation_id": "INV-7f3a",
  "policy_fingerprint": "sha256:9c1e…",
  "input_observation_ids": ["obs-91c4"],
  "input_digests": ["sha256:3d7b…"],
  "semantic_profile_ref": "semantic/standard/2",
  "output_kind": "assertion_candidates",
  "output_schema_version": "3.0.0",
  "output_digest": "sha256:ff02…",
  "artifact_refs": ["art-extract-118"],
  "evidence_refs": ["…"],
  "method_fingerprint": "sha256:1a77…",
  "parameters_fingerprint": "sha256:6e04…",
  "model_fingerprint": "sha256:model-2b41…",
  "deterministic": false,
  "replay_key": "sha256:aa90…",
  "replay_mode": "result_replay",
  "status": "succeeded",
  "error_code": null,
  "warnings": ["1 candidate failed schema validation and was preserved as unknown-predicate"],
  "missingness": [],
  "uncertainty": { "candidate_confidence": "uncalibrated_score" },
  "started_at": "2026-10-14T09:20:00Z",
  "completed_at": "2026-10-14T09:20:09.771Z",
  "source_times": [],
  "cost": { "cpu_seconds": 0, "memory_bytes": 0, "network_io_bytes": 41_200, "model_tokens": 7_412, "latency_ms": 9771, "storage_bytes": 0, "retries": 0, "expected_human_review_minutes": 4.5, "licensing_cost": null }
}
```

Note `uncertainty.candidate_confidence = "uncalibrated_score"` — a **named semantics string**, never
a bare probability. FR-016 / P5.