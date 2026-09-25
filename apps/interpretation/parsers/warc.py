"""WARC 1.0/1.1 → document text with provenance (deterministic, stdlib only).

The interpretation lane receives archived web captures, not just bare HTTP
bodies: a WARC record carries the response together with the provenance that
makes the capture citable — ``WARC-Record-ID``, ``WARC-Date``,
``WARC-Target-URI`` and ``WARC-Payload-Digest``. This module turns those bytes
into :class:`WarcDocument` records whose text can be parsed by the ordinary
``ParserRegistry`` lane, while keeping every claim traceable back to the exact
record it came from.

Why a local reader instead of ``warcio``: the deterministic extraction lane
(spec 007) is pure-Python by contract — no ML, no clock, no network — and its
suite must run without the optional acquisition extras installed. A WARC record
is a small, fully specified framing (version line, named fields, blank line, a
``Content-Length``-delimited block, then a CRLFCRLF trailer), so the framing is
implemented here directly and stays available everywhere. Records stored as
individual gzip members (the Common Crawl layout) are inflated in place.

Determinism invariants (I-1, NFR-1):
  * identical bytes → identical documents, in identical record order;
  * no wall-clock, no randomness, no network, no environment lookups;
  * ids are content-derived (``sha256`` over stable fields), never random;
  * a malformed record raises with a stable reason code instead of yielding a
    half-parsed document.

Revisit records are first-class here: a ``revisit`` capture has no payload of
its own but proves the page was re-captured, which is publication evidence.
They are surfaced as documents with ``is_revisit=True`` and empty text rather
than silently dropped, so the admission lane can count them as corroboration.

Refs only (I-5): :meth:`WarcDocument.provenance` exposes record ids, URIs and
digests — never the payload bytes.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import re
import zlib
from collections.abc import Iterator
from dataclasses import dataclass

# Budgets: a hostile archive must not exhaust memory. Fixed constants (not
# per-call knobs) so behaviour stays reproducible across runs.
MAX_RECORD_BYTES = 16 * 1024 * 1024
MAX_RECORDS = 100_000
MAX_TEXT_BYTES = 8 * 1024 * 1024

GZIP_MAGIC = b"\x1f\x8b"
CRLFCRLF = b"\r\n\r\n"

_VERSION_RE = re.compile(rb"^WARC/(\d+)\.(\d+)\s*$")

# Record types that carry a retrievable entity. ``warcinfo``/``request``/
# ``metadata`` describe the crawl rather than the page itself.
PAYLOAD_RECORD_TYPES = frozenset({"response", "resource"})

_TEXTUAL_TYPES = (
    "text/",
    "application/json",
    "application/xml",
    "application/xhtml",
    "application/javascript",
    "application/x-www-form-urlencoded",
    "application/rss",
    "application/atom",
    "application/ld+json",
)

_BINARY_MAGICS = (
    b"%PDF-",
    b"\x89PNG",
    b"\xff\xd8\xff",
    b"GIF8",
    b"PK\x03\x04",
    b"Rar!",
    b"\x7fELF",
    b"MZ",
    GZIP_MAGIC,
    b"RIFF",
    b"OggS",
)


class WarcParseError(ValueError):
    """Malformed WARC framing. Carries a stable ``reason`` code for quarantine."""

    def __init__(self, reason: str, detail: str = "") -> None:
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}" if detail else reason)


@dataclass(frozen=True)
class WarcRecord:
    """One framed WARC record: header fields plus the raw content block."""

    record_type: str
    version: str
    headers: dict[str, str]
    block: bytes
    offset: int = 0
    truncated: bool = False

    def header(self, name: str, default: str | None = None) -> str | None:
        return self.headers.get(name.lower(), default)


@dataclass(frozen=True)
class HttpMessage:
    """The HTTP entity carried inside a ``response`` record's block."""

    status_code: int | None
    reason: str
    headers: dict[str, str]
    body: bytes
    body_offset: int = 0

    def header(self, name: str, default: str | None = None) -> str | None:
        return self.headers.get(name.lower(), default)


@dataclass(frozen=True)
class WarcInfo:
    """``warcinfo`` record: crawl-level provenance for the whole file."""

    record_id: str = ""
    filename: str = ""
    date: str | None = None
    software: str = ""
    format: str = ""
    robots: str = ""
    host: str = ""
    description: str = ""
    declared_size: int | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "record_id": self.record_id,
            "filename": self.filename,
            "date": self.date,
            "software": self.software,
            "format": self.format,
            "robots": self.robots,
            "host": self.host,
            "description": self.description,
            "declared_size": self.declared_size,
        }


@dataclass(frozen=True)
class WarcDocument:
    """An archived capture reduced to deterministic document text + provenance.

    ``text`` is empty (with a note explaining why) for payloads that carry no
    readable text — binary resources and payload-less ``revisit`` records. The
    record is still returned, because its existence is itself evidence.
    """

    document_id: str
    record_id: str
    record_type: str
    url: str
    warc_date: str | None = None
    content_type: str | None = None
    charset: str = ""
    http_status: int | None = None
    text: str = ""
    payload: bytes = b""
    body_sha256: str = ""
    warc_digest: str | None = None
    digest_verified: bool | None = None
    revisit_of: str | None = None
    is_revisit: bool = False
    truncated: bool = False
    notes: tuple[str, ...] = ()

    @property
    def has_text(self) -> bool:
        return bool(self.text.strip())

    def provenance(self) -> dict[str, object]:
        """Refs-only provenance for this document (never the payload, I-5)."""
        return {
            "document_id": self.document_id,
            "record_id": self.record_id,
            "record_type": self.record_type,
            "url": self.url,
            "warc_date": self.warc_date,
            "content_type": self.content_type,
            "charset": self.charset,
            "http_status": self.http_status,
            "body_sha256": self.body_sha256,
            "warc_digest": self.warc_digest,
            "digest_verified": self.digest_verified,
            "revisit_of": self.revisit_of,
            "is_revisit": self.is_revisit,
            "truncated": self.truncated,
            "notes": list(self.notes),
        }

    def to_dict(self) -> dict[str, object]:
        data = self.provenance()
        data["text"] = self.text
        return data


# --------------------------------------------------------------------------- #
# Framing
# --------------------------------------------------------------------------- #


def _read_gzip_member(data: bytes, pos: int) -> tuple[bytes, int]:
    """Inflate the gzip member starting at ``pos``; return (bytes, consumed)."""
    decomp = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        out = decomp.decompress(data[pos:])
        out += decomp.flush()
    except zlib.error as exc:
        raise WarcParseError("warc.gzip_corrupt", str(exc)) from exc
    consumed = len(data) - pos - len(decomp.unused_data)
    if consumed <= 0:
        raise WarcParseError("warc.gzip_truncated", "member consumed no input")
    return out, consumed


def _parse_header_block(raw: bytes) -> tuple[str, dict[str, str]]:
    """Split a record header block into (version, lowercased named fields).

    Field names are case-insensitive per the WARC spec, so they fold to
    lowercase; repeated fields keep the first value (WARC fields are
    single-valued) and folded continuation lines are appended to the previous
    field.
    """
    lines = raw.split(b"\n")
    if not lines:
        raise WarcParseError("warc.header_empty", "no version line")
    version_raw = lines[0].strip()
    if _VERSION_RE.match(version_raw) is None:
        raise WarcParseError("warc.bad_version_line", version_raw[:64].decode("latin-1"))
    headers: dict[str, str] = {}
    last_key: str | None = None
    for line in lines[1:]:
        stripped = line.rstrip(b"\r")
        if not stripped:
            continue
        if stripped[:1] in (b" ", b"\t") and last_key is not None:
            headers[last_key] += " " + stripped.strip().decode("utf-8", "replace")
            continue
        name, sep, value = stripped.partition(b":")
        if not sep:
            raise WarcParseError("warc.bad_header_line", stripped[:64].decode("latin-1"))
        last_key = name.strip().decode("latin-1").lower()
        headers.setdefault(last_key, value.strip().decode("utf-8", "replace"))
    return version_raw.decode("ascii"), headers


def _find_header_end(data: bytes, start: int) -> int:
    """Index just past the blank line closing a header block, or -1 if absent."""
    crlf = data.find(CRLFCRLF, start)
    lf = data.find(b"\n\n", start)
    if crlf < 0 and lf < 0:
        return -1
    if crlf >= 0 and (lf < 0 or crlf <= lf):
        return crlf + 4
    return lf + 2


def _parse_record(
    data: bytes, pos: int, max_record_bytes: int
) -> tuple[WarcRecord | None, int]:
    """Parse one record from a non-gzip buffer; return (record, next_offset).

    Returns ``(None, pos)`` when no record starts here, which marks the end of
    the scan rather than an error: trailing padding after the final record is
    normal in WARC files.
    """
    if pos >= len(data):
        return None, pos
    first_line = data[pos : pos + 16].split(b"\n", 1)[0].rstrip(b"\r")
    if _VERSION_RE.match(first_line) is None:
        return None, pos
    header_end = _find_header_end(data, pos)
    if header_end < 0:
        raise WarcParseError("warc.unterminated_header", f"at offset {pos}")
    version, headers = _parse_header_block(data[pos:header_end])
    raw_len = headers.get("content-length")
    if raw_len is None:
        raise WarcParseError("warc.missing_content_length", headers.get("warc-type", ""))
    try:
        length = int(raw_len)
    except ValueError as exc:
        raise WarcParseError("warc.bad_content_length", raw_len[:32]) from exc
    if length < 0 or length > max_record_bytes:
        raise WarcParseError("warc.record_too_large", f"{length} bytes")

    body_start = header_end
    available = max(0, min(length, len(data) - body_start))
    block = data[body_start : body_start + available]
    block_end = body_start + available

    # Consume the CRLFCRLF record trailer (spec: two CRLFs after the block).
    next_pos = block_end
    if data[next_pos : next_pos + 4] == CRLFCRLF:
        next_pos += 4
    else:
        while next_pos < len(data) and next_pos - block_end < 4 and data[next_pos] in (0x0D, 0x0A):
            next_pos += 1

    record = WarcRecord(
        record_type=headers.get("warc-type", "").lower(),
        version=version,
        headers=headers,
        block=block,
        offset=pos,
        truncated=available < length,
    )
    return record, next_pos


def _scan(
    buf: bytes,
    base: int,
    budget: list[int],
    max_records: int,
    max_record_bytes: int,
) -> Iterator[WarcRecord]:
    """Yield records from a plain (already inflated) buffer, rebasing offsets."""
    pos = 0
    while pos < len(buf):
        record, next_pos = _parse_record(buf, pos, max_record_bytes)
        if record is None:
            return
        budget[0] += 1
        if budget[0] > max_records:
            raise WarcParseError("warc.too_many_records", str(max_records))
        yield WarcRecord(
            record_type=record.record_type,
            version=record.version,
            headers=record.headers,
            block=record.block,
            offset=base + pos,
            truncated=record.truncated,
        )
        if next_pos <= pos:  # defensive: never loop on a zero-width step
            return
        pos = next_pos


def iter_records(
    data: bytes,
    *,
    max_records: int = MAX_RECORDS,
    max_record_bytes: int = MAX_RECORD_BYTES,
) -> Iterator[WarcRecord]:
    """Yield every WARC record in ``data``, inflating gzip members in place.

    Raises :class:`WarcParseError` on malformed framing so the caller can
    quarantine the capture with a stable reason code instead of interpreting
    half a record.
    """
    budget = [0]
    pos = 0
    while pos < len(data):
        if data[pos : pos + 2] == GZIP_MAGIC:
            member, consumed = _read_gzip_member(data, pos)
            yield from _scan(member, pos, budget, max_records, max_record_bytes)
            pos += consumed
            continue
        record, next_pos = _parse_record(data, pos, max_record_bytes)
        if record is None:
            return
        budget[0] += 1
        if budget[0] > max_records:
            raise WarcParseError("warc.too_many_records", str(max_records))
        yield record
        if next_pos <= pos:  # defensive: never loop on a zero-width step
            return
        pos = next_pos


# --------------------------------------------------------------------------- #
# HTTP entity extraction
# --------------------------------------------------------------------------- #


def parse_http_message(block: bytes) -> HttpMessage:
    """Split a raw HTTP response (status line + headers + body) from a block."""
    header_end = _find_header_end(block, 0)
    if header_end < 0:
        # No blank line: a bare body with no HTTP envelope (resource records).
        return HttpMessage(status_code=None, reason="", headers={}, body=block)
    head = block[:header_end]
    body = block[header_end:]
    lines = head.replace(b"\r\n", b"\n").split(b"\n")
    status_line = lines[0].decode("latin-1").strip() if lines else ""
    parts = status_line.split(None, 2)
    status: int | None = None
    reason = ""
    if len(parts) >= 2 and parts[0].upper().startswith("HTTP/"):
        try:
            status = int(parts[1])
        except ValueError:
            status = None
        reason = parts[2] if len(parts) > 2 else ""
    headers: dict[str, str] = {}
    for line in lines[1:]:
        stripped = line.strip()
        if not stripped:
            continue
        name, sep, value = stripped.partition(b":")
        if not sep:
            continue
        key = name.strip().decode("latin-1").lower()
        headers.setdefault(key, value.strip().decode("utf-8", "replace"))
    return HttpMessage(
        status_code=status,
        reason=reason,
        headers=headers,
        body=body,
        body_offset=header_end,
    )


def _decode_content_encoding(body: bytes, encoding: str | None) -> tuple[bytes, str | None]:
    """Undo a transfer ``Content-Encoding``. Returns (bytes, note-or-None)."""
    if not encoding:
        return body, None
    name = encoding.strip().lower()
    try:
        if name in ("gzip", "x-gzip"):
            return zlib.decompress(body, 16 + zlib.MAX_WBITS), None
        if name == "deflate":
            try:
                return zlib.decompress(body), None
            except zlib.error:
                return zlib.decompress(body, -zlib.MAX_WBITS), None
    except zlib.error:
        # Undecodable transfer coding is reported, never guessed around.
        return b"", f"content_encoding_undecodable:{name}"
    return body, f"content_encoding_unsupported:{name}"


def _content_type_of(record: WarcRecord, message: HttpMessage | None) -> str | None:
    """Entity content type: the HTTP header wins over the WARC envelope type.

    A ``response`` record's own ``Content-Type`` describes the *envelope*
    (``application/http; msgtype=response``), not the page, so it must never be
    reported as the document's type.
    """
    if message is not None:
        raw = message.header("content-type")
        if raw:
            return raw.split(";", 1)[0].strip().lower() or None
    warc_type = record.header("content-type") or ""
    if warc_type.lower().startswith("application/http"):
        return None
    return warc_type.split(";", 1)[0].strip().lower() or None


def _charset_of(record: WarcRecord, message: HttpMessage | None) -> str:
    for source in (
        message.header("content-type") if message is not None else None,
        record.header("content-type"),
    ):
        if not source:
            continue
        match = re.search(r"charset\s*=\s*\"?([\w.:+-]+)\"?", source, re.IGNORECASE)
        if match:
            return match.group(1).strip().lower()
    return ""


def verify_payload_digest(payload: bytes, declared: str | None) -> bool | None:
    """Check a ``WARC-Payload-Digest`` against the decoded payload.

    Returns True/False, or None when no digest is declared or the algorithm is
    not one this module implements — absence of verification is reported
    honestly rather than as a pass.
    """
    if not declared:
        return None
    algo, _, expected = declared.partition(":")
    algo = algo.strip().lower().replace("-", "")
    expected = expected.strip()
    if not expected:
        return None
    factory = {
        "sha1": hashlib.sha1,
        "sha256": hashlib.sha256,
        "md5": hashlib.md5,
    }.get(algo)
    if factory is None:
        return None
    actual = factory(payload).digest()
    candidates = {actual.hex().lower(), actual.hex().upper()}
    try:
        candidates.add(base64.b32encode(actual).decode("ascii").rstrip("=").lower())
    except binascii.Error:  # pragma: no cover - digest lengths are b32-safe
        pass
    return expected.replace("=", "").lower() in candidates


def _looks_binary(content_type: str | None, payload: bytes) -> bool:
    if payload.startswith(_BINARY_MAGICS):
        return True
    if b"\x00" in payload[:4096]:
        return True
    if not content_type:
        return False
    return not content_type.startswith(_TEXTUAL_TYPES)


def _decode_text(payload: bytes) -> tuple[str, str]:
    """Charset-aware text decode via the deterministic extraction lane."""
    try:
        from extractors.language import decode_bytes

        return decode_bytes(payload)
    except Exception:  # noqa: BLE001 - hostile bytes degrade, never crash
        return payload.decode("utf-8", errors="replace"), "utf-8"


def _document_id(record_id: str, url: str, body_sha256: str) -> str:
    """Content-derived document id: the same capture always yields the same id."""
    stable = f"{record_id}|{url}|{body_sha256}".encode()
    return "WD-" + hashlib.sha256(stable).hexdigest()[:24]


def _warcinfo_from(record: WarcRecord) -> WarcInfo:
    fields: dict[str, str] = {}
    for line in record.block.decode("utf-8", "replace").splitlines():
        name, sep, value = line.partition(":")
        if sep:
            fields.setdefault(name.strip().lower(), value.strip())
    declared = fields.get("filesize") or fields.get("size") or ""
    return WarcInfo(
        record_id=record.header("warc-record-id", "") or "",
        filename=fields.get("filename", ""),
        date=record.header("warc-date") or fields.get("date") or None,
        software=fields.get("software", ""),
        format=fields.get("format", ""),
        robots=fields.get("robots", ""),
        # WARC 1.0 names this field `host`; de-facto writers (warcio, wget,
        # Common Crawl) emit `hostname`. Both are accepted rather than
        # silently dropping the crawl's origin.
        host=fields.get("host") or fields.get("hostname", ""),
        description=fields.get("description", ""),
        declared_size=int(declared) if declared.isdigit() else None,
    )


def _revisit_document(record: WarcRecord) -> WarcDocument:
    record_id = record.header("warc-record-id", "") or ""
    url = record.header("warc-target-uri", "") or ""
    notes = ["revisit_no_payload"]
    if record.truncated:
        notes.append("record_truncated")
    return WarcDocument(
        document_id=_document_id(record_id, url, ""),
        record_id=record_id,
        record_type=record.record_type,
        url=url,
        warc_date=record.header("warc-date"),
        revisit_of=record.header("warc-refers-to"),
        is_revisit=True,
        truncated=record.truncated,
        notes=tuple(notes),
    )


def _payload_document(record: WarcRecord) -> WarcDocument:
    record_id = record.header("warc-record-id", "") or ""
    url = record.header("warc-target-uri", "") or ""
    notes: list[str] = []

    message = parse_http_message(record.block) if record.record_type == "response" else None
    raw_body = message.body if message is not None else record.block
    content_type = _content_type_of(record, message)
    declared_encoding = message.header("content-encoding") if message is not None else None

    payload, encoding_note = _decode_content_encoding(raw_body, declared_encoding)
    if encoding_note:
        notes.append(encoding_note)
    if record.truncated:
        notes.append("record_truncated")
    if message is not None and message.status_code is not None and message.status_code >= 400:
        notes.append(f"http_error_status:{message.status_code}")

    body_sha = hashlib.sha256(payload).hexdigest()
    text = ""
    if _looks_binary(content_type, payload):
        notes.append("non_text_payload")
    else:
        text, _ = _decode_text(payload[:MAX_TEXT_BYTES])
        if len(payload) > MAX_TEXT_BYTES:
            notes.append("text_truncated_to_budget")

    digest = record.header("warc-payload-digest")
    return WarcDocument(
        document_id=_document_id(record_id, url, body_sha),
        record_id=record_id,
        record_type=record.record_type,
        url=url,
        warc_date=record.header("warc-date"),
        content_type=content_type,
        charset=_charset_of(record, message),
        http_status=message.status_code if message is not None else None,
        text=text,
        payload=payload,
        body_sha256=body_sha,
        warc_digest=digest,
        digest_verified=verify_payload_digest(payload, digest),
        truncated=record.truncated,
        notes=tuple(notes),
    )


def document_from_record(record: WarcRecord) -> WarcDocument | None:
    """Reduce one record to a document, or None when it carries no entity.

    ``warcinfo``/``request``/``metadata`` describe the crawl, not the page, so
    they are not documents; ``response``/``resource`` are, and ``revisit`` is
    reduced to a payload-less document that still proves a re-capture.
    """
    if record.record_type == "revisit":
        return _revisit_document(record)
    if record.record_type not in PAYLOAD_RECORD_TYPES:
        return None
    return _payload_document(record)


def documents_from_records(records: Iterator[WarcRecord]) -> list[WarcDocument]:
    """Map records to documents, dropping non-entity records, in record order."""
    documents: list[WarcDocument] = []
    for record in records:
        document = document_from_record(record)
        if document is not None:
            documents.append(document)
    return documents


def parse_warc_info(data: bytes) -> WarcInfo | None:
    """Return the first ``warcinfo`` record of an archive, if it has one."""
    for record in iter_records(data):
        if record.record_type == "warcinfo":
            return _warcinfo_from(record)
    return None


def parse_warc(data: bytes) -> list[WarcDocument]:
    """Parse a WARC byte stream into documents (deterministic, record order)."""
    return documents_from_records(iter_records(data))


def is_warc(data: bytes) -> bool:
    """Cheap sniff: does this buffer start with a WARC version line or gzip?"""
    if data[:2] == GZIP_MAGIC:
        return True
    return data[:64].lstrip().startswith(b"WARC/")
