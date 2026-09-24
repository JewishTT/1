"""Raw CC capture records -> normalized observations (L1, CC-TEMPORALITY v1).

Pure functions only: no network, no global state. Accepts ``Mapping`` records
(never L0 types — layer boundary). CC 14-digit timestamps
(``YYYYMMDDhhmmss``) are converted to ISO-UTC. Output is sorted by
``observed_at`` and deduplicated by ``(digest, observed_at)`` — deterministic
(first occurrence wins), streaming-friendly (one pass, O(1) per record).

Content addressing (I-1): ``record_hash``/``record_id`` are deterministic
functions of the immutable capture identity and content metadata. Replays
therefore produce byte-identical records, while captures at different fetch
times remain distinct temporal observations.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

__all__ = ["CaptureObservation", "iso_utc_from_cc_timestamp", "normalize_captures"]


@dataclass(frozen=True)
class CaptureObservation:
    """A single normalized capture observation ready for L2 series projection.

    Content-addressed (I-1): ``record_hash``/``record_id`` are deterministic
    functions of the immutable fields — replay-safe, never fabricated.
    """

    url: str
    observed_at: str  # ISO-UTC, e.g. "2023-10-12T00:00:00Z"
    status: int
    digest: str
    crawl: str = ""
    subset: str = ""
    warc_filename: str = ""
    offset: int = 0
    length: int = 0
    warc_record_id: str = ""

    @property
    def locator(self) -> str:
        return f"{self.warc_filename}@{self.offset},{self.length}"

    @property
    def record_hash(self) -> str:
        """Deterministic sha256 over the immutable observation content."""
        material = json.dumps(
            {
                "url": self.url,
                "observed_at": self.observed_at,
                "status": self.status,
                "digest": self.digest,
                "crawl": self.crawl,
                "subset": self.subset,
                "warc_filename": self.warc_filename,
                "offset": self.offset,
                "length": self.length,
                "warc_record_id": self.warc_record_id,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    @property
    def record_id(self) -> str:
        """Content-addressed record id (``evt-<record_hash>``), I-1/I-11."""
        return f"evt-{self.record_hash}"


def iso_utc_from_cc_timestamp(timestamp: str) -> str | None:
    """CC 14-digit timestamp -> ISO-UTC, or None if not parseable.

    Deterministic: ``"20231012000000"`` -> ``"2023-10-12T00:00:00Z"``.
    """
    value = timestamp.strip()
    if len(value) != 14 or not value.isdigit():
        return None
    return (
        f"{value[0:4]}-{value[4:6]}-{value[6:8]}"
        f"T{value[8:10]}:{value[10:12]}:{value[12:14]}Z"
    )


def _as_int(value: object) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return 0


def normalize_captures(
    raw: Iterable[Mapping[str, object]],
) -> list[CaptureObservation]:
    """Normalize raw capture ``Mapping`` records into sorted, deduped observations.

    - CC 14-digit ``timestamp`` -> ISO-UTC (an already-ISO ``observed_at``
      passes through unchanged).
    - Records without a URL or a parseable timestamp are dropped.
    - Sort key: ``observed_at`` (stable); duplicate *capture identities* collapse
      to the first occurrence, not equal content digests.
    """
    out: list[CaptureObservation] = []
    seen: set[tuple[object, ...]] = set()
    for record in raw:
        url = str(record.get("url", "")).strip()
        if not url:
            continue
        timestamp = record.get("timestamp")
        if timestamp is None:
            timestamp = record.get("fetch_time")
        if timestamp is None:
            timestamp = record.get("observed_at")
        if timestamp is None:
            continue
        observed_at = iso_utc_from_cc_timestamp(str(timestamp))
        if observed_at is None:
            # tolerate an already-ISO-UTC observed_at, still deterministic
            ts = str(timestamp).strip()
            observed_at = ts if ts.endswith("Z") and "T" in ts else None
        if observed_at is None:
            continue
        digest = str(record.get("digest", "")).strip()
        crawl = str(record.get("crawl") or record.get("collection") or "").strip()
        subset = str(record.get("subset", "")).strip()
        warc_filename = str(record.get("warc_filename", "")).strip()
        offset = _as_int(record.get("offset", record.get("warc_record_offset", 0)))
        length = _as_int(record.get("length", record.get("warc_record_length", 0)))
        warc_record_id = str(record.get("warc_record_id", "")).strip()
        # Legacy mappings have no locator. In that case digest is the only
        # available discriminator between otherwise identical captures.
        identity_locator = (
            (warc_filename, offset, length, warc_record_id)
            if warc_filename or offset or length or warc_record_id
            else ("digest-fallback", digest)
        )
        key = (crawl, subset, url, observed_at, *identity_locator)
        if key in seen:
            continue
        seen.add(key)
        out.append(
            CaptureObservation(
                url=url,
                observed_at=observed_at,
                status=_as_int(record.get("status", record.get("fetch_status", 0))),
                digest=digest,
                crawl=crawl,
                subset=subset,
                warc_filename=warc_filename,
                offset=offset,
                length=length,
                warc_record_id=warc_record_id,
            )
        )
    out.sort(key=lambda o: o.observed_at)
    return out
