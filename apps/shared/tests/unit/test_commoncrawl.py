"""T102: shared Common Crawl index access (badges, pagination, client)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pytest

from network.commoncrawl import (
    CommonCrawlClient,
    build_index_url,
    crawl_badge,
    parse_index_lines,
    select_latest,
)


def test_build_index_url_pagination_and_extra() -> None:
    url = build_index_url("CC-MAIN-2023-40", "https://news.example/a", page=2, filter="status:200")
    assert "url=https%3A%2F%2Fnews.example%2Fa" in url
    assert "output=json" in url
    assert "page=2" in url
    assert "filter=status%3A200" in url


def test_parse_index_lines_normalizes_offset_length_contract() -> None:
    lines = [
        '{"url": "u", "timestamp": "t", "status": "200", "mime": "text/html", '
        '"digest": "d", "filename": "f.warc.gz", "offset": "10", "length": "20"}',
        '{"url": "bad"}',  # no filename -> dropped
        '{"filename": "g.warc.gz", "offset": "1"}',  # no length -> dropped
    ]
    hits = parse_index_lines("\n".join(lines))
    assert len(hits) == 1
    assert hits[0]["uri"] == "s3://data.commoncrawl.org/f.warc.gz?offset=10&length=20"
    assert hits[0]["length"] == 20


def test_crawl_badges_and_latest_selection() -> None:
    assert crawl_badge("CC-MAIN-2024-10") == ("CC", 2024, 10)
    assert crawl_badge("CC-NEWS-2023-08") == ("CC", 2023, 8)
    assert crawl_badge("weird") is None
    crawls = ["CC-MAIN-2023-10", "CC-MAIN-2024-05", "CC-NEWS-2024-01"]
    assert select_latest(crawls) == "CC-MAIN-2024-05"


@pytest.mark.asyncio
async def test_client_discover_uses_injected_transport() -> None:
    record = (
        '{"url": "https://x.example/", "filename": "c/0.warc.gz", "offset": "3", "length": "4"}'
    )
    seen: list[str] = []

    async def transport(url: str) -> str:
        seen.append(url)
        return record

    client = CommonCrawlClient(transport=transport)
    hits = await client.discover("https://x.example/", crawl="CC-MAIN-2023-40", page=1)
    assert len(hits) == 1
    assert hits[0]["url"] == "https://x.example/"
    assert "page=1" in seen[0]
    assert "https://index.commoncrawl.org/CC-MAIN-2023-40?" in seen[0]


def _record(filename: str, timestamp: str, *, digest: str = "digest") -> str:
    return json.dumps(
        {
            "url": f"https://x.example/{filename}",
            "timestamp": timestamp,
            "status": "200",
            "mime": "text/html",
            "digest": digest,
            "filename": f"{filename}.warc.gz",
            "offset": "10",
            "length": "20",
        }
    )


@pytest.mark.asyncio
async def test_discover_partitions_uses_index_list_and_bounded_page_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    crawls = [
        "CC-MAIN-2023-40",
        "CC-MAIN-2024-10",
        "CC-MAIN-2022-50",
        "CC-MAIN-2024-10",
    ]
    calls: list[tuple[str, int, str, str]] = []
    list_calls = 0

    async def list_indexes() -> list[str]:
        nonlocal list_calls
        list_calls += 1
        return crawls

    async def transport(url: str) -> str:
        parsed = urlsplit(url)
        params = parse_qs(parsed.query)
        crawl = parsed.path.rsplit("/", 1)[-1]
        page = int(params["page"][0])
        calls.append((crawl, page, params["limit"][0], params["filter"][0]))
        if crawl == "CC-MAIN-2024-10":
            if page == 0:
                return "\n".join(
                    [
                        _record("newest-0", "20240101000000", digest="a"),
                        _record("newest-1", "20240102000000", digest="b"),
                    ]
                )
            if page == 1:
                return "\n".join(
                    [
                        _record("newest-0", "20240101000000", digest="a"),
                        _record("newest-2", "20240103000000", digest="c"),
                    ]
                )
        if crawl == "CC-MAIN-2023-40" and page == 0:
            return _record("older-0", "20231201000000", digest="d")
        return ""

    client = CommonCrawlClient(transport=transport)
    monkeypatch.setattr(client, "list_indexes", list_indexes)

    hits = await client.discover_partitions(
        "x.example",
        max_crawls=2,
        max_pages=3,
        limit=2,
        filter="status:200",
    )

    assert list_calls == 1
    assert calls == [
        ("CC-MAIN-2024-10", 0, "2", "status:200"),
        ("CC-MAIN-2024-10", 1, "2", "status:200"),
        ("CC-MAIN-2024-10", 2, "2", "status:200"),
        ("CC-MAIN-2023-40", 0, "2", "status:200"),
    ]
    assert [(hit["crawl"], hit["page"], hit["digest"]) for hit in hits] == [
        ("CC-MAIN-2023-40", 0, "d"),
        ("CC-MAIN-2024-10", 0, "a"),
        ("CC-MAIN-2024-10", 0, "b"),
        ("CC-MAIN-2024-10", 1, "c"),
    ]


@pytest.mark.asyncio
async def test_discover_partitions_skips_failed_page_and_other_partition() -> None:
    calls: list[tuple[str, int]] = []

    async def transport(url: str) -> str:
        parsed = urlsplit(url)
        params = parse_qs(parsed.query)
        crawl = parsed.path.rsplit("/", 1)[-1]
        page = int(params["page"][0])
        calls.append((crawl, page))
        if crawl == "CC-MAIN-2024-10" and page == 0:
            raise RuntimeError("partition temporarily unavailable")
        if crawl == "CC-MAIN-2024-10":
            return _record("recovered", "20240101000000")
        if page == 0:
            return _record("older", "20231201000000")
        return ""

    client = CommonCrawlClient(transport=transport)
    hits = await client.discover_partitions(
        "x.example",
        crawls=["CC-MAIN-2023-40", "CC-MAIN-2024-10"],
        max_pages=2,
        limit=1,
    )

    assert calls == [
        ("CC-MAIN-2024-10", 0),
        ("CC-MAIN-2024-10", 1),
        ("CC-MAIN-2023-40", 0),
        ("CC-MAIN-2023-40", 1),
    ]
    assert [hit["crawl"] for hit in hits] == ["CC-MAIN-2023-40", "CC-MAIN-2024-10"]


@pytest.mark.asyncio
async def test_discover_partitions_rejects_unbounded_settings() -> None:
    client = CommonCrawlClient()
    with pytest.raises(ValueError, match="max_crawls"):
        await client.discover_partitions("x.example", crawls=[], max_crawls=0)
    assert await client.discover_partitions("x.example", crawls=[]) == []
