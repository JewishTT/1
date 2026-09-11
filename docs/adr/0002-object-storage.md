# ADR-0002: Object storage for raw artifacts

Status: Accepted
Date: 2026-09-07

## Context

Raw fetched artifacts (responses, documents, screenshots, browser DOM) must be
stored durably, regionally local for egress locality (FR-030), and cheaply
retrievable with provenance. Candidates: S3-compatible object store, HDFS,
local disk, database blobs.

## Decision

Use an **S3-compatible object store** (S3-API) for raw artifacts.

## Rationale

- Durable, cheap, scalable, no schema lock-in for irregular binary artifacts.
- Regional buckets/prefixes match multi-region data-locality (FR-030), layered
  under per-tenant prefixes (T061).
- Object keys carry provenance and content-addressable stability, supporting
  the immutable-observation invariant (I-1).
- S3 API is a de-facto standard; portable across AWS/GCS/MinIO.

## Consequences

- Blobs never go on Kafka (I-5); Kafka/S3 carry only metadata + object keys.
- Object lifecycle (retention, versioning, bucket-policy) must be GitOps-managed.
- S3 read path needs caching to avoid hot-path latency.
