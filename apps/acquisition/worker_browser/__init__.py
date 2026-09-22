"""Browser work-cluster fabric (T105) and headless render pipeline (T107)."""

from __future__ import annotations

from .fabric import (
    Assignment,
    BrowserCluster,
    BrowserNode,
    CoverageOverlay,
    CoverageRegion,
    host_of,
    region_of,
)
from .renderer import (
    ElementSignature,
    Fetcher,
    HeadlessRenderPipeline,
    NoopRenderer,
    Renderer,
    RenderResult,
    leftover_dom,
    parse_elements,
)

__all__ = [
    "Assignment",
    "BrowserCluster",
    "BrowserNode",
    "CoverageOverlay",
    "CoverageRegion",
    "ElementSignature",
    "Fetcher",
    "HeadlessRenderPipeline",
    "NoopRenderer",
    "RenderResult",
    "Renderer",
    "host_of",
    "leftover_dom",
    "parse_elements",
    "region_of",
]