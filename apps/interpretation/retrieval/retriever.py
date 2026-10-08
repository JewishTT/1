"""Cross-semantic search retriever (T109).

A free-text query is resolved to a *badge* over the capability-annotated engine
façade (fuzzy over badge names/aliases), then routed to the search backends
whose capability surface covers that badge. Backends expose a common
:class:`Retriever` protocol so no query path special-cases a store.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

# A small canonical catalog so the interpretation app stays dependency-light
# while staying aligned with control-plane.badges.BADGE_CATALOG.
BADGE_CATALOG: frozenset[str] = frozenset(
    {
        "http",
        "get",
        "headers",
        "etag",
        "last-modified",
        "javascript",
        "dom",
        "screenshot",
        "archive",
        "parquet",
        "warc",
        "bulk",
        "range-read",
        "content-addressed",
    }
)

ENGINE_ALIASES: dict[str, tuple[str, ...]] = {
    "http": ("http-fetch", "static-fetch", "plain-http"),
    "browser": ("browser-render", "browsertrix", "js-render", "headless", "playwright"),
    "dataset": ("dataset-read", "parquet-read", "warehouse"),
    "archival": ("archive-read", "warc-read", "wayback", "heritrix"),
    "feed": ("feed-poll", "rss", "atom", "syndication"),
    "api": ("api-adapter", "rest", "graphql"),
    "custom": ("custom-engine", "plugin"),
    "bulk": ("bulk-crawl", "bulk-backfill", "common-crawl", "cc", "wayback-cdx"),
}

ENGINE_BADGES: dict[str, frozenset[str]] = {
    "http": frozenset({"http", "get", "headers", "etag", "last-modified", "content-addressed"}),
    "browser": frozenset({"javascript", "dom", "screenshot", "http", "content-addressed"}),
    "dataset": frozenset({"parquet", "content-addressed"}),
    "archival": frozenset({"warc", "archive", "range-read", "content-addressed"}),
    "feed": frozenset({"http", "get", "headers"}),
    "api": frozenset({"http", "get", "headers"}),
    "custom": frozenset(),
    "bulk": frozenset({"bulk", "content-addressed"}),
}

# Flag of an engine: the badge that best represents it for routing.
ENGINE_FLAGSHIP: dict[str, str | None] = {
    "http": "http",
    "browser": "javascript",
    "dataset": "parquet",
    "archival": "warc",
    "feed": "http",
    "api": "http",
    "custom": None,
    "bulk": "bulk",
}


@runtime_checkable
class Retriever(Protocol):
    """A search backend supporting an engine badge surface."""

    def supports(self, badge: str) -> bool: ...
    def retrieve(self, badge: str, query: str, top_k: int = 10) -> list[Hit]: ...


@dataclass(frozen=True)
class Hit:
    """A retrieval hit; score is backend-normalised to 0..1."""

    doc_id: str
    text: str = ""
    score: float = 0.0
    backend: str = ""


class SemanticBadgeIndex:
    """Fuzzy resolution of free-text queries onto badge tokens."""

    def __init__(self, aliases: dict[str, tuple[str, ...]] | None = None) -> None:
        self._aliases = ENGINE_ALIASES if aliases is None else aliases
        self._terms: dict[str, str] = {"token": "token"}
        for token in BADGE_CATALOG:
            self._terms[token] = token
        for engine, aliases_tuple in self._aliases.items():
            for alias in aliases_tuple:
                self._terms[alias.lower()] = engine

    def fuzzy_resolve(self, query: str, *, cutoff: float = 0.6) -> str | None:
        """Best badge for ``query``, else None (threshold-controlled)."""
        q = (query or "").strip().lower()
        if not q:
            return None
        if q in self._terms:
            return self._terms[q]
        close = difflib.get_close_matches(q, set(self._terms), n=1, cutoff=cutoff)
        if not close:
            close = difflib.get_close_matches(q, set(BADGE_CATALOG), n=1, cutoff=cutoff * 0.8)
        if not close:
            return None
        canonical = self._terms[close[0]]
        if canonical in BADGE_CATALOG:
            return canonical
        return ENGINE_FLAGSHIP.get(canonical)


def _engine_badges(engine: str) -> frozenset[str]:
    return ENGINE_BADGES.get(engine, frozenset())


class CrossSemanticRetriever:
    """Route a query onto backends via badge resolution (capability-aware)."""

    def __init__(self, backends: Retriever | list[Retriever]) -> None:
        self._backends = [backends] if not isinstance(backends, list) else list(backends)
        self._index = SemanticBadgeIndex()

    def add_backend(self, backend: Retriever) -> None:
        self._backends.append(backend)

    def badge_for(self, query: str, *, cutoff: float = 0.6) -> str | None:
        return self._index.fuzzy_resolve(query, cutoff=cutoff)

    def _covering_backends(self, badge: str) -> list[Retriever]:
        wanted = set()
        if badge in BADGE_CATALOG:
            wanted.add(badge)
        for surface in ENGINE_BADGES.values():
            if badge in surface:
                wanted.update(surface)
        return [b for b in self._backends if any(b.supports(t) for t in wanted) or b.supports(badge)]

    def search(self, query: str, *, top_k: int = 10, merge: str = "rrf_any") -> list[Hit]:
        """Badge-resolve ``query`` and merge results from covering backends.

        ``merge="rrf_any"`` reciprocal-rank fuses hits from every covering
        backend; ``merge="first"`` returns the single best backend's list.
        """
        badge = self.badge_for(query)
        if badge is None:
            return []
        backends = self._covering_backends(badge)
        if not backends:
            return []
        if merge == "first":
            return backends[0].retrieve(badge, query, top_k=top_k)
        buckets: dict[str, Hit] = {}
        for backend in backends:
            for rank, hit in enumerate(backend.retrieve(badge, query, top_k=top_k)):
                key = hit.doc_id
                prev = buckets.get(key)
                score = 1.0 / (rank + 60) + 0.01 * hit.score
                if prev is None:
                    buckets[key] = Hit(key, text=hit.text, score=score, backend=hit.backend or backend.__class__.__name__)
                else:
                    buckets[key] = Hit(key, text=prev.text, score=prev.score + score, backend=prev.backend)
        return sorted(buckets.values(), key=lambda h: h.score, reverse=True)[:top_k]


class MemoryRetriever:
    """Hermetic backend: exact + prefix scan over an in-memory corpus."""

    def __init__(self, docs: dict[str, str] | None = None, *, capabilities: set[str] | frozenset[str] | None = None) -> None:
        self._docs = dict(docs or {})
        self._caps = frozenset(capabilities or {"http", "content-addressed"})
        self._name = "memory"

    def supports(self, badge: str) -> bool:
        return badge in self._caps

    def retrieve(self, badge: str, query: str, top_k: int = 10) -> list[Hit]:
        ql = (query or "").lower()
        tokens = [t for t in ql.split() if t]
        ranked: list[Hit] = []
        for doc_id, text in self._docs.items():
            tl = text.lower()
            if ql in tl:
                score = 1.0
            elif tokens and all(t in tl for t in tokens):
                score = 0.7
            elif ql in doc_id.lower():
                score = 0.4
            else:
                continue
            ranked.append(Hit(doc_id, text=text, score=score, backend=self._name))
        ranked.sort(key=lambda h: h.score, reverse=True)
        return ranked[:top_k]