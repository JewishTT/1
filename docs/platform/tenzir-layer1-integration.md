# Tenzir in Layer 1: structural dataflow, not semantic truth

Status: **integrated behind an opt-in feature flag; live-node validation still required**.

## Decision

Tenzir Node is the structural batch/stream execution engine for a derived stage after
the platform's lossless payload parser. It does not replace acquisition, the
Observation Gate, raw storage, exact-span parsing, mention binding, relation extraction,
entity resolution, case policy or graph projection.

Upstream reference: [Tenzir Query Language](https://tenzir.com/docs/explanations/language/),
[launch pipeline API](https://tenzir.com/docs/reference/api/node/pipelines/launch-pipeline/),
[read pipeline output API](https://tenzir.com/docs/reference/api/node/pipeline-output/read-pipeline-output/),
and [API security modes](https://tenzir.com/docs/guides/node-setup/start-the-api/).

## Existing native path

1. **ArtifactSink** writes immutable source bytes to **ObjectStore**; **ObservationGate**
   mints the capture/observation references and emits **observation.created**.
2. **apps/interpretation/observation_consumer** loads the bytes named by **raw_ref** and
   uses **parsers.payload** to produce **ObservedField** records, including source byte
   spans and an address or a named refusal.
3. **extractors.payload** uses those records for explicit hypotheses and structural
   relations. It remains the authority for mention/occurrence semantics.
4. The optional Tenzir stage receives the serialized **ObservedField** records, computes
   structural features, and stores an immutable derived artifact. It creates no
   observations, mentions, entities, relation claims or graph edges.

## What Tenzir computes

The versioned TQL transform is **tenzir-observed-fields-v1**. It adds these derived
columns while preserving the original record in full:

- lowercase field path and value-type view;
- value character count and UTF-8 byte count;
- whether the observed string is a numeric lexeme (a lexical feature, not a semantic
  type assertion);
- whether the surface is non-empty after whitespace trimming;
- width of the original byte span, when a span exists;
- a coarse structural role (container, null, surface) based on the parser's observed
  value type.

These are structural features for later joins, schema comparison and streaming filters.
They are not confidence, identity or truth. In particular, this transform does not
run OCSF casts or trims, because a target-schema projection may discard fields that
are unknown to that schema, while Cognitive requires open-world source fields to remain
reachable.

## Preservation contract

The adapter rejects results that:
- drop or duplicate an input ordinal;
- alter or omit any protected source field (field, value, value_type, byte_span, depth,
  label, address, address_refusal);
- omit or mistype the derived structural columns;
- calculate a span width that disagrees with the original byte offsets;
- exceed configured request, response, record-count or time limits.

The original parser result is always retained as the primary extraction output. If
Tenzir is unavailable or fails its output contract, the processing result records
normalization.status = failed and the error code, but the native parser path remains
available. A successful Tenzir pass produces a separate S3/MinIO content-addressed
object under derived/<tenant>/<yyyymm>/<sha256>, with its original raw_ref,
observation/capture ids, parser reference, TQL pipeline digest and Tenzir version.
The original raw artifact is never overwritten.

## Runtime boundary and configuration

Tenzir remains off unless TENZIR_ENABLED=true. The local profile is started with:

~~~bash
docker compose -f apps/deploy/docker-compose.yml --profile tenzir up -d tenzir-node
~~~

For a local host-run interpretation worker:

~~~dotenv
TENZIR_ENABLED=true
TENZIR_NODE_URL=http://localhost:5160
TENZIR_NODE_VERSION=6.19.1
TENZIR_MAX_BATCH_RECORDS=256
TENZIR_MAX_REQUEST_BYTES=2000000
TENZIR_MAX_RESPONSE_BYTES=4000000
TENZIR_MAX_OUTPUT_RECORDS=4096
TENZIR_TIMEOUT_SECONDS=45
~~~

The compose API runs in Tenzir developer mode, which bypasses API authentication and
TLS; therefore it is bound to host loopback only. Never expose that listener beyond the
local machine. Production must configure Tenzir server/upstream/mTLS mode, HTTPS and a
node token (TENZIR_NODE_TOKEN), and set TENZIR_NODE_URL to the trusted TLS endpoint.
TENZIR_ALLOW_INSECURE_HTTP=true is an explicit development-only escape hatch for a
private non-loopback HTTP endpoint; it is not appropriate for production.

Resource limits are local admission bounds for each invocation, not a global tenant
budget. Case collection budgets still belong to the existing control-plane reservation
service; Tenzir cannot increase those limits or initiate additional source acquisition.

## Performance posture and remaining gate

The first adapter submits bounded batches through Tenzir's interactive pipeline API
(POST /pipeline/launch then POST /serve) and deletes hidden pipelines on failure;
hidden pipelines also have a finite TTL. This is a concrete execution path, not a
Python imitation of TQL, but creating one pipeline per batch has overhead. Measure
throughput and tail latency on realistic record distributions before enabling it for
high-volume workloads. If pipeline startup dominates, the next step is a long-lived
Tenzir input endpoint / persistent pipeline and backpressure-aware streaming, not
loosening batch limits or buffering an unbounded case in memory.

CI includes contract tests for configuration, safe literal construction, chunking,
preservation, output completeness and native-consumer fallback. A real-node acceptance
run against the pinned Tenzir image is still required before assigning LIVE_PROVEN
status; mocks prove adapter contracts, not that a deployed node accepts the TQL program.
