"""DiscoveryRegistry durable-enqueue count and hard-cap contracts."""

from __future__ import annotations

from adapters.discovery.contracts import Candidate, candidates_from_urls
from adapters.discovery.registry import DiscoveryRegistry, InMemoryFrontierSink


class _PublicIndex:
    name = "public-index"
    capabilities = frozenset({"index"})

    def discover(self, query: str) -> list[Candidate]:
        return candidates_from_urls(
            [
                "https://example.org/a",
                "https://example.org/b",
                "https://example.org/a#duplicate",
            ],
            source=self.name,
            method="fixture-index",
            query=query,
        )


def _registry() -> DiscoveryRegistry:
    registry = DiscoveryRegistry()
    registry.register(_PublicIndex())
    return registry


def test_enqueued_counts_only_new_frontier_inserts() -> None:
    registry = _registry()
    frontier = InMemoryFrontierSink()
    first = registry.discover(
        "example.org", frontier=frontier, tenant_id="tenant-a", investigation_id="inv-a"
    )
    second = registry.discover(
        "example.org", frontier=frontier, tenant_id="tenant-a", investigation_id="inv-a"
    )
    assert first.candidates_found == 2
    assert first.enqueued == 2
    assert second.candidates_found == 2
    assert second.enqueued == 0
    assert len(frontier.items) == 2


def test_enqueue_cap_is_explicit_and_does_not_rewrite_found_count() -> None:
    registry = _registry()
    frontier = InMemoryFrontierSink()
    report = registry.discover(
        "example.org", frontier=frontier, tenant_id="tenant-a",
        investigation_id="inv-a", max_enqueues=1,
    )
    assert report.candidates_found == 2
    assert report.enqueued == 1
    assert report.candidates_enqueue_capped is True
    assert len(frontier.items) == 1
