"""Security contract tests for the control-plane authentication boundary."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from starlette.requests import Request

from api.auth import Role, TenantContext, _verify_jwt, resolve_tenant


SECRET = b"test-secret-that-is-at-least-32-bytes-long"
ISSUER = "test-issuer"
AUDIENCE = "cognitive-control-plane"


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _token(payload: dict, *, secret: bytes = SECRET, alg: str = "HS256") -> str:
    header = _b64(json.dumps({"alg": alg, "typ": "JWT"}, separators=(",", ":")).encode())
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    message = f"{header}.{body}".encode("ascii")
    signature = _b64(hmac.new(secret, message, hashlib.sha256).digest())
    return f"{header}.{body}.{signature}"


def _payload(**overrides: object) -> dict:
    payload = {
        "sub": "analyst-1",
        "tenant_id": "tenant-1",
        "roles": ["analyst"],
        "iss": ISSUER,
        "aud": AUDIENCE,
        "iat": time.time() - 1,
        "exp": time.time() + 300,
    }
    payload.update(overrides)
    return payload


def _request(headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    return Request({
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": headers or [],
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 12345),
    })


def test_valid_signed_jwt_resolves_expected_tenant_and_roles() -> None:
    ctx = _verify_jwt(_token(_payload()), secret=SECRET, issuer=ISSUER, audience=AUDIENCE)
    assert ctx == TenantContext("tenant-1", "analyst-1", frozenset({Role.ANALYST}))


def test_jwt_signature_tampering_is_rejected() -> None:
    token = _token(_payload())
    parts = token.split(".")
    parts[1] = _b64(json.dumps(_payload(tenant_id="victim-tenant")).encode())
    with pytest.raises(ValueError):
        _verify_jwt(".".join(parts), secret=SECRET, issuer=ISSUER, audience=AUDIENCE)


def test_expired_wrong_audience_and_wrong_algorithm_are_rejected() -> None:
    with pytest.raises(ValueError):
        _verify_jwt(
            _token(_payload(exp=time.time() - 10)),
            secret=SECRET,
            issuer=ISSUER,
            audience=AUDIENCE,
        )
    with pytest.raises(ValueError):
        _verify_jwt(
            _token(_payload(aud="some-other-service")),
            secret=SECRET,
            issuer=ISSUER,
            audience=AUDIENCE,
        )
    with pytest.raises(ValueError):
        _verify_jwt(
            _token(_payload(), alg="none"),
            secret=SECRET,
            issuer=ISSUER,
            audience=AUDIENCE,
        )


@pytest.mark.asyncio
async def test_missing_credentials_fail_closed_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COGNITIVE_AUTH_MODE", raising=False)
    monkeypatch.delenv("COGNITIVE_AUTH_ALLOW_DEV_HEADERS", raising=False)
    with pytest.raises(HTTPException) as exc:
        await resolve_tenant(_request(), None)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_development_headers_never_grant_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COGNITIVE_AUTH_MODE", "development")
    monkeypatch.setenv("COGNITIVE_AUTH_ALLOW_DEV_HEADERS", "true")
    request = _request([
        (b"x-tenant-id", b"dev-tenant"),
        (b"x-user-id", b"dev-user"),
    ])
    ctx = await resolve_tenant(request, None)
    assert ctx.tenant_id == "dev-tenant"
    assert ctx.user_id == "dev-user"
    assert ctx.has_role(Role.ANALYST)
    assert not ctx.has_role(Role.ADMIN)


def test_expiration_and_identity_claims_are_mandatory() -> None:
    with pytest.raises(ValueError):
        _verify_jwt(
            _token(_payload(exp=float("nan"))),
            secret=SECRET,
            issuer=ISSUER,
            audience=AUDIENCE,
        )
    payload = _payload()
    del payload["exp"]
    with pytest.raises(ValueError):
        _verify_jwt(_token(payload), secret=SECRET, issuer=ISSUER, audience=AUDIENCE)
    with pytest.raises(ValueError):
        _verify_jwt(
            _token(_payload(tenant_id="")),
            secret=SECRET,
            issuer=ISSUER,
            audience=AUDIENCE,
        )
