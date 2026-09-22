"""Nutch source onboarding (T100): bulk crawl backend."""

from __future__ import annotations

from adapters.registry import register

from .collect import adapt_nutch

register(
    "nutch",
    execution_class="bulk",
    capabilities={"bulk", "content-addressed"},
    adapter=adapt_nutch,
)