"""WARC adapter unit tests (T093): extraction + range contract."""

from __future__ import annotations

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))

import pytest
from adapters.warc.collect import (
    parse_warc,
    range_of,
    split_s3_uri,
)
from warcio import WARCWriter
from warcio.statusandheaders import StatusAndHeaders


def _warc_bytes(url="https://collect.example/page", body=b"<html>from warc</html>") -> bytes:
    buf = io.BytesIO()
    writer = WARCWriter(buf, gzip=False)
    http_headers = StatusAndHeaders(
        "HTTP/1.1 200 OK",
        [("Content-Type", "text/html; charset=utf-8"), ("Content-Length", str(len(body)))],
        protocol="HTTP/1.1",
    )
    record = writer.create_warc_record(
        url,
        "response",
        payload=io.BytesIO(body),
        http_headers=http_headers,
    )
    writer.write_record(record)
    return buf.getvalue()


def test_parse_warc_extracts_payload_and_metadata() -> None:
    data = _warc_bytes()
    records = parse_warc(io.BytesIO(data))
    assert len(records) == 1
    rec = records[0]
    assert rec.url == "https://collect.example/page"
    assert rec.payload == b"<html>from warc</html>"
    assert rec.content_type == "text/html"
    assert rec.warc_date


def test_parse_warc_skips_metadata_records() -> None:
    buf = io.BytesIO()
    writer = WARCWriter(buf, gzip=False)
    writer.write_record(writer.create_warc_record("https://collect.example/page", "warcinfo"))
    assert parse_warc(io.BytesIO(buf.getvalue())) == []


def test_range_uri_contract() -> None:
    uri = "s3://data.commoncrawl.org/CC-MAIN-1.warc?offset=42&length=900"
    assert split_s3_uri(uri) == ("data.commoncrawl.org", "CC-MAIN-1.warc")
    assert range_of(uri) == (42, 900)
    assert range_of("s3://b/k?offset=7") == (7, None)
    with pytest.raises(ValueError):
        split_s3_uri("/not/s3")