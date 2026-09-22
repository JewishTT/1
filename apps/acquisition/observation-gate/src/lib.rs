//! Observation Gate — the single content-addressed write path (US1, T130/T131).
//!
//! External engines and workers converge HERE: bytes are hashed with sha256 and
//! stored content-addressed (S3/MinIO), a [`ObservationManifest`] bridges the
//! stores, and lifecycle events `observation.{created,changed,unchanged,
//! duplicate}` are emitted. Workers/adapters MUST NOT store or define storage
//! semantics (Constitution gate: one Observation Gate).
//!
//! Storage transport is behind the [`ObjectStore`] trait so the gate logic is
//! fully testable and engine-independent; `MinioObjectStore` talks to the dev
//! MinIO with path-style S3 PUTs.

use cognitive_acq_contracts::manifest::{CollectorRef, ManifestError, ObservationManifest, PolicyRef, ProvenanceRef, RequestRef, SourceRef};
use sha2::{Digest, Sha256};
use std::time::Duration;

/// Content-addressed storage transport. Implementations must store the bytes so
/// that identical content always maps to the same key (content addressing).
#[async_trait::async_trait]
pub trait ObjectStore: Send + Sync {
    /// Store bytes at a content-addressed key, returning the `raw_uri`.
    /// Returns `Ok(true)` when the object already existed (dedup) —
    /// content-addressed stores may keep one copy for identical content.
    async fn put(&self, key: &str, bytes: &[u8]) -> anyhow::Result<bool>;
}

/// In-memory store for tests and local joints.
pub struct MemoryObjectStore {
    objects: std::sync::Mutex<std::collections::HashMap<String, Vec<u8>>>,
}

impl MemoryObjectStore {
    pub fn new(_prefix: impl Into<String>) -> Self {
        Self { objects: std::sync::Mutex::new(std::collections::HashMap::new()) }
    }
}

#[async_trait::async_trait]
impl ObjectStore for MemoryObjectStore {
    async fn put(&self, key: &str, bytes: &[u8]) -> anyhow::Result<bool> {
        let mut map = self.objects.lock().unwrap();
        let existed = map.contains_key(key);
        map.insert(key.to_string(), bytes.to_vec());
        Ok(existed)
    }
}

/// Bucket + endpoint + credentials for the dev MinIO (path-style S3 API).
#[derive(Debug, Clone)]
pub struct MinioStoreConfig {
    pub endpoint: String, // e.g. http://localhost:9000
    pub bucket: String,
    pub access_key: String,
    pub secret_key: String,
}

/// Path-style S3/MinIO PUT via reqwest (dev topology; SigV4 kept for the
/// integration phase so the gate contract stays independent of transport).
pub struct MinioObjectStore {
    config: MinioStoreConfig,
    client: reqwest::Client,
}

impl MinioObjectStore {
    pub fn new(config: MinioStoreConfig) -> anyhow::Result<Self> {
        let client = reqwest::Client::builder()
            .connect_timeout(Duration::from_secs(5))
            .build()?;
        Ok(Self { config, client })
    }
}

#[async_trait::async_trait]
impl ObjectStore for MinioObjectStore {
    async fn put(&self, key: &str, bytes: &[u8]) -> anyhow::Result<bool> {
        let url = format!("{}/{}/{}", self.config.endpoint, self.config.bucket, key);
        let resp = self.client.put(&url).basic_auth(&self.config.access_key, Some(&self.config.secret_key)).body(bytes.to_vec()).send().await?;
        let status = resp.status();
        if status.is_success() || status == reqwest::StatusCode::CONFLICT {
            // CONFLICT on existing object (S3 path-style with overwrite disabled);
            // either way the content is stored under a content-addressed key.
            return Ok(status == reqwest::StatusCode::CONFLICT);
        }
        anyhow::bail!("minio put failed: {} {}", status, resp.text().await.unwrap_or_default());
    }
}

/// Lifecycle classification of one observation, per R-08 three-way split
/// (created / changed / duplicate / unchanged).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Lifecycle {
    Created,
    Changed,
    Unchanged,
    Duplicate,
}

impl Lifecycle {
    pub fn event_type(self) -> &'static str {
        match self {
            Self::Created => "observation.created",
            Self::Changed => "observation.changed",
            Self::Unchanged => "observation.unchanged",
            Self::Duplicate => "observation.duplicate",
        }
    }

    pub fn outcome_status(self) -> &'static str {
        match self {
            Self::Created | Self::Changed => "completed",
            Self::Unchanged => "unchanged",
            Self::Duplicate => "duplicate",
        }
    }
}

/// How the gate resolves lifecycle. `previous_digest` comes from the frontier's
/// last observation of the same source+target.
///
/// Order matters (R-08 three-way split): a same-source refresh with identical
/// content is `unchanged` (reachable for real re-observations, where the store
/// already holds the bytes); a content-address collision from another context
/// is `duplicate`; otherwise created/changed by first difference.
pub fn resolve_lifecycle(stored_before: bool, previous_digest: Option<&str>, new_digest: &str) -> Lifecycle {
    if previous_digest == Some(new_digest) {
        return Lifecycle::Unchanged;
    }
    if stored_before {
        // Content-addressed store already had identical bytes -> dedup.
        return Lifecycle::Duplicate;
    }
    match previous_digest {
        None => Lifecycle::Created,
        Some(_) => Lifecycle::Changed,
    }
}

/// Envelope-shaped event the gate emits (mirrors `EventEnvelope` v2 routing
/// fields; full protobuf emission in the integration phase).
#[derive(Debug, Clone, serde::Serialize)]
pub struct GateEvent {
    pub event_type: String,
    pub event_version: String,
    pub observation_id: String,
    pub raw_uri: String,
    pub sha256: String,
    pub tenant_id: String,
    pub source_id: String,
    pub work_id: String,
    pub region_id: String,
}

/// Lifecycle event sink (T131). Transport behind a trait; integration wires a
/// Redpanda producer.
#[async_trait::async_trait]
pub trait EventEmitter: Send + Sync {
    async fn emit(&self, event: &GateEvent) -> anyhow::Result<()>;
}

/// Stub emitter logging events (dev/no-broker). Redpanda producer lands with
/// the stream plane (phase C).
pub struct LoggingEmitter;

#[async_trait::async_trait]
impl EventEmitter for LoggingEmitter {
    async fn emit(&self, event: &GateEvent) -> anyhow::Result<()> {
        tracing::info!(event_type = %event.event_type, observation_id = %event.observation_id, raw_uri = %event.raw_uri, "gate event");
        Ok(())
    }
}

/// Metadata required to build an [`ObservationManifest`] for the stored blob.
#[derive(Debug, Clone)]
pub struct ObservationMeta {
    pub observation_id: String,
    pub tenant_id: String,
    pub source_id: String,
    pub work_id: String,
    pub region_id: String,
    pub target: String,
    pub content_type: Option<String>,
    pub collector_name: String,
    pub collector_version: String,
    pub source_kind: String,
    pub policy_id: String,
    pub policy_version: String,
    pub parent_observation: Option<String>,
    pub causation_id: Option<String>,
    pub correlation_id: Option<String>,
    pub retrieved_at: String, // RFC3339
    pub previous_digest: Option<String>,
}

/// Stored observation: the immutable manifest + the lifecycle classification.
#[derive(Debug, Clone)]
pub struct StoredObservation {
    pub manifest: ObservationManifest,
    pub lifecycle: Lifecycle,
}

/// The single gate. `store` is the ONLY path bytes enter Cognitive storage.
pub struct ObservationGate {
    store: std::sync::Arc<dyn ObjectStore>,
    emitter: std::sync::Arc<dyn EventEmitter>,
    base_uri: String,
}

impl ObservationGate {
    pub fn new(store: std::sync::Arc<dyn ObjectStore>, emitter: std::sync::Arc<dyn EventEmitter>, base_uri: impl Into<String>) -> Self {
        Self { store, emitter, base_uri: base_uri.into() }
    }

    /// Content-address, store, classify, validate + emit for one blob.
    pub async fn store(&self, bytes: &[u8], meta: &ObservationMeta) -> anyhow::Result<StoredObservation> {
        let digest = format!("{:x}", Sha256::digest(bytes));
        let key = format!("obs/{digest}");
        let stored_before = self.store.put(&key, bytes).await?;
        let lifecycle = resolve_lifecycle(stored_before, meta.previous_digest.as_deref(), &digest);

        let raw_uri = format!("{}/{}", self.base_uri.trim_end_matches('/'), key);
        let manifest = ObservationManifest {
            observation_id: meta.observation_id.clone(),
            raw_uri: raw_uri.clone(),
            sha256: digest.clone(),
            content_type: meta.content_type.clone().unwrap_or_else(|| "application/octet-stream".into()),
            content_length: bytes.len() as u64,
            collector: CollectorRef { name: meta.collector_name.clone(), version: meta.collector_version.clone() },
            source: SourceRef { source_id: meta.source_id.clone(), kind: meta.source_kind.clone() },
            request: RequestRef { target: meta.target.clone(), retrieved_at: meta.retrieved_at.clone() },
            policy: PolicyRef { policy_id: meta.policy_id.clone(), version: meta.policy_version.clone() },
            provenance: ProvenanceRef {
                parent_observation: meta.parent_observation.clone(),
                causation_id: meta.causation_id.clone(),
                correlation_id: meta.correlation_id.clone(),
            },
        };
        manifest.validate().map_err(|e: ManifestError| anyhow::Error::new(e))?;

        self.emitter
            .emit(&GateEvent {
                event_type: lifecycle.event_type().into(),
                event_version: "2.0".into(),
                observation_id: manifest.observation_id.clone(),
                raw_uri: raw_uri.clone(),
                sha256: digest,
                tenant_id: meta.tenant_id.clone(),
                source_id: meta.source_id.clone(),
                work_id: meta.work_id.clone(),
                region_id: meta.region_id.clone(),
            })
            .await?;

        Ok(StoredObservation { manifest, lifecycle })
    }
}

/// Convenience MINIO path-style store bound to the dev MinIO.
pub async fn minio_store(config: MinioStoreConfig) -> anyhow::Result<std::sync::Arc<dyn ObjectStore>> {
    Ok(std::sync::Arc::new(MinioObjectStore::new(config)?))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Arc;

    fn meta(prev: Option<String>, obs_id: &str, sha_marker: &str) -> ObservationMeta {
        ObservationMeta {
            observation_id: obs_id.into(),
            tenant_id: "ten-1".into(),
            source_id: "src-1".into(),
            work_id: "wrk-1".into(),
            region_id: "eu-west".into(),
            target: format!("http://host/{sha_marker}"),
            content_type: Some("text/html".into()),
            collector_name: "worker-http".into(),
            collector_version: "0.4.0".into(),
            source_kind: "web".into(),
            policy_id: "pol-1".into(),
            policy_version: "1".into(),
            parent_observation: None,
            causation_id: Some("caus-1".into()),
            correlation_id: Some("corr-1".into()),
            retrieved_at: "2026-09-16T12:00:00Z".into(),
            previous_digest: prev,
        }
    }

    fn gate() -> ObservationGate {
        ObservationGate::new(Arc::new(MemoryObjectStore::new("s3://know")), Arc::new(LoggingEmitter), "s3://know")
    }

    #[tokio::test]
    async fn first_observation_is_created() {
        let g = gate();
        let blob = b"<html>v1</html>";
        let stored = g.store(blob, &meta(None, "OBS-1", "a")).await.unwrap();
        assert_eq!(stored.lifecycle, Lifecycle::Created);
        assert_eq!(stored.manifest.content_length, blob.len() as u64);
        assert!(stored.manifest.is_content_addressed());
        stored.manifest.validate().unwrap();
    }

    #[tokio::test]
    async fn identical_bytes_dedup_to_duplicate_without_source_context() {
        // Same bytes from a DIFFERENT source (no previous digest): content-address
        // collision -> duplicate, never a second copy or a created event.
        let g = gate();
        let blob = b"<html>same</html>";
        let first = g.store(blob, &meta(None, "OBS-1", "a")).await.unwrap();
        let second = g.store(blob, &meta(None, "OBS-2", "b")).await.unwrap();
        assert_eq!(first.lifecycle, Lifecycle::Created);
        assert_eq!(second.lifecycle, Lifecycle::Duplicate);
        assert_eq!(first.manifest.raw_uri, second.manifest.raw_uri);
    }

    #[tokio::test]
    async fn same_source_refresh_of_identical_bytes_classifies_unchanged() {
        // Re-observation of the SAME source+target: identical digest -> unchanged
        // (previous_digest wins over storage presence so the event is reachable).
        let g = gate();
        let blob = b"<html>stable</html>";
        g.store(blob, &meta(None, "OBS-1", "a")).await.unwrap();
        let prev = format!("{:x}", Sha256::digest(blob));
        let second = g.store(blob, &meta(Some(prev), "OBS-2", "b")).await.unwrap();
        assert_eq!(second.lifecycle, Lifecycle::Unchanged);
        assert_eq!(first_store_uri(blob), second.manifest.raw_uri);
    }

    fn first_store_uri(blob: &[u8]) -> String {
        let digest = format!("{:x}", Sha256::digest(blob));
        format!("s3://know/obs/{digest}")
    }

    #[tokio::test]
    async fn changed_bytes_classify_changed() {
        let g = gate();
        g.store(b"<html>v1</html>", &meta(None, "OBS-1", "a")).await.unwrap();
        let prev = format!("{:x}", Sha256::digest(b"<html>v1</html>"));
        let second = g.store(b"<html>v2</html>", &meta(Some(prev), "OBS-2", "b")).await.unwrap();
        assert_eq!(second.lifecycle, Lifecycle::Changed);
    }

    #[tokio::test]
    async fn identical_content_with_known_digest_classifies_unchanged() {
        // Same source re-fetched, content unchanged, but store dropped the key
        // (cache eviction in an upstream dedup won't happen; here we verify the
        // frontier-digest branch independent of storage presence).
        let g = ObservationGate::new(Arc::new(MemoryObjectStore::new("s3://know")), Arc::new(LoggingEmitter), "s3://know");
        let blob = b"<html>stable</html>";
        let digest = format!("{:x}", Sha256::digest(blob));
        assert_eq!(resolve_lifecycle(false, Some(&digest), &digest), Lifecycle::Unchanged);
        let stored = g.store(blob, &meta(Some(digest), "OBS-1", "a")).await.unwrap();
        assert_eq!(stored.lifecycle, Lifecycle::Unchanged);
    }

    #[test]
    fn lifecycle_maps_to_topics_and_statuses() {
        assert_eq!(Lifecycle::Created.event_type(), "observation.created");
        assert_eq!(Lifecycle::Changed.outcome_status(), "completed");
        assert_eq!(Lifecycle::Unchanged.outcome_status(), "unchanged");
        assert_eq!(Lifecycle::Duplicate.outcome_status(), "duplicate");
    }
}