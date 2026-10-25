"""Fail-closed bearer authentication and tenant context for the control plane.

Production requests require a signed HS256 JWT issued by the configured identity
provider. The development header adapter is disabled unless explicitly opted into;
it never grants ADMIN. Tenant and role claims are accepted only after signature,
issuer, audience, expiry and claim-shape validation.
"""
from __future__ import annotations

import base64
import enum
import hashlib
import hmac
import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Annotated, Any

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
        if not any(self.has_role(role) for role in roles):
            raise HTTPException(status_code=403, detail="insufficient role")


_scheme = HTTPBearer(auto_error=False)
_SEGMENT_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _decode_base64url(segment: str) -> bytes:
    if not segment or _SEGMENT_RE.fullmatch(segment) is None:
        raise ValueError("invalid base64url segment")
    padded = segment + ("=" * (-len(segment) % 4))
    return base64.b64decode(
        padded.translate(str.maketrans("-_", "+/")),
        validate=True,
    )


def _json_object(segment: str) -> dict[str, Any]:
    value = json.loads(_decode_base64url(segment).decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JWT section must be an object")
    return value


def _verify_jwt(token: str, *, secret: bytes, issuer: str, audience: str) -> TenantContext:
    """Verify one configured HS256 JWT; never return unverified claims."""
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("malformed JWT")

    header = _json_object(parts[0])
    # Pin one algorithm. Never accept the token's algorithm choice generically.
    if header.get("alg") != "HS256" or header.get("typ", "JWT") != "JWT":
        raise ValueError("unsupported JWT header")

    signing_input = f"{parts[0]}.{parts[1]}".encode("ascii")
    signature = _decode_base64url(parts[2])
    expected = hmac.new(secret, signing_input, hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected):
        raise ValueError("invalid JWT signature")

    # Payload claims are not parsed until the signature is verified.
    claims = _json_object(parts[1])
    now = time.time()

    exp = claims.get("exp")
    if isinstance(exp, bool) or not isinstance(exp, (int, float)) or exp <= now:
        raise ValueError("missing or expired exp claim")
    for time_claim in ("iat", "nbf"):
        value = claims.get(time_claim)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"invalid {time_claim} claim")
        if time_claim == "iat" and value > now + 30:
            raise ValueError("iat is in the future")
        if time_claim == "nbf" and value > now:
            raise ValueError("token is not yet valid")

    if claims.get("iss") != issuer:
        raise ValueError("invalid issuer")
    aud = claims.get("aud")
    if not (
        aud == audience
        or (isinstance(aud, list) and all(isinstance(item, str) for item in aud) and audience in aud)
    ):
        raise ValueError("invalid audience")

    tenant_id = claims.get("tenant_id")
    user_id = claims.get("sub", claims.get("user_id"))
    role_values = claims.get("roles")
    if not isinstance(tenant_id, str) or not tenant_id.strip():
        raise ValueError("missing tenant_id")
    if not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("missing subject")
    if not isinstance(role_values, list) or not role_values:
        raise ValueError("missing roles")
    try:
        roles = frozenset(Role(value) for value in role_values if isinstance(value, str))
    except ValueError as exc:
        raise ValueError("unknown role") from exc
    if len(roles) != len(role_values):
        raise ValueError("invalid role list")

    return TenantContext(
        tenant_id=tenant_id.strip(),
        user_id=user_id.strip(),
        roles=roles,
    )


def _configured_jwt_context(token: str) -> TenantContext:
    secret_text = os.getenv("COGNITIVE_JWT_SECRET", "")
    issuer = os.getenv("COGNITIVE_JWT_ISSUER", "").strip()
    audience = os.getenv("COGNITIVE_JWT_AUDIENCE", "").strip()
    if len(secret_text.encode("utf-8")) < 32 or not issuer or not audience:
        raise HTTPException(
            status_code=503,
            detail="JWT authentication is not configured",
        )
    try:
        return _verify_jwt(
            token,
            secret=secret_text.encode("utf-8"),
            issuer=issuer,
            audience=audience,
        )
    except (ValueError, UnicodeError, json.JSONDecodeError, base64.binascii.Error):
        raise HTTPException(status_code=401, detail="invalid bearer token") from None


async def resolve_tenant(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_scheme)] = None,
) -> TenantContext:
    """Resolve an authenticated principal and its signed tenant/role claims.

    Default mode is JWT and fails closed. Header-based development identity may be
    enabled only with both COGNITIVE_AUTH_MODE=development and
    COGNITIVE_AUTH_ALLOW_DEV_HEADERS=true. That explicit adapter grants ANALYST,
    never ADMIN, and must not be enabled in a deployed environment.
    """
    if credentials is not None:
        if credentials.scheme.lower() != "bearer" or not credentials.credentials:
            raise HTTPException(status_code=401, detail="invalid bearer credentials")
        return _configured_jwt_context(credentials.credentials)

    mode = os.getenv("COGNITIVE_AUTH_MODE", "jwt").strip().lower()
    allow_dev_headers = os.getenv("COGNITIVE_AUTH_ALLOW_DEV_HEADERS", "").lower() == "true"
    if mode == "development" and allow_dev_headers:
        tenant_id = request.headers.get("x-tenant-id", "default-tenant").strip()
        user_id = request.headers.get("x-user-id", "dev-user").strip()
        if not tenant_id or not user_id:
            raise HTTPException(status_code=401, detail="invalid development identity")
        return TenantContext(
            tenant_id=tenant_id,
            user_id=user_id,
            roles=frozenset({Role.ANALYST}),
        )

    if mode not in {"jwt", "development"}:
        raise HTTPException(status_code=503, detail="unsupported authentication mode")
    raise HTTPException(status_code=401, detail="bearer token required")


async def require_analyst(ctx: Annotated[TenantContext, Depends(resolve_tenant)]) -> TenantContext:
    ctx.require_role(Role.ANALYST, Role.ADMIN)
    return ctx


async def require_admin(ctx: Annotated[TenantContext, Depends(resolve_tenant)]) -> TenantContext:
    ctx.require_role(Role.ADMIN)
    return ctx
