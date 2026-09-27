"""bm25s-backed ranked index (feature 010, slice 3).

``RankedInvertedIndex`` (``search.relevance``) is a stdlib-only BM25-ish core:
dependency-free, deterministic, and the fallback that keeps the search surface
alive. It is the *floor*, not the production retrieval path.

``BM25SRankedIndex`` is the real thing: it hands the corpus to the ``bm25s``
package (declared in ``apps/projection/pyproject.toml``) and lets a proper
sparse BM25 implementation do the ranking. The externally visible contract is
deliberately identical to the stdlib core so the two are interchangeable:

- ``put(*, doc_id, index, body, tenant_id, provenance) -> bool`` — idempotent
  by ``doc_id`` (I-11) and provenance-enforced (I-12),
- ``results(query, *, top_k, tenant_id) -> list[RelevanceHit]`` — BM25-ranked
  and tenant-filtered (``tenant_id=None`` searches every tenant),
- ``hit`` / ``all`` / ``size`` / ``clear`` / ``rebuild`` for inspection and
  rebuild replay without a transport (I-12),
- hits tagged ``"ranked-bm25s"`` so the provenance of a ranking stays visible.

Two deliberate differences from the stdlib core:

1. BM25 statistics are rebuilt lazily on the first read after a write.
   ``bm25s`` exposes no incremental append, so ``put`` marks the corpus dirty
   and the index is rebuilt on the next ``results`` — a newly indexed document
   is always visible to the next query, with no stale-read window.
2. ``body["relevance"]`` is applied as a per-document prior (``0.5 + rel``)
   exactly as the stdlib core does, so a document the projector already rated
   highly keeps ranking above identical text that it did not.

``bm25s`` is an optional runtime: if it cannot be imported the class still
imports cleanly and ``available()`` reports False, and
``search.indexer.default_ranked_index`` then picks the stdlib core instead of
exploding at import time. A ``BM25SRankedIndex`` constructed directly on such
an install stays useful — retrieval transparently delegates to the stdlib core,
while writes, sizing and rebuild replay are unaffected.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from domain import enforce_projection_provenance

import path_shim  # noqa: F401
from search.relevance import RankedInvertedIndex, RelevanceHit, tokenize

try:  # optional runtime: a missing (or broken) install must not break imports
    import bm25s
except Exception:  # noqa: BLE001 - a broken install degrades exactly like a missing one
    bm25s = None  # type: ignore[assignment]

#: Provenance tag stamped on every hit this backend produces.
BACKEND = "ranked-bm25s"


@dataclass
class _BM25Doc:
    """One indexed document, kept verbatim so rebuild can replay it."""

    doc_id: str
    index: str
    body: dict
    tenant_id: str = ""
    provenance: dict = field(default_factory=dict)


class BM25SRankedIndex:
    """Sparse BM25 ranked retrieval over observed content, tenant-isolated (I-12).

    Duck-type compatible with :class:`search.relevance.RankedInvertedIndex`:
    same constructor arity, same write/read/inspection surface, hits of the same
    :class:`~search.relevance.RelevanceHit` shape.
    """

    #: Lucene-flavoured BM25 defaults, matching ``bm25s.BM25``.
    DEFAULT_K1 = 1.5
    DEFAULT_B = 0.75

    def __init__(self, *, k1: float = DEFAULT_K1, b: float = DEFAULT_B) -> None:
        self._k1 = k1
        self._b = b
        self._docs: dict[str, _BM25Doc] = {}
        self._by_tenant: dict[str, set[str]] = defaultdict(set)
        self._retriever = None
        self._order: list[str] = []
        self._dirty = True
        self._stdlib: RankedInvertedIndex | None = None
        self._stdlib_dirty = True

    @classmethod
    def available(cls) -> bool:
        """True when the optional ``bm25s`` runtime is importable."""
        return bm25s is not None

    # -- write side ---------------------------------------------------------

    def put(
        self,
        *,
        doc_id: str,
        index: str,
        body: dict,
        tenant_id: str,
        provenance: dict | None = None,
    ) -> bool:
        """Index one document. Returns True when inserted, False on idempotent dup."""
        enforce_projection_provenance(provenance)
        if doc_id in self._docs:
            return False  # idempotent (I-11): same doc_id never overwrites
        self._docs[doc_id] = _BM25Doc(
            doc_id=doc_id,
            index=index,
            body=dict(body),
            tenant_id=tenant_id,
            provenance=dict(provenance or {}),
        )
        self._by_tenant[tenant_id].add(doc_id)
        self._invalidate()
        return True

    # -- read side ----------------------------------------------------------

    def results(
        self, query: str, *, top_k: int = 10, tenant_id: str | None = None
    ) -> list[RelevanceHit]:
        """BM25 retrieval: score every document, keep the tenant, rank, slice."""
        terms = tokenize(query)
        if not terms or not self._docs:
            return []
        self._ensure_index()
        if self._retriever is None:
            return self._stdlib_results(query, top_k=top_k, tenant_id=tenant_id)
        scores = self._retriever.get_scores(terms)
        scored: list[tuple[float, int]] = []
        for pos, raw in enumerate(scores):
            doc_id = self._order[pos]
            if tenant_id is not None and self._docs[doc_id].tenant_id != tenant_id:
                continue
            score = float(raw) * self._prior(self._docs[doc_id].body)
            if score <= 0.0:
                continue  # BM25 scores a non-matching document at exactly zero
            scored.append((score, pos))
        scored.sort(key=lambda item: (-item[0], item[1]))  # stable: insertion order
        return [self.hit(self._order[pos], score) for score, pos in scored[:top_k]]

    def hit(self, doc_id: str, score: float) -> RelevanceHit:
        doc = self._docs[doc_id]
        full = " ".join(
            [
                str(doc.body.get("title", "")),
                str(doc.body.get("text", "")),
                " ".join(str(v) for v in (doc.body.get("fields") or [])),
            ]
        )
        return RelevanceHit(
            doc_id=doc_id,
            text=str(doc.body.get("text", "")),
            snippet=self._snippet(full),
            score=round(score, 6),
            backend=BACKEND,
        )

    # -- inspection / rebuild (I-12) -----------------------------------------

    def all(self, tenant_id: str | None = None) -> list[str]:
        if tenant_id is not None:
            return sorted(self._by_tenant.get(tenant_id, set()))
        return sorted(self._docs)

    def size(self, tenant_id: str | None = None) -> int:
        return len(self.all(tenant_id))

    def clear(self) -> None:
        self._docs.clear()
        self._by_tenant.clear()
        self._retriever = None
        self._order = []
        self._dirty = True
        self._stdlib = None
        self._stdlib_dirty = True

    def rebuild(self, docs: list[dict]) -> None:
        """Replay a durable doc list into a clean index (I-12)."""
        self.clear()
        for d in docs:
            self.put(
                doc_id=d["doc_id"],
                index=d["index"],
                body=d["body"],
                tenant_id=d["tenant_id"],
                provenance=d.get("provenance"),
            )

    # -- internals ----------------------------------------------------------

    def _invalidate(self) -> None:
        """Drop derived BM25 state; the corpus is rebuilt on the next read."""
        self._retriever = None
        self._dirty = True
        self._stdlib_dirty = True

    def _ensure_index(self) -> None:
        if not self._dirty:
            return
        self._dirty = False
        self._order = list(self._docs)
        self._retriever = None
        if bm25s is None or not self._order:
            return  # degraded (or empty) — ``results`` falls back accordingly
        retriever = bm25s.BM25(k1=self._k1, b=self._b)
        # bm25s indexes a list of per-document token lists; the vocabulary and
        # the document-length statistics are derived from them.
        retriever.index(
            [tokenize(self._corpus_text(self._docs[d].body)) for d in self._order],
            show_progress=False,
        )
        self._retriever = retriever

    def _stdlib_results(
        self, query: str, *, top_k: int, tenant_id: str | None
    ) -> list[RelevanceHit]:
        """Retrieval when ``bm25s`` is absent: same shape, stdlib BM25 core."""
        mirror = self._stdlib_view()
        return [
            RelevanceHit(
                doc_id=h.doc_id,
                text=h.text,
                snippet=h.snippet,
                score=h.score,
                backend=BACKEND,
            )
            for h in mirror.results(query, top_k=top_k, tenant_id=tenant_id)
        ]

    def _stdlib_view(self) -> RankedInvertedIndex:
        """A stdlib-core mirror of this index (degraded-mode scoring only)."""
        mirror = self._stdlib
        if mirror is None:
            mirror = self._stdlib = RankedInvertedIndex()
        elif self._stdlib_dirty:
            mirror.clear()
        else:
            return mirror
        for doc in self._docs.values():
            mirror.put(
                doc_id=doc.doc_id,
                index=doc.index,
                body=doc.body,
                tenant_id=doc.tenant_id,
                provenance=doc.provenance,
            )
        self._stdlib_dirty = False
        return mirror

    @staticmethod
    def _prior(body: dict) -> float:
        """Per-document relevance prior (``0.5 + relevance``) as the stdlib core."""
        try:
            return 0.5 + float(body.get("relevance", 0.5))
        except (TypeError, ValueError):
            return 1.0  # unrated body ranks neutrally rather than crashing

    @staticmethod
    def _corpus_text(body: dict) -> str:
        return " ".join(
            [
                str(body.get("text", "")),
                str(body.get("title", "")),
                " ".join(str(v) for v in (body.get("fields") or [])),
                " ".join(str(v) for v in (body.get("entities") or [])),
            ]
        )

    @staticmethod
    def _snippet(text: str, width: int = 160) -> str:
        t = " ".join((text or "").split())
        return t if len(t) <= width else t[:width] + "…"
