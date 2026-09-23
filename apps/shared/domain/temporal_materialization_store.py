"""In-memory temporal materialization repository used by the control plane."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from threading import RLock

from domain.dynamics import StreamRecord
from domain.temporal_materialization import (
    MaterializationError,
    TemporalHistory,
    compare_publications,
    materialize_history,
)


@dataclass(frozen=True)
class MaterializationResult:
    history: TemporalHistory
    changed: bool
    revision: int
    comparison: dict | None = None


class TemporalMaterializationRepository:
    """Tenant/entity-scoped publication store with last-valid semantics."""

    def __init__(self) -> None:
        self._heads: dict[tuple[str, str], TemporalHistory] = {}
        self._revisions: dict[tuple[str, str], int] = {}
        self._lock = RLock()

    def materialize(
        self,
        records: Iterable[StreamRecord],
        *,
        tenant_id: str,
        entity_id: str,
        window: timedelta = timedelta(days=7),
    ) -> MaterializationResult:
        if not tenant_id or not entity_id:
            raise MaterializationError("tenant_id and entity_id are required")
        candidate = materialize_history(
            records, tenant_id=tenant_id, entity_id=entity_id, window=window
        )
        key = (tenant_id, entity_id)
        with self._lock:
            current = self._heads.get(key)
            if (
                current
                and current.publication.integrity_fingerprint
                == candidate.publication.integrity_fingerprint
            ):
                return MaterializationResult(
                    current,
                    False,
                    self._revisions[key],
                    compare_publications(current, candidate).to_dict(),
                )
            revision = self._revisions.get(key, 0) + 1
            candidate = TemporalHistory(
                tenant_id=tenant_id,
                entity_id=entity_id,
                publication=candidate.publication.__class__(
                    publication_id=candidate.publication.publication_id,
                    source_cut=candidate.publication.source_cut,
                    revisions=candidate.publication.revisions,
                    features=candidate.publication.features,
                    integrity_fingerprint=candidate.publication.integrity_fingerprint,
                    projection_generation=revision,
                ),
            )
            self._heads[key] = candidate
            self._revisions[key] = revision
            return MaterializationResult(
                candidate, True, revision, compare_publications(current, candidate).to_dict()
            )

    def compare(self, candidate: TemporalHistory) -> dict:
        return compare_publications(
            self.current(tenant_id=candidate.tenant_id, entity_id=candidate.entity_id), candidate
        ).to_dict()

    def quarantine(
        self, *, tenant_id: str, entity_id: str, source_record_id: str, reason: str
    ) -> dict:
        return {
            "tenant_id": tenant_id,
            "entity_id": entity_id,
            "source_record_id": source_record_id,
            "reason": reason,
            "status": "QUARANTINED",
        }

    def current(self, *, tenant_id: str, entity_id: str) -> TemporalHistory | None:
        return self._heads.get((tenant_id, entity_id))

    def revision(self, *, tenant_id: str, entity_id: str) -> int:
        return self._revisions.get((tenant_id, entity_id), 0)

    def point_in_time(self, *, tenant_id: str, entity_id: str, at: datetime):
        history = self.current(tenant_id=tenant_id, entity_id=entity_id)
        return history.window_at(at) if history else None
