"""Entity-driven web discovery (feature 010/011, web-discovery slice).

The zero-layer audit found Layer 0 only went one direction — URL in, entities
out. This package is the missing front door: **entity in → candidate URLs out**,
by searching the open web for an entity's identifiers, re-ranking hits by entity
relevance, and returning Frontier-sink-ready candidates.

Layers (all transport-injected, hermetic by default):
- ``contracts`` — SearchQuery / SearchHit / DiscoveryCandidate / provider+sink
  protocols.
- ``queries`` — entity identifiers → bounded, intent-tagged search queries.
- ``providers`` — Brave (open web, HTTP), Memory (0-I/O test), Federated
  (score-weighted fan-out merge).
- ``relevance`` — entity-relevance re-ranking (exact identifier evidence beats
  loose token overlap).
- ``discovery`` — EntityWebDiscovery orchestration + FrontierSink bridge.
"""

from __future__ import annotations

from websearch.contracts import (
    DiscoveryCandidate,
    FrontierSink,
    SearchHit,
    SearchQuery,
    WebSearchProvider,
)
from websearch.discovery import EntityWebDiscovery, default_providers, memory_providers
from websearch.providers import (
    BraveSearchProvider,
    FederatedSearchProvider,
    MemorySearchProvider,
    TavilySearchProvider,
)
from websearch.queries import entity_identifiers_to_queries, identifiers_to_tokens
from websearch.relevance import entity_relevance_score, rerank_for_entity

NAME = "cognitive_shared_websearch"
VERSION = "0.1.0"

__all__ = [
    "BraveSearchProvider",
    "DiscoveryCandidate",
    "EntityWebDiscovery",
    "FederatedSearchProvider",
    "FrontierSink",
    "MemorySearchProvider",
    "SearchHit",
    "SearchQuery",
    "TavilySearchProvider",
    "WebSearchProvider",
    "default_providers",
    "entity_identifiers_to_queries",
    "entity_relevance_score",
    "identifiers_to_tokens",
    "memory_providers",
    "rerank_for_entity",
]
