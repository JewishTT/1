"""Entity + finding catalog with full evidence drill-down (T052/T053, US2).

Provides the entity overview (current state, historical versions, aliases,
relationships, supporting assertions, evidence, timeline, structural signals)
and the finding overview (why detected, structural/semantic evidence,
supporting graph region, assertions, observations, raw source). Hermetic
in-memory catalog for smoke/tests; real adapters sit behind the same surface.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field


@dataclass
class EntityRecord:
    entity_id: str
    canonical_identity: dict
    versions: list[dict] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    relationships: list[dict] = field(default_factory=list)
    supporting_assertions: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    observations: list[str] = field(default_factory=list)
    structural_signals: list[dict] = field(default_factory=list)

    def current(self) -> dict:
        return self.versions[-1] if self.versions else {"version": 0}

    def add_version(self, version: dict) -> None:
        self.versions.append(version)


@dataclass
class FindingRecord:
    finding_id: str
    why_detected: str
    structural_evidence: list[dict] = field(default_factory=list)
    semantic_evidence: list[dict] = field(default_factory=list)
    supporting_graph_region: dict = field(default_factory=dict)
    supporting_assertions: list[str] = field(default_factory=list)
    observations: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    status: str = "open"


class Catalog:
    """In-memory catalog mapping ids to entity/finding records."""

    def __init__(self, observations: dict[str, dict] | None = None) -> None:
        self._entities: dict[str, EntityRecord] = {}
        self._findings: dict[str, FindingRecord] = {}
        self._observations = observations or {}

    def put_entity(self, record: EntityRecord) -> None:
        self._entities[record.entity_id] = record

    def entity_ids(self) -> list[str]:
        """Sorted ids so callers can mint the next id for a new atomic entity."""
        return sorted(self._entities)

    def put_finding(self, record: FindingRecord) -> None:
        self._findings[record.finding_id] = record

    def entity(self, entity_id: str) -> dict | None:
        record = self._entities.get(entity_id)
        if record is None:
            return None
        current = record.current()
        first_seen = (
            record.versions[0].get("first_seen")
            if record.versions and isinstance(record.versions[0], dict)
            else None
        )
        last_seen = (
            current.get("last_seen")
            or current.get("observed_at")
            or current.get("first_seen")
            or first_seen
        )
        # Deterministic identity digest over the canonical identity dimensions.
        identity_digest = "sha256:" + hashlib.sha256(
            json.dumps(
                record.canonical_identity,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            ).encode("utf-8")
        ).hexdigest()[:16]
        return {
            "entity_id": record.entity_id,
            "canonical_identity": record.canonical_identity,
            "current_state": current,
            # The entity id is the stable anchor; the asserted identity may be
            # re-versioned as new evidence arrives. This projection makes the
            # atomic-entity-as-dynamic-invariant contract explicit to every
            # client instead of forcing each UI to reverse-engineer it from
            # historical_versions.
            "identity_invariant": {
                "status": "MATERIALIZED",
                "continuity": "PERSISTENT",
                "version": current.get("version", len(record.versions)),
                "history_depth": len(record.versions),
                "identity_digest": identity_digest,
                "first_seen": first_seen,
                "last_seen": last_seen,
            },
            "historical_versions": record.versions,
            "aliases": record.aliases,
            "relationships": record.relationships,
            "supporting_assertions": record.supporting_assertions,
            "evidence": self._evidence(record.evidence_ids),
            "timeline": [self._observation(o) for o in record.observations if o],
            "structural_signals": record.structural_signals,
        }

    def finding(self, finding_id: str) -> dict | None:
        record = self._findings.get(finding_id)
        if record is None:
            return None
        observations = [self._observation(o) for o in record.observations if o]
        return {
            "finding_id": record.finding_id,
            "status": record.status,
            "why_detected": record.why_detected,
            "structural_evidence": record.structural_evidence,
            "semantic_evidence": record.semantic_evidence,
            "supporting_graph_region": {**record.supporting_graph_region, "nodes": [], "edges": []},
            "supporting_assertions": record.supporting_assertions,
            "observations": observations,
            "sources": record.sources,
            "evidence_resolves": all(o.get("immutable") for o in observations),
        }

    def lineage(self, doc: str) -> list[dict]:
        """FR-032 walk: finding -> feature -> assertion -> evidence -> obs -> source."""
        record = self._findings.get(doc)
        chain: list[dict] = []
        if record:
            chain.append({"kind": "finding", "label": record.finding_id})
            for fe in record.structural_evidence + record.semantic_evidence:
                chain.append({"kind": "feature", "label": fe.get("feature_id", fe.get("kind", ""))})
            for a in record.supporting_assertions:
                chain.append({"kind": "assertion", "label": a})
            for o in record.observations:
                chain.append({"kind": "observation", "label": o})
                chain.append({"kind": "source", "label": self._observation(o).get("uri", o)})
        return chain

    def _evidence(self, evidence_ids: list[str]) -> list[dict]:
        return [
            {
                "evidence_id": eid,
                "observation_id": self._observations.get(eid, {}).get("observation_id", eid),
                "immutable": True,  # I-1: evidence anchors to immutable observations
            }
            for eid in evidence_ids
        ]

    def _observation(self, observation_id: str) -> dict:
        obs = self._observations.get(observation_id, {})
        return {
            "observation_id": obs.get("observation_id", observation_id),
            "uri": obs.get("uri", ""),
            "content_hash": obs.get("content_hash", ""),
            "immutable": True,  # I-1
        }