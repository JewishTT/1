"""WARC/archive source onboarding (T093)."""

from __future__ import annotations

from adapters.registry import register

from .collect import adapt_warc

register(
    "webarchive",
    execution_class="archival",
    capabilities={"warc", "range-read"},
    adapter=adapt_warc,
)