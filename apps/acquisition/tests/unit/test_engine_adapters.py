"""Engine adapter unit tests (T096/T098/T099/T100): onboarding + pure contracts."""

from __future__ import annotations

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))

import adapters.browsertrix  # noqa: F401 - import-time registration
import adapters.heritrix  # noqa: F401
import adapters.nutch  # noqa: F401
import adapters.stormcrawler  # noqa: F401
import pytest
from adapters.browsertrix.collect import build_crawl_command, parse_warc_file
from adapters.heritrix.collect import parse_warc_bytes
from adapters.nutch.collect import build_crawl_args, parse_segment_file
from adapters.registry import REGISTRY
from adapters.stormcrawler.collect import build_job_spec, parse_fetch_manifest
from warcio import WARCWriter
from warcio.statusandheaders import StatusAndHeaders


def _registration(source_type: str):
    return next((r for r in REGISTRY if r.source_type == source_type), None)


def _warc_bytes(url: str, body: bytes, content_type: str = "text/html") -> bytes:
    buf = io.BytesIO()
    writer = WARCWriter(buf, gzip=False)
    writer.write_record(
        writer.create_warc_record(
            url,
            "response",
            payload=io.BytesIO(body),
            http_headers=StatusAndHeaders(
                "HTTP/1.1 200 OK",
                [("Content-Type", content_type), ("Content-Length", str(len(body)))],
                protocol="HTTP/1.1",
            ),
        )
    )
    return buf.getvalue()


def test_engine_adapters_register_with_capability_surfaces() -> None:
    heritrix = _registration("heritrix")
    assert heritrix is not None and heritrix.execution_class == "archival"
    assert heritrix.covers(frozenset({"warc", "range-read", "bulk"}))

    browsertrix = _registration("browsertrix")
    assert browsertrix is not None and browsertrix.execution_class == "browser"
    assert browsertrix.covers(frozenset({"javascript", "dom", "warc"}))

    stormcrawler = _registration("stormcrawler")
    assert stormcrawler is not None and stormcrawler.execution_class == "custom"
    assert stormcrawler.covers(frozenset({"bulk", "warc"}))

    nutch = _registration("nutch")
    assert nutch is not None and nutch.execution_class == "bulk"
    assert nutch.covers(frozenset({"bulk", "content-addressed"}))


def test_heritrix_parse_warc_bytes_extracts_http_responses() -> None:
    records = parse_warc_bytes(_warc_bytes("https://h.example/p", b"<html>h</html>"))
    assert len(records) == 1
    assert records[0].url == "https://h.example/p"
    assert records[0].payload == b"<html>h</html>"
    assert records[0].content_type == "text/html"


def test_browsertrix_crawl_command_contract() -> None:
    cmd = build_crawl_command(
        {"seed_urls": ["https://a.example/", "https://b.example/"], "workers": 4},
        collection="c1",
    )
    assert cmd[:2] == ["crawler", "crawl"]
    assert cmd[cmd.index("--collection") + 1] == "c1"
    assert cmd[cmd.index("--workers") + 1] == "4"
    assert cmd.count("--url") == 2
    assert "--noScreenshots" in cmd
    assert build_crawl_command(
        {"uri": "https://c.example/", "screenshots": True}, collection="c2"
    ).count("--noScreenshots") == 0
    with pytest.raises(ValueError):
        build_crawl_command({}, collection="c3")


def test_browsertrix_parse_warc_file(tmp_path: Path) -> None:
    warc = tmp_path / "000.warc"
    warc.write_bytes(_warc_bytes("https://b.example/", b"<html>b</html>"))
    records = parse_warc_file(warc)
    assert [r.url for r in records] == ["https://b.example/"]


def test_stormcrawler_job_spec_and_manifest() -> None:
    spec = build_job_spec({"seed_urls": ["https://s.example/"]}, crawl_id="job-1", fetchers=3)
    assert spec["crawl_id"] == "job-1"
    assert spec["seeds"] == ["https://s.example/"]
    assert spec["fetchers"] == 3
    assert spec["sink"] == "manifest://cognitive"
    with pytest.raises(ValueError):
        build_job_spec({})

    rows = parse_fetch_manifest(
        '{"url": "https://s.example/a", "path": "/tmp/a", "content_type": "text/html"}\n'
        '{"url": "missing-path"}\n\n'
    )
    assert len(rows) == 1
    assert rows[0]["content_type"] == "text/html"


def test_nutch_crawl_args_and_segment_parse(tmp_path: Path) -> None:
    args = build_crawl_args({"uri": "https://n.example/"}, seeds_dir="/seeds", crawl_dir="/crawl")
    assert args[:3] == ["bin/nutch", "crawl", "/seeds"]
    assert args[args.index("-dir") + 1] == "/crawl"
    assert args[args.index("-depth") + 1] == "3"

    doc = tmp_path / "seg" / "parse_text" / "0000"
    doc.parent.mkdir(parents=True)
    doc.write_text("URL: https://n.example/page\n# meta\n<html>nutch</html>", encoding="utf-8")
    parsed = parse_segment_file(doc.read_text(encoding="utf-8"))
    assert parsed is not None
    url, payload = parsed
    assert url == "https://n.example/page"
    assert payload == b"<html>nutch</html>"
    assert parse_segment_file("no url here") is None