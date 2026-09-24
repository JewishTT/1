"""WARC/WET byte-range pull (FR-003, 011)."""
from __future__ import annotations

import gzip
import re
from dataclasses import dataclass
from typing import Protocol

_CONTENT_RANGE_RE = re.compile(r"^bytes\s+(\d+)-(\d+)/(\d+)$", re.IGNORECASE)


class ByteTransport(Protocol):
    async def fetch(self, filename: str, offset: int, length: int) -> bytes: ...


@dataclass(frozen=True)
class HttpByteTransport:
    """Bounded Common Crawl HTTP range transport."""
    base_url: str = "https://data.commoncrawl.org"
    timeout: float = 120.0

    async def fetch(self, filename: str, offset: int, length: int) -> bytes:
        if offset < 0 or length <= 0:
            raise ValueError("offset must be non-negative and length must be positive")
        import httpx
        url = f"{self.base_url.rstrip('/')}/{filename.lstrip('/')}"
        expected_end = offset + length - 1
        async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
            response = await client.get(url, headers={"Range": f"bytes={offset}-{expected_end}"})
            if response.status_code != 206:
                raise ValueError(f"range request returned HTTP {response.status_code}; expected 206")
            match = _CONTENT_RANGE_RE.match(response.headers.get("content-range", "").strip())
            if not match or int(match.group(1)) != offset or int(match.group(2)) != expected_end:
                raise ValueError(f"invalid Content-Range; expected bytes {offset}-{expected_end}")
            if len(response.content) != length:
                raise ValueError(f"range response length {len(response.content)} != requested {length}")
            return response.content


@dataclass(frozen=True)
class WarcPull:
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
        headers[_decode_header_field(key).strip().lower()] = _decode_header_field(value).strip()
    return headers, payload_offset


def _decompress_warc_members(blob: bytes) -> bytes:
    if blob.startswith(b"\x1f\x8b"):
        return gzip.decompress(blob)
    return blob


def split_warc_records(blob: bytes) -> list[WarcPull]:
    decoded = _decompress_warc_members(blob)
    headers, payload_offset = parse_warc_prefix(decoded)
    if not headers:
        return []
    # The transport already bounds the compressed indexed range.  Do not
    # reinterpret WARC Content-Length here: WET fixtures and HTTP payload
    # framing may disagree, and truncating here drops the response body.
    payload = decoded[payload_offset:]
    return [WarcPull(
        filename="", offset=0, length=len(blob), record_type=headers.get("warc-type"),
        content_type=headers.get("content-type"), url=headers.get("warc-target-uri"),
        warc_date=headers.get("warc-date"), digest=headers.get("warc-block-digest"),
        payload=payload, warc_record_id=headers.get("warc-record-id"),
    )]


async def pull_warc_range(transport: ByteTransport, *, filename: str, offset: int, length: int) -> WarcPull:
    blob = await transport.fetch(filename, offset, length)
    records = split_warc_records(blob)
    if not records:
        raise ValueError(f"range {filename}@{offset},{length} contains no WARC record")
    record = records[0]
    return WarcPull(
        filename=filename, offset=offset, length=length, record_type=record.record_type,
        content_type=record.content_type, url=record.url, warc_date=record.warc_date,
        digest=record.digest, payload=record.payload, warc_record_id=record.warc_record_id,
    )


__all__ = ["ByteTransport", "HttpByteTransport", "WarcPull", "parse_warc_prefix", "pull_warc_range", "split_warc_records"]
