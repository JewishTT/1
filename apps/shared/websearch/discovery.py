"""EntityWebDiscovery — entity-in, candidate-URLs-out (web-discovery, feature 010/011).

The zero-layer audit's finding was incomplete directionality: fetch→parse→
extract existed, but nothing **searched the open web for an entity**. This is
the missing front door:

    entity identifiers (FIO/phone/email/domain/…) →
      query builder (deterministic, bounded) →
        providers (Brave / memory / federated) →
          entity-relevance re-ranking →
            dedup → top_k DiscoveryCandidates

The result feeds the Frontier via the pipeline's ``seed`` stage (R-4: the
frontier stays the queue of truth) and every candidate carries back the query
intent + provider provenance so the fabric can attribute the find (R-1).

Hermetic by construction: providers are injected (memory provider = zero I/O,
Brave provider = injectable httpx transport), so contract tests never touch the
network.
"""

from __future__ import annotations

from websearch.contracts import DiscoveryCandidate, FrontierSink, WebSearchProvider
from websearch.providers import (
    BraveSearchProvider,
    FederatedSearchProvider,
    MemorySearchProvider,
    TavilySearchProvider,
)
from websearch.queries import entity_identifiers_to_queries
from websearch.relevance import rerank_for_entity


class EntityWebDiscovery:
    """Fan-in pipeline: entity identifiers → ranked, deduplicated URL candidates.

    Stream-first by construction (feature 009): candidates are produced by an
    async generator, so a consumer can sink each one the moment it is discovered
    instead of after the whole search ends. ``discover`` is the convenience
    materializer for batch-style callers; ``discover_and_sink`` streams each
    candidate into the frontier immediately.
    """

    def __init__(
        self,
        *,
        providers: list[WebSearchProvider] | None = None,
        max_queries: int = 12,
        top_k: int = 10,
        min_score: float = 1.5,
        max_per_host: int = 3,
    ) -> None:
        self._federated = FederatedSearchProvider(providers or default_providers())
        self._max_queries = max_queries
        self._top_k = top_k
        self._min_score = min_score
        self._max_per_host = max_per_host

    async def stream(
        self,
        identifiers: dict[str, str],
        *,
        tenant_id: str = "",
        top_k: int | None = None,
        max_per_host: int | None = None,
    ):
        """Yield DiscoveryCandidates as providers return them (stream-first).

        Dedup is incremental on the fly: a URI already yielded for an earlier
        query is never yielded again. Host diversity is enforced per stream — a
        single site can take at most ``max_per_host`` slots so the frontier is
        not flooded by one source. Order is discovery order — callers that
        need global relevance ranking use ``discover``.
        """
        queries = entity_identifiers_to_queries(identifiers, max_queries=self._max_queries)
        seen: set[str] = set()
        host_count: dict[str, int] = {}
        per_host = self._max_per_host if max_per_host is None else max_per_host
        for query in queries:
            hits = await self._federated.search(query, tenant_id=tenant_id, top_k=self._top_k)
            for cand in rerank_for_entity(
                hits,
                identifiers,
                query=query.text,
                intent=query.intent,
                tenant_id=tenant_id,
                min_score=self._min_score,
                top_k=self._top_k,
            ):
                if cand.uri in seen:
                    continue
                seen.add(cand.uri)
                if cand.host and per_host > 0 and host_count.get(cand.host, 0) >= per_host:
                    continue
                host_count[cand.host] = host_count.get(cand.host, 0) + 1
                yield cand

    async def discover(
        self,
        identifiers: dict[str, str],
        *,
        tenant_id: str = "",
        top_k: int | None = None,
        max_per_host: int | None = None,
    ) -> list[DiscoveryCandidate]:
        """Materialize the stream into a globally relevance-ranked candidate list."""
        seen: dict[str, DiscoveryCandidate] = {}
        async for cand in self.stream(
            identifiers, tenant_id=tenant_id, top_k=top_k, max_per_host=max_per_host
        ):
            prev = seen.get(cand.uri)
            if prev is None or cand.relevance > prev.relevance:
                seen[cand.uri] = cand
        ordered = sorted(seen.values(), key=lambda c: (c.relevance, c.uri), reverse=True)
        return ordered[: top_k or self._top_k]

    async def discover_and_sink(
        self,
        identifiers: dict[str, str],
        sink: FrontierSink,
        *,
        tenant_id: str = "",
        investigation_id: str = "",
        source: str = "web-search",
        method: str = "entity",
        top_k: int | None = None,
        max_per_host: int | None = None,
    ) -> list[DiscoveryCandidate]:
        """Stream discovery and enqueue each candidate into the FrontierSink (R-4).

        Each candidate is sunk as soon as its query returns — never buffered
        until the search completes. Returns the candidates actually enqueued so
        callers (and tests) can see what entered the frontier. Provenance
        carries entity/query provenance.
        """
        candidates: list[DiscoveryCandidate] = []
        async for cand in self.stream(
            identifiers,
            tenant_id=tenant_id,
            top_k=top_k,
            max_per_host=max_per_host,
        ):
            sink.enqueue(
                uri=cand.uri,
                tenant_id=tenant_id,
                investigation_id=investigation_id,
                source=source,
                method=method,
                priority=cand.relevance,
                provenance={
                    "entity": cand.query_text,
                    "intent": cand.intent or cand.query_text,
                    "provider": cand.provider,
                    "relevance": cand.relevance,
                },
            )
            candidates.append(cand)
        return candidates


def default_providers() -> list[WebSearchProvider]:
    """Production default: real search engines — Brave + Tavily (full live index).

    Memory is only the test/offline stand-in; the pipeline-default path never
    touches it.
    """
    return [BraveSearchProvider(), TavilySearchProvider()]
    return [BraveSearchProvider()]


def memory_providers(corpus: dict[str, dict] | None = None) -> list[WebSearchProvider]:
    return [MemorySearchProvider(corpus)]
