"""Common Crawl index adapter (T092) — re-exports the shared network module (T102)."""

from __future__ import annotations

from network.commoncrawl import (
    DEFAULT_CRAWL,
    build_index_url,
    crawl_badge,
    parse_index_lines,
    select_latest,
)


async def discover(task: dict, *, http_get=None) -> dict:
    """Adapter callable: query the index and produce candidate Frontier items."""
    url = task.get("url") or task.get("uri")
    if not url:
        raise ValueError("task requires 'url' to query the index")
    from network.commoncrawl import CommonCrawlClient

    client = CommonCrawlClient()
    if callable(http_get):
        client._transport = http_get  # test seam, mirrors the T092 stub
    candidates = await client.discover(
        url,
        crawl=task.get("cc_index", DEFAULT_CRAWL),
        index_url=task.get("index_url"),
    )
    return {
        "task_id": task.get("task_id", ""),
        "candidates": candidates,
        "reservoir": f"commoncrawl:{task.get('cc_index', DEFAULT_CRAWL)}",
        "candidate_count": len(candidates),
        "adapted_fits": all(
            c["uri"].startswith(("http://", "https://", "s3://")) and c["length"] > 0
            for c in candidates
        ),
    }


__all__ = [
    "DEFAULT_CRAWL",
    "build_index_url",
    "crawl_badge",
    "discover",
    "parse_index_lines",
    "select_latest",
]