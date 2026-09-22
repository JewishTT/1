"""Dataset worker onboarding (T094): parquet/bulk/range-read sources."""

from __future__ import annotations

from adapters.registry import register

from .acquire import acquire

register(
    "dataset",
    execution_class="dataset",
    capabilities={"parquet", "bulk", "range-read"},
    adapter=acquire,
)