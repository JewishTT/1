"""Live-transport contract tests without making real network calls."""

from __future__ import annotations

from dataclasses import dataclass

from zero.harvesters.transport import SecurePublicTransport


@dataclass
class _Response:
    url: str
    status: int
    body: bytes
    content_type: str = "text/html"
    pinned_ip: str = "93.184.216.34"
    redirects: tuple[str, ...] = ()


class _FakeFetcher:
    def __init__(self, *, robots: bytes = b"User-agent: *\nAllow: /\n", page: bytes = b"<html><title>Public</title></html>"):
        self.robots = robots
        self.page = page
        self.calls: list[str] = []

    async def fetch(self, url: str, *, headers=None):
        self.calls.append(url)
        if url.endswith("/robots.txt"):
            return _Response(url=url, status=200, body=self.robots, content_type="text/plain")
        return _Response(url=url, status=200, body=self.page)

    async def aclose(self) -> None:
        return None


def test_secure_public_transport_captures_raw_bytes_after_robots_allow() -> None:
    instances: list[_FakeFetcher] = []

    def factory(**_kwargs):
        item = _FakeFetcher()
        instances.append(item)
        return item

    transport = SecurePublicTransport(
        fetcher_factory=factory,
        minimum_host_interval_s=0,
        max_response_bytes=4096,
    )
    transport.set_source_metadata(
        "https://example.org/about#fragment",
        parent_observation_id="OBS-parent",
        discovery_source_id="searxng_public_search",
        action_ref="ACT-discovery",
    )
    text = transport.fetch("https://EXAMPLE.org/about#fragment")

    assert "Public" in text
    assert len(transport.captures) == 1
    capture = transport.captures[0]
    assert capture.body == b"<html><title>Public</title></html>"
    assert capture.status == 200
    assert capture.parent_observation_id == "OBS-parent"
    assert capture.discovery_source_id == "searxng_public_search"
    assert capture.action_ref == "ACT-discovery"
    assert len(instances) == 1
    assert instances[0].calls == [
        "https://example.org/robots.txt",
        "https://example.org/about",
    ]


def test_secure_public_transport_refuses_disallowed_robots_path() -> None:
    instances: list[_FakeFetcher] = []

    def factory(**_kwargs):
        item = _FakeFetcher(robots=b"User-agent: *\nDisallow: /\n")
        instances.append(item)
        return item

    transport = SecurePublicTransport(fetcher_factory=factory, minimum_host_interval_s=0)
    assert transport.fetch("https://example.org/private") == ""
    assert transport.captures == ()
    assert transport.failures
    assert transport.failures[0]["code"] == "SecurityBlocked"
    assert instances[0].calls == ["https://example.org/robots.txt"]


def test_secure_public_transport_rejects_http_before_network() -> None:
    calls: list[bool] = []

    def factory(**_kwargs):
        calls.append(True)
        return _FakeFetcher()

    transport = SecurePublicTransport(fetcher_factory=factory, minimum_host_interval_s=0)
    assert transport.fetch("http://example.org/") == ""
    assert calls == []
    assert transport.captures == ()
    assert transport.failures[0]["code"] == "SecurityBlocked"
