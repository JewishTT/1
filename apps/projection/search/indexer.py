"""Relevant-content indexer + retriever adapter (feature 010, slice 2).

Bridges the ranked index (``relevance.RankedInvertedIndex``) to the two
consumers the zero-layer audit wanted wired:

- the **direct pipeline** search hook: ``RelevantContentIndexer.index`` takes
  raw observation bytes + router metadata, extracts searchable text across
  HTML/JSON/XML/CSV/plain formats and index documents per tenant;
- the **cross-semantic retriever**: ``RankedRetrieverBackend`` satisfies the
  interpretation ``Retriever`` protocol surface (``supports``/``retrieve``,
  hits exposing doc_id/text/score/backend) so a single query can fuse ranked
  observed-content hits into ``CrossSemanticRetriever``.

Both are provenance-bearing (I-11/I-12): every document carries event/observation
refs via ``provenance`` and indexing is idempotent by ``doc_id``.
"""

from __future__ import annotations

from dataclasses import dataclass

import path_shim  # noqa: F401
from search.bm25s_backend import BM25SRankedIndex
from search.index import IndexedDoc  # noqa: F401  (re-export surface)
from search.relevance import ObservationTextExtractor, RankedInvertedIndex, RelevanceHit


def default_ranked_index() -> RankedInvertedIndex | BM25SRankedIndex:
    """Best available ranked index: bm25s when installed, stdlib otherwise."""
    if BM25SRankedIndex.available():
        return BM25SRankedIndex()
    return RankedInvertedIndex()


class RelevantContentIndexer:
    """Mass-index observations of any textual format into a ranked index.

    ``SearchHook``-compatible with the Layer 0 pipeline: drops a searchable
    document per fresh observation (three-way split decides freshness upstream).
    """

    def __init__(
        self,
        index: RankedInvertedIndex | BM25SRankedIndex | None = None,
        extractor: ObservationTextExtractor | None = None,
    ) -> None:
        self._index = index or default_ranked_index()
        self._extractor = extractor or ObservationTextExtractor()

    def index(
        self,
        *,
        observation_id: str,
        uri: str,
        body: bytes,
        content_type: str | None,
        tenant_id: str,
        event_id: str = "",
        relevance: float = 0.5,
    ) -> bool:
        extracted = self._extractor.extract(body, content_type)
        if not extracted.text and not extracted.title:
            return False  # nothing indexable (binary/media/empty)
        return self._index.put(
            doc_id=f"obs:{observation_id}",
            index="documents",
            body={
                "observation_id": observation_id,
                "uri": uri,
                "content_type": content_type or "",
                "text": extracted.text,
                "title": extracted.title,
                "fields": extracted.fields,
                "relevance": relevance,
            },
            tenant_id=tenant_id,
            provenance={"event_id": event_id or observation_id, "observation_id": observation_id},
        )

    def index_with_entities(
        self,
        *,
        observation_id: str,
        uri: str,
        body: bytes,
        content_type: str | None,
        tenant_id: str,
        entities: list[str] | None = None,
        event_id: str = "",
        relevance: float = 0.5,
    ) -> bool:
        extracted = self._extractor.extract(body, content_type)
        return self._index.put(
            doc_id=f"obs:{observation_id}",
            index="documents",
            body={
                "observation_id": observation_id,
                "uri": uri,
                "content_type": content_type or "",
                "text": extracted.text,
                "title": extracted.title,
                "fields": extracted.fields,
                "entities": entities or [],
                "relevance": relevance,
            },
            tenant_id=tenant_id,
            provenance={"event_id": event_id or observation_id, "observation_id": observation_id},
        )

    def _store(self) -> RankedInvertedIndex | BM25SRankedIndex:
        """The underlying ranked index (intentional private accessor)."""
        return self._index


@dataclass
class RankedRetrieverBackend:
    """`Retriever`-protocol adapter over the ranked index (interpretation fuse).

    Supplies the ``http``/``content-addressed`` badge surface the interpretation
    retriever routes on, so ``CrossSemanticRetriever.search`` can fuse these hits
    into its reciprocal-rank merge. Hits are structurally compatible with
    ``interpretation.search.retriever.Hit`` (doc_id/text/score/backend).
    """

    index: RankedInvertedIndex | BM25SRankedIndex | None = None
    indexer: RelevantContentIndexer | None = None
    capabilities: frozenset[str] = frozenset({"http", "content-addressed", "document"})
    tenant_id: str = "default-tenant"
    name: str = "ranked-inmemory"

    def __post_init__(self) -> None:
        self._index = self.index
        if self._index is None and self.indexer is not None:
            self._index = self.indexer._store()
        if self._index is None:
            raise ValueError("RankedRetrieverBackend requires an index or indexer")

    def supports(self, badge: str) -> bool:
        return badge in self.capabilities

    def retrieve(self, badge: str, query: str, top_k: int = 10) -> list[RelevanceHit]:
        hits = self._index.results(query, top_k=top_k, tenant_id=self.tenant_id)
        for h in hits:
            h = RelevanceHit(
                doc_id=h.doc_id, text=h.text, snippet=h.snippet, score=h.score, backend=self.name
            )
        return hits
