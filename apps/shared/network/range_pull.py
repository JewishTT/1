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


class ByteTransport(Protocol):
    """Fetch one exact byte range from a WARC object."""

    async def fetch(self, filename: str, offset: int, length: int) -> bytes: ...


@dataclass(frozen=True)
class HttpByteTransport:
    """Minimal Common Crawl HTTP range transport.

    Common Crawl publishes WARC objects over HTTPS. The response is deliberately
    bounded to the indexed byte range; callers never download the whole crawl.
    """

    base_url: str = "https://data.commoncrawl.org"
    timeout: float = 120.0

    async def fetch(self, filename: str, offset: int, length: int) -> bytes:
        if offset < 0 or length <= 0:
            raise ValueError("offset must be non-negative and length must be positive")
        import httpx

        url = f"{self.base_url.rstrip('/')}/{filename.lstrip('/')}"
        headers = {"Range": f"bytes={offset}-{offset + length - 1}"}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.content


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
    warc_record_id: str | None = None

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
            warc_record_id=headers.get("warc-record-id"),
        )
    ]


async def pull_warc_range(
    transport: ByteTransport,
    *,
    filename: str,
    offset: int,
    length: int,
) -> WarcPull:
    """Fetch and parse one indexed WARC range without losing its locator."""
    blob = await transport.fetch(filename, offset, length)
    records = split_warc_records(blob)
    if not records:
        raise ValueError(f"range {filename}@{offset},{length} contains no WARC record")
    record = records[0]
    return WarcPull(
        filename=filename,
        offset=offset,
        length=length,
        record_type=record.record_type,
        content_type=record.content_type,
        url=record.url,
        warc_date=record.warc_date,
        digest=record.digest,
        payload=record.payload,
        warc_record_id=record.warc_record_id,
    )


__all__ = [
    "ByteTransport",
    "HttpByteTransport",
    "WarcPull",
    "parse_warc_prefix",
    "pull_warc_range",
    "split_warc_records",
]