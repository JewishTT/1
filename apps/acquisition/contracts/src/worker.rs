//! AcquisitionWorker v2 — asynchronous acquisition contract (T088, FR-005).
//!
//! Replaces the sync `capabilities()/estimate()/acquire()` contract (previously
//! defined locally in `worker-http`) with an async trait run on a shared Tokio
//! runtime (thousands of in-flight tasks; no `runtime.block_on` on the hot
//! path). Selection is capability-based, never hard-coded routing (Constitution
//! gate).

use serde::{Deserialize, Serialize};

/// A worker/adapter capability, e.g. `http`, `javascript`, `dom`, `screenshot`,
/// `parquet`, `warc`, `range-read`, `bulk`, `content-addressed`.
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct Capability(String);

impl Capability {
    pub fn new(name: impl Into<String>) -> Self {
        Self(name.into())
    }

    pub fn as_str(&self) -> &str {
        &self.0
    }
}

impl std::fmt::Display for Capability {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.0)
    }
}

impl From<&str> for Capability {
    fn from(s: &str) -> Self {
        Self::new(s)
    }
}

impl From<String> for Capability {
    fn from(s: String) -> Self {
        Self::new(s)
    }
}

/// Execution classes for the Collection Fabric (replaces scalar `worker_class`).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum ExecutionClass {
    Http,
    Browser,
    Dataset,
    Archival,
    Feed,
    Api,
    Custom,
}

impl ExecutionClass {
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Http => "http",
            Self::Browser => "browser",
            Self::Dataset => "dataset",
            Self::Archival => "archival",
            Self::Feed => "feed",
            Self::Api => "api",
            Self::Custom => "custom",
        }
    }
}

impl std::fmt::Display for ExecutionClass {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(self.as_str())
    }
}

/// Static capability surface of a worker/adapter.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct WorkerSpec {
    pub execution_class: ExecutionClass,
    pub capabilities: Vec<Capability>,
}

/// Concrete collection request. Extends the v1 `AcquisitionTask` with the
/// capability/region/work bookkeeping the capability-matching scheduler needs.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AcquisitionTask {
    pub task_id: String,
    pub uri: String,
    pub tenant_id: String,
    pub investigation_id: Option<String>,
    pub source_id: Option<String>,
    pub work_id: Option<String>,
    pub region: Option<String>,
    pub max_bytes: usize,
    pub timeout_ms: u64,
    pub required_capabilities: Vec<Capability>,
    pub user_agent: String,
}

/// Verdict of a cost estimate, used by the resource scheduler (Stage B).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum EffortVerdict {
    Cheap,
    Acceptable,
    Expensive,
}

/// Expected cost of executing a task (R-09 execution-class pricing).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CostEstimate {
    pub predicted_bytes: u64,
    pub predicted_ms: u64,
    pub network_cost: f64,
    pub compute_cost: f64,
    pub verdict: EffortVerdict,
}

/// Result of a single acquisition. `raw_ref` is filled by the Observation Gate
/// after content-addressed storage; workers themselves MUST NOT define storage
/// semantics (Constitution gate: single Observation Gate).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AcquisitionOutcome {
    pub task_id: String,
    pub status: String, // completed | unchanged | duplicate | failed
    pub sha256: String,
    pub size: usize,
    pub content_type: Option<String>,
    pub duration_ms: u64,
    pub raw_ref: Option<String>,
}

/// AcquisitionWorker v2 — async contract implemented by every internal worker.
#[async_trait::async_trait]
pub trait AcquisitionWorker: Send + Sync {
    /// Declared capability surface used for capability matching (T091).
    fn capabilities(&self) -> Vec<Capability>;

    /// Execution class of this worker (source of `worker_class` routing).
    fn execution_class(&self) -> ExecutionClass;

    /// Cost estimate for scheduling (Stage A/B). Should be cheap to compute.
    async fn estimate(&self, task: &AcquisitionTask) -> anyhow::Result<CostEstimate>;

    /// Execute the task. Produces bytes + metadata; raw bytes are NOT stored
    /// here — they flow to the Observation Gate.
    async fn acquire(&self, task: &AcquisitionTask) -> anyhow::Result<AcquisitionOutcome>;
}

/// Convenience: a fully static spec for workers that declare it at construction.
pub trait DeclaresSpec: Send + Sync {
    fn spec(&self) -> &WorkerSpec;
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn capability_wraps_and_roundtrips() {
        let cap = Capability::new("javascript");
        assert_eq!(cap.as_str(), "javascript");
        assert_eq!(cap.to_string(), "javascript");
        assert_eq!(serde_json::to_string(&cap).unwrap(), "\"javascript\"");
    }

    #[test]
    fn execution_class_display() {
        assert_eq!(ExecutionClass::Dataset.as_str(), "dataset");
        assert_eq!(ExecutionClass::Custom.to_string(), "custom");
    }

    #[test]
    fn task_roundtrips_through_json() {
        let task = AcquisitionTask {
            task_id: "T-1".into(),
            uri: "http://x.local/".into(),
            tenant_id: "default".into(),
            investigation_id: None,
            source_id: None,
            work_id: Some("W-1".into()),
            region: Some("eu-west".into()),
            max_bytes: 1024,
            timeout_ms: 5000,
            required_capabilities: vec!["http".into(), "get".into()],
            user_agent: "cognitive-test/0.1".into(),
        };
        let json = serde_json::to_string(&task).unwrap();
        let back: AcquisitionTask = serde_json::from_str(&json).unwrap();
        assert_eq!(back.task_id, task.task_id);
        assert_eq!(back.region, Some("eu-west".to_string()));
        assert_eq!(back.required_capabilities.len(), 2);
    }
}