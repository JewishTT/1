//! HTTP worker implementing the AcquisitionWorker v2 async contract (T088, R-10).
//!
//! Contract surface: `capabilities() / execution_class() / estimate(task) /
//! acquire(task)`, async, running on the caller's Tokio runtime (no
//! `runtime.block_on` on the hot path). On success, returns bytes + metadata;
//! raw bytes are NOT stored here — the Observation Gate owns storage semantics
//! (Constitution gate).

use std::time::{SystemTime, UNIX_EPOCH};

use anyhow::{bail, Result};
use cognitive_acq_contracts::worker::{
    AcquisitionOutcome, AcquisitionTask, Capability, CostEstimate, EffortVerdict,
    ExecutionClass,
};
use cognitive_acq_contracts::AcquisitionWorker;
use sha2::{Digest, Sha256};

fn now_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis() as u64)
        .unwrap_or(0)
}

/// HTTP worker using reqwest; respects timeout + size caps (FR-029 security limits).
pub struct HttpWorker {
    client: reqwest::Client,
    max_bytes: usize,
    timeout_ms: u64,
}

impl Default for HttpWorker {
    fn default() -> Self {
        let client = reqwest::Client::builder()
            .timeout(std::time::Duration::from_secs(30))
            .build()
            .unwrap();
        HttpWorker {
            client,
            max_bytes: 10 * 1024 * 1024,
            timeout_ms: 30_000,
        }
    }
}

impl HttpWorker {
    pub fn new(client: reqwest::Client, max_bytes: usize, timeout_ms: u64) -> Self {
        HttpWorker {
            client,
            max_bytes,
            timeout_ms,
        }
    }

    fn sha256(body: &[u8]) -> String {
        let mut hasher = Sha256::new();
        hasher.update(body);
        let out = hasher.finalize();
        format!("{:x}", out)
    }
}

#[async_trait::async_trait]
impl AcquisitionWorker for HttpWorker {
    fn capabilities(&self) -> Vec<Capability> {
        vec![
            Capability::new("http"),
            Capability::new("get"),
            Capability::new("headers"),
            Capability::new("etag"),
            Capability::new("last-modified"),
            Capability::new("content-addressed"),
        ]
    }

    fn execution_class(&self) -> ExecutionClass {
        ExecutionClass::Http
    }

    async fn estimate(&self, task: &AcquisitionTask) -> Result<CostEstimate> {
        // Expected cost in normalized units (per R-09 execution-class pricing).
        let predicted_bytes = task.max_bytes as u64;
        let predicted_ms = task.timeout_ms;
        Ok(CostEstimate {
            predicted_bytes,
            predicted_ms,
            network_cost: 0.001 + (task.max_bytes as f64) / (10_000_000.0),
            compute_cost: 0.0,
            verdict: if task.max_bytes <= 1_000_000 {
                EffortVerdict::Cheap
            } else {
                EffortVerdict::Acceptable
            },
        })
    }

    async fn acquire(&self, task: &AcquisitionTask) -> Result<AcquisitionOutcome> {
        if task.max_bytes > self.max_bytes {
            bail!("max_bytes exceeds worker cap {}", self.max_bytes);
        }
        let start = now_ms();
        let deadline = std::time::Duration::from_millis(task.timeout_ms.min(self.timeout_ms));

        let resp = self
            .client
            .get(&task.uri)
            .header("user-agent", &task.user_agent)
            .timeout(deadline)
            .send()
            .await?;

        let status = resp.status();
        let content_type = resp
            .headers()
            .get(reqwest::header::CONTENT_TYPE)
            .and_then(|v| v.to_str().ok())
            .map(|s| s.to_string());
        let body = resp.bytes().await?;
        if body.len() > task.max_bytes {
            bail!("response exceeds size limit");
        }

        let digest = Self::sha256(&body);
        let outcome_status = if status.is_success() {
            "completed".to_string()
        } else if status.as_u16() == 304 {
            "unchanged".to_string()
        } else {
            bail!("http status {}", status);
        };

        Ok(AcquisitionOutcome {
            task_id: task.task_id.clone(),
            status: outcome_status,
            sha256: digest,
            size: body.len(),
            content_type,
            duration_ms: now_ms() - start,
            raw_ref: None, // Observation Gate fills this after content-addressed storage
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use sha2::Digest;

    fn fake() -> AcquisitionTask {
        AcquisitionTask {
            task_id: "T-1".into(),
            uri: "http://fixtures.local/index.html".into(),
            tenant_id: "default-tenant".into(),
            investigation_id: None,
            source_id: None,
            work_id: None,
            region: None,
            max_bytes: 1_000_000,
            timeout_ms: 5_000,
            required_capabilities: vec![Capability::new("http")],
            user_agent: "cognitive-test/0.1".into(),
        }
    }

    #[test]
    fn capabilities_include_http_and_content_addressing() {
        let w = HttpWorker::default();
        let caps = w.capabilities();
        assert!(caps.iter().any(|c| c.as_str() == "content-addressed"));
        assert!(caps.iter().any(|c| c.as_str() == "etag"));
    }

    #[test]
    fn execution_class_is_http() {
        assert_eq!(HttpWorker::default().execution_class(), ExecutionClass::Http);
    }

    #[tokio::test]
    async fn estimate_is_positive_units() {
        let w = HttpWorker::default();
        let est = w.estimate(&fake()).await.unwrap();
        assert!(est.network_cost > 0.0);
        assert_eq!(est.verdict, EffortVerdict::Cheap);
    }

    #[test]
    fn sha256_matches_known_digest() {
        let body = b"hello cognitive";
        let mut hasher = Sha256::new();
        hasher.update(body);
        let expected = format!("{:x}", hasher.finalize());
        assert_eq!(HttpWorker::sha256(body), expected);
    }
}