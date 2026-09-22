//! Contract tests for the CollectionAdapter surface (T138, Phase A gate).

use cognitive_acq_contracts::source::{CapabilityGap, Selection, SourceRegistration, select};
use cognitive_acq_contracts::worker::{
    AcquisitionOutcome, AcquisitionTask, Capability, ExecutionClass,
};
use cognitive_acq_contracts::CollectionAdapter;

/// A stub "common crawl index" adapter standing in for an external engine.
struct FakeCommonCrawlAdapter;

#[async_trait::async_trait]
impl CollectionAdapter for FakeCommonCrawlAdapter {
    fn source_type(&self) -> &'static str {
        "common_crawl"
    }

    fn capabilities(&self) -> Vec<Capability> {
        vec!["bulk".into(), "archive".into(), "parquet".into(), "range-read".into()]
    }

    fn execution_class(&self) -> ExecutionClass {
        ExecutionClass::Dataset
    }

    async fn estimate(&self, task: &cognitive_acq_contracts::worker::AcquisitionTask) -> anyhow::Result<cognitive_acq_contracts::worker::CostEstimate> {
        Ok(cognitive_acq_contracts::worker::CostEstimate {
            predicted_bytes: task.max_bytes as u64,
            predicted_ms: task.timeout_ms,
            network_cost: 0.5,
            compute_cost: 0.0,
            verdict: cognitive_acq_contracts::worker::EffortVerdict::Acceptable,
        })
    }

    async fn execute(&self, task: &AcquisitionTask) -> anyhow::Result<AcquisitionOutcome> {
        Ok(AcquisitionOutcome {
            task_id: task.task_id.clone(),
            status: "completed".into(),
            sha256: "cd".repeat(32),
            size: task.max_bytes,
            content_type: Some("application/x-warc".into()),
            duration_ms: 40,
            raw_ref: None,
        })
    }
}

fn task() -> AcquisitionTask {
    AcquisitionTask {
        task_id: "T-cc-1".into(),
        uri: "https://index.commoncrawl.org/index?url=x".into(),
        tenant_id: "default".into(),
        investigation_id: None,
        source_id: Some("SRC-cc".into()),
        work_id: None,
        region: None,
        max_bytes: 1_000_000,
        timeout_ms: 30_000,
        required_capabilities: vec!["bulk".into(), "parquet".into()],
        user_agent: "cognitive-contract/0.1".into(),
    }
}

#[tokio::test]
async fn adapter_declares_source_type_capabilities_and_class() {
    let adapter = FakeCommonCrawlAdapter;
    assert_eq!(adapter.source_type(), "common_crawl");
    assert_eq!(adapter.execution_class(), ExecutionClass::Dataset);
    let caps = adapter.capabilities();
    assert!(caps.iter().any(|c| c.as_str() == "range-read"));
}

#[tokio::test]
async fn adapter_observation_boundary_outcome_has_no_raw_ref() {
    // The adapter produces bytes + metadata; it must NOT write storage itself.
    let adapter = FakeCommonCrawlAdapter;
    let outcome = adapter.execute(&task()).await.unwrap();
    assert_eq!(outcome.status, "completed");
    assert_eq!(outcome.content_type.as_deref(), Some("application/x-warc"));
    assert!(outcome.raw_ref.is_none());
}

#[test]
fn registry_selects_adapter_by_capability_intersection() {
    let reg = SourceRegistration {
        source_type: "common_crawl".into(),
        execution_class: ExecutionClass::Dataset,
        capabilities: vec!["bulk".into(), "archive".into(), "parquet".into()],
    };
    let required: Vec<Capability> = vec!["bulk".into(), "parquet".into()];
    match select(&required, [&reg]) {
        Selection::Matched(m) => assert_eq!(m.source_type, "common_crawl"),
        Selection::Gap(_) => panic!("capabilities must intersect"),
    }
}

#[test]
fn registry_reports_gap_when_capabilities_missing() {
    let reg = SourceRegistration {
        source_type: "plain-http".into(),
        execution_class: ExecutionClass::Http,
        capabilities: vec!["http".into()],
    };
    let required: Vec<Capability> = vec!["http".into(), "screenshot".into()];
    match select(&required, [&reg]) {
        Selection::Matched(_) => panic!("must not match without screenshot"),
        Selection::Gap(g) => {
            assert!(g.missing.iter().any(|c| c.as_str() == "screenshot"));
            let typed: CapabilityGap = g;
            assert_eq!(typed.missing.len(), 1);
        }
    }
}