//! Observation Manifest — the immutable bridge entity (T129, R-08, I-5).
//!
//! Every observation converges on one content-addressed gate; bytes live in
//! object storage, the manifest (this struct) bridges S3 / Redpanda / Iceberg /
//! Postgres / OpenSearch. Identical bytes → identical content address →
//! `duplicate`/`unchanged` instead of re-storage.

use serde::{Deserialize, Serialize};

/// Collector identity + version so rebuilds and audits stay faithful.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct CollectorRef {
    pub name: String,
    pub version: String,
}

/// Source identity (+ type) of the observation.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct SourceRef {
    pub source_id: String,
    pub kind: String, // e.g. "web", "archive", "dataset", "feed", "api"
}

/// Request/timing facts of the retrieval.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RequestRef {
    pub target: String,
    pub retrieved_at: String, // RFC3339
}

/// The policy under which the observation was collected.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PolicyRef {
    pub policy_id: String,
    pub version: String,
}

/// Provenance links into the causation/correlation chain.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ProvenanceRef {
    pub parent_observation: Option<String>,
    pub causation_id: Option<String>,
    pub correlation_id: Option<String>,
}

/// The bridge manifest. Written by the Observation Gate; immutable afterwards.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ObservationManifest {
    pub observation_id: String,
    pub raw_uri: String,
    pub sha256: String,
    pub content_type: String,
    pub content_length: u64,
    pub collector: CollectorRef,
    pub source: SourceRef,
    pub request: RequestRef,
    pub policy: PolicyRef,
    pub provenance: ProvenanceRef,
}

impl ObservationManifest {
    /// Content-addressing contract: `raw_uri` must encode the sha256 of the
    /// stored bytes so identical content maps to identical addresses.
    pub fn is_content_addressed(&self) -> bool {
        self.raw_uri.contains(&self.sha256)
    }

    /// Minimal structural validation (immutability + addressing invariants).
    pub fn validate(&self) -> Result<(), ManifestError> {
        if self.observation_id.is_empty() {
            return Err(ManifestError::EmptyField("observation_id"));
        }
        if self.sha256.len() != 64 || !self.sha256.bytes().all(|b| b.is_ascii_hexdigit()) {
            return Err(ManifestError::InvalidSha256);
        }
        if !self.is_content_addressed() {
            return Err(ManifestError::NotContentAddressed);
        }
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
pub enum ManifestError {
    #[error("manifest field is empty: {0}")]
    EmptyField(&'static str),
    #[error("sha256 must be 64 lowercase hex digits")]
    InvalidSha256,
    #[error("raw_uri must encode the content sha256")]
    NotContentAddressed,
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sample() -> ObservationManifest {
        ObservationManifest {
            observation_id: "OBS-001".into(),
            raw_uri: "s3://bucket/obs/2026/09/16/ab12cd".into(),
            sha256: "ab12cd".repeat(11), // 66 chars — adjusted below
            content_type: "text/html".into(),
            content_length: 182390,
            collector: CollectorRef {
                name: "heritrix".into(),
                version: "3.x".into(),
            },
            source: SourceRef {
                source_id: "SRC-001".into(),
                kind: "archive".into(),
            },
            request: RequestRef {
                target: "https://example.com/".into(),
                retrieved_at: "2026-09-16T10:00:00Z".into(),
            },
            policy: PolicyRef {
                policy_id: "POL-001".into(),
                version: "1.2".into(),
            },
            provenance: ProvenanceRef {
                parent_observation: None,
                causation_id: Some("EVT-1".into()),
                correlation_id: Some("COR-1".into()),
            },
        }
    }

    #[test]
    fn manifest_roundtrips_through_json() {
        let m = sample();
        let json = serde_json::to_string(&m).unwrap();
        let back: ObservationManifest = serde_json::from_str(&json).unwrap();
        assert_eq!(back, m);
    }

    #[test]
    fn content_address_must_be_encoded_in_raw_uri() {
        let m = sample();
        assert!(!m.is_content_addressed()); // uri does not contain sha256 yet
        let addr: String = m.sha256.clone();
        let addressed = ObservationManifest {
            raw_uri: format!("s3://bucket/obs/{addr}"),
            ..m
        };
        assert!(addressed.is_content_addressed());
    }

    #[test]
    fn validation_rejects_bad_sha256() {
        let mut m = sample();
        m.sha256 = "zz".repeat(32); // not hex
        assert_eq!(m.validate(), Err(ManifestError::InvalidSha256));
    }
}