from __future__ import annotations

import pytest

from api.auth import TenantContext
from api.routes import metrics


def test_metrics_are_unavailable_instead_of_fabricated() -> None:
    payload = metrics._metric_payload()
    assert payload["availability"] == "unavailable"
    assert payload["scope"] == "tenant"
    assert all(payload[key] is None for key in (
        "throughput_per_s", "useful_observations", "discovery_yield",
        "duplicate_ratio", "browser_utilization", "cost_per_1m_obs",
    ))
    assert payload["lags_s"] == {}
    assert payload["queues"] == {}
    assert payload["storage_growth_b"] == {}


@pytest.mark.asyncio
async def test_worker_pool_endpoint_does_not_publish_private_mock_registry() -> None:
    payload = await metrics.pools(TenantContext("tenant-a", "analyst-a"))
    assert payload["availability"] == "unavailable"
    assert payload["pools"] == {}
