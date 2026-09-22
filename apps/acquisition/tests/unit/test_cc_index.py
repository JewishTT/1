"""Common Crawl index adapter unit tests (T092): discovery normalization."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))

from adapters.commoncrawl.index import build_index_url, parse_index_lines

SAMPLE = "\n".join(
    [
        '{"url": "https://news.example/a", "timestamp": "20231012000000", "status": "200", '
        '"mime": "text/html", "digest": "abc", '
        '"filename": "crawl-data/CC-MAIN-1/segments/0/warc/000.warc.gz", '
        '"offset": "123", "length": "456"}',
        '{"url": "https://news.example/b", "timestamp": "20231012000001", "status": "200", '
        '"mime": "text/html", "digest": "def", '
        '"filename": "crawl-data/CC-MAIN-1/segments/0/warc/000.warc.gz", '
        '"offset": "457", "length": "789"}',
        '{"url": "https://skip.example/x"}',
    ]
)


def test_parse_index_lines_emits_warc_range_candidates() -> None:
    hits = parse_index_lines(SAMPLE)
    assert len(hits) == 2
    first = hits[0]
    assert first["uri"] == (
        "s3://data.commoncrawl.org/crawl-data/CC-MAIN-1/segments/0/warc/000.warc.gz"
        "?offset=123&length=456"
    )
    assert first["length"] == 456
    assert first["mime"] == "text/html"


def test_parse_index_lines_drops_malformed() -> None:
    assert parse_index_lines('{"url":"x"}\n\n{"filename":"f","offset":"1","length":"2"}\n') == [
        {
            "uri": "s3://data.commoncrawl.org/f?offset=1&length=2",
            "url": "",
            "timestamp": None,
            "status": None,
            "mime": None,
            "digest": None,
            "length": 2,
        }
    ]


def test_build_index_url_encodes_crawl_and_url() -> None:
    url = build_index_url("CC-MAIN-2023-40-index", "https://example.com/a?b=1")
    assert url.startswith("https://index.commoncrawl.org/CC-MAIN-2023-40-index?")
    assert "url=https%3A%2F%2Fexample.com%2Fa%3Fb%3D1" in url
    assert "output=json" in url