"""Execute a source definition and emit one observation per page.

The load-bearing property here is that **every page becomes its own observation**. The
donor streamed pages 1..N-1 to subscribers and then discarded them, keeping only the last
as "the observation" — so a ten-page source reported one page of what was actually
acquired. Here the page count is the observation count, and the count is reported.

Three further rules, each of which the donor's transport got wrong:

Raw bytes are retained
    The donor called ``resp.text()`` and destroyed the bytes before anything could hash
    them. An observation we cannot re-parse after a parser upgrade is not durable, so the
    body is kept as bytes and the content digest is computed over those bytes.

A cache hit does not invent a response
    The donor set ``meta["status"] = 200`` on a cache hit, fabricating a status nobody
    observed, and left ``content_type`` unset, so the shape of the record depended on
    whether the network had been touched. Here a cached page records ``from_cache`` and its
    real capture time, and the status is whatever was actually recorded.

The query is part of the identity
    The donor's cache key hashed method, URL and body but not ``params``, and 72 of the
    definitions carry their query in ``params`` — so a cached response for one query was
    served for another. The loader folds params into the URL; this module additionally
    digests the *resolved* URL into every event's identity, so two different queries can
    never collide.
"""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from typing import Any

from sources.catalogue import Pagination, SourceDefinition

DEFAULT_TIMEOUT_S = 12.0
DEFAULT_USER_AGENT = "cognitive-substrate/021 (+OSINT acquisition)"

#: Reserved ranges, refused before a connection is made. A fact about the network, not a
#: policy opinion: these addresses are not public and a source must never reach them.
BLOCKED_V4 = (
    "0.0.0.0/8",
    "10.0.0.0/8",
    "100.64.0.0/10",
    "127.0.0.0/8",
    "169.254.0.0/16",
    "172.16.0.0/12",
    "192.0.0.0/24",
    "192.168.0.0/16",
    "198.18.0.0/15",
    "224.0.0.0/4",
    "240.0.0.0/4",
    "255.255.255.255/32",
)


class AcquisitionError(RuntimeError):
    """A source could not be executed, and says which guard stopped it."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class CapturePage:
    """One retrieved page. ``body`` is the raw bytes, not a decoded guess."""

    source_id: str
    source_name: str
    query: str
    page: int
    url: str
    status: int
    content_type: str
    body: bytes
    content_digest: str
    retrieved_at: float
    from_cache: bool = False
    elapsed_s: float = 0.0
    truncated: bool = False
    detail: Mapping[str, Any] = field(default_factory=dict)

    @property
    def redirected_from(self) -> tuple[str, ...]:
        """The URLs this page was reached through, empty when there were none."""
        return tuple(self.detail.get("redirects") or ())

    @property
    def byte_length(self) -> int:
        return len(self.body)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_name": self.source_name,
            "query": self.query,
            "page": self.page,
            "url": self.url,
            "status": self.status,
            "content_type": self.content_type,
            "content_digest": self.content_digest,
            "retrieved_at": self.retrieved_at,
            "from_cache": self.from_cache,
            "elapsed_s": round(self.elapsed_s, 6),
            "byte_length": self.byte_length,
            "truncated": self.truncated,
            "redirected_from": list(self.redirected_from),
        }


def _digest(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


def resolve_query(tool: Mapping[str, Any], query: str) -> str:
    """Substitute a query as URL-encoded data, never as raw URL syntax.

    Source definitions commonly carry placeholders in query parameters. Interpolating
    a user-supplied subject literally lets ampersands, fragments or reserved characters
    modify the request's target instead of remaining the query value.
    """
    from urllib.parse import quote

    url = str(tool.get("url") or "")
    if not url:
        raise AcquisitionError("source_has_no_url", "definition declares no url")
    encoded = quote(str(query), safe="")
    return url.replace("{query}", encoded).replace("%7Bquery%7D", encoded).replace(
        "%7bquery%7d", encoded
    )


def _source_api_key(source: SourceDefinition) -> str | None:
    """Resolve a source's declared credential without exposing its value."""
    if not source.requires_key:
        return None
    if not source.key_env:
        # Some keyed catalogue entries use the explicitly-declared two-part
        # HTTP Basic credential pair instead of an API-key environment variable.
        if source.tool.get("basic_auth_env"):
            return None
        raise AcquisitionError(
            "keyed_source_without_key_env",
            f"{source.name} needs a key but declares no key_env",
        )
    value = os.environ.get(source.key_env, "").strip()
    if not value:
        raise AcquisitionError(
            "missing_credential",
            f"{source.name} needs credential {source.key_env}",
        )
    return value


def _replace_api_key(value: str, api_key: str | None, *, url_value: bool = False) -> str:
    """Resolve a declared API-key placeholder in a header or URL."""
    if not api_key:
        return value
    from urllib.parse import quote

    replacement = quote(api_key, safe="") if url_value else api_key
    return (
        value.replace("{api_key}", replacement)
        .replace("%7Bapi_key%7D", replacement)
        .replace("%7bapi_key%7d", replacement)
    )


def _redact_url(url: str, *, credentials: tuple[str | None, ...] = ()) -> str:
    """Remove credentials from URLs before they enter captures or provenance."""
    from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

    credential_values = {
        encoded
        for credential in credentials
        if credential
        for encoded in (credential, quote(credential, safe=""), quote(credential, safe="+"))
    }
    parts = urlsplit(url)
    sensitive_names = {
        "apikey", "api_key", "key", "token", "access_token", "auth",
        "authorization", "signature", "secret", "client_secret", "password",
    }
    sensitive_names = {name.replace("_", "") for name in sensitive_names}
    query = []
    for name, value in parse_qsl(parts.query, keep_blank_values=True):
        normalized = name.lower().replace("-", "").replace("_", "")
        contains_credential = any(item and item in value for item in credential_values)
        query.append(
            (name, "[REDACTED]" if normalized in sensitive_names or contains_credential else value)
        )
    path = parts.path
    for credential in credential_values:
        path = path.replace(credential, "[REDACTED]")
    return urlunsplit((parts.scheme, parts.netloc, path, urlencode(query), parts.fragment))


def request_headers(
    source: SourceDefinition, *, api_key: str | None = None
) -> dict[str, str]:
    """Build source headers and resolve explicitly named environment credentials."""
    headers = {
        str(key): str(value)
        for key, value in (source.tool.get("headers") or {}).items()
    }
    if api_key is None:
        api_key = _source_api_key(source)

    import re

    def replace_header(match: re.Match[str]) -> str:
        placeholder = match.group(1)
        if placeholder.lower() == "api_key":
            if not api_key:
                raise AcquisitionError(
                    "missing_credential",
                    f"{source.name} uses an API-key placeholder without a configured key",
                )
            return api_key
        env_name = placeholder.upper()
        value = os.environ.get(env_name, "").strip()
        if not value:
            raise AcquisitionError(
                "missing_credential",
                f"{source.name} needs credential {env_name}",
            )
        return value

    for name, value in tuple(headers.items()):
        headers[name] = re.sub(r"\{([A-Za-z][A-Za-z0-9_]*)\}", replace_header, value)

    if source.source_id == "crossref_doi" or source.name == "crossref_doi":
        # Crossref's polite pool requires a reachable operator contact. The YAML
        # sample address is historical documentation and must not be sent upstream.
        contact = os.environ.get("COGNITIVE_CROSSREF_MAILTO", "").strip()
        if not contact or "@" not in contact or contact.endswith(".local"):
            raise AcquisitionError(
                "missing_contact_email",
                "Crossref requests require a real COGNITIVE_CROSSREF_MAILTO contact email",
            )
        headers["User-Agent"] = f"cognitive-substrate/034 (mailto:{contact})"
    return headers


def _refuse_blocked_host(url: str) -> None:
    """Refuse a literal host that lands in a reserved range, before connecting."""
    import ipaddress
    from urllib.parse import urlsplit

    host = urlsplit(url).hostname or ""
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return  # a name; resolution happens at connect time and is a separate check
    for cidr in BLOCKED_V4:
        if addr in ipaddress.ip_network(cidr):
            raise AcquisitionError(
                "host_in_reserved_range", f"{host} is inside {cidr} and is not public"
            )


def page_count(pagination: Pagination) -> int:
    """How many pages this definition may fetch. Always a real ceiling."""
    if not pagination.enabled:
        return 1
    return max(1, pagination.max_pages)


def _basic_auth(source: Any) -> tuple[str, str] | None:
    """HTTP Basic credentials for a source that declares them.

    Some upstreams authenticate with a *pair* of secrets (WiGLE: an API name plus an
    API token), which a single ``key_env`` string cannot express -- the YAML can only
    name one variable, and an earlier attempt concatenated the names into a single
    nonexistent identifier. ``basic_auth_env`` names the pair explicitly instead.

    A half-configured pair is a configuration error, not a request to send one blank
    credential, so it is reported rather than guessed at.
    """
    pair = source.tool.get("basic_auth_env")
    if not pair:
        return None
    if isinstance(pair, str):
        pair = [pair]
    if len(pair) != 2:
        raise AcquisitionError(
            "bad_basic_auth_env",
            f"{source.name} declares {len(pair)} basic_auth_env names, expected 2",
        )
    user, password = (os.environ.get(str(name), "") for name in pair)
    missing = [str(n) for n, v in zip(pair, (user, password), strict=True) if not v]
    if missing:
        raise AcquisitionError(
            "missing_credential",
            f"{source.name} needs {', '.join(missing)} for HTTP Basic auth",
        )
    return user, password


class HttpSourceExecutor:
    """Fetch a source definition, page by page, yielding one capture per page."""

    def __init__(
        self,
        *,
        timeout: float = DEFAULT_TIMEOUT_S,
        max_bytes: int = 2_000_000,
        user_agent: str = DEFAULT_USER_AGENT,
        client: Any | None = None,
        secure_fetcher: Any | None = None,
    ) -> None:
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.user_agent = user_agent
        self._client = client
        self._secure_fetcher = secure_fetcher
        if self._client is None and self._secure_fetcher is None:
            from net.secure_fetch import SecureFetcher
            from security import ResourceLimits

            self._secure_fetcher = SecureFetcher(
                limits=ResourceLimits(
                    max_response_bytes=max_bytes,
                    max_timeout_ms=max(1, int(timeout * 1000)),
                ),
                user_agent=user_agent,
            )

    async def _session(self) -> Any:
        if self._secure_fetcher is not None:
            raise RuntimeError("secure production fetch does not expose a raw HTTP client")
        if self._client is not None:
            return self._client
        raise AcquisitionError(
            "secure_fetcher_missing",
            "production HTTP acquisition requires the shared SecureFetcher boundary",
        )

    async def aclose(self) -> None:
        if self._client is not None and hasattr(self._client, "aclose"):
            await self._client.aclose()
        if self._secure_fetcher is not None:
            await self._secure_fetcher.aclose()
        self._client = None
        self._secure_fetcher = None

    def _page_url(self, base_url: str, pagination: Pagination, page: int) -> str:
        """Advance the URL to ``page``. Page 1 is the definition's own URL, unmodified."""
        if not pagination.enabled or page <= 1:
            return base_url
        from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

        parts = urlsplit(base_url)
        query = parse_qsl(parts.query, keep_blank_values=True)
        if pagination.strategy == "page":
            if pagination.page_size:
                query = [(k, v) for k, v in query if k != pagination.param]
                query.append((pagination.param, str(pagination.page_size)))
            key = pagination.param if pagination.param != "per_page" else "page"
            query = [(k, v) for k, v in query if k != key]
            query.append((key, str(page)))
        elif pagination.strategy == "offset":
            query = [(k, v) for k, v in query if k != pagination.param]
            step = pagination.page_size or 25
            query.append((pagination.param, str(step * (page - 1))))
        return urlunsplit(
            (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
        )

    async def capture(
        self, source: SourceDefinition, query: str
    ) -> AsyncIterator[CapturePage]:
        """Yield one capture per page, in order, up to the definition's ceiling."""
        if source.kind != "http":
            raise AcquisitionError(
                "not_an_http_source", f"{source.name} is a {source.kind} source"
            )
        if (
            source.requires_key
            and not source.key_env
            and not source.tool.get("basic_auth_env")
        ):
            raise AcquisitionError(
                "keyed_source_without_key_env", f"{source.name} needs a key it cannot name"
            )
        api_key = _source_api_key(source)
        base_url = _replace_api_key(resolve_query(source.tool, query), api_key, url_value=True)
        _refuse_blocked_host(base_url)
        session = None if self._secure_fetcher is not None else await self._session()
        method = str(source.tool.get("method") or "GET").upper()
        headers = request_headers(source, api_key=api_key)
        # Only forwarded when a source actually declares basic auth. Passing auth=None
        # to every request would be harmless against httpx but changes the call
        # signature every transport double has to match.
        auth = _basic_auth(source)

        total = page_count(source.pagination)
        for page in range(1, total + 1):
            url = self._page_url(base_url, source.pagination, page)
            _refuse_blocked_host(url)
            started = time.monotonic()
            retrieved_at = time.time()
            secure_result = None
            try:
                if self._secure_fetcher is not None:
                    from security import SecurityBlocked

                    secure_headers = dict(headers)
                    if auth is not None:
                        import base64

                        token = base64.b64encode(f"{auth[0]}:{auth[1]}".encode("utf-8")).decode("ascii")
                        secure_headers["Authorization"] = f"Basic {token}"
                    try:
                        secure_result = await self._secure_fetcher.fetch(
                            url,
                            headers=secure_headers,
                            method=method,
                            trusted_private_hosts=tuple(source.tool.get("trusted_private_hosts") or ()),
                        )
                    except SecurityBlocked as blocked:
                        raise AcquisitionError(
                            "security_blocked",
                            f"{source.name} page {page}: {type(blocked).__name__}: {blocked}",
                        ) from blocked
                    response = None
                    body = secure_result.body
                    response_status = secure_result.status
                    response_headers = secure_result.headers
                    response_url = secure_result.url
                    response_redirects = secure_result.redirects
                    pinned_ip = secure_result.pinned_ip
                else:
                    if auth is None:
                        response = await session.request(method, url, headers=headers)
                    else:
                        response = await session.request(method, url, headers=headers, auth=auth)
                    body = response.content or b""
                    response_status = int(response.status_code)
                    response_headers = dict(response.headers)
                    response_url = str(getattr(response, "url", url) or url)
                    response_redirects = tuple(
                        str(h.url) for h in (getattr(response, "history", None) or ())
                    )
                    pinned_ip = ""
            except AcquisitionError:
                raise
            except Exception as exc:  # transport failure is a value, not a crash
                # HTTP client exceptions can include the request URL; redact credentials
                # before this detail reaches a failure journal or an event payload.
                error_detail = str(exc)
                from urllib.parse import quote

                for credential in (api_key, *(auth or ())):
                    if credential:
                        error_detail = error_detail.replace(credential, "[REDACTED]")
                        encoded = quote(credential, safe="")
                        if encoded:
                            error_detail = error_detail.replace(encoded, "[REDACTED]")
                raise AcquisitionError(
                    "transport_failed",
                    f"{source.name} page {page}: {type(exc).__name__}: {error_detail}",
                ) from exc
            truncated = len(body) > self.max_bytes
            if truncated:
                body = body[: self.max_bytes]
            # The request uses the real credential; capture metadata never does.
            safe_url = _redact_url(url, credentials=(api_key,))
            safe_final_url = _redact_url(response_url, credentials=(api_key,))
            yield CapturePage(
                source_id=source.source_id,
                source_name=source.name,
                query=query,
                page=page,
                url=safe_url,
                status=response_status,
                content_type=str(response_headers.get("content-type", response_headers.get("Content-Type", ""))),
                body=body,
                content_digest=_digest(body),
                retrieved_at=retrieved_at,
                from_cache=False,
                elapsed_s=time.monotonic() - started,
                truncated=truncated,
                detail={
                    "final": page == total,
                    # The chain is recorded so following a redirect stays visible. Several
                    # sources answer 301/302 by design (rdap.org -> the registry, arxiv
                    # http -> https), and a reader of the provenance should see that the
                    # bytes came from somewhere other than the URL they asked for.
                    "redirects": [
                        _redact_url(str(h), credentials=(api_key,))
                        for h in (response_redirects or ())
                    ],
                    "requested_url": safe_url,
                    "final_url": safe_final_url,
                    "dns_checked_ip": pinned_ip or None,
                    "fetch_security": "SECURE_FETCHER" if secure_result is not None else "INJECTED_TEST_TRANSPORT",
                },
            )
            # A short page is a short page: the source told us there is no next one.
            if truncated or (source.pagination.page_size and len(body) == 0):
                return
            await asyncio.sleep(0)
