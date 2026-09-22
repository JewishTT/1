"""Unit: historical archive replay enqueues CC candidates safely (T121)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))

import pytest
from network.commoncrawl import DEFAULT_CRAWL, CommonCrawlClient

from historical.replay import HistoricalReplay, MemoryFrontierSink, ReplayStats

pytestmark = pytest.mark.unit

_HIT_A = {
    "url": "https://news.example/a",
    "timestamp": "20231012000000",
    "status": "200",
    "mime": "text/html",
    "digest": "abc",
    "filename": "crawl-data/CC-MAIN-1/segments/0/warc/000.warc.gz",
    "offset": "123",
    "length": "456",
}


def _page_payload(hits: list[dict]) -> bytes:
    return "\n".join(json.dumps(h) for h in hits).encode()


async def test_single_batch_enqueues_candidates() -> None:
    async def transport(url: str) -> str:
        return _page_payload([_HIT_A])
    sink = MemoryFrontierSink()
    replay = HistoricalReplay(sink, client=CommonCrawlClient(transport=transport), batch_size=100)

    stats = await replay.run(["https://news.example/a"])

    assert stats.discovered == 1
    assert stats.enqueued == 1
    assert stats.deduped == 0
    assert stats.batches == 1
    candidate = sink.enqueued[0]
    assert candidate["uri"].startswith("s3://data.commoncrawl.org/")
    assert "offset=123" in candidate["uri"]
    assert "length=456" in candidate["uri"]
    assert candidate["url"] == "https://news.example/a"


async def test_sink_dedup_returns_false_for_repeat_uri() -> None:
    sink = MemoryFrontierSink()
    assert sink.enqueue({"uri": "s3://x/1?offset=0&length=1"}) is True
    assert sink.enqueue({"uri": "s3://x/1?offset=0&length=1"}) is False
    assert sink.count == 1

async def test_duplicate_candidates_deduped_across_prefixes() -> None:
    async def transport(url: str) -> str:
        return _page_payload([dict(_HIT_A)])

    sink = MemoryFrontierSink()
    replay = HistoricalReplay(
        sink, client=CommonCrawlClient(transport=transport), batch_size=1
    )

    stats = await replay.run(["https://news.example/a", "https://news.example/b"])

    assert stats.enqueued == 1  # second prefix re-visits the same hit
    assert stats.deduped == 2  # page-1 of prefix a + page-0 of prefix b
    assert stats.batches == 3
    assert stats.discovered == 3  # raw rows scanned (dup pages included)
    assert sink.count == 1


async def test_empty_page_stops_pagination() -> None:
    async def transport(url: str) -> str:
        return ""
    sink = MemoryFrontierSink()
    replay = HistoricalReplay(sink, client=CommonCrawlClient(transport=transport))
    stats = await replay.run(["https://news.example/a"])
    assert stats == ReplayStats()
    assert sink.count == 0


async def test_stats_merge_totals() -> None:
    a = ReplayStats(discovered=2, enqueued=1, deduped=1, batches=1)
    b = ReplayStats(discovered=3, enqueued=2, deduped=1, batches=2)
    merged = a.merge(b)
    assert merged.discovered == 5
    assert merged.enqueued == 3
    assert merged.deduped == 2
    assert merged.batches == 3
    assert DEFAULT_CRAWL  # imported constant resolves