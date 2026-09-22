"""Cross-semantic retriever (T109): fuzzy badge routing + capability-aware backends."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from search import CrossSemanticRetriever, Hit, MemoryRetriever, SemanticBadgeIndex


def test_fuzzy_resolve_alias() -> None:
    index = SemanticBadgeIndex()
    assert index.fuzzy_resolve("common crawl") is not None
    assert index.fuzzy_resolve("browser render") == "javascript"


def test_fuzzy_resolve_returns_none_for_gibberish_low_cutoff() -> None:
    index = SemanticBadgeIndex()
    assert index.fuzzy_resolve("zzz jibberish kota", cutoff=0.9) is None


def test_badge_missing_from_catalog_resolves_via_alias() -> None:
    index = SemanticBadgeIndex()
    assert index.fuzzy_resolve("wayback-cdx", cutoff=1.0) == "bulk"


def test_route_to_covering_backend_only() -> None:
    http_mem = MemoryRetriever(
        {"d1": "http page content source example"}, capabilities={"http", "content-addressed"}
    )
    parquet_mem = MemoryRetriever(
        {"d2": "dataset read warehouse parquet"}, capabilities={"parquet"}
    )
    retriever = CrossSemanticRetriever([http_mem, parquet_mem])
    hits = retriever.search("page content")
    assert hits
    assert all(h.backend == "memory" for h in hits)


def test_unsupported_badge_returns_nothing() -> None:
    mem = MemoryRetriever({"d1": "http content"}, capabilities={"http"})
    retriever = CrossSemanticRetriever(mem)
    assert retriever.search("warc wayback archive") == []


def test_rrf_merges_across_backends() -> None:
    a = MemoryRetriever({"shared": "topic http body one", "only_a": "http only in a"}, capabilities={"http"})
    b = MemoryRetriever({"shared": "topic http body one", "only_b": "http in b too"}, capabilities={"http", "parquet"})
    retriever = CrossSemanticRetriever([a, b])
    hits = retriever.search("http topic", merge="rrf_any")
    assert hits[0].doc_id == "shared"


def test_first_merge_single_backend() -> None:
    mem = MemoryRetriever({"d1": "content here"}, capabilities={"http"})
    retriever = CrossSemanticRetriever(mem)
    hits = retriever.search("here", merge="first")
    assert len(hits) == 1
    assert isinstance(hits[0], Hit)