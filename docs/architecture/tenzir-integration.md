# Tenzir in the interpretation layer

## Decision and boundary

Tenzir Node is integrated as an **optional structural-dataflow stage**, not as a replacement for the platform's evidence model or semantic extractor.

The canonical path remains:

`source → ArtifactSink → immutable Capture/raw object → Observation/event → native payload parser → mention binding → existing semantic/admission stages`.

The native `parsers.payload` implementation owns byte spans, unknown-field retention, and deferred occurrence addresses. `extractors.payload` owns typed hypotheses and structure-derived signals. Tenzir does not write canonical observations, create mentions, resolve entities, assert relations, or admit claims.

## What the adapter actually does

`apps/interpretation/normalization/tenzir.py` sends already-parsed `ObservedField` records to a Tenzir Node using its versioned REST API. The reviewed TQL transform adds structural annotations: case-normalized field paths and value types, character/byte lengths, numeric lexical shape, non-empty surface state, byte-span width, a coarse structural role, and a versioned `value_shape` hint (`container`, `null`, `empty`, `numeric`, `boolean`, `email_like`, `url_like`, `uuid_like`, `hex_digest_like`, or `text`). These are lexical/structural hints for downstream profiling, not assertions that the observed string is a valid email/URL/identifier or a semantic type.

The returned rows are checked against the original records. Protected source fields must be present and byte-for-byte/value-equivalent, every input ordinal must appear exactly once, output order/cardinality is verified, and the recorded span width must equal the parser's span width. Tenzir output is written as an immutable, content-addressed derived manifest using the existing object-store deduplication path. The manifest records the observation/capture/raw refs, parser reference, Node version, TQL pipeline version and digest.

The derived annotations are **not semantic facts**. For example, a numeric-looking lexeme does not prove that a field is a number, and a lowercase field path does not authorize entity matching. The native record and its byte span remain authoritative.

## Execution and resource limits

The feature flag is `TENZIR_ENABLED=false` by default. When enabled, the current adapter sends a bounded chunk of one parsed observation's records to a short-lived interactive pipeline. Input/output record counts, request/response bytes, timeout and pipeline lifetime are capped. A Tenzir failure is recorded in the processing result while the native parse remains usable; it cannot delete or rewrite raw evidence.

For local development, start the pinned node using the optional Compose profile:

```bash
docker compose -f apps/deploy/docker-compose.yml --profile tenzir up -d tenzir-node
```

Set `TENZIR_ENABLED=true` in the environment of the interpretation consumer. `TENZIR_NODE_URL` must be the Node origin, not an API path; the adapter uses the versioned `/api/v0` REST prefix. The live acceptance test runs against the pinned Tenzir Node `v6.19.1`, launches a real TQL pipeline, reads its output, and verifies the protected source fields.

The Compose node binds to loopback and uses developer mode. **That configuration is only for local development/CI.** Developer mode bypasses TLS and token authentication. Do not expose it beyond loopback. A deployed Node needs a deliberate TLS/authentication configuration and a secret-managed token.

## Production fit and remaining gate

Tenzir is a suitable candidate for the platform's Layer-1 dataflow work: high-volume event transformation, schema-aware enrichment, aggregation and routing. The adapter here is a safe, live-tested integration seam, but it is **not yet the high-throughput streaming architecture**. It launches an interactive pipeline per bounded chunk, so it must not be enabled indiscriminately for a high-rate ingestion workload without measuring launch overhead and resource pressure.

The production-scale next step is a long-lived Tenzir pipeline over a versioned, durable stream contract, with a durable side-output and consumer acknowledgements. That change must retain the present invariants: raw evidence is immutable, unknown fields survive, provenance is explicit, and Tenzir has no write access to canonical claims or entity resolution. Do not silently route the canonical extraction path through Tenzir until the long-lived stream, backpressure, replay, failure handling and end-to-end persisted-result gates pass.
