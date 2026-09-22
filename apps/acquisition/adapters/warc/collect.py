"""WARC/archive retrieval adapter (T093).

Reads WARC payloads (http `response` records) from a local file or a byte range
of an S3 object and streams them -> bytes + metadata -> Observation Gate.
Range retrieval honors the Common Crawl offset/length contract so a full WARC
buffer is never required.
"""

from __future__ import annotations

import asyncio
import io
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from warcio.archiveiterator import ArchiveIterator

MAX_PAYLOAD_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True)
class WarcRecord:
    url: str
    warc_date: str | None
    content_type: str | None
    payload: bytes
    digest: str | None


def split_s3_uri(uri: str) -> tuple[str, str]:
    parsed = urlsplit(uri)
    if parsed.scheme != "s3":
        raise ValueError(f"expected s3:// bucket/key, got {uri!r}")
    key = parsed.path.lstrip("/")
    return parsed.netloc, key


def range_of(uri: str) -> tuple[int, int | None]:
    query = parse_qs(urlsplit(uri).query)
    offset = int(query.get("offset", ["0"])[0])
    length = int(query["length"][0]) if "length" in query else None
    return offset, length


def parse_warc(handle: io.BytesIO) -> list[WarcRecord]:
    records: list[WarcRecord] = []
    for rec in ArchiveIterator(handle):
        if rec.rec_type != "response":
            continue
        url = rec.rec_headers.get_header("WARC-Target-URI") or ""
        if not url.startswith(("http://", "https://")):
            continue
        payload = rec.content_stream().read(MAX_PAYLOAD_BYTES + 1)
        content_type = None
        if rec.http_headers is not None:
            content_type = rec.http_headers.get_header("Content-Type")
        records.append(
            WarcRecord(
                url=url,
                warc_date=rec.rec_headers.get_header("WARC-Date"),
                content_type=(content_type or "").split(";")[0].strip() or None,
                payload=payload,
                digest=rec.rec_headers.get_header("WARC-Payload-Digest"),
            )
        )
    return records


def _open_local(path: str) -> bytes:
    return Path(path).read_bytes()


async def adapt_warc(task: dict) -> dict:
    """Adapter callable: resolve source bytes, parse records, push to gate."""
    gate = task.get("observation_gate")
    if gate is None:
        raise ValueError("task requires 'observation_gate' (Observation boundary)")
    uri = task.get("warc_uri") or task.get("uri")
    if not uri:
        raise ValueError("task requires 'warc_uri'")
    store = task.get("object_store")
    if uri.startswith("s3://"):
        if store is None:
            raise ValueError("task requires 'object_store' for s3:// WARC sources")
        offset, length = range_of(uri)
        bucket, key = split_s3_uri(uri)
        data = await store.read_range(bucket=bucket, key=key, offset=offset, length=length)
    else:
        data = await asyncio.to_thread(_open_local, uri.removeprefix("local:"))
    records = await asyncio.to_thread(parse_warc, io.BytesIO(data))
    observations = []
    for rec in records:
        obs = await gate.ingest(
            body=rec.payload,
            uri=rec.url,
            tenant_id=task.get("tenant_id", "tenant-demo"),
            investigation_id=task.get("investigation_id"),
            source_id=task.get("source_id"),
            work_id=task.get("work_id"),
            region_id=task.get("region_id"),
            content_type=rec.content_type or "application/octet-stream",
            collector="warc-adapter",
            collector_version="2.0.0",
            source_kind="webarchive",
        )
        observations.append(
            {
                "uri": rec.url,
                "observation_id": obs["observation_id"],
                "status": obs["status"],
                "raw_ref": obs["raw_ref"],
            }
        )
    return {
        "task_id": task.get("task_id", ""),
        "adapted": len(observations),
        "observations": observations,
    }