"""Unit: bulk backfill planner merges CC + Wayback CDX surfaces (T108)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))

import pytest
from network.commoncrawl import CommonCrawlClient

from backfill import (
    BackfillPlan,
    BackfillStats,
    backfill,
    build_cdx_url,
    dedupe_candidates,
    parse_cdx_lines,
)
from historical.replay import MemoryFrontierSink

pytestmark = pytest.mark.unit


def _cc_payload() -> bytes:
    hits = [
        {
            "url": "https://old.example/x",
            "timestamp": "20231001000000",
            "status": "200",
            "mime": "text/html",
            "digest": "aa",
            "filename": "crawl-data/CC-MAIN-1/segments/0/warc/a.warc.gz",
            "offset": "10",
            "length": "20",
        },
        {
            "url": "https://old.example/y",
            "timestamp": "20231001000001",
            "status": "200",
            "mime": "text/html",
            "digest": "bb",
            "filename": "crawl-data/CC-MAIN-1/segments/0/warc/a.warc.gz",
            "offset": "30",
            "length": "40",
        },
    ]
    return "\n".join(json.dumps(h) for h in hits).encode()


class _CdxFake:
    def __init__(self, records: list[dict]) -> None:
        self._records = records

    async def captures(self, plan: BackfillPlan) -> list[dict]:
        return dedupe_candidates(
            [
                {
                    "uri": f"https://web.archive.org/web/{r['timestamp']}id_/{r['url']}",
                    "url": r["url"],
                    "timestamp": r["timestamp"],
                    "surface": "wayback",
                }
                for r in self._records
            ]
        )


def test_build_cdx_url_contains_domain_window_and_digest_collapse() -> None:
    url = build_cdx_url("example.com", from_ts="20230101", to_ts="20231231")
    assert url.startswith("https://web.archive.org/cdx?")
    assert "matchType=domain" in url
    assert "from=20230101" in url
    assert "to=20231231" in url
    assert "collapse=digest" in url
    limited = build_cdx_url("example.com", from_ts="20230101", to_ts="20231231", limit=5)
    assert "limit=5" in limited


def test_parse_cdx_json_array_normalizes_candidates() -> None:
    text = json.dumps(
        [
            {
                "urlkey": "example.com/x",
                "timestamp": "20230601120000",
                "original": "https://example.com/x",
                "statuscode": "200",
                "mimetype": "text/html",
                "digest": "DDD",
                "length": "123",
            }
        ]
    )
    candidates = parse_cdx_lines(text)
    assert len(candidates) == 1
    c = candidates[0]
    assert c["uri"].startswith("https://web.archive.org/web/20230601120000id_/")
    assert c["status"] == "200"
    assert c["surface"] == "wayback"
    assert c["length"] == "123"


def test_parse_cdx_ndjson_and_plain_columns() -> None:
    ndjson = json.dumps({"urlkey": "a", "timestamp": "20230601", "original": "https://a/page"})
    assert parse_cdx_lines(ndjson)[0]["timestamp"] == "20230601"
    assert parse_cdx_lines("") == []
    column = parse_cdx_lines("example.com 20230601 https://example.com 200 text/html DDD 9")
    assert column[0]["url"] == "https://example.com"


def test_dedupe_candidates_collapses_cross_surface_duplicate() -> None:
    a = {"url": "https://s/page", "timestamp": "20230101", "digest": "z", "surface": "cc"}
    b = {"url": "https://s/page", "timestamp": "20230101", "digest": "z", "surface": "wayback"}
    merged = dedupe_candidates([a, b])
    assert len(merged) == 1


async def test_backfill_merges_cc_and_wayback_with_stats() -> None:
    async def cc_transport(url: str) -> str:
        return _cc_payload()
    sink = MemoryFrontierSink()
    plan = BackfillPlan(
        cc_prefixes=["https://old.example"],
        domains=["example.com"],
        cc_crawl="CC-MAIN-2023-40",
    )
    cdx = _CdxFake(
        [
            {"url": "https://example.com/w", "timestamp": "20230201000000"},
            {"url": "https://old.example/x", "timestamp": "20231001000000"},  # unique surface
        ]
    )

    stats = await backfill(
        plan,
        sink,
        cc_client=CommonCrawlClient(transport=cc_transport),
        cdx_client=cdx,
    )

    assert stats.discovered_cc == 2
    assert stats.discovered_cdx == 2
    assert stats.merged == 2
    assert stats.enqueued == 4
    assert stats.deduped == 0
    assert BackfillStats().enqueued == 0