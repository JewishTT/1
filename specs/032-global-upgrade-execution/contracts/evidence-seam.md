# Contract 01 — The Evidence Seam

**Feature**: `032-global-upgrade-execution`
**Governs**: every path by which collected material becomes canonical observation.
**Enforces**: FR-001, FR-002, FR-003, FR-004, FR-005; SC-002, SC-004.

---

## Why this contract exists

Blueprint §0.1 states the decision in one sentence: *"Все исполнители отдают артефакты через общий
`ArtifactSink` / Observation Gate. Никакой runtime не создаёт собственную независимую версию
canonical observation и не пишет напрямую в canonical entity/projection stores."*

That is a claim about **cardinality**: there is exactly one path, and a second path is a defect.
The blueprint's WP4 is the gate that makes the cardinality true, and its §3.5 lists the eight
obligations the sink owes.

The seam is the only place where raw bytes, capture identity, observation identity, locator,
membership and publication meet. Everything downstream — span grounding, replay idempotency,
coverage accounting, provenance independence, conflict lineage — assumes this contract holds.

---

## The path

```text
executor (any family)
  │  returns AcquisitionArtifact { raw bytes, locator metadata, runtime/source/version }
  v
ArtifactSink
  ├── 1. persist raw object                        (durable, content-addressed)
  ├── 2. compute digest + content address
  ├── 3. derive capture identity                   (deterministic, scheme-versioned)
  ├── 4. create record observations                (parent capture + N records)
  │        each with a typed locator
  ├── 5. attach membership / provenance context
  ├── 6. write outbox row + canonical event        (one transaction seam)
  └── 7. return acknowledged publication details
  v
Observation Gate  ──> canonical observation ──> downstream interpretation
```

There is no branch around step 1, and no publisher other than step 6.

---

## Shape

```text
AcquisitionArtifact
├── raw_bytes                   REQUIRED   the exact received bytes, uncompressed as received
├── content_type                REQUIRED   declared and detected, both kept when they differ
├── locator_metadata            REQUIRED   source-native address of the artifact
├── runtime_ref                 REQUIRED   which executor family and version produced it
├── source_ref                  REQUIRED   catalogue source, with its policy snapshot ref
├── requested_scope             REQUIRED   the scope this fetch was authorised under
├── http_or_transport_meta      OPTIONAL   status, headers subset, redirect chain
├── timing                      REQUIRED   requested_at, first_byte_at, completed_at
├── outcome                     REQUIRED   one of the closed fetch outcomes (see R6)
└── warnings[]                  OPTIONAL   partial-coverage signals from the executor

Publication
├── artifact_ref                REQUIRED   content address of the raw object
├── raw_ref                     REQUIRED   durable object-store reference
├── capture_id                  REQUIRED   deterministic, scheme-versioned
├── capture_identity_scheme     REQUIRED   version of the derivation rule
├── observation_ids[]           REQUIRED   one per record; at least one for a non-empty artifact
├── locators[]                  REQUIRED   typed, one per observation
├── outbox_event_id             REQUIRED   the committed canonical event
├── committed_at                REQUIRED   transaction commit time, not wall-clock guess
└── idempotency_key             REQUIRED   echoed from the task that produced it

Observation
├── observation_id              REQUIRED
├── capture_id                  REQUIRED   parent
├── locator                     REQUIRED   typed union: json_pointer | table_cell |
│                                          warc_record | page_span | char_span | record_index
├── observed_bytes_digest       REQUIRED   digest of the bytes this observation covers
├── provenance_context          REQUIRED   investigation, context revision, obligation, action
├── observed_at                 REQUIRED   when the platform received the bytes
└── published_at                REQUIRED   when the canonical event committed
```

---

## Normative rules

### R1 — Raw before publication

No observation may exist without a persisted `raw_ref`. An attempt to publish without one is
**rejected**, and the rejection is recorded as an event with the executor, the task and the missing
reference named. "Rejected" is not "logged and continued".

### R2 — Deterministic identity, versioned scheme

`capture_id` and `observation_id` are derived from content and locator under a **named scheme
version**. Two runs over the same bytes and locator produce the same ids; a scheme change produces
new ids and is a deliberate migration, not an accident. Wall-clock time, arrival order and mutable
worker state are never hashed into identity.

### R3 — One parent, many records

A single capture may yield multiple record observations — JSON records, table rows, WARC records,
page spans. Each carries its own typed locator and its own digest. The parent is not duplicated per
record.

### R4 — Atomic publication

The outbox row and the canonical event commit in **one** transaction. If the transaction fails, no
event exists. An event without committed backing state is a contract violation, not a race to
tolerate.

### R5 — Idempotent replay

Re-delivering the same artifact with the same idempotency key MUST NOT:
- create a second canonical observation,
- increment coverage,
- increment evidence-independence accounting,
- update cost learning twice,
- emit an additional semantic revision.

The replay returns the original publication. This is the single most important property of the
seam, because every retry, every checkpoint resume and every backfill exercises it.

### R6 — Closed fetch outcome vocabulary

An executor reports exactly one of:

| Outcome | Meaning | Is a durable result? |
|---|---|---|
| `accepted` | artifact persisted and published | yes |
| `partial` | artifact persisted; coverage incomplete and declared | yes |
| `no-result` | fetch succeeded; the source returned nothing in scope | yes |
| `unsupported` | this executor cannot express the requested query | yes |
| `unavailable` | the source or transport is unavailable | yes |
| `policy-denied` | access policy refused the request | yes |
| `failed` | an error occurred and was classified | yes |

An outcome is never `null`. A failure is never represented as an empty artifact.

### R7 — Orphan reconciliation

A crash between raw persistence and outbox commit leaves an orphan artifact. Reconciliation MUST
either publish it with a **new, derivable** capture identity or mark it `unplaced` with a reason.
It MUST NOT invent a capture identity that claims a provenance the platform cannot prove.

### R8 — No semantic interpretation here

The sink does not decide whether the data is true, relevant, important or well-formed beyond
transport integrity. It stores, addresses, publishes. Truth is downstream.

### R9 — Membership is recorded, not inferred

The observation carries its investigation, context revision, obligation and action references. A
consumer must never have to guess which investigation an observation belongs to from its source or
its timing.

### R10 — Secrets never cross the seam

Credentials, session tokens and authorisation headers are referenced by vault pointer or omitted.
They do not appear in the artifact metadata, the outbox payload, the event or the log line.

---

## Prohibitions

- A source-specific worker mounting its own observation-event schema.
- A runtime creating "canonical" evidence without a durable `raw_ref`.
- A second publisher inside the same service, even behind a feature flag.
- An event emitted before the backing transaction commits.
- A "retry" that duplicates coverage because idempotency was not threaded through the task.

---

## Tests that prove this contract

| Test | Asserts |
|---|---|
| `tests/integration/test_evidence_seam.py::test_publish_without_raw_is_rejected` | R1 |
| `tests/replay/test_evidence_seam_idempotency.py::test_replay_does_not_inflate` | R5 |
| `tests/integration/test_evidence_seam.py::test_orphan_reconciliation` | R7 |
| `tests/contract/test_stage_outcome.py::test_every_outcome_round_trips` | R6 |
| `tests/security/test_seam_redaction.py::test_no_secret_in_artifact_metadata` | R10 |
| `tests/golden/test_failure_restart_replay.py` | R4, R5, R7 together |
