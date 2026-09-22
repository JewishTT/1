"""Common Crawl index access (T102): badges + pagination + shared client.

The acquisition/adapters/commoncrawl adapter delegates here so the piece is
reusable outside the acquisition loop (batch backfill, badge-picking playground).
Pure parsing lives here; transport stays injectable (``httpx`` default).

Index hits normalize into *candidate* ``warc://`` Frontier items carrying the
exact offset/length required by the WARC range adapter (T093).
"""

from __future__ import annotations

import json
import re
from urllib.parse import urlencode

import httpx

INDEX_BASE = "https://index.commoncrawl.org"
DEFAULT_CRAWL = "CC-MAIN-2023-40"

_BADGE = re.compile(r"^(?P<kind>[A-Z]+)-(?:MAIN|NEWS)-(?P<year>\d{4})-(?P<week>\d{2})$")


def build_index_url(
    crawl: str,
    url: str,
    *,
    output: str = "json",
    page: int | None = None,
    **extra: str,
) -> str:
    """Build a Common Crawl index query URL (badge ``crawl`` + optional ``page``)."""
    query: dict[str, str] = {"url": url, "output": output}
    if page is not None:
        query["page"] = str(page)
    query.update(extra)
    return f"{INDEX_BASE}/{crawl}?{urlencode(query)}"


def crawl_badge(crawl: str) -> tuple[str, int, int] | None:
    """Numeric badge of a crawl id for ordering/sorting, or None if unknown."""
    m = _BADGE.match(crawl)
    if not m:
        return None
    return m.group("kind"), int(m.group("year")), int(m.group("week"))


def select_latest(crawls: list[str]) -> str:
    """Pick the newest crawl badge from a list of index names."""
    return max(crawls, key=lambda c: crawl_badge(c) or (c, 0, 0))


def parse_index_lines(text: str) -> list[dict]:
    """Normalize CC index NDJSON lines into candidate hits (offset/length contract).

    Each hit is a dict matching the acquisition adapter's Frontier candidate
    contract: ``uri`` (``s3://...warc?offset=..&length=..``) plus metadata.
    """
    hits: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        filename = rec.get("filename", "")
        offset, length = rec.get("offset"), rec.get("length")
        if not filename or offset is None or length is None:
            continue
        hits.append(
            {
                "uri": f"s3://data.commoncrawl.org/{filename}?offset={int(offset)}&length={int(length)}",
                "url": rec.get("url", ""),
                "timestamp": rec.get("timestamp"),
                "status": rec.get("status"),
                "mime": rec.get("mime"),
                "digest": rec.get("digest"),
                "length": int(length),
            }
        )
    return sorted(hits, key=lambda h: (h["uri"], h["timestamp"] or ""))


class CommonCrawlClient:
    """Thin async HTTP facade for the public CC index (injectable transport)."""

    def __init__(self, *, base: str = INDEX_BASE, timeout: float = 120.0, transport=None) -> None:
        self._base = base.rstrip("/")
        self._timeout = timeout
        self._transport = transport

    async def _get(self, url: str) -> str:
        if self._transport is not None:
            return await self._transport(url)
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.text

    async def list_indexes(self) -> list[str]:
        """Badge list from the collinfo.json endpoint (``CC-MAIN-*`` entries)."""
        hits_url = f"{self._base}/collinfo.json"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(hits_url)
            resp.raise_for_status()
        return [
            str(entry.get("id"))
            for entry in resp.json()
            if str(entry.get("id", "")).startswith(("CC-MAIN", "CC-NEWS"))
        ]

    async def discover(
        self,
        url: str,
        *,
        crawl: str = DEFAULT_CRAWL,
        page: int | None = None,
        index_url: str | None = None,
        **extra: str,
    ) -> list[dict]:
        """Query the index and return normalized candidate hits (dicts)."""
        if index_url is None:
            index_url = build_index_url(crawl, url, page=page, **extra)
        else:
            index_url = index_url.replace(INDEX_BASE, self._base)
        text = await self._get(index_url)
        return parse_index_lines(text)