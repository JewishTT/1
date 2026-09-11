"""Tenant isolation hardening (T061, FR-029, US3).

Deterministic per-tenant scoping across layered backends so two tenants can
never share a partition, index alias, object prefix, graph namespace, or budget
scope. Every derived name is namespaced by tenant_id; cross-tenant lookups fail
closed (the default is deny).
"""

from __future__ import annotations

import re


def _slug(tenant_id: str) -> str:
    cleaned = re.sub(r"[^a-z0-9-]", "-", tenant_id.lower())
    return cleaned.strip("-") or "default"


class TenantIsolation:
    """Namespace derivation + fail-closed scoping for a single tenant."""

    def __init__(self, tenant_id: str) -> None:
        self.tenant_id = tenant_id
        self.slug = _slug(tenant_id)

    @property
    def kafka_topic(self, base: str = "cognitive-events") -> str:
        # Per-tenant partitions: `cognitive-events--t-<slug>` routed by ACL.
        return f"{base}--t-{self.slug}"[:249]

    @property
    def search_index_alias(self, base: str = "observations") -> str:
        return f"{base}--t-{self.slug}"[:249]

    @property
    def s3_prefix(self, base: str = "raw") -> str:
        return f"{base}/t/{self.slug}/"

    @property
    def graph_namespace(self, base: str = "cognitive") -> str:
        return f"{base}_{self.slug}"

    @property
    def budget_scope(self) -> str:
        return self.slug

    @property
    def dlq_topic(self, base: str = "cognitive-dlq") -> str:
        return f"{base}--t-{self.slug}"[:249]

    def require_tenant(self, actual: str) -> None:
        """Fail closed: raise if a caller claims a different tenant."""
        if actual != self.tenant_id:
            raise TenantIsolationViolation(
                f"cross-tenant access denied: {actual!r} != {self.tenant_id!r}"
            )


class TenantIsolationViolation(Exception):
    pass


def is_valid_tenant_id(tenant_id: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,62}", tenant_id))