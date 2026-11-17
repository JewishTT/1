"""Deployment composition root for the SpecOps&CI Temporal worker.

ARTEX graph storage and the safe assessment evaluator remain deployment-owned ports.
This factory binds them to the repository's PostgreSQL authorization gate and fails
closed when either adapter factory is absent or incomplete.
"""
from __future__ import annotations

import importlib
import os
from typing import Any

from db.session import make_session_factory
from services.specops_ci_authorization_gate import PostgresSpecOpsAuthorizationGate
from specops_ci.orchestration.runtime_ports import ArtexSpecOpsRuntime


def _load_factory(env_name: str) -> Any:
    """Load a zero-argument deployment factory from python.module:factory_name."""
    value = os.environ.get(env_name, "").strip()
    if ":" not in value:
        raise RuntimeError(f"{env_name} must be set to 'python.module:factory_name'")
    module_name, factory_name = value.split(":", 1)
    if not module_name or not factory_name:
        raise RuntimeError(f"{env_name} is malformed")
    module = importlib.import_module(module_name)
    factory = getattr(module, factory_name, None)
    if not callable(factory):
        raise TypeError(f"{env_name} does not resolve to a callable factory")
    return factory


def build_runtime() -> ArtexSpecOpsRuntime:
    """Build the trusted adapter composition used by Temporal Activities."""
    graph_factory = _load_factory("SPECOPS_CI_ARTEX_GRAPH_FACTORY")
    evaluator_factory = _load_factory("SPECOPS_CI_ASSESSMENT_ENGINE_FACTORY")
    graphs = graph_factory()
    evaluator = evaluator_factory()
    if graphs is None or evaluator is None:
        raise RuntimeError("ARTEX graph and assessment factories must return live adapters")
    return ArtexSpecOpsRuntime(
        authorization=PostgresSpecOpsAuthorizationGate(make_session_factory()),
        graphs=graphs,
        evaluator=evaluator,
    )


__all__ = ["build_runtime"]
