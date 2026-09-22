"""T102: shared Common Crawl index access (badges, pagination, client)."""

from __future__ import annotations

import sys
from pathlib import Path

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