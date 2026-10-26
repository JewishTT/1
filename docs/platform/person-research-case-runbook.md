# Feature 034 — Person Research Case operational runbook

## Supported first slice

The first source-backed slice is **public scholarly metadata via Crossref**. It can discover and preserve publication records; it does not, by itself, substantiate employment or public office. The policy deliberately blocks professional-role families unless an eligible, attested source explicitly supports them. Search results from SearXNG are discovery-only and do not count as primary evidence.

The request path is:

1. The control plane creates a draft case, an append-only scope revision, and obligations without network I/O.
2. A user with the appropriate role approves the exact scope digest/revision.
3. The planner produces source-bound actions against the policy and source catalogue. Actions require their own review/approval.
4. The durable budget reservation and dispatch intent are committed; the existing planner publishes the canonical `acquisition.request` envelope.
5. The host-run acquisition worker revalidates tenant, context state, approval, scope/policy revisions, approved action, source allowlist, dispatch intent, and budget immediately before I/O.
6. The source connector stores original response bytes in the content-addressed ObjectStore. `ArtifactSink` registers `captures` + `observations` in PostgreSQL in one transaction, then publishes `observation.created`.
7. The interpretation consumer reads the same raw bytes, runs the declared parser and optional Tenzir normalization, stores immutable derived manifests, runs the existing `InterpretationBridge`, and persists the processing result before committing its Kafka offset.
8. The workspace reads PostgreSQL-backed claims/relations, coverage and bitemporal projections. Missing projections are reported as unavailable, not replaced with fabricated data.

## Local development setup

From the repository root:

```bash
cp .env.example .env
```

Edit `.env` before running a source-backed case:

- Set `COGNITIVE_CROSSREF_MAILTO` to a real, monitored operator address. The Crossref connector will refuse to run if this is absent or a placeholder.
- Configure `POSTGRES_*`, `KAFKA_BOOTSTRAP_SERVERS`, `S3_ENDPOINT`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, and `S3_RAW_BUCKET` to match the services you start.
- Configure the control-plane JWT issuer, audience, and secret from your identity provider. Unauthenticated requests fail closed by default.

Install the locked workspace and start the core dependencies (including MinIO, PostgreSQL, Redpanda and SearXNG):

```bash
uv sync --locked --all-packages --all-groups
docker compose -f apps/deploy/docker-compose.yml --profile core up -d minio minio-init postgres redpanda searxng
```

Apply the versioned database migrations **before** starting application processes:

```bash
cd apps/control-plane
uv run --project . alembic -c alembic.ini upgrade head
cd ../..
```

Start the control plane in one terminal:

```bash
uv run --project apps/control-plane uvicorn api.main:app --host 0.0.0.0 --port 8000
```

Start the acquisition worker in a second terminal:

```bash
uv run --project apps/acquisition cognitive-acquisition-worker
```

Start the observation consumer in a third terminal:

```bash
uv run --project apps/control-plane cognitive-observation-consumer
```

The deployment topology intentionally runs these worker processes on the host; their dependencies (PostgreSQL, Redpanda, MinIO, and SearXNG) run in Compose. Don't set the worker broker to the Docker-internal service name when running on the host; use `localhost:19092` in that topology.

For optional Tenzir normalization, start the loopback-only development node separately:

```bash
docker compose -f apps/deploy/docker-compose.yml --profile tenzir up -d tenzir-node
```

Set `TENZIR_ENABLED=true` and keep `TENZIR_NODE_URL=http://localhost:5160` only for local development. The worker records a normalization failure explicitly and retains the native parser result if Tenzir is unavailable. Never expose its unauthenticated development mode beyond loopback; production must use the protected upstream mode.

## Verifying the path

Use an approved public-name/ORCID/author-record anchor and select only claim families supported by the selected source. For the current Crossref source, `public_authorship_or_publication` is supported; `public_professional_role` must remain blocked unless another source is formally attested and registered.

After approval, plan the case and review every source-bound action. Start acquisition only after reviewing/approving the concrete actions. Check the case coverage ledger:
- `DISPATCH_ACKNOWLEDGED_AWAITING_OBSERVATIONS` means the broker acknowledged the task, but a durable worker observation has not yet been linked.
- `OBSERVATIONS_RECEIVED` means the canonical observation table contains the matching task-linked row.
- `NO_ELIGIBLE_ACTIONS` / `BLOCKED_CAPABILITY` means the declared scope has no approved source action; it is not evidence that the requested fact is absent.

In PostgreSQL, verify these records share the same tenant and case/investigation:
- `captures` and `observations`, including the raw-object URI and SHA-256 digest;
- `processing_results` with the same `observation_id` and concrete immutable `derived_ref`;
- `entities`, `entity_versions`, `relation_claims`, and `entity_stream` where deterministic extraction yielded those records;
- `person_case_dispatch_intents` and `person_case_budget_reservations` for the run.

A successful HTTP response or Kafka broker acknowledgement alone is not end-to-end success. To promote the path, retain the real source URL, capture ID, raw digest, observation ID, processing result ID, parser/extractor version, exact evidence span/relations, budget reservation, task/offset, and final report references for the exact commit SHA.

## Failure and replay semantics

- Source-policy, scope or approval mismatch: refuse the task before network I/O and retain a typed quarantine outcome.
- PostgreSQL or broker infrastructure failure: do not commit the failing Kafka offset; redelivery is expected and writes are idempotent by durable identity.
- Native parser succeeds but Tenzir fails: preserve the native parse artifact and record normalization failure. Do not pretend normalization succeeded.
- No mentions/relations extracted: persist the parser result and report the absence of extracted structures; do not manufacture entities or factual negatives.
- Unwired projection: API reports a truthful capability error; it does not synthesize graph edges, findings or coverage.
