"""Search projector (T039).

Projects observations/documents/mentions/candidates/entities/assertions/findings
into a search index. Each write is idempotent (by doc_id) and provenance-
bearing (I-11/I-12); `rebuild` clears and re-indexes from the durable batch.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

import path_shim  # noqa: F401

from .index import IndexedDoc, SearchIndex


@dataclass
class SearchEvent:
    kind: str  # one of the six index kinds
    doc_id: str
    body: dict
    event_id: str | None = None
    observation_id: str | None = None


class SearchProjector:
    INDEX_ALIASES: ClassVar[dict[str, str]] = {
        "observation": "observations",
        "document": "documents",
        "mention": "mentions",
        "candidate": "candidates",
        "entity": "entities",
        "assertion": "assertions",
        "finding": "findings",
    }

    def __init__(self, index: SearchIndex) -> None:
        self._index = index
        self._order: list[SearchEvent] = []

    def project(self, event: SearchEvent) -> None:
        index = self.INDEX_ALIASES.get(event.kind)
        if index is None:
            raise ValueError(f"Unknown search kind: {event.kind}")
        doc = IndexedDoc(
            doc_id=event.doc_id,
            index=index,
            body=event.body,
            provenance={
                "event_id": event.event_id or event.doc_id,
                "observation_id": event.observation_id or event.doc_id,
            },
        )
        self._index.index_doc(doc)
        self._order.append(event)

    def rebuild(self) -> None:
        """Clear the index and re-project the durable batch (I-12)."""
        self._index.clear()
        self._order.sort(key=lambda e: e.doc_id)
        replay = list(self._order)
        self._order = []
        for ev in replay:
            self.project(ev)

    def search(self, kind: str, query: str) -> list[str]:
        index = self.INDEX_ALIASES.get(kind)
        if index is None:
            raise ValueError(f"Unknown search kind: {kind}")
        return self._index.search(index, query)