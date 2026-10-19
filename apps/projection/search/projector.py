"""Search projector (T039).

Projects observations/documents/mentions/candidates/entities/assertions/findings
into a search index. Each write is idempotent (by doc_id) and provenance-
bearing (I-11/I-12); `rebuild` clears and re-indexes from the durable batch.

Given a publisher, every indexed document is announced on ``search.projected``
after the write (`publisher.py`); without one the projector is a pure index
writer, as before.

**Every rebuild produces a `ProjectionManifest`** (FR-006). It is returned rather
than merely logged: a manifest nobody can hold is a manifest nobody consults, and
"this projection is rebuildable" is a claim the blueprint wants checkable, not
narrated. The in-memory projector reports `rebuildable=False` on purpose -- its
batch is the process, not a durable cut -- and a subclass with a durable batch
declares `source_is_durable=True`.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import ClassVar

import path_shim  # noqa: F401

from contracts.projection_manifest import (
    BuilderRef,
    ProjectionKind,
    ProjectionManifest,
    Staleness,
)

from .index import IndexedDoc, SearchIndex
from .mappings import DOC_KINDS
from .publisher import SearchProjectionPublisher

#: Names this builder in every manifest it emits. Bump the version when the alias
#: derivation or the document shape changes, because either changes the output.
SEARCH_BUILDER = BuilderRef(id="projection.search", version="1.0.0")


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

    def _doc_for(self, event: SearchEvent) -> IndexedDoc:
        index = self.INDEX_ALIASES.get(event.kind)
        if index is None:
            raise ValueError(f"Unknown search kind: {event.kind}")
        return IndexedDoc(
            doc_id=event.doc_id,
            index=index,
            body=event.body,
            provenance={
                "event_id": event.event_id or event.doc_id,
                "observation_id": event.observation_id or event.doc_id,
            },
        )

    def project(self, event: SearchEvent) -> None:
        doc = self._doc_for(event)
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

    def rebuild(
        self,
        *,
        tenant_id: str | None = None,
        source_is_durable: bool = False,
    ) -> ProjectionManifest | None:
        """Clear the index and re-project the durable batch (I-12), returning the manifest.

        A publisher is not re-fed: the log it wrote is what the rebuild replays,
        and the same (doc_id, tenant_id, kind) never emits twice.

        **When a manifest is returned.** The contract refuses a manifest without a
        tenant, because a projection that cannot name its tenant can be read across
        tenants (FR-090). So the tenant is taken from the caller when given, else
        derived from the batch — and derived *only* when the whole batch agrees.
        A batch with no tenant, or with two, returns ``None``: there is no honest
        value to write, and inventing one would be the failure the field exists to
        prevent. A caller that needs FR-006 compliance passes ``tenant_id``.

        ``source_is_durable`` is the caller's claim about the batch it replayed.
        The in-memory projector cannot make it, so the default is False and the
        manifest says `rebuildable: false` — the honest answer, not a missing one.
        """
        self._index.clear()
        self._order.sort(key=lambda e: e.doc_id)
        replay = list(self._order)
        self._order = []

        written: list[IndexedDoc] = []
        for ev in replay:
            doc = self._doc_for(ev)
            self._index.index_doc(doc)
            written.append(doc)
            if self._publisher is not None:
                self._publish(doc)

        resolved = tenant_id or _sole_tenant(written)
        if not resolved:
            return None
        return self._manifest(replay, written, tenant_id=resolved, durable=source_is_durable)

    def _manifest(
        self,
        replay: list[SearchEvent],
        written: list[IndexedDoc],
        *,
        tenant_id: str,
        durable: bool,
    ) -> ProjectionManifest:
        """The reproducible build record for the batch that was just written.

        Both digests are over canonical JSON with sorted keys: two runs over the
        same batch must produce the same fingerprint, and a re-run after a code
        change that alters the document shape must produce a different
        ``output_digest``. That difference is the point — it is how a rebuild that
        silently changed the projection becomes visible.
        """
        event_ids = sorted(str(ev.event_id or ev.doc_id) for ev in replay)
        docs = sorted(
            (
                {
                    "doc_id": doc.doc_id,
                    "index": str(doc.index),
                    "body": doc.body,
                    "provenance": doc.provenance,
                }
                for doc in written
            ),
            key=lambda item: (item["index"], item["doc_id"]),
        )
        return ProjectionManifest.declare(
            projection_id="search-index",
            projection_kind=ProjectionKind.SEARCH,
            tenant_id=tenant_id,
            source_event_offset={
                "event_count": len(replay),
                "event_ids_digest": _digest(event_ids),
                "last_event_id": event_ids[-1] if event_ids else None,
            },
            input_snapshot_digest=_digest(event_ids),
            builder=SEARCH_BUILDER,
            parameters={
                "indexes": sorted({str(doc.index) for doc in written}),
                "projector": type(self).__name__,
            },
            output_digest=_digest(docs),
            rebuildable=durable,
            staleness=Staleness(),
            output_derivation={
                "documents": len(written),
                "publication_failures": self.publication_failures,
                "source_is_durable": durable,
            },
        )

    def search(self, kind: str, query: str) -> list[str]:
        index = self.INDEX_ALIASES.get(kind)
        if index is None:
            raise ValueError(f"Unknown search kind: {kind}")
        return self._index.search(index, query)


def _digest(payload: object) -> str:
    """Stable content address over canonical JSON."""
    material = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(material.encode("utf-8")).hexdigest()


def _sole_tenant(docs: list[IndexedDoc]) -> str:
    """The one tenant every document agrees on, or ``""`` when there is not one.

    Two tenants in one batch and no tenants at all are both "no single answer".
    Neither is a reason to pick whichever sorted first.
    """
    tenants = {str(doc.body.get("tenant_id") or "") for doc in docs}
    tenants.discard("")
    if len(tenants) == 1:
        return tenants.pop()
    return ""