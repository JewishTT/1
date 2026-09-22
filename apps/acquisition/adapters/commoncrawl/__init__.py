"""Common Crawl index source onboarding (T092/T102)."""

from __future__ import annotations

from adapters.registry import register

from .index import discover

register(
    "commoncrawl",
    execution_class="archival",
    capabilities={"warc", "range-read", "bulk"},
    adapter=discover,
)