"""The red-team boundary: authorization, identity validation and kill switch.

This module decides whether a red-team action may run. It is deliberately not an
allowlist: targets and recipients are constrained by the confirmed RoE and by ordinary
input validation, not by a hard-coded lab domain. The production RoE gate
(`specops.roe.gate`) still decides whether a sign-off is confirmed; this module decides
whether the request is well-formed and whether the lab is live.
"""

from __future__ import annotations

import threading
import uuid
from urllib.parse import urlsplit

from specops.lab.audit import AuditLog
from specops.lab.models import LabStatus, now_iso

ALLOWED_SCHEMES = frozenset({"lab", "http", "https"})


class LabError(Exception):
    code = "LabError"
    status_code = 400

    def __init__(self, reason: str, *, rejected: list[str] | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.rejected = rejected or []


class AuthorizationRefused(LabError):
    code = "AuthorizationRefused"
    status_code = 409


class CapabilityDisabled(AuthorizationRefused):
    code = "CapabilityDisabled"


class TargetRefused(LabError):
    code = "TargetRefused"
    status_code = 422


class ExternalAssetRefused(TargetRefused):
    code = "ExternalAssetRefused"


class EgressDenied(TargetRefused):
    code = "EgressDenied"


class SetupRequired(LabError):
    code = "SetupRequired"
    status_code = 424


class LabNotFound(LabError):
    code = "NotFound"
    status_code = 404


def _normalise_host(host: str) -> str:
    return host.strip().lower().rstrip(".")


def is_valid_identity(address: str) -> bool:
    """True for a syntactically valid mailbox, without restricting the domain."""
    address = address.strip()
    if not address or address.count("@") != 1 or any(c.isspace() for c in address):
        return False
    local, host = address.split("@", 1)
    host = _normalise_host(host)
    if not local or not host:
        return False
    if host.startswith("[") and host.endswith("]"):
        return bool(host[1:-1])
    return all(label and len(label) <= 63 for label in host.split("."))


def validate_roster(addresses: list[str]) -> None:
    seen: set[str] = set()
    refused: list[str] = []
    duplicates: list[str] = []
    for address in addresses:
        key = address.strip().lower()
        if not is_valid_identity(address):
            refused.append(address)
        elif key in seen:
            duplicates.append(address)
        seen.add(key)
    if refused:
        raise TargetRefused(
            f"{len(refused)} recipient(s) are not valid email addresses",
            rejected=refused,
        )
    if duplicates:
        raise TargetRefused(
            f"{len(duplicates)} duplicate recipient(s) in the roster",
            rejected=duplicates,
        )


def _split_target(target: str) -> tuple[str, int | None]:
    value = target.strip()
    if not value:
        raise TargetRefused("target is empty")
    if "://" in value:
        raise TargetRefused("target_host must be a host, not a URL", rejected=[target])
    parts = urlsplit(f"//{value}")
    host = _normalise_host(parts.hostname or "")
    try:
        port = parts.port
    except ValueError as exc:
        raise TargetRefused(f"target {target!r} has an invalid port", rejected=[target]) from exc
    if not host:
        raise TargetRefused(f"target {target!r} carries no host", rejected=[target])
    if any(c.isspace() for c in host) or "/" in host:
        raise TargetRefused(f"target {target!r} is not a valid host", rejected=[target])
    return host, port


class LabBoundary:
    def __init__(self, audit: AuditLog, targets: tuple[str, ...] | None = None) -> None:
        self._lock = threading.RLock()
        self._audit = audit
        self._lab_id = f"lab-{uuid.uuid4().hex[:10]}"
        self._targets = tuple(_normalise_host(t) for t in (targets or ("*",)))
        self._status = LabStatus.READY
        self._kill_switch_at: str | None = None
        self._teardown_at: str | None = None

    @property
    def lab_id(self) -> str:
        return self._lab_id

    @property
    def status(self) -> LabStatus:
        with self._lock:
            return self._status

    @property
    def targets(self) -> tuple[str, ...]:
        return self._targets

    def is_allowlisted(self, host: str) -> bool:
        """Kept for callers that still ask; the boundary is no longer an allowlist."""
        return bool(_normalise_host(host))

    def validate_host(self, host: str) -> str:
        normalised, _ = _split_target(host)
        return normalised

    def require_ready(self) -> None:
        with self._lock:
            if self._status is LabStatus.KILLED:
                raise AuthorizationRefused(
                    "lab kill switch is active; reset the lab before starting new activity"
                )
            if self._status is LabStatus.TORN_DOWN:
                raise AuthorizationRefused("lab is torn down; reset the lab before starting activity")

    def check_egress(
        self,
        url: str,
        *,
        tenant_id: str,
        actor: str,
        correlation_id: str = "",
        action: str = "egress.denied",
    ) -> str:
        """Return the normalised host, or raise and record a denial."""
        parts = urlsplit(url.strip())
        scheme = parts.scheme.lower()
        host = _normalise_host(parts.hostname or "")
        port = parts.port
        reason: str | None = None
        if scheme not in {"http", "https"}:
            reason = f"scheme {scheme or '(none)'} is not allowed"
        elif not host:
            reason = "URL carries no host"
        elif port is not None and not 1 <= port <= 65535:
            reason = f"port {port} is not valid"
        if reason is None:
            return host
        self._audit.append(
            tenant_id=tenant_id,
            actor=actor,
            action=action,
            object_type="egress",
            object_id=host or url,
            outcome="refused",
            correlation_id=correlation_id,
            detail={"reason": reason, "url": url, "policy": "roe-gated"},
        )
        raise EgressDenied(reason, rejected=[url])

    def validate_asset(self, asset: str, *, tenant_id: str, actor: str, correlation_id: str = "") -> None:
        """Assets may be local, relative or fetched over HTTP(S)."""
        asset = asset.strip()
        if not asset:
            raise ExternalAssetRefused("empty asset reference")
        parts = urlsplit(asset)
        if parts.scheme == "lab":
            return
        if parts.scheme in {"http", "https"}:
            self.check_egress(
                asset,
                tenant_id=tenant_id,
                actor=actor,
                correlation_id=correlation_id,
                action="template.asset_refused",
            )
            return
        if parts.scheme:
            raise ExternalAssetRefused(
                f"asset scheme {parts.scheme!r} is not allowed; use lab://, http(s):// or a relative path",
                rejected=[asset],
            )

    def kill_switch(
        self,
        *,
        tenant_id: str,
        actor: str,
        correlation_id: str = "",
        stopped_sessions: int = 0,
        partial_campaigns: int = 0,
    ) -> dict:
        with self._lock:
            already = self._status is LabStatus.KILLED
            self._status = LabStatus.KILLED
            self._kill_switch_at = self._kill_switch_at or now_iso()
            self._audit.append(
                tenant_id=tenant_id,
                actor=actor,
                action="lab.kill_switch",
                object_type="lab",
                object_id=self._lab_id,
                outcome="ok",
                correlation_id=correlation_id,
                detail={
                    "already_active": already,
                    "stopped_sessions": stopped_sessions,
                    "partial_campaigns": partial_campaigns,
                },
            )
            return self.view()

    def reset(self, *, tenant_id: str, actor: str, correlation_id: str = "") -> dict:
        with self._lock:
            self._status = LabStatus.READY
            self._kill_switch_at = None
            self._teardown_at = None
            self._audit.append(
                tenant_id=tenant_id,
                actor=actor,
                action="lab.reset",
                object_type="lab",
                object_id=self._lab_id,
                outcome="ok",
                correlation_id=correlation_id,
                detail={"evidence_preserved": True},
            )
            return self.view()

    def teardown(self, *, tenant_id: str, actor: str, correlation_id: str = "") -> dict:
        with self._lock:
            self._status = LabStatus.TORN_DOWN
            self._teardown_at = now_iso()
            self._audit.append(
                tenant_id=tenant_id,
                actor=actor,
                action="lab.teardown",
                object_type="lab",
                object_id=self._lab_id,
                outcome="ok",
                correlation_id=correlation_id,
                detail={"evidence_deleted": False},
            )
            return self.view()

    def view(self) -> dict:
        with self._lock:
            return {
                "lab_id": self._lab_id,
                "status": self._status.value,
                "egress_policy": "roe-gated",
                "targets": list(self._targets),
                "kill_switch_at": self._kill_switch_at,
                "teardown_at": self._teardown_at,
            }
