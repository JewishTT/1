"""Bulk ingestion for the Global Collection Fabric (T121).

Historical archive replay (Common Crawl bulk → batch discovery → Frontier) and
eventual dataset/bulk collectors. Emits bytes + metadata only; the Observation
Gate (T130/T131) owns storage and lifecycle events.
"""

from __future__ import annotations

NAME = "cognitive_bulk_ingestion"
VERSION = "0.1.0"

__all__ = ["NAME", "VERSION"]