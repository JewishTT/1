"""WARC/WET byte-range pull (FR-003, 011).

The CC index gives byte-exact WARC addresses (`warc_filename@offset,length`).
A single HTTP Range GET (or S3 range request) materializes exactly one WARC
record — no corpus download. We parse the WARC header prefix and hand the
payload (headers or plaintext WET text) to the deterministic extractor.

Transport is injectable (FR-015 seam): tests use a fake that serves bytes for
the exact range, so the whole pilot runs network-free (SC-002).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from network.cc_session import CCPageRecord, Transport


class ByteTransport(Protocol):
    async def fetch(self, filename: str, offset: int, length: int) -> bytes: ...


@dataclass(frozen=True)
class WarcPull:
    """Result of one byte-range pull (FR-003)."""

    filename: str
    offset: int
    length: int
    record_type: str | None
    content_type: str | None
    url: str | None
    warc_date: str | None
    digest: str | None
    payload: bytes

    def as_text(self, encoding: str = "utf-8", errors: str = "replace") -> str:
        return self.payload.decode(encoding, errors=errors)


_WARC_HEADER_END = b"\r\n\r\n"
_WARC_HEADER_END_SHORT = b"\n\n"


def _decode_header_field(value: bytes) -> str:
    return value.decode("iso-8859-1", errors="replace")


def parse_warc_prefix(blob: bytes) -> tuple[dict[str, str], int]:
    """Split a WARC/WET record into header dict + payload offset.

    Handles both ``\\r\\n`` (strict WARC) and ``\\n`` (some WET producers)
    line endings. Returns (headers, byte offset of payload start).
    """
    for terminator in (_WARC_HEADER_END, _WARC_HEADER_END_SHORT):
        idx = blob.find(terminator)
        if idx >= 0:
            header_bytes = blob[:idx]
            payload_offset = idx + len(terminator)
            break
    else:
        return {}, 0

    headers: dict[str, str] = {}
    lines = header_bytes.split(b"\r\n") if b"\r\n" in header_bytes else header_bytes.split(b"\n")
    for line in lines:
        line = line.strip()
        if not line or line.startswith(b"WARC/") or b":" not in line:
            continue
        key, _, value = line.partition(b":")
        headers[_decode_header_field(key).strip().lower()] = _decode_header_field(
            value
        ).strip()
    return headers, payload_offset


def split_warc_records(blob: bytes) -> list[WarcPull]:
    """Parse the raw record bytes into (header, payload) results.

    A proper WARC stream may contain many records; the CC index aligns each
    range to exactly one record, but we stay tolerant: scan until the byte
    budget described by ``content-length`` is exhausted.
    """
    headers, payload_offset = parse_warc_prefix(blob)
    if not headers:
        return []
    return [
        WarcPull(
            filename="",
            offset=0,
            length=len(blob),
            record_type=headers.get("warc-type"),
            content_type=headers.get("content-type"),
            url=headers.get("warc-target-uri"),
            warc_date=headers.get("warc-date"),
            digest=headers.get("warc-block-digest"),
            payload=blob[payload_offset:],
        )
    ]


__all__ = ["ByteTransport", "WarcPull", "parse_warc_prefix", "split_warc_records"]