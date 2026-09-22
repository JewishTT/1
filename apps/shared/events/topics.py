"""Full event/topic catalog (Spec FR-023, R-7).

One topic per canonical event type; consumers are idempotent on
``event_id`` / ``task_id`` / ``observation_id`` (I-11, R-7). Kafka never
carries raw blobs — payloads carry refs (I-5).
"""

from __future__ import annotations

EVENT_CATALOG: dict[str, str] = {
    # Investigation (control plane)
    "investigation.created": "investigation",
    "investigation.updated": "investigation",
    "investigation.started": "investigation",
    "investigation.paused": "investigation",
    "investigation.resumed": "investigation",
    "investigation.completed": "investigation",
    "investigation.archived": "investigation",
    # Discovery / frontier
    "discovery.seed": "discovery",
    "discovery.discovered": "discovery",
    "frontier.enqueued": "frontier",
    # Acquisition
    "acquisition.assigned": "acquisition",
    "acquisition.request": "acquisition",
    "acquisition.outcome": "acquisition",
    "acquisition.completed": "acquisition",
    "acquisition.failed": "acquisition",
    "observation.created": "observation",
    "observation.changed": "observation",
    "observation.unchanged": "observation",
    "observation.duplicate": "observation",
    # Interpretation
    "mention.created": "interpretation",
    "candidate.created": "interpretation",
    "assertion.created": "interpretation",
    # Admission / resolution
    "admission.decided": "admission",
    "entity.resolved": "admission",
    "entity.version_created": "admission",
    "evidence.link_created": "admission",
    # Resolution candidates (feature 005: donor-core-subsystems, OpenOSINT)
    "resolution.candidate_created": "resolution",
    "resolution.candidate_decided": "resolution",
    "resolution.merge_recorded": "resolution",
    # Projections
    "graph.projected": "projection",
    "graph.snapshot_created": "projection",
    "graph.snapshot_rebuilt": "projection",
    "search.projected": "projection",
    "analytics.projected": "projection",
    "projection.completed": "projection",
    # TDA
    "tda.completed": "tda",
    # Findings / feedback (three-way split, T116-T118)
    "finding.created": "knowledge",
    "feedback.generated": "feedback",
    "feedback.source": "feedback",
    "feedback.entity": "feedback",
    "feedback.system": "feedback",
    # Donor patterns (feature 002: donor-pattern-integration)
    "statement.created": "statement",
    "correlation.edge_created": "correlation",
    "evidence.independence_fused": "evidence",
    "evidence.manifest_created": "evidence",
    "review.recorded": "review",
    "review.replayed": "review",
    "connector.registered": "connector",
    "connector.status_changed": "connector",
    "recon.plan_started": "recon",
    "recon.plan_completed": "recon",
    "ontology.registered": "ontology",
    "claim.assessed": "claim",
    # Atomic entity fabric (feature 009: stream-first, process-centric)
    "entity.stream.appended": "entity-stream",
    "entity.state.projected": "entity-stream",
    "entity.series.projected": "entity-stream",
    "hyperedge.created": "hypergraph",
    "hyperedge.temporal_version_created": "hypergraph",
    "hyperedge.expired": "hypergraph",
    # Governance / ops (audit, budgets)
    "policy.budget_exceeded": "governance",
    "audit.access": "governance",
    "governance.quarantined": "governance",
    "governance.replayed": "governance",
    # Scientific Intelligence Fabric (feature 006: refs-only payloads, I-5)
    "science.claim.registered": "science",
    "science.claim.status_changed": "science",
    "science.claim.discarded": "science",
    "science.claim.scope_rejected": "science",
    "science.hypothesis.proposed": "science",
    "science.hypothesis.evidence_attached": "science",
    "science.hypothesis.status_changed": "science",
    "science.hypothesis.discarded": "science",
    "science.calibration.report": "science",
    "science.causal.classified": "science",
    "science.causal.scope_rejected": "science",
    "science.temporal.change_point": "science",
    "science.structure.analyzed": "science",
    "science.robustness.report": "science",
    "science.experiment.run": "science",
    "science.experiment.reproduction": "science",
    "science.review.commented": "science",
    "science.review.status_changed": "science",
    # Zero-layer contact harvesting (feature 010)
    "zero_layer.seed_detected": "zero_layer",
    "zero_layer.harvest_started": "zero_layer",
    "zero_layer.observation": "zero_layer",
    "zero_layer.harvest_cycle_complete": "zero_layer",
    "zero_layer.enrichment": "zero_layer",
    "zero_layer.feedback_seeds": "zero_layer.feedback_seeds",
}

# Dead-letter / quarantine lanes (best-effort delivery + idempotency, R-7).
TOPIC_DLQ = "events.dlq"
TOPIC_QUARANTINE = "events.quarantine"

TOPICS = sorted(set(EVENT_CATALOG.values()) | {TOPIC_DLQ, TOPIC_QUARANTINE})

# Event types whose payload carries versioned protobuf (registry-validated).
def topic_for(event_type: str) -> str:
    try:
        return EVENT_CATALOG[event_type]
    except KeyError as exc:  # pragma: no cover - defensive
        raise UnknownEventTypeError(event_type) from exc


class UnknownEventTypeError(KeyError):
    pass