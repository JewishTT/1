# Tenzir in Layer 1: structural dataflow, not semantic truth

Status: **integrated behind an opt-in feature flag; live TQL contract tested against the pinned Node in CI; production-scale throughput is not yet benchmarked.**

## Decision

Tenzir Node is a structural dataflow engine for a derived stage after the platform's lossless payload parser. It does not replace acquisition, the Observation Gate, raw storage, exact-span parsing, mention binding, relation extraction, entity resolution, case policy or graph projection.

Upstream references: [Tenzir Query Language](https://tenzir.com/docs/explanations/language/), [launch pipeline API](https://tenzir.com/docs/reference/api/node/pipelines/launch-pipeline/), [read pipeline output API](https://tenzir.com/docs/reference/api/node/pipeline-output/read-pipeline-output/), and [API security modes](https://tenzir.com/docs/guides/node-setup/start-the-api/).

## Existing native path

1. **ArtifactSink** stores immutable source bytes using the existing ObjectStore; **ObservationGate** mints capture/observation references and emits the canonical event.
2. `apps/interpretation/observation_consumer` resolves `raw_ref` and invokes the native `parsers.payload` layer to create `ObservedField` records. Each preserves the exact source byte span and a deferred occurrence address or a named refusal.
3. **`extractors.payload` remains authoritative** for cited type hypotheses and structure-derived signals; the existing semantic interpretation bridge remains responsible for semantic mention/entity/relation work.
4. The optional Tenzir stage receives serialized `ObservedField` records, derives structural annotations, then persists a separate immutable, content-addressed artifact. It creates no canonical observations, mentions, entities, relation claims or graph edges.

Tenzir's output is currently a **sidecar projection**: its values are recorded for downstream profiling/streaming consumers, but are not promoted to semantic type hypotheses or passed as authority into entity resolution. That is deliberate.

## What the pinned TQL transform computes

The current transform is `tenzir-observed-fields-v2`. It adds:

- lowercase field-path and value-type views;
- character count and UTF-8 byte count;
- numeric-lexeme and non-empty-surface flags;
- byte-span width, checked against the native parser's original span;
- coarse structural role (`container`, `null`, `surface`);
- a lexical/structural `value_shape` hint: `container`, `null`, `empty`, `numeric`, `boolean`, `email_like`, `url_like`, `uuid_like`, `hex_digest_like`, or `text`.

These are **not semantic assertions**. For example, `email_like` does not prove an email address exists, and a numeric-looking lexeme does not say whether its source-defined meaning is a count, port, coordinate or something else. No confidence, identity, truth or authorization is derived.

The adapter uses the versioned Tenzir Node REST API, bounded TQL batches and typed literal serialization; callers cannot submit arbitrary TQL through the case API. It refuses outputs that change/drop protected fields, omit/duplicate an ordinal, produce an inconsistent byte-span width, or violate output-size/type contracts. The returned artifact records the observation/capture/raw references, parser reference, Tenzir version and pipeline digest.

## Preservation and failure semantics

- Native parse output and the original raw evidence remain authoritative and independently addressable.
- Tenzir output is stored separately through the existing content-addressed derived-object path.
- Tenzir errors are represented in the processing result; they do not erase or replace a successful native parse.
- The adapter has finite request/response, output record, per-batch, timeout and pipeline-lifetime bounds.

The dedicated `tenzir-normalization-contract` workflow runs adapter/consumer contracts **and** launches the pinned `ghcr.io/tenzir/tenzir:v6.19.1` Node to compile and execute the actual TQL transform. This is live-node functional acceptance, not proof of production-scale throughput.

## Runtime configuration and security

Tenzir is disabled by default. Example local setup:

```bash
docker compose -f apps/deploy/docker-compose.yml --profile tenzir up -d tenzir-node
```

Set `TENZIR_ENABLED=true` for the interpretation consumer and `TENZIR_NODE_URL=http://localhost:5160`. The URL must be the Node origin without an API path; the adapter supplies `/api/v0`.

The Compose API uses Tenzir developer mode bound to host loopback. **Local/CI only**: developer mode bypasses TLS and token authentication. Never expose it beyond loopback. A deployed Node must use a trusted HTTPS endpoint and secret-managed `TENZIR_NODE_TOKEN`; non-loopback plain HTTP is rejected unless the explicit development-only `TENZIR_ALLOW_INSECURE_HTTP=true` override is set.

## Production-scale gate

This is a real execution integration, but the current implementation starts a hidden interactive pipeline for each bounded batch. Tenzir's long-lived streaming capability is not yet being fully exploited, and pipeline-start overhead, throughput and tail latency have not been measured under realistic event volumes.

The next scale step should be a long-lived Tenzir pipeline consuming a versioned durable stream contract, with bounded buffering/backpressure, durable side-output and explicit consumer acknowledgements. Before enabling it broadly, validate restart/replay/idempotency, poison-input isolation, per-tenant resource accounting, raw/derived lineage and end-to-end persisted-result correctness. Do not route canonical extraction or entity resolution through Tenzir until those gates pass.
