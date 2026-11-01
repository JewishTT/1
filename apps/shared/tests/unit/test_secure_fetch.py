"""Feature 024 T023 -- Security-First fetch boundary.

Hermetic: DNS and the HTTP transport are injected, so every assertion here runs
with no network. That is deliberate -- a security control whose tests need the
internet will silently stop running in CI.
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from net.secure_fetch import (  # noqa: E402
    RedirectBlocked,
    ResponseTooLarge,
    SecureFetcher,
    SecurityBlocked,
)


class FakeTransport:
    """Records requests and replays a scripted response per URL."""

    def __init__(self, script: dict[str, httpx.Response]) -> None:
        self.script = script
        self.seen: list[str] = []
        self.closed: list[str] = []
        self.pinned: list[tuple[str, str]] = []

    async def request_pinned(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        pinned_ip: str,
        timeout: float,
    ) -> httpx.Response:
        self.seen.append(url)
        self.pinned.append((url, pinned_ip))
        if url not in self.script:
            raise AssertionError(f"unexpected fetch: {url}")
        response = self.script[url]
        response.request = httpx.Request(method, url, headers=headers)
        return response

    async def aclose(self) -> None:
        return None


def resp(status: int, body: bytes = b"", headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(
        status_code=status, content=body, headers=headers or {}, request=httpx.Request("GET", "http://x")
    )


PUBLIC = {"example.com": ["93.184.216.34"]}


async def resolver_for(mapping: dict[str, list[str]]):
    async def _resolve(host: str, port: int) -> list[str]:
        return mapping.get(host, [])

    return _resolve


def fetcher(script: dict[str, httpx.Response], dns: dict[str, list[str]], **kw) -> SecureFetcher:
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        res = loop.run_until_complete(resolver_for(dns))
    finally:
        loop.close()
    return SecureFetcher(transport=FakeTransport(script), resolver=res, **kw)


@pytest.mark.asyncio
async def test_happy_path_pins_public_ip():
    t = FakeTransport({"http://example.com/": resp(200, b"ok")})
    f = SecureFetcher(transport=t, resolver=await resolver_for(PUBLIC))
    r = await f.fetch("http://example.com/")
    assert r.status == 200
    assert r.body == b"ok"
    assert r.pinned_ip == "93.184.216.34"
    assert r.redirects == ()
    assert t.pinned == [("http://example.com/", "93.184.216.34")]


@pytest.mark.asyncio
async def test_exact_trusted_private_service_hostname_is_allowed():
    t = FakeTransport({"http://searxng:8080/search": resp(200, b"json")})
    f = SecureFetcher(
        transport=t,
        resolver=await resolver_for({"searxng": ["172.20.0.4"]}),
    )
    result = await f.fetch("http://searxng:8080/search", trusted_private_hosts=("searxng",))
    assert result.status == 200
    assert result.pinned_ip == "172.20.0.4"


@pytest.mark.asyncio
async def test_trusted_service_allowlist_does_not_cover_other_private_redirect_hosts():
    t = FakeTransport({
        "http://searxng:8080/search": resp(302, headers={"location": "http://metadata.internal/latest"}),
        "http://metadata.internal/latest": resp(200, b"secret"),
    })
    f = SecureFetcher(
        transport=t,
        resolver=await resolver_for({
            "searxng": ["172.20.0.4"],
            "metadata.internal": ["169.254.169.254"],
        }),
    )
    with pytest.raises(SecurityBlocked):
        await f.fetch("http://searxng:8080/search", trusted_private_hosts=("searxng",))
    assert "http://metadata.internal/latest" not in t.seen


@pytest.mark.asyncio
async def test_private_destination_refused():
    """The classic SSRF: a public name resolving into the metadata range."""
    t = FakeTransport({"http://evil.test/": resp(200, b"secret")})
    f = SecureFetcher(transport=t, resolver=await resolver_for({"evil.test": ["169.254.169.254"]}))
    with pytest.raises(SecurityBlocked, match="non-public"):
        await f.fetch("http://evil.test/")
    assert t.seen == []  # refused BEFORE any request was made


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "ip", ["127.0.0.1", "10.1.2.3", "192.168.1.1", "172.16.5.5", "100.64.0.1", "::1"]
)
async def test_every_blocked_range_refused(ip):
    t = FakeTransport({})
    f = SecureFetcher(transport=t, resolver=await resolver_for({"h.test": [ip]}))
    with pytest.raises(SecurityBlocked):
        await f.fetch("http://h.test/")
    assert t.seen == []


@pytest.mark.asyncio
async def test_redirect_is_revalidated_not_followed_blindly():
    """A 302 into link-local must be refused even though the first hop was public."""
    script = {
        "http://example.com/": resp(302, headers={"location": "http://169.254.169.254/latest/meta-data/"}),
        "http://169.254.169.254/latest/meta-data/": resp(200, b"credentials"),
    }
    t = FakeTransport(script)
    f = SecureFetcher(transport=t, resolver=await resolver_for({"example.com": ["93.184.216.34"], "169.254.169.254": ["169.254.169.254"]}))
    with pytest.raises(SecurityBlocked):
        await f.fetch("http://example.com/")
    assert "http://169.254.169.254/latest/meta-data/" not in t.seen


@pytest.mark.asyncio
async def test_redirect_to_allowed_host_is_followed_and_recorded():
    script = {
        "http://example.com/": resp(301, headers={"location": "/final"}),
        "http://example.com/final": resp(200, b"landed"),
    }
    t = FakeTransport(script)
    f = SecureFetcher(transport=t, resolver=await resolver_for(PUBLIC))
    r = await f.fetch("http://example.com/")
    assert r.url == "http://example.com/final"
    assert r.redirects == ("http://example.com/",)


@pytest.mark.asyncio
async def test_redirect_budget_exhausted():
    chain = {
        "http://example.com/": resp(302, headers={"location": "/a"}),
        "http://example.com/a": resp(302, headers={"location": "/b"}),
        "http://example.com/b": resp(302, headers={"location": "/c"}),
    }
    t = FakeTransport(chain)
    f = SecureFetcher(transport=t, resolver=await resolver_for(PUBLIC), max_redirects=2)
    with pytest.raises(RedirectBlocked, match="exceeds 2 hops"):
        await f.fetch("http://example.com/")
    assert t.seen == [
        "http://example.com/",
        "http://example.com/a",
        "http://example.com/b",
    ]


@pytest.mark.asyncio
async def test_scheme_downgrade_refused():
    script = {"https://example.com/": resp(302, headers={"location": "http://example.com/"})}
    t = FakeTransport(script)
    f = SecureFetcher(transport=t, resolver=await resolver_for(PUBLIC))
    with pytest.raises(RedirectBlocked, match="downgrade"):
        await f.fetch("https://example.com/")


@pytest.mark.asyncio
async def test_redirect_without_location_refused():
    t = FakeTransport({"http://example.com/": resp(302)})
    f = SecureFetcher(transport=t, resolver=await resolver_for(PUBLIC))
    with pytest.raises(RedirectBlocked, match="without Location"):
        await f.fetch("http://example.com/")


@pytest.mark.asyncio
async def test_response_size_cap_enforced_before_read():
    t = FakeTransport({"http://example.com/": resp(200, b"x", {"content-length": "99999999"})})
    f = SecureFetcher(transport=t, resolver=await resolver_for(PUBLIC))
    with pytest.raises(SecurityBlocked):
        await f.fetch("http://example.com/")


@pytest.mark.asyncio
async def test_response_size_cap_enforced_while_streaming():
    """Chunked response: no Content-Length to short-circuit on, so the cap has to
    fire from the streaming loop itself rather than from the header check."""
    from security import ResourceLimits

    def chunked() -> httpx.Response:
        class _Stream(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b"y" * 900
                yield b"y" * 900

        return httpx.Response(
            status_code=200,
            stream=_Stream(),
            headers={"transfer-encoding": "chunked"},
            request=httpx.Request("GET", "http://example.com/"),
        )

    t = FakeTransport({"http://example.com/": chunked()})
    f = SecureFetcher(
        transport=t,
        resolver=await resolver_for(PUBLIC),
        limits=ResourceLimits(max_response_bytes=1000),
    )
    with pytest.raises(ResponseTooLarge):
        await f.fetch("http://example.com/")


@pytest.mark.asyncio
async def test_dns_rebinding_detected_on_second_hop():
    """Same host, different answer on the second resolution -> rebinding."""
    answers = iter([["93.184.216.34"], ["127.0.0.1"]])

    async def rebinding_resolver(host: str, port: int) -> list[str]:
        return next(answers, ["93.184.216.34"])

    script = {
        "http://example.com/": resp(302, headers={"location": "/second"}),
        "http://example.com/second": resp(200, b"should not be reached"),
    }
    t = FakeTransport(script)
    f = SecureFetcher(transport=t, resolver=rebinding_resolver)
    with pytest.raises(SecurityBlocked):
        await f.fetch("http://example.com/")
    assert "http://example.com/second" not in t.seen


@pytest.mark.asyncio
async def test_off_policy_port_refused():
    t = FakeTransport({})
    f = SecureFetcher(transport=t, resolver=await resolver_for({"h.test": ["93.184.216.34"]}))
    with pytest.raises(SecurityBlocked, match="port"):
        await f.fetch("http://h.test:8081/")


@pytest.mark.asyncio
async def test_unresolvable_host_refused():
    t = FakeTransport({})
    f = SecureFetcher(transport=t, resolver=await resolver_for({}))
    with pytest.raises(SecurityBlocked, match="no address"):
        await f.fetch("http://nowhere.test/")


@pytest.mark.asyncio
async def test_egress_allowlist_cannot_punch_through_private_ranges():
    """`ssrf_guard` applies the allowlist first and then checks public-ness
    unconditionally, so an allowlist may only *narrow* the permitted public set --
    it cannot be used to reach 10/8. That is fail-closed, and it is asserted here so
    that a future relaxation shows up as a visible break rather than a silent hole."""
    from security import EgressPolicy

    t = FakeTransport({})
    f = SecureFetcher(
        transport=t,
        resolver=await resolver_for({"partner.test": ["10.20.30.40"]}),
        egress=EgressPolicy(allow_cidrs=["10.0.0.0/8"]),
    )
    with pytest.raises(SecurityBlocked, match="non-public"):
        await f.fetch("http://partner.test/")
    assert t.seen == []


@pytest.mark.asyncio
async def test_egress_allowlist_narrows_permitted_public_set():
    from security import EgressPolicy

    t = FakeTransport({})
    f = SecureFetcher(
        transport=t,
        resolver=await resolver_for({"partner.test": ["93.184.216.34"]}),
        egress=EgressPolicy(allow_cidrs=["10.0.0.0/8"]),
    )
    with pytest.raises(SecurityBlocked, match="not in egress allowlist"):
        await f.fetch("http://partner.test/")


@pytest.mark.asyncio
async def test_default_transport_is_ip_pinned_and_has_no_client_redirect_mode():
    """Default production transport connects to the validated IP, not a second DNS lookup."""
    from net.secure_fetch import PinnedHttpcoreTransport

    own = SecureFetcher(resolver=await resolver_for(PUBLIC))
    assert isinstance(own._transport, PinnedHttpcoreTransport)
    await own.aclose()


@pytest.mark.asyncio
async def test_pinned_network_backend_connects_to_the_validated_ip_only():
    """The HTTP core sees the hostname; the socket backend receives the checked IP."""
    from net.secure_fetch import PinnedNetworkBackend

    class RecordingBackend:
        def __init__(self):
            self.calls = []

        async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
            self.calls.append((host, port, timeout, local_address, socket_options))
            return object()

        async def connect_unix_socket(self, path, timeout=None, socket_options=None):
            raise AssertionError("public fetch must never use unix sockets")

        async def sleep(self, seconds):
            return None

    recording = RecordingBackend()
    backend = PinnedNetworkBackend(
        hostname="Example.COM",
        pinned_ip="93.184.216.34",
        delegate=recording,
    )
    await backend.connect_tcp("example.com", 443, timeout=2.0)
    assert recording.calls[0][:2] == ("93.184.216.34", 443)


@pytest.mark.asyncio
async def test_pinned_network_backend_refuses_an_unexpected_origin_host():
    from net.secure_fetch import PinnedNetworkBackend

    backend = PinnedNetworkBackend(hostname="example.com", pinned_ip="93.184.216.34")
    with pytest.raises(SecurityBlocked, match="outside the validated origin"):
        await backend.connect_tcp("metadata.internal", 443)

