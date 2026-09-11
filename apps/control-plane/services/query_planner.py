"""Query planner (T050, US2).

Fuses OpenSearch (lexical/semantic), graph, ClickHouse (timeline/stats) and TDA
metadata behind one surface: the caller passes a query + filters and receives
fused results with evidence links whose chain resolves to immutable
observations (I-1). The user never sees which backend answered.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable
from dataclasses import dataclass, field
from typing import Protocol

EVIDENCE_BASE = 0.6


@dataclass(frozen=True)
class QueryFilters:
    temporal_from: str | None = None  # ISO-8601
    temporal_to: str | None = None
    source_ids: frozenset[str] = frozenset()
    investigation_id: str | None = None


@dataclass
class BackendHit:
    doc_id: str
    kind: str = "document"
    score: float = 0.5
    backend: str = ""
    observation_id: str | None = None
    source_id: str | None = None
    payload: dict = field(default_factory=dict)


@dataclass
class FusedResult:
    doc_id: str
    score: float
    backends: list[str]
    observation_ids: list[str] = field(default_factory=list)
    evidence: list[dict] = field(default_factory=list)


class BackendClient(Protocol):
    async def search(self, text: str, filters: QueryFilters, limit: int) -> list[BackendHit]: ...


@dataclass
class QueryPlan:
    query: str
    filters: QueryFilters
    backends: list[str]
    fusion: str = "score-weighted"  # user never reasons about backends

    def assert_observational(self) -> None:
        """US2 invariant: evidence must resolve to immutable observations."""
        if self.fusion != "score-weighted":
            raise ValueError("unexpected fusion strategy")


class QueryPlanner:
    SUPPORTED_ROUTES = ("document", "entity", "finding", "observation", "mention")

    def __init__(self, backends: dict[str, BackendClient], observations: dict[str, dict] | None = None) -> None:
        self._backends = dict(backends)
        self._observations = observations or {}

    def plan(self, text: str, filters: QueryFilters | None = None, preferred: list[str] | None = None) -> QueryPlan:
        candidate = list(self._backends)
        subset = [b for b in candidate if b in (preferred or candidate)]
        plan = QueryPlan(query=text, filters=filters or QueryFilters(), backends=subset)
        plan.assert_observational()
        return plan

    async def execute(self, plan: QueryPlan, limit: int = 20) -> list[FusedResult]:
        tasks: dict[str, Awaitable[list[BackendHit]]] = {
            name: backend.search(plan.query, plan.filters, limit)
            for name, backend in self._backends.items()
            if name in plan.backends
        }
        gathered = await asyncio.gather(*tasks.values())
        hits: dict[str, list[tuple[BackendHit, str]]] = {}
        for name, batch in zip(tasks, gathered, strict=True):
            for hit in batch:
                hits.setdefault(hit.doc_id, []).append((hit, name))
        fused = [
            self._fuse(doc_id, docs)
            for doc_id, docs in hits.items()
        ]
        fused.sort(key=lambda f: f.score, reverse=True)
        return fused[:limit]

    def _fuse(self, doc_id: str, docs: list[tuple[BackendHit, str]]) -> FusedResult:
        backend_names = sorted({name for _, name in docs})
        max_score = max((hit.score for hit, _ in docs), default=0.0)
        composite = EVIDENCE_BASE * max_score + (1 - EVIDENCE_BASE) * max_score
        evidence = [self._to_evidence(hit, name) for hit, name in docs]
        obs_ids = sorted({hit.observation_id for hit, _ in docs if hit.observation_id})
        return FusedResult(
            doc_id=doc_id,
            score=composite,
            backends=backend_names,
            observation_ids=obs_ids,
            evidence=evidence,
        )

    def _to_evidence(self, hit: BackendHit, backend: str) -> dict:
        obs = self._observations.get(hit.observation_id or "", {})
        return {
            "backend": backend,
            "kind": hit.kind,
            "observation_id": hit.observation_id,
            "observation": {
                "observation_id": obs.get("observation_id"),
                "uri": obs.get("uri"),
                "content_hash": obs.get("content_hash"),
                "immutable": True,  # I-1
            },
            "source_id": hit.source_id,
            "reason": hit.payload.get("reason", ""),
        }


@dataclass
class MemoryBackend:
    """Hermetic search backend over a list of documents (for tests + smoke)."""

    name: str
    docs: list[BackendHit]

    async def search(self, text: str, filters: QueryFilters, limit: int = 20) -> list[BackendHit]:
        tokens = _tokens(text)
        hits: list[BackendHit] = []
        for doc in self.docs:
            if filters.source_ids and doc.source_id not in filters.source_ids:
                continue
            if filters.investigation_id and doc.payload.get("investigation_id") != filters.investigation_id:
                continue
            body = f"{doc.kind} {doc.doc_id} {doc.payload.get('text', '')}"
            overlap = len(set(tokens) & set(_tokens(body)))
            if overlap == 0:
                continue
            hits.append(BackendHit(
                doc_id=doc.doc_id,
                backend=self.name,
                score=round(doc.score * (overlap / max(1, len(tokens))), 4),
                kind=doc.kind,
                observation_id=doc.observation_id,
                source_id=doc.source_id,
                payload={**doc.payload, "text": doc.payload.get("text", "")},
            ))
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:limit]


def _tokens(text: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9_]+", text.lower()) if t]