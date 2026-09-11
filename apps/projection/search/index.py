"""Search index abstraction + in-memory adapter (T039).

App code uses `SearchIndex`; OpenSearch lives behind `opensearch.py`. The
projector pushes documents of six kinds (observations/document/mentions/
candidates/entities/assertions/findings) and supports idempotent rebuild.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from domain import enforce_projection_provenance

import path_shim  # noqa: F401


@dataclass
class IndexedDoc:
    doc_id: str
    index: str
    body: dict
    provenance: dict[str, str] = field(default_factory=dict)


class SearchIndex(Protocol):
    def index_doc(self, doc: IndexedDoc) -> None: ...
    def bulk_index_docs(self, docs: list[IndexedDoc]) -> None: ...
    def search(self, index: str, query: str) -> list[str]: ...


class Id(str):
    pass


class InMemorySearchIndex:
    """Tiny inverted index for deterministic projector tests."""

    def __init__(self) -> None:
        self._docs: dict[str, dict] = {}
        self._postings: dict[str, set[str]] = {}

    def index_doc(self, doc: IndexedDoc, provenance: dict | None = None) -> None:
        enforce_projection_provenance(doc.provenance or provenance)
        if doc.doc_id in self._docs:
            return  # idempotent (I-11)
        self._docs[doc.doc_id] = {"index": doc.index, "body": doc.body}
        tokens = self._tokenize(doc.body.get("text", "") + " " + " ".join(doc.body.get("fields", [])))
        for tok in tokens:
            self._postings.setdefault(tok, set()).add(doc.doc_id)

    def bulk_index_docs(self, docs: list[IndexedDoc]) -> None:
        """Bulk-index multiple docs in one call (amortized idempotency)."""
        for doc in docs:
            self.index_doc(doc)

    def search(self, index: str, query: str) -> list[str]:
        tokens = self._tokenize(query)
        if not tokens:
            return []
        hits: set[str] | None = None
        for tok in tokens:
            ids = self._postings.get(tok, set())
            hits = ids if hits is None else hits & ids
        return sorted(
            doc_id for doc_id in (hits or set())
            if self._docs.get(doc_id, {}).get("index") == index
        )

    def all(self, index: str) -> list[str]:
        return sorted(doc_id for doc_id, d in self._docs.items() if d["index"] == index)

    def clear(self) -> None:
        self._docs.clear()
        self._postings.clear()

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        import re

        lowered = re.sub(r"[^a-z0-9 ]", " ", text.lower())
        return [t for t in lowered.split() if t]