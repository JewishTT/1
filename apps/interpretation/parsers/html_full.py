"""Main-text parser adapter: trafilatura readability extraction (spec 007, T008/T010).

Wraps trafilatura (LGPL-3.0, pinned dep, unmodified) behind the ParserAdapter
seam. ``parse`` yields boilerplate-free text findings with byte offsets;
``extract`` additionally returns an ``ExtractionResult`` carrying clean
segments (navigation/footer excluded), the detected charset and a heuristic
language hint. Deterministic: same artifact → same segments; no network.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import trafilatura  # type: ignore[import-not-found]

from extractors.language import decode_bytes, detect_language
from extractors.types import ExtractionResult
from parsers.registry import Finding, Segment


@dataclass
class HtmlFullAdapter:
    name: str = "html_full"
    content_types: tuple[str, ...] = ("text/html", "application/xhtml+xml")

    _HTML_MARKERS = ("<html", "<!doctype html", "<head", "<body", "<div", "<p")

    def can_parse(self, artifact) -> bool:
        text = _to_text(artifact).lower()
        if not text:
            return False
        return any(marker in text for marker in self._HTML_MARKERS)

    def parse(self, artifact) -> list[Finding]:
        segments = self._segments(artifact)
        return [
            Finding(kind="text", value=s.text, offset=s.offset, meta=s.meta)
            for s in segments
        ]

    def extract(self, artifact) -> ExtractionResult:
        raw = _to_bytes(artifact)
        text, encoding = decode_bytes(raw)
        segments = self._segments_from_text(text, encoding)
        lang = detect_language(" ".join(s.text for s in segments)) if segments else None
        body_segments = [
            Segment(
                text=s.text,
                offset=s.offset,
                lang_hint=lang,
                kind=s.kind,
                meta=s.meta,
            )
            for s in segments
        ]
        return ExtractionResult(
            artifact_sha=hashlib.sha256(raw).hexdigest(),
            content_type="text/html",
            segments=body_segments,
            mentions=[],
        )

    # -- internals ---------------------------------------------------------
    def _segments(self, artifact) -> list[Segment]:
        text, encoding = decode_bytes(_to_bytes(artifact))
        return self._segments_from_text(text, encoding)

    def _segments_from_text(self, text: str, encoding: str) -> list[Segment]:
        main_text = trafilatura.extract(
            text,
            include_comments=False,
            include_tables=True,
            include_links=False,
            favor_recall=True,
            output_format="txt",
        )
        if not main_text:
            return []
        paragraphs = [p.strip() for p in main_text.split("\n") if p.strip()]
        segments: list[Segment] = []
        for i, paragraph in enumerate(paragraphs):
            offset = _locate(paragraph, text)
            segments.append(
                Segment(
                    text=paragraph,
                    offset=offset,
                    kind="text",
                    meta={"parser": "trafilatura", "charset": encoding, "paragraph": i},
                )
            )
        return segments


def _locate(paragraph: str, text: str) -> int:
    """Deterministic byte offset of a cleaned paragraph in the decoded text."""
    probe = " ".join(paragraph.split()[:4])
    idx = text.find(probe)
    if idx < 0 and probe:
        token = probe.split()[0]
        idx = text.find(token)
    if idx < 0:
        return 0
    return len(text[:idx].encode("utf-8"))


def _to_text(artifact) -> str:
    return _to_bytes(artifact).decode("utf-8", errors="replace")


def _to_bytes(artifact) -> bytes:
    if isinstance(artifact, (bytes, bytearray)):
        return bytes(artifact)
    if isinstance(artifact, str):
        return artifact.encode("utf-8")
    return getattr(artifact, "body", b"").encode("utf-8") if hasattr(artifact, "body") else b""