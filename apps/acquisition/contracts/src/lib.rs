//! Global Collection Fabric contracts (Phase A / T088-T089, T090, T129).
//!
//! One contract → any collector. These crates are the ONLY surface internal and
//! external engines touch. They define:
//!
//! - [`worker`]: async `AcquisitionWorker` v2 (capability/estimate/acquire)
//! - [`adapter`]: `CollectionAdapter` for external engines (Observation boundary)
//! - [`source`]: `SourceRegistration` + capability-intersection selection
//! - [`manifest`]: immutable `ObservationManifest` (bytes + metadata bridge)
//!
//! Constitution gates enforced here: capability-based selection (no `if source
//! == ...` routing), Postgres stays the authoritative frontier, projections stay
//! rebuildable, and workers never own storage semantics (Observation Gate does).

pub mod adapter;
pub mod manifest;
pub mod source;
pub mod worker;

pub use adapter::CollectionAdapter;
pub use manifest::ObservationManifest;
pub use source::{CapabilityGap, SourceRegistration, select};
pub use worker::{
    AcquisitionOutcome, AcquisitionTask, Capability, CostEstimate, EffortVerdict,
    ExecutionClass, WorkerSpec,
};

pub use worker::AcquisitionWorker;