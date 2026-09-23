"""L0 transport: raw Common Crawl capture-index records (CC-TEMPORALITY v1).

The zero layer only *moves* index records — no entity knowledge, no
timestamp normalization (that is L1 ``cc_extract``), no WARC fetching
(index rows only). Input primitives (``url_query`` / ``match_type`` /
``surt_prefix``) come from the L1 plan; L0 never sees ``CcQueryPlan``.

Determinism contract (I-11, mirrored from ``cc_session``): same index
slice + same query ⇒ same ordered ``RawCapture`` list. Records are
ordered by ``(url, timestamp, digest)`` before transport-level digest
dedup, so output order is stable regardless of upstream row order.

Content addressing (I-1): every transport record derives a deterministic
``capture_id`` (``evt-<sha256>``) from its immutable content, so a replay
of the same index slice yields byte-identical records — the address the
``cc.captures_pulled`` event carries (refs-only, I-5).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from typing import Protocol

from network.cc_session import CCPageRecord, CcIndexSession


@dataclass(frozen=True)
class RawCapture:
    """One raw CC index row (transport record — no interpretation)."""

    url: str
    timestamp: str  # 14-digit CC timestamp, verbatim from the index
    digest: str
    status: int
    mime: str
    length: int
    collection: str

    @property
    def capture_id(self) -> str:
        """Content-addressed transport record id (I-1): deterministic per row."""
        material = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return "evt-" + hashlib.sha256(material.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "timestamp": self.timestamp,
            "digest": self.digest,
            "status": self.status,
            "mime": self.mime,
            "length": self.length,
            "collection": self.collection,
        }


class IndexSession(Protocol):
    """Minimal session seam L0 pulls through (``CcIndexSession`` fits)."""

    def query_domain(self, url_pattern: str) -> list[CCPageRecord]: ...


def _default_session() -> CcIndexSession:
    """Live session built by L0 itself (only when no session is injected)."""
    index_path = os.environ.get("CC_INDEX_PATH", "")
    if not index_path:
        raise RuntimeError(
            "CC_INDEX_PATH is not set: cannot build a live CcIndexSession. "
            "Point CC_INDEX_PATH at a CC URL-index parquet slice, or inject "
            "a session (hermetic tests use a fake session)."
        )
    return CcIndexSession(index_path=index_path)


_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")
_WWW_RE = re.compile(r"^www\.(?=[^/])")


def _url_key(url: str) -> str:
    """Deterministic scheme/www-stripped key used only for prefix filtering."""
    s = _SCHEME_RE.sub("", url.strip())
    s = _WWW_RE.sub("", s)
    return s.rstrip("/").lower()


def pull_capture_index(
    url_query: str,
    match_type: str,
    surt_prefix: str | None,
    limit: int = 50,
    session: IndexSession | None = None,
    page_size: int = 5,
) -> list[RawCapture]:
    """Pull raw capture-index rows for a query primitive (L0 transport only).

    ``url_query``/``match_type``/``surt_prefix`` are opaque primitives from
    the L1 plan — L0 neither builds nor interprets plans. ``surt_prefix`` is
    accepted for contract symmetry and is deliberately not used as a filter:
    the index session matches on plain URLs, and normalizing to surt would
    be interpretation (L1's job).

    Semantics:
      - single ``query_domain`` pass over the index slice (no WARC pulls);
      - ``match_type == "prefix"`` keeps only rows whose stripped URL starts
        with ``url_query`` (deterministic, case-insensitive on the stripped
        key); ``"domain"`` applies no extra filter;
      - records sorted by ``(url, timestamp, digest)`` — stable order;
      - digest dedup keeps the first row per digest in that order;
      - emission walks records in batches of ``page_size`` and stops as soon
        as ``limit`` raw captures are collected;
      - ``session=None`` builds a live ``CcIndexSession`` from CC_INDEX_PATH.
    """
    if page_size <= 0:
        raise ValueError("page_size must be a positive batch size")
    if limit <= 0:
        return []
    if not url_query or not url_query.strip():
        return []

    sess = session if session is not None else _default_session()
    records = sess.query_domain(url_query.strip().rstrip("/"))

    if match_type == "prefix":
        prefix = _url_key(url_query)
        records = [r for r in records if _url_key(r.url).startswith(prefix)]

    ordered = sorted(records, key=lambda r: (r.url, r.timestamp, r.digest))
    collection = getattr(sess, "crawl", "") or ""

    out: list[RawCapture] = []
    seen_digests: set[str] = set()
    for start in range(0, len(ordered), page_size):
        for rec in ordered[start : start + page_size]:
            if rec.digest in seen_digests:
                continue
            seen_digests.add(rec.digest)
            out.append(
                RawCapture(
                    url=rec.url,
                    timestamp=rec.timestamp,
                    digest=rec.digest,
                    status=int(rec.status),
                    mime=rec.mime,
                    length=int(rec.length),
                    collection=collection,
                )
            )
            if len(out) >= limit:
                return out
    return out


__all__ = ["IndexSession", "RawCapture", "pull_capture_index"]
