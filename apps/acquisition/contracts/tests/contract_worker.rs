//! Contract tests for the async AcquisitionWorker v2 surface (T137, Phase A gate).

use cognitive_acq_contracts::worker::{
    AcquisitionOutcome, AcquisitionTask, Capability, CostEstimate, EffortVerdict,
    ExecutionClass, WorkerSpec,
};
use cognitive_acq_contracts::AcquisitionWorker;

struct FakeHttp {
    spec: WorkerSpec,
}

#[async_trait::async_trait]
impl AcquisitionWorker for FakeHttp {
    fn capabilities(&self) -> Vec<Capability> {
        self.spec.capabilities.clone()
    }

    fn execution_class(&self) -> ExecutionClass {
        self.spec.execution_class
    }

    async fn estimate(&self, task: &AcquisitionTask) -> anyhow::Result<CostEstimate> {
        Ok(CostEstimate {
            predicted_bytes: task.max_bytes as u64,
            predicted_ms: task.timeout_ms,
            network_cost: 0.1,
            compute_cost: 0.0,
            verdict: EffortVerdict::Cheap,
        })
    }

    async fn acquire(&self, task: &AcquisitionTask) -> anyhow::Result<AcquisitionOutcome> {
        Ok(AcquisitionOutcome {
            task_id: task.task_id.clone(),
            status: "completed".into(),
            sha256: "ab".repeat(32),
            size: task.max_bytes,
            content_type: Some("text/html".into()),
            duration_ms: 12,
            raw_ref: None, // gate fills this; worker must not invent storage
        })
    }
}

fn task() -> AcquisitionTask {
    AcquisitionTask {
        task_id: "T-1".into(),
        uri: "http://fixtures.local/".into(),
        tenant_id: "default".into(),
        investigation_id: Some("INV-1".into()),
        source_id: Some("SRC-1".into()),
        work_id: Some("W-1".into()),
        region: Some("eu-west".into()),
        max_bytes: 1024,
        timeout_ms: 5_000,
        required_capabilities: vec!["http".into(), "get".into()],
        user_agent: "cognitive-contract/0.1".into(),
    }
}

#[tokio::test]
async fn worker_declares_execution_class_and_capabilities() {
    let worker = FakeHttp {
        spec: WorkerSpec {
            execution_class: ExecutionClass::Http,
            capabilities: vec!["http".into(), "get".into()],
        },
    };
    assert_eq!(worker.execution_class(), ExecutionClass::Http);
    assert!(worker.capabilities().iter().any(|c| c.as_str() == "get"));
}

#[tokio::test]
async fn worker_runs_on_a_shared_runtime_without_block_on() {
    let worker = FakeHttp {
        spec: WorkerSpec {
            execution_class: ExecutionClass::Http,
            capabilities: vec!["http".into()],
        },
    };
    // Multiple in-flight acquires prove the trait is async and Send+Sync
    // (callable from the multi-threaded runtime, no per-call block_on).
    let worker = std::sync::Arc::new(worker);
    let handles: Vec<_> = (0..100)
        .map(|i| {
            let mut t = task();
            t.task_id = format!("T-{i}");
            let w = std::sync::Arc::clone(&worker);
            tokio::spawn(async move { w.acquire(&t).await.unwrap() })
        })
        .collect();
    for h in handles {
        let outcome = h.await.unwrap();
        assert_eq!(outcome.status, "completed");
        assert!(outcome.raw_ref.is_none()); // Observation-boundary contract
    }
}

#[tokio::test]
async fn worker_supplies_cost_estimate_for_scheduling() {
    let worker = FakeHttp {
        spec: WorkerSpec {
            execution_class: ExecutionClass::Http,
            capabilities: vec!["http".into()],
        },
    };
    let estimate = worker.estimate(&task()).await.unwrap();
    assert_eq!(estimate.verdict, EffortVerdict::Cheap);
    assert_eq!(estimate.predicted_bytes, 1024);
}