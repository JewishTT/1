"""L0 transport: raw Common Crawl capture-index records (CC-TEMPORALITY v1).

The zero layer only *moves* index records — no entity knowledge, no
timestamp normalization (that is L1 ``cc_extract``), no WARC fetching
(index rows only). Input primitives (``url_query`` / ``match_type`` /
``surt_prefix``) come from the L1 plan; L0 never sees ``CcQueryPlan``.

Determinism contract (I-11, mirrored from ``cc_session``): same index
slice + same query ⇒ same ordered ``RawCapture`` list. Records are
ordered by capture identity before transport-level capture dedup, so
output order is stable regardless of upstream row order. Content digest
is deliberately not a dedup key: the same payload at two fetch times is
two temporal observations.

Content addressing (I-1): every transport record derives a deterministic
``capture_id`` from its capture/locator identity, not from content alone.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from typing import Protocol

from network.cc_session import CcIndexSession, CCPageRecord


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
    warc_filename: str = ""
    offset: int = 0
    crawl: str = ""
    subset: str = ""
    warc_record_id: str = ""

    @property
    def locator(self) -> str:
        """Byte-exact WARC provenance for the corresponding capture."""
        return f"{self.warc_filename}@{self.offset},{self.length}"

    @property
    def capture_identity(self) -> tuple[str, str, str, str, str, int, int, str]:
        """Identity of a capture, independent of content digest.

        Identical payloads at different fetch times or WARC locations remain
        separate temporal observations. The filename and offset/length are
        part of the identity because they identify the immutable byte range.
        """
        return (
            self.crawl or self.collection,
            self.subset,
            self.url,
            self.timestamp,
            self.warc_filename,
            self.offset,
            self.length,
            self.warc_record_id,
        )

    @property
    def capture_id(self) -> str:
        """Content-addressed transport id for this capture, not its payload."""
        material = json.dumps(
            {
                "capture_identity": self.capture_identity,
                "warc_filename": self.warc_filename,
                "length": self.length,
                "warc_record_id": self.warc_record_id,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
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
            "crawl": self.crawl or self.collection,
            "subset": self.subset,
            "warc_filename": self.warc_filename,
            "offset": self.offset,
            "warc_record_id": self.warc_record_id,
            "locator": self.locator,
            "capture_id": self.capture_id,
        }


class IndexSession(Protocol):
    """Minimal session seam L0 pulls through (``CcIndexSession`` fits)."""

    def query_domain(self, url_pattern: str) -> list[CCPageRecord]: ...


class ByteTransport(Protocol):
    """Injectable CC WARC range transport."""

    async def fetch(self, filename: str, offset: int, length: int) -> bytes: ...


def _default_session() -> CcIndexSession:
    """Live session built by L0 itself (only when no session is injected)."""
    index_path = os.environ.get("CC_INDEX_PATH", "")
    if not index_path:
        raise RuntimeError(
            "CC_INDEX_PATH is not set: cannot build a live CcIndexSession. "
            "Point CC_INDEX_PATH at a CC URL-index parquet slice, or inject "
            "a session (hermetic tests use a fake session)."
        )
    return CcIndexSession(
        index_path=index_path,
        crawl=os.environ.get("CC_CRAWL", ""),
        subset=os.environ.get("CC_SUBSET", ""),
    )


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
    the L1 plan. The concrete index session may use the SURT prefix and
    crawl/subset partition; legacy fake sessions remain supported.

    Semantics:
      - one deterministic ``query_domain`` pass over the selected index slice;
      - ``prefix`` keeps only the URL subtree after scheme/www normalization;
      - records are sorted by capture identity and duplicate *captures* are
        removed, while equal content digests at different times remain;
      - the returned records retain WARC locator and partition provenance;
      - ``session=None`` builds a live session from ``CC_INDEX_PATH``.
    """
    if page_size <= 0:
        raise ValueError("page_size must be a positive batch size")
    if limit <= 0:
        return []
    if not url_query or not url_query.strip():
        return []

    sess = session if session is not None else _default_session()
    query = url_query.strip().rstrip("/")
    try:
        records = sess.query_domain(
            query, surt_prefix=surt_prefix, match_type=match_type
        )
    except TypeError:
        # Legacy injected sessions predate the optional planning arguments.
        records = sess.query_domain(query)

    if match_type == "prefix":
        prefix = _url_key(url_query)
        records = [r for r in records if _url_key(r.url).startswith(prefix)]

    ordered = sorted(
        records,
        key=lambda r: (
            r.url,
            r.timestamp,
            getattr(r, "crawl", "") or "",
            getattr(r, "subset", "") or "",
            getattr(r, "warc_filename", "") or "",
            int(getattr(r, "offset", 0) or 0),
            int(getattr(r, "length", 0) or 0),
            r.digest,
        ),
    )

    out: list[RawCapture] = []
    seen_captures: set[tuple[object, ...]] = set()
    for rec in ordered:
        capture = RawCapture(
            url=rec.url,
            timestamp=rec.timestamp,
            digest=rec.digest,
            status=int(rec.status),
            mime=rec.mime,
            length=int(rec.length),
            collection=getattr(rec, "crawl", "") or getattr(sess, "crawl", "") or "",
            warc_filename=getattr(rec, "warc_filename", "") or "",
            offset=int(getattr(rec, "offset", 0) or 0),
            crawl=getattr(rec, "crawl", "") or "",
            subset=getattr(rec, "subset", "") or "",
            warc_record_id=getattr(rec, "warc_record_id", "") or "",
        )
        if capture.capture_identity in seen_captures:
            continue
        seen_captures.add(capture.capture_identity)
        out.append(capture)
        if len(out) >= limit:
            break
    return out


__all__ = ["IndexSession", "RawCapture", "pull_capture_index"]
