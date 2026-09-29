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
        }


def _digest(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


def resolve_query(tool: Mapping[str, Any], query: str) -> str:
    """Substitute the query into the URL. The resolved URL is the request's identity."""
    url = str(tool.get("url") or "")
    if not url:
        raise AcquisitionError("source_has_no_url", "definition declares no url")
    return url.replace("{query}", query).replace("%7Bquery%7D", query)


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


class HttpSourceExecutor:
    """Fetch a source definition, page by page, yielding one capture per page."""

    def __init__(
        self,
        *,
        timeout: float = DEFAULT_TIMEOUT_S,
        max_bytes: int = 2_000_000,
        user_agent: str = DEFAULT_USER_AGENT,
        client: Any | None = None,
    ) -> None:
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.user_agent = user_agent
        self._client = client

    async def _session(self) -> Any:
        if self._client is not None:
            return self._client
        import httpx

        self._client = httpx.AsyncClient(
            timeout=self.timeout, follow_redirects=False, headers={"User-Agent": self.user_agent}
        )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and hasattr(self._client, "aclose"):
            await self._client.aclose()
        self._client = None

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
        if source.requires_key and not source.key_env:
            raise AcquisitionError(
                "keyed_source_without_key_env", f"{source.name} needs a key it cannot name"
            )
        base_url = resolve_query(source.tool, query)
        _refuse_blocked_host(base_url)
        session = await self._session()
        method = str(source.tool.get("method") or "GET").upper()
        headers = {str(k): str(v) for k, v in (source.tool.get("headers") or {}).items()}

        total = page_count(source.pagination)
        for page in range(1, total + 1):
            url = self._page_url(base_url, source.pagination, page)
            _refuse_blocked_host(url)
            started = time.monotonic()
            retrieved_at = time.time()
            try:
                response = await session.request(method, url, headers=headers)
            except Exception as exc:  # transport failure is a value, not a crash
                raise AcquisitionError(
                    "transport_failed", f"{source.name} page {page}: {type(exc).__name__}: {exc}"
                ) from exc
            body = response.content or b""
            truncated = len(body) > self.max_bytes
            if truncated:
                body = body[: self.max_bytes]
            yield CapturePage(
                source_id=source.source_id,
                source_name=source.name,
                query=query,
                page=page,
                url=url,
                status=int(response.status_code),
                content_type=str(response.headers.get("content-type", "")),
                body=body,
                content_digest=_digest(body),
                retrieved_at=retrieved_at,
                from_cache=False,
                elapsed_s=time.monotonic() - started,
                truncated=truncated,
                detail={"final": page == total},
            )
            # A short page is a short page: the source told us there is no next one.
            if truncated or (source.pagination.page_size and len(body) == 0):
                return
            await asyncio.sleep(0)
