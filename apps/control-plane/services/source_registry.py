"""Source registry + SourceProfile (T023, FR-005, R-3).

Capabilities, quality profile, yield/cost/freshness per source. Workers expose
capabilities()/estimate()/acquire() (Constitution V, AcquisitionWorker contract);
the registry associates source profiles with worker classes.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


@dataclass
class SourceProfile:
    source_id: str
    tenant_id: str
    uri: str
    source_class: str
    worker_class: str
    quality_score: float = 0.5
    yield_est: float = 0.0
    cost_per_unit: float = 0.0
    freshness_note: str = ""
    capabilities: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "tenant_id": self.tenant_id,
            "uri": self.uri,
            "source_class": self.source_class,
            "worker_class": self.worker_class,
            "quality_score": self.quality_score,
            "yield_est": self.yield_est,
            "cost_per_unit": self.cost_per_unit,
            "freshness_note": self.freshness_note,
            "capabilities": self.capabilities,
        }


class SourceRegistry:
    """Registers and resolves source profiles by (tenant, uri)."""

    def __init__(self) -> None:
        self._sources: dict[str, SourceProfile] = {}

    def register(self, profile: SourceProfile) -> None:
        self._sources[(profile.tenant_id, profile.uri)] = profile

    def get(self, tenant_id: str, uri: str) -> SourceProfile | None:
        return self._sources.get((tenant_id, uri))

    def list(self, tenant_id: str) -> list[SourceProfile]:
        return [s for (tid, _), s in self._sources.items() if tid == tenant_id]

    def default_for_uri(self, uri: str, tenant_id: str | None = None) -> SourceProfile:
        tenant = tenant_id or "default-tenant"
        uri_lower = uri.lower()
        if uri_lower.endswith(".xml") or "sitemap" in uri_lower:
            klass, worker = "RSS", "rss-http"
        elif uri_lower.startswith("http"):
            klass, worker = "HTML", "html-http"
        else:
            klass, worker = "HTTP", "http"
        return SourceProfile(
            source_id=f"src-{abs(hash(uri)) % 10**8}",
            tenant_id=tenant,
            uri=uri,
            source_class=klass,
            worker_class=worker,
            capabilities=["capabilities", "estimate", "acquire"],
        )


# ---------------------------------------------------------------------------
# Connector registry + recon plans (T026, FR-008/FR-009, SpiderFoot/reNgine)
# ---------------------------------------------------------------------------


class ConnectorStatus(str, Enum):
    REGISTERED = "REGISTERED"
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


@dataclass
class Connector:
    """Source connector implementing the AcquisitionWorker contract (FR-008)."""

    name: str
    tenant_id: str
    source_types: list[str] = field(default_factory=list)
    capabilities: dict = field(default_factory=dict)
    policy_id: str = "policies/default"
    version: str = "1.0"
    connector_id: str = field(default_factory=lambda: "CN-" + uuid.uuid4().hex[:12])
    status: ConnectorStatus = ConnectorStatus.REGISTERED
    impl: Any | None = None  # object exposing capabilities()/estimate()/acquire()

    REQUIRED_CONTRACT: frozenset[str] = frozenset({"capabilities", "estimate", "acquire"})

    def compliant(self) -> bool:
        """AcquisitionWorker compliance: impl must expose the three methods."""
        if self.impl is None:
            return False
        return all(callable(getattr(self.impl, m, None)) for m in self.REQUIRED_CONTRACT)

    def to_dict(self) -> dict[str, Any]:
        return {
            "connector_id": self.connector_id,
            "name": self.name,
            "tenant_id": self.tenant_id,
            "source_types": list(self.source_types),
            "capabilities": dict(self.capabilities),
            "policy_id": self.policy_id,
            "version": self.version,
            "status": self.status.value,
            "contract_compliant": self.compliant(),
        }


class ConnectorRegistry:
    """Registers connectors, gates ACTIVE on AcquisitionWorker compliance."""

    def __init__(self) -> None:
        self._connectors: dict[str, Connector] = {}

    def register(self, connector: Connector) -> Connector:
        if connector.name in self._connectors:
            raise ValueError(f"connector already registered: {connector.name}")
        connector.status = ConnectorStatus.REGISTERED
        self._connectors[connector.name] = connector
        return connector

    def activate(self, name: str) -> Connector:
        connector = self._connectors.get(name)
        if connector is None:
            raise KeyError(name)
        if not connector.compliant():
            raise ValueError(
                f"connector '{name}' must satisfy AcquisitionWorker "
                f"(capabilities/estimate/acquire) before ACTIVE"
            )
        connector.status = ConnectorStatus.ACTIVE
        return connector

    def disable(self, name: str) -> Connector:
        connector = self._connectors.get(name)
        if connector is None:
            raise KeyError(name)
        connector.status = ConnectorStatus.DISABLED
        return connector

    def get(self, name: str) -> Connector | None:
        return self._connectors.get(name)

    def list(self, tenant_id: str | None = None) -> list[Connector]:
        return [
            c for c in self._connectors.values()
            if tenant_id is None or c.tenant_id == tenant_id
        ]


class ReconPlanStatus(str, Enum):
    PLANNED = "PLANNED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass
class ReconPlan:
    """reNgine-style recon orchestration over acquisition tasks (FR-009)."""

    plan_id: str = field(default_factory=lambda: "RP-" + uuid.uuid4().hex[:12])
    investigation_id: str = ""
    tenant_id: str = "default-tenant"
    strategy: dict = field(default_factory=dict)
    task_ids: list[str] = field(default_factory=list)
    status: ReconPlanStatus = ReconPlanStatus.PLANNED
    started_at: str = ""
    finished_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "investigation_id": self.investigation_id,
            "tenant_id": self.tenant_id,
            "strategy": dict(self.strategy),
            "task_ids": list(self.task_ids),
            "status": self.status.value,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


class ReconPlanService:
    """Creates and advances recon plans (Investigation → Tasks → Kafka → Collectors)."""

    def __init__(self) -> None:
        self._plans: dict[str, ReconPlan] = {}

    def create(self, *, investigation_id: str, tenant_id: str, strategy: dict | None = None) -> ReconPlan:
        plan = ReconPlan(
            investigation_id=investigation_id,
            tenant_id=tenant_id,
            strategy=strategy or {},
        )
        self._plans[plan.plan_id] = plan
        return plan

    def start(self, plan_id: str, task_ids: list[str]) -> ReconPlan:
        plan = self._get(plan_id)
        if plan.status not in (ReconPlanStatus.PLANNED, ReconPlanStatus.FAILED):
            raise ValueError(f"plan {plan_id} already started")
        plan.task_ids = list(task_ids)
        plan.status = ReconPlanStatus.RUNNING
        plan.started_at = plan.started_at or datetime.now(UTC).isoformat()
        return plan

    def complete(self, plan_id: str) -> ReconPlan:
        plan = self._get(plan_id)
        plan.status = ReconPlanStatus.COMPLETED
        plan.finished_at = datetime.now(UTC).isoformat()
        return plan

    def fail(self, plan_id: str, reason: str = "") -> ReconPlan:
        plan = self._get(plan_id)
        plan.status = ReconPlanStatus.FAILED
        plan.finished_at = datetime.now(UTC).isoformat()
        plan.strategy["failure_reason"] = reason
        return plan

    def get(self, plan_id: str) -> ReconPlan | None:
        return self._plans.get(plan_id)

    def list(self, tenant_id: str | None = None) -> list[ReconPlan]:
        return [
            p for p in self._plans.values()
            if tenant_id is None or p.tenant_id == tenant_id
        ]

    def _get(self, plan_id: str) -> ReconPlan:
        plan = self._plans.get(plan_id)
        if plan is None:
            raise KeyError(plan_id)
        return plan