"""Browsertrix source onboarding (T098): browser worker pool (JS/DOM)."""

from __future__ import annotations

from adapters.registry import register

from .collect import adapt_browsertrix

register(
    "browsertrix",
    execution_class="browser",
    capabilities={"javascript", "dom", "warc", "bulk", "screenshot"},
    adapter=adapt_browsertrix,
)