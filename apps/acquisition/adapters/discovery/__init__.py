"""Discovery sources (feature 008, FR-001..FR-007).

Discovery produces URL *candidates* (not observations) and feeds the Postgres
frontier (ADR-0015). Sources live behind a single contract so the capability
registry and the scheduler stay unaware of any vendor specifics.
"""

from __future__ import annotations

from .contracts import Candidate, DiscoverySource, canonicalize, coalesce
from .registry import DiscoveryRegistry, FrontierSink, InMemoryFrontierSink

__all__ = [
    "Candidate",
    "DiscoverySource",
    "canonicalize",
    "coalesce",
    "DiscoveryRegistry",
    "FrontierSink",
    "InMemoryFrontierSink",
]
