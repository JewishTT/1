"""Web-search providers (feature web-discovery): real search engines only.

``BraveSearchProvider`` — Brave Search API, a full live web-search engine
(subscription token via env ``BRAVE_SEARCH_API_KEY``).

``TavilySearchProvider`` — Tavily API, a purpose-built web-search engine for
applications (key via env ``TAVILY_API_KEY``).

``FederatedSearchProvider`` fans a query out to all engines and merges hits
deterministically (score-weighted) — that composition is how the pipeline gets
the breadth of a meta-search engine without coupling to any one vendor.

``MemorySearchProvider`` is the hermetical research/CI stand-in: it indexes a
fixed corpus and ranks it with the same token-matching used in the ranked
projection index, so the whole discovery path is testable with zero I/O.

All transports are injectable (``httpx`` default) so contract tests never touch
the network.
"""

from __future__ import annotations

import os
import urllib.parse

import httpx

from websearch.contracts import SearchHit, SearchQuery, WebSearchProvider

BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
TAVILY_ENDPOINT = "https://api.tavily.com/search"


class BraveSearchProvider:
    """Brave Search API provider (web search to the open internet)."""

    name = "brave-search"

    # query.lang (ru/…) → Brave's country/search_lang knobs (best-effort).
    _LOCALE: dict[str, dict[str, str]] = {
        "ru": {"country": "ru", "search_lang": "ru"},
    }

    def __init__(
        self,
        *,
        endpoint: str = BRAVE_ENDPOINT,
        api_key: str | None = None,
        transport=None,
        timeout: float = 20.0,
        country: str = "us",
        freshness: str = "py",
    ) -> None:
        self._endpoint = endpoint
        self._api_key = api_key or os.environ.get("BRAVE_SEARCH_API_KEY", "")
        self._transport = transport
        self._timeout = timeout
        self._country = country
        self._freshness = freshness

    def supports(self, query: SearchQuery) -> bool:
        return query.kind in ("web", "news")

    async def search(
        self, query: SearchQuery, *, tenant_id: str = "", top_k: int = 10
    ) -> list[SearchHit]:
        if not self._api_key and self._transport is None:
            return []  # no creds, no transport → honest empty (no crash, no burn)
        locale = self._LOCALE.get(query.lang or "") or {}
        params = {
            "q": query.text,
            "count": str(max(1, min(top_k, 20))),
            "country": locale.get("country", self._country),
            "freshness": self._freshness,
            "search_lang": locale.get("search_lang", "en"),
        }
        url = f"{self._endpoint}?{urllib.parse.urlencode(params)}"
        if self._transport is not None:
            raw = await self._transport(url, api_key=self._api_key)
        else:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    url,
                    headers={"Accept": "application/json", "X-Subscription-Token": self._api_key},
                )
                resp.raise_for_status()
                raw = resp.text
        return _parse_brave(raw, provider=self.name)


class TavilySearchProvider:
    """Tavily API provider — purpose-built web-search engine (full live index)."""

    name = "tavily"

    def __init__(
        self,
        *,
        endpoint: str = TAVILY_ENDPOINT,
        api_key: str | None = None,
        transport=None,
        timeout: float = 20.0,
        search_depth: str = "basic",
    ) -> None:
        self._endpoint = endpoint
        self._api_key = api_key or os.environ.get("TAVILY_API_KEY", "")
        self._transport = transport
        self._timeout = timeout
        self._search_depth = search_depth

    def supports(self, query: SearchQuery) -> bool:
        return query.kind in ("web", "news")

    async def search(
        self, query: SearchQuery, *, tenant_id: str = "", top_k: int = 10
    ) -> list[SearchHit]:
        if not self._api_key and self._transport is None:
            return []  # no key + no transport → honest empty (no crash, no burn)
        payload = {
            "query": query.text,
            "search_depth": self._search_depth,
            "max_results": max(1, min(top_k, 20)),
        }
        if self._api_key:
            payload["api_key"] = self._api_key
        if self._transport is not None:
            raw = await self._transport(self._endpoint, payload)
        else:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(self._endpoint, json=payload)
                resp.raise_for_status()
                raw = resp.text
        return _parse_tavily(raw, provider=self.name)


class MemorySearchProvider:
    """Hermetic provider: ranks an in-memory corpus (0 I/O, deterministic)."""

    name = "memory-search"

    def __init__(self, corpus: dict[str, dict] | None = None) -> None:
        # corpus: {score_tag_uri: {"title", "snippet", "terms"}}
        self._corpus = corpus or {}

    def supports(self, query: SearchQuery) -> bool:
        return True

    async def search(
        self, query: SearchQuery, *, tenant_id: str = "", top_k: int = 10
    ) -> list[SearchHit]:
        q = query.text.lower()
        tokens = [t for t in q.replace('"', "").split() if t]
        hits: list[SearchHit] = []
        for uri, doc in self._corpus.items():
            hay = f"{doc.get('title', '')} {doc.get('snippet', '')} {doc.get('terms', '')}".lower()
            score = 0.0 if tokens else 1.0
            for tok in tokens:
                score += len(tok) > 2 and tok in hay
            if score > 0:
                hits.append(
                    SearchHit(
                        uri=uri,
                        title=doc.get("title", ""),
                        snippet=doc.get("snippet", ""),
                        score=score,
                        provider=self.name,
                    )
                )
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:top_k]


class FederatedSearchProvider:
    """Fan-out to several providers, deterministic score-weighted merge.

    A hit's merged score is the max of provider scores (a provider agreeing
    twice on the same URL counts once, but with stronger evidence). Dedup is by
    uri; ties resolve by provider order so results are reproducible.
    """

    name = "federated"

    def __init__(self, providers: list[WebSearchProvider]) -> None:
        self._providers = list(providers)

    def supports(self, query: SearchQuery) -> bool:
        return any(pr.supports(query) for pr in self._providers)

    async def search(
        self, query: SearchQuery, *, tenant_id: str = "", top_k: int = 10
    ) -> list[SearchHit]:
        merged: dict[str, SearchHit] = {}
        for provider in self._providers:
            if not provider.supports(query):
                continue
            for hit in await provider.search(query, tenant_id=tenant_id, top_k=top_k):
                if not hit.uri.startswith(("http://", "https://")):
                    continue
                prev = merged.get(hit.uri)
                merged[hit.uri] = SearchHit(
                    uri=hit.uri,
                    title=prev.title if prev and prev.title else hit.title,
                    snippet=prev.snippet if prev and prev.snippet else hit.snippet,
                    score=max(prev.score, hit.score) if prev else hit.score,
                    provider=f"{prev.provider},{hit.provider}" if prev else hit.provider,
                )
        ordered = sorted(merged.values(), key=lambda h: (h.score, h.uri), reverse=True)
        return ordered[:top_k]


def _parse_brave(raw: str, *, provider: str) -> list[SearchHit]:
    import json

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    results = (data or {}).get("web", {}).get("results", []) or []
    hits: list[SearchHit] = []
    for r in results:
        uri = r.get("url") or r.get("profile", {}).get("url") if isinstance(r, dict) else None
        if not uri:
            continue
        hits.append(
            SearchHit(
                uri=str(uri),
                title=str(r.get("title", "") or ""),
                snippet=str(r.get("description", "") or ""),
                score=float(r.get("score", 0.0) or 0.0),
                provider=provider,
                raw=r,
            )
        )
    return hits


def _parse_tavily(raw: str, *, provider: str) -> list[SearchHit]:
    import json

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    results = (data or {}).get("results", []) or []
    hits: list[SearchHit] = []
    for r in results:
        uri = r.get("url") if isinstance(r, dict) else None
        if not uri:
            continue
        hits.append(
            SearchHit(
                uri=str(uri),
                title=str(r.get("title", "") or ""),
                snippet=str(r.get("content", "") or ""),
                score=float(r.get("score", 0.0) or 0.0),
                provider=provider,
                raw=r,
            )
        )
    return hits
