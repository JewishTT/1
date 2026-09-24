"""Common Crawl index access."""
from __future__ import annotations

import json
import re
from urllib.parse import urlencode

import httpx

INDEX_BASE = "https://index.commoncrawl.org"
DEFAULT_CRAWL = "CC-MAIN-2023-40"
_BADGE = re.compile(r"^(?P<kind>[A-Z]+)-(?:MAIN|NEWS)-(?P<year>\d{4})-(?P<week>\d{2})$")


def build_index_url(crawl: str, url: str, *, output: str = "json", page: int | None = None, **extra: str) -> str:
    query: dict[str, str] = {"url": url, "output": output}
    if page is not None:
        query["page"] = str(page)
    query.update(extra)
    return f"{INDEX_BASE}/{crawl}?{urlencode(query)}"


def crawl_badge(crawl: str) -> tuple[str, int, int] | None:
    m = _BADGE.match(crawl)
    return (m.group("kind"), int(m.group("year")), int(m.group("week"))) if m else None


def select_latest(crawls: list[str]) -> str:
    return max(crawls, key=lambda c: crawl_badge(c) or (c, 0, 0))


def parse_index_lines(text: str, *, crawl: str = "", page: int | None = None) -> list[dict]:
    hits: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        filename, offset, length = rec.get("filename"), rec.get("offset"), rec.get("length")
        if not filename or offset is None or length is None:
            continue
        hits.append({
            "uri": f"s3://data.commoncrawl.org/{filename}?offset={int(offset)}&length={int(length)}",
            "url": rec.get("url", ""), "timestamp": rec.get("timestamp"),
            "status": rec.get("status"), "mime": rec.get("mime"),
            "digest": rec.get("digest"), "length": int(length),
        })
    return sorted(hits, key=lambda h: (h["uri"], h["timestamp"] or ""))


class CommonCrawlClient:
    def __init__(self, *, base: str = INDEX_BASE, timeout: float = 120.0, transport=None) -> None:
        self._base, self._timeout, self._transport = base.rstrip("/"), timeout, transport

    async def _get(self, url: str) -> str:
        if self._transport is not None:
            return await self._transport(url)
        async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.text

    async def list_indexes(self) -> list[str]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(f"{self._base}/collinfo.json")
            response.raise_for_status()
        return [str(x.get("id")) for x in response.json() if str(x.get("id", "")).startswith(("CC-MAIN", "CC-NEWS"))]

    async def discover(self, url: str, *, crawl: str = DEFAULT_CRAWL, page: int | None = None, index_url: str | None = None, **extra: str) -> list[dict]:
        if index_url is None:
            live_crawl = crawl if crawl.endswith("-index") else f"{crawl}-index"
            index_url = build_index_url(live_crawl if self._transport is None else crawl, url, page=page, **extra)
        else:
            index_url = index_url.replace(INDEX_BASE, self._base)
        text = await self._get(index_url)
        if isinstance(text, bytes):
            text = text.decode("utf-8")
        if text.lstrip().startswith("<"):
            raise ValueError("Common Crawl index returned HTML instead of NDJSON")
        return parse_index_lines(text, crawl=crawl, page=page)

    async def discover_partitions(
        self,
        url: str,
        *,
        crawls: list[str] | None = None,
        max_crawls: int = 3,
        max_pages: int = 1,
        limit: int = 50,
        **extra: str,
    ) -> list[dict]:
        """Discover bounded candidates across crawl partitions and index pages.

        A partition is a Common Crawl index epoch, not a single global query.
        When ``crawls`` is omitted, the newest unique IDs returned by
        :meth:`list_indexes` are selected. A failed partition/page is skipped so
        one unavailable epoch cannot erase the rest of a historical run.
        """
        if max_crawls <= 0 or max_pages <= 0 or limit <= 0:
            raise ValueError("max_crawls, max_pages, and limit must be positive")

        available = list(crawls) if crawls is not None else await self.list_indexes()
        partitions = sorted(
            {crawl.strip() for crawl in available if crawl.strip()},
            key=lambda crawl: (crawl_badge(crawl) or ("", 0, 0), crawl),
            reverse=True,
        )[:max_crawls]
        out: dict[tuple[str, str, str], dict] = {}
        for partition in partitions:
            for page in range(max_pages):
                try:
                    hits = await self.discover(
                        url, crawl=partition, page=page, limit=limit, **extra
                    )
                except Exception:
                    continue
                if not hits:
                    break
                for hit in hits:
                    key = (
                        str(hit.get("uri", "")),
                        str(hit.get("timestamp", "")),
                        str(hit.get("digest", "")),
                    )
                    if not key[0] or key in out:
                        continue
                    out[key] = {**hit, "crawl": partition, "page": page}
                if len(hits) < limit:
                    break
        return sorted(
            out.values(),
            key=lambda hit: (
                str(hit.get("timestamp", "")),
                str(hit.get("uri", "")),
                str(hit.get("crawl", "")),
                int(hit.get("page", 0)),
            ),
        )

__all__ = ["CommonCrawlClient", "build_index_url", "crawl_badge", "parse_index_lines", "select_latest"]
