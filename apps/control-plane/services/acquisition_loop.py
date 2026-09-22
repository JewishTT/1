"""Minimal acquisition loop (US1, FR-005).

Closes the fabric circle for one frontier item:
    pop (Postgres) -> fetch bytes (worker) -> gate.ingest (MinIO + Redpanda
    lifecycle event) -> complete (Postgres, records last_digest for the
    re-observation three-way split).

The loop is intentionally thin: it owns no storage semantics (the gate does),
decides nothing about routing (the registry/dispatcher does), and never reads
`if source == ...` (capability matching only). External engines plug in behind
:class:`CollectionAdapter` / an adapters registry.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx
from events.observation_gate import ObservationGate

from services.frontier import FrontierItem, PgFrontier


@dataclass
class LoopResult:
    frontier_id: str
    uri: str
    observation_id: str
    lifecycle: str
    raw_ref: str
    digest: str
    ok: bool
    reason: str = ""
    body: bytes = b""
    content_type: str = ""
    tenant_id: str = ""


class AcquisitionLoop:
    """Fetches and gates one item from an async Pg frontier."""

    def __init__(
        self,
        frontier: PgFrontier,
        gate: ObservationGate,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._frontier = frontier
        self._gate = gate
        self._client = client or httpx.AsyncClient(
            timeout=10.0, follow_redirects=True, headers={"User-Agent": "cognitive-acquisition/0.1"}
        )

    @property
    def frontier(self) -> PgFrontier:
        """The frontier the loop pops/leases from (shared with the pipeline)."""
        return self._frontier

    async def run_item(self, item: FrontierItem) -> LoopResult:
        """Acquire one previously-leased frontier item."""
        try:
            resp = await self._client.get(item.uri)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            await self._frontier.fail_retry(item.frontier_id)
            return LoopResult(
                frontier_id=item.frontier_id,
                uri=item.uri,
                observation_id="",
                lifecycle="failed",
                raw_ref="",
                digest="",
                ok=False,
                reason=f"fetch failed: {exc}",
            )

        prev_digest = await self._frontier.last_digest(item.frontier_id, item.uri)
        obs = await self._gate.ingest(
            body=resp.content,
            uri=str(resp.url),
            tenant_id=item.tenant_id,
            investigation_id=item.investigation_id,
            source_id=item.source_id,
            work_id=item.frontier_id,
            content_type=resp.headers.get("content-type"),
            previous_digest=prev_digest,
            collector="worker-http",
            collector_version="0.4.0",
        )
        await self._frontier.complete(
            item.frontier_id, digest=obs["content_hash"], status=obs["status"]
        )
        return LoopResult(
            frontier_id=item.frontier_id,
            uri=item.uri,
            observation_id=obs["observation_id"],
            lifecycle=obs["status"],
            raw_ref=obs["raw_ref"],
            digest=obs["content_hash"],
            ok=True,
            body=resp.content,
            content_type=obs.get("content_type", ""),
            tenant_id=item.tenant_id,
        )

    async def pump_one(
        self, *, tenant_id: str | None = None, injected: FrontierItem | None = None
    ) -> LoopResult | None:
        """Pop one item (or use an injected one) and run it."""
        item = injected or await self._frontier.pop_next(tenant_id=tenant_id)
        if item is None:
            return None
        return await self.run_item(item)

    async def aclose(self) -> None:
        await self._client.aclose()
