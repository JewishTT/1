"""Operational metrics API (T068, US3).

Throughput, useful observations, discovery yield, duplicate ratio, browser
utilization, lags, queues, storage growth and cost — served from a hermetic
in-memory metrics sink for the smoke path (real adapters read Kafka lag,
ClickHouse aggregates and object storage sizes).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Annotated

from fastapi import APIRouter, Depends

from api.auth import TenantContext, resolve_tenant
from services.worker_pools import WorkerKind, WorkerPoolRegistry

router = APIRouter(prefix="/metrics", tags=["metrics"])

_worker_pools = WorkerPoolRegistry()


@dataclass
class Metrics:
    throughput_per_s: float = 0.0
    useful_observations: int = 0
    discovery_yield: float = 0.0
    duplicate_ratio: float = 0.0
    browser_utilization: float = 0.0
    lags_s: dict[str, float] = field(default_factory=dict)
    queues: dict[str, int] = field(default_factory=dict)
    storage_growth_b: dict[str, int] = field(default_factory=dict)
    cost_per_1m_obs: float = 0.0


_metrics = Metrics(
    throughput_per_s=142.3,
    useful_observations=1_048_576,
    discovery_yield=0.41,
    duplicate_ratio=0.12,
    lags_s={"dispatcher->interpretation": 8.4, "interpretation->projection": 11.2},
    queues={"frontier": 24_318},
    storage_growth_b={"observations": 512_000_000, "events": 96_000_000},
    cost_per_1m_obs=3.75,
)


@router.get("")
async def metrics(ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None) -> dict:
    return _metric_payload()


@router.get("/pools")
async def pools(ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None) -> dict:
    return {
        "pools": {
            kind.value: {
                "healthy": _worker_pools.status(kind).healthy,
                "active": _worker_pools.status(kind).active,
                "capacity": _worker_pools.status(kind).capacity,
                "failures": _worker_pools.status(kind).failures,
            }
            for kind in WorkerKind
        },
        "healthy": _worker_pools.healthy_kinds(),
    }


def _metric_payload() -> dict:
    payload = asdict(_metrics)
    browser = _worker_pools.status(WorkerKind.BROWSER)
    payload["browser_utilization"] = round(
        browser.active / browser.capacity if browser.capacity else 0.0, 3
    )
    return payload