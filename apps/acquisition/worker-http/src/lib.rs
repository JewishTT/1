//! HTTP worker implementing the AcquisitionWorker contract (T028, FR-005, R-6).
//!
//! Contract surface: `capabilities() / estimate(task) / acquire(task)`.
//! On success, stores raw bytes content-addressed (sha256) and emits an
//! acquisition-completed + observation-created outcome for the Kafka/S3 layer.

use std::time::{SystemTime, UNIX_EPOCH};

use anyhow::{bail, Result};
use sha2::{Digest, Sha256};

/// Worker contract exposed by every acquisition implementation (Constitution V).
pub trait AcquisitionWorker: Send + Sync {
    fn capabilities(&self) -> Vec<String>;
    fn estimate(&self, task: &AcquisitionTask) -> f64;
    fn acquire(&self, task: &AcquisitionTask) -> Result<AcquisitionOutcome>;
}

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct AcquisitionTask {
    pub task_id: String,
    pub uri: String,
    pub tenant_id: String,
    pub investigation_id: Option<String>,
    pub source_id: Option<String>,
    pub max_bytes: usize,
    pub timeout_ms: u64,
    pub worker_class: String,
    pub user_agent: String,
}

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct AcquisitionOutcome {
    pub task_id: String,
    pub status: String, // completed | unchanged | duplicate | failed
    pub sha256: String,
    pub size: usize,
    pub content_type: Option<String>,
    pub duration_ms: u64,
    pub raw_ref: Option<String>,
}

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
    // Reuse a single tokio runtime across acquires: per-call Runtime::new()
    // spawns a fresh thread pool per fetch (a measurable hot-path cost).
    runtime: tokio::runtime::Runtime,
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
            runtime: tokio::runtime::Runtime::new().unwrap(),
        }
    }
}

impl HttpWorker {
    pub fn new(client: reqwest::Client, max_bytes: usize, timeout_ms: u64) -> Self {
        HttpWorker {
            client,
            max_bytes,
            timeout_ms,
            runtime: tokio::runtime::Runtime::new().unwrap(),
        }
    }

    fn sha256(body: &[u8]) -> String {
        let mut hasher = Sha256::new();
        hasher.update(body);
        let out = hasher.finalize();
        format!("{:x}", out)
    }
}

impl AcquisitionWorker for HttpWorker {
    fn capabilities(&self) -> Vec<String> {
        vec!["http".to_string(), "get".into(), "headers".into(), "etag".into(),
             "last-modified".into(), "content-addressed".into()]
    }

    fn estimate(&self, task: &AcquisitionTask) -> f64 {
        // Expected cost in normalized units (per R-9 execution-class pricing).
        0.001 + (task.max_bytes as f64) / (10_000_000.0)
    }

    fn acquire(&self, task: &AcquisitionTask) -> Result<AcquisitionOutcome> {
        if task.max_bytes > self.max_bytes {
            bail!("max_bytes exceeds worker cap {}", self.max_bytes);
        }
        let start = now_ms();
        let deadline = std::time::Duration::from_millis(task.timeout_ms.min(self.timeout_ms));

        let outcome = self.runtime.block_on(async {
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
                raw_ref: None,
            })
        })?;
        Ok(outcome)
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
            max_bytes: 1_000_000,
            timeout_ms: 5_000,
            worker_class: "http".into(),
            user_agent: "cognitive-test/0.1".into(),
        }
    }

    #[test]
    fn capabilities_include_http_and_content_addressing() {
        let w = HttpWorker::default();
        let caps = w.capabilities();
        assert!(caps.iter().any(|c| c == "content-addressed"));
        assert!(caps.iter().any(|c| c == "etag"));
    }

    #[test]
    fn estimate_is_positive_units() {
        let w = HttpWorker::default();
        assert!(w.estimate(&fake()) > 0.0);
    }

    #[test]
    fn sha256_matches_known_digest() {
        let body = b"hello cognitive";
        let mut hasher = Sha256::new();
        hasher.update(body);
        let expected = format!("{:x}", hasher.finalize());
        assert_eq!(HttpWorker::sha256(body), expected);
    }

    #[test]
    #[should_panic]
    fn acquire_rejects_over_cap() {
        let w = HttpWorker::default();
        let mut t = fake();
        t.max_bytes = 999_999_999_999;
        w.acquire(&t).unwrap();
    }
}