"""Search projector (T039).

Projects observations/documents/mentions/candidates/entities/assertions/findings
into a search index. Each write is idempotent (by doc_id) and provenance-
bearing (I-11/I-12); `rebuild` clears and re-indexes from the durable batch.

Given a publisher, every indexed document is announced on ``search.projected``
after the write (`publisher.py`); without one the projector is a pure index
writer, as before.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

import path_shim  # noqa: F401

from .index import IndexedDoc, SearchIndex
from .mappings import DOC_KINDS
from .publisher import SearchProjectionPublisher


@dataclass
class SearchEvent:
    kind: str  # one of the six index kinds
    doc_id: str
    body: dict
    event_id: str | None = None
    observation_id: str | None = None


def _alias(kind: str) -> str:
    """The event-kind name a caller uses for a canonical index kind."""
    if kind.endswith("ies"):
        return kind[:-3] + "y"
    return kind.removesuffix("s")


def _index_aliases() -> dict[str, str]:
    """Derive the singular-alias table from ``DOC_KINDS`` — one source of truth.

    A kind that does not inflect (or that collides with another alias) raises
    here rather than silently aliasing to the wrong index.
    """
    aliases: dict[str, str] = {}
    for kind in DOC_KINDS:
        alias = _alias(kind)
        if not alias or alias in aliases:
            raise ValueError(f"cannot derive a unique search alias for kind: {kind}")
        aliases[alias] = kind
    return aliases


class SearchProjector:
    #: Event kind -> canonical index kind, derived from ``mappings.DOC_KINDS``.
    INDEX_ALIASES: ClassVar[dict[str, str]] = _index_aliases()

    def __init__(
        self,
        index: SearchIndex,
        publisher: SearchProjectionPublisher | None = None,
    ) -> None:
        self._index = index
        self._publisher = publisher
        self._order: list[SearchEvent] = []
        #: Publications that failed; repaired by log replay, never by the index.
        self.publication_failures: int = 0

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
        if self._publisher is not None:
            self._publish(doc)

    def _publish(self, doc: IndexedDoc) -> None:
        """Announce the indexed document on ``search.projected``.

        Strictly downstream of the index write, and deliberately unable to fail
        it: the event log is the rebuild source for the index (I-12), so a lost
        publication is repaired by replaying the log. Rolling the index write
        back instead would lose the document from both places.
        """
        try:
            self._publisher.publish(doc, doc.index, str(doc.body.get("tenant_id") or ""))
        except Exception:  # noqa: BLE001 - publication is best-effort by contract
            self.publication_failures += 1

    def rebuild(self) -> None:
        """Clear the index and re-project the durable batch (I-12).

        A publisher is not re-fed: the log it wrote is what the rebuild replays,
        and the same (doc_id, tenant_id, kind) never emits twice.
        """
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