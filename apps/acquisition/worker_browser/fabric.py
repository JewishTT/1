"""Browser work-cluster fabric (T105): cluster topology + coverage overlay.

A *browser cluster* is the SS/Collusion-style set of regional browser nodes
(Worker Browser, Browsertrix, Playwright farms). The overlay answers "which
node renders which host surface" and tracks how much of a region's visible
surface is actually covered by JS-capable nodes. Assignment is deterministic,
load-balanced, and region-pinned.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_HOST_RE = re.compile(r"^(?:[a-z]+://)?([^/:?#]+)")


def host_of(url: str) -> str:
    """Best-effort host extraction from a URL."""
    match = _HOST_RE.match(url or "")
    return match.group(1).lower() if match else (url or "").lower()


def region_of(host: str, region_map: dict[str, str] | None = None) -> str:
    """Map a host to a region; default region is ``global``.

    Suffixes starting with ``.`` match the exact parent domain; bare suffixes
    also match subdomains (``example.com`` covers ``x.example.com``).
    """
    host = host_of(host)
    if region_map:
        for suffix, region in region_map.items():
            if suffix.startswith("."):
                if host.endswith(suffix):
                    return region
            elif host == suffix or host.endswith("." + suffix):
                return region
    return "global"


@dataclass
class BrowserNode:
    """A single browser node (browser_instance_id) in the cluster."""

    node_id: str
    region: str = "global"
    max_tabs: int = 8
    js_enabled: bool = True
    tabs: int = 0

    def can_take(self) -> bool:
        return self.tabs < self.max_tabs

    def assign(self) -> None:
        self.tabs += 1

    def release(self, count: int = 1) -> None:
        self.tabs = max(0, self.tabs - count)

    @property
    def free(self) -> int:
        return max(0, self.max_tabs - self.tabs)


@dataclass
class CoverageRegion:
    """Coverage bookkeeping for one region inside the overlay."""

    region: str
    hosts: set[str] = field(default_factory=set)
    pages: list[str] = field(default_factory=list)
    rendered: int = 0  # pages assigned to a JS-capable node

    def add(self, host: str, page: str, js: bool) -> None:
        self.hosts.add(host)
        self.pages.append(page)
        if js:
            self.rendered += 1

    @property
    def visible_surface(self) -> tuple[str, ...]:
        return tuple(sorted(self.hosts))

    @property
    def visibility_ratio(self) -> float:
        """Fraction of assigned pages rendered on a JS-capable node."""
        if not self.pages:
            return 1.0
        return self.rendered / len(self.pages)


@dataclass
class Assignment:
    """Deterministic result of assigning pages to cluster nodes."""

    page_to_node: dict[str, str] = field(default_factory=dict)
    node_to_pages: dict[str, list[str]] = field(default_factory=dict)
    rejected: list[str] = field(default_factory=list)


class BrowserCluster:
    """Regional browser cluster with load-aware page assignment."""

    def __init__(self, nodes: list[BrowserNode]) -> None:
        if not nodes:
            raise ValueError("cluster needs at least one node")
        self._nodes = {n.node_id: n for n in nodes}

    @property
    def nodes(self) -> list[BrowserNode]:
        return list(self._nodes.values())

    def node(self, node_id: str) -> BrowserNode:
        return self._nodes[node_id]

    def _pick(self, page: str, region_map: dict[str, str] | None) -> BrowserNode | None:
        """Node in the page's region with most free tabs (region-pinned)."""
        host = host_of(page)
        region = region_of(host, region_map)
        candidates = [n for n in self._nodes.values() if n.region == region and n.can_take()]
        if not candidates:
            candidates = [n for n in self._nodes.values() if n.can_take()]
        if not candidates:
            return None
        return max(candidates, key=lambda n: n.free)

    def assign(
        self,
        pages: list[str],
        *,
        region_map: dict[str, str] | None = None,
    ) -> Assignment:
        """Distribute pages onto nodes: load-balanced, region-pinned."""
        result = Assignment()
        for page in pages:
            node = self._pick(page, region_map)
            if node is None:
                result.rejected.append(page)
                continue
            node.assign()
            result.page_to_node[page] = node.node_id
            result.node_to_pages.setdefault(node.node_id, []).append(page)
        return result


class CoverageOverlay:
    """SS/Collusion cluster <-> coverage overlay (visibility accounting).

    The overlay is folded from a cluster :class:`Assignment` so page->node
    bindings are exactly what the cluster decided (no separate routing order).
    """

    def __init__(
        self,
        cluster: BrowserCluster,
        *,
        region_map: dict[str, str] | None = None,
    ) -> None:
        self._cluster = cluster
        self._region_map = region_map or {}
        self._regions: dict[str, CoverageRegion] = {}
        self._page_node: dict[str, str] = {}

    def record(self, assignment: Assignment) -> CoverageOverlay:
        """Fold an assignment into the coverage overlay."""
        for page, node_id in assignment.page_to_node.items():
            node = self._cluster.node(node_id)
            region = node.region
            coverage = self._regions.setdefault(region, CoverageRegion(region))
            coverage.add(host_of(page), page, js=node.js_enabled)
            self._page_node[page] = node_id
        return self

    def region(self, name: str) -> CoverageRegion | None:
        return self._regions.get(name)

    def node_of(self, page: str) -> str | None:
        return self._page_node.get(page)

    def snapshot(self) -> dict[str, object]:
        """Overlay snapshot: per-region hosts, page counts, visibility."""
        return {
            region: {
                "hosts": sorted(cov.hosts),
                "pages": len(cov.pages),
                "rendered": cov.rendered,
                "visibility": round(cov.visibility_ratio, 4),
            }
            for region, cov in sorted(self._regions.items())
        }