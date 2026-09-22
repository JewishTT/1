"""Scrapy exemplar onboarding (T096): register once, schedule adopts."""

from __future__ import annotations

from adapters.registry import register

from .stream import scrapy_crawl

register(
    "webpage",
    execution_class="http",
    capabilities={"http", "get"},
    adapter=scrapy_crawl,
)