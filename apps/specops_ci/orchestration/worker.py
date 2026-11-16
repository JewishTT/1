"""Dedicated Temporal Worker for SpecOps&CI durable operation graphs.

A deployment must supply an adapter factory that binds its authorization store,
ARTEX Asset/Exploration Graphs and read-only assessment evaluator. There is no
permissive default adapter.
"""
from __future__ import annotations

import asyncio
import importlib
import os
from datetime import timedelta
from typing import Any

from temporalio.client import Client
from temporalio.common import RetryPolicy
from temporalio.langgraph import LangGraphPlugin
from temporalio.worker import Worker

from specops_ci.orchestration.graph import GRAPH_NAME, build_operation_graph
from specops_ci.orchestration.runtime_ports import configure_runtime_ports
from specops_ci.orchestration.workflow import SpecOpsOperationWorkflow


def _load_runtime_ports() -> Any:
    factory_path = os.environ.get("SPECOPS_CI_RUNTIME_FACTORY", "")
    if ":" not in factory_path:
        raise RuntimeError(
            "SPECOPS_CI_RUNTIME_FACTORY must be set to 'python.module:factory_name'"
        )
    module_name, factory_name = factory_path.split(":", 1)
    if not module_name or not factory_name:
        raise RuntimeError("SPECOPS_CI_RUNTIME_FACTORY is malformed")
    factory = getattr(importlib.import_module(module_name), factory_name)
    ports = factory()
    if asyncio.iscoroutine(ports):
        raise TypeError("runtime factory must be synchronous; initialize async clients in the factory")
    return ports


async def run_worker() -> None:
    """Connect to Temporal and serve only the registered SpecOps operation graph."""
    address = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")
    namespace = os.environ.get("TEMPORAL_NAMESPACE", "default")
    task_queue = os.environ.get("SPECOPS_CI_TASK_QUEUE", "specops-ci-operations")
    configure_runtime_ports(_load_runtime_ports())

    client = await Client.connect(address, namespace=namespace)
    plugin = LangGraphPlugin(
        graphs={GRAPH_NAME: build_operation_graph()},
        default_activity_options={
            "start_to_close_timeout": timedelta(minutes=5),
            "retry_policy": RetryPolicy(maximum_attempts=3),
        },
    )
    worker = Worker(
        client,
        task_queue=task_queue,
        workflows=[SpecOpsOperationWorkflow],
        plugins=[plugin],
    )
    await worker.run()


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
