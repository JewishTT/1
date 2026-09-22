"""Headless JS render pipeline (T107): leftover DOM, asset links."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))

from worker_browser.renderer import (  # noqa: E402
    HeadlessRenderPipeline,
    NoopRenderer,
    leftover_dom,
    parse_elements,
)

STATIC = b"<html><body><h1>Static</h1><p>skeleton</p></body></html>"
RENDERED = b"<html><body><h1>Static</h1><p>skeleton</p><div id='dyn'>Live</div></body></html>"


class FakeFetcher:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    async def fetch(self, url: str) -> bytes:
        return self._payload


class FakeRenderer:
    def __init__(self, html: str) -> None:
        self._html = html

    async def render(self, url: str, static: bytes) -> str:
        return self._html


def test_leftover_dom_finds_dynamic_elements() -> None:
    leftovers = leftover_dom(STATIC.decode(), RENDERED.decode())
    assert any(e.tag == "div" and "Live" in e.text for e in leftovers)
    assert not any(e.tag == "h1" for e in leftovers)


def test_leftover_dom_no_difference() -> None:
    assert leftover_dom(STATIC.decode(), STATIC.decode()) == []


def test_parse_elements_counts() -> None:
    elements = parse_elements(RENDERED.decode())
    tags = [e.tag for e in elements]
    assert "div" in tags
    assert "script" not in tags


async def test_pipeline_awaitable() -> None:
    pipeline = HeadlessRenderPipeline(FakeFetcher(STATIC), FakeRenderer(RENDERED.decode()))
    result = await pipeline.render("https://a.x/page")
    assert result.js_leftover is True
    assert any(e.tag == "div" for e in result.leftovers)


async def test_pipeline_noop_renderer_static_only() -> None:
    pipeline = HeadlessRenderPipeline(FakeFetcher(STATIC), NoopRenderer())
    result = await pipeline.render("https://a.x/")
    assert result.js_leftover is False


def test_asset_links_resolved() -> None:
    html = "<a href='/about'>A</a><script src='app.js'></script>"
    pipeline = HeadlessRenderPipeline(FakeFetcher(STATIC), FakeRenderer(html))
    links = pipeline._asset_links(html, "https://a.x/page")
    assert "https://a.x/about" in links
    assert "https://a.x/app.js" in links