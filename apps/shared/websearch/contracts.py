"""Shared proto-contract: search queries, hits, providers, discovery results.

This is the "search-engine analog" for **discovery**: turning an entity's
identifiers into web-search queries, fanning out to providers, and turning
ranked hits into Frontier candidate URIs. Providers are transport-injected so
the layer is testable hermetically; production binds HTTP transports.

The audit gap this closes: Layer 0 had fetch→parse→extract→fabric→search
(URL-in, entities-out) but **nothing searched the open web for an entity**. This
module completes the circle (entity-in → candidate-URLs-out).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class SearchQuery:
    """One materialized query for a provider, tagged with its intent and locale.

    ``lang`` is a BCP47-ish hint ``"ru"``/``"en"``/… detected from the entity's
    identifiers, so providers can bias toward the entity's native search locale
    (a Russian name should search the Russian web, not the US index).
    """

    text: str
    intent: str = "entity"  # entity | alias | phone | email | domain | handle | geo
    weight: float = 1.0
    kind: str = "web"
    lang: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "intent": self.intent,
            "weight": self.weight,
            "kind": self.kind,
            "lang": self.lang,
        }


@dataclass(frozen=True, slots=True)
class SearchHit:
    """One ranked hit from a provider (before entity-relevance rerank)."""

    uri: str
    title: str = ""
    snippet: str = ""
    score: float = 0.0
    provider: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "uri": self.uri,
            "title": self.title,
            "snippet": self.snippet,
            "score": self.score,
            "provider": self.provider,
        }


@dataclass(frozen=True, slots=True)
class DiscoveryCandidate:
    """A candidate Frontier item after entity relevance reranking (slice: web).

    Mirrors the acquisition adapter's ``Candidate`` shape (url/host/source/score)
    plus enough provenance for the fabric to attribute the find back to the
    originating entity query/goal (R-1 honesty).
    """

    uri: str
    host: str
    title: str = ""
    snippet: str = ""
    relevance: float = 0.0
    query_text: str = ""
    intent: str = ""
    provider: str = ""
    tenant_id: str = ""


@runtime_checkable
class WebSearchProvider(Protocol):
    """Search-engine provider surface (Brave Search, SerpAPI, DDG, local…)."""

    name: str

    def supports(self, query: SearchQuery) -> bool: ...

    async def search(
        self, query: SearchQuery, *, tenant_id: str = "", top_k: int = 10
    ) -> list[SearchHit]: ...


@runtime_checkable
class FrontierSink(Protocol):
    """The frontier receipt the discovery adopter uses (R-4: frontier is truth)."""

    def enqueue(
        self,
        *,
        uri: str,
        tenant_id: str,
        investigation_id: str,
        source: str,
        method: str,
        priority: float = 0.0,
        provenance: dict[str, Any] | None = None,
    ) -> None: ...
