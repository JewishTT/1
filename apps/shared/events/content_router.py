"""Content router + dedup (T030, FR-007, R-6).

MIME detection, size validation, hashing, and request/canonical-url/exact-hash
dedup. Conditional acquisition (ETag/Last-Modified) is honoured so unchanged
content yields `observation.unchanged` rather than re-parse (SC-006).
"""

from __future__ import annotations

import hashlib


class OversizedContentError(Exception):
    pass


class ContentRouter:
    """Classifies + validates fetched content before storage/dedup."""

    def __init__(self, *, max_bytes: int = 10 * 1024 * 1024) -> None:
        self._max_bytes = max_bytes

    @staticmethod
    def sha256(body: bytes) -> str:
        return hashlib.sha256(body).hexdigest()

    @staticmethod
    def canonical_url(url: str) -> str:
        """Canonicalize a URL for request-level dedup (lowercase scheme/host, strip fragment)."""
        lowered = url.strip().lower()
        if "#" in lowered:
            lowered = lowered.split("#", 1)[0]
        return lowered

    def sniff_mime(self, body: bytes, fallback: str | None = None) -> str:
        if body.startswith(b"%PDF"):
            return "application/pdf"
        if body.lstrip().startswith(b"<"):
            return "text/html"
        if b"<urlset" in body[:2048]:
            return "application/xml"  # sitemap
        if b"<rss" in body[:2048] or b"<feed" in body[:2048]:
            return "application/rss+xml"
        if fallback:
            return fallback
        return "application/octet-stream"

    def validate_content(self, body: bytes) -> None:
        if len(body) > self._max_bytes:
            raise OversizedContentError(
                f"content {len(body)} bytes exceeds max {self._max_bytes} (FR-029 size cap)"
            )

    def classify(self, body: bytes, *, url: str, headers: dict | None = None) -> dict:
        """Return routing metadata: hash, mime, etag, last_modified, size, canonical_url."""
        self.validate_content(body)
        etag = (headers or {}).get("etag")
        last_modified = (headers or {}).get("last-modified")
        return {
            "sha256": self.sha256(body),
            "content_type": self.sniff_mime(body),
            "size": len(body),
            "canonical_url": self.canonical_url(url),
            "etag": etag,
            "last_modified": last_modified,
        }


class RequestDedupKey:
    """Request / canonical-url / exact-hash dedup keys for the dedup store (FR-007)."""

    @staticmethod
    def exact_hash(sha256: str) -> str:
        return f"dedup:hash:{sha256}"

    @staticmethod
    def canonical_url(url: str) -> str:
        return f"dedup:url:{ContentRouter.canonical_url(url)}"

    @staticmethod
    def request_url(url: str) -> str:
        return f"dedup:req:{url}"