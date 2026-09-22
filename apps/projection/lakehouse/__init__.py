"""Lakehouse projections (phase D, T108/T121, US3).

Backfill/rebuildable materialized views from the Kafka stream to Iceberg
(optimized ClickHouse ↔ Iceberg ↔ Parquet). Always rebuildable: projections
are derived state, never authoritative sources of truth.
"""

from __future__ import annotations

NAME = "cognitive_projection_lakehouse"
VERSION = "0.1.0"

__all__ = ["NAME", "VERSION"]