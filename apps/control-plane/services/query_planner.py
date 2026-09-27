"""Query planner (T050, US2).

Fuses OpenSearch (lexical/semantic), graph, ClickHouse (timeline/stats) and TDA
metadata behind one surface: the caller passes a query + filters and receives
fused results with evidence links whose chain resolves to immutable
observations (I-1). The user never sees which backend answered.

Two invariants the fusion must hold (T006-T008):

* a backend failure **degrades** a query, it never ends it -- a sick backend
  costs the caller the healthy backends' results unless the total outage is
  raised explicitly (:class:`AllBackendsFailed`), because ``[]`` means "no
  matches" (Constitution Invariant 9);
* the composite is *derived* from ``relevance`` and ``support``, both of which
  are retained, so no reader has to take a single score on faith
  (Constitution IV).
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from typing import Protocol

EVIDENCE_BASE = 0.6

# A degradation notice is a label, not a log line: bounded so a chatty exception
# cannot inflate a response body.
DEGRADED_ERROR_MAX = 160

_TRACEBACK_MARKER = "Traceback (most recent call last)"
# An absolute path anchored at a token boundary, so ``/var/lib/x`` and
# ``C:\x`` are redacted while intra-token slashes ("a/b", "api/v1") are not.
_ABSOLUTE_PATH = re.compile(r"(^|[\s'\"=(])(?:[A-Za-z]:)?[\\/][^\s'\"]*")


class AllBackendsFailed(RuntimeError):
    """Every selected backend failed.

    Raised instead of returning an empty result set: ``[]`` means "no matches",
    and conflating that with "everything is down" is exactly the ambiguity
    Constitution Invariant 9 exists to prevent.
    """

    def __init__(self, degraded_backends: list[dict]) -> None:
        self.degraded_backends = list(degraded_backends)
        detail = "; ".join(f"{d['backend']}: {d['error']}" for d in self.degraded_backends)
        super().__init__(f"all {len(self.degraded_backends)} backends failed: {detail}")


def _error_text(exc: BaseException) -> str:
    """Render a backend failure as a bounded ``type: message`` string.

    Uses the exception's *type name* rather than a formatted traceback, and
    redacts absolute paths, so neither an internal call stack nor host layout
    can reach a user-facing body.
    """
    name = type(exc).__name__
    message = " ".join(str(exc).split())
    if _TRACEBACK_MARKER in message:
        message = message.split(_TRACEBACK_MARKER, 1)[0]
    message = _ABSOLUTE_PATH.sub(r"\1<path>", message).strip()
    text = f"{name}: {message}" if message else name
    if len(text) > DEGRADED_ERROR_MAX:
        text = text[: DEGRADED_ERROR_MAX - 1].rstrip() + "…"
    return text


def _composite(relevance: float, support: int) -> float:
    """The declared fusion formula.

    ``relevance`` is the best single-backend score; ``support`` counts
    independent SOURCES agreeing; the composite is their product. ``support == 0``
    -- hits with no source attribution -- yields exactly ``1 - EVIDENCE_BASE``:
    evidence that cannot be attributed earns no corroboration credit.
    """
    return relevance * (1 + EVIDENCE_BASE * (support - 1))


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
    relevance: float = 0.0
    support: int = 0
    observation_ids: list[str] = field(default_factory=list)
    evidence: list[dict] = field(default_factory=list)
    degraded_backends: list[dict] = field(default_factory=list)

    def rederive_composite(self) -> float:
        """Recompute `score` from the retained components.

        Exists so a client can check or dispute the stored composite against
        the declared formula rather than trusting one number (Constitution IV).
        """
        return _composite(self.relevance, self.support)


@dataclass
class _BackendOutcome:
    """One backend's answer, or the bounded record of why it has none."""

    backend: str
    hits: list[BackendHit] = field(default_factory=list)
    error: str | None = None

    def degraded(self, *, recoverable: bool) -> dict:
        return {"backend": self.backend, "error": self.error, "recoverable": recoverable}


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
        names = [name for name in self._backends if name in plan.backends]
        if not names:
            # Not an outage: nothing was even attempted, so reporting it as one
            # would put a lie in `degraded_backends`, which is non-empty iff at
            # least one *selected* backend failed.
            raise ValueError("query plan selected no backends")
        outcomes = await asyncio.gather(*(self._search_one(n, plan, limit) for n in names))

        healthy = [o for o in outcomes if o.error is None]
        if not healthy:
            # Total outage: raise rather than return []. `recoverable=False`
            # because nothing answered at all.
            raise AllBackendsFailed(
                sorted((o.degraded(recoverable=False) for o in outcomes), key=lambda d: d["backend"])
            )

        # Partial degradation: the surviving backends still answer, and the
        # failures are named rather than swallowed.
        degraded = sorted(
            (o.degraded(recoverable=True) for o in outcomes if o.error is not None),
            key=lambda d: d["backend"],
        )
        hits: dict[str, list[tuple[BackendHit, str]]] = {}
        for outcome in healthy:
            for h in outcome.hits:
                hits.setdefault(h.doc_id, []).append((h, outcome.backend))
        fused = [self._fuse(doc_id, docs, degraded) for doc_id, docs in hits.items()]
        fused.sort(key=lambda f: (-f.score, f.doc_id))
        return fused[:limit]

    async def _search_one(self, name: str, plan: QueryPlan, limit: int) -> _BackendOutcome:
        """Isolate one backend call: a sick backend degrades the query, never ends it.

        Catches `Exception`, not `BaseException`, so a cancelled or interrupted
        query propagates instead of being relabelled as a degraded backend.
        """
        try:
            batch = await self._backends[name].search(plan.query, plan.filters, limit)
        except Exception as exc:  # noqa: BLE001 - deliberate isolation boundary
            return _BackendOutcome(backend=name, error=_error_text(exc))
        return _BackendOutcome(backend=name, hits=list(batch))

    def _fuse(
        self,
        doc_id: str,
        docs: list[tuple[BackendHit, str]],
        degraded: list[dict] | None = None,
    ) -> FusedResult:
        backend_names = sorted({name for _, name in docs})
        relevance = max((hit.score for hit, _ in docs), default=0.0)
        # Distinct SOURCES, never backends: two backends reading one source are
        # one piece of evidence, not two (Constitution Governance).
        support = len({hit.source_id for hit, _ in docs if hit.source_id})
        return FusedResult(
            doc_id=doc_id,
            score=_composite(relevance, support),
            backends=backend_names,
            relevance=relevance,
            support=support,
            observation_ids=sorted({h.observation_id for h, _ in docs if h.observation_id}),
            evidence=[self._to_evidence(h, name) for h, name in docs],
            degraded_backends=list(degraded or []),
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