"""Bulk historical backfill (T108): Common Crawl + Wayback CDX.

The backfill planner merges two archive surfaces into one deterministic
candidate list: Common Crawl index hits (``s3://`` WARC range candidates) and
Wayback CDX captures (``web.archive.org`` replay candidates). Cross-archive
duplicates (same URL+timestamp) collapse before anything reaches the frontier;
ordering is stable so replays are reproducible.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Protocol

CDX_BASE = "https://web.archive.org/cdx"
CC_CRAWL_DEFAULT = "CC-MAIN-2023-40"


def build_cdx_url(
    domain: str,
    *,
    from_ts: str,
    to_ts: str,
    output: str = "json",
    limit: int | None = None,
    base: str = CDX_BASE,
    match_type: str = "domain",
) -> str:
    """Build a Wayback CDX API query for a domain over a time window."""
    from urllib.parse import urlencode

    query: dict[str, str] = {
        "url": domain,
        "from": from_ts,
        "to": to_ts,
        "output": output,
        "collapse": "digest",
        "matchType": match_type,
        "fl": "urlkey,timestamp,original,statuscode,mimetype,digest,length",
    }
    if limit is not None:
        query["limit"] = str(limit)
    return f"{base}?{urlencode(query)}"


def parse_cdx_lines(text: str) -> list[dict]:
    """Normalize CDX JSON (array or NDJSON) into capture candidates.

    Candidate contract mirrors the CC adapter: ``uri`` points at the replay
    URL, plus ``timestamp``/``status``/``mime``/``digest`` metadata.
    """
    text = (text or "").strip()
    if not text:
        return []
    if text.startswith("["):
        records = json.loads(text)
    else:
        records = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                # CDX "text" output: urlkey timestamp original status mime digest length
                parts = line.split()
                if len(parts) >= 4:
                    records.append(
                        {
                            "urlkey": parts[0],
                            "timestamp": parts[1],
                            "original": parts[2],
                            "statuscode": parts[3],
                        }
                    )
    candidates: list[dict] = []
    for rec in records:
        original = rec.get("original") or rec.get("url") or ""
        timestamp = rec.get("timestamp")
        if not original or not timestamp:
            continue
        candidates.append(
            {
                "uri": f"https://web.archive.org/web/{timestamp}id_/{original}",
                "url": original,
                "timestamp": timestamp,
                "status": rec.get("statuscode"),
                "mime": rec.get("mimetype"),
                "digest": rec.get("digest"),
                "length": rec.get("length"),
                "surface": "wayback",
            }
        )
    return candidates


def dedupe_candidates(candidates: list[dict]) -> list[dict]:
    """Stable dedup: identical (url, timestamp, digest) collapse across archives."""
    seen: set[tuple[str, str, str]] = set()
    out: list[dict] = []
    for c in candidates:
        key = (c.get("url", ""), str(c.get("timestamp", "")), str(c.get("digest", "")))
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


class FrontierSink(Protocol):
    def enqueue(self, candidate: dict) -> bool: ...


@dataclass
class BackfillPlan:
    """Deterministic merged plan across both archive surfaces."""

    cc_prefixes: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    from_ts: str = "20230101"
    to_ts: str = "20231231"
    cc_crawl: str = CC_CRAWL_DEFAULT

    def source_count(self) -> int:
        return len(self.cc_prefixes) + len(self.domains)


@dataclass
class BackfillStats:
    discovered_cc: int = 0
    discovered_cdx: int = 0
    merged: int = 0
    enqueued: int = 0
    deduped: int = 0


class WaybackCdxClient:
    """Thin CDX transport (injectable for hermetic tests)."""

    def __init__(self, *, base: str = CDX_BASE, fetch=None) -> None:
        self._base = base
        self._fetch = fetch

    async def captures(self, plan: BackfillPlan) -> list[dict]:
        out: list[dict] = []
        for domain in plan.domains:
            url = build_cdx_url(domain, from_ts=plan.from_ts, to_ts=plan.to_ts, base=self._base)
            text = await self._fetch(url) if self._fetch else await self._http_get(url)
            out.extend(parse_cdx_lines(text))
        return dedupe_candidates(out)

    async def _http_get(self, url: str) -> str:
        import httpx

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.text


async def backfill(
    plan: BackfillPlan,
    sink: FrontierSink,
    *,
    cc_client=None,
    cdx_client: WaybackCdxClient | None = None,
) -> BackfillStats:
    """Backfill both archive surfaces into one frontier sink (CC -> replay)."""
    from network.commoncrawl import CommonCrawlClient

    stats = BackfillStats()
    cdx = cdx_client or WaybackCdxClient()
    cdx_candidates = await cdx.captures(plan)
    stats.discovered_cdx = len(cdx_candidates)

    replay = None
    if plan.cc_prefixes:
        from historical.replay import HistoricalReplay

        cc = cc_client or CommonCrawlClient()
        replay = HistoricalReplay(sink, client=cc)
        cc_stats = await replay.run(plan.cc_prefixes, crawl=plan.cc_crawl)
        stats.discovered_cc = cc_stats.discovered
        stats.enqueued += cc_stats.enqueued
        stats.deduped += cc_stats.deduped

    merged = dedupe_candidates(cdx_candidates)
    stats.merged = len(merged)
    for candidate in merged:
        if sink.enqueue(candidate):
            stats.enqueued += 1
        else:
            stats.deduped += 1
    return stats