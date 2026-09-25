"""WARC reader tests: framing, determinism, provenance, hostile input.

WARC bytes are built by hand rather than with ``warcio`` so the reader is
verified against the raw spec (version line, named fields, blank line,
Content-Length block, CRLFCRLF trailer) and the suite stays dependency-free.
"""

from __future__ import annotations

import base64
import gzip
import hashlib
import sys
import zlib
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from parsers.warc import (
    WarcParseError,
    document_from_record,
    is_warc,
    iter_records,
    parse_http_message,
    parse_warc,
    parse_warc_info,
    verify_payload_digest,
)


def build_record(
    record_type: str,
    block: bytes,
    *,
    uri: str = "",
    record_id: str = "<urn:uuid:00000000-0000-0000-0000-000000000001>",
    content_type: str = "application/http; msgtype=response",
    extra_headers: str = "",
    version: str = "WARC/1.0",
    date: str = "2024-01-02T03:04:05Z",
) -> bytes:
    """Assemble one WARC record exactly as the spec frames it."""
    head = f"{version}\r\n"
    head += f"WARC-Type: {record_type}\r\n"
    head += f"WARC-Record-ID: {record_id}\r\n"
    head += f"WARC-Date: {date}\r\n"
    if uri:
        head += f"WARC-Target-URI: {uri}\r\n"
    head += f"Content-Type: {content_type}\r\n"
    if extra_headers:
        head += extra_headers.rstrip("\r\n") + "\r\n"
    head += f"Content-Length: {len(block)}\r\n\r\n"
    return head.encode("utf-8") + block + b"\r\n\r\n"


def http_response(
    body: bytes,
    *,
    status: str = "HTTP/1.1 200 OK",
    content_type: str = "text/html; charset=utf-8",
    extra_headers: str = "",
) -> bytes:
    headers = f"{status}\r\nContent-Type: {content_type}\r\nContent-Length: {len(body)}\r\n"
    if extra_headers:
        headers += extra_headers.rstrip("\r\n") + "\r\n"
    return headers.encode("utf-8") + b"\r\n" + body


def sha1_b32(payload: bytes) -> str:
    return base64.b32encode(hashlib.sha1(payload).digest()).decode("ascii").rstrip("=")


class TestFraming:
    def test_parses_version_headers_and_block(self):
        rec = next(iter(iter_records(_response_record())))
        assert rec.record_type == "response"
        assert rec.version == "WARC/1.0"
        assert rec.header("warc-target-uri") == "https://acme.example/report"
        assert int(rec.header("content-length")) == len(rec.block)

    def test_header_lookup_is_case_insensitive(self):
        rec = next(iter(iter_records(_response_record())))
        assert rec.header("WARC-Type") == "response"
        assert rec.header("missing-header", "fallback") == "fallback"

    def test_multiple_records_keep_file_order(self):
        data = _response_record() + build_record(
            "response",
            http_response(b"second"),
            uri="https://acme.example/second",
            record_id="<urn:uuid:00000000-0000-0000-0000-000000000002>",
        )
        assert [r.header("warc-target-uri") for r in iter_records(data)] == [
            "https://acme.example/report",
            "https://acme.example/second",
        ]

    def test_warc_1_1_version_accepted(self):
        data = build_record("response", http_response(b"ok"), version="WARC/1.1")
        assert next(iter(iter_records(data))).version == "WARC/1.1"

    def test_lf_only_line_endings_parsed(self):
        head = (
            "WARC/1.0\nWARC-Type: response\nWARC-Record-ID: <urn:uuid:lf>\n"
            "WARC-Target-URI: https://acme.example/lf\n"
            f"Content-Length: {len(PAGE)}\n\n"
        ).encode()
        records = list(iter_records(head + PAGE + b"\n\n"))
        assert records[0].record_type == "response"
        assert records[0].block == PAGE

    def test_gzip_member_inflated_in_place(self):
        documents = parse_warc(gzip.compress(_response_record()))
        assert len(documents) == 1
        assert documents[0].url == "https://acme.example/report"
        assert "ops@acme.example" in documents[0].text

    def test_gzip_and_plain_records_mixed(self):
        data = _response_record() + gzip.compress(
            build_record(
                "response",
                http_response(b"<html>from gzip</html>"),
                uri="https://acme.example/gz",
                record_id="<urn:uuid:00000000-0000-0000-0000-000000000003>",
            )
        )
        assert [d.url for d in parse_warc(data)] == [
            "https://acme.example/report",
            "https://acme.example/gz",
        ]

    def test_truncated_block_is_flagged_not_silently_accepted(self):
        documents = parse_warc(_response_record()[:-40])
        assert len(documents) == 1
        assert documents[0].truncated is True
        assert "record_truncated" in documents[0].notes

    def test_folded_header_continuation_joined(self):
        data = build_record(
            "response",
            http_response(b"x"),
            extra_headers="WARC-Concurrent-To: <urn:uuid:a>\r\n\t<urn:uuid:b>",
        )
        rec = next(iter(iter_records(data)))
        assert rec.header("warc-concurrent-to") == "<urn:uuid:a> <urn:uuid:b>"


class TestMalformedInput:
    def test_missing_content_length_raises_stable_reason(self):
        with pytest.raises(WarcParseError) as excinfo:
            list(iter_records(b"WARC/1.0\r\nWARC-Type: response\r\n\r\nbody"))
        assert excinfo.value.reason == "warc.missing_content_length"

    def test_bad_version_line_stops_scan_without_raising(self):
        # Leading junk is padding, not corruption: the scan finds no record.
        assert list(iter_records(b"not a warc file at all")) == []

    def test_unterminated_header_raises(self):
        with pytest.raises(WarcParseError) as excinfo:
            list(iter_records(b"WARC/1.0\r\nWARC-Type: response\r\nContent-Length: 4\r\n"))
        assert excinfo.value.reason == "warc.unterminated_header"

    def test_non_numeric_content_length_raises(self):
        with pytest.raises(WarcParseError) as excinfo:
            list(iter_records(b"WARC/1.0\r\nWARC-Type: response\r\nContent-Length: abc\r\n\r\nxx"))
        assert excinfo.value.reason == "warc.bad_content_length"

    def test_oversized_record_rejected(self):
        with pytest.raises(WarcParseError) as excinfo:
            list(iter_records(_response_record(), max_record_bytes=10))
        assert excinfo.value.reason == "warc.record_too_large"

    def test_record_budget_enforced(self):
        with pytest.raises(WarcParseError) as excinfo:
            list(iter_records(_response_record() * 5, max_records=3))
        assert excinfo.value.reason == "warc.too_many_records"

    def test_corrupt_gzip_raises(self):
        with pytest.raises(WarcParseError) as excinfo:
            list(iter_records(b"\x1f\x8b" + b"garbage-not-deflate"))
        assert excinfo.value.reason.startswith("warc.gzip")

    def test_error_carries_reason_for_quarantine_routing(self):
        with pytest.raises(WarcParseError) as excinfo:
            list(iter_records(b"WARC/1.0\r\nWARC-Type: response\r\n\r\nx"))
        assert isinstance(excinfo.value.reason, str) and excinfo.value.reason


class TestDocuments:
    def test_response_becomes_document_with_text_and_status(self):
        doc = parse_warc(_response_record())[0]
        assert doc.record_type == "response"
        assert doc.url == "https://acme.example/report"
        assert doc.http_status == 200
        assert doc.content_type == "text/html"
        assert doc.charset == "utf-8"
        assert doc.has_text
        assert "CVE-2021-44228" in doc.text

    def test_envelope_content_type_never_leaks_as_document_type(self):
        # The record's own Content-Type is application/http; the page's is text/html.
        assert parse_warc(_response_record())[0].content_type == "text/html"

    def test_payload_digest_verified(self):
        doc = parse_warc(_response_record())[0]
        assert doc.digest_verified is True
        assert doc.warc_digest.startswith("sha1:")

    def test_digest_mismatch_reported_honestly(self):
        data = build_record(
            "response",
            http_response(PAGE),
            extra_headers=f"WARC-Payload-Digest: sha1:{sha1_b32(b'other')}\r\n",
        )
        assert parse_warc(data)[0].digest_verified is False

    def test_absent_digest_reports_none_not_pass(self):
        assert parse_warc(build_record("response", http_response(b"x")))[0].digest_verified is None

    def test_warcinfo_is_not_a_document(self):
        data = build_record(
            "warcinfo",
            b"software: crawler/1.0\r\n",
            content_type="application/warc-fields",
        )
        assert parse_warc(data) == []

    def test_warcinfo_metadata_exposed_separately(self):
        data = build_record(
            "warcinfo",
            b"software: crawler/1.0\r\nhostname: acme.example\r\n",
            content_type="application/warc-fields",
        ) + _response_record()
        info = parse_warc_info(data)
        assert info is not None
        assert info.software == "crawler/1.0"
        assert info.host == "acme.example"

    def test_request_record_is_not_a_document(self):
        assert parse_warc(build_record("request", b"GET / HTTP/1.1\r\nHost: a\r\n\r\n")) == []

    def test_revisit_surfaces_as_payloadless_document(self):
        data = build_record(
            "revisit",
            b"",
            uri="https://acme.example/report",
            record_id="<urn:uuid:00000000-0000-0000-0000-000000000009>",
            extra_headers="WARC-Refers-To: <urn:uuid:original>\r\n"
            "WARC-Profile: http://netpreserve.org/warc/1.0/revisit/identical-payload-digest\r\n",
        )
        doc = parse_warc(data)[0]
        assert doc.is_revisit is True
        assert doc.revisit_of == "<urn:uuid:original>"
        assert doc.text == ""
        assert "revisit_no_payload" in doc.notes
        assert doc.has_text is False

    def test_resource_record_has_no_http_envelope(self):
        data = build_record(
            "resource",
            b"raw bytes, no status line",
            uri="https://acme.example/thing",
            content_type="text/plain",
        )
        doc = parse_warc(data)[0]
        assert doc.record_type == "resource"
        assert doc.http_status is None
        assert doc.text == "raw bytes, no status line"

    def test_error_status_noted_but_still_a_document(self):
        doc = parse_warc(_response_record(status="HTTP/1.1 404 Not Found"))[0]
        assert doc.http_status == 404
        assert "http_error_status:404" in doc.notes

    def test_gzip_content_encoding_is_decoded(self):
        block = http_response(
            gzip.compress(PAGE),
            content_type="text/html",
            extra_headers="Content-Encoding: gzip\r\n",
        )
        doc = parse_warc(build_record("response", block))[0]
        assert doc.text.strip().startswith("<html>")

    def test_deflate_content_encoding_decoded(self):
        block = http_response(
            zlib.compress(PAGE),
            content_type="text/html",
            extra_headers="Content-Encoding: deflate\r\n",
        )
        doc = parse_warc(build_record("response", block))[0]
        assert doc.text.strip().startswith("<html>")
        assert doc.body_sha256 == hashlib.sha256(PAGE).hexdigest()


class TestDeterminism:
    def test_same_bytes_same_documents(self):
        data = _response_record() * 3
        assert [d.to_dict() for d in parse_warc(data)] == [d.to_dict() for d in parse_warc(data)]

    def test_document_id_is_content_derived(self):
        first = parse_warc(_response_record())[0]
        second = parse_warc(_response_record())[0]
        assert first.document_id == second.document_id
        assert first.document_id.startswith("WD-")

    def test_document_id_differs_per_uri(self):
        a = parse_warc(_response_record())[0]
        b = parse_warc(
            build_record("response", http_response(PAGE), uri="https://other.example/report")
        )[0]
        assert a.document_id != b.document_id

    def test_gzip_and_plain_equivalence(self):
        plain = parse_warc(_response_record())[0]
        packed = parse_warc(gzip.compress(_response_record()))[0]
        assert plain.document_id == packed.document_id
        assert plain.text == packed.text


class TestHelpers:
    def test_is_warc_detects_version_line_and_gzip(self):
        assert is_warc(_response_record()) is True
        assert is_warc(gzip.compress(_response_record())) is True
        assert is_warc(b"<html>plain page</html>") is False
        assert is_warc(b"") is False

    def test_parse_http_message_splits_status_headers_body(self):
        msg = parse_http_message(http_response(b"payload"))
        assert msg.status_code == 200
        assert msg.reason == "OK"
        assert msg.header("content-type") == "text/html; charset=utf-8"
        assert msg.body == b"payload"
        assert msg.body_offset > 0

    def test_parse_http_message_without_envelope_returns_whole_block(self):
        msg = parse_http_message(b"just a body")
        assert msg.status_code is None
        assert msg.body == b"just a body"

    def test_verify_payload_digest_accepts_hex_and_base32(self):
        payload = b"digest me"
        assert verify_payload_digest(payload, f"sha256:{hashlib.sha256(payload).hexdigest()}") is True
        assert verify_payload_digest(payload, f"sha1:{sha1_b32(payload)}") is True

    def test_verify_payload_digest_unknown_algorithm_is_none(self):
        assert verify_payload_digest(b"x", "crc32:deadbeef") is None
        assert verify_payload_digest(b"x", None) is None
        assert verify_payload_digest(b"x", "sha1:") is None

    def test_document_from_record_returns_none_for_non_entity(self):
        rec = next(
            iter_records(
                build_record("metadata", b"x", content_type="application/warc-fields")
            )
        )
        assert document_from_record(rec) is None

    def test_undecodable_content_encoding_reported_not_guessed(self):
        block = http_response(b"not-really-gzip", extra_headers="Content-Encoding: gzip\r\n")
        doc = parse_warc(build_record("response", block))[0]
        assert any(n.startswith("content_encoding_undecodable") for n in doc.notes)
        assert doc.payload == b""

    def test_unsupported_content_encoding_kept_with_note(self):
        block = http_response(b"\x00\x01binary", extra_headers="Content-Encoding: br\r\n")
        doc = parse_warc(build_record("response", block))[0]
        assert "content_encoding_unsupported:br" in doc.notes
        assert doc.payload == b"\x00\x01binary"

    def test_binary_payload_yields_no_text_but_keeps_record(self):
        data = build_record(
            "response",
            http_response(b"%PDF-1.7\nbinary", content_type="application/pdf"),
        )
        doc = parse_warc(data)[0]
        assert doc.content_type == "application/pdf"
        assert doc.text == ""
        assert "non_text_payload" in doc.notes
        assert doc.body_sha256  # still hashed: the bytes are evidence

    def test_provenance_is_refs_only(self):
        prov = parse_warc(_response_record())[0].provenance()
        assert "payload" not in prov and "text" not in prov
        assert prov["record_id"].startswith("<urn:uuid:")
        assert len(prov["body_sha256"]) == 64
        assert prov["notes"] == list(parse_warc(_response_record())[0].notes)



PAGE = b"<html><body>Contact ops@acme.example about CVE-2021-44228</body></html>"


def _response_record(**kwargs) -> bytes:
    return build_record(
        "response",
        http_response(PAGE, **kwargs),
        uri="https://acme.example/report",
        extra_headers=f"WARC-Payload-Digest: sha1:{sha1_b32(PAGE)}\r\n",
    )
