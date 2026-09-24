"""T1-04: Common Crawl columnar session tests (determinism, empty-domain, seam)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pytest

from network.cc_session import CcIndexSession, hostname_of

pytestmark = pytest.mark.unit


def _make_fixture_parquet(tmp_path: Path) -> Path:
    import duckdb

    parquet = tmp_path / "cc-index.parquet"
    duckdb.execute(
        """
        COPY (
            SELECT 'https://example.com/a' AS url, '20230101120000' AS timestamp,
                   200 AS status, 'text/html' AS mime, 'A' AS digest,
                   'crawldata/0.warc.gz' AS filename, 10 AS offset, 40 AS length
            UNION ALL SELECT 'https://example.com/b', '20230102120000', 200,
                   'text/html', 'B', 'crawldata/0.warc.gz', 55, 30
            UNION ALL SELECT 'https://www.example.com/c', '20230103120000', 200,
                   'text/html', 'C', 'crawldata/1.warc.gz', 90, 20
            UNION ALL SELECT 'https://other.org/x', '20230101120000', 200,
                   'text/html', 'D', 'crawldata/1.warc.gz', 1, 5
        ) TO '__(tmp)' (FORMAT PARQUET);
        """.replace("'__(tmp)'", f"'{parquet.as_posix()}'")
    )
    return parquet


@pytest.mark.asyncio
async def test_query_domain_deterministic(tmp_path: Path) -> None:
    if not CcIndexSession.available():
        pytest.skip("duckdb not installed")
    parquet = _make_fixture_parquet(tmp_path)
    sess = CcIndexSession(index_path=str(parquet), crawl="CC-MAIN-2023-40")
    try:
        first = sess.query_domain("example.com")
        second = sess.query_domain("example.com")
        assert [h.url for h in first] == [h.url for h in second]  # determinism
        assert [h.url for h in first] == [
            "https://example.com/a",
            "https://example.com/b",
            "https://www.example.com/c",
        ]
        loc = first[0].locator
        assert loc == "crawldata/0.warc.gz@10,40"
        assert first[0].crawl == "CC-MAIN-2023-40"
        assert first[0].subset == ""

        other = sess.query_domain("other.org")
        assert [h.url for h in other] == ["https://other.org/x"]
    finally:
        sess.close()


@pytest.mark.asyncio
async def test_query_domain_reads_current_schema_and_partitions(tmp_path: Path) -> None:
    if not CcIndexSession.available():
        pytest.skip("duckdb not installed")
    import duckdb

    parquet = tmp_path / "cc-current.parquet"
    duckdb.execute(
        """
        COPY (
            SELECT 'https://example.com/a' AS url,
                   '20240101120000' AS fetch_time,
                   200 AS fetch_status,
                   'text/html' AS content_mime_type,
                   'sha256:a' AS content_digest,
                   'crawldata/0.warc.gz' AS warc_filename,
                   10 AS warc_record_offset,
                   40 AS warc_record_length,
                   'CC-MAIN-2024-10' AS crawl,
                   'warc' AS subset,
                   'record-a' AS warc_record_id,
                   'example.com' AS url_host_registered_domain,
                   'com,example)/a' AS url_surtkey
            UNION ALL SELECT 'https://other.org/x', '20240101120000', 200,
                   'text/html', 'sha256:x', 'crawldata/1.warc.gz', 1, 5,
                   'CC-MAIN-2024-10', 'warc', 'record-x', 'other.org', 'org,other)/x'
            UNION ALL SELECT 'https://example.com/other', '20240101120000', 200,
                   'text/html', 'sha256:b', 'crawldata/2.warc.gz', 2, 6,
                   'CC-MAIN-2023-40', 'warc', 'record-b', 'example.com', 'com,example)/other'
            UNION ALL SELECT 'https://example.computer/x', '20240101120000', 200,
                   'text/html', 'sha256:c', 'crawldata/3.warc.gz', 3, 7,
                   'CC-MAIN-2024-10', 'warc', 'record-c', 'example.computer', 'com,example,computer)/x'
        ) TO '__(tmp)' (FORMAT PARQUET);
        """.replace("'__(tmp)'", f"'{parquet.as_posix()}'")
    )
    sess = CcIndexSession(index_path=str(parquet), crawl="CC-MAIN-2024-10", subset="warc")
    try:
        rows = sess.query_domain("example.com", match_type="domain")
        assert [(row.url, row.warc_record_id, row.locator) for row in rows] == [
            ("https://example.com/a", "record-a", "crawldata/0.warc.gz@10,40")
        ]
    finally:
        sess.close()


@pytest.mark.asyncio
async def test_query_domain_empty(tmp_path: Path) -> None:
    if not CcIndexSession.available():
        pytest.skip("duckdb not installed")
    parquet = _make_fixture_parquet(tmp_path)
    sess = CcIndexSession(index_path=str(parquet))
    try:
        assert sess.query_domain("nosuchdomain.example") == []
        assert sess.query_domain("") == []
    finally:
        sess.close()


def test_hostname_of() -> None:
    assert hostname_of("https://www.example.com/a?q=1") == "example.com"
    assert hostname_of("http://example.com") == "example.com"
    assert hostname_of("https://sub.example.com/x#y") == "sub.example.com"