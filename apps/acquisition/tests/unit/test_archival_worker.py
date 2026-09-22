"""Archival-mode HTTP worker (T106): WARC capture + ARClint-style lint."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))

from worker_http.archival import (  # noqa: E402
    WarcCapture,
    archival_eligible,
    build_warc,
    lint_warc,
    validate_warc,
)


def _captures() -> list[WarcCapture]:
    return [
        WarcCapture(target_uri="https://a.x/page1", payload=b"<h1>one</h1>"),
        WarcCapture(target_uri="https://b.x/page2", payload=b"<h1>two</h1>"),
    ]


def test_build_and_validate_warc() -> None:
    data = build_warc(_captures())
    ok, issues = validate_warc(data)
    assert ok, issues
    assert not [i for i in issues if i.level == "error"]


def test_lint_detects_bad_magic() -> None:
    issues = lint_warc(b"GARBAGE-NOT-A-WARC")
    assert any(i.level == "error" and "magic" in i.message for i in issues)


def test_lint_empty_payload() -> None:
    assert lint_warc(b"")[0].message == "empty warc payload"


def test_lint_missing_required_header() -> None:
    data = build_warc(_captures())
    # Tear out a WARC-Date line to simulate a structurally broken record.
    broken = data.replace(b"WARC-Date", b"XARC-Stamp")
    issues = lint_warc(broken)
    assert any("WARC-Date" in i.message for i in issues)


def test_lint_warns_first_record_not_warcinfo() -> None:
    data = build_warc(_captures())
    issues = lint_warc(data)
    assert not any(i.level == "error" for i in issues)


def test_truncated_content_length_detected() -> None:
    data = build_warc(_captures())
    truncated = data[:-5]
    issues = lint_warc(truncated)
    assert any(i.level == "error" for i in issues)


def test_archival_eligible_min_bytes() -> None:
    small = WarcCapture(target_uri="https://a.x/", payload=b"x")
    assert archival_eligible(small, min_bytes=10) is False
    big = WarcCapture(target_uri="https://a.x/", payload=b"x" * 64)
    assert archival_eligible(big, min_bytes=10) is True


def test_archival_eligible_html_only() -> None:
    gif = WarcCapture(target_uri="https://a.x/logo.png", payload=b"gif")
    assert archival_eligible(gif, html_only=True) is False
    page = WarcCapture(target_uri="https://a.x/index.html", payload=b"<html/>")
    assert archival_eligible(page, html_only=True) is True