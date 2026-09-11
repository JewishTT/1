"""Evidence manifest chain (feature 005 US3): Finding → Evidence → Observation → Raw.

NetForensicAI-style immutable evidence ledger: every parsed observation traces
back to the raw SHA-256 of the byte stream it was parsed from, so projections
can verify integrity end-to-end and a human or reviewer can always name the
exact raw source of a statement (FR-010, evidence provenance).

   Source repo : donors/NetForensicAI/netforensicai/core/evidence.py
   License     : MIT
   What changed: sha256 streaming (NetForensicAI ``sha256_of_file``) is ported as
                 ``sha256_of_bytes`` (in-memory payload + chunked file-like reads);
                 the on-disk EvidenceManager is NOT ported — COGNITIVE chains to
                 the raw sha256 of the delivered observation payload, leaving blob
                 storage to the acquisition agent (data stays refs-only, I-5).
                 Manifest records are frozen dataclasses; ``build_manifest`` emits
                 ``evidence.manifest_created`` whenever a producer is supplied.

Chain invariants (all refs, no blobs):

    finding_id  →  evidence_id  →  observation_id  →  raw_sha256

``EvidenceManifest.chain()`` returns that ordered tuple; consumers verifying a
replayed observation recompute ``sha256_of_bytes`` against the manifest and
abort if the digests disagree.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from events.kafka import build_envelope
from events.topics import topic_for

HASH_CHUNK_SIZE = 1024 * 1024


def sha256_of_bytes(data: bytes | bytearray | memoryview | Any) -> str:
    """SHA-256 of an observation payload, chunked so file-like inputs stream.

    Mirrors NetForensicAI's streaming guarantee: a multi-gigabyte evidence file
    never needs to fit in memory; in-memory byte payloads hash directly.
    """
    digest = hashlib.sha256()
    if isinstance(data, (bytes, bytearray, memoryview)):
        digest.update(bytes(data))
        return digest.hexdigest()
    while True:
        chunk = data.read(HASH_CHUNK_SIZE)
        if not chunk:
            break
        digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class Finding:
    """A reviewable finding anchored to evidence (reusable across parses).

    ``finding_id`` is deterministic-stable per ``kind:value:offset`` so the same
    extraction re-manifests with the same id (dedup key, I-11).
    """

    kind: str
    value: str
    offset: int = 0
    meta: dict[str, Any] = field(default_factory=dict)
    finding_id: str = ""

    def __post_init__(self) -> None:
        if not self.finding_id:
            stable = f"{self.kind}:{self.value}:{self.offset}"
            digest = hashlib.sha256(stable.encode("utf-8")).hexdigest()[:16]
            object.__setattr__(self, "finding_id", f"F-{digest}")

    def to_dict(self) -> dict:
        return {
            "finding_id": self.finding_id,
            "kind": self.kind,
            "value": self.value,
            "offset": self.offset,
            "meta": dict(self.meta),
        }


@dataclass(frozen=True)
class EvidenceManifest:
    """Immutable chain record: finding → evidence → observation → raw sha256."""

    manifest_id: str
    finding_id: str
    evidence_id: str
    observation_id: str
    raw_sha256: str
    created_at: str
    producer: str
    producer_version: str
    tenant_id: str = "default-tenant"

    def chain(self) -> tuple[str, str, str, str]:
        return (self.finding_id, self.evidence_id, self.observation_id, self.raw_sha256)

    def to_dict(self) -> dict:
        return {
            "manifest_id": self.manifest_id,
            "chain": list(self.chain()),
            "created_at": self.created_at,
            "producer": self.producer,
            "producer_version": self.producer_version,
            "tenant_id": self.tenant_id,
        }


class ManifestError(ValueError):
    """Invalid manifest request: missing ids, computed digest mismatch handling."""


def build_manifest(
    *,
    finding: Finding,
    evidence_id: str,
    observation_id: str,
    raw_sha256: str | None = None,
    raw: bytes | None = None,
    tenant_id: str = "default-tenant",
    producer=None,
    producer_version: str = "0.1.0",
) -> EvidenceManifest:
    """Build an immutable EvidenceManifest and emit ``evidence.manifest_created``.

    Exactly one integrity source is allowed: ``raw_sha256`` (already computed) or
    ``raw`` bytes to hash now. The chain is (finding, evidence, observation, raw
    sha256); every element is a ref — never the payload itself (I-5). When a
    ``producer`` is supplied, one envelope is produced on the ``evidence`` topic.
    """
    if raw_sha256 is not None and raw is not None:
        raise ManifestError("supply raw_sha256 or raw, not both")
    if raw_sha256 is None:
        if raw is None:
            raise ManifestError("raw_sha256 or raw is required")
        raw_sha256 = sha256_of_bytes(raw)
    if not evidence_id or not observation_id:
        raise ManifestError("evidence_id and observation_id are required")

    manifest = EvidenceManifest(
        manifest_id="M-" + uuid.uuid4().hex[:12],
        finding_id=finding.finding_id,
        evidence_id=evidence_id,
        observation_id=observation_id,
        raw_sha256=raw_sha256,
        created_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        producer="interpretation.manifest",
        producer_version=producer_version,
        tenant_id=tenant_id,
    )
    if producer is not None:
        envelope = manifest_envelope(manifest)
        producer.produce(
            topic_for("evidence.manifest_created"),
            envelope,
            key=manifest.manifest_id,
        )
    return manifest


def manifest_envelope(manifest: EvidenceManifest) -> Any:
    """Build the ``evidence.manifest_created`` envelope (refs-only chain, I-5)."""
    return build_envelope(
        event_type="evidence.manifest_created",
        event_version="1.0",
        producer="interpretation.manifest",
        producer_version=manifest.producer_version,
        payload=json.dumps(manifest.to_dict(), default=str).encode("utf-8"),
        observation_id=manifest.observation_id,
        entity_id=manifest.finding_id,
        event_id=f"evt-{manifest.manifest_id}",
    )