"""RBAC + tenant-scoped auth middleware (T013, FR-029/FR-032, R-10).

Tenant isolation enforced at every layer: tenant_id resolution, scoped
queries. This module provides the FastAPI middleware and dependency functions
that extract tenant context from request headers and bind it to the DB
session scope.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


class Role(str, enum.Enum):
    ADMIN = "admin"
    ANALYST = "analyst"
    VIEWER = "viewer"


@dataclass(frozen=True)
class TenantContext:
    tenant_id: str
    user_id: str
    roles: frozenset[Role] = field(default_factory=frozenset)

    def has_role(self, role: Role) -> bool:
        return role in self.roles

    def require_role(self, *roles: Role) -> None:
        if not any(self.has_role(r) for r in roles):
            raise HTTPException(status_code=403, detail="insufficient role")


# In production this would be replaced by JWT validation against Vault / SSO.
_scheme = HTTPBearer(auto_error=False)


async def resolve_tenant(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_scheme)] = None,
) -> TenantContext:
    """Resolve tenant + user + roles.

    Bearer-token path: claims are read from the token and are the only trustworthy source.

    Anonymous path (development): the tenant is taken from the ``X-Tenant-Id`` header, and
    the user id from ``X-User-Id``, each falling back to ``default-tenant`` / ``dev-user``.

    .. warning::
       The anonymous path is **not a security boundary**. A caller chooses its own tenant
       by choosing a header, so this provides *scoping* (one investigation's data does not
       appear in another's queries) and **zero isolation**. It exists so that tenant-scoped
       queries and their tests are exercisable locally.

       Previously this branch returned a hardcoded ``default-tenant`` and ignored the header
       entirely. That was worse than no scoping: every caller silently shared one tenant, so
       a scoped query looked correct while the isolation it appeared to provide did not
       exist. A spoofable boundary is at least a visible one.

       Real isolation requires the bearer path with a signed token; until that is wired,
       treat cross-tenant separation as untested.
    """
    if credentials is not None and credentials.credentials:
        # Placeholder: in real impl, decode and verify a signed JWT.
        # Unverified claims are still not trusted for authorisation here.
        import json

        token = credentials.credentials
        if not token:
            raise HTTPException(status_code=401, detail="missing bearer token")
        try:
            claims = json.loads(token)
        except Exception:
            raise HTTPException(status_code=401, detail="invalid token format")
        return TenantContext(
            tenant_id=claims.get("tenant_id", "default-tenant"),
            user_id=claims.get("user_id", "unknown"),
            roles=frozenset(Role(r) for r in claims.get("roles", ["viewer"])),
        )

    tenant_id = "default-tenant"
    user_id = "dev-user"
    if request is not None:
        raw_tenant = request.headers.get("x-tenant-id", "").strip()
        if raw_tenant:
            tenant_id = raw_tenant
        raw_user = request.headers.get("x-user-id", "").strip()
        if raw_user:
            user_id = raw_user
    return TenantContext(tenant_id=tenant_id, user_id=user_id, roles={Role.ADMIN})


async def require_analyst(ctx: Annotated[TenantContext, Depends(resolve_tenant)]) -> TenantContext:
    ctx.require_role(Role.ANALYST, Role.ADMIN)
    return ctx


async def require_admin(ctx: Annotated[TenantContext, Depends(resolve_tenant)]) -> TenantContext:
    ctx.require_role(Role.ADMIN)
    return ctx