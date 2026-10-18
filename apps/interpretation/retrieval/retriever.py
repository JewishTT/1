"""Cross-semantic search retriever (T109).

A free-text query is resolved to a *badge* over the capability-annotated engine
façade (fuzzy over badge names/aliases), then routed to the search backends
whose capability surface covers that badge. Backends expose a common
:class:`Retriever` protocol so no query path special-cases a store.
"""

from __future__ import annotations

import difflib
import hashlib
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from scoring.fusion import (
    FusionPolicy,
    RankedCandidate,
    reciprocal_rank_fusion,
)
from scoring.fusion import (
    RankerOutcome as FusionOutcome,
)
from scoring.fusion import (
    RankerOutcome_ as _RankerOutcome,
)


def _backend_name(backend: object) -> str:
    """Stable identity for a retriever backend, for fusion attribution."""
    name = getattr(backend, "name", None) or getattr(backend, "backend", None)
    return str(name) if name else type(backend).__name__

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

        This delegates to the shared fusion contract rather than carrying a
        second implementation. The local copy had three defects that the shared
        module makes impossible by construction:

        * ``enumerate`` started at 0, so a backend's *best* hit scored
          ``1/(0+k)`` instead of ``1/(1+k)``. Every list was systematically
          shifted, and a single-backend "fusion" was not a no-op.
        * ``+ 0.01 * hit.score`` folded the raw score back into the fused value,
          which is the one thing reciprocal rank fusion exists to avoid: the
          backends do not share a scale, so whichever one emits large numbers
          decides the ranking.
        * Ties fell back to dict insertion order, i.e. backend arrival order,
          which is not a property of the query.
        """
        badge = self.badge_for(query)
        if badge is None:
            return []
        backends = self._covering_backends(badge)
        if not backends:
            return []
        if merge == "first":
            return backends[0].retrieve(badge, query, top_k=top_k)

        # `query_id` is shared by construction so the fusion contract can verify
        # that every ranker answered the same question.
        query_id = hashlib.sha256(query.encode("utf-8")).hexdigest()[:16]

        outcomes: list[_RankerOutcome] = []
        texts: dict[str, str] = {}
        for backend in backends:
            retrieved = backend.retrieve(badge, query, top_k=top_k)
            # A hit knows which backend produced it; prefer that over the
            # instance's class name, which is an implementation detail and is
            # what makes attribution useless to a reader of the response.
            ranker_id = next((h.backend for h in retrieved if h.backend), "") or _backend_name(backend)
            candidates = tuple(
                RankedCandidate(
                    candidate_id=h.doc_id,
                    source_ranker_id=ranker_id,
                    rank=rank,  # 1-based: rank 1 is the backend's best hit
                    query_id=query_id,
                )
                for rank, h in enumerate(retrieved, start=1)
            )
            for h in retrieved:
                texts.setdefault(h.doc_id, h.text)
            outcomes.append(
                _RankerOutcome(
                    ranker_id=ranker_id,
                    query_id=query_id,
                    outcome=FusionOutcome.OK if candidates else FusionOutcome.EMPTY,
                    candidates=candidates,
                )
            )

        fused = reciprocal_rank_fusion(outcomes, query_id=query_id, policy=FusionPolicy())
        return [
            Hit(
                f.candidate_id,
                text=texts.get(f.candidate_id, ""),
                score=f.fused_score,
                backend=", ".join(f.contributing_rankers),
            )
            for f in fused[:top_k]
        ]


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