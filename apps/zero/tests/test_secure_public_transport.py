from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

from net.secure_fetch import FetchResult
from zero.harvesters.transport import SecurePublicTransport


class _Fetcher:
    def __init__(self, calls: list[tuple[str, str]]) -> None:
        self.calls = calls

    async def fetch(self, url: str, *, method: str = "GET", headers: dict[str, str] | None = None) -> FetchResult:
        self.calls.append((url, method))
        if url.endswith("/robots.txt"):
            return FetchResult(url=url, status=404, body=b"", headers={}, pinned_ip="203.0.113.10")
        body = b"" if method == "HEAD" else b"<html><body>public</body></html>"
        return FetchResult(
            url=url,
            status=200,
            body=body,
            headers={"content-type": "text/html"},
            pinned_ip="203.0.113.10",
            content_type="text/html",
        )

    async def aclose(self) -> None:
        return None


def _factory(calls: list[tuple[str, str]]):
    def make(**_kwargs: Any) -> _Fetcher:
        return _Fetcher(calls)
    return make


def test_transport_caps_physical_requests_including_robots() -> None:
    calls: list[tuple[str, str]] = []
    transport = SecurePublicTransport(
        max_requests=1,
        minimum_host_interval_s=0,
        fetcher_factory=_factory(calls),
    )
    assert transport.fetch("https://example.org/") == ""
    assert transport.requests_used == 1
    assert calls == [("https://example.org/robots.txt", "GET")]
    assert any("budget exhausted" in item["detail"] for item in transport.failures)


def test_exists_uses_head_and_does_not_persist_a_body_capture() -> None:
    calls: list[tuple[str, str]] = []
    transport = SecurePublicTransport(
        max_requests=2,
        minimum_host_interval_s=0,
        fetcher_factory=_factory(calls),
    )
    assert transport.exists("https://example.org/public")
    assert calls == [
        ("https://example.org/robots.txt", "GET"),
        ("https://example.org/public", "HEAD"),
    ]
    assert transport.captures == ()


def test_concurrent_same_url_fetches_are_coalesced() -> None:
    calls: list[tuple[str, str]] = []
    transport = SecurePublicTransport(
        max_requests=4,
        max_concurrency=2,
        minimum_host_interval_s=0,
        fetcher_factory=_factory(calls),
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _i: transport.fetch("https://example.org/page"), range(2)))
    assert results == ["<html><body>public</body></html>"] * 2
    assert calls.count(("https://example.org/robots.txt", "GET")) == 1
    assert calls.count(("https://example.org/page", "GET")) == 1
    assert len(transport.captures) == 1
