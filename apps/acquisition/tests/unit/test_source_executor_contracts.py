"""URL and upstream identity contracts for public metadata acquisition."""
from __future__ import annotations

import os
from pathlib import Path

import httpx
import pytest

from sources.catalogue import CATALOGUE_ROOT, load_source
from sources.executor import AcquisitionError, HttpSourceExecutor, request_headers, resolve_query


def test_query_is_encoded_as_data_not_url_syntax() -> None:
    url = resolve_query(
        {"url": "https://api.example.test/search?query={query}&rows=10"},
        'Alice & Bob "Ltd" #fragment + institute',
    )
    assert url == (
        "https://api.example.test/search?query="
        "Alice%20%26%20Bob%20%22Ltd%22%20%23fragment%20%2B%20institute&rows=10"
    )
    assert url.count("&") == 1
    assert "#fragment" not in url


def test_percent_encoded_placeholder_is_also_replaced_safely() -> None:
    url = resolve_query(
        {"url": "https://api.example.test/search?query=%7Bquery%7D"},
        "Čārlis Bērziņš",
    )
    assert url == "https://api.example.test/search?query=%C4%8C%C4%81rlis%20B%C4%93rzi%C5%86%C5%A1"


def _crossref_definition():
    path = CATALOGUE_ROOT / "08_knowledge" / "crossref_doi.yaml"
    return load_source(path)


def test_crossref_request_fails_closed_without_real_contact(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COGNITIVE_CROSSREF_MAILTO", raising=False)
    with pytest.raises(AcquisitionError, match="COGNITIVE_CROSSREF_MAILTO"):
        request_headers(_crossref_definition())


def test_crossref_user_agent_uses_configured_contact_not_yaml_sample(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COGNITIVE_CROSSREF_MAILTO", "operator@example.org")
    headers = request_headers(_crossref_definition())
    assert headers["User-Agent"] == "cognitive-substrate/034 (mailto:operator@example.org)"
    assert ".local" not in headers["User-Agent"]



def test_twitch_headers_resolve_declared_environment_placeholders(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Provider-specific header placeholders resolve from their documented env names."""
    monkeypatch.setenv("TWITCH_ACCESS_TOKEN", "test-access-token")
    monkeypatch.setenv("TWITCH_CLIENT_ID", "test-client-id")
    source = load_source(CATALOGUE_ROOT / "04_social" / "twitch_user.yaml")
    headers = request_headers(source)
    assert headers["Authorization"] == "Bearer test-access-token"
    assert headers["Client-ID"] == "test-client-id"


@pytest.mark.asyncio
async def test_keyed_url_parameter_is_injected_but_redacted_from_capture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A credential reaches the upstream request, never the persisted capture URL."""
    marker = "test-ethplorer-credential-do-not-persist"
    monkeypatch.setenv("ETHPLORER_API_KEY", marker)
    source = load_source(CATALOGUE_ROOT / "10_blockchain" / "ethplorer_address.yaml")
    observed: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed["url"] = str(request.url)
        return httpx.Response(
            200,
            json={"address": "0xabc", "ETH": {"balance": 1.0, "txCount": 2}},
            request=request,
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    executor = HttpSourceExecutor(client=client)
    captures = []
    try:
        async for capture in executor.capture(source, "0xabc"):
            captures.append(capture)
    finally:
        await executor.aclose()

    assert len(captures) == 1
    assert marker in observed["url"]
    assert captures[0].status == 200
    assert marker not in captures[0].url
    assert marker not in captures[0].detail["requested_url"]
    assert marker not in captures[0].detail["final_url"]
    assert "REDACTED" in captures[0].url


@pytest.mark.asyncio
async def test_missing_declared_api_key_fails_before_network_io(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ETHPLORER_API_KEY", raising=False)
    source = load_source(CATALOGUE_ROOT / "10_blockchain" / "ethplorer_address.yaml")

    def forbidden_handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("network must not be touched without the required key")

    client = httpx.AsyncClient(transport=httpx.MockTransport(forbidden_handler))
    executor = HttpSourceExecutor(client=client)
    try:
        with pytest.raises(AcquisitionError, match="ETHPLORER_API_KEY"):
            async for _capture in executor.capture(source, "0xabc"):
                pass
    finally:
        await executor.aclose()



@pytest.mark.asyncio
async def test_basic_auth_only_source_executes_with_both_declared_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The full executor path must accept a key pair without a single key_env."""
    monkeypatch.setenv("WIGLE_API_NAME", "operator-name")
    monkeypatch.setenv("WIGLE_API_TOKEN", "operator-token")
    source = load_source(CATALOGUE_ROOT / "09_wireless" / "wigle_search.yaml")
    observed: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed["authorization"] = request.headers.get("authorization", "")
        return httpx.Response(200, json={"results": []}, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    executor = HttpSourceExecutor(client=client)
    try:
        captures = [capture async for capture in executor.capture(source, "3C-37-86")]
    finally:
        await executor.aclose()

    assert captures
    assert captures[0].status == 200
    assert observed["authorization"].startswith("Basic ")


@pytest.mark.asyncio
async def test_basic_auth_only_source_fails_closed_when_pair_is_incomplete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WIGLE_API_NAME", "operator-name")
    monkeypatch.delenv("WIGLE_API_TOKEN", raising=False)
    source = load_source(CATALOGUE_ROOT / "09_wireless" / "wigle_search.yaml")

    def forbidden_handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("network must not be touched with incomplete credentials")

    client = httpx.AsyncClient(transport=httpx.MockTransport(forbidden_handler))
    executor = HttpSourceExecutor(client=client)
    try:
        with pytest.raises(AcquisitionError, match="WIGLE_API_TOKEN"):
            async for _capture in executor.capture(source, "3C-37-86"):
                pass
    finally:
        await executor.aclose()


@pytest.mark.asyncio
async def test_transport_error_redacts_api_key_from_failure_detail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = "transport-secret-marker-ethplorer"
    monkeypatch.setenv("ETHPLORER_API_KEY", marker)
    source = load_source(CATALOGUE_ROOT / "10_blockchain" / "ethplorer_address.yaml")

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"connect failed for {request.url}", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    executor = HttpSourceExecutor(client=client)
    try:
        with pytest.raises(AcquisitionError) as raised:
            async for _capture in executor.capture(source, "0xabc"):
                pass
    finally:
        await executor.aclose()

    assert raised.value.code == "transport_failed"
    assert marker not in raised.value.message
    assert "[REDACTED]" in raised.value.message
