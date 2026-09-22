"""Feedback loop closing: frontier sinks + shared forms (T116-T118).

Every feedback branch produces :class:`FeedbackCandidate`s and a sink writes
them into the AUTHORITATIVE Postgres frontier (same ``frontier_items`` table /
insert contract as control-plane PgFrontier; see apps/control-plane/db/schema.py
and services/frontier.py). Memory sink keeps unit tests hermetic.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class FeedbackCandidate:
    uri: str
    priority: float
    kind: str  # pivot | hypothesis | research
    tenant_id: str
    investigation_id: str | None = None
    source_id: str | None = None
    work_id: str | None = None
    reason: str = ""
    payload: dict = field(default_factory=dict)


class FrontierSink(Protocol):
    async def enqueue_candidate(self, candidate: FeedbackCandidate) -> bool: ...


class MemoryFrontierSink:
    """Hermetic sink for unit tests / planning; records enqueued candidates."""

    def __init__(self) -> None:
        self.items: list[FeedbackCandidate] = []

    async def enqueue_candidate(self, candidate: FeedbackCandidate) -> bool:
        if any(i.uri == candidate.uri and i.tenant_id == candidate.tenant_id for i in self.items):
            return False
        self.items.append(candidate)
        return True


class PgFrontierSink:
    """Write feedback candidates into the authoritative Postgres frontier.

    Mirrors PgFrontier.enqueue's exact insert contract: unique (tenant_id, uri),
    ON CONFLICT DO NOTHING, READY state. Own session factory keeps this module
    standalone; consumers may inject one for shared-engine pooling.
    """

    def __init__(self, session_factory=None) -> None:
        self._factory = session_factory

    def _factory_or_default(self):
        if self._factory is None:
            from db.session import make_session_factory

            self._factory = make_session_factory()
        return self._factory

    async def enqueue_candidate(self, candidate: FeedbackCandidate) -> bool:
        from db.schema import FrontierItem as Row
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        stmt = pg_insert(Row).values(
            frontier_id="FB-" + uuid.uuid4().hex[:14],
            tenant_id=candidate.tenant_id,
            investigation_id=candidate.investigation_id,
            source_id=candidate.source_id,
            uri=candidate.uri,
            host_key=None,
            priority=candidate.priority,
            state="READY",
            retries=0,
            lease_until=None,
            next_schedule_at=None,
        )
        stmt = stmt.on_conflict_do_nothing(index_elements=["tenant_id", "uri"])
        factory = self._factory_or_default()
        async with factory() as session:
            result = await session.execute(stmt)
            await session.commit()
            return bool(result.rowcount)

    async def close(self) -> None:
        if self._factory is None:
            engine = getattr(self._factory_or_default(), "kwargs", {}).get("bind")
            if engine is not None:
                await engine.dispose()


def retrieval_key_uri(kind: str, key: str) -> str:
    """Canonical uri for a retrieval pivot / hypothesis (T117/T118)."""
    if kind == "pivot":
        return f"retrieval://pivot/{key}"
    if kind == "hypothesis":
        return f"retrieval://hypothesis/{key}"
    return f"retrieval://{kind}/{key}"
