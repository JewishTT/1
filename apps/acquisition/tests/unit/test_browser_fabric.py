"""Browser work-cluster fabric (T105): assignment, overlay, visibility."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))

from worker_browser.fabric import (  # noqa: E402
    Assignment,
    BrowserCluster,
    BrowserNode,
    CoverageOverlay,
    host_of,
    region_of,
)

REGIONS = {".ru": "emea", ".jp": "apac", "example.com": "amer"}


def test_host_of_variants() -> None:
    assert host_of("https://Example.com/x?y=1") == "example.com"
    assert host_of("http://a.b.ru/p") == "a.b.ru"
    assert host_of("ftp://c.d/e") == "c.d"


def test_region_of_suffix_mapping() -> None:
    assert region_of("https://bbc.ru/news", REGIONS) == "emea"
    assert region_of("http://x.example.com/a", REGIONS) == "amer"
    assert region_of("https://other.org/1", REGIONS) == "global"


def test_region_pinned_assignment() -> None:
    cluster = BrowserCluster(
        [
            BrowserNode("n-eu", region="emea", max_tabs=2),
            BrowserNode("n-jp", region="apac", max_tabs=2),
            BrowserNode("n-global", region="global", max_tabs=8),
        ]
    )
    assignment = cluster.assign(["https://a.ru/1", "https://b.ru/2"], region_map=REGIONS)
    assert set(assignment.page_to_node.values()) == {"n-eu"}
    assert not assignment.rejected


def test_load_balanced_fill() -> None:
    nodes = [BrowserNode(f"n{i}", region="global", max_tabs=2) for i in range(2)]
    cluster = BrowserCluster(nodes)
    assignment = cluster.assign([f"https://h{i}.x/" for i in range(4)])
    assert len(assignment.rejected) == 0
    counts = [len(assignment.node_to_pages.get(n.node_id, [])) for n in nodes]
    assert sorted(counts) == [2, 2]


def test_over_capacity_rejects() -> None:
    cluster = BrowserCluster([BrowserNode("n1", region="global", max_tabs=1)])
    assignment = cluster.assign(["https://a.x/", "https://b.x/"])
    assert len(assignment.rejected) == 1


def test_overlay_visibility_accounting() -> None:
    cluster = BrowserCluster(
        [
            BrowserNode("n-js", region="global", max_tabs=8, js_enabled=True),
            BrowserNode("n-plain", region="global", max_tabs=8, js_enabled=False),
        ]
    )
    assignment = cluster.assign(
        [
            "https://a.ru/1",
            "https://b.ru/2",
            "https://plain.ru/x",
            "https://plain.ru/y",
        ],
        region_map=REGIONS,
    )
    overlay = CoverageOverlay(cluster, region_map=REGIONS).record(assignment)
    region = overlay.region("global")
    assert region is not None
    assert "a.ru" in region.hosts
    snapshot = overlay.snapshot()
    assert snapshot["global"]["rendered"] >= 2
    assert 0.0 < snapshot["global"]["visibility"] <= 1.0
    assert overlay.node_of("https://a.ru/1") == "n-js"


def test_assignment_is_deterministic() -> None:
    pages = [f"https://h{i}.x/" for i in range(10)]
    results = []
    for _ in range(2):
        nodes = [BrowserNode("n1", region="global"), BrowserNode("n2", region="global")]
        cluster = BrowserCluster(nodes)
        results.append(cluster.assign(pages, region_map={}).page_to_node)
    assert results[0] == results[1]


def test_empty_assignment_rejected() -> None:
    assignment = Assignment()
    assert assignment.rejected == []