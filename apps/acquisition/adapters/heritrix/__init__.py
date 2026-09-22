"""Heritrix source onboarding (T096): archival WARC-first collection."""

from __future__ import annotations

from adapters.registry import register

from .collect import adapt_heritrix

register(
    "heritrix",
    execution_class="archival",
    capabilities={"warc", "range-read", "bulk"},
    adapter=adapt_heritrix,
)