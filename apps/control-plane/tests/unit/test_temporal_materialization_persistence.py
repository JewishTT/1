"""Persistence metadata tests for temporal materialization."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from db.schema import (
    TemporalHistoryPublication,
    TemporalMaterializationRun,
    TemporalWindowRevision,
)


def test_temporal_tables_have_tenant_entity_indexes() -> None:
    for model in (TemporalMaterializationRun, TemporalWindowRevision, TemporalHistoryPublication):
        indexes = {
            tuple(column.name for column in index.columns) for index in model.__table__.indexes
        }
        assert any("tenant_id" in columns and "entity_id" in columns for columns in indexes)


def test_publication_generation_is_unique_per_entity() -> None:
    names = {
        tuple(column.name for column in index.columns)
        for index in TemporalHistoryPublication.__table__.indexes
    }
    assert ("tenant_id", "entity_id", "projection_generation") in names
