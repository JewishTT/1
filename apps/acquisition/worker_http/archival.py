"""Archival mode for the HTTP worker (T106): WARC capture + ARClint-style lint.

The HTTP worker can run in ``archival`` mode: instead of passing the raw wire
payload through, it stamps a WARC (the archive fabric's canonical container)
and validates that container structurally — WARC version, required record
headers, byte alignment — before the payload moves to the Observation Gate.
Validation mirrors ARClint discipline: a WARC that fails lint is never emitted.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urlsplit

from warcio import WARCWriter
from warcio.statusandheaders import StatusAndHeaders

WARC_VERSION_PREFIXES = (b"WARC/1.0", b"WARC/1.1")
REQUIRED_REC_HEADERS = (
    "WARC-Type",
    "WARC-Record-ID",
    "WARC-Date",
    "Content-Length",
    "Content-Type",
)
RECORD_SEP = b"\r\n\r\n"


@dataclass(frozen=True)
class WarcCapture:
    """One archival observation unit (a packet the worker wants to archive)."""

    target_uri: str
    payload: bytes
    warc_type: str = "response"
    warc_date: str = field(default_factory=lambda: datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))
    content_type: str = "application/http; msgtype=response"
    extra: dict[str, str] = field(default_factory=dict)


def _status_and_headers(capture: WarcCapture) -> StatusAndHeaders:
    protocol = "HTTP/1.1 200 OK"
    return StatusAndHeaders(
        "200 OK",
        [("Content-Type", capture.content_type)],
        protocol=protocol,
    )


@dataclass(frozen=True)
class WarcIssue:
    level: str  # "error" | "warning"
    message: str


def _record_segments(data: bytes) -> tuple[list[tuple[bytes, bytes, int]], bool]:
    """Split ``data`` into ``(header_block, payload, advance_len)`` segments.

    A WARC file is a run of records glued by ``\\r\\n\\r\\n``; each record's
    Content-Length locates its payload so lint does not depend on a parser.
    The second return value flags a payload truncated against its declared
    Content-Length (ARClint treats that as a structural error).
    """
    segments: list[tuple[bytes, bytes, int]] = []
    truncated = False
    cursor = 0
    size = len(data)
    while cursor < size:
        while cursor < size and data[cursor : cursor + 2] == b"\r\n":
            cursor += 2
        if cursor >= size:
            break
        end = data.find(RECORD_SEP, cursor)
        if end == -1:
            segments.append((data[cursor:], b"", size - cursor))
            break
        header_block = data[cursor:end]
        payload_len = 0
        for line in header_block.split(b"\r\n"):
            if line.lower().startswith(b"content-length:"):
                try:
                    payload_len = int(line.split(b":", 1)[1].strip())
                except ValueError:
                    payload_len = 0
        header_len = end - cursor + len(RECORD_SEP)
        payload_start = end + len(RECORD_SEP)
        if payload_len < 0 or payload_start + payload_len > size:
            truncated = True
            segments.append((header_block, b"", size - cursor))
            break
        payload = data[payload_start : payload_start + payload_len]
        segments.append((header_block, payload, header_len + payload_len))
        cursor = payload_start + payload_len
    return segments, truncated


def lint_warc(data: bytes) -> list[WarcIssue]:
    """ARClint-style structural validation; empty list == valid WARC."""
    issues: list[WarcIssue] = []
    if not data:
        return [WarcIssue("error", "empty warc payload")]
    if not data.strip():
        return [WarcIssue("error", "whitespace-only warc payload")]
    if not any(data.startswith(prefix) for prefix in WARC_VERSION_PREFIXES):
        issues.append(WarcIssue("error", f"bad magic, expected WARC header, got {data[:12]!r}"))
        return issues
    segments, truncated = _record_segments(data)
    if truncated:
        message = "truncated record payload: Content-Length exceeds available bytes"
        issues.append(WarcIssue("error", message))
    if not segments:
        issues.append(WarcIssue("error", "no warc records found"))
        return issues
    for idx, (header_block, _payload, _advance) in enumerate(segments):
        headers = {}
        for line in header_block.split(b"\r\n"):
            if b":" in line:
                key, _, value = line.partition(b":")
                headers[key.strip().decode("ascii", errors="ignore")] = value.strip()
        missing = [name for name in REQUIRED_REC_HEADERS if name not in headers]
        if missing:
            issues.append(WarcIssue("error", f"record {idx}: missing headers {missing}"))
        if "WARC-Target-URI" not in headers and headers.get("WARC-Type") in ("response", "request"):
            wtype = headers.get("WARC-Type")
            issues.append(WarcIssue("error", f"record {idx}: WARC-Target-URI required for {wtype}"))
        if idx == 0 and "warc-toplevel" not in str(headers).lower():
            issues.append(WarcIssue("warning", f"record {idx}: first record should be warcinfo"))
    return issues


def validate_warc(data: bytes) -> tuple[bool, list[WarcIssue]]:
    """``True`` when ``data`` is a structurally valid WARC (ARClint discipline)."""
    issues = lint_warc(data)
    errors = [i for i in issues if i.level == "error"]
    return not errors, issues


def build_warc(captures: list[WarcCapture]) -> bytes:
    """Stamp captures into a WARC 1.0 container (buffer is lint-clean by design)."""
    buffer = io.BytesIO()
    writer = WARCWriter(buffer, gzip=False)
    for idx, capture in enumerate(captures):
        record_id = f"<urn:uuid:cog-{idx}-{abs(hash(capture.target_uri))}>"
        if capture.warc_type == "response":
            record = writer.create_warc_record(
                capture.target_uri,
                "response",
                payload=io.BytesIO(capture.payload),
                http_headers=_status_and_headers(capture),
            )
        else:
            record = writer.create_warc_record(
                capture.target_uri,
                "resource",
                payload=io.BytesIO(capture.payload),
            )
        record.rec_headers.replace_header("WARC-Record-ID", record_id)
        record.rec_headers.replace_header("WARC-Date", capture.warc_date)
        writer.write_record(record)
    return buffer.getvalue()


def archival_eligible(capture: WarcCapture, *, min_bytes: int = 0, html_only: bool = False) -> bool:
    """Decide whether a capture enters archival mode."""
    if len(capture.payload) < min_bytes:
        return False
    if html_only:
        parsed = urlsplit(capture.target_uri)
        path = parsed.path or "/"
        if path.rpartition(".")[2].lower() not in ("html", "htm"):
            return False
    return True