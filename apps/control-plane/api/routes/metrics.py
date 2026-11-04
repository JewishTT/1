"""Honest operational metrics contract.

The route deliberately reports unavailable measurements until tenant-scoped,
time-windowed telemetry adapters are wired. It must never substitute seeded
numbers or process-local mock counters for production measurements.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from api.auth import TenantContext, resolve_tenant

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("")
async def metrics(ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None) -> dict:
    return _metric_payload()


@router.get("/pools")
async def pools(ctx: Annotated[TenantContext, Depends(resolve_tenant)] = None) -> dict:
    return {
        "pools": {},
        "healthy": [],
        "availability": "unavailable",
        "reason": "worker-pool telemetry is not connected to the control plane",
    }


def _metric_payload() -> dict:
    return {
        "availability": "unavailable",
        "scope": "tenant",
        "reason": "tenant-scoped telemetry and time-windowed aggregates are not connected",
        "throughput_per_s": None,
        "useful_observations": None,
        "discovery_yield": None,
        "duplicate_ratio": None,
        "browser_utilization": None,
        "lags_s": {},
        "queues": {},
        "storage_growth_b": {},
        "cost_per_1m_obs": None,
        "metric_sources": {
            "throughput_per_s": "not_connected",
            "useful_observations": "not_connected",
            "discovery_yield": "not_connected",
            "duplicate_ratio": "not_connected",
            "browser_utilization": "not_connected",
            "lags_s": "not_connected",
            "queues": "not_connected",
            "storage_growth_b": "not_connected",
            "cost_per_1m_obs": "not_connected",
        },
    }
