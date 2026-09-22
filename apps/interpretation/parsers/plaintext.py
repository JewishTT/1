"""Plain-text adapter for the deterministic lane (spec 007, US1/US2).

US1 takes plain-text biographies ("Иванов, Сергей Петрович родился в
Казани…"); the extraction lane therefore needs a *conservative* plain-text
claim: UTF-8-decodable, no binary magic, no NUL bytes, and no HTML markers
(those go to ``html_full``/``structured`` instead of producing raw-markup
segments). Never guesses on binary or encoded pages.
"""

from __future__ import annotations

import hashlib

from extractors.language import decode_bytes
from extractors.types import ExtractionResult
from parsers.registry import Finding, Segment

_BINARY_MAGICS = (
    b"%PDF-",
    b"\x89PNG",
    b"\xff\xd8",
    b"GIF8",
    b"PK\x03\x04",
    b"II*\x00",
    b"MM\x00*",
    b"\x7fELF",
    b"MZ",
)
_HTML_MARKERS = ("<html", "<head", "<body", "<!doctype html", "<article", "<main", "<div")


class PlainTextAdapter:
    name = "plaintext"
    content_types: tuple[str, ...] = ("text/plain", "text/markdown", "text/x-log")

    def can_parse(self, artifact) -> bool:
        raw = _to_bytes(artifact)
        if not raw:
            return False
        if raw.startswith(tuple(b for b in _BINARY_MAGICS if b)):
            return False
        if b"\x00" in raw[:4096]:
            return False
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            return False
        head = text[:2048].lower()
        if any(marker in head and marker in text.lower()[:2048] for marker in _HTML_MARKERS):
            return False
        return bool(text.strip())

    def extract(self, artifact) -> ExtractionResult:
        raw = _to_bytes(artifact)
        text, charset = decode_bytes(raw)
        return ExtractionResult(
            artifact_sha=hashlib.sha256(raw).hexdigest(),
            content_type="text/plain",
            segments=[Segment(text=text, offset=0, kind="text", meta={"parser": "charset", "charset": charset})],
            mentions=[],
        )

    def parse(self, artifact) -> list[Finding]:
        result = self.extract(artifact)
        return [
            Finding(kind=s.kind, value=s.text, offset=s.offset, meta={"parser": "plaintext"})
            for s in result.segments
        ]


def _to_bytes(artifact) -> bytes:
    if isinstance(artifact, (bytes, bytearray)):
        return bytes(artifact)
    if isinstance(artifact, str):
        return artifact.encode("utf-8")
    return b""