"""Kafka-native publication of projected search documents (FR-008/FR-012).

``mappings.index_config`` binds every search index to a Kafka source on topic
``search.projected`` with a ``tenant_id == "<t>" && kind == "<k>"`` transform
filter, and Quickwit is the only thing that indexes from it. This module is
that feed: the producer side of an otherwise fully declarative contract.
Transport is the ``EventBus`` protocol, so the same code drives the hermetic
in-memory bus and the phase-2 Kafka adapter (no second event bus invented).

Three properties are enforced here rather than upstream:

* **routability** — the filter is a literal equality test per index, so a
  document without ``tenant_id``/``kind`` (or with values that disagree with
  the envelope it is routed on) matches no filter and lands in no index at all:
  an error nobody sees, on a projection nobody can query. Such a document is
  rejected before it is published (fail-closed, FR-011);
* **idempotency** — one envelope per ``(doc_id, tenant_id, kind)`` with a
  deterministic ``event_id`` (``evt-<hash>``), so at-least-once delivery can
  never double-apply a document and a re-run of the same batch is a no-op
  (I-11);
* **partitioning** — the record key is the ``tenant_id``, so every document of
  one tenant shares a partition and stays ordered behind that tenant's index.

Ordering is the caller's contract, not an optimisation: the projector publishes
strictly *after* ``SearchIndex.index_doc`` returned and swallows publication
failures. The event log is the rebuild source for the index (I-12), so a lost
publication is repaired by replaying the log — never by rolling back or
patching the index.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from events.bus import EventBus
from events.kafka import Envelope, build_envelope

import path_shim  # noqa: F401 - keep apps/shared ahead of conflicting dirs

from .index import IndexedDoc
from .mappings import DOC_KINDS

#: Event type / topic the search indexes are sourced from (``mappings``).
EVENT_TYPE = "search.projected"

EVENT_VERSION = "1.0"
PRODUCER = "projection.search"
PRODUCER_VERSION = "0.1.0"


class UnroutableProjectionError(ValueError):
    """The Quickwit transform filter would drop this document silently (FR-011)."""


def projection_event_id(doc_id: str, tenant_id: str, kind: str) -> str:
    """Deterministic consumer idempotency key for one projected document.

    Content-addressed on the routing triple only, so the same document always
    yields the same ``event_id`` across processes, retries and replays (I-11).
    """
    canonical = json.dumps([doc_id, tenant_id, kind], separators=(",", ":"))
    return f"evt-{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def _encode(document: dict[str, Any]) -> bytes:
    return json.dumps(document, sort_keys=True, default=str).encode("utf-8")


class SearchProjectionPublisher:
    """Publishes one ``search.projected`` envelope per indexed document.

    The bus is injected, so the publisher is exercised hermetically in-process
    and unchanged against a real broker. Two catalog facts differ between the
    two, and neither belongs to this layer:

    * the default topic is the *Kafka* topic the indexes are sourced from
      (``mappings.index_config``), while ``events.bus`` gates on its own lane
      catalog — pass ``topic=topic_for(EVENT_TYPE)`` to target the hermetic bus;
    * the hermetic bus additionally keeps the I-5 inline cap of
      ``events.bus.MAX_INLINE_REFS``, so a full-text document only fits the
      phase-2 Kafka adapter, where the body is a projection rather than a blob.
    """

    def __init__(self, bus: EventBus, *, topic: str = "search.projected") -> None:
        self._bus = bus
        self._topic = topic
        self._published: set[str] = set()

    @property
    def topic(self) -> str:
        return self._topic

    def publish(self, doc: IndexedDoc, kind: str, tenant_id: str) -> None:
        """Publish one projected document; a repeat of the same triple is a no-op."""
        envelope = self.envelope(doc, kind, tenant_id)
        if envelope.event_id in self._published:
            return
        self._bus.publish(self._topic, envelope, key=tenant_id)
        # Recorded only once the bus took the record: a failed publish must stay
        # retryable, an accepted one must never be emitted twice (I-11).
        self._published.add(envelope.event_id)

    def envelope(self, doc: IndexedDoc, kind: str, tenant_id: str) -> Envelope:
        """The envelope one document is published as (built, never published).

        Validation runs here, so an unroutable document is rejected even on a
        call that would otherwise have been deduplicated.
        """
        self._require_routable(doc, kind, tenant_id)
        envelope = build_envelope(
            event_type=EVENT_TYPE,
            event_version=EVENT_VERSION,
            producer=PRODUCER,
            producer_version=PRODUCER_VERSION,
            payload=b"",
            event_id=projection_event_id(doc.doc_id, tenant_id, kind),
            tenant_id=tenant_id,
            observation_id=doc.provenance.get("observation_id") or None,
            causation_id=doc.provenance.get("event_id") or None,
        )
        # One clock read: the ingest timestamp *is* the envelope timestamp, so
        # the Quickwit ``timestamp_field`` and the envelope lineage agree.
        envelope.payload = _encode(self._document(doc, kind, tenant_id, envelope.produced_at))
        return envelope

    @staticmethod
    def _document(doc: IndexedDoc, kind: str, tenant_id: str, produced_at: str) -> dict[str, Any]:
        """The ingest document: the projected body plus the routed identity.

        Field for field the shape ``QuickwitSearchIndex`` posts over HTTP, so an
        index built from this topic and one built through the REST adapter hold
        identical documents.
        """
        document = dict(doc.body)
        document["doc_id"] = doc.doc_id
        document["kind"] = kind
        document["tenant_id"] = tenant_id
        document["produced_at"] = produced_at
        return document

    @staticmethod
    def _require_routable(doc: IndexedDoc, kind: str, tenant_id: str) -> None:
        """Reject anything the transform filter would discard without an error.

        Every index filters on its own literal ``(tenant, kind)`` pair, so a
        document that does not carry both fields — or carries values other than
        the ones this envelope routes on — is dropped by *all* of them. That is
        invisible data loss on a projection, so it is refused here instead.
        """
        if kind not in DOC_KINDS:
            raise UnroutableProjectionError(f"unknown document kind: {kind}")
        if not tenant_id:
            raise UnroutableProjectionError(f"document {doc.doc_id} lacks tenant_id")
        body_tenant = str(doc.body.get("tenant_id") or "")
        body_kind = str(doc.body.get("kind") or "")
        if not body_tenant or not body_kind:
            missing = [name for name, value in (("tenant_id", body_tenant), ("kind", body_kind)) if not value]
            raise UnroutableProjectionError(
                f"document {doc.doc_id} body lacks {' and '.join(missing)} (unroutable)"
            )
        if body_tenant != tenant_id or body_kind != kind:
            raise UnroutableProjectionError(
                f"document {doc.doc_id} body ({body_tenant}/{body_kind}) disagrees with "
                f"the routed ({tenant_id}/{kind})"
            )


__all__ = [
    "EVENT_TYPE",
    "SearchProjectionPublisher",
    "UnroutableProjectionError",
    "projection_event_id",
]
