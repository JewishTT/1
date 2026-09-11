# Storage Contract (Evidence Plane)

Content-addressable raw object storage (Spec §25, Constitution I). Raw objects are the durable source of truth for reproduction; projections are always downstream.

## Layout

```text
s3://knowledge/raw/{yyyymm}/{sha256}          // raw response body (content-addressed)
s3://knowledge/raw-meta/{yyyymm}/{sha256}.json // retrieval metadata (headers, etag)
s3://knowledge/normalized/{yyyymm}/{sha256}   // normalized doc for parsers (rebuildable)
```

## Interface

```text
put_raw(observation_meta) -> RawObjectRef      // sha256 addressable; idempotent by hash
get_raw(ref, stream) -> RawObject              // s3:// ref resolution
get_meta(ref) -> MongoMeta
put_normalized(doc, source_hash) -> NormRef
exists(sha256) -> bool
```

## Requirements

- Address = content hash: `put_raw` of identical content is dedup by hash (R-6, FR-007).
- The original object remains available independent of any projection (I-1, FR-002).
- MinIO for dev/self-hosted; S3-compatible by contract (Assumptions/Spec §4).
- Kafka events carry refs, never blobs (I-5).
- Bucket prefixes are tenant-scoped (`s3://knowledge/raw/{tenant}/{yyyymm}/{sha256}`) for isolation (R-10, FR-030).
- Objects are immutably stored; no overwrite semantics.