"""Bounded adapter for a separately deployed theHarvester REST API.

Only the passive subdomains capability is submitted. Person/email/breach results,
DNS brute force, takeover, screenshots, virtual-host probes and other active
actions are not exposed. The upstream is GPL-2.0-only and currently requires
Python 3.14, so the Python 3.11-3.13 acquisition workspace uses its documented
REST/JSONL boundary instead of linking or vendoring upstream implementation.
"""
from __future__ import annotations

import ipaddress
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


MAX_RESPONSE_BYTES = 16 * 1024 * 1024
MAX_RESULTS = 10_000
TERMINAL_STATES = frozenset({"completed", "failed", "cancelled"})


class AdapterError(RuntimeError):
    """Sanitized connector error; never includes request headers or response bodies."""


class AuthorizationError(AdapterError):
    """The requested network action is outside the recorded authorization scope."""


def normalize_domain(value: str) -> str:
    raw = str(value or "").strip().rstrip(".")
    if not raw or any(token in raw for token in ("://", "/", "?", "#", "@")):
        raise ValueError("expected a bare DNS domain")
    try:
        ipaddress.ip_address(raw.strip("[]"))
    except ValueError:
        pass
    else:
        raise ValueError("IP literals are not domain scopes")
    try:
        normalized = raw.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise ValueError("invalid IDNA domain") from exc
    if len(normalized) > 253 or "." not in normalized:
        raise ValueError("domain must be a fully qualified DNS name")
    labels = normalized.split(".")
    if any(not label or len(label) > 63 for label in labels):
        raise ValueError("invalid DNS label")
    if any(not all(ch.isalnum() or ch == "-" for ch in label) for label in labels):
        raise ValueError("invalid DNS label")
    if any(label.startswith("-") or label.endswith("-") for label in labels):
        raise ValueError("invalid DNS label")
    return normalized


@dataclass(frozen=True)
class AuthorizationScope:
    """Time-bounded authorization for a finite passive discovery operation."""

    tenant_id: str
    authorization_ref: str
    allowed_domains: tuple[str, ...]
    expires_at: datetime
    allow_tls_probe: bool = False

    def __post_init__(self) -> None:
        if not self.tenant_id.strip() or not self.authorization_ref.strip():
            raise ValueError("tenant_id and authorization_ref are required")
        if self.expires_at.tzinfo is None:
            raise ValueError("expires_at must be timezone-aware")
        roots = tuple(sorted({normalize_domain(item) for item in self.allowed_domains}))
        if not roots:
            raise ValueError("at least one authorized domain is required")
        object.__setattr__(self, "allowed_domains", roots)

    def assert_active(self, *, now: datetime | None = None) -> None:
        moment = now or datetime.now(UTC)
        if moment.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        if moment >= self.expires_at:
            raise AuthorizationError("authorization window has expired")

    def contains_domain(self, value: str) -> bool:
        try:
            host = normalize_domain(value)
        except ValueError:
            return False
        return any(host == root or host.endswith("." + root) for root in self.allowed_domains)

    def assert_domain(self, value: str, *, now: datetime | None = None) -> str:
        self.assert_active(now=now)
        host = normalize_domain(value)
        if not self.contains_domain(host):
            raise AuthorizationError("domain is outside the approved scope")
        return host

    def assert_tls_probe(self, value: str, *, now: datetime | None = None) -> str:
        if not self.allow_tls_probe:
            raise AuthorizationError("TLS probing was not included in the authorization")
        return self.assert_domain(value, now=now)


@dataclass(frozen=True)
class HarvestedRecord:
    kind: str
    value: str
    source_ids: tuple[str, ...]
    scope_class: str
    expandable: bool


@dataclass(frozen=True)
class RunEvidence:
    run_id: str
    lifecycle_status: str
    evidence_status: str
    records: tuple[HarvestedRecord, ...]
    source_outcomes: tuple[dict[str, Any], ...]
    filtered_counts: dict[str, int]
    submitted_at: str
    completed_at: str | None

    @property
    def may_support_qualified_absence(self) -> bool:
        return (
            self.evidence_status == "complete"
            and bool(self.source_outcomes)
            and all(str(item.get("status", "")).lower() in {"complete", "completed"} for item in self.source_outcomes)
        )


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


class TheHarvesterApiClient:
    """Finite, passive-only client for a separately deployed theHarvester service."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout_seconds: float = 10.0,
        max_wait_seconds: float = 600.0,
        poll_interval_seconds: float = 2.0,
        max_response_bytes: int = MAX_RESPONSE_BYTES,
        opener: Any | None = None,
    ) -> None:
        parsed = urlsplit(base_url.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("base_url must be an absolute HTTP(S) origin")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("base_url must not contain credentials, query, or fragment")
        if parsed.scheme == "http" and parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("non-loopback theHarvester endpoints must use HTTPS")
        if not api_key.strip():
            raise ValueError("theHarvester API key is required")
        if not 0 < timeout_seconds <= 30:
            raise ValueError("timeout_seconds must be in (0, 30]")
        if not 0 < max_wait_seconds <= 600:
            raise ValueError("max_wait_seconds must be in (0, 600]")
        if not 0.1 <= poll_interval_seconds <= 10:
            raise ValueError("poll_interval_seconds must be in [0.1, 10]")
        if not 1024 <= max_response_bytes <= MAX_RESPONSE_BYTES:
            raise ValueError("max_response_bytes is outside the supported bound")
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = float(timeout_seconds)
        self._max_wait = float(max_wait_seconds)
        self._poll_interval = float(poll_interval_seconds)
        self._max_response_bytes = int(max_response_bytes)
        self._opener = opener or build_opener(_NoRedirect())

    @property
    def base_url(self) -> str:
        """Configured API origin without credentials or query parameters."""
        return self._base_url

    @staticmethod
    def safe_run_request(target: str, *, limit: int = 500, source_workers: int = 3) -> dict[str, Any]:
        if not 1 <= limit <= MAX_RESULTS:
            raise ValueError(f"limit must be in [1, {MAX_RESULTS}]")
        if not 1 <= source_workers <= 5:
            raise ValueError("source_workers must be in [1, 5]")
        return {
            "target": normalize_domain(target),
            "sources": ["subdomains"],
            "limit": limit,
            "source_workers": source_workers,
            "deadline_seconds": 600,
        }

    def run_authorized_domain(
        self,
        target: str,
        scope: AuthorizationScope,
        *,
        limit: int = 500,
        source_workers: int = 3,
        stop_event: Any | None = None,
    ) -> RunEvidence:
        domain = scope.assert_domain(target)
        submitted_at = datetime.now(UTC).isoformat()
        request_body = self.safe_run_request(domain, limit=limit, source_workers=source_workers)
        submitted = self._request_json("POST", "/api/v1/runs", request_body)
        run_id = str(submitted.get("run_id") or submitted.get("id") or "").strip()
        if not run_id or len(run_id) > 256:
            raise AdapterError("theHarvester did not return a valid run identifier")
        deadline = time.monotonic() + self._max_wait
        terminal: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            if stop_event is not None and stop_event.is_set():
                self._cancel(run_id)
                raise AdapterError("run cancelled by operator")
            state = self._request_json("GET", f"/api/v1/runs/{quote(run_id, safe='')}")
            lifecycle = str(state.get("status") or "").lower()
            if lifecycle in TERMINAL_STATES:
                terminal = state
                break
            time.sleep(min(self._poll_interval, max(0.0, deadline - time.monotonic())))
        if terminal is None:
            self._cancel(run_id)
            raise AdapterError("theHarvester run exceeded the configured deadline")
        ndjson = self._request_text("GET", f"/api/v1/runs/{quote(run_id, safe='')}/export")
        summary, raw_records = _parse_export(ndjson)
        outcomes = _source_outcomes(summary, terminal)
        evidence_status = str(
            summary.get("evidence_status")
            or terminal.get("evidence_status")
            or ("failed" if terminal.get("status") == "failed" else "partial")
        ).lower()
        if evidence_status not in {"complete", "partial", "failed"}:
            evidence_status = "partial"
        records, filtered = normalize_findings(raw_records, scope, target=domain)
        if terminal.get("status") != "completed":
            evidence_status = "failed" if terminal.get("status") == "failed" else "partial"
        return RunEvidence(
            run_id=run_id,
            lifecycle_status=str(terminal.get("status") or "unknown"),
            evidence_status=evidence_status,
            records=tuple(records),
            source_outcomes=tuple(outcomes),
            filtered_counts=filtered,
            submitted_at=submitted_at,
            completed_at=str(terminal.get("completed_at") or "") or None,
        )

    def _cancel(self, run_id: str) -> None:
        try:
            self._request_json("POST", f"/api/v1/runs/{quote(run_id, safe='')}/cancel", {})
        except AdapterError:
            return

    def _request_json(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        raw = self._request_text(method, path, body)
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AdapterError("theHarvester returned invalid JSON") from exc
        if not isinstance(decoded, dict):
            raise AdapterError("theHarvester returned an unexpected JSON shape")
        return decoded

    def _request_text(self, method: str, path: str, body: dict[str, Any] | None = None) -> str:
        if not path.startswith("/api/v1/") or "://" in path or ".." in path:
            raise ValueError("invalid theHarvester API path")
        data = json.dumps(body, separators=(",", ":")).encode("utf-8") if body is not None else None
        request = Request(
            self._base_url + path,
            data=data,
            method=method,
            headers={
                "Accept": "application/json, application/x-ndjson",
                "Content-Type": "application/json",
                "X-API-Key": self._api_key,
                "User-Agent": "Cognitive-Industry-Adapter/1.0",
            },
        )
        try:
            response = self._opener.open(request, timeout=self._timeout)
            with response:
                status = int(response.status)
                payload = response.read(self._max_response_bytes + 1)
        except HTTPError as exc:
            raise AdapterError(f"theHarvester HTTP request failed with status {exc.code}") from None
        except (URLError, TimeoutError, OSError) as exc:
            raise AdapterError(f"theHarvester connection failed: {type(exc).__name__}") from None
        if status < 200 or status >= 300:
            raise AdapterError(f"theHarvester HTTP request failed with status {status}")
        if len(payload) > self._max_response_bytes:
            raise AdapterError("theHarvester response exceeded the configured size limit")
        try:
            return payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise AdapterError("theHarvester response was not UTF-8") from exc


def _parse_export(ndjson: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    summary: dict[str, Any] = {}
    records: list[dict[str, Any]] = []
    for line in ndjson.splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise AdapterError("theHarvester JSONL export contains an invalid line") from exc
        if not isinstance(value, dict):
            continue
        kind = str(value.get("record_type") or value.get("type") or "").lower()
        if kind in {"summary", "run_summary"} or "evidence_status" in value:
            summary = value
        else:
            records.append(value)
    return summary, records


def _source_outcomes(summary: dict[str, Any], terminal: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = summary.get("source_executions") or terminal.get("source_executions") or []
    if not isinstance(candidates, list):
        return []
    result = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        result.append({
            "source": str(item.get("source") or item.get("name") or "")[:120],
            "status": str(item.get("status") or "unknown")[:40],
            "reported_count": _nonnegative_int(item.get("reported_count") or item.get("result_count")),
            "stop_reason": str(item.get("stop_reason") or "")[:300],
        })
    return result


def _nonnegative_int(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return min(max(parsed, 0), MAX_RESULTS)


def normalize_findings(
    findings: list[dict[str, Any]],
    scope: AuthorizationScope,
    *,
    target: str,
) -> tuple[list[HarvestedRecord], dict[str, int]]:
    root = scope.assert_domain(target)
    output: list[HarvestedRecord] = []
    filtered: dict[str, int] = {}
    seen: set[tuple[str, str]] = set()
    for item in findings:
        kind = str(item.get("type") or item.get("kind") or "unknown").strip().lower()
        value = str(item.get("value") or "").strip()
        if not value:
            filtered[kind] = filtered.get(kind, 0) + 1
            continue
        if kind in {"hostname", "subdomain", "domain"}:
            try:
                host = normalize_domain(value)
            except ValueError:
                filtered[kind] = filtered.get(kind, 0) + 1
                continue
            if not scope.contains_domain(host) or not (host == root or host.endswith("." + root)):
                filtered[kind] = filtered.get(kind, 0) + 1
                continue
            canonical_kind, scope_class, expandable = "hostname", "authorized-domain", True
            canonical_value = host
        elif kind == "ip":
            try:
                canonical_value = str(ipaddress.ip_address(value))
            except ValueError:
                filtered[kind] = filtered.get(kind, 0) + 1
                continue
            canonical_kind, scope_class, expandable = "ip", "external-relationship", False
        elif kind == "asn":
            normalized = value.upper().removeprefix("AS")
            if not normalized.isdigit() or int(normalized) > 4_294_967_295:
                filtered[kind] = filtered.get(kind, 0) + 1
                continue
            canonical_value = f"AS{int(normalized)}"
            canonical_kind, scope_class, expandable = "asn", "external-relationship", False
        else:
            filtered[kind] = filtered.get(kind, 0) + 1
            continue
        key = (canonical_kind, canonical_value)
        if key in seen:
            continue
        seen.add(key)
        sources = item.get("sources") or item.get("actions") or []
        source_values = sources if isinstance(sources, (list, tuple, set)) else [sources]
        source_ids = tuple(sorted({str(source)[:120] for source in source_values if str(source).strip()}))
        output.append(HarvestedRecord(canonical_kind, canonical_value, source_ids, scope_class, expandable))
    output.sort(key=lambda item: (item.kind, item.value))
    return output, filtered
