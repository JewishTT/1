"""Headless JS render pipeline (T107).

A page is fetched statically, then rendered headlessly; the *leftover DOM*
(elements that only appear after script execution) is the signal that drives
re-observation. The pipeline is fully injectable so it runs hermetic in tests
and against Playwright/Crawlee in production.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Protocol
from urllib.parse import urljoin


@dataclass(frozen=True)
class ElementSignature:
    """Structural signature of a DOM element for diffing."""

    tag: str
    attrs: tuple[tuple[str, str], ...] = ()
    text: str = ""


class _SoupParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.elements: list[ElementSignature] = []
        self._tags: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        normalized = tuple(sorted((k, v or "") for k, v in attrs))
        self.elements.append(ElementSignature(tag=tag, attrs=normalized))
        self._tags.append(tag)

    def handle_startendtag(self, tag: str, attrs) -> None:
        normalized = tuple(sorted((k, v or "") for k, v in attrs))
        self.elements.append(ElementSignature(tag=tag, attrs=normalized))

    def handle_endtag(self, tag: str) -> None:
        if self._tags:
            self._tags.pop()

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text and self._tags:
            self.elements.append(ElementSignature(tag=self._tags[-1], text=text))


def parse_elements(html: str) -> list[ElementSignature]:
    parser = _SoupParser()
    parser.feed(html or "")
    return parser.elements


def leftover_dom(static_html: str, rendered_html: str) -> list[ElementSignature]:
    """Elements present only after rendering (the JS "leftover" surface)."""
    static = Counter(parse_elements(static_html))
    rendered = Counter(parse_elements(rendered_html))
    leftovers = rendered - static
    return sorted({e for e in leftovers.elements()}, key=lambda e: (e.tag, e.text, e.attrs))


class Fetcher(Protocol):
    async def fetch(self, url: str) -> bytes: ...


class Renderer(Protocol):
    async def render(self, url: str, static: bytes) -> str: ...


@dataclass
class RenderResult:
    """Outcome of a headless render pipeline run."""

    url: str
    static_bytes: bytes
    rendered_html: str
    leftovers: list[ElementSignature] = field(default_factory=list)
    asset_links: list[str] = field(default_factory=list)

    @property
    def js_leftover(self) -> bool:
        return bool(self.leftovers)


class NoopRenderer:
    """Renderer stub for hermetic tests / static-only deployments."""

    async def render(self, url: str, static: bytes) -> str:
        return static.decode("utf-8", errors="replace")


class HeadlessRenderPipeline:
    """Static fetch -> headless render -> leftover DOM extraction."""

    def __init__(self, fetcher: Fetcher, renderer: Renderer | None = None) -> None:
        self._fetcher = fetcher
        self._renderer = renderer or NoopRenderer()

    async def render(self, url: str, *, base: str | None = None) -> RenderResult:
        static = await self._fetcher.fetch(url)
        static_text = static.decode("utf-8", errors="replace")
        rendered = await self._renderer.render(url, static)
        leftovers = leftover_dom(static_text, rendered)
        links = self._asset_links(rendered, base or url)
        return RenderResult(
            url=url,
            static_bytes=static,
            rendered_html=rendered,
            leftovers=leftovers,
            asset_links=links,
        )

    def _asset_links(self, html: str, base: str) -> list[str]:
        links: list[str] = []

        class _LinkParser(HTMLParser):
            def handle_starttag(self, tag, attrs):
                for key, value in attrs:
                    if key in ("href", "src") and value:
                        links.append(urljoin(base, value))

        _LinkParser().feed(html)
        return links