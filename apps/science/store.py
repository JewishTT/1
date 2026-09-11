"""In-memory, event-replayable state store (T088, Constitution I-12).

The Scientific Intelligence Fabric projects its current state (claims,
hypotheses, calibration reports, …) purely from ``science.*`` envelopes — the
store never invents state. ``apply`` upserts a record keyed by the event's
deterministic entity id and merges refs-only payload fields, so the log
fully determines the snapshot (``rebuild`` reproduces it exactly). The API
mirrors ``shared.storage`` semantics; swapping to a durable kernel keeps the
same contract (Constitution V — plugability by contract).
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from events.kafka import Envelope

# event_type -> (collection, deterministic id field in the payload)
ENTITY_BY_EVENT: dict[str, tuple[str, str]] = {
    "science.claim.registered": ("claims", "claim_id"),
    "science.claim.status_changed": ("claims", "claim_id"),
    "science.claim.discarded": ("claims", "claim_id"),
    "science.claim.scope_rejected": ("scope_audit", "event_id"),
    "science.hypothesis.proposed": ("hypotheses", "hypothesis_id"),
    "science.hypothesis.evidence_attached": ("hypotheses", "hypothesis_id"),
    "science.hypothesis.status_changed": ("hypotheses", "hypothesis_id"),
    "science.hypothesis.discarded": ("hypotheses", "hypothesis_id"),
    "science.calibration.report": ("calibration", "report_id"),
    "science.causal.classified": ("causal", "conclusion_id"),
    "science.causal.scope_rejected": ("scope_audit", "event_id"),
    "science.temporal.change_point": ("temporal", "series_id"),
    "science.structure.analyzed": ("structure", "result_id"),
    "science.robustness.report": ("robustness", "report_id"),
    "science.experiment.run": ("experiments", "run_id"),
    "science.experiment.reproduction": ("experiments", "run_id"),
    "science.review.commented": ("reviews", "event_id"),
    "science.review.status_changed": ("reviews", "event_id"),
}


class ScienceStore:
    """Append-only event log + last-state projections (I-12 rebuildable)."""

    def __init__(self) -> None:
        self._collections: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
        self._log: list[Envelope] = []

    # -- event plumbing -----------------------------------------------------
    def apply(self, envelope: Envelope) -> dict[str, Any]:
        """Project one envelope: upsert the entity record by deterministic id."""
        collection, id_field = ENTITY_BY_EVENT.get(
            envelope.event_type, ("events", "event_id")
        )
        payload = json.loads(envelope.payload.decode("utf-8"))
        record_id = payload.get(id_field) or envelope.event_id
        record = self._collections[collection].setdefault(record_id, {})
        for key, value in payload.items():
            record[key] = value
        if envelope.event_type.endswith(".status_changed") and payload.get("to_status"):
            record["status"] = payload["to_status"]
        if envelope.event_type == "science.hypothesis.evidence_attached":
            links = record.setdefault("evidence_links", [])
            link_id = payload.get("link_id")
            if link_id is not None and not any(
                existing.get("link_id") == link_id for existing in links
            ):
                links.append(
                    {
                        "link_id": link_id,
                        "observation_id": payload.get("observation_id", ""),
                        "direction": payload.get("direction", ""),
                        "weight": payload.get("weight", 0.0),
                    }
                )
        record.setdefault("_first_event", envelope.event_id)
        record["_updated_event"] = envelope.event_id
        record["_updated_at"] = envelope.produced_at
        if envelope.investigation_id:
            record["_project_id"] = envelope.investigation_id
        self._log.append(envelope)
        return record

    def rebuild(self, envelopes: list[Envelope]) -> None:
        """Reproduce the snapshot from an event stream (I-12)."""
        self.clear()
        for envelope in envelopes:
            self.apply(envelope)

    # -- read API -----------------------------------------------------------
    def get(self, collection: str, record_id: str) -> dict[str, Any] | None:
        return self._collections.get(collection, {}).get(record_id)

    def all(self, collection: str) -> list[dict[str, Any]]:
        return list(self._collections.get(collection, {}).values())

    def list(self, collection: str) -> list[str]:
        return list(self._collections.get(collection, {}).keys())

    def count(self, collection: str) -> int:
        return len(self._collections.get(collection, {}))

    def clear(self) -> None:
        self._collections.clear()
        self._log = []

    # -- write API (non-event, for tests/services constructing envelopes) ---
    def put(self, collection: str, record_id: str, record: dict[str, Any]) -> dict[str, Any]:
        return self._collections[collection].__setitem__(record_id, record) or record

    # -- introspection ------------------------------------------------------
    @property
    def log_len(self) -> int:
        return len(self._log)

    @property
    def collections(self) -> list[str]:
        return sorted(self._collections)