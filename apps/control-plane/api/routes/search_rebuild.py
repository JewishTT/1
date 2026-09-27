"""Admin-only search projection rebuild (T029, SC-009).

``POST /api/v1/search/rebuild`` rebuilds one tenant's search indices **from the
event log and nothing else** (I-12). The previous generation is never read: a
replay into a fresh index that starts empty is what makes the result evidence
that the index is a projection of ``search.projected`` rather than an
accumulation of whatever happened to be there. The rebuilt generation is
published in one assignment, so a query running during the replay keeps reading
the old one to completion and the next one reads the new one.

Guards, in the order they are applied:

* **admin only** -- ``require_admin`` (RBAC, FR-029);
* **tenant-scoped** -- the tenant comes from the resolved context, never from the
  request body, so a rebuild can only ever rebuild the caller's own indices;
* **rate limited** -- a fixed window per (tenant, user). A rebuild is
  whole-generation work, and an unbounded one would let one admin stall the search
  plane for everyone in their tenant.

The ``documents_replayed``/``duplicates`` counts are the audit trail: duplicates
are records the idempotent index refused (I-11), which is how at-least-once
delivery in the log shows up as a number instead of a silent no-op.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Annotated, Any

from events.topics import topic_for
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.auth import TenantContext, require_admin
from services.event_bus import get_bus_facade
from services.search_backends import (
    DOC_KINDS,
    InMemoryObservationLedger,
    SearchGeneration,
    SearchProjectionStore,
    search_projection,
)

router = APIRouter(prefix="/search", tags=["search"])

#: The event type the search indexes are sourced from
#: (``apps/projection/search/publisher.py::EVENT_TYPE``, via
#: ``mappings.index_config``). Resolved through the catalog rather than hardcoded,
#: so a rename fails the import instead of silently replaying an empty topic.
EVENT_TYPE = "search.projected"
TOPIC = topic_for(EVENT_TYPE)

#: One rebuild per window, per (tenant, user). A rebuild replaces a whole
#: generation, so the cost is proportional to the log, not to the request.
DEFAULT_LIMIT = 1
DEFAULT_WINDOW_S = 30.0


class RebuildRequest(BaseModel):
    from_position: int = Field(default=0, ge=0)
    #: Omitted means every routable kind. An unknown kind is refused rather than
    #: ignored: silently rebuilding nothing because of a typo is indistinguishable
    #: from rebuilding a log that held nothing.
    kinds: list[str] | None = None


@dataclass
class FixedWindow:
    """In-process fixed-window limiter, keyed per (tenant, user).

    Process-local on purpose: it bounds one control-plane process's rebuilds, and
    a shared limit across replicas is the scheduler's decision, not this route's.
    A rebuild is rare and admin-initiated, so the window is held in memory rather
    than given a table.
    """

    limit: int = DEFAULT_LIMIT
    window_s: float = DEFAULT_WINDOW_S
    _allowed_at: dict[tuple[str, str], float] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def check(self, key: tuple[str, str]) -> float | None:
        """Seconds until the caller may try again, or ``None`` when allowed."""
        now = time.monotonic()
        with self._lock:
            earliest = self._allowed_at.get(key)
            if earliest is not None and now < earliest:
                return earliest - now
            self._allowed_at[key] = now + self.window_s
        return None


_LIMITER = FixedWindow(
    limit=int(os.environ.get("SEARCH_REBUILD_RATE_LIMIT", DEFAULT_LIMIT)),
    window_s=float(os.environ.get("SEARCH_REBUILD_WINDOW_S", DEFAULT_WINDOW_S)),
)


@dataclass
class ReplayCounters:
    """What one replay did, and what it could not do.

    Mutable on purpose: these are tallied as the log is walked, and the tally is
    the audit trail (I-11), so a counter that could not be incremented would be
    a counter that could not be reported.
    """

    records_scanned: int = 0
    documents_replayed: int = 0
    duplicates: int = 0
    unroutable: int = 0
    unreadable: int = 0
    #: The catalog is one topic per layer, so the replayed topic also carries the
    #: other projection events. They are counted, not silently dropped, so a
    #: ``records_scanned`` that dwarfs ``documents_replayed`` is explained.
    other_event_types: int = 0


def _replay(
    *, tenant_id: str, from_position: int, kinds: frozenset[str]
) -> tuple[SearchGeneration, ReplayCounters]:
    """Rebuild the tenant's indices from the log alone. Never reads the old ones."""
    store = SearchProjectionStore()
    observations = InMemoryObservationLedger()
    counters = ReplayCounters()

    for record in get_bus_facade().bus.consume(TOPIC, from_position):
        counters.records_scanned += 1
        try:
            envelope = record.parse()
            document = json.loads(envelope.payload or b"{}")
            if not isinstance(document, dict):
                raise TypeError(f"projected payload is {type(document).__name__}, not an object")
        except Exception as exc:  # noqa: BLE001 - one bad record must not stop the replay
            # A record that cannot be decoded cannot be applied, and a replay that
            # stopped here would leave the generation silently half-built. Counted
            # and skipped, so the report says so instead of the index quietly
            # missing documents.
            counters.unreadable += 1
            _note_unreadable(exc)
            continue

        if str(envelope.event_type) != EVENT_TYPE:
            counters.other_event_types += 1
            continue  # the layer topic carries other projection events too

        kind = str(document.get("kind") or "")
        if kind not in DOC_KINDS or kind not in kinds:
            continue  # not this kind, or not routable: nothing to apply
        if str(document.get("tenant_id") or "") != tenant_id:
            continue  # another tenant's record: expected, not an error
        doc_id = str(document.get("doc_id") or "")
        if not doc_id:
            counters.unroutable += 1
            continue
        observation_id = str(document.get("observation_id") or envelope.observation_id or "")
        if not observation_id and kind == "observations":
            observation_id = doc_id
        if not observation_id:
            # No path back to a raw object, so no evidence chain could ever be
            # built for it: refused rather than indexed as a dead reference.
            counters.unroutable += 1
            continue

        counters.documents_replayed += 1
        stored = store.put(
            doc_id=doc_id,
            kind=kind,
            body=document,
            tenant_id=tenant_id,
            provenance={"event_id": record.event_id, "observation_id": observation_id},
        )
        if not stored:
            counters.duplicates += 1
            continue
        if kind == "observations":
            observations.put(
                {
                    "observation_id": observation_id,
                    "uri": document.get("uri"),
                    "content_hash": document.get("content_hash"),
                    "investigation_id": document.get("investigation_id"),
                    "source_id": document.get("source_id"),
                    "tenant_id": tenant_id,
                }
            )

    return SearchGeneration(store=store, observations=observations), counters


def _note_unreadable(exc: BaseException) -> None:
    """Bounded, path-free note of an undecodable log record.

    The count is what the caller is told; this is the operator-facing half, and
    it carries the same guarantee as every other user-facing error string in this
    app: a type name, never a traceback or a host path.
    """
    logging.getLogger("api.routes.search_rebuild").warning(
        "search rebuild skipped an unreadable %s record: %s", EVENT_TYPE, type(exc).__name__
    )


@router.post("/rebuild")
async def rebuild_search(
    body: RebuildRequest | None = None,
    ctx: Annotated[TenantContext, Depends(require_admin)] = None,
) -> dict[str, Any]:
    request = body or RebuildRequest()
    kinds = frozenset(request.kinds) if request.kinds else frozenset(DOC_KINDS)
    unknown = sorted(kinds - set(DOC_KINDS))
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"unknown document kind(s): {unknown}; routable kinds are {list(DOC_KINDS)}",
        )

    wait = _LIMITER.check((ctx.tenant_id, ctx.user_id))
    if wait is not None:
        retry_after = max(1, int(wait + 0.999))
        raise HTTPException(
            status_code=429,
            detail=(
                f"at most {DEFAULT_LIMIT} rebuild per "
                f"{int(_LIMITER.window_s)}s per tenant and user"
            ),
            headers={"Retry-After": str(retry_after)},
        )

    started = time.monotonic()
    generation, counters = _replay(
        tenant_id=ctx.tenant_id,
        from_position=request.from_position,
        kinds=kinds,
    )
    search_projection().replace_generation(generation)

    return {
        "tenant_id": ctx.tenant_id,
        "event_type": EVENT_TYPE,
        "topic": TOPIC,
        "kinds": sorted(kinds),
        "from_position": request.from_position,
        "records_scanned": counters.records_scanned,
        "documents_replayed": counters.documents_replayed,
        "duplicates": counters.duplicates,
        "unroutable": counters.unroutable,
        "unreadable": counters.unreadable,
        "other_event_types": counters.other_event_types,
        "documents_indexed": generation.store.size(ctx.tenant_id),
        "duration_ms": int((time.monotonic() - started) * 1000),
    }
