"""Economics application service: read Intelligence, then apply economic analysis."""
from __future__ import annotations

from shared.contracts.intelligence_feed import (
    IntelligenceQuery,
    IntelligenceReadPort,
    IntelligenceSnapshot,
)
from .domain import EconomicSubject, subjects_from_snapshot

ECONOMIC_PURPOSE = "economic_analysis"


async def load_economic_context(
    intelligence: IntelligenceReadPort,
    query: IntelligenceQuery,
) -> tuple[IntelligenceSnapshot, tuple[EconomicSubject, ...]]:
    """Load the authoritative input view from Intelligence; never launch recon here."""
    if query.purpose != ECONOMIC_PURPOSE:
        raise ValueError(f"Economics requests must use purpose={ECONOMIC_PURPOSE!r}")
    snapshot = await intelligence.get_snapshot(query)
    return snapshot, subjects_from_snapshot(snapshot)
