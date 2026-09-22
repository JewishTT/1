"""Standalone Scrapy spider for the exemplar adapter (T096).

Runs via ``scrapy runspider`` inside the adapter's own process; emits one
record per page to ``index.ndjson`` plus a binary blob per page. Spiders never
touch Postgres/events directly (Observation boundary) — the adapter streams the
written bytes into the gate afterwards.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import scrapy


class CollectorPipeline:
    """Write page bytes side-by-side with an NDJSON line (url/path/type)."""

    def process_item(self, item, spider):  # type: ignore[no-untyped-def]
        outdir = Path(spider.outdir)
        name = hashlib.sha1(item["url"].encode()).hexdigest()[:16]
        path = outdir / f"{name}.blob"
        path.write_bytes(item.pop("body"))
        item["path"] = str(path)
        with (outdir / "index.ndjson").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")
        return item


class ExemplarSpider(scrapy.Spider):
    name = "exemplar"
    custom_settings = {
        "LOG_LEVEL": "ERROR",
        "ROBOTSTXT_OBEY": False,
        "CONCURRENT_REQUESTS": 4,
        "AUTOTHROTTLE_ENABLED": False,
        "TELNETCONSOLE_ENABLED": False,
        "ITEM_PIPELINES": {"adapters.scrapy.spider.CollectorPipeline": 300},
    }

    def __init__(self, urls_file: str | None = None, outdir: str | None = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.outdir = str(Path(outdir or ".").resolve())
        self.start_urls: list[str] = []
        if urls_file:
            text = Path(urls_file).read_text(encoding="utf-8")
            self.start_urls = [ln.strip() for ln in text.splitlines() if ln.strip()]

    def parse(self, response):
        yield {
            "url": response.url,
            "status": response.status,
            "content_type": (response.headers.get("Content-Type") or b"")
            .decode(errors="replace")
            .split(";")[0],
            "body": response.body,
            "title": "".join(response.css("title ::text").getall()),
        }
        if response.status == 200:
            yield from self._follow_same_host(response)

    def _follow_same_host(self, response):
        from urllib.parse import urlparse

        host = urlparse(response.url).netloc
        for href in response.css("a::attr(href)").getall():
            url = response.urljoin(href)
            if url.startswith("http") and urlparse(url).netloc == host:
                yield scrapy.Request(url, callback=self.parse, errback=self.on_error)

    def on_error(self, failure) -> None:  # type: ignore[no-untyped-def]
        self.logger.debug("skip %s: %s", failure.request.url, failure.getErrorMessage())