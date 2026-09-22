"""T1-04: WARC/WET byte-range pull tests (parse WARC header prefix deterministically)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pytest

from network.range_pull import parse_warc_prefix, split_warc_records

pytestmark = pytest.mark.unit

WARC_PRELUDE = b"""WARC/1.0\r\nWARC-Type: response\r\nWARC-Warcinfo-ID: <urn:uuid:1111>\r\nWARC-Date: 2023-01-01T12:00:00Z\r\nWARC-Record-ID: <urn:uuid:2222>\r\nWARC-Target-URI: https://example.com/a\r\nContent-Type: application/http\r\nContent-Length: 30\r\n\r\n"""


def test_parse_warc_prefix_headers() -> None:
    headers, offset = parse_warc_prefix(WARC_PRELUDE)
    assert headers["warc-type"] == "response"
    assert headers["warc-target-uri"] == "https://example.com/a"
    assert headers["content-type"] == "application/http"
    assert offset == len(WARC_PRELUDE)  # payload begins after blank line


def test_split_warc_records_lf_endings() -> None:
    lf = WARC_PRELUDE.replace(b"\r\n", b"\n")
    pulls = split_warc_records(lf)
    assert len(pulls) == 1
    assert pulls[0].record_type == "response"
    assert pulls[0].url == "https://example.com/a"
    assert pulls[0].payload == b""


def test_split_warc_records_payload_text() -> None:
    blob = WARC_PRELUDE + b"<html><body>hello</body></html>"
    pulls = split_warc_records(blob)
    text = pulls[0].as_text()
    assert text == "<html><body>hello</body></html>"


def test_parse_empty_blob() -> None:
    assert parse_warc_prefix(b"") == ({}, 0)
    assert split_warc_records(b"") == []