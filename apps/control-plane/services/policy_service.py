"""Policy service (T022): loads policies/budgets and runs pre-dispatch checks.

Wraps the domain PolicyEngine with persistence/configuration concerns.
"""

from __future__ import annotations

from typing import Any

from cp_domain.policy import Budget, Policy, PolicyDecision, PolicyEngine, ResourceLimit


class PolicyService:
    """In-memory policy/budget service; replaceable by a DB-backed impl.

    Provides default policy (``policies/default``) and default budget used by
    the quickstart smoke scenario.
    """

    def __init__(self) -> None:
        self._policies: dict[str, Policy] = {
            "policies/default": Policy(
                policy_id="policies/default",
                tenant_id="default-tenant",
                name="Default",
                allowed_source_classes=["HTTP", "RSS", "HTML"],
                forbidden_hosts=[],
                retention_days=30,
            )
        }
        self._budgets: dict[str, Budget] = {
            "budget/default": Budget(
                budget_id="budget/default",
                tenant_id="default-tenant",
                limits={
                    "http": ResourceLimit(cost_per_unit=0.001, max_units_per_window=1_000_000),
                    "browser": ResourceLimit(cost_per_unit=0.05, max_units_per_window=10_000),
                    "parse": ResourceLimit(cost_per_unit=0.002, max_units_per_window=500_000),
                },
            )
        }
        self._engine = PolicyEngine(self._policies, self._budgets)

    def get_policy(self, policy_id: str) -> Policy | None:
        return self._policies.get(policy_id)

    def get_budget(self, budget_id: str) -> Budget | None:
        return self._budgets.get(budget_id)

    def check(self, **kwargs: Any) -> PolicyDecision:
        return self._engine.check(**kwargs)

    def commit_usage(self, budget_id: str, worker_class: str, units: float) -> None:
        self._engine.commit_usage(budget_id, worker_class, units)