"""Authenticated control-plane factory for the Intelligence read boundary."""
from __future__ import annotations

from api.auth import TenantContext
from composition import get_platform
from services.intelligence_reader import PostgresIntelligenceReadPort


async def intelligence_port(ctx: TenantContext, *, purpose: str) -> PostgresIntelligenceReadPort:
    """Bind the PostgreSQL read port to the authenticated tenant and approved API purpose."""
    platform = await get_platform(tenant_id=ctx.tenant_id)
    if platform.session_factory is None:
        raise RuntimeError("durable PostgreSQL session factory is unavailable")
    return PostgresIntelligenceReadPort(
        platform.session_factory,
        tenant_id=ctx.tenant_id,
        allowed_purposes=frozenset({purpose}),
    )


__all__ = ["intelligence_port"]
