from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from domain.temporal_materialization import TemporalHistory


@dataclass(frozen=True)
class TemporalFeatureRow:
    tenant_id: str
    entity_id: str
    projection_generation: int
    feature_name: str
    window_start: datetime
    window_end: datetime
    value: float | int | str | None
    available: bool
    structural_only: bool
    source_record_ids: tuple[str, ...]
    feature_fingerprint: str
    source_cut_id: str

    @property
    def pk(self) -> tuple[str, str, int, str, str]:
        return (
            self.tenant_id,
            self.entity_id,
            self.projection_generation,
            self.feature_name,
            self.window_start.isoformat(),
        )


class TemporalFeatureTable(Protocol):
    def replace(self, rows: list[TemporalFeatureRow]) -> int: ...
    def canonical(self, *, tenant_id: str, entity_id: str) -> list[TemporalFeatureRow]: ...


class MemoryTemporalFeatureTable:
    def __init__(self) -> None:
        self._rows: dict[tuple, TemporalFeatureRow] = {}

    def replace(self, rows: list[TemporalFeatureRow]) -> int:
        scope = {(row.tenant_id, row.entity_id) for row in rows}
        for key in list(self._rows):
            if (self._rows[key].tenant_id, self._rows[key].entity_id) in scope:
                del self._rows[key]
        for row in rows:
            self._rows[row.pk] = row
        return len(rows)

    def canonical(self, *, tenant_id: str, entity_id: str) -> list[TemporalFeatureRow]:
        return sorted(
            (
                row
                for row in self._rows.values()
                if row.tenant_id == tenant_id and row.entity_id == entity_id
            ),
            key=lambda row: (row.projection_generation, row.window_start, row.feature_name),
        )


TemporalFeatureDDL = """
CREATE TABLE IF NOT EXISTS temporal_feature_series
(
    tenant_id LowCardinality(String),
    entity_id String,
    projection_generation UInt32,
    feature_name LowCardinality(String),
    window_start DateTime64(6),
    window_end DateTime64(6),
    value Nullable(String),
    available UInt8,
    structural_only UInt8,
    source_record_ids Array(String),
    feature_fingerprint String,
    source_cut_id String
)
ENGINE = ReplacingMergeTree(projection_generation)
PARTITION BY toYYYYMM(window_start)
ORDER BY (tenant_id, entity_id, feature_name, window_start, projection_generation);
"""


def project_features(
    history: TemporalHistory, table: TemporalFeatureTable | None = None
) -> list[TemporalFeatureRow]:
    target = table or MemoryTemporalFeatureTable()
    rows: list[TemporalFeatureRow] = []
    for revision, feature in zip(
        history.publication.revisions, history.publication.features, strict=True
    ):
        rows.append(
            TemporalFeatureRow(
                tenant_id=history.tenant_id,
                entity_id=history.entity_id,
                projection_generation=history.publication.projection_generation,
                feature_name=feature.feature_name,
                window_start=revision.window.window_start,
                window_end=revision.window.window_end,
                value=feature.value,
                available=feature.available,
                structural_only=feature.structural_only,
                source_record_ids=feature.source_record_ids,
                feature_fingerprint=feature.feature_fingerprint,
                source_cut_id=history.publication.source_cut.cut_id,
            )
        )
    target.replace(rows)
    return rows


__all__ = [
    "MemoryTemporalFeatureTable",
    "TemporalFeatureDDL",
    "TemporalFeatureRow",
    "TemporalFeatureTable",
    "project_features",
]
