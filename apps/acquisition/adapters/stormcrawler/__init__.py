"""StormCrawler source onboarding (T099): distributed streaming crawl engine."""

from __future__ import annotations

from adapters.registry import register

from .collect import adapt_stormcrawler

register(
    "stormcrawler",
    execution_class="custom",
    capabilities={"bulk", "warc"},
    adapter=adapt_stormcrawler,
)