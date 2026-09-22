"""Historical archive replay (T121, CC -> Frontier).

Common Crawl index hits are normalized into ``warc://`` Frontier candidates by
the shared client; the replay walks a set of prefix URLs in batches and hands
each deduplicated candidate to the Frontier sink. The sink contract is the only
dependency, so the replay runs in-process (hermetic), over the acquisition
adapter, or against the Postgres frontier identically.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from network.commoncrawl import DEFAULT_CRAWL, CommonCrawlClient


@dataclass
class ReplayStats:
    """Outcome of one replay run."""

    discovered: int = 0
    enqueued: int = 0
    deduped: int = 0
    batches: int = 0
    per_batch: list[dict] = field(default_factory=list)

    def merge(self, other: ReplayStats) -> ReplayStats:
        return ReplayStats(
            discovered=self.discovered + other.discovered,
            enqueued=self.enqueued + other.enqueued,
            deduped=self.deduped + other.deduped,
            batches=self.batches + other.batches,
            per_batch=self.per_batch + other.per_batch,
        )


class FrontierSink(Protocol):
    """Anything that accepts a candidate to collect (frontier/adapter)."""

    def enqueue(self, candidate: dict) -> bool: ...


class MemoryFrontierSink:
    """Hermetic sink: accepts unique ``uri`` candidates, dedups sqlite-style."""

    def __init__(self) -> None:
        self._seen: set[str] = set()
        self.enqueued: list[dict] = []

    def enqueue(self, candidate: dict) -> bool:
        if candidate.get("uri") in self._seen:
            return False
        self._seen.add(candidate.get("uri", ""))
        self.enqueued.append(candidate)
        return True

    @property
    def count(self) -> int:
        return len(self.enqueued)


class HistoricalReplay:
    """Discover Common Crawl candidates in batches and enqueue to a Frontier."""

    def __init__(
        self,
        sink: FrontierSink,
        *,
        client: CommonCrawlClient | None = None,
        batch_size: int = 100,
    ) -> None:
        self._sink = sink
        self._client = client or CommonCrawlClient()
        self._batch_size = max(1, batch_size)
        self._seen_uris: set[str] = set()

    async def discover_batch(
        self,
        prefix_url: str,
        *,
        crawl: str = DEFAULT_CRAWL,
        page: int | None = None,
    ) -> list[dict]:
        """One raw discovery batch (dedup happens at enqueue, not pagination)."""
        return await self._client.discover(prefix_url, crawl=crawl, page=page)

    async def run(self, prefixes: list[str], *, crawl: str = DEFAULT_CRAWL) -> ReplayStats:
        """Walk every prefix in batches, enqueueing novel candidates."""
        stats = ReplayStats()
        for prefix in prefixes:
            page = 0
            while True:
                hits = await self.discover_batch(prefix, crawl=crawl, page=page)
                if not hits:
                    break
                stats.batches += 1
                stats.discovered += len(hits)
                new_on_page = 0
                for hit in hits:
                    uri = hit.get("uri", "")
                    if uri in self._seen_uris:
                        stats.deduped += 1
                        continue
                    new_on_page += 1
                    self._seen_uris.add(uri)
                    if self._sink.enqueue(hit):
                        stats.enqueued += 1
                    else:
                        stats.deduped += 1
                stats.per_batch.append({"prefix": prefix, "page": page, "hits": len(hits)})
                if len(hits) < self._batch_size or new_on_page == 0:
                    break
                page += 1
        return stats

    @property
    def discovered_uris(self) -> set[str]:
        return set(self._seen_uris)