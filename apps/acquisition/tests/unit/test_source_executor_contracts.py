"""URL and upstream identity contracts for public metadata acquisition."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from sources.catalogue import CATALOGUE_ROOT, load_source
from sources.executor import AcquisitionError, request_headers, resolve_query


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
