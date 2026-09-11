"""Temporal client + worker connection bootstrap (T016).

Namespaces, task queues, retry policy config. Investigation lifecycle workflows
(T078) and recrawl schedulers use this client.
"""

from __future__ import annotations

from functools import lru_cache

from config.settings import get_settings


@lru_cache(maxsize=1)
def get_temporal_client():
    """Return a cached Temporal client connected to the dev cluster."""
    from temporalio.client import Client

    settings = get_settings()
    import asyncio

    async def _connect() -> Client:
        return await Client.connect(settings.temporal_host, namespace="default")

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Cannot block; caller must await _connect() directly.
        raise RuntimeError("Cannot call get_temporal_client() from a running event loop; await connect_temporal() instead.")

    return asyncio.run(_connect())


async def connect_temporal(host: str | None = None) -> Client:
    """Async Temporal client connection (use from async contexts)."""
    from temporalio.client import Client

    return await Client.connect(host or get_settings().temporal_host, namespace="default")


async def get_workflow_handle(client, workflow_id: str):
    return await client.get_handle(workflow_id)