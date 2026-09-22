//! CollectionAdapter — the only surface external engines touch (T089, R-09).
//!
//! External engines (Heritrix, Browsertrix, StormCrawler, Nutch, Crawlee/Scrapy,
//! Common Crawl, ...) are separate processes/services, never vendored into the
//! core. An adapter:
//!
//! 1. declares its source type + capabilities,
//! 2. estimates cost,
//! 3. executes, emitting **bytes + metadata only**.
//!
//! Enforcement rule: adapters MUST NOT write to Postgres, Neo4j, OpenSearch,
//! ClickHouse, Iceberg, or emit events directly — everything converges on the
//! single Observation Gate (Constitution gate).

use async_trait::async_trait;

use super::worker::{
    AcquisitionOutcome, AcquisitionTask, Capability, CostEstimate, ExecutionClass,
};

/// Adapter wrapping an external collection engine.
#[async_trait]
pub trait CollectionAdapter: Send + Sync {
    /// Stable source type, e.g. `"common_crawl"`, `"heritrix"`, `"rss"`.
    fn source_type(&self) -> &'static str;

    /// Declared capability surface (used for capability matching).
    fn capabilities(&self) -> Vec<Capability>;

    /// Preferred execution class for this adapter when it handles a task.
    fn execution_class(&self) -> ExecutionClass;

    /// Cost estimate for scheduler decision-making.
    async fn estimate(&self, task: &AcquisitionTask) -> anyhow::Result<CostEstimate>;

    /// Execute the task against the external engine and return bytes/metadata.
    async fn execute(&self, task: &AcquisitionTask) -> anyhow::Result<AcquisitionOutcome>;
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::worker::EffortVerdict;

    struct Stub;

    #[async_trait]
    impl CollectionAdapter for Stub {
        fn source_type(&self) -> &'static str {
            "test_source"
        }

        fn capabilities(&self) -> Vec<Capability> {
            vec!["bulk".into(), "parquet".into()]
        }

        fn execution_class(&self) -> ExecutionClass {
            ExecutionClass::Dataset
        }

        async fn estimate(&self, _task: &AcquisitionTask) -> anyhow::Result<CostEstimate> {
            Ok(CostEstimate {
                predicted_bytes: 0,
                predicted_ms: 0,
                network_cost: 0.0,
                compute_cost: 0.0,
                verdict: EffortVerdict::Cheap,
            })
        }

        async fn execute(&self, _task: &AcquisitionTask) -> anyhow::Result<AcquisitionOutcome> {
            Ok(AcquisitionOutcome {
                task_id: "T-1".into(),
                status: "completed".into(),
                sha256: "abc".repeat(8),
                size: 0,
                content_type: None,
                duration_ms: 1,
                raw_ref: None,
            })
        }
    }

    #[tokio::test]
    async fn adapter_declares_source_and_capabilities() {
        let stub = Stub;
        assert_eq!(stub.source_type(), "test_source");
        assert_eq!(stub.execution_class(), ExecutionClass::Dataset);
        let caps = stub.capabilities();
        assert!(caps.iter().any(|c| c.as_str() == "parquet"));
    }

    #[tokio::test]
    async fn adapter_executes_to_an_outcome() {
        let stub = Stub;
        let outcome = stub
            .execute(&AcquisitionTask {
                task_id: "T-1".into(),
                uri: "s3://nope".into(),
                tenant_id: "default".into(),
                investigation_id: None,
                source_id: None,
                work_id: None,
                region: None,
                max_bytes: 1024,
                timeout_ms: 1000,
                required_capabilities: vec![],
                user_agent: "cognitive-test/0.1".into(),
            })
            .await
            .unwrap();
        assert_eq!(outcome.status, "completed");
        assert_eq!(outcome.raw_ref, None); // gate-absent, not engine-written
    }
}