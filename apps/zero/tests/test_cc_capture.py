"""L0 transport tests for ``cc_capture.pull_capture_index`` (hermetic).

No network, no DuckDB: the session seam is a fake ``query_domain`` session
backed by fixture index records (mirrors ``network.cc_session`` records).
"""

from __future__ import annotations

import random

import pytest

from network.cc_session import CCPageRecord
from zero.cc_capture import RawCapture, pull_capture_index

pytestmark = pytest.mark.unit


class FakeSession:
    """Deterministic in-memory stand-in for ``CcIndexSession``."""

    def __init__(self, records: list[CCPageRecord], crawl: str = "CC-MAIN-FIXTURE"):
        self.records = list(records)
        self.crawl = crawl
        self.calls: list[str] = []

    def query_domain(self, url_pattern: str) -> list[CCPageRecord]:
        self.calls.append(url_pattern)
        return list(self.records)


def _rec(url: str, ts: str, digest: str, *, status: int = 200,
         mime: str = "text/html", length: int = 100) -> CCPageRecord:
    return CCPageRecord(
        url=url,
        timestamp=ts,
        status=status,
        mime=mime,
        digest=digest,
        warc_filename="crawldata/0.warc.gz",
        offset=10,
        length=length,
        crawl="CC-MAIN-FIXTURE",
    )


def _records() -> list[CCPageRecord]:
    return [
        _rec("https://www.example.com/c", "20230103120000", "C", length=20),
        _rec("https://example.com/a", "20230101120000", "A", length=40),
        _rec("https://example.com/b", "20230102120000", "B", length=30),
        _rec("https://other.org/x", "20230101120000", "D"),
        _rec("https://example.com/a", "20230115120000", "A2"),
    ]


def test_deterministic_order_and_repeatable() -> None:
    sess = FakeSession(_records())
    first = pull_capture_index("example.com", "domain", None, session=sess)
    second = pull_capture_index("example.com", "domain", None, session=sess)
    assert first == second
    # fake session is domain-agnostic; transport keeps full (url, ts, digest) order
    assert [(r.url, r.timestamp) for r in first] == [
        ("https://example.com/a", "20230101120000"),
        ("https://example.com/a", "20230115120000"),
        ("https://example.com/b", "20230102120000"),
        ("https://other.org/x", "20230101120000"),
        ("https://www.example.com/c", "20230103120000"),
    ]


def test_order_independent_of_upstream_row_order() -> None:
    base = pull_capture_index("example.com", "domain", None, session=FakeSession(_records()))
    rng = random.Random(7)
    for _ in range(5):
        shuffled = _records()
        rng.shuffle(shuffled)
        out = pull_capture_index("example.com", "domain", None, session=FakeSession(shuffled))
        assert out == base


def test_dedup_by_digest_keeps_first_in_order() -> None:
    records = [
        _rec("https://example.com/a", "20230201120000", "DUP"),
        _rec("https://example.com/a", "20230101120000", "DUP"),  # earlier, kept
        _rec("https://example.com/b", "20230102120000", "B"),
    ]
    out = pull_capture_index("example.com", "domain", None, session=FakeSession(records))
    assert [r.timestamp for r in out] == ["20230101120000", "20230102120000"]


def test_limit_stops_mid_batch_and_is_exact() -> None:
    out = pull_capture_index(
        "example.com", "domain", None, session=FakeSession(_records()), limit=2
    )
    assert len(out) == 2
    assert [r.digest for r in out] == ["A", "A2"]


def test_page_size_does_not_change_result() -> None:
    for size in (1, 2, 5, 100):
        assert (
            pull_capture_index(
                "example.com", "domain", None, session=FakeSession(_records()), page_size=size
            )
            == pull_capture_index("example.com", "domain", None, session=FakeSession(_records()))
        )


def test_page_size_batches_across_batches() -> None:
    # limit inside a later batch still stops exactly at the limit boundary.
    out = pull_capture_index(
        "example.com", "domain", None, session=FakeSession(_records()), limit=3, page_size=2
    )
    assert len(out) == 3
    assert [r.digest for r in out] == ["A", "A2", "B"]


def test_invalid_page_size_rejected() -> None:
    with pytest.raises(ValueError):
        pull_capture_index("example.com", "domain", None, session=FakeSession([]), page_size=0)


def test_prefix_match_filters() -> None:
    out = pull_capture_index(
        "example.com/a", "prefix", None, session=FakeSession(_records())
    )
    assert [r.url for r in out] == [
        "https://example.com/a",
        "https://example.com/a",
    ]
    assert {r.digest for r in out} == {"A", "A2"}


def test_empty_query_returns_empty_without_calling_session() -> None:
    sess = FakeSession(_records())
    assert pull_capture_index("", "domain", None, session=sess) == []
    assert pull_capture_index("   ", "domain", None, session=sess) == []
    assert sess.calls == []


def test_non_positive_limit_returns_empty() -> None:
    sess = FakeSession(_records())
    assert pull_capture_index("example.com", "domain", None, limit=0, session=sess) == []
    assert sess.calls == []


def test_raw_capture_carries_collection_and_is_frozen() -> None:
    out = pull_capture_index("example.com", "domain", None, session=FakeSession(_records()))
    assert all(r.collection == "CC-MAIN-FIXTURE" for r in out)
    assert isinstance(out[0], RawCapture)
    assert out[0].status == 200 and out[0].length == 40
    with pytest.raises(Exception):  # noqa: B017, PT011 - frozen dataclass
        out[0].status = 500  # type: ignore[misc]


def test_missing_cc_index_path_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CC_INDEX_PATH", raising=False)
    with pytest.raises(RuntimeError, match="CC_INDEX_PATH"):
        pull_capture_index("example.com", "domain", None, session=None)
