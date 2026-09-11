"""Policy & Budget models + policy engine (T022, FR-003/FR-027/FR-028).

Pre-dispatch validation against investigation/tenant policy; budget enforcement
with per-resource-class limits; retention policy. SWA/pricing never hard-coded
in domain logic (R-9) — read from config/limits passed at runtime.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any


class PolicyDecision(str, enum.Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    DEFER = "DEFER"


@dataclass
class ResourceLimit:
    cost_per_unit: float = 0.0
    max_units_per_window: float = float("inf")
    max_concurrency: int = 16


@dataclass
class Budget:
    budget_id: str
    tenant_id: str
    investigation_id: str | None = None
    limits: dict[str, ResourceLimit] = field(default_factory=dict)
    usage: dict[str, float] = field(default_factory=dict)  # worker_class -> spent

    def authorize(self, worker_class: str, units: float) -> PolicyDecision:
        limit = self.limits.get(worker_class)
        if limit is None:
            return PolicyDecision.ALLOW
        spent = self.usage.get(worker_class, 0.0)
        if spent + units > limit.max_units_per_window:
            return PolicyDecision.DENY
        return PolicyDecision.ALLOW

    def charge(self, worker_class: str, units: float) -> None:
        self.usage[worker_class] = self.usage.get(worker_class, 0.0) + units

    def over_limit(self) -> list[str]:
        return [
            wc
            for wc, limit in self.limits.items()
            if self.usage.get(wc, 0.0) > limit.max_units_per_window
        ]


@dataclass
class Policy:
    policy_id: str
    tenant_id: str
    name: str
    allowed_source_classes: list[str] = field(default_factory=list)
    forbidden_hosts: list[str] = field(default_factory=list)
    retention_days: int | None = None
    require_browser_escalation: bool = False
    rules: dict[str, Any] = field(default_factory=dict)

    def evaluate(self, *, source_class: str, host: str, budget: Budget | None = None) -> PolicyDecision:
        if self.allowed_source_classes and source_class not in self.allowed_source_classes:
            return PolicyDecision.DENY
        if host in self.forbidden_hosts:
            return PolicyDecision.DENY
        if self.require_browser_escalation:
            return PolicyDecision.DEFER
        return PolicyDecision.ALLOW


class PolicyEngine:
    """Applies policy + budget before dispatch (pre-dispatch validation)."""

    def __init__(self, policies: dict[str, Policy], budgets: dict[str, Budget]) -> None:
        self._policies = policies
        self._budgets = budgets

    def check(
        self,
        *,
        policy_id: str,
        source_class: str,
        host: str,
        worker_class: str,
        units: float,
        budget_id: str | None = None,
    ) -> PolicyDecision:
        policy = self._policies.get(policy_id)
        if policy is None:
            return PolicyDecision.DENY

        decision = policy.evaluate(source_class=source_class, host=host)
        if decision is PolicyDecision.DENY:
            return PolicyDecision.DENY

        if budget_id and budget_id in self._budgets:
            budget = self._budgets[budget_id]
            budget_decision = budget.authorize(worker_class, units)
            if budget_decision is PolicyDecision.DENY:
                return PolicyDecision.DENY

        return decision

    def commit_usage(self, budget_id: str, worker_class: str, units: float) -> None:
        budget = self._budgets.get(budget_id)
        if budget:
            budget.charge(worker_class, units)